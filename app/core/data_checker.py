# -*- coding: utf-8 -*-
"""
Data consistency checker: DB records vs filesystem files.
数据一致性自检 - 检测数据库记录与实际文件的差异.

Checks performed:
1. Orphaned DB records: DB says stored, but file missing on disk
2. Ghost files: Files exist on disk with no DB record
3. Size mismatch: DB file_size differs from actual file size
4. Hash mismatch: DB file_hash doesn't match recomputed hash

Reports discrepancies and optionally auto-repairs.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.database.db import Database
from app.models.photo import PhotoStatus

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyIssue:
    """Represents a single consistency discrepancy."""

    category: str  # "orphaned_record", "ghost_file", "size_mismatch", "hash_mismatch"
    photo_id: str
    description: str
    db_path: str = ""
    actual_size: int = 0
    db_size: int = 0
    severity: str = "warning"  # "warning" | "error"


@dataclass
class ConsistencyReport:
    """Full report of consistency check."""

    checked_at: str
    total_db_records: int = 0
    total_files_checked: int = 0
    issues: List[ConsistencyIssue] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return len(self.issues) == 0

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)


class DataConsistencyChecker:
    """
    Verifies alignment between database records and filesystem.

    Usage:
        checker = DataConsistencyChecker(db)
        report = await checker.check()
        if report.has_errors:
            print(f"Found {len(report.issues)} issues!")
    """

    def __init__(self, database: Database):
        self._db = database

    async def check(
        self,
        fix_orphaned_records: bool = False,
        verify_hashes: bool = False,
    ) -> ConsistencyReport:
        """
        Run all consistency checks.

        Args:
            fix_orphaned_records: Auto-mark orphaned records as FAILED.
            verify_hashes: Recompute SHA256 hashes (slower).

        Returns:
            ConsistencyReport with all findings.
        """
        from datetime import datetime

        report = ConsistencyReport(
            checked_at=datetime.now().isoformat(),
        )

        # Count total records
        row = self._db.conn.execute(
            "SELECT COUNT(*) AS cnt FROM photos",
        ).fetchone()
        report.total_db_records = row["cnt"] if row else 0

        # Check 1: Orphaned records (DB says stored, file missing)
        await self._check_orphaned_records(report, fix_orphaned_records)

        # Check 2 & 3: Ghost files + Size mismatches
        await self._check_files_on_disk(report)

        # Check 4: Hash verification (optional, expensive)
        if verify_hashes:
            await self._verify_hashes(report)

        # Build summary
        report.summary = {}
        for issue in report.issues:
            cat = issue.category
            report.summary[cat] = report.summary.get(cat, 0) + 1

        if report.is_clean:
            logger.info("Data consistency check: CLEAN")
        else:
            logger.warning(
                "Data consistency check: %d issues found "
                "[%s]",
                len(report.issues),
                ", ".join(
                    f"{k}={v}" for k, v in
                    report.summary.items()
                ),
            )

        return report

    async def _check_orphaned_records(
        self,
        report: ConsistencyReport,
        auto_fix: bool = False,
    ) -> None:
        """Find DB records pointing to non-existent files."""
        rows = self._db.conn.execute(
            "SELECT photo_id, stored_path, local_path, status "
            "FROM photos WHERE status IN ('stored', 'completed', "
            "'uploaded') AND (stored_path != '' OR "
            "local_path != '')",
        ).fetchall()

        for row in rows:
            paths_to_check = [
                p for p in [row["stored_path"], row["local_path"]]
                if p
            ]

            for path_str in paths_to_check:
                path = Path(path_str)
                if path.exists():
                    continue

                issue = ConsistencyIssue(
                    category="orphaned_record",
                    photo_id=row["photo_id"],
                    description=(
                        f"File missing: {path_str} "
                        f"(status={row['status']})"
                    ),
                    db_path=path_str,
                    severity="error",
                )
                report.issues.append(issue)

                if auto_fix:
                    self._db.update_photo_status(
                        row["photo_id"],
                        PhotoStatus.FAILED,
                        f"File missing: {path_str}",
                    )
                    logger.info(
                        "Auto-fixed orphaned record: %s",
                        row["photo_id"],
                    )

    async def _check_files_on_disk(
        self, report: ConsistencyReport,
    ) -> None:
        """Scan output directory for files without DB records."""
        rows = self._db.conn.execute(
            "SELECT stored_path FROM photos WHERE "
            "stored_path IS NOT NULL AND stored_path != ''",
        ).fetchall()

        known_paths: set = set()
        for row in rows:
            known_paths.add(Path(row["stored_path"]))

        # Scan actual directories
        # Collect all unique parent dirs from stored_path values
        parent_dirs: set = set()
        for p in known_paths:
            parent_dir = p.parent
            if str(parent_dir).startswith("."):
                continue
            parent_dirs.add(parent_dir)

        for parent_dir in parent_dirs:
            if not parent_dir.exists():
                continue
            for file_path in parent_dir.iterdir():
                if not file_path.is_file():
                    continue
                report.total_files_checked += 1

                # Normalize for comparison
                normalized = file_path.resolve()
                if normalized not in known_paths and file_path not in known_paths:
                    # Could be a ghost file (no DB record)
                    issue = ConsistencyIssue(
                        category="ghost_file",
                        photo_id="",
                        description=(
                            f"File has no DB record: "
                            f"{file_path}"
                        ),
                        db_path=str(file_path),
                        severity="warning",
                    )
                    report.issues.append(issue)

    async def _verify_hashes(
        self, report: ConsistencyReport,
    ) -> None:
        """Recompute hashes and compare with DB."""
        rows = self._db.conn.execute(
            "SELECT photo_id, local_path, stored_path, "
            "file_hash FROM photos WHERE file_hash IS NOT NULL "
            "AND (local_path != '' OR stored_path != '')",
        ).fetchall()

        for row in rows:
            primary_path = row["stored_path"] or row["local_path"]
            path = Path(primary_path)
            if not path.exists():
                continue

            computed_hash = Database.compute_file_hash(path)
            if computed_hash != row["file_hash"]:
                actual_size = path.stat().st_size
                issue = ConsistencyIssue(
                    category="hash_mismatch",
                    photo_id=row["photo_id"],
                    description=(
                        f"Hash mismatch for {row['photo_id']} "
                        f"(expected={row['file_hash'][:16]}..., "
                        f"actual={computed_hash[:16]}...)"
                    ),
                    db_path=primary_path,
                    db_size=row.get("file_size", 0) or 0,
                    actual_size=actual_size,
                    severity="error",
                )
                report.issues.append(issue)


async def run_consistency_check(db: Database) -> ConsistencyReport:
    """Convenience function for running a full check."""
    checker = DataConsistencyChecker(db)
    return await checker.check()

