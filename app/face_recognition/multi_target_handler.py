# -*- coding: utf-8 -*-
"""
Multi-target face recognition handler.
多目标人物识别处理器 - 支持同时识别多个目标人物(如多个孩子).

Handles parallel recognition against multiple target faces,
aggregates results with per-target confidence tracking.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config.logging_config import get_logger
from app.face_recognition.interfaces import IFaceRecognizer
from app.face_recognition.models import RecognitionResult

logger = get_logger(__name__)


@dataclass
class TargetMatch:
    """Result of matching a photo against a specific target."""
    target_name: str
    is_match: bool
    confidence: float
    bbox: Optional[Tuple[int, int, int, int]] = None


@dataclass
class MultiTargetResult:
    """Aggregated result for a single photo across all targets."""
    photo_path: str
    photo_id: str
    matches: Dict[str, TargetMatch] = field(default_factory=dict)
    # Best match summary for the photo
    best_target: str = ""
    best_confidence: float = 0.0
    is_any_match: bool = False


class MultiTargetHandler:
    """
    Orchestrates recognition of photos against multiple targets.

    Features:
        - Parallel batch processing across targets
        - Per-target confidence thresholds
        - Result aggregation with best-match selection
        - Target enable/disable at runtime
    """

    def __init__(
        self,
        recognizer: IFaceRecognizer,
        target_configs: List[Dict[str, Any]],
        default_min_confidence: float = 0.80,
    ):
        """
        Args:
            recognizer: The underlying face recognizer instance.
            target_configs: List of target config dicts from YAML.
                Each dict has: name, reference_photos_dir, min_confidence, enabled.
            default_min_confidence: Fallback threshold.
        """
        self._recognizer = recognizer
        self._default_confidence = default_min_confidence
        # Parse targets
        self._targets: Dict[str, Dict[str, Any]] = {}
        for cfg in target_configs:
            name = cfg.get("name", "")
            if not name:
                continue
            self._targets[name] = {
                "min_confidence": cfg.get(
                    "min_confidence", default_min_confidence,
                ),
                "enabled": cfg.get("enabled", True),
                "ref_dir": cfg.get("reference_photos_dir", ""),
            }

        logger.info(
            "MultiTargetHandler initialized with %d targets: %s",
            len(self._targets),
            list(self._targets.keys()),
        )

    @property
    def target_names(self) -> List[str]:
        return list(self._targets.keys())

    @property
    def enabled_targets(self) -> List[str]:
        return [
            name
            for name, cfg in self._targets.items()
            if cfg["enabled"]
        ]

    def set_target_enabled(
        self, target_name: str, enabled: bool,
    ) -> None:
        """Enable or disable a specific target."""
        if target_name in self._targets:
            old = self._targets[target_name]["enabled"]
            self._targets[target_name]["enabled"] = enabled
            logger.info(
                "Target '%s' %s",
                target_name,
                "ENABLED" if enabled else "DISABLED",
            )
        else:
            logger.warning("Unknown target: %s", target_name)

    async def recognize_photo(
        self, image_path: Path, photo_id: str = "",
    ) -> MultiTargetResult:
        """
        Recognize a single photo against all enabled targets.

        Runs recognitions concurrently using asyncio.gather.
        """
        result = MultiTargetResult(
            photo_path=str(image_path),
            photo_id=photo_id or image_path.name,
        )

        if not self.enabled_targets:
            result.is_any_match = False
            return result

        active_targets = [
            t for t in self._targets.values() if t["enabled"]
        ]

        # Run recognition concurrently for each target
        coros = []
        for name, cfg in self._targets.items():
            if not cfg["enabled"]:
                continue
            coros.append(
                self._recognize_single_target(
                    image_path, name, cfg["min_confidence"],
                )
            )

        if coros:
            outcomes = await asyncio.gather(*coros, return_exceptions=True)
            
            for i, outcome in enumerate(outcomes):
                target_name = self.enabled_targets[i]
                if isinstance(outcome, Exception):
                    logger.error(
                        "Recognition error for target '%s': %s",
                        target_name, outcome,
                    )
                    result.matches[target_name] = TargetMatch(
                        target_name=target_name,
                        is_match=False,
                        confidence=0.0,
                    )
                    continue
                
                match: TargetMatch = outcome
                result.matches[target_name] = match
                if match.is_match and match.confidence > result.best_confidence:
                    result.best_confidence = match.confidence
                    result.best_target = target_name

        result.is_any_match = (
            result.best_confidence > 0
            and len(result.best_target) > 0
        )

        return result

    async def recognize_batch(
        self,
        photo_paths: List[Path],
        max_concurrent: int = 5,
    ) -> List[MultiTargetResult]:
        """
        Recognize a batch of photos with concurrency control.

        Args:
            photo_paths: List of paths to photos.
            max_concurrent: Max parallel recognitions.

        Returns:
            List of results in same order as input.
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _bounded_recognize(path: Path) -> MultiTargetResult:
            async with semaphore:
                return await self.recognize_photo(path)

        tasks = [_bounded_recognize(p) for p in photo_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        output: List[MultiTargetResult] = []
        for r in results:
            if isinstance(r, Exception):
                output.append(MultiTargetResult(
                    photo_path="error", photo_id="", is_any_match=False,
                ))
            else:
                output.append(r)
        return output

    async def _recognize_single_target(
        self,
        image_path: Path,
        target_name: str,
        min_confidence: float,
    ) -> TargetMatch:
        """Run recognition for one target on one photo."""
        try:
            rec_result: RecognitionResult = (
                await self._recognizer.recognize(str(image_path))
            )
            is_match = rec_result.contains_target
            conf = rec_result.best_confidence

            # Apply per-target min_confidence override
            effective_threshold = min_confidence
            if is_match and conf < effective_threshold:
                is_match = False

            bbox_tuple = None
            if rec_result.all_face_detections:
                fd = rec_result.all_face_detections[0]
                bb = fd.bounding_box
                bbox_tuple = (bb.x, bb.y, bb.width, bb.height)

            return TargetMatch(
                target_name=target_name,
                is_match=is_match,
                confidence=conf,
                bbox=bbox_tuple,
            )

        except Exception as exc:
            logger.error(
                "Error recognizing '%s' against target '%s': %s",
                image_path.name, target_name, exc,
            )
            return TargetMatch(
                target_name=target_name,
                is_match=False,
                confidence=0.0,
            )


def create_multi_target_handler(
    recognizer: IFaceRecognizer,
    config: dict,
) -> MultiTargetHandler:
    """Factory: create handler from full config dict."""
    fr_cfg = config.get("face_recognition", {})
    targets = fr_cfg.get("targets", [])
    default_conf = 0.80
# Check for global default
    for t in targets:
        if t.get("min_confidence"):
            default_conf = t["min_confidence"]
            break
    
    return MultiTargetHandler(
        recognizer=recognizer,
        target_configs=targets,
        default_min_confidence=default_conf,
    )
