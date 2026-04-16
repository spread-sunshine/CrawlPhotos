# -*- coding: utf-8 -*-
"""
QQ Group Album Crawler - Cookie-based photo collection.
QQ群相册采集器 - 基于Cookie模拟采集照片列表.

This module provides the base interface and a concrete implementation
for crawling photos from QQ group albums using saved cookies.
"""

import asyncio
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from app.config.logging_config import get_logger
from app.models.photo import PhotoInfo, SourceType

logger = get_logger(__name__)


# ==================== Data Classes ====================


@dataclass
class CrawlResult:
    """Result of a single crawl operation."""
    success: bool
    photos: List[PhotoInfo] = field(default_factory=list)
    error_message: Optional[str] = None
    total_found: int = 0
    crawled_at: datetime = field(default_factory=datetime.now)


@dataclass
class AlbumInfo:
    """Album metadata."""
    album_id: str
    album_name: str = ""
    photo_count: int = 0
    created_at: Optional[datetime] = None


# ==================== Abstract Interface ====================


class IAlbumCrawler(ABC):
    """
    Abstract interface for photo source crawlers.

    All crawlers must implement this to enable pluggable sources
    (QQ Group, WeChat Album, Local Directory, etc.).
    """

    @abstractmethod
    async def list_albums(self) -> List[AlbumInfo]:
        """List available albums."""
        pass

    @abstractmethod
    async def crawl_photos(
        self,
        album_id: str,
        since: Optional[datetime] = None,
    ) -> CrawlResult:
        """
        Crawl new photos from an album.

        Args:
            album_id: Target album ID.
            since: Only fetch photos after this time (incremental).

        Returns:
            CrawlResult with discovered photos.
        """
        pass

    @abstractmethod
    async def download_photo(
        self, photo: PhotoInfo, save_path: Path,
    ) -> bool:
        """
        Download a single photo to local path.

        Args:
            photo: Photo info with URL.
            save_path: Destination file path.

        Returns:
            True if downloaded successfully.
        """
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check if cookies/session is valid."""
        pass


# ==================== QQ Album Crawler Implementation ====================


class QQAlbumCrawler(IAlbumCrawler):
    """
    Concrete crawler for QQ group albums.

    Uses saved cookie file for authentication. Implements
    incremental sync based on upload_time.
    """

    # QQ API endpoints (may need adjustment based on actual API)
    BASE_URL = "https://photo.qzone.qq.com"
    ALBUM_LIST_API = (
        "/cgi-bin/tbg/get_tbg_list?g_tk=&format=json"
    )
    PHOTO_LIST_API = (
        "/cgi-bin/app/list_photo?g_tk=&format=json"
    )

    # Default request headers
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 "
            "Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://qzone.qq.com/",
    }

    # Download timeout in seconds
    DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=60)
    REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

    def __init__(
        self,
        group_id: str,
        cookies_file: str = "data/qq_cookies.txt",
        **kwargs: Any,
    ):
        self._group_id = group_id
        self._cookies_file = Path(cookies_file)
        self._cookies: Dict[str, str] = {}
        self._session: Optional[aiohttp.ClientSession] = None

        logger.info(
            "QQAlbumCrawler initialized: group_id=%s, "
            "cookies=%s",
            group_id,
            self._cookies_file,
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        """Create or return HTTP session with loaded cookies."""
        if self._session is None or self._session.closed:
            await self._load_cookies()
            jar = aiohttp.CookieJar(unsafe=True)
            self._session = aiohttp.ClientSession(
                cookie_jar=jar,
                headers=self.DEFAULT_HEADERS.copy(),
                timeout=self.REQUEST_TIMEOUT,
            )
            # Add cookies from file
            for name, value in self._cookies.items():
                jar.update_cookies({name: value})
        return self._session

    async def _load_cookies(self) -> None:
        """Load cookies from file."""
        if not self._cookies_file.exists():
            logger.warning(
                "Cookies file not found: %s", self._cookies_file
            )
            self._cookies = {}
            return

        try:
            content = self._cookies_file.read_text(
                encoding="utf-8"
            )
            # Support Netscape cookie format or simple key=value
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

            logger.info(
                "Loaded %d cookies from %s",
                len(self._cookies),
                self._cookies_file,
            )
        except Exception as exc:
            logger.error("Failed to load cookies: %s", exc)
            self._cookies = {}

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def list_albums(self) -> List[AlbumInfo]:
        """List albums in the configured QQ group."""
        session = await self._get_session()
        try:
            url = f"{self.BASE_URL}{self.ALBUM_LIST_API}"
            params = {"group_id": self._group_id}

            async with session.get(url, params=params) as resp:
                data = await resp.json()

            if data.get("code") != 0:
                logger.error(
                    "Failed to list albums: %s", data
                )
                return []

            albums = []
            for item in data.get("data", {}).get("albumList", []):
                albums.append(
                    AlbumInfo(
                        album_id=str(item.get("id", "")),
                        album_name=item.get("name", ""),
                        photo_count=item.get("picNum", 0),
                    )
                )

            logger.info("Found %d albums", len(albums))
            return albums

        except Exception as exc:
            logger.error("Error listing albums: %s", exc)
            return []

    async def crawl_photos(
        self,
        album_id: str = "",
        since: Optional[datetime] = None,
    ) -> CrawlResult:
        """
        Crawl photos from a QQ group album.

        Note: This is a skeleton implementation. Actual QQ API
        endpoints and response formats need to be verified against
        the real QQ Zone / Group Album API.
        """
        session = await self._get_session()
        result = CrawlResult(success=False)

        try:
            url = f"{self.BASE_URL}{self.PHOTO_LIST_API}"
            params = {
                "group_id": self._group_id,
                "albumId": album_id,
                "pageNum": 1,
                "pageSize": 100,
            }

            async with session.get(url, params=params) as resp:
                data = await resp.json()

            code = data.get("code", -1)
            if code != 0:
                msg = data.get("msg", "Unknown error")
                logger.error(
                    "Crawl failed (code=%d): %s", code, msg
                )
                result.error_message = f"API error {code}: {msg}"
                return result

            photos_data = data.get("data", {}).get(
                "photoList", []
            )
            photos: List[PhotoInfo] = []

            for p in photos_data:
                upload_time_str = p.get("uploadTime", "")
                upload_time = None
                if upload_time_str:
                    try:
                        upload_time = datetime.fromisoformat(
                            upload_time_str.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    except ValueError:
                        pass

                # Filter by time if specified
                if since and upload_time and upload_time < since:
                    continue

                photo_info = PhotoInfo(
                    photo_id=str(p.get("id", "")),
                    album_id=album_id,
                    group_id=self._group_id,
                    upload_time=upload_time,
                    uploader=p.get("uploaderName", ""),
                    url=p.get("url", p.get("rawUrl", "")),
                    thumbnail_url=p.get(
                        "thumbnailUrl", ""
                    ),
                    file_size=int(p.get("size", 0)),
                    width=int(p.get("width", 0)),
                    height=int(p.get("height", 0)),
                )
                photos.append(photo_info)

            result.success = True
            result.photos = photos
            result.total_found = len(photos)

            logger.info(
                "Crawled %d photos from album=%s",
                len(photos),
                album_id,
            )

        except Exception as exc:
            logger.error("Error during crawl: %s", exc)
            result.error_message = str(exc)

        return result

    async def download_photo(
        self, photo: PhotoInfo, save_path: Path
    ) -> bool:
        """Download a single photo to the given path."""
        session = await self._get_session()

        if not photo.url:
            logger.warning("No URL for photo %s", photo.photo_id)
            return False

        save_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            async with session.get(
                photo.url, timeout=self.DOWNLOAD_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        "Download failed status=%d for %s",
                        resp.status,
                        photo.photo_id,
                    )
                    return False

                content = await resp.read()
                with open(save_path, "wb") as f:
                    f.write(content)

                logger.debug(
                    "Downloaded photo=%s size=%d to %s",
                    photo.photo_id,
                    len(content),
                    save_path,
                )
                return True

        except asyncio.TimeoutError:
            logger.error(
                "Timeout downloading photo=%s", photo.photo_id
            )
            return False
        except Exception as exc:
            logger.error(
                "Error downloading photo=%s: %s",
                photo.photo_id,
                exc,
            )
            return False

    async def health_check(self) -> Dict[str, Any]:
        """Verify that cookies are valid and connection works."""
        session = await self._get_session()
        try:
            start = asyncio.get_event_loop().time()
            async with session.get(
                self.BASE_URL,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                elapsed_ms = (
                    asyncio.get_event_loop().time() - start
                ) * 1000

            return {
                "healthy": True,
                "latency_ms": round(elapsed_ms, 2),
                "message": (
                    "Cookies loaded" if self._cookies else
                    "No cookies"
                ),
            }
        except Exception as exc:
            return {
                "healthy": False,
                "latency_ms": -1,
                "message": str(exc),
            }
