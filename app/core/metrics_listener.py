# -*- coding: utf-8 -*-
"""
Metrics Event Listener - Auto-collect metrics from EventBus events.
指标事件监听器 - 从事件总线自动采集指标.

Subscribes to all pipeline lifecycle events and records
corresponding Counter/Gauge/Histogram metrics.
"""

import time
from typing import Any, Dict

from app.core.event_bus import EventBus
from app.core.events import (
    PhotoDownloadedEvent,
    PhotoDownloadFailedEvent,
    PhotoDownloadSkippedEvent,
    PipelineCompletedEvent,
    PipelineFailedEvent,
    PipelineStartedEvent,
    RecognitionCompletedEvent,
    TargetFoundEvent,
)
from app.core.metrics import get_metrics
from app.config.logging_config import get_logger

logger = get_logger(__name__)


class MetricsEventListener:
    """Listens to EventBus events and auto-records metrics.

    Call bind() after creating an instance to subscribe
    to all relevant event types.
    """

    def __init__(self):
        self._metrics = None

    def _get_metrics(self):
        if self._metrics is None:
            self._metrics = get_metrics()
        return self._metrics

    def bind(self, bus: EventBus) -> None:
        """Subscribe to all pipeline-related events."""
        bus.subscribe(
            "metrics_pipeline_start",
            self._on_pipeline_started,
            event_type="pipeline.started",
        )
        bus.subscribe(
            "metrics_pipeline_complete",
            self._on_pipeline_completed,
            event_type="pipeline.completed",
        )
        bus.subscribe(
            "metrics_pipeline_fail",
            self._on_pipeline_failed,
            event_type="pipeline.failed",
        )
        bus.subscribe(
            "metrics_download_complete",
            self._on_download_completed,
            event_type="download.completed",
        )
        bus.subscribe(
            "metrics_download_fail",
            self._on_download_failed,
            event_type="download.failed",
        )
        bus.subscribe(
            "metrics_download_skip",
            self._on_download_skipped,
            event_type="download.skipped",
        )
        bus.subscribe(
            "metrics_recognition_complete",
            self._on_recognition_completed,
            event_type="recognition.completed",
        )
        bus.subscribe(
            "metrics_target_found",
            self._on_target_found,
            event_type="recognition.target_found",
        )

    # ---- Event handlers ----

    def _on_pipeline_started(self, event: Any) -> None:
        m = self._get_metrics()
        m.record_api_call("system", "pipeline_start")

    def _on_pipeline_completed(self, event: Any) -> None:
        m = self._get_metrics()
        data = getattr(event, 'data', {}) or {}
        trigger_type = data.get('trigger_type', 'manual')
        duration = data.get('duration_seconds', 0)

        m.record_task_completed(trigger_type, "success")
        m.record_pipeline_latency(duration)

        discovered = data.get('discovered', 0)
        target_found = data.get('target_found', 0)
        stored = data.get('stored', 0)

        for _ in range(discovered + stored):
            m.record_photo_processed("success")

        for _ in range(target_found):
            m.record_target_found()

    def _on_pipeline_failed(self, event: Any) -> None:
        m = self._get_metrics()
        data = getattr(event, 'data', {}) or {}
        trigger_type = data.get('trigger_type', 'manual')

        m.record_task_completed(trigger_type, "failed")
        m.record_photo_processed("failed")

    def _on_download_completed(self, event: Any) -> None:
        m = self._get_metrics()
        data = getattr(event, 'data', {}) or {}
        file_size = data.get('file_size', 0)
        # Approximate latency from event timestamp
        m.record_photo_size_kb(file_size / 1024.0 if file_size else 0)
        m.inc_counter("photos_downloaded_total", labels={
            "status": "success"
        })

    def _on_download_failed(self, event: Any) -> None:
        m = self._get_metrics()
        m.inc_counter("photos_downloaded_total", value=1.0,
                      labels={"status": "failed"})

    def _on_download_skipped(self, event: Any) -> None:
        m = self._get_metrics()
        m.inc_counter("photos_downloaded_total", value=1.0,
                      labels={"status": "skipped"})

    def _on_recognition_completed(self, event: Any) -> None:
        m = self._get_metrics()
        data = getattr(event, 'data', {}) or {}

        confidence = data.get('confidence', 0.0)
        face_count = data.get('face_count', 0)
        elapsed_ms = data.get('elapsed_ms', 0.0)
        provider_name = data.get('provider_name', 'unknown')
        contains_target = data.get('contains_target', False)

        m.record_confidence(confidence)
        m.record_face_detected(face_count)

        if elapsed_ms > 0:
            m.record_recognize_latency(elapsed_ms / 1000.0)

        result_label = "target" if contains_target else "no_target"
        m.record_api_call(provider_name, result_label)

    def _on_target_found(self, event: Any) -> None:
        m = self._get_metrics()
        data = getattr(event, 'data', {}) or {}
        target_name = data.get('target_name', 'default')
        confidence = data.get('confidence', 0.0)

        m.record_target_found(target_name)
        m.record_confidence(confidence)
