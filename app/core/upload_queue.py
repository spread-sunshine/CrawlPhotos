# -*- coding: utf-8 -*-
"""
Upload deduplication queue.
上传去重队列 - 防止重复上传照片到个人相册.

Tracks personal_photo_ids that have been uploaded (or are
queued for upload) to prevent duplicate uploads when the
same photo gets re-processed.
"""

import logging
import sqlite3
from pathlib import Path
from typing import List, Optional, Set

from app.config.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_QUEUE_DB_PATH = Path("data") / "upload_queue.db"


class UploadDedupQueue:
    """
    Persistent queue tracking uploads to prevent duplicates.

    Uses a separate SQLite DB (or shared table) to record
    which personal_photo_ids have already been successfully
    uploaded. This survives restarts.

    Usage:
        queue = UploadDedupQueue()
        queue.init()

        if queue.should_upload(personal_pid="up_12345"):
            # Do upload
            queue.mark_uploaded(personal_pid="up_12345")
    """

    SQL_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS uploaded_photos (
        personal_photo_id TEXT PRIMARY KEY,
        source_photo_id   TEXT NOT NULL DEFAULT '',
        uploaded_at       TEXT NOT NULL DEFAULT '',
        remote_album_id   TEXT DEFAULT '',
        remote_file_id    TEXT DEFAULT ''
    );
    """

    SQL_CREATE_INDEX = (
        "CREATE INDEX IF NOT EXISTS idx_upload_source "
        "ON uploaded_photos(source_photo_id);"
    )

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or DEFAULT_QUEUE_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        # In-memory cache for this session
        self._cache: Set[str] = set()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        """Create table if not exists."""
        c = self.conn.cursor()
        c.execute(self.SQL_CREATE_TABLE)
        c.execute(self.SQL_CREATE_INDEX)
        self.conn.commit()
        self._warm_cache()
        logger.info("UploadDedupQueue initialized")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def should_upload(
        self, personal_photo_id: str,
    ) -> bool:
        """
        Check if a photo should be uploaded (not yet uploaded).

        Checks L0 cache first, then DB.
        Returns True if safe to upload.
        """
        if personal_photo_id in self._cache:
            return False

        row = self.conn.execute(
            "SELECT 1 FROM uploaded_photos WHERE "
            "personal_photo_id=?",
            (personal_photo_id,),
        ).fetchone()

        if row is not None:
            self._cache.add(personal_photo_id)
            return False

        return True

    def mark_uploaded(
        self,
        personal_photo_id: str,
        source_photo_id: str = "",
        remote_album_id: str = "",
        remote_file_id: str = "",
    ) -> bool:
        """Record that a photo has been successfully uploaded."""
        import datetime

        now = datetime.datetime.now().isoformat()
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO uploaded_photos "
                "(personal_photo_id, source_photo_id, "
                "uploaded_at, remote_album_id, "
                "remote_file_id) VALUES (?, ?, ?, ?, ?)",
                (
                    personal_photo_id,
                    source_photo_id,
                    now,
                    remote_album_id,
                    remote_file_id,
                ),
            )
            self.conn.commit()
            self._cache.add(personal_photo_id)
            return True
        except sqlite3.IntegrityError:
            return False  # Already exists

    def mark_queued(self, personal_photo_id: str) -> None:
        """Mark as queued (in-memory only, prevents re-queue)."""
        self._cache.add(personal_photo_id)

    def remove(self, personal_photo_id: str) -> bool:
        """Remove a record (e.g., upload was cancelled)."""
        self.conn.execute(
            "DELETE FROM uploaded_photos WHERE "
            "personal_photo_id=?",
            (personal_photo_id,),
        )
        self.conn.commit()
        self._cache.discard(personal_photo_id)
        return True

    def count_uploaded(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM uploaded_photos",
        ).fetchone()
        return row["cnt"] if row else 0

    def list_recent(self, limit: int = 20) -> list:
        rows = self.conn.execute(
            "SELECT * FROM uploaded_photos ORDER BY "
            "uploaded_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def clear_all(self) -> int:
        """Remove all records (for reset/debug)."""
        cur = self.conn.execute("DELETE FROM uploaded_photos")
        self.conn.commit()
        count = cur.rowcount
        self._cache.clear()
        logger.info("Cleared %d upload records", count)
        return count

    def _warm_cache(self) -> None:
        """Load existing IDs into memory cache."""
        rows = self.conn.execute(
            "SELECT personal_photo_id FROM uploaded_photos",
        ).fetchall()
        count = 0
        for r in rows:
            if r["personal_photo_id"]:
                self._cache.add(r["personal_photo_id"])
                count += 1
        logger.debug("Upload cache warmed: %d entries", count)


def create_upload_queue() -> UploadDedupQueue:
    """Factory function for creating and initializing queue."""
    queue = UploadDedupQueue()
    queue.initialize()
    return queue
