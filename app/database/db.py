# -*- coding: utf-8 -*-
"""
SQLite Database layer for photo records and task history.
数据库模块 - 建表/CRUD/去重.
"""

import hashlib
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from app.models.photo import (
    PhotoStatus,
    ProcessedPhoto,
    TaskRun,
)

# Default database path
DEFAULT_DB_PATH = Path("data") / "crawl_photos.db"

# SQL Schema definitions
SQL_CREATE_PHOTOS_TABLE = """
CREATE TABLE IF NOT EXISTS photos (
    photo_id       TEXT PRIMARY KEY,
    status         TEXT NOT NULL DEFAULT 'pending',
    source_type    TEXT NOT NULL DEFAULT 'qq_group_album',
    url            TEXT DEFAULT '',
    local_path     TEXT,
    file_size      INTEGER DEFAULT 0,
    file_hash      TEXT UNIQUE,
    contains_target INTEGER DEFAULT 0,
    confidence     REAL DEFAULT 0.0,
    face_count     INTEGER DEFAULT 0,
    provider_name  TEXT DEFAULT '',
    stored_path    TEXT,
    personal_photo_id TEXT UNIQUE,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    error_message  TEXT,
    retry_count    INTEGER DEFAULT 0
);
"""

SQL_CREATE_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS runs (
    run_id         TEXT PRIMARY KEY,
    trigger_type   TEXT NOT NULL DEFAULT 'manual',
    started_at     TEXT NOT NULL,
    finished_at    TEXT,
    total_discovered INTEGER DEFAULT 0,
    total_new      INTEGER DEFAULT 0,
    total_downloaded INTEGER DEFAULT 0,
    total_contains_target INTEGER DEFAULT 0,
    total_stored   INTEGER DEFAULT 0,
    total_failed   INTEGER DEFAULT 0,
    total_skipped  INTEGER DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'running',
    error_message  TEXT
);
"""

SQL_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_photos_status ON photos(status);",
    "CREATE INDEX IF NOT EXISTS idx_photos_file_hash ON photos(file_hash);",
    "CREATE INDEX IF NOT EXISTS idx_photos_created_at ON photos(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);",
]


class DatabaseError(Exception):
    """Database operation error."""
    pass


class Database:
    """
    SQLite database manager for the application.

    Responsibilities:
    - Initialize tables on first run.
    - Provide CRUD operations for photos and task runs.
    - Support dedup queries by photo_id and file_hash.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Lazy-initialize and return DB connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrent read performance
            self._conn.execute("PRAGMA journal_mode=WAL;")
        return self._conn

    def initialize(self) -> None:
        """Create tables and indexes if they do not exist."""
        c = self.conn.cursor()
        c.execute(SQL_CREATE_PHOTOS_TABLE)
        c.execute(SQL_CREATE_RUNS_TABLE)
        for index_sql in SQL_CREATE_INDEXES:
            c.execute(index_sql)
        self.conn.commit()

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ==================== Photo CRUD ====================

    def insert_photo(self, photo: ProcessedPhoto) -> bool:
        """Insert a new photo record. Returns True if inserted."""
        try:
            self.conn.execute(
                """INSERT INTO photos
                   (photo_id, status, source_type, url, local_path,
                    file_size, file_hash, contains_target, confidence,
                    face_count, provider_name, stored_path,
                    personal_photo_id, created_at, updated_at,
                    error_message, retry_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           ?, ?, ?, ?, ?)""",
                photo.to_storage_row(),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            # photo_id or file_hash already exists
            return False

    def get_photo_by_id(
        self, photo_id: str,
    ) -> Optional[ProcessedPhoto]:
        """Fetch photo record by source photo_id."""
        row = self.conn.execute(
            "SELECT * FROM photos WHERE photo_id = ?", (photo_id,)
        ).fetchone()
        return self._row_to_photo(row) if row else None

    def get_photo_by_hash(
        self, file_hash: str,
    ) -> Optional[ProcessedPhoto]:
        """Fetch photo record by SHA256 file hash."""
        row = self.conn.execute(
            "SELECT * FROM photos WHERE file_hash = ?",
            (file_hash,),
        ).fetchone()
        return self._row_to_photo(row) if row else None

    def update_photo_status(
        self,
        photo_id: str,
        status: PhotoStatus,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update photo processing status."""
        now = datetime.now().isoformat()
        cursor = self.conn.execute(
            """UPDATE photos SET status=?, updated_at=?,
               error_message=?
               WHERE photo_id=?""",
            (status.value, now, error_message, photo_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def update_photo_recognition(
        self,
        photo_id: str,
        contains_target: bool,
        confidence: float,
        face_count: int,
        provider_name: str,
    ) -> bool:
        """Update photo with recognition result."""
        now = datetime.now().isoformat()
        cursor = self.conn.execute(
            """UPDATE photos SET status=?, updated_at=?,
               contains_target=?, confidence=?, face_count=?,
               provider_name=?
               WHERE photo_id=?""",
            (
                PhotoStatus.RECOGNIZED.value,
                now,
                int(contains_target),
                confidence,
                face_count,
                provider_name,
                photo_id,
            ),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def update_photo_stored(
        self,
        photo_id: str,
        stored_path: str,
        status: PhotoStatus = PhotoStatus.STORED,
    ) -> bool:
        """Update photo with storage location."""
        now = datetime.now().isoformat()
        cursor = self.conn.execute(
            """UPDATE photos SET status=?, updated_at=?,
               stored_path=?
               WHERE photo_id=?""",
            (status.value, now, stored_path, photo_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def increment_retry(self, photo_id: str) -> int:
        """Increment retry count and return new value."""
        self.conn.execute(
            "UPDATE photos SET retry_count = retry_count + 1 "
            "WHERE photo_id = ?",
            (photo_id,),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT retry_count FROM photos WHERE photo_id = ?",
            (photo_id,),
        ).fetchone
        return row["retry_count"] if row else 0

    def list_photos_by_status(
        self,
        status: PhotoStatus,
        limit: int = 100,
    ) -> List[ProcessedPhoto]:
        """List photos with given status."""
        rows = self.conn.execute(
            "SELECT * FROM photos WHERE status=? ORDER BY "
            "created_at DESC LIMIT ?",
            (status.value, limit),
        ).fetchall()
        return [self._row_to_photo(r) for r in rows]

    def count_by_status(self, status: PhotoStatus) -> int:
        """Count photos with given status."""
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM photos WHERE status=?",
            (status.value,),
        ).fetchone()
        return row["cnt"] if row else 0

    # ==================== Dedup Queries ====================

    def exists_photo_id(self, photo_id: str) -> bool:
        """Check if a photo with this ID has been recorded."""
        row = self.conn.execute(
            "SELECT 1 FROM photos WHERE photo_id=?",
            (photo_id,),
        ).fetchone()
        return row is not None

    def exists_file_hash(self, file_hash: str) -> bool:
        """Check if a file with this hash already exists."""
        row = self.conn.execute(
            "SELECT 1 FROM photos WHERE file_hash=?",
            (file_hash,),
        ).fetchone()
        return row is not None

    def exists_personal_photo_id(
        self, personal_photo_id: str,
    ) -> bool:
        """Check if a photo was already uploaded with this ID."""
        row = self.conn.execute(
            "SELECT 1 FROM photos WHERE personal_photo_id=?",
            (personal_photo_id,),
        ).fetchone()
        return row is not None

    # ==================== Run History ====================

    def create_run(self, trigger_type: str) -> TaskRun:
        """Create a new task run record and return it."""
        run = TaskRun(
            run_id=str(uuid.uuid4()),
            trigger_type=trigger_type,
        )
        self.conn.execute(
            """INSERT INTO runs
               (run_id, trigger_type, started_at, status)
               VALUES (?, ?, ?, ?)""",
            (run.run_id, run.trigger_type.value,
             run.started_at.isoformat(), run.status),
        )
        self.conn.commit()
        return run

    def finish_run(
        self,
        run_id: str,
        status: str,
        error_message: Optional[str] = None,
        **stats_kwargs: int,
    ) -> None:
        """Mark a run as finished with final statistics."""
        now = datetime.now().isoformat()
        allowed_stats = {
            "total_discovered", "total_new", "total_downloaded",
            "total_contains_target", "total_stored",
            "total_failed", "total_skipped",
        }
        set_clauses = ["finished_at=?", "status=?"]
        values: list = [now, status]

        if error_message:
            set_clauses.append("error_message=?")
            values.append(error_message)

        for key, val in stats_kwargs.items():
            if key in allowed_stats:
                set_clauses.append(f"{key}=?")
                values.append(val)

        values.append(run_id)
        sql = (
            f"UPDATE RUNS SET {', '.join(set_clauses)} "
            f"WHERE run_id=?"
        )
        self.conn.execute(sql, values)
        self.conn.commit()

    def get_recent_runs(self, limit: int = 10) -> List[dict]:
        """Get recent task run summaries."""
        rows = self.conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC "
            "LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ==================== Utility ====================

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def _row_to_photo(row: sqlite3.Row) -> ProcessedPhoto:
        """Convert a DB row to ProcessedPhoto."""
        created = (
            datetime.fromisoformat(row["created_at"])
            if row["created_at"] else datetime.now()
        )
        updated = (
            datetime.fromisoformat(row["updated_at"])
            if row["updated_at"] else datetime.now()
        )
        return ProcessedPhoto(
            photo_id=row["photo_id"],
            status=PhotoStatus(row["status"]),
            source_type=row.get("source_type",
                                "qq_group_album"),
            url=row.get("url", ""),
            local_path=row.get("local_path"),
            file_size=row.get("file_size", 0),
            file_hash=row.get("file_hash"),
            contains_target=bool(row.get("contains_target",
                                         0)),
            confidence=row.get("confidence", 0.0),
            face_count=row.get("face_count", 0),
            provider_name=row.get("provider_name", ""),
            stored_path=row.get("stored_path"),
            personal_photo_id=row.get("personal_photo_id"),
            created_at=created,
            updated_at=updated,
            error_message=row.get("error_message"),
            retry_count=row.get("retry_count", 0),
        )
