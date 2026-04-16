# -*- coding: utf-8 -*-
"""
Pluggable album crawler interface + registry + facade.
采集器可插拔架构 - 对齐人脸识别的设计模式.

Architecture mirrors face_recognition module:
    IAlbumCrawler   (interface)
      |
      +-- QQAlbumCrawler (existing implementation)
      +-- [Future providers]
    CrawlerRegistry  (factory + registration)
    CrawlerFacade     (unified entry point)
"""

import abc
import dataclasses
import importlib
import logging
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.config.logging_config import get_logger

logger = get_logger(__name__)


# ==================== Enums & Models ====================


class CrawlerType(Enum):
    """Supported crawler types."""
    QQ_GROUP_ALBUM = "qq_group_album"
    PERSONAL_ALBUM = "personal_album"
    CUSTOM = "custom"


@dataclass
class CrawlerInfo:
    """Crawler capability description."""

    crawler_type: CrawlerType
    display_name: str
    version: str
    supports_incremental: bool
    max_concurrent_downloads: int
    description: str = ""


@dataclass
class CrawlResult:
    """Result of a crawl operation."""

    success: bool
    photos: list  # List of PhotoInfo objects
    total_count: int = 0
    has_more: bool = False
    cursor: str = ""
    error_message: str = ""

    def __len__(self):
        return len(self.photos)


@dataclass
class PhotoInfo:
    """Photo metadata from source."""

    photo_id: str
    url: str
    album_id: str = ""
    title: str = ""
    upload_time: str = ""
    file_size: int = 0
    thumbnail_url: str = ""
    extra: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}


@dataclass
class DownloadResult:
    """Result of downloading one photo."""

    photo_id: str
    success: bool
    local_path: str = ""
    file_size: int = 0
    error_message: str = ""


# ==================== Interface ====================


class IAlbumCrawler(abc.ABC):
    """
    Abstract interface for album crawlers.

    All crawler implementations must inherit from this class.
    """

    @property
    @abc.abstractmethod
    def crawler_type(self) -> CrawlerType:
        """Return the crawler type identifier."""
        pass

    @property
    @abc.abstractmethod
    def info(self) -> CrawlerInfo:
        """Return crawler capability description."""
        pass

    @abc.abstractmethod
    async def authenticate(self, **credentials: Any) -> bool:
        """
        Authenticate with the source platform.

        Args:
            **credentials: Platform-specific auth params
                         (e.g., cookie string for QQ).
        Returns:
            Whether authentication succeeded.
        """
        pass

    @abc.abstractmethod
    async def crawl_photos(
        self,
        album_id: str = "",
        since: Optional[Any] = None,
        limit: int = 100,
        cursor: str = "",
    ) -> CrawlResult:
        """
        Discover photos from the source.

        Args:
            album_id: Target album (empty = all albums).
            since: Only photos after this datetime.
            limit: Max photos to return per call.
            cursor: Pagination cursor for incremental.

        Returns:
            CrawlResult with discovered PhotoInfo objects.
        """
        pass

    @abc.abstractmethod
    async def download_photo(
        self,
        photo: PhotoInfo,
        destination: Path,
    ) -> DownloadResult:
        """
        Download a single photo to destination path.

        Args:
            photo: The photo metadata to download.
            destination: Local path to save the file.

        Returns:
            DownloadResult with status and local path.
        """
        pass

    @abc.abstractmethod
    async def download_batch(
        self,
        photos: List[PhotoInfo],
        dest_dir: Path,
        concurrency: int = 5,
    ) -> List[DownloadResult]:
        """
        Download multiple photos concurrently.

        Results are in same order as input photos.
        """
        pass

    @abc.abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check crawler connection/auth status."""
        pass

    @abc.abstractmethod
    async def cleanup(self) -> None:
        """Release resources on shutdown."""
        pass


# ==================== Registry ====================


class CrawlerRegistry:
    """
    Singleton registry for crawler implementations.

    Mirrors FaceRecognizerRegistry pattern.
    """

    _instance: Optional["CrawlerRegistry"] = None
    _crawlers: Dict[CrawlerType, type] = {}

    def __init__(self):
        self._register_builtin()

    @classmethod
    def get_instance(cls) -> "CrawlerRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(
        self,
        crawler_type: CrawlerType,
        crawler_class: type,
    ) -> None:
        if not issubclass(crawler_class, IAlbumCrawler):
            raise TypeError(
                f"{crawler_class.__name__} must implement "
                f"IAlbumCrawler"
            )
        self._crawlers[crawler_type] = crawler_class
        logger.debug(
            "Registered crawler: %s", crawler_type.value,
        )

    def create(
        self,
        crawler_type: CrawlerType,
        **config_kwargs: Any,
    ) -> IAlbumCrawler:
        if crawler_type not in self._crawlers:
            available = [ct.value for ct in self._crawlers]
            raise ValueError(
                f"Unknown crawler: {crawler_type}. "
                f"Available: {available}"
            )

        cls = self._crawlers[crawler_type]
        instance = cls(**config_kwargs)
        logger.info(
            "Created crawler: %s (%s)",
            crawler_type.value,
            cls.__name__,
        )
        return instance

    def _register_builtin(self) -> None:
        builtin_mappings = {
            CrawlerType.QQ_GROUP_ALBUM:
                ("app.crawler.qq_album_crawler",
                 "QQAlbumCrawler"),
        }

        for ctype, (mod_name, cls_name) in builtin_mappings.items():
            try:
                mod = importlib.import_module(mod_name)
                cls = getattr(mod, cls_name)
                self.register(ctype, cls)
            except ImportError as exc:
                logger.debug(
                    "Builtin crawler %s not available: %s",
                    ctype.value, exc,
                )


# ==================== Facade ====================


class CrawlerFacade:
    """
    Facade for unified crawler access.

    Hides which specific crawler is being used behind
    a clean interface.
    """

    def __init__(self, config: Dict[str, Any]):
        self._config = config
        self._registry = CrawlerRegistry.get_instance()
        self._crawler: Optional[IAlbumCrawler] = None
        self._initialize_from_config()

    def _initialize_from_config(self) -> None:
        crawler_name = self._config.get("type", "qq_group_album")
        try:
            ctype = CrawlerType(crawler_name)
        except ValueError:
            logger.warning(
                "Unknown crawler type '%s', defaulting to "
                "qq_group_album",
                crawler_name,
            )
            ctype = CrawlerType.QQ_GROUP_ALBUM

        crawler_config = self._config.get("settings", {})
        self._crawler = self._registry.create(ctype, **crawler_config)
        logger.info(
            "CrawlerFacade initialized: type=%s",
            ctype.value,
        )

    @property
    def crawler(self) -> IAlbumCrawler:
        if self._crawler is None:
            raise RuntimeError("Crawler not initialized")
        return self._crawler

    async def authenticate(self, **creds: Any) -> bool:
        return await self.crawler.authenticate(**creds)

    async def crawl_photos(self, **kwargs: Any) -> CrawlResult:
        return await self.crawler.crawl_photos(**kwargs)

    async def download_photo(
        self, photo: PhotoInfo, dest: Path,
    ) -> DownloadResult:
        return await self.crawler.download_photo(photo, dest)

    async def download_batch(
        self, photos: List[PhotoInfo], dest_dir: Path,
        concurrency: int = 5,
    ) -> List[DownloadResult]:
        return await self.crawler.download_batch(
            photos, dest_dir, concurrency,
        )

    async def health_check(self) -> Dict[str, Any]:
        return await self.crawler.health_check()

    async def cleanup(self) -> None:
        if self._crawler:
            await self._crawler.cleanup()
