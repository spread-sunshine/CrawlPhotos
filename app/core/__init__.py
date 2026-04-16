# -*- coding: utf-8 -*-
"""
Core infrastructure module.
核心基础设施模块.

Contains:
    - EventBus: Publish-Subscribe event bus
    - Event types: All domain events definitions
"""

from app.core.event_bus import EventBus, get_event_bus
from app.core.events import (
    CookieExpiringEvent,
    Event,
    EventType,
    PhotoDownloadFailedEvent,
    PhotoDownloadedEvent,
    PhotoDownloadSkippedEvent,
    PhotoDiscoveredEvent,
    PipelineCompletedEvent,
    PipelineFailedEvent,
    PipelineStartedEvent,
    RecognitionCompletedEvent,
    TargetFoundEvent,
    PhotoStoredEvent,
)

__all__ = [
    "EventBus",
    "get_event_bus",
    "Event",
    "EventType",
    "PipelineStartedEvent",
    "PipelineCompletedEvent",
    "PipelineFailedEvent",
    "PhotoDiscoveredEvent",
    "PhotoDownloadedEvent",
    "PhotoDownloadSkippedEvent",
    "PhotoDownloadFailedEvent",
    "RecognitionCompletedEvent",
    "TargetFoundEvent",
    "PhotoStoredEvent",
    "CookieExpiringEvent",
]
