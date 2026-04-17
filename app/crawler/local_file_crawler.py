# -*- coding: utf-8 -*-
"""
Local Directory Crawler - read photos from a local folder.
本地目录采集器 - 从指定目录读取照片文件.

This crawler reads image files from a local directory and
exposes them through the same IAlbumCrawler interface as
QQAlbumCrawler, enabling pluggable data sources.
"""

import asyncio
import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config.logging_config import get_logger
from app.crawler.qq_album_crawler import (
    IAlbumCrawler,
    AlbumInfo,
    CrawlResult,
)
from app.models.photo import PhotoInfo, SourceType

logger = get_logger(__name__)

# Supported image extensions
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


@dataclass
class LocalFileConfig:
    """Configuration for local file crawler."""
    source_dir: str = ""          # Source directory path
    recursive: bool = True        # Scan subdirectories


class LocalFileCrawler(IAlbumCrawler):
    """
    Crawler that reads photos from a local directory.

    Instead of downloading from QQ album API, this crawler
    directly accesses files on the local filesystem.
    """

    def __init__(self, config: Optional[LocalFileConfig] = None):
        self._config = config or LocalFileConfig()
        self._source_path = Path(self._config.source_dir) if self._config.source_dir else Path(".")
        logger.info(
            "LocalFileCrawler initialized: source=%s recursive=%s",
            self._source_path,
            self._config.recursive,
        )

    async def list_albums(self) -> List[AlbumInfo]:
        """List subdirectories as virtual albums."""
        if not self._source_path.exists():
            return []

        albums: List[AlbumInfo] = []
        try:
            for item in sorted(self._source_path.iterdir()):
                if item.is_dir():
                    # Count images in this subdir
                    photo_count = sum(
                        1 for _ in self._scan_images(item)
                        if _
                    )
                    if photo_count > 0:
                        albums.append(AlbumInfo(
                            album_id=item.name,
                            album_name=item.name,
                            photo_count=photo_count,
                            created_at=datetime.fromtimestamp(
                                item.stat().st_ctime
                            ),
                        ))
        except Exception as exc:
            logger.error("Failed to list albums: %s", exc)

        return albums

    def _scan_images(self, base_path: Path):
        """Generator yielding image file paths."""
        if self._config.recursive:
            pattern = "**/*"
        else:
            pattern = "*"

        try:
            for f in base_path.glob(pattern):
                if (
                    f.is_file()
                    and f.suffix.lower() in SUPPORTED_EXTENSIONS
                ):
                    yield f
        except Exception:
            pass

    async def crawl_photos(
        self,
        album_id: str = "",
        since: Optional[datetime] = None,
    ) -> CrawlResult:
        """
        Scan local directory for photos.

        Args:
            album_id: Subdirectory name (empty = scan all).
            since: Filter by file modification time.
        """
        photos: List[PhotoInfo] = []

        if not self._source_path.exists():
            return CrawlResult(
                success=False,
                error_message=(
                    f"Source directory does not exist: "
                    f"{self._source_path}"
                ),
            )

        # Determine scan root
        scan_root = self._source_path / album_id if album_id else self._source_path

        if not scan_root.exists():
            return CrawlResult(
                success=False,
                error_message=f"Directory does not exist: {scan_root}",
            )

        # Scan for image files
        seen_files: set = set()
        for img_path in self._scan_images(scan_root):
            # Use relative path + filename as unique ID
            rel_path = str(img_path.relative_to(self._source_path))
            file_stat = img_path.stat()

            # Time-based filter (using modification time as proxy)
            if since:
                mod_time = datetime.fromtimestamp(file_stat.st_mtime)
                if mod_time < since:
                    continue

            photo = PhotoInfo(
                photo_id=rel_path.replace("\\", "/"),
                album_id=album_id or "default",
                upload_time=datetime.fromtimestamp(
                    file_stat.st_mtime
                ),
                url=str(img_path),           # Local file path as URL
                thumbnail_url="",
                file_size=file_stat.st_size,
            )
            photos.append(photo)
            seen_files.add(rel_path)

        logger.info(
            "LocalFileCrawler scanned: found %d photos in %s",
            len(photos),
            scan_root,
        )

        return CrawlResult(
            success=True,
            photos=photos,
            total_found=len(photos),
        )

    async def download_photo(
        self, photo: PhotoInfo, save_path: Path,
    ) -> bool:
        """
        Copy photo from source location to target path.

        For local files this is just shutil.copy2().
        """
        src_path = Path(photo.url)
        if not src_path.exists():
            logger.error("Source file not found: %s", src_path)
            return False

        save_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(str(src_path), str(save_path))
            return True
        except OSError as exc:
            logger.error("Copy failed: %s -> %s: %s",
                         src_path, save_path, exc)
            return False

    async def health_check(self) -> Dict[str, Any]:
        """Check if source directory is accessible."""
        exists = self._source_path.exists()
        is_dir = self._source_path.is_dir()

        status = "ok" if (exists and is_dir) else "error"

        info: Dict[str, Any] = {
            "status": status,
            "source_type": "local_directory",
            "source_dir": str(self._source_path),
            "accessible": exists and is_dir,
        }

        if exists and is_dir:
            total_images = sum(1 for _ in self._scan_images(self._source_path) if _)
            info["total_photos"] = total_images

        return info

    def close(self) -> None:
        """No resources to release."""
        pass
