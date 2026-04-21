# -*- coding: utf-8 -*-
"""
Recognition Result Cache Layer.
识别结果缓存层 - 避免重复API调用节省配额.

Strategy:
    - L1: In-memory LRU cache (fastest, session-scoped)
    - L2: SQLite persistent cache (survives restarts)
    - Cache key: SHA256 of image content (content-addressable)
    - TTL support with configurable expiry
    - Stats tracking for hit/miss rate monitoring
"""

import hashlib
import logging
import sqlite3
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.config.logging_config import get_logger
from app.face_recognition.models import RecognitionResult

logger = get_logger(__name__)

DEFAULT_CACHE_DB_PATH = Path("data") / "recognition_cache.db"


@dataclass
class CachedRecognition:
    """A cached recognition result."""
    cache_key: str       # SHA256 hash of image
    is_match: bool
    confidence: float
    target_name: str
    bbox_left: int = 0
    bbox_top: int = 0
    bbox_width: int = 0
    bbox_height: int = 0
    cached_at: float = 0.0   # Unix timestamp
    ttl_seconds: float = 3600.0


# Cache constants
DEFAULT_CACHE_TTL_SECONDS = 3600.0  # Default 1 hour
IO_BUFFER_SIZE = 65536


class RecognitionCache:
    """
    Two-level recognition result cache.

    L1: In-memory OrderedDict-based LRU (configurable size)
    L2: SQLite table (persistent across restarts)

    Usage:
        cache = RecognitionCache(l1_max_size=500)
        
        # Try cache first
        cached = cache.get(image_path)
        if cached:
            return cached.to_recognition_result()
        
        # Cache miss -> call real API
        result = await recognizer.recognize(str(image_path))
        cache.put(image_path, result)
    """

    SQL_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS recognition_cache (
        cache_key     TEXT PRIMARY KEY,
        is_match      INTEGER NOT NULL DEFAULT 0,
        confidence    REAL NOT NULL DEFAULT 0,
        target_name   TEXT NOT NULL DEFAULT '',
        bbox_left     INTEGER DEFAULT 0,
        bbox_top      INTEGER DEFAULT 0,
        bbox_width    INTEGER DEFAULT 0,
        bbox_height   INTEGER DEFAULT 0,
        cached_at     REAL NOT NULL,
        ttl_seconds   REAL NOT NULL DEFAULT 3600
    );
    """

    SQL_CREATE_INDEX = (
        "CREATE INDEX IF NOT EXISTS idx_cache_expiry "
        "ON recognition_cache(cached_at, ttl_seconds)"
    )

    def __init__(
        self,
        l1_max_size: int = 500,
        l2_db_path: Optional[Path] = None,
        default_ttl: float = 3600.0,
    ):
        self._l1_max = l1_max_size
        self._default_ttl = default_ttl
        # L1: OrderedDict as LRU (Python 3.7+ preserves insertion order)
        self._l1: OrderedDict[str, CachedRecognition] = OrderedDict()  # noqa: E501
        # L2: SQLite
        self._l2_db_path = l2_db_path or DEFAULT_CACHE_DB_PATH
        self._l2_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._l2_conn: Optional[sqlite3.Connection] = None
        # Stats
        self._hits_l1 = 0
        self._hits_l2 = 0
        self._misses = 0

    @property
    def conn(self) -> sqlite3.Connection:
        if self._l2_conn is None:
            self._l2_conn = sqlite3.connect(
                str(self._l2_db_path),
            )
            self._l2_conn.row_factory = sqlite3.Row
        return self._l2_conn

    def initialize(self) -> None:
        """Create tables and indexes."""
        c = self.conn.cursor()
        c.execute(self.SQL_CREATE_TABLE)
        c.execute(self.SQL_CREATE_INDEX)
        self.conn.commit()
        logger.info(
            "RecognitionCache initialized (L1=%d, L2=%s)",
            self._l1_max, self._l2_db_path,
        )

    def close(self) -> None:
        if self._l2_conn is not None:
            self._l2_conn.close()
            self._l2_conn = None

    @staticmethod
    def compute_key(image_path: Path) -> str:
        """Compute SHA256 hash of image file as cache key."""
        sha = hashlib.sha256()
        buf_size = IO_BUFFER_SIZE
        with open(image_path, "rb") as f:
            while True:
                chunk = f.read(buf_size)
                if not chunk:
                    break
                sha.update(chunk)
        return sha.hexdigest()

    def get(
        self,
        image_path: Path,
    ) -> Optional[CachedRecognition]:
        """
        Look up cached result for image.

        Checks L1 first, then L2. Promotes L2 hits to L1.
        Returns None on miss.
        """
        key = self.compute_key(image_path)

        # L1 check
        if key in self._l1:
            entry = self._l1[key]
            if self._is_valid(entry):
                # LRU: move to end
                self._l1.move_to_end(key)
                self._hits_l1 += 1
                return entry
            else:
                # Expired -> evict
                del self._l1[key]

        # L2 check
        now = time.time()
        row = self.conn.execute(
            "SELECT * FROM recognition_cache WHERE cache_key=?",
            (key,),
        ).fetchone()

        if row is not None:
            entry = self._row_to_entry(row)
            if self._is_valid(entry):
                # Promote to L1
                self._l1_put(key, entry)
                self._hits_l2 += 1
                return entry
            else:
                # Stale in DB -> remove
                self.conn.execute(
                    "DELETE FROM recognition_cache WHERE cache_key=?",
                    (key,),
                )
                self.conn.commit()

        self._misses += 1
        return None

    def put(
        self,
        image_path: Path,
        result: RecognitionResult,
        ttl_override: Optional[float] = None,
    ) -> None:
        """Cache a recognition result."""
        key = self.compute_key(image_path)
        now = time.time()
        ttl = ttl_override or self._default_ttl

        bbox_l = bbox_t = bbox_w = bbox_h = 0
        if result.bounding_box:
            bbox_l = result.bounding_box.left
            bbox_t = result.bounding_box.top
            bbox_w = result.bounding_box.width
            bbox_h = result.bounding_box.height

        entry = CachedRecognition(
            cache_key=key,
            is_match=result.is_match or False,
            confidence=result.confidence or 0.0,
            target_name=result.target_name or "",
            bbox_left=bbox_l,
            bbox_top=bbox_t,
            bbox_width=bbox_w,
            bbox_height=bbox_h,
            cached_at=now,
            ttl_seconds=ttl,
        )

        # Store in both levels
        self._l1_put(key, entry)
        self._l2_put(key, entry)

    def invalidate(self, image_path: Path) -> bool:
        """Remove a specific image from cache."""
        key = self.compute_key(image_path)
        removed = False
        if key in self._l1:
            del self._l1[key]
            removed = True
        cur = self.conn.execute(
            "DELETE FROM recognition_cache WHERE cache_key=?",
            (key,),
        )
        self.conn.commit()
        if cur.rowcount > 0:
            removed = True
        return removed

    def clear_expired(self, force: bool = False) -> int:
        """Remove expired entries from both levels."""
        now = time.time()
        expired_keys = [
            k for k, v in self._l1.items()
            if not self._is_valid(v)
        ]
        for k in expired_keys:
            del self._l1[k]

        count = 0
        if force or len(expired_keys) > 0:
            cur = self.conn.execute(
                "DELETE FROM recognition_cache WHERE "
                "(cached_at + ttl_seconds) < ?",
                (now,),
            )
            self.conn.commit()
            count = cur.rowcount

        if count > 0:
            logger.info("Cleared %d expired cache entries", count)
        return count

    def clear_all(self) -> int:
        """Remove ALL entries from both levels."""
        self._l1.clear()
        cur = self.conn.execute("DELETE FROM recognition_cache")
        self.conn.commit()
        count = cur.rowcount
        logger.info("Cleared all %d cache entries", count)
        return count

    def stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        total_lookups = self._hits_l1 + self._hits_l2 + self._misses
        hit_rate = (
            (self._hits_l1 + self._hits_l2) / total_lookups
            if total_lookups > 0 else 0
        )
        l2_total = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM recognition_cache",
        ).fetchone()["cnt"]

        return {
            "l1_size": len(self._l1),
            "l1_max": self._l1_max,
            "l2_size": l2_total,
            "hits_l1": self._hits_l1,
            "hits_l2": self._hits_l2,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4),
            "total_lookups": total_lookups,
        }

    def _l1_put(self, key: str, entry: CachedRecognition) -> None:
        """Put into L1 with LRU eviction."""
        if key in self._l1:
            self._l1.move_to_end(key)
            self._l1[key] = entry
        else:
            if len(self._l1) >= self._l1_max:
                self._l1.popitem(last=False)  # Evict oldest
            self._l1[key] = entry

    def _l2_put(self, key: str, entry: CachedRecognition) -> None:
        """Upsert into L2 (SQLite)."""
        self.conn.execute(
            "INSERT OR REPLACE INTO recognition_cache VALUES "
            "(?,?,?,?,?,?,?,?,?,?)",
            (
                entry.cache_key,
                1 if entry.is_match else 0,
                entry.confidence,
                entry.target_name,
                entry.bbox_left,
                entry.bbox_top,
                entry.bbox_width,
                entry.bbox_height,
                entry.cached_at,
                entry.ttl_seconds,
            ),
        )
        self.conn.commit()

    @staticmethod
    def _is_valid(entry: CachedRecognition) -> bool:
        """Check if a cache entry hasn't expired."""
        return (
            time.time() < entry.cached_at + entry.ttl_seconds
        )

    @staticmethod
    def _row_to_entry(row: Dict[str, Any]) -> CachedRecognition:
        return CachedRecognition(
            cache_key=row["cache_key"],
            is_match=bool(row["is_match"]),
            confidence=row["confidence"],
            target_name=row["target_name"],
            bbox_left=row["bbox_left"],
            bbox_top=row["bbox_top"],
            bbox_width=row["bbox_width"],
            bbox_height=row["bbox_height"],
            cached_at=row["cached_at"],
            ttl_seconds=row["ttl_seconds"],
        )


def create_recognition_cache(
    l1_max_size: int = 500,
    default_ttl_hours: float = 1.0,
) -> RecognitionCache:
    """Factory function."""
    cache = RecognitionCache(
        l1_max_size=l1_max_size,
        default_ttl=default_ttl_hours * 3600,
    )
    cache.initialize()
    return cache
