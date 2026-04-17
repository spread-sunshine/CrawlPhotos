# -*- coding: utf-8 -*-
"""
Core domain models for the Baby Photos Auto-Filter Tool.
核心领域模型.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


# ==================== Enums ====================


class PhotoStatus(str, Enum):
    """Photo processing lifecycle status."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    PREPROCESSING = "preprocessing"
    RECOGNIZING = "recognizing"
    RECOGNIZED = "recognized"
    STORING = "storing"
    STORED = "stored"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TriggerType(str, Enum):
    """Task trigger type."""
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    EVENT = "event"


class SourceType(str, Enum):
    """Photo source type."""
    QQ_GROUP_ALBUM = "qq_group_album"
    PERSONAL = "personal"
    LOCAL_DIR = "local_directory"


# ==================== Photo Models ====================


@dataclass
class PhotoInfo:
    """
    Photo metadata from source (QQ group album).

    Represents a photo as discovered from the source,
    before any local processing.
    """

    photo_id: str
    album_id: str = ""
    group_id: str = ""
    upload_time: Optional[datetime] = None
    uploader: str = ""
    url: str = ""
    thumbnail_url: str = ""
    file_size: int = 0
    width: int = 0
    height: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "photo_id": self.photo_id,
            "album_id": self.album_id,
            "group_id": self.group_id,
            "upload_time": (
                self.upload_time.isoformat()
                if self.upload_time else None
            ),
            "uploader": self.uploader,
            "url": self.url,
            "thumbnail_url": self.thumbnail_url,
            "file_size": self.file_size,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class ProcessedPhoto:
    """
    A photo that has been fully processed.

    Contains both original metadata and recognition results.
    """

    photo_id: str
    status: PhotoStatus = PhotoStatus.PENDING

    # Source info
    source_type: SourceType = SourceType.QQ_GROUP_ALBUM
    url: str = ""
    thumbnail_url: str = ""

    # File info after download
    local_path: Optional[str] = None
    temp_path: Optional[str] = None  # Downloaded but not yet stored
    file_size: int = 0
    file_hash: Optional[str] = None   # SHA256 hash for dedup

    # Recognition results
    contains_target: bool = False
    confidence: float = 0.0
    face_count: int = 0
    provider_name: str = ""
    processing_time_ms: float = 0.0

    # Storage info
    stored_path: Optional[str] = None
    personal_photo_id: Optional[str] = None  # For upload dedup

    # Timestamps
    created_at: datetime = field(
        default_factory=datetime.now
    )
    updated_at: datetime = field(
        default_factory=datetime.now
    )

    # Error info
    error_message: Optional[str] = None
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "photo_id": self.photo_id,
            "status": self.status.value,
            "source_type": self.source_type.value,
            "url": self.url,
            "local_path": self.local_path,
            "file_hash": self.file_hash,
            "contains_target": self.contains_target,
            "confidence": self.confidence,
            "face_count": self.face_count,
            "provider_name": self.provider_name,
            "stored_path": self.stored_path,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
        }

    def to_storage_row(self) -> tuple:
        """Convert to tuple for SQLite insertion."""
        return (
            self.photo_id,
            self.status.value,
            self.source_type.value,
            self.url,
            self.local_path,
            self.file_size,
            self.file_hash,
            self.contains_target,
            self.confidence,
            self.face_count,
            self.provider_name,
            self.stored_path,
            self.personal_photo_id,
            self.created_at.isoformat(),
            self.updated_at.isoformat(),
            self.error_message,
            self.retry_count,
        )


# ==================== Task / Run Models ====================


@dataclass
class TaskRun:
    """
    A single execution run of the crawl + filter pipeline.
    """

    run_id: str = ""
    trigger_type: TriggerType = TriggerType.MANUAL
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None

    # Statistics
    total_discovered: int = 0
    total_new: int = 0
    total_downloaded: int = 0
    total_contains_target: int = 0
    total_stored: int = 0
    total_failed: int = 0
    total_skipped: int = 0

    # Status
    status: str = "running"  # running / completed / failed
    error_message: Optional[str] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.finished_at is None:
            return None
        return (
            self.finished_at - self.started_at
        ).total_seconds()


@dataclass
class DailyMetadata:
    """
    Daily summary metadata (written as metadata.json).
    """

    date: str
    total_photos: int = 0
    target_photos: int = 0
    source: str = "qq_group_album"
    group_name: str = ""
    uploader: str = ""
    process_time: Optional[str] = None
    photos: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "total_photos": self.total_photos,
            "target_photos": self.target_photos,
            "source": self.source,
            "group_name": self.group_name,
            "uploader": self.uploader,
            "process_time": self.process_time,
            "photos": self.photos,
        }
