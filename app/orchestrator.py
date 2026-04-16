# -*- coding: utf-8 -*-
"""
Main orchestration engine - coordinates all modules into a pipeline.
主流程编排引擎 - 协调采集→下载→识别→存储流水线.

Pipeline flow:

    Trigger
      |
      v
  [Discover Photos] --> [Dedup Check]
      |                      |
      v                      v (new only)
  [Download Photos] --> [Compute Hash]
      |                      |
      v                      v (unique hash)
  [Preprocess Images]
      |
      v
  [Face Recognition]
      |
      +---> [Contains Target?] --Yes--> [Store Locally]
      |                                    |
      +---> No/Skip                       v
                                   [Record Result]
                                      |
                                      v
                                 [Optional Upload]
"""

import asyncio
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config.logging_config import get_logger
from app.config.settings import Settings
from app.database.db import Database
from app.face_recognition.facade import FaceRecognizerFacade
from app.face_recognition.models import TargetConfig
from app.models.photo import (
    DailyMetadata,
    PhotoInfo,
    PhotoStatus,
    ProcessedPhoto,
    SourceType,
    TaskRun,
    TriggerType,
)
from app.preprocessor.image_pipeline import ImagePreprocessor
from app.storage.local_storage import StorageManager
from app.crawler.qq_album_crawler import QQAlbumCrawler, CrawlResult

logger = get_logger(__name__)


class Orchestrator:
    """
    Main orchestrator that coordinates the entire crawl ->
    recognize -> store pipeline.

    Responsibilities:
    - Execute pipeline steps in correct order.
    - Handle deduplication at each stage.
    - Collect statistics and record task runs.
    - Manage errors with retry logic.
    """

    def __init__(
        self,
        settings: Settings,
        database: Database,
        recognizer: FaceRecognizerFacade,
        crawler: QQAlbumCrawler,
        preprocessor: ImagePreprocessor,
        storage_manager: StorageManager,
    ):
        self._settings = settings
        self._db = database
        self._recognizer = recognizer
        self._crawler = crawler
        self._preprocessor = preprocessor
        self._storage = storage_manager
        self._temp_dir = Path("data/temp")
        self._temp_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Orchestrator initialized")

    async def execute(
        self,
        trigger_type: TriggerType,
        options: Optional[Dict[str, Any]] = None,
    ) -> TaskRun:
        """
        Execute the complete photo filtering pipeline.

        Args:
            trigger_type: What triggered this execution.
            options: Additional options like scan_days_back.

        Returns:
            TaskRun with full execution statistics.
        """
        options = options or {}
        run = self._db.create_run(trigger_type.value)
        logger.info(
            "========== PIPELINE STARTED run_id=%s "
            "trigger=%s ==========",
            run.run_id,
            trigger_type.value,
        )
        start_time = time.time()

        try:
            # Step 1: Discover photos from source
            photos_discovered = await self._discover_photos(run, options)
            run.total_discovered = len(photos_discovered)

            if not photos_discovered:
                logger.info("No new photos discovered")
                self._finish_run_successfully(run, start_time)
                return run

            # Step 2: Download new photos
            downloaded = await self._download_photos(
                photos_discovered
            )
            run.total_downloaded = len(downloaded)

            # Step 3: Recognize faces
            recognized = await self._recognize_faces(downloaded)
            run.total_contains_target = sum(
                1 for p in recognized if p.contains_target
            )

            # Step 4: Store target photos locally
            stored = await self._store_photos(recognized)
            run.total_stored = len(stored)

            # Step 5: Write daily metadata
            await self._write_metadata(stored)

            # Update stats for new (non-skipped) photos
            run.total_new = len(downloaded)
            run.total_failed = self._db.count_by_status(PhotoStatus.FAILED)
            run.total_skipped = self._db.count_by_status(PhotoStatus.SKIPPED)

            self._finish_run_successfully(run, start_time)
            logger.info(
                "========== PIPELINE COMPLETED run_id=%s "
                "discovered=%d new=%d target=%d stored=%d "
                "duration=%.1fs ==========",
                run.run_id,
                run.total_discovered,
                run.total_new,
                run.total_contains_target,
                run.total_stored,
                run.duration_seconds or 0,
            )

        except Exception as exc:
            logger.exception("Pipeline failed: %s", exc)
            run.status = "failed"
            run.error_message = str(exc)
            self._db.finish_run(
                run.run_id,
                "failed",
                error_message=str(exc),
                total_discovered=run.total_discovered,
                total_downloaded=run.total_downloaded,
                total_contains_target=run.total_contains_target,
                total_stored=run.total_stored,
                total_failed=run.total_failed,
                total_skipped=run.total_skipped,
            )

        return run

    async def _discover_photos(
        self,
        run: TaskRun,
        options: Dict[str, Any],
    ) -> List[PhotoInfo]:
        """
        Step 1: Crawl source for new photos, dedup by photo_id.
        """
        album_id = self._settings.get("qq.group.album_id", "")

        # Determine time boundary
        since: Optional[datetime] = None
        days_back = options.get("scan_days_back")
        if days_back:
            since = datetime.now() - timedelta(days=int(days_back))

        # Perform crawl
        result: CrawlResult = await self._crawler.crawl_photos(
            album_id=album_id, since=since
        )

        if not result.success:
            logger.error("Photo discovery failed: %s",
                         result.error_message)
            return []

        # Dedup: filter out already-known photos
        new_photos: List[PhotoInfo] = []
        for photo in result.photos:
            if self._db.exists_photo_id(photo.photo_id):
                logger.debug(
                    "Already exists, skipping: %s",
                    photo.photo_id,
                )
            else:
                new_photos.append(photo)

                # Insert pending record
                proc = ProcessedPhoto(
                    photo_id=photo.photo_id,
                    status=PhotoStatus.PENDING,
                    source_type=SourceType.QQ_GROUP_ALBUM,
                    url=photo.url,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
                self._db.insert_photo(proc)

        logger.info(
            "Discovered %d total, %d new photos",
            len(result.photos),
            len(new_photos),
        )
        return new_photos

    async def _download_photos(
        self, photos: List[PhotoInfo],
    ) -> List[ProcessedPhoto]:
        """
        Step 2: Download new photos to temp directory.
        """
        downloaded: List[ProcessedPhoto] = []

        sem = asyncio.Semaphore(5)  # Concurrency limit

        async def _download_one(photo: PhotoInfo) -> Optional[ProcessedPhoto]:
            async with sem:
                temp_path = self._temp_dir / f"{photo.photo_id}.tmp"

                ok = await self._crawler.download_photo(
                    photo, temp_path
                )
                if not ok:
                    self._db.update_photo_status(
                        photo.photo_id,
                        PhotoStatus.FAILED,
                        "Download failed",
                    )
                    return None

                # Compute hash for dedup layer 3
                file_hash = Database.compute_file_hash(temp_path)

                # Hash-level dedup
                if self._db.exists_file_hash(file_hash):
                    logger.debug(
                        "Hash duplicate, skipping: %s",
                        photo.photo_id,
                    )
                    temp_path.unlink(missing_ok=True)
                    self._db.update_photo_status(
                        photo.photo_id,
                        PhotoStatus.SKIPPED,
                        "File hash duplicate",
                    )
                    return None

                # Record download
                proc = ProcessedPhoto(
                    photo_id=photo.photo_id,
                    status=PhotoStatus.DOWNLOADED,
                    source_type=SourceType.QQ_GROUP_ALBUM,
                    url=photo.url,
                    local_path=str(temp_path),
                    file_size=temp_path.stat().st_size,
                    file_hash=file_hash,
                    updated_at=datetime.now(),
                )
                self._db.update_photo_status(
                    photo.photo_id, PhotoStatus.DOWNLOADED
                )
                # Update hash
                self._conn_update_hash(proc)
                return proc

        tasks = [_download_one(p) for p in photos]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, ProcessedPhoto):
                downloaded.append(r)
            elif isinstance(r, Exception):
                logger.error("Download error: %s", r)

        logger.info(
            "Downloaded %d/%d photos successfully",
            len(downloaded), len(photos),
        )
        return downloaded

    def _conn_update_hash(self, proc: ProcessedPhoto) -> None:
        """Update file_hash in DB for existing photo record."""
        conn = self._db.conn
        conn.execute(
            "UPDATE photos SET file_hash=?, local_path=? "
            "WHERE photo_id=?",
            (proc.file_hash, proc.local_path, proc.photo_id),
        )
        conn.commit()

    async def _recognize_faces(
        self, photos: List[ProcessedPhoto],
    ) -> List[ProcessedPhoto]:
        """
        Step 3: Run face recognition on downloaded photos.
        """
        recognized: List[ProcessedPhoto] = []

        for proc in photos:
            try:
                self._db.update_photo_status(
                    proc.photo_id,
                    PhotoStatus.RECOGNIZING,
                )

                t_start = time.time()
                result = await self._recognizer.recognize(
                    proc.local_path or "",
                )
                elapsed_ms = (time.time() - t_start) * 1000

                # Update record with recognition result
                proc.contains_target = result.contains_target
                proc.confidence = result.best_confidence
                proc.face_count = result.total_faces_detected
                proc.provider_name = result.provider_name

                self._db.update_photo_recognition(
                    photo_id=proc.photo_id,
                    contains_target=result.contains_target,
                    confidence=result.best_confidence,
                    face_count=result.total_faces_detected,
                    provider_name=result.provider_name,
                )

                recognized.append(proc)

                logger.debug(
                    "Recognized %s: target=%s conf=%.2f "
                    "faces=%d (%.0fms)",
                    proc.photo_id,
                    result.contains_target,
                    result.best_confidence,
                    result.total_faces_detected,
                    elapsed_ms,
                )

            except Exception as exc:
                logger.error(
                    "Recognition failed for %s: %s",
                    proc.photo_id, exc,
                )
                self._db.update_photo_status(
                    proc.photo_id,
                    PhotoStatus.FAILED,
                    str(exc),
                )

        logger.info(
            "Recognized %d photos, %d contain target",
            len(recognized),
            sum(1 for p in recognized if p.contains_target),
        )
        return recognized

    async def _store_photos(
        self, photos: List[ProcessedPhoto],
    ) -> List[ProcessedPhoto]:
        """
        Step 4: Store photos containing target to local storage.
        """
        stored: List[ProcessedPhoto] = []

        for proc in photos:
            if not proc.contains_target:
                self._db.update_photo_status(
                    proc.photo_id, PhotoStatus.COMPLETED
                )
                continue

            try:
                source_path = Path(proc.local_path or "")
                stored_path = self._storage.store_photo(source_path)

                if stored_path:
                    proc.stored_path = str(stored_path)
                    proc.status = PhotoStatus.STORED

                    self._db.update_photo_stored(
                        proc.photo_id,
                        str(stored_path),
                        PhotoStatus.COMPLETED,
                    )

                    # Clean up temp file
                    source_path.unlink(missing_ok=True)
                    stored.append(proc)

            except Exception as exc:
                logger.error(
                    "Storage failed for %s: %s",
                    proc.photo_id, exc,
                )
                self._db.update_photo_status(
                    proc.photo_id, PhotoStatus.FAILED, str(exc)
                )

        logger.info(
            "Stored %d target photos to local storage",
            len(stored),
        )
        return stored

    async def _write_metadata(
        self, photos: List[ProcessedPhoto],
    ) -> None:
        """
        Step 5: Write daily metadata.json summaries.
        """
        if not photos:
            return

        # Group by date
        by_date: Dict[date, List[ProcessedPhoto]] = {}
        for p in photos:
            pdate = date.today()  # Could extract from upload_time
            by_date.setdefault(pdate, []).append(p)

        for pdate, plist in by_date.items():
            meta = DailyMetadata(
                date=pdate.isoformat(),
                total_photos=len(plist),
                target_photos=sum(
                    1 for p in plist if p.contains_target
                ),
                process_time=datetime.now().isoformat(),
                photos=[
                    {
                        "filename": Path(
                            p.stored_path or ""
                        ).name,
                        "confidence": p.confidence,
                        "face_count": p.face_count,
                    }
                    for p in plist
                ],
            )
            self._storage.write_daily_metadata(meta)

    def _finish_run_successfully(
        self, run: TaskRun, start_time: float,
    ) -> None:
        """Finalize a successful run."""
        run.finished_at = datetime.now()
        run.status = "completed"
        self._db.finish_run(
            run.run_id,
            "completed",
            total_discovered=run.total_discovered,
            total_new=run.total_new,
            total_downloaded=run.total_downloaded,
            total_contains_target=run.total_contains_target,
            total_stored=run.total_stored,
            total_failed=run.total_failed,
            total_skipped=run.total_skipped,
        )
