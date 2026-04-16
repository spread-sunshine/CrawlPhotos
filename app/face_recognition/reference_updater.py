# -*- coding: utf-8 -*-
"""
Reference Photo Auto-Update Mechanism.
参考照片自动更新机制 - 用高置信度识别结果更新目标人物参考照库.

Rationale:
    Children's facial features change over time. Periodically
    updating the reference photo set with high-confidence
    recognition results keeps the face model accurate as
    the child grows.

Strategy:
    - Collect photos where confidence >= update_threshold
      (higher than normal min_confidence)
    - Dedup against existing reference photos (SHA256 hash)
    - Add new unique photos to reference directory
    - Rotate out oldest references if max_count exceeded
"""

import hashlib
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.config.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class UpdatePolicy:
    """Configuration for reference photo updates."""
    target_name: str
    reference_dir: Path
    update_confidence_threshold: float = 0.92  # Higher than match threshold
    max_reference_photos: int = 10            # Max refs per target
    min_update_interval_days: int = 7         # Don't update too frequently
    enabled: bool = True


@dataclass
class UpdateResult:
    """Result of a reference photo update cycle."""
    target_name: str
    total_candidates: int = 0
    added_count: int = 0
    skipped_duplicate: int = 0
    removed_old: int = 0
    current_total: int = 0
    last_update_time: Optional[datetime] = None


class ReferencePhotoUpdater:
    """
    Manages automatic updates to reference photo sets.

    Usage:
        updater = ReferencePhotoUpdater(config)
        # After each batch of recognition:
        results = await recognizer.recognize_batch(photos)
        for res in results:
            if res.is_match and res.confidence >= 0.92:
                updater.add_candidate(
                    target_name=res.target_name,
                    photo_path=res.photo_path,
                    confidence=res.confidence,
                )

        # Run periodic update (e.g., weekly):
        update_result = updater.run_update(target_name="宝贝女儿")
    """

    def __init__(self, base_config: Dict[str, Any]):
        """
        Args:
            base_config: The full config dict with
                          face_recognition.targets.
        """
        fr_cfg = base_config.get("face_recognition", {})
        self._targets_raw = fr_cfg.get("targets", [])
        self._policies: Dict[str, UpdatePolicy] = {}
        self._candidates: Dict[str, List[Dict[str, Any]]] = {}
        self._last_update: Dict[str, datetime] = {}
        self._state_file: Path = Path("data") / "ref_updater_state.json"

        for t in self._targets_raw:
            name = t.get("name", "")
            ref_dir = Path(t.get("reference_photos_dir", ""))
            if not name or not ref_dir:
                continue
            self._policies[name] = UpdatePolicy(
                target_name=name,
                reference_dir=ref_dir,
                update_confidence_threshold=t.get(
                    "update_confidence_threshold",
                    0.92,
                ),
                max_reference_photos=t.get(
                    "max_reference_photos", 10,
                ),
                min_update_interval_days=t.get(
                    "min_update_interval_days", 7,
                ),
                enabled=t.get("enabled", True),
            )
            self._candidates[name] = []
            self._last_update[name] = datetime.min
            ref_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "ReferencePhotoUpdater initialized with %d targets",
            len(self._policies),
        )

    def add_candidate(
        self,
        target_name: str,
        photo_path: Path,
        confidence: float,
    ) -> None:
        """Register a candidate photo for potential reference update."""
        if target_name not in self._policies:
            return
        policy = self._policies[target_name]
        if not policy.enabled:
            return
        if confidence < policy.update_confidence_threshold:
            return
        if not photo_path.exists():
            return

        file_hash = self._file_hash(photo_path)
        self._candidates[target_name].append({
            "path": str(photo_path),
            "confidence": confidence,
            "hash": file_hash,
            "collected_at": datetime.now().isoformat(),
        })

    def run_update(self, target_name: str) -> Optional[UpdateResult]:
        """
        Execute an update cycle for the given target.

        Returns UpdateResult or None if skip conditions apply.
        """
        if target_name not in self._policies:
            logger.warning("Unknown target: %s", target_name)
            return None

        policy = self._policies[target_name]
        if not policy.enabled:
            return UpdateResult(target_name=target_name)

        # Check interval
        last = self._last_update.get(target_name, datetime.min)
        if datetime.now() - last < timedelta(
            days=policy.min_update_interval_days,
        ):
            logger.debug(
                "Skipping update for '%s': interval not met "
                "(last=%s)",
                target_name, last.date(),
            )
            return None

        candidates = self._candidates.get(target_name, [])
        result = UpdateResult(
            target_name=target_name,
            total_candidates=len(candidates),
        )

        # Sort by confidence descending
        candidates.sort(
            key=lambda c: c["confidence"], reverse=True,
        )

        existing_hashes = self._get_existing_hashes(policy.reference_dir)

        new_refs: List[Path] = []
        for c in candidates[:policy.max_reference_photos * 2]:  # Take extra candidates
            if c["hash"] in existing_hashes:
                result.skipped_duplicate += 1
                continue

            src = Path(c["path"])
            if not src.exists():
                continue

            # Copy to reference dir with timestamped name
            dst = policy.reference_dir / (
                f"ref_{datetime.now():%Y%m%d_%H%M%S}_"
                f"{c['confidence']:.0%}_{src.suffix}"
            )
            try:
                shutil.copy2(src, dst)
                new_refs.append(dst)
                existing_hashes.add(c["hash"])
                result.added_count += 1
                logger.info(
                    "Added reference for '%s': %s (%.1f%%)",
                    target_name, dst.name, c["confidence"],
                )
            except Exception as exc:
                logger.error(
                    "Failed to copy reference: %s", exc,
                )

        # Trim to max count (remove oldest first)
        current_files = sorted(
            policy.reference_dir.glob("ref_*.*"),
            key=lambda p: p.stat().st_mtime,
        )
        while len(current_files) > policy.max_reference_photos:
            oldest = current_files.pop(0)
            try:
                oldest.unlink()
                result.removed_old += 1
                logger.debug(
                    "Removed old reference: %s", oldest.name,
                )
            except Exception as exc:
                logger.warning(
                    "Could not remove old ref %s: %s",
                    oldest, exc,
                )

        result.current_total = len(current_files) + len(new_refs)
        result.last_update_time = datetime.now()

        # Cleanup and record
        self._candidates[target_name] = []
        self._last_update[target_name] = datetime.now()
        self._save_state()

        logger.info(
            "Reference update for '%s': +%d, dup=%d, "
            "removed=%d, total=%d",
            target_name,
            result.added_count,
            result.skipped_duplicate,
            result.removed_old,
            result.current_total,
        )

        return result

    def run_all_updates(self) -> List[UpdateResult]:
        """Run update cycles for all targets."""
        results: List[UpdateResult] = []
        for name in self._policies:
            r = self.run_update(name)
            if r is not None:
                results.append(r)
        return results

    def _get_existing_hashes(self, ref_dir: Path) -> Set[str]:
        """Compute SHA256 hashes for existing reference photos."""
        hashes: Set[str] = set()
        if not ref_dir.exists():
            return hashes
        for f in ref_dir.iterdir():
            if f.is_file():
                h = self._file_hash(f)
                hashes.add(h)
        return hashes

    @staticmethod
    def _file_hash(path: Path) -> str:
        """SHA256 hex digest of a file."""
        h = hashlib.sha256()
        buf_size = 65536
        with open(path, "rb") as f:
            while True:
                chunk = f.read(buf_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def _save_state(self) -> None:
        """Persist state for restart recovery."""
        import json
        state_data = {
            name: {
                "last_update": dt.isoformat(),
                "pending_candidates": len(cands),
            }
            for name, dt in self._last_update.items()
            for cands in [self._candidates.get(name, [])]
        }
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps(state_data, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("Could not save state: %s", exc)


def create_ref_updater(config: dict) -> ReferencePhotoUpdater:
    """Factory function."""
    return ReferencePhotoUpdater(base_config=config)
