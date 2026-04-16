# -*- coding: utf-8 -*-
"""
Three-layer photo deduplication manager.
三层照片去重管理器.

Dedup layers (checked in order):
    Layer 0: Memory Set   - O(1) in-memory lookup within single run.
                            Avoids DB queries for photos already seen
                            this session. Cleared after each pipeline run.
    Layer 1: DB photo_id  - UNIQUE index on source photo_id.
                            Persistent across runs.
    Layer 2: DB file_hash - UNIQUE index on SHA256 content hash.
                            Catches re-uploaded / renamed duplicates.

Usage:
    dedup = DedupManager(db)
    # Pre-load existing IDs into memory cache
    await dedup.warm_up()

    # Check if new (returns reason if duplicate)
    is_dup, reason = await dedup.check(photo_id="abc123")
    if not is_dup:
        dedup.mark_seen(photo_id="abc123")  # Add to L0 cache
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

from app.database.db import Database

logger = logging.getLogger(__name__)


class DedupResult:
    """Result of a dedup check."""

    __slots__ = ("is_duplicate", "layer", "reason")

    def __init__(
        self,
        is_duplicate: bool = False,
        layer: str = "",
        reason: str = "",
    ):
        self.is_duplicate = is_duplicate
        self.layer = layer  # "L0_memory", "L1_photo_id", "L2_file_hash"
        self.reason = reason

    def __bool__(self) -> bool:
        return self.is_duplicate


class DedupManager:
    """
    Three-layer dedup manager coordinating memory and DB checks.

    Layer 0 (Memory): In-memory Set of photo_ids seen this run.
                      Fastest path, cleared per run.

    Layer 1 (DB): SQLite UNIQUE on photo_id column.
                   Persists across restarts.

    Layer 2 (DB): SQLite UNIQUE on file_hash (SHA256).
                   Catches content-level duplicates even if
                   photo_id differs.
    """

    def __init__(self, db: Database):
        self._db = db
        # Layer 0: In-memory seen set
        self._seen_photo_ids: set = set()
        self._seen_file_hashes: set = set()
        self._stats = {
            "l0_hits": 0,
            "l1_hits": 0,
            "l2_hits": 0,
            "total_checks": 0,
        }

    async def warm_up(
        self, limit: int = 10000,
    ) -> None:
        """
        Pre-populate Layer 0 memory cache from DB.

        Loads recent photo_ids and file_hashes into memory sets
        so the first pipeline run benefits from O(1) lookups.
        """
        logger.info("Warming up dedup cache from DB...")
        rows = self._db.conn.execute(
            "SELECT photo_id, file_hash FROM photos "
            "WHERE file_hash IS NOT NULL LIMIT ?",
            (limit,),
        ).fetchall()

        count = 0
        for row in rows:
            if row["photo_id"]:
                self._seen_photo_ids.add(row["photo_id"])
            if row["file_hash"]:
                self._seen_file_hashes.add(row["file_hash"])
            count += 1

        self._seen_photo_ids.update(
            r[0] for r in self._db.conn.execute(
                "SELECT photo_id FROM photos LIMIT ?",
                (limit,),
            ).fetchall() if r and r[0]
        )
        logger.info(
            "Dedup cache warmed: %d photo_ids, %d hashes",
            len(self._seen_photo_ids),
            len(self._seen_file_hashes),
        )

    def clear_cache(self) -> None:
        """Clear Layer 0 memory cache (call between pipeline runs)."""
        size_before = len(self._seen_photo_ids)
        self._seen_photo_ids.clear()
        self._seen_file_hashes.clear()
        self._stats = {
            "l0_hits": 0,
            "l1_hits": 0,
            "l2_hits": 0,
            "total_checks": 0,
        }
        logger.debug("Dedup cache cleared (%d entries)", size_before)

    def check_by_photo_id(self, photo_id: str) -> DedupResult:
        """
        Check if photo_id is duplicate across all layers.

        Returns:
            DedupResult indicating whether it's a duplicate and why.
        """
        self._stats["total_checks"] += 1

        # Layer 0: Memory set (fastest)
        if photo_id in self._seen_photo_ids:
            self._stats["l0_hits"] += 1
            return DedupResult(
                is_duplicate=True,
                layer="L0_memory",
                reason=f"Already seen this run: {photo_id}",
            )

        # Layer 1: DB photo_id
        if self._db.exists_photo_id(photo_id):
            self._seen_photo_ids.add(photo_id)  # Cache for future
            self._stats["l1_hits"] += 1
            return DedupResult(
                is_duplicate=True,
                layer="L1_photo_id",
                reason=f"Exists in DB: {photo_id}",
            )

        return DedupResult(is_duplicate=False)

    def check_by_file_hash(self, file_hash: str) -> DedupResult:
        """
        Check if file_hash is duplicate across all layers.

        Called after download completes (when hash becomes available).
        """
        # Layer 0: Memory
        if file_hash in self._seen_file_hashes:
            self._stats["l0_hits"] += 1
            return DedupResult(
                is_duplicate=True,
                layer="L0_memory",
                reason="Hash seen this run",
            )

        # Layer 2: DB file_hash
        if self._db.exists_file_hash(file_hash):
            self._seen_file_hashes.add(file_hash)
            self._stats["l2_hits"] += 1
            return DedupResult(
                is_duplicate=True,
                layer="L2_file_hash",
                reason=f"File hash exists in DB: "
                       f"{file_hash[:16]}...",
            )

        return DedupResult(is_duplicate=False)

    def mark_seen(
        self,
        photo_id: str,
        file_hash: Optional[str] = None,
    ) -> None:
        """Add identifiers to Layer 0 memory cache."""
        if photo_id:
            self._seen_photo_ids.add(photo_id)
        if file_hash:
            self._seen_file_hashes.add(file_hash)

    @property
    def stats(self) -> dict:
        """Return dedup statistics for this session."""
        s = dict(self._stats)
        s["cache_size_ids"] = len(self._seen_photo_ids)
        s["cache_size_hashes"] = len(self._seen_file_hashes)
        return s

    def log_stats(self) -> None:
        """Log current dedup statistics."""
        s = self.stats
        total_hits = (
            s["l0_hits"] + s["l1_hits"] + s["l2_hits"]
        )
        logger.info(
            "Dedup stats: checks=%d hits=%d "
            "(L0=%d L1=%d L2=%d) cache=%d/%d",
            s["total_checks"],
            total_hits,
            s["l0_hits"],
            s["l1_hits"],
            s["l2_hits"],
            s["cache_size_ids"],
            s["cache_size_hashes"],
        )
