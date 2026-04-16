# -*- coding: utf-8 -*-
"""
Personal QQ Album Uploader.
个人QQ相册自动上传模块 - 将筛选后的照片上传到个人相册.

Features:
    - Auto-create monthly albums (e.g., "2026年04月宝宝照片")
    - Dedup via UploadDedupQueue (personal_photo_id)
    - Retry with exponential backoff (max 3 retries)
    - Batch upload support with concurrency control
    - Visibility control (self_only / family)

Config (from config.yaml):
    qq:
      personal:
        enabled: true/false
        album_prefix: "{year}年{month}月宝宝照片"
        visibility: "self_only"
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from app.config.logging_config import get_logger
from app.core.retry import RetryHandler
from app.core.upload_queue import UploadDedupQueue

logger = get_logger(__name__)

# Default timeout settings
_UPLOAD_TIMEOUT = aiohttp.ClientTimeout(total=120)
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

# QQ Personal Album API endpoints
_QZONE_BASE = "https://photo.qzone.qq.com"


@dataclass
class UploadTask:
    """A single photo upload task."""
    local_path: Path
    source_photo_id: str
    target_name: str = ""
    confidence: float = 0.0
    upload_date: datetime = field(default_factory=datetime.now)
    # Filled after successful upload
    remote_album_id: str = ""
    remote_photo_id: str = ""
    error_message: str = ""
    retry_count: int = 0


@dataclass
class UploadResult:
    """Result of an upload operation."""
    success: bool
    total_attempted: int = 0
    total_success: int = 0
    total_skipped: int = 0  # Already uploaded (dedup)
    total_failed: int = 0
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class PersonalAlbumUploader:
    """
    Uploads filtered photos to user's personal QQ album.

    Workflow:
        1. Check dedup queue -> skip if already uploaded
        2. Resolve or create target album for current month
        3. Upload photo via QZone API
        4. Mark success in dedup queue
        5. On failure -> enqueue retry (exponential backoff)
    """

    def __init__(
        self,
        cookies_file: str = "data/qq_cookies.txt",
        album_prefix: str = "{year}年{month}月宝宝照片",
        visibility: str = "self_only",
        dedup_queue: Optional[UploadDedupQueue] = None,
        max_retries: int = 3,
        concurrent_uploads: int = 3,
        enabled: bool = False,
    ):
        self._cookies_file = Path(cookies_file)
        self._album_prefix = album_prefix
        self._visibility = visibility
        self._dedup_queue = dedup_queue
        self._max_retries = max_retries
        self._concurrent = concurrent_uploads
        self._enabled = enabled

        self._cookies: Dict[str, str] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._retry_handler = RetryHandler(
            max_retries=max_retries,
            base_delay=2.0,
            max_delay=30.0,
            jitter=True,
        )
        # Cache: month_key -> album_id
        self._album_cache: Dict[str, str] = {}

    @property
    def is_enabled(self) -> bool:
        return self._enabled and bool(self._dedup_queue)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session with cookies loaded."""
        if self._session is None or self._session.closed:
            await self._load_cookies()
            jar = aiohttp.CookieJar(unsafe=True)
            self._session = aiohttp.ClientSession(
                cookie_jar=jar,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 "
                        "Safari/537.36"
                    ),
                    "Accept": "*/*",
                    "Referer": "https://qzone.qq.com/",
                },
                timeout=_REQUEST_TIMEOUT,
            )
            for name, value in self._cookies.items():
                jar.update_cookies({name: value})
        return self._session

    async def _load_cookies(self) -> None:
        """Load cookies from file (same format as crawler)."""
        if not self._cookies_file.exists():
            logger.warning(
                "Cookies file not found: %s", self._cookies_file,
            )
            return

        try:
            content = self._cookies_file.read_text(
                encoding="utf-8",
            )
            for line in content.strip().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "\t" in line:
                    parts = line.split("\t")
                    if len(parts) >= 7:
                        self._cookies[parts[5]] = parts[6]
                elif "=" in line:
                    key, _, val = line.partition("=")
                    self._cookies[key.strip()] = val.strip()
            logger.debug(
                "Uploader loaded %d cookies", len(self._cookies),
            )
        except Exception as exc:
            logger.error("Failed to load cookies: %s", exc)

    async def _resolve_album_id(
        self, session: aiohttp.ClientSession,
        date_obj: datetime,
    ) -> str:
        """
        Get or create album ID for the given date.

        Album naming follows the configured prefix pattern.
        Caches resolved IDs to avoid repeated API calls.
        """
        month_key = date_obj.strftime("%Y-%m")

        if month_key in self._album_cache:
            return self._album_cache[month_key]

        album_name = self._album_prefix.format(
            year=date_obj.year,
            month=f"{date_obj.month:02d}",
            month_name=self._get_month_name(date_obj.month),
        )

        try:
            # Try to find existing album by name
            url = f"{_QZONE_BASE}/cgi-bin/app/list_album"
            params = {"format": "json", "num": 100}

            async with session.get(url, params=params) as resp:
                data = await resp.json()

            if data.get("code") == 0:
                for alb in data.get("data", {}).get(
                    "albumList", [],
                ):
                    if alb.get("name", "") == album_name:
                        album_id = str(alb.get("id", ""))
                        self._album_cache[
                            month_key
                        ] = album_id
                        logger.debug(
                            "Found existing album: %s (%s)",
                            album_name, album_id,
                        )
                        return album_id

            # Not found -> create new album
            album_id = await self._create_album(
                session, album_name,
            )
            self._album_cache[month_key] = album_id
            return album_id

        except Exception as exc:
            logger.error(
                "Failed to resolve album for %s: %s",
                month_key, exc,
            )
            return ""

    async def _create_album(
        self,
        session: aiohttp.ClientSession,
        album_name: str,
    ) -> str:
        """Create a new album in QZone."""
        url = f"{_QZONE_BASE}/cgi-bin/app/add_album"
        payload = {
            "format": "json",
            "name": album_name,
            "desc": (
                f"Auto-created by BabyPhotos "
                f"Crawler on {datetime.now():%Y-%m-%d}"
            ),
            "priv": (
                "3" if self._visibility == "self_only" else "1"
            ),  # 3=private, 1=friends
        }

        async with session.post(url, data=payload) as resp:
            data = await resp.json()

        if data.get("code") == 0:
            album_id = str(data.get("data", {}).get("id", ""))
            logger.info("Created new album: %s (%s)", album_name, album_id)
            return album_id

        logger.error(
            "Failed to create album '%s': %s",
            album_name, data.get("msg", ""),
        )
        return ""

    async def _upload_single(
        self,
        session: aiohttp.ClientSession,
        task: UploadTask,
    ) -> bool:
        """Upload a single photo to the target album."""
        if not task.local_path.exists():
            task.error_message = f"File not found: {task.local_path}"
            return False

        # Resolve album
        album_id = await self._resolve_album_id(
            session, task.upload_date,
        )
        if not album_id:
            task.error_message = "Could not resolve/create album"
            return False

        try:
            url = f"{_QZONE_BASE}/cgi-bin/app/upload_pic"
            form_data = aiohttp.FormData()
            form_data.add_field(
                "format", "json",
            )
            form_data.add_field(
                "albumid", album_id,
            )
            form_data.add_field(
                "picdesc", (
                    f"[{task.target_name}] "
                    f"confidence={task.confidence:.0%}"
                ),
            )

            file_content = task.local_path.read_bytes()
            form_data.add_field(
                "file",
                file_content,
                filename=task.local_path.name,
                content_type="image/jpeg",
            )

            async with session.post(
                url,
                data=form_data,
                timeout=_UPLOAD_TIMEOUT,
            ) as resp:
                result = await resp.json()

            if result.get("code") == 0:
                task.remote_album_id = album_id
                task.remote_photo_id = str(
                    result.get("data", {}).get("photoid", ""),
                )
                logger.debug(
                    "Uploaded %s -> album=%s pid=%s",
                    task.local_path.name,
                    album_id,
                    task.remote_photo_id[:16],
                )
                return True
            else:
                task.error_message = (
                    f"API error {result.get('code')}: "
                    f"{result.get('msg', '')}"
                )
                return False

        except asyncio.TimeoutError:
            task.error_message = "Upload timed out"
            return False
        except Exception as exc:
            task.error_message = str(exc)
            return False

    async def upload_photos(
        self,
        tasks: List[UploadTask],
    ) -> UploadResult:
        """
        Upload multiple photos with dedup and retry.

        Args:
            tasks: List of UploadTask objects to process.

        Returns:
            UploadResult with statistics.
        """
        start_time = asyncio.get_event_loop().time()
        result = UploadResult(success=True)

        if not tasks:
            result.total_attempted = 0
            return result

        if not self.is_enabled:
            logger.info("Personal album upload is disabled")
            result.success = True
            return result

        session = await self._get_session()

        # Phase 1: Dedup check and build actual work list
        pending_tasks: List[UploadTask] = []
        for task in tasks:
            pid = self._make_personal_pid(task)
            if self._dedup_queue.should_upload(pid):
                pending_tasks.append(task)
            else:
                result.total_skipped += 1
                logger.debug(
                    "Skipping already uploaded: %s", pid,
                )

        if not pending_tasks:
            result.total_attempted = len(tasks)
            logger.info(
                "All %d photos already uploaded (skipped)",
                len(tasks),
            )
            return result

        result.total_attempted = len(tasks)

        # Phase 2: Concurrent upload with semaphore
        semaphore = asyncio.Semaphore(self._concurrent)

        async def _process_with_retry(
            task: UploadTask,
        ) -> bool:
            """Process one task with retry logic."""
            async with semaphore:
                for attempt in range(self._max_retries):
                    if await self._upload_single(session, task):
                        # Success -> record in dedup
                        pid = self._make_personal_pid(task)
                        self._dedup_queue.mark_uploaded(
                            personal_photo_id=pid,
                            source_photo_id=task.source_photo_id,
                            remote_album_id=task.remote_album_id,
                            remote_file_id=task.remote_photo_id,
                        )
                        return True
                    # Failure path
                    task.retry_count = attempt + 1
                    if attempt < self._max_retries - 1:
                        delay = self._retry_handler.get_delay(
                            attempt + 1,
                        )
                        logger.warning(
                            "Upload failed for %s (attempt %d/%d), "
                            "retry in %.1fs: %s",
                            task.local_path.name,
                            attempt + 1,
                            self._max_retries,
                            delay,
                            task.error_message,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "Upload permanently failed after "
                            "%d attempts: %s",
                            self._max_retries,
                            task.error_message,
                        )
                return False

        # Process all tasks concurrently
        coros = [
            _process_with_retry(t) for t in pending_tasks
        ]
        outcomes = await asyncio.gather(*coros, return_exceptions=True)

        for i, outcome in enumerate(outcomes):
            if isinstance(outcome, Exception) or not outcome:
                result.total_failed += 1
                err_msg = (
                    str(outcome)
                    if isinstance(outcome, Exception)
                    else pending_tasks[i].error_message
                )
                result.errors.append(err_msg)
            else:
                result.total_success += 1

        elapsed = asyncio.get_event_loop().time() - start_time
        result.duration_seconds = elapsed
        result.success = result.total_failed == 0

        logger.info(
            "Upload batch complete: %d success, %d skipped, "
            "%d failed, %.1fs",
            result.total_success,
            result.total_skipped,
            result.total_failed,
            elapsed,
        )

        return result

    @staticmethod
    def _make_personal_pid(task: UploadTask) -> str:
        """Generate unique personal_photo_id from task info."""
        return (
            f"pp_{task.source_photo_id}_"
            f"{task.upload_date:%Y%m%d}"
        )

    @staticmethod
    def _get_month_name(month: int) -> str:
        """Return Chinese month name."""
        months = {
            1: "一月", 2: "二月", 3: "三月",
            4: "四月", 5: "五月", 6: "六月",
            7: "七月", 8: "八月", 9: "九月",
            10: "十月", 11: "十一月", 12: "十二月",
        }
        return months.get(month, "")

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None


def create_uploader_from_config(
    config: dict,
    dedup_queue: Optional[UploadDedupQueue] = None,
) -> PersonalAlbumUploader:
    """Factory: create uploader from config dict."""
    qq_cfg = config.get("qq", {})
    personal_cfg = qq_cfg.get("personal", {})

    return PersonalAlbumUploader(
        cookies_file=qq_cfg.get("group", {}).get(
            "cookies_file",
            "data/qq_cookies.txt",
        ),
        album_prefix=personal_cfg.get(
            "album_prefix",
            "{year}年{month}月宝宝照片",
        ),
        visibility=personal_cfg.get("visibility", "self_only"),
        dedup_queue=dedup_queue,
        max_retries=3,
        concurrent_uploads=3,
        enabled=personal_cfg.get("enabled", False),
    )
