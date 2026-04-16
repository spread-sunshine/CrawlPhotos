# -*- coding: utf-8 -*-
"""
Structured Metrics Collection System.
结构化指标收集系统.

Provides Prometheus-style metrics (Counter, Gauge, Histogram)
with SQLite persistence, memory cache, and Prometheus export support.
Integrates with EventBus for automatic pipeline event tracking.

Metrics types:
    - Counter: Monotonically increasing value
    - Gauge: Point-in-time snapshot value
    - Histogram: Distribution with configurable buckets
"""

import json
import shutil
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config.logging_config import get_logger

logger = get_logger(__name__)

# Default database path
_DEFAULT_METRICS_DB_PATH = "data/crawl_photos.db"


# ==================== Data Models ====================


@dataclass
class CounterDef:
    """Counter metric definition."""

    name: str
    help: str = ""
    labels: Optional[List[str]] = None


@dataclass
class GaugeDef:
    """Gauge metric definition."""

    name: str
    help: str = ""
    labels: Optional[List[str]] = None


@dataclass
class HistogramDef:
    """Histogram metric definition."""

    name: str
    help: str = ""
    buckets: Optional[List[float]] = None


@dataclass
class MetricValue:
    """A single metric data point with labels."""

    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = datetime.now(timezone.utc).timestamp()


# ==================== MetricsDB ====================


class MetricsDB:
    """Metrics persistence layer using SQLite.

    Stores Counter/Gauge/Histogram values in separate tables
    with time-series support for Gauges.
    Thread-safe: uses a dedicated connection per write operation.
    """

    def __init__(self, db_path: str = _DEFAULT_METRICS_DB_PATH):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS metrics_counter (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        name        TEXT    NOT NULL,
                        value       REAL    NOT NULL DEFAULT 0,
                        labels      TEXT    DEFAULT '{}',
                        updated_at  TEXT    NOT NULL,
                        UNIQUE(name, labels)
                    );

                    CREATE INDEX IF NOT EXISTS idx_counter_name
                        ON metrics_counter(name);

                    CREATE TABLE IF NOT EXISTS metrics_gauge (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        name        TEXT    NOT NULL,
                        value       REAL    NOT NULL DEFAULT 0,
                        labels      TEXT    DEFAULT '{}',
                        updated_at  TEXT    NOT NULL,
                        UNIQUE(name, labels)
                    );

                    CREATE INDEX IF NOT EXISTS idx_gauge_name
                        ON metrics_gauge(name);

                    CREATE TABLE IF NOT EXISTS metrics_histogram (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        name        TEXT    NOT NULL,
                        bucket      REAL    NOT NULL,
                        count       INTEGER NOT NULL DEFAULT 0,
                        labels      TEXT    DEFAULT '{}',
                        sum_value   REAL    NOT NULL DEFAULT 0,
                        count_total INTEGER NOT NULL DEFAULT 0,
                        created_at  TEXT    NOT NULL,
                        UNIQUE(name, bucket, labels)
                    );

                    CREATE INDEX IF NOT EXISTS idx_hist_name
                        ON metrics_histogram(name);
                """)
                conn.commit()
            finally:
                conn.close()

    # ---- Counter operations ----

    def inc_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        label_str = json.dumps(labels or {}, ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO metrics_counter "
                    "(name, value, labels, updated_at) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(name, labels) "
                    "DO UPDATE SET value = value + ?, "
                    "updated_at = ?",
                    (name, value, label_str, value, now),
                )
                conn.commit()
            except Exception as e:
                logger.error("Failed inc_counter %s: %s", name, e)
            finally:
                conn.close()

    def get_counter(self, name: str) -> float:
        label_str = json.dumps({})

        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT value FROM metrics_counter "
                    "WHERE name=? AND labels=?",
                    (name, label_str),
                ).fetchone()
                return row["value"] if row else 0.0
            finally:
                conn.close()

    # ---- Gauge operations ----

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        label_str = json.dumps(labels or {}, ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO metrics_gauge "
                    "(name, value, labels, updated_at) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(name, labels) "
                    "DO UPDATE SET value = ?, updated_at = ?",
                    (name, value, label_str, value, now),
                )
                conn.commit()
            except Exception as e:
                logger.error("Failed set_gauge %s: %s", name, e)
            finally:
                conn.close()

    def get_gauge(self, name: str) -> float:
        label_str = json.dumps({})

        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT value FROM metrics_gauge "
                    "WHERE name=? AND labels=?",
                    (name, label_str),
                ).fetchone()
                return row["value"] if row else 0.0
            finally:
                conn.close()

    # ---- Histogram operations ----

    def observe_histogram(
        self,
        name: str,
        value: float,
        buckets: List[float],
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        label_str = json.dumps(labels or {}, ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()

        sorted_buckets = sorted(buckets)

        with self._lock:
            conn = self._get_conn()
            try:
                for bucket_upper in sorted_buckets:
                    bucket_val = "+Inf" if bucket_upper == float(
                        'inf'
                    ) else bucket_upper
                    if value <= bucket_upper:
                        conn.execute(
                            "INSERT INTO metrics_histogram "
                            "(name, bucket, count, labels, "
                            "sum_value, count_total, created_at) "
                            "VALUES (?, ?, 1, ?, ?, 1, ?) "
                            "ON CONFLICT(name, bucket, labels) "
                            "DO UPDATE SET count = count + 1, "
                            "sum_value = sum_value + ?, "
                            "count_total = count_total + 1",
                            (
                                name,
                                bucket_val,
                                label_str,
                                value,
                                now,
                                value,
                            ),
                        )
                    else:
                        conn.execute(
                            "INSERT INTO metrics_histogram "
                            "(name, bucket, count, labels, "
                            "sum_value, count_total, created_at) "
                            "VALUES (?, ?, 0, ?, ?, 1, ?) "
                            "ON CONFLICT(name, bucket, labels) "
                            "DO UPDATE SET count_total = "
                            "count_total + 1",
                            (
                                name,
                                bucket_val,
                                label_str,
                                value,
                                now,
                            ),
                        )

                # Handle +Inf bucket explicitly
                inf_bucket = "+Inf"
                conn.execute(
                    "INSERT INTO metrics_histogram "
                    "(name, bucket, count, labels, "
                    "sum_value, count_total, created_at) "
                    "VALUES (?, ?, 1, ?, ?, 1, ?) "
                    "ON CONFLICT(name, bucket, labels) "
                    "DO UPDATE SET count = count + 1, "
                    "sum_value = sum_value + ?, "
                    "count_total = count_total + 1",
                    (name, inf_bucket, label_str, value, now, value),
                )
                conn.commit()
            except Exception as e:
                logger.error(
                    "Failed observe_histogram %s: %s", name, e
                )
            finally:
                conn.close()

    # ---- Export / Query ----

    def export_prometheus_format(self) -> str:
        lines: List[str] = []

        counters = self._query_all("metrics_counter")
        seen_counters: set = set()
        for r in counters:
            name = r["name"]
            if name not in seen_counters:
                lines.append(f"# HELP {name} counter")
                lines.append(f"# TYPE {name} counter")
                seen_counters.add(name)
            val = r["value"]
            lines.append(f"{name} {val}")

        gauges = self._query_all("metrics_gauge")
        seen_gauges: set = set()
        for r in gauges:
            name = r["name"]
            if name not in seen_gauges:
                lines.append(f"# HELP {name} gauge")
                lines.append(f"# TYPE {name} gauge")
                seen_gauges.add(name)
            val = r["value"]
            lines.append(f"{name} {val}")

        histograms = self._query_all("metrics_histogram")
        hist_names: set = set()
        hist_data: Dict[str, List] = {}
        for r in histograms:
            name = r["name"]
            if name not in hist_names:
                lines.append(f"# HELP {name} histogram")
                lines.append(f"# TYPE {name} histogram")
                hist_names.add(name)
                hist_data[name] = []
            hist_data[name].append(r)

        for name, buckets in hist_data.items():
            total_count = 0
            for b in sorted(
                buckets, key=lambda x: float('inf')
                if x["bucket"] == "+Inf" else x["bucket"],
            ):
                bkt = b["bucket"]
                cnt = b["count"]
                total_count = max(total_count, b.get(
                    "count_total", 0
                ))
                lines.append(f'{name}_bucket{{le="{bkt}"}} {cnt}')
            lines.append(
                f"{name}_sum {buckets[0]['sum_value'] if buckets else 0}"
            )
            lines.append(f"{name}_count {total_count}")

        return "\n".join(lines) + "\n"

    def get_all_metrics(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "counters": {},
            "gauges": {},
            "histograms": {},
        }

        for r in self._query_all("metrics_counter"):
            result["counters"][r["name"]] = r["value"]

        for r in self._query_all("metrics_gauge"):
            result["gauges"][r["name"]] = r["value"]

        for r in self._query_all("metrics_histogram"):
            hname = r["name"]
            if hname not in result["histograms"]:
                result["histograms"][hname] = {
                    "buckets": {},
                    "sum": 0.0,
                    "count": 0,
                }
            result["histograms"][hname]["buckets"][
                r["bucket"]
            ] = r["count"]
            result["histograms"][hname]["sum"] = r.get(
                "sum_value", 0
            )
            result["histograms"][hname]["count"] = r.get(
                "count_total", 0
            )

        return result

    def _query_all(self, table: str) -> List[Dict]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    f"SELECT * FROM {table}"
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def reset_metric(self, name: str) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "DELETE FROM metrics_counter WHERE name=?", (name,)
                )
                conn.execute(
                    "DELETE FROM metrics_gauge WHERE name=?", (name,)
                )
                conn.execute(
                    "DELETE FROM metrics_histogram WHERE name=?",
                    (name,),
                )
                conn.commit()
            finally:
                conn.close()


# ==================== MetricsCollector ====================


class MetricsCollector:
    """
    Application-level metrics collector (Prometheus style).

    Provides a unified interface for recording Counter/Gauge/Histogram
    metrics. Integrates with EventBus for automatic event-driven collection.

    Usage:
        collector = MetricsCollector(db_path="data/my.db")
        collector.inc_counter("photos_processed_total")
        collector.set_gauge("disk_free_bytes", 1024*1024*100)
        collector.observe_histogram("latency_sec", 1.5)
    """

    # ---- Pre-defined Counter definitions ----
    COUNTER_PHOTOS_PROCESSED = CounterDef(
        name="photos_processed_total",
        help="Total photos processed",
        labels=["status"],
    )
    COUNTER_FACES_DETECTED = CounterDef(
        name="faces_detected_total",
        help="Total faces detected",
    )
    COUNTER_TARGET_FOUND = CounterDef(
        name="target_found_total",
        help="Total target-person photos found",
        labels=["target_name"],
    )
    COUNTER_API_CALLS = CounterDef(
        name="api_calls_total",
        help="Total face recognition API calls",
        labels=["provider", "result"],
    )
    COUNTER_TASKS_COMPLETED = CounterDef(
        name="tasks_completed_total",
        help="Total pipeline tasks completed",
        labels=["trigger_type", "result"],
    )

    # ---- Pre-defined Gauge definitions ----
    GAUGE_API_QUOTA = GaugeDef(
        name="api_quota_remaining",
        help="Remaining API quota",
        labels=["provider"],
    )
    GAUGE_DISK_USAGE = GaugeDef(
        name="disk_usage_bytes",
        help="Disk usage in bytes",
    )
    GAUGE_DISK_FREE = GaugeDef(
        name="disk_free_bytes",
        help="Free disk space in bytes",
    )
    GAUGE_TASK_QUEUE_PENDING = GaugeDef(
        name="task_queue_pending",
        help="Pending task queue size",
    )
    GAUGE_TASK_QUEUE_FAILED = GaugeDef(
        name="task_queue_failed",
        help="Failed (retryable) task count",
    )
    GAUGE_REVIEW_POOL_SIZE = GaugeDef(
        name="review_pool_size",
        help="Review pool photo count",
    )
    GAUGE_CIRCUIT_BREAKER = GaugeDef(
        name="circuit_breaker_state",
        help="Circuit breaker state (0=closed,1=open,2=half_open)",
        labels=["provider"],
    )

    # ---- Pre-defined Histogram definitions ----
    HISTOGRAM_RECOGNIZE_LATENCY = HistogramDef(
        name="recognize_latency_sec",
        help="Face recognition latency distribution (seconds)",
        buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
    )
    HISTOGRAM_DOWNLOAD_LATENCY = HistogramDef(
        name="download_latency_sec",
        help="Photo download latency distribution (seconds)",
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    )
    HISTOGRAM_PIPELINE_LATENCY = HistogramDef(
        name="full_pipeline_latency_sec",
        help="Full pipeline latency distribution (seconds)",
        buckets=[1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
    )
    HISTOGRAM_PHOTO_SIZE = HistogramDef(
        name="photo_size_kb",
        help="Photo file size distribution (KB)",
        buckets=[100, 500, 1000, 2000, 5000, 10000],
    )
    HISTOGRAM_CONFIDENCE = HistogramDef(
        name="confidence_distribution",
        help="Recognition confidence distribution",
        buckets=[
            0.5, 0.6, 0.7, 0.8, 0.85,
            0.9, 0.93, 0.96, 0.98, 1.0,
        ],
    )

    def __init__(
        self,
        db_path: str = _DEFAULT_METRICS_DB_PATH,
    ):
        self._db = MetricsDB(db_path)
        self._memory_cache: Dict[str, float] = {}
        self._histogram_configs: Dict[
            str, List[float]
        ] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        reg = [
            (self.HISTOGRAM_RECOGNIZE_LATENCY.name,
             self.HISTOGRAM_RECOGNIZE_LATENCY.buckets),
            (self.HISTOGRAM_DOWNLOAD_LATENCY.name,
             self.HISTOGRAM_DOWNLOAD_LATENCY.buckets),
            (self.HISTOGRAM_PIPELINE_LATENCY.name,
             self.HISTOGRAM_PIPELINE_LATENCY.buckets),
            (self.HISTOGRAM_PHOTO_SIZE.name,
             self.HISTOGRAM_PHOTO_SIZE.buckets),
            (self.HISTOGRAM_CONFIDENCE.name,
             self.HISTOGRAM_CONFIDENCE.buckets),
        ]
        for name, buckets in reg:
            if buckets:
                self._histogram_configs[name] = list(buckets)
                self._histogram_configs[name].append(float('inf'))

    # ---- Public API: Counter ----

    def inc_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment a counter metric."""
        self._db.inc_counter(name, value, labels)
        cache_key = self._cache_key(name, labels)
        self._memory_cache[cache_key] = (
            self._memory_cache.get(cache_key, 0.0) + value
        )

    # ---- Public API: Gauge ----

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Set a gauge metric value."""
        self._db.set_gauge(name, value, labels)
        cache_key = self._cache_key(name, labels)
        self._memory_cache[cache_key] = value

    # ---- Public API: Histogram ----

    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record an observation into a histogram."""
        buckets = self._histogram_configs.get(name)
        if not buckets:
            buckets = [
                0.005, 0.01, 0.025, 0.05, 0.1,
                0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
                float('inf'),
            ]
            self._histogram_configs[name] = buckets
        self._db.observe_histogram(name, value, buckets, labels)

    # ---- Convenience methods for pre-defined metrics ----

    def record_photo_processed(
        self, status: str = "success"
    ) -> None:
        self.inc_counter(
            self.COUNTER_PHOTOS_PROCESSED.name,
            labels={"status": status},
        )

    def record_face_detected(self, count: int = 1) -> None:
        self.inc_counter(
            self.COUNTER_FACES_DETECTED.name, value=count
        )

    def record_target_found(
        self, target_name: str = "default"
    ) -> None:
        self.inc_counter(
            self.COUNTER_TARGET_FOUND.name,
            labels={"target_name": target_name},
        )

    def record_api_call(
        self, provider: str, result: str = "success"
    ) -> None:
        self.inc_counter(
            self.COUNTER_API_CALLS.name,
            labels={"provider": provider, "result": result},
        )

    def record_task_completed(
        self, trigger_type: str, result: str = "success"
    ) -> None:
        self.inc_counter(
            self.COUNTER_TASKS_COMPLETED.name,
            labels={
                "trigger_type": trigger_type,
                "result": result,
            },
        )

    def record_recognize_latency(self, seconds: float) -> None:
        self.observe_histogram(
            self.HISTOGRAM_RECOGNIZE_LATENCY.name, seconds
        )

    def record_download_latency(self, seconds: float) -> None:
        self.observe_histogram(
            self.HISTOGRAM_DOWNLOAD_LATENCY.name, seconds
        )

    def record_pipeline_latency(self, seconds: float) -> None:
        self.observe_histogram(
            self.HISTOGRAM_PIPELINE_LATENCY.name, seconds
        )

    def record_photo_size_kb(self, kb: float) -> None:
        self.observe_histogram(
            self.HISTOGRAM_PHOTO_SIZE.name, kb
        )

    def record_confidence(self, confidence: float) -> None:
        self.observe_histogram(
            self.HISTOGRAM_CONFIDENCE.name, confidence
        )

    # ---- Query / Export ----

    def export_prometheus(self) -> str:
        return self._db.export_prometheus_format()

    def get_snapshot(self) -> Dict[str, Any]:
        snap = self._db.get_all_metrics()
        snap.update(dict(self._memory_cache))
        return snap

    def reset(self, name: Optional[str] = None) -> None:
        if name:
            self._db.reset_metric(name)
            keys_to_remove = [
                k for k in self._memory_cache
                if k.startswith(name)
            ]
            for k in keys_to_remove:
                del self._memory_cache[k]
        else:
            pass

    @staticmethod
    def _cache_key(
        name: str, labels: Optional[Dict]
    ) -> str:
        if not labels:
            return name
        label_str = ",".join(
            f"{k}={v}" for k, v in sorted(labels.items())
        )
        return f"{name}{{{label_str}}}"


# ==================== Global Singleton ====================

_collector_instance: Optional[MetricsCollector] = None
_lock = threading.Lock()


def init_metrics(
    db_path: str = _DEFAULT_METRICS_DB_PATH,
) -> MetricsCollector:
    """Initialize the global MetricsCollector singleton."""
    global _collector_instance
    with _lock:
        if _collector_instance is None:
            _collector_instance = MetricsCollector(db_path)
            logger.info("MetricsCollector initialized: %s", db_path)
        return _collector_instance


def get_metrics() -> MetricsCollector:
    """Get the global MetricsCollector instance."""
    global _collector_instance
    if _collector_instance is None:
        return init_metrics()
    return _collector_instance
