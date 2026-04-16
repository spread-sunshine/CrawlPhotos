# -*- coding: utf-8 -*-
"""
Review Pool - Human review queue for edge-case photos.
人工审核池 - 边缘案例照片待审核队列.

Photos that fall into the confidence gray zone
(between low_threshold and high_threshold) enter this pool
for human confirmation before final decision.

Table: review_pool
"""

import shutil
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config.logging_config import get_logger
from PIL import Image

logger = get_logger(__name__)

_DEFAULT_DB_PATH = "data/crawl_photos.db"
_DEFAULT_REVIEW_DIR = "data/review_pending"


class ReviewReason(str, Enum):
    """Reasons for a photo entering the review pool."""

    LOW_CONFIDENCE = "low_confidence"       # Gray zone
    NO_FACE = "no_face"                      # No face detected
    EDGE_CASE = "edge_case"                  # Edge case
    AMBIGUOUS_MATCH = "ambiguous_match"      # Ambiguous match


class ReviewStatus(str, Enum):
    """Status of a review item."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class ReviewItem:
    """A photo awaiting human review.

    Attributes:
        id: Database primary key.
        record_id: FK to photos_record.id.
        photo_id: Source photo identifier.
        local_path: Local file path (for preview).
        original_path: Original full-size path.
        confidence: Recognition confidence score.
        face_count: Number of faces detected.
        reason: Why this photo is in the review pool.
        status: Current review status.
        reviewed_by: Who reviewed this item.
        reviewed_at: When was it reviewed.
        review_note: Optional comment from reviewer.
        thumbnail_data: Thumbnail binary for web display.
        created_at: When added to pool.
        expires_at: When auto-approve deadline.
    """

    id: int = 0
    record_id: int = 0
    photo_id: str = ""
    local_path: str = ""
    original_path: str = ""
    confidence: float = 0.0
    face_count: int = 0
    reason: str = "low_confidence"
    status: str = ReviewStatus.PENDING.value
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_note: Optional[str] = None
    thumbnail_data: Optional[bytes] = None
    created_at: str = ""
    expires_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "record_id": self.record_id,
            "photo_id": self.photo_id,
            "local_path": self.local_path,
            "original_path": self.original_path,
            "confidence": self.confidence,
            "face_count": self.face_count,
            "reason": self.reason,
            "status": self.status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "review_note": self.review_note,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


@dataclass
class DualThresholdConfig:
    """Configuration for dual-threshold strategy.

    High threshold (>=): Auto-accept.
    Low threshold (<): Auto-reject.
    Between: Enter review pool.
    """

    high_confidence: float = 0.92
    low_confidence: float = 0.75
    no_face_action: str = "review"
    auto_accept_hours: int = 48
    max_pool_size: int = 200


class ReviewPool:
    """
    Manages the human review pool for edge-case photos.

    Responsibilities:
    - Add photos that fall in the gray zone.
    - CRUD operations on review items.
    - Auto-expire old items.
    - Generate thumbnails for web display.
    """

    THUMBNAIL_SIZE = (300, 300)

    def __init__(
        self,
        db_path: str = _DEFAULT_DB_PATH,
        review_dir: str = _DEFAULT_REVIEW_DIR,
        config: Optional[DualThresholdConfig] = None,
    ):
        self._db_path = db_path
        self._review_dir = Path(review_dir)
        self._review_dir.mkdir(parents=True, exist_ok=True)
        self._config = config or DualThresholdConfig()
        self._lock = threading.Lock()
        self._init_table()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_table(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS review_pool (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        record_id       INTEGER NOT NULL DEFAULT 0,
                        photo_id        TEXT    NOT NULL,
                        local_path      TEXT    NOT NULL,
                        original_path   TEXT    DEFAULT '',
                        confidence      REAL    NOT NULL DEFAULT 0,
                        face_count      INTEGER NOT NULL DEFAULT 0,
                        reason          TEXT    NOT NULL DEFAULT 'low_confidence',
                        status          TEXT    NOT NULL DEFAULT 'pending',
                        reviewed_by     TEXT    DEFAULT NULL,
                        reviewed_at     DATETIME DEFAULT NULL,
                        review_note     TEXT    DEFAULT NULL,
                        thumbnail_data  BLOB    DEFAULT NULL,
                        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                        expires_at      DATETIME DEFAULT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_review_status
                        ON review_pool(status);
                    CREATE INDEX IF NOT EXISTS idx_review_expires
                        ON review_pool(expires_at);
                """)
                conn.commit()
            finally:
                conn.close()

    def classify(
        self,
        confidence: float,
        face_count: int,
        contains_target: bool,
    ) -> str:
        """
        Classify a recognition result using dual-threshold.

        Returns:
            'auto_accept', 'auto_reject', or 'review'
        """
        cfg = self._config

        # If target found with high confidence -> auto accept
        if contains_target and confidence >= cfg.high_confidence:
            return "auto_accept"

        # If target not found or very low confidence
        if not contains_target or confidence < cfg.low_confidence:
            if face_count == 0 and cfg.no_face_action != "review":
                return "auto_reject"
            if confidence < cfg.low_confidence:
                return "auto_reject"

        # Gray zone -> review
        return "review"

    def add_item(
        self,
        photo_id: str,
        record_id: int = 0,
        local_path: str = "",
        original_path: str = "",
        confidence: float = 0.0,
        face_count: int = 0,
        reason: str = ReviewReason.LOW_CONFIDENCE.value,
    ) -> Optional[int]:
        """
        Add a photo to the review pool.

        Returns:
            The new review item ID, or None if pool is at capacity.
        """
        # Check capacity - evict oldest if needed
        pending_count = self.count_by_status(ReviewStatus.PENDING)
        if pending_count >= self._config.max_pool_size:
            logger.warning(
                "Review pool at capacity (%d), "
                "auto-approving oldest item",
                self._config.max_pool_size,
            )
            self._auto_approve_oldest()

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(
            hours=self._config.auto_accept_hours
        )

        # Generate thumbnail
        thumbnail_data = self._generate_thumbnail(local_path)

        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "INSERT INTO review_pool "
                    "(record_id, photo_id, local_path, "
                    "original_path, confidence, face_count, "
                    "reason, status, thumbnail_data, "
                    "created_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record_id,
                        photo_id,
                        local_path,
                        original_path,
                        confidence,
                        face_count,
                        reason,
                        ReviewStatus.PENDING.value,
                        thumbnail_data,
                        now.isoformat(),
                        expires_at.isoformat(),
                    ),
                )
                conn.commit()
                item_id = cursor.lastrowid
                logger.info(
                    "Added to review pool: id=%d photo=%s "
                    "reason=%s conf=%.2f",
                    item_id, photo_id, reason, confidence,
                )
                return item_id
            except Exception as e:
                logger.error("Failed to add review item: %s", e)
                return None
            finally:
                conn.close()

    def approve(
        self,
        item_id: int,
        reviewer: str = "admin",
        note: str = "",
    ) -> bool:
        """Mark a review item as approved."""
        return self._update_status(
            item_id,
            ReviewStatus.APPROVED.value,
            reviewer,
            note,
        )

    def reject(
        self,
        item_id: int,
        reviewer: str = "admin",
        note: str = "",
    ) -> bool:
        """Mark a review item as rejected."""
        return self._update_status(
            item_id,
            ReviewStatus.REJECTED.value,
            reviewer,
            note,
        )

    def _update_status(
        self,
        item_id: int,
        status: str,
        reviewer: str = "",
        note: str = "",
    ) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                result = conn.execute(
                    "UPDATE review_pool SET status=?, "
                    "reviewed_by=?, reviewed_at=?, "
                    "review_note=? WHERE id=? AND status='pending'",
                    (
                        status,
                        reviewer,
                        datetime.now(timezone.utc).isoformat(),
                        note,
                        item_id,
                    ),
                )
                conn.commit()
                return result.rowcount > 0
            except Exception as e:
                logger.error("Failed update review %d: %s", item_id, e)
                return False
            finally:
                conn.close()

    def get_item(self, item_id: int) -> Optional[ReviewItem]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM review_pool WHERE id=?",
                    (item_id,),
                ).fetchone()
                if row:
                    return self._row_to_item(row)
                return None
            finally:
                conn.close()

    def list_items(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ReviewItem]:
        with self._lock:
            conn = self._get_conn()
            try:
                query = "SELECT * FROM review_pool WHERE 1=1"
                params: List[Any] = []

                if status:
                    query += " AND status=?"
                    params.append(status)

                query += " ORDER BY created_at DESC LIMIT ? OFFSET?"
                params.extend([limit, offset])

                rows = conn.execute(query, params).fetchall()
                return [self._row_to_item(r) for r in rows]
            finally:
                conn.close()

    def count_by_status(
        self, status: ReviewStatus
    ) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM review_pool "
                    "WHERE status=?",
                    (status.value,),
                ).fetchone()
                return row["cnt"] if row else 0
            finally:
                conn.close()

    def count_pending(self) -> int:
        return self.count_by_status(ReviewStatus.PENDING)

    def expire_items(self) -> int:
        """Expire overdue items (mark as expired)."""
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "UPDATE review_pool SET status='expired', "
                    "reviewed_at=? "
                    "WHERE status='pending' AND "
                    "expires_at IS NOT NULL AND expires_at<=?",
                    (now, now),
                )
                conn.commit()
                count = cursor.rowcount
                if count > 0:
                    logger.info(
                        "Expired %d review items", count
                    )
                return count
            finally:
                conn.close()

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the review pool state."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT status, COUNT(*) AS cnt "
                    "FROM review_pool GROUP BY status"
                ).fetchall()
                by_status = {
                    r["status"]: r["cnt"] for r in (rows or [])
                }

                total = sum(by_status.values())
                return {
                    "total": total,
                    "pending": by_status.get(
                        ReviewStatus.PENDING.value, 0
                    ),
                    "approved": by_status.get(
                        ReviewStatus.APPROVED.value, 0
                    ),
                    "rejected": by_status.get(
                        ReviewStatus.REJECTED.value, 0
                    ),
                    "expired": by_status.get(
                        ReviewStatus.EXPIRED.value, 0
                    ),
                }
            finally:
                conn.close()

    def _auto_approve_oldest(self) -> bool:
        """Auto-approve the oldest pending item."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT id FROM review_pool "
                    "WHERE status='pending' "
                    "ORDER BY created_at ASC LIMIT 1"
                ).fetchone()
                if row:
                    self._update_status(
                        row["id"],
                        ReviewStatus.APPROVED.value,
                        reviewer="system",
                        note="Pool at capacity, auto-approved",
                    )
                    return True
                return False
            finally:
                conn.close()

    def _generate_thumbnail(
        self, image_path: str
    ) -> Optional[bytes]:
        """Generate JPEG thumbnail for web display."""
        if not image_path or not Path(image_path).exists():
            return None

        try:
            img = Image.open(image_path)

            # Convert mode if necessary
            if img.mode in ("P", "PA", "LA"):
                img = img.convert("RGBA")
            elif img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")

            img.thumbnail(self.THUMBNAIL_SIZE, Image.LANCZOS)

            import io
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=70)
            return buffer.getvalue()
        except Exception as e:
            logger.debug(
                "Failed to generate thumbnail for %s: %s",
                image_path, e,
            )
            return None

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> ReviewItem:
        return ReviewItem(
            id=row["id"],
            record_id=row["record_id"],
            photo_id=row["photo_id"],
            local_path=row["local_path"],
            original_path=row["original_path"],
            confidence=row["confidence"],
            face_count=row["face_count"],
            reason=row["reason"],
            status=row["status"],
            reviewed_by=row["reviewed_by"],
            reviewed_at=row["reviewed_at"],
            review_note=row["review_note"],
            thumbnail_data=row["thumbnail_data"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )
