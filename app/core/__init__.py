# -*- coding: utf-8 -*-
"""
Core infrastructure module.
核心基础设施模块.

Contains:
    - EventBus: Publish-Subscribe event bus
    - Event types: All domain events definitions
    - Metrics: Structured metrics collection (Counter/Gauge/Histogram)
    - MetricsEventListener: Auto-collect metrics from EventBus
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
from app.core.metrics import (
    MetricsCollector,
    MetricsDB,
    get_metrics,
    init_metrics,
)
from app.core.metrics_listener import MetricsEventListener
from app.core.review_pool import (
    DualThresholdConfig,
    ReviewItem,
    ReviewPool,
    ReviewReason,
    ReviewStatus,
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
    "MetricsCollector",
    "MetricsDB",
    "MetricsEventListener",
    "get_metrics",
    "init_metrics",
    "ReviewPool",
    "ReviewItem",
    "DualThresholdConfig",
    "ReviewReason",
    "ReviewStatus",
]
