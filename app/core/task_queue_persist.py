# -*- coding: utf-8 -*-
"""
Persistent Task Queue with State Machine + Dead Letter Queue.
任务队列持久化 - 基于SQLite的任务队列,支持状态机和死信队列(DLQ).

Features:
    - SQLite-backed persistent queue (survives restarts)
    - Full state machine: pending -> running -> success/failed/dlq
    - Dead Letter Queue (DLQ) for permanently failed tasks
    - Priority support, retry counting, scheduled execution
    - Thread/async-safe operations
"""

import asyncio
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.config.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_QUEUE_DB_PATH = Path("data") / "task_queue.db"


class TaskStatus(Enum):
    """Task lifecycle states."""
    PENDING = "pending"       # Waiting to be processed
    RUNNING = "running"       # Currently being processed
    SUCCESS = "success"       # Completed successfully
    FAILED = "failed"         # Failed but retryable
    DEAD_LETTER = "dead_letter"  # Failed beyond retries -> DLQ
    CANCELLED = "cancelled"   # Explicitly cancelled


VALID_TRANSITIONS: Dict[str, List[str]] = {
    "pending": ["running", "cancelled"],
    "running": ["success", "failed", "dead_letter"],
    "failed": ["pending", "dead_letter"],
    "success": [],           # Terminal
    "dead_letter": [],      # Terminal (DLQ)
    "cancelled": [],        # Terminal
}


@dataclass
class PersistedTask:
    """A persisted task record."""
    task_id: str
    task_type: str          # e.g., "download", "recognize", "upload"
    payload: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0        # Higher = more important
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: Optional[float] = None  # Unix timestamp
    error_message: str = ""
    created_at: str = ""
    updated_at: str = ""
    completed_at: str = ""


class PersistentTaskQueue:
    """
    SQLite-based persistent task queue with state machine.

    Usage:
        queue = PersistentTaskQueue()
        queue.initialize()

        # Enqueue
        tid = queue.enqueue("download", {"photo_id": "123"})

        # Dequeue (get next pending task, mark as running)
        task = queue.dequeue()
        if task:
            try:
                # Process...
                queue.mark_success(task.task_id)
            except Exception as e:
                queue.mark_failed(task.task_id, str(e))
    """

    SQL_CREATE_TASKS = """
    CREATE TABLE IF NOT EXISTS tasks (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id         TEXT    NOT NULL UNIQUE,
        task_type       TEXT    NOT NULL DEFAULT '',
        payload         TEXT    NOT NULL DEFAULT '{}',
        status          TEXT    NOT NULL DEFAULT 'pending',
        priority        INTEGER NOT NULL DEFAULT 0,
        retry_count     INTEGER NOT NULL DEFAULT 0,
        max_retries     INTEGER NOT NULL DEFAULT 3,
        next_retry_at   REAL    DEFAULT NULL,
        error_message   TEXT    DEFAULT '',
        created_at      TEXT    NOT NULL DEFAULT '',
        updated_at      TEXT    NOT NULL DEFAULT '',
        completed_at    TEXT    DEFAULT ''
    );
    """

    SQL_CREATE_INDEXES = [
        "CREATE INDEX IF NOT EXISTS idx_task_status ON tasks(status)",
        "CREATE INDEX IF NOT EXISTS idx_task_priority ON tasks(priority DESC)",
        "CREATE INDEX IF NOT EXISTS idx_task_retry ON "
        "tasks(next_retry_at) WHERE status='failed'",
        "CREATE INDEX IF NOT EXISTS idx_task_type ON tasks(task_type)",
    ]

    SQL_CREATE_DLQ = """
    CREATE TABLE IF NOT EXISTS dead_letters (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        original_task_id    TEXT NOT NULL,
        task_type          TEXT NOT NULL DEFAULT '',
        payload            TEXT NOT NULL DEFAULT '{}',
        final_error        TEXT DEFAULT '',
        total_retries      INTEGER DEFAULT 0,
        died_at            TEXT DEFAULT ''
    );
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
    ):
        self._db_path = db_path or DEFAULT_QUEUE_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        """Create tables and indexes."""
        c = self.conn.cursor()
        c.execute(self.SQL_CREATE_TASKS)
        for idx_sql in self.SQL_CREATE_INDEXES:
            c.execute(idx_sql)
        c.execute(self.SQL_CREATE_DLQ)
        self.conn.commit()
        logger.info(
            "PersistentTaskQueue initialized at %s",
            self._db_path,
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def enqueue(
        self,
        task_type: str,
        payload: Dict[str, Any],
        priority: int = 0,
        max_retries: int = 3,
        task_id: str = "",
    ) -> str:
        """
        Add a new task to the queue.

        Returns:
            The generated task ID.
        """
        import uuid
        tid = task_id or f"t_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        try:
            self.conn.execute(
                "INSERT INTO tasks (task_id, task_type, payload, "
                "status, priority, max_retries, created_at, "
                "updated_at) VALUES (?, ?, ?, 'pending', ?, "
                "?, ?, ?)",
                (
                    tid, task_type,
                    json.dumps(payload, ensure_ascii=False),
                    priority, max_retries, now, now,
                ),
            )
            self.conn.commit()
            logger.debug("Enqueued task=%s type=%s", tid, task_type)
            return tid
        except sqlite3.IntegrityError:
            logger.warning("Task %s already exists, skipping", tid)
            return tid

    async def dequeue(
        self, task_types: Optional[List[str]] = None,
    ) -> Optional[PersistedTask]:
        """
        Get next pending task and mark it as RUNNING.

        Also checks failed tasks whose next_retry_at has passed.
        Uses lock for safety in async context.
        """
        async with self._lock:
            return self._dequeue_sync(task_types)

    def _dequeue_sync(
        self,
        task_types: Optional[List[str]] = None,
    ) -> Optional[PersistedTask]:
        """Synchronous dequeue implementation."""
        now = time.time()
        conditions = ["(status='pending' OR ("
                      "status='failed' AND "
                      "(next_retry_at IS NULL OR "
                      f"next_retry_at <= {now})))"]
        params: list = []

        if task_types:
            placeholders = ",".join(["?"] * len(task_types))
            conditions.append(f"task_type IN ({placeholders})")
            params.extend(task_types)

        where_clause = " AND ".join(conditions)
        sql = (
            f"SELECT * FROM tasks WHERE {where_clause} "
            f"ORDER BY priority DESC, created_at ASC LIMIT 1"
        )

        row = self.conn.execute(sql, params).fetchone()
        if row is None:
            return None

        task_dict = dict(row)
        task_id = task_dict["task_id"]

        # Transition: pending/failed -> running
        now_str = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE tasks SET status='running', "
            "updated_at=? WHERE task_id=?",
            (now_str, task_id),
        )
        self.conn.commit()

        return self._row_to_task(task_dict)

    def mark_success(self, task_id: str) -> bool:
        """Mark a task as successfully completed."""
        now = datetime.now().isoformat()
        cur = self.conn.execute(
            "UPDATE tasks SET status='success', "
            "updated_at=?, completed_at=? WHERE task_id=?",
            (now, now, task_id),
        )
        self.conn.commit()
        ok = cur.rowcount > 0
        if ok:
            logger.debug("Task %s marked SUCCESS", task_id)
        return ok

    def mark_failed(
        self,
        task_id: str,
        error_message: str = "",
    ) -> bool:
        """
        Mark a task as failed.

        If retry_count < max_retries, stays in 'failed'
        with next_retry_at for later re-processing.
        Otherwise moves to DLQ (dead letter).
        """
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE task_id=?", (task_id,),
        ).fetchone()
        if row is None:
            return False

        task_dict = dict(row)
        new_retry = task_dict["retry_count"] + 1
        max_ret = task_dict["max_retries"]
        now = datetime.now().isoformat()

        if new_retry >= max_ret:
            # Move to DLQ
            return self._move_to_dlq(task_id, task_dict, error_message)

        # Stay in failed with exponential backoff
        delay = min(2 ** new_retry * 60, 3600)  # Cap at 1h
        next_retry = time.time() + delay

        self.conn.execute(
            "UPDATE tasks SET status='failed', retry_count=?, "
            "next_retry_at=?, error_message=?, updated_at=? "
            "WHERE task_id=?",
            (new_retry, next_retry, error_message, now, task_id),
        )
        self.conn.commit()
        logger.debug(
            "Task %s FAILED (%d/%d), next retry in %.0fs",
            task_id, new_retry, max_ret, delay,
        )
        return True

    def _move_to_dlq(
        self,
        task_id: str,
        original_row: Dict[str, Any],
        error_msg: str,
    ) -> bool:
        """Move a task permanently to Dead Letter Queue."""
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO dead_letters (original_task_id, "
            "task_type, payload, final_error, total_retries, "
            "died_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                original_row["task_id"],
                original_row["task_type"],
                original_row["payload"],
                error_msg,
                original_row["retry_count"] + 1,
                now,
            ),
        )
        self.conn.execute(
            "DELETE FROM tasks WHERE task_id=?", (task_id,),
        )
        self.conn.commit()
        logger.warning(
            "Task %s moved to DLQ after %d failures: %s",
            task_id, original_row["retry_count"] + 1, error_msg,
        )
        return True

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending or failed task."""
        cur = self.conn.execute(
            "UPDATE tasks SET status='cancelled', "
            "updated_at=? WHERE task_id=? AND "
            "status IN ('pending', 'failed')",
            (datetime.now().isoformat(), task_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def get_status_counts(
        self,
    ) -> Dict[str, int]:
        """Get count of tasks per status."""
        counts: Dict[str, int] = {}
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM tasks "
            "GROUP BY status",
        ).fetchall()
        for r in rows:
            counts[r["status"]] = r["cnt"]

        dlq_count = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM dead_letters",
        ).fetchone()["cnt"]
        counts["dlq"] = dlq_count
        return counts

    def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[PersistedTask]:
        """List tasks with optional status filter."""
        if status:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE status=? "
                "ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM tasks ORDER BY "
                "created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_task(dict(r)) for r in rows]

    def list_dead_letters(self, limit: int = 20) -> List[Dict]:
        """List items in dead letter queue."""
        rows = self.conn.execute(
            "SELECT * FROM dead_letters ORDER BY "
            "died_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def retry_dlq_item(self, dlq_id: int) -> Optional[str]:
        """Re-enqueue a dead letter item back into the main queue."""
        row = self.conn.execute(
            "SELECT * FROM dead_letters WHERE id=?", (dlq_id,),
        ).fetchone()
        if row is None:
            return None

        dlr = dict(row)
        new_tid = self.enqueue(
            dlr["task_type"],
            json.loads(dlr["payload"]),
            max_retries=dlr["total_retries"] + 2,  # Give extra chances
        )
        self.conn.execute(
            "DELETE FROM dead_letters WHERE id=?", (dlq_id,),
        )
        self.conn.commit()
        logger.info("DLQ item %d re-enqueued as %s", dlq_id, new_tid)
        return new_tid

    def clear_completed(self) -> int:
        """Remove all terminal-state tasks (success/cancelled)."""
        cur = self.conn.execute(
            "DELETE FROM tasks WHERE status IN ('success', 'cancelled')",
        )
        self.conn.commit()
        count = cur.rowcount
        if count > 0:
            logger.info("Cleared %d completed tasks", count)
        return count

    @staticmethod
    def _row_to_task(row: Dict[str, Any]) -> PersistedTask:
        """Convert DB row dict to PersistedTask."""
        try:
            payload = json.loads(row.get("payload", "{}"))
        except (json.JSONDecodeError, TypeError):
            payload = {}

        status_val = row.get("status", "pending")
        try:
            status = TaskStatus(status_val)
        except ValueError:
            status = TaskStatus.PENDING

        return PersistedTask(
            task_id=row.get("task_id", ""),
            task_type=row.get("task_type", ""),
            payload=payload,
            status=status,
            priority=row.get("priority", 0),
            retry_count=row.get("retry_count", 0),
            max_retries=row.get("max_retries", 3),
            next_retry_at=row.get("next_retry_at"),
            error_message=row.get("error_message", ""),
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
            completed_at=row.get("completed_at", ""),
        )


def create_task_queue(db_path: Optional[Path] = None) -> PersistentTaskQueue:
    """Factory function."""
    queue = PersistentTaskQueue(db_path=db_path)
    queue.initialize()
    return queue
