# -*- coding: utf-8 -*-
"""
Event definitions for the Baby Photos Auto-Filter Tool.
事件定义 - 流水线中所有事件的类型与数据结构.

All events emitted during the pipeline lifecycle are defined here.
Modules subscribe to events via EventBus to implement loose coupling.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ==================== Event Type Enum ====================


class EventType(str, Enum):
    """All event types in the system.

    Naming convention: {module}_{action}_{object}
    E.g., crawler_photo_discovered,
          recognizer_photo_matched.
    """

    # Pipeline lifecycle
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"
    PIPELINE_STEP_STARTED = "pipeline.step_started"
    PIPELINE_STEP_COMPLETED = "pipeline.step_completed"

    # Crawler events
    CRAWLER_PHOTO_DISCOVERED = "crawler.photo_discovered"
    CRAWLER_CRAWL_COMPLETED = "crawler.crawl_completed"
    CRAWLER_CRAWL_FAILED = "crawler.crawl_failed"

    # Download events
    DOWNLOAD_STARTED = "download.started"
    DOWNLOAD_COMPLETED = "download.completed"
    DOWNLOAD_FAILED = "download.failed"
    DOWNLOAD_SKIPPED = "download.skipped"  # dedup

    # Recognition events
    RECOGNITION_STARTED = "recognition.started"
    RECOGNITION_COMPLETED = "recognition.completed"
    RECOGNITION_FAILED = "recognition.failed"
    RECOGNITION_TARGET_FOUND = "recognition.target_found"
    RECOGNITION_TARGET_NOT_FOUND = "recognition.target_not_found"

    # Storage events
    STORAGE_STARTED = "storage.started"
    STORAGE_COMPLETED = "storage.completed"
    STORAGE_FAILED = "storage.failed"

    # System events
    COOKIE_EXPIRING = "system.cookie_expiring"
    COOKIE_EXPIRED = "system.cookie_expired"
    DISK_SPACE_WARNING = "system.disk_space_warning"
    DATA_INCONSISTENCY = "system.data_inconsistency"

    # Notification events (internal)
    NOTIFY_NEW_PHOTO = "notify.new_photo"
    NOTIFY_ERROR = "notify.error"
    NOTIFY_DAILY_SUMMARY = "notify.daily_summary"


# ==================== Event Base Class ====================


@dataclass
class Event:
    """Base class for all events.

    Attributes:
        event_type: The EventType enum value.
        timestamp: When the event occurred.
        source: Module name that emitted the event.
        data: Arbitrary event-specific payload.
        run_id: Associated pipeline run ID (if applicable).
    """

    event_type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    run_id: str = ""


# ==================== Concrete Events ====================


@dataclass
class PipelineStartedEvent(Event):
    """Emitted when a pipeline run begins."""

    def __init__(
        self,
        run_id: str,
        trigger_type: str,
        options: Optional[Dict[str, Any]] = None,
        source: str = "orchestrator",
    ):
        super().__init__(
            event_type=EventType.PIPELINE_STARTED,
            run_id=run_id,
            source=source,
            data={
                "trigger_type": trigger_type,
                "options": options or {},
            },
        )


@dataclass
class PipelineCompletedEvent(Event):
    """Emitted when a pipeline run succeeds."""

    def __init__(
        self,
        run_id: str,
        discovered: int = 0,
        downloaded: int = 0,
        target_found: int = 0,
        stored: int = 0,
        duration_seconds: float = 0.0,
        source: str = "orchestrator",
    ):
        super().__init__(
            event_type=EventType.PIPELINE_COMPLETED,
            run_id=run_id,
            source=source,
            data={
                "discovered": discovered,
                "downloaded": downloaded,
                "target_found": target_found,
                "stored": stored,
                "duration_seconds": duration_seconds,
            },
        )


@dataclass
class PipelineFailedEvent(Event):
    """Emitted when a pipeline run fails."""

    def __init__(
        self,
        run_id: str,
        error: str,
        step: str = "",
        source: str = "orchestrator",
    ):
        super().__init__(
            event_type=EventType.PIPELINE_FAILED,
            run_id=run_id,
            source=source,
            data={"error": error, "step": step},
        )


@dataclass
class PhotoDiscoveredEvent(Event):
    """Emitted when a new photo is found by the crawler."""

    def __init__(
        self,
        photo_id: str,
        url: str,
        album_id: str = "",
        run_id: str = "",
        source: str = "crawler",
    ):
        super().__init__(
            event_type=EventType.CRAWLER_PHOTO_DISCOVERED,
            run_id=run_id,
            source=source,
            data={
                "photo_id": photo_id,
                "url": url,
                "album_id": album_id,
            },
        )


@dataclass
class PhotoDownloadedEvent(Event):
    """Emitted when a photo is successfully downloaded."""

    def __init__(
        self,
        photo_id: str,
        local_path: str,
        file_size: int = 0,
        file_hash: str = "",
        run_id: str = "",
        source: str = "downloader",
    ):
        super().__init__(
            event_type=EventType.DOWNLOAD_COMPLETED,
            run_id=run_id,
            source=source,
            data={
                "photo_id": photo_id,
                "local_path": local_path,
                "file_size": file_size,
                "file_hash": file_hash,
            },
        )


@dataclass
class PhotoDownloadSkippedEvent(Event):
    """Emitted when a photo is skipped (duplicate)."""

    def __init__(
        self,
        photo_id: str,
        reason: str = "",
        run_id: str = "",
        source: str = "downloader",
    ):
        super().__init__(
            event_type=EventType.DOWNLOAD_SKIPPED,
            run_id=run_id,
            source=source,
            data={
                "photo_id": photo_id,
                "reason": reason,
            },
        )


@dataclass
class PhotoDownloadFailedEvent(Event):
    """Emitted when a photo download fails."""

    def __init__(
        self,
        photo_id: str,
        error: str,
        run_id: str = "",
        source: str = "downloader",
    ):
        super().__init__(
            event_type=EventType.DOWNLOAD_FAILED,
            run_id=run_id,
            source=source,
            data={
                "photo_id": photo_id,
                "error": error,
            },
        )


@dataclass
class RecognitionCompletedEvent(Event):
    """Emitted after face recognition on a photo."""

    def __init__(
        self,
        photo_id: str,
        contains_target: bool,
        confidence: float = 0.0,
        face_count: int = 0,
        matches: Optional[List[Dict[str, Any]]] = None,
        elapsed_ms: float = 0.0,
        provider_name: str = "",
        run_id: str = "",
        source: str = "recognizer",
    ):
        super().__init__(
            event_type=EventType.RECOGNITION_COMPLETED,
            run_id=run_id,
            source=source,
            data={
                "photo_id": photo_id,
                "contains_target": contains_target,
                "confidence": confidence,
                "face_count": face_count,
                "matches": matches or [],
                "elapsed_ms": elapsed_ms,
                "provider_name": provider_name,
            },
        )


@dataclass
class TargetFoundEvent(Event):
    """Emitted when target person is detected in a photo."""

    def __init__(
        self,
        photo_id: str,
        target_name: str,
        confidence: float,
        run_id: str = "",
        source: str = "recognizer",
    ):
        super().__init__(
            event_type=EventType.RECOGNITION_TARGET_FOUND,
            run_id=run_id,
            source=source,
            data={
                "photo_id": photo_id,
                "target_name": target_name,
                "confidence": confidence,
            },
        )


@dataclass
class PhotoStoredEvent(Event):
    """Emitted when a target photo is saved locally."""

    def __init__(
        self,
        photo_id: str,
        stored_path: str,
        run_id: str = "",
        source: str = "storage",
    ):
        super().__init__(
            event_type=EventType.STORAGE_COMPLETED,
            run_id=run_id,
            source=source,
            data={
                "photo_id": photo_id,
                "stored_path": stored_path,
            },
        )


@dataclass
class CookieExpiringEvent(Event):
    """Emitted when QQ cookie is about to expire."""

    def __init__(
        self,
        days_remaining: int,
        cookie_file: str = "",
        source: str = "crawler",
    ):
        super().__init__(
            event_type=EventType.COOKIE_EXPIRING,
            source=source,
            data={
                "days_remaining": days_remaining,
                "cookie_file": cookie_file,
            },
        )
