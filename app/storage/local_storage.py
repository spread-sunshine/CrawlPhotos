# -*- coding: utf-8 -*-
"""
Local filesystem storage manager.
本地存储管理器 - 按年/月/日目录结构归档存储.

Directory structure:
{root}/{year}/{month_num}_{month_name}/{date}/
    {YYYYMMDD}_{seq:04d}_qqgroup.{ext}
    metadata.json
"""

import json
from calendar import month_name, month_abbr
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config.logging_config import get_logger
from app.models.photo import ProcessedPhoto, DailyMetadata

logger = get_logger(__name__)

# Month number to English name mapping
MONTH_NAMES = {
    i: month_name[i] for i in range(1, 13)
}


class StorageManager:
    """
    Manages local file storage of filtered baby photos.

    Responsibilities:
    - Create date-based directory structure.
    - Save photos with standardized naming.
    - Generate daily metadata.json files.
    - Check disk space availability.
    """

    def __init__(
        self,
        root_directory: str,
        directory_format: str = "{root}/{year}/{month_num}"
                                  "_{month_name}/{date}",
        filename_format: str = "{date}_{seq:04d}_qqgroup.{ext}",
    ):
        self._root = Path(root_directory)
        self._dir_format = directory_format
        self._filename_format = filename_format

        # Track sequence numbers per date
        _seq_counters: Dict[str, int] = {}

        self._root.mkdir(parents=True, exist_ok=True)
        logger.info(
            "StorageManager initialized: root=%s",
            self._root.resolve(),
        )

    def resolve_output_path(
        self,
        target_date: Optional[date] = None,
        ext: str = "jpg",
    ) -> tuple:
        """
        Resolve full output path for a photo on a given date.

        Returns:
            (full_path, date_directory)
        """
        if target_date is None:
            target_date = date.today()

        dir_path = self._resolve_dir_path(target_date)
        seq = self._next_seq(target_date.isoformat())
        filename = self._build_filename(
            target_date, seq, ext
        )
        full_path = dir_path / filename
        return full_path, dir_path

    def store_photo(
        self,
        source_path: Path,
        target_date: Optional[date] = None,
        ext: str = "jpg",
    ) -> Optional[Path]:
        """
        Copy/move a processed photo to its final location.

        Args:
            source_path: Path to the processed photo file.
            target_date: Date for directory placement.
            ext: File extension.

        Returns:
            Final stored path, or None on failure.
        """
        dest_path, _ = self.resolve_output_path(
            target_date, ext
        )

        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file to destination
            import shutil
            shutil.copy2(str(source_path), str(dest_path))

            logger.debug(
                "Stored photo: %s -> %s",
                source_path.name,
                dest_path,
            )
            return dest_path

        except Exception as exc:
            logger.error(
                "Failed to store photo %s: %s",
                source_path,
                exc,
            )
            return None

    def write_daily_metadata(
        self,
        meta: DailyMetadata,
    ) -> bool:
        """
        Write daily summary metadata JSON file.

        Args:
            meta: DailyMetadata instance to serialize.

        Returns:
            Success boolean.
        """
        target_date = date.fromisoformat(meta.date)
        dir_path = self._resolve_dir_path(target_date)
        meta_path = dir_path / "metadata.json"

        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta.to_dict(), f, ensure_ascii=False, indent=2)

            logger.info(
                "Wrote metadata: %s (total=%d, target=%d)",
                meta_path,
                meta.total_photos,
                meta.target_photos,
            )
            return True

        except Exception as exc:
            logger.error("Failed to write metadata: %s", exc)
            return False

    def check_disk_space(
        self,
        warning_gb: float = 20.0,
        critical_gb: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Check available disk space on storage volume.

        Args:
            warning_gb: Threshold for warning level (GB).
            critical_gb: Threshold for critical level (GB).

        Returns:
            Disk space info dict.
        """
        import shutil

        total, used, free = shutil.disk_usage(self._root)
        free_gb = free / (1024**3)

        status = "ok"
        if free_gb < critical_gb:
            status = "critical"
        elif free_gb < warning_gb:
            status = "warning"

        return {
            "status": status,
            "free_gb": round(free_gb, 2),
            "used_gb": round(used / (1024**3), 2),
            "total_gb": round(total / (1024**3), 2),
        }

    def list_stored_dates(
        self, year: Optional[int] = None,
    ) -> List[date]:
        """List all dates that have stored photos."""
        results = []
        search_root = self._root
        if year:
            search_root = self._root / str(year)

        if not search_root.exists():
            return results

        for month_dir in sorted(search_root.iterdir()):
            if not month_dir.is_dir():
                continue
            for day_dir in sorted(month_dir.iterdir()):
                if day_dir.is_dir():
                    try:
                        d = date.fromisoformat(day_dir.name)
                        results.append(d)
                    except ValueError:
                        pass

        return results

    # ==================== Private Helpers ====================

    def _resolve_dir_path(self, target_date: date) -> Path:
        """Build the directory path for a specific date."""
        formatted = self._dir_format.format(
            root=self._root,
            year=target_date.year,
            month_num=f"{target_date.month:02d}",
            month_name=MONTH_NAMES.get(target_date.month, f"M{target_date.month}"),
            date=target_date.isoformat(),
        )
        return Path(formatted)

    @staticmethod
    def _build_filename(
        target_date: date,
        seq: int,
        ext: str,
    ) -> str:
        """Build standard filename."""
        return f"{target_date.isoformat().replace('-', '')}" \
               f"_{seq:04d}_qqgroup.{ext}"

    def _next_seq(self, date_key: str) -> int:
        """Get next sequence number for this date."""
        if not hasattr(self, "_seq_counters"):
            self._seq_counters = {}

        current = self._seq_counters.get(date_key, 0)
        current += 1
        self._seq_counters[date_key] = current
        return current
