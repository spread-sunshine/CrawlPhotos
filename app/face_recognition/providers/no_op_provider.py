# -*- coding: utf-8 -*-
"""
No-Op / Dummy face recognition provider.
空操作人脸识别器 - Phase 1占位实现，所有照片均视为包含目标人物.

This provider accepts all images as containing target persons,
allowing the pipeline to run end-to-end during development
before real recognition providers are implemented.

Replace with actual provider (TencentCloud/Baidu/InsightFace) in Phase 2.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from app.face_recognition.interfaces import IFaceRecognizer
from app.face_recognition.models import (
    BoundingBox,
    FaceDetection,
    ProviderInfo,
    ProviderType,
    RecognitionResult,
    TargetConfig,
)

logger = logging.getLogger(__name__)


class NoOpRecognizer(IFaceRecognizer):
    """
    Placeholder face recognizer that always returns positive results.

    In Phase 1, this allows testing the full pipeline without needing
    real API keys or models. Every image is treated as containing
    all configured target persons with 100% confidence.
    """

    def __init__(self, **kwargs: Any):
        self._targets: List[TargetConfig] = []
        self._kwargs = kwargs

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.TENCENT_CLOUD

    @property
    def provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            name="no_op_placeholder",
            version="0.1.0",
            description=(
                "Phase 1 placeholder - "
                "all images accepted"
            ),
        )

    async def initialize(
        self, targets: List[TargetConfig],
    ) -> bool:
        self._targets = targets
        names = [t.name for t in targets]
        logger.info(
            "NoOpRecognizer initialized with targets=%s", names,
        )
        return True

    async def health_check(self) -> Dict[str, Any]:
        return {
            "healthy": True,
            "latency_ms": 0.0,
            "quota_remaining": -1,
            "message": "NoOp provider - always healthy",
        }

    async def detect_faces(
        self,
        image_path: str,
        max_faces: int = 10,
    ) -> List[FaceDetection]:
        logger.debug(
            "NoOp detect_faces: %s (max=%d)",
            image_path, max_faces,
        )
        # Return one dummy face detection per target
        results = []
        for idx, target in enumerate(self._targets[:max_faces]):
            results.append(
                FaceDetection(
                    bounding_box=BoundingBox(
                        x=0, y=0,
                        width=100, height=100,
                    ),
                    confidence=target.min_confidence or 0.95,
                    landmarks=None,
                    attributes={},
                )
            )
        return results

    async def recognize(
        self,
        image_path: str,
        target_names: Optional[List[str]] = None,
    ) -> RecognitionResult:
        start_time = time.time()

        # Determine which targets to match
        check_targets = target_names or [
            t.name for t in self._targets
        ]
        matches = []
        for name in check_targets:
            target_conf = 0.95
            for t in self._targets:
                if t.name == name and t.min_confidence:
                    target_conf = t.min_confidence
            matches.append({
                "name": name,
                "confidence": target_conf,
            })

        elapsed_ms = (time.time() - start_time) * 1000

        logger.info(
            "NoOp recognize: %s -> matched=%s (%.1fms)",
            image_path,
            [m["name"] for m in matches],
            elapsed_ms,
        )

        return RecognitionResult(
            has_target=True,
            matches=matches,
            faces_detected=len(matches),
            elapsed_ms=elapsed_ms,
            raw_response={"provider": "no_op"},
        )

    async def add_reference_photos(
        self,
        target_name: str,
        photo_paths: List[str],
    ) -> bool:
        logger.info(
            "NoOp add_reference_photos: %s (%d photos)",
            target_name, len(photo_paths),
        )
        return True

    async def remove_target(
        self, target_name: str,
    ) -> bool:
        self._targets = [
            t for t in self._targets
            if t.name != target_name
        ]
        logger.info("NoOp remove_target: %s", target_name)
        return True

    async def list_targets(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": t.name,
                "reference_count": 0,
                "feature_vector_cached": False,
                "last_updated": "-",
            }
            for t in self._targets
        ]

    async def batch_recognize(
        self,
        image_paths: List[str],
        target_names: Optional[List[str]] = None,
        concurrency: int = 5,
    ) -> List[RecognitionResult]:
        import asyncio

        tasks = [
            self.recognize(path, target_names)
            for path in image_paths
        ]
        return await asyncio.gather(*tasks)

    async def cleanup(self) -> None:
        self._targets.clear()
        logger.info("NoOpRecognizer cleaned up")
