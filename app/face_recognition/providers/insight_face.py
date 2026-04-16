# -*- coding: utf-8 -*-
"""
InsightFace Local Face Recognition Provider.
InsightFace本地人脸识别提供商(完全离线).

Uses ONNX models for local face detection and recognition.
No network required, completely free.

Dependencies:
    pip install insightface onnxruntime-gpu  # GPU
    pip install insightface onnxruntime       # CPU

Config (from config.yaml):
    face_recognition.insight_face_local:
        model_name: "buffalo_l"
        device: "cpu"
        model_cache_dir: "data/models"
        confidence_threshold: 0.80
        use_faiss: false
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.face_recognition.exceptions import (
    ImageInvalidError,
    ProviderApiError,
    ProviderInitError,
    TargetNotFoundError,
)
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

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    np = None  # type: ignore[assignment,misc]
    CV2_AVAILABLE = False

try:
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    FaceAnalysis = None  # type: ignore[assignment,misc]
    INSIGHTFACE_AVAILABLE = False


class InsightFaceLocalProvider(IFaceRecognizer):
    """
    InsightFace local face recognition provider.

    Runs entirely on-device with ONNX models:
    - buffalo_l / buffalo_s for detection + recognition
    - Cosine similarity for matching against reference embeddings
    """

    def __init__(
        self,
        model_name: str = "buffalo_l",
        device: str = "cpu",
        model_cache_dir: str = "data/models",
        confidence_threshold: float = 0.80,
        use_faiss: bool = False,
        **kwargs: Any,
    ) -> None:
        if not INSIGHTFACE_AVAILABLE or not CV2_AVAILABLE:
            missing = []
            if not INSIGHTFACE_AVAILABLE:
                missing.append("insightface")
            if not CV2_AVAILABLE:
                missing.append("opencv-python")
            raise ProviderInitError(
                f"Missing dependencies: {', '.join(missing)}. "
                "Run: pip install insightface opencv-python "
                "onnxruntime"
            )

        self._model_name = model_name
        self._device = device
        self._cache_dir = Path(model_cache_dir)
        self._confidence_threshold = confidence_threshold
        self._use_faiss = use_faiss

        self._app: Optional[Any] = None
        self._targets: List[TargetConfig] = []
        # Target name -> list of embedding vectors
        self._target_embeddings: Dict[str, List[Any]] = {}
        self._initialized = False

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.INSIGHT_FACE_LOCAL

    @property
    def provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            provider_type=ProviderType.INSIGHT_FACE_LOCAL,
            display_name="InsightFace Local Recognition",
            version="1.0",
            is_local=True,
            max_faces_per_image=20,
            supported_image_formats=[
                "jpg", "jpeg", "png", "bmp", "webp",
            ],
            requires_api_key=False,
            has_batch_support=True,
            estimated_cost_per_call=0.0,
            description="Fully offline, no network required",
        )

    async def initialize(
        self, targets: List[TargetConfig],
    ) -> bool:
        """Load ONNX model and extract reference embeddings."""
        try:
            loop = asyncio.get_event_loop()
            self._app = await loop.run_in_executor(
                None, self._load_model,
            )

            self._targets = [t for t in targets if t.enabled]

            # Extract reference embeddings for each target
            for target in self._targets:
                embeddings = await self._extract_target_embeddings(
                    target
                )
                self._target_embeddings[target.name] = embeddings

            self._initialized = True
            logger.info(
                "InsightFaceLocalProvider initialized: "
                "model=%s, device=%s, targets=%d",
                self._model_name,
                self._device,
                len(self._targets),
            )
            return True

        except Exception as exc:
            raise ProviderInitError(
                f"InsightFace init failed: {exc}"
            ) from exc

    def _load_model(self) -> Any:
        """Load the FaceAnalysis model."""
        cache_dir_str = str(self._cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        app = FaceAnalysis(
            name=self._model_name,
            providers=["CPUExecutionProvider"],
            root=str(self._cache_dir.parent),
        )
        app.prepare(ctx_id=0, det_size=(640, 640))
        return app

    async def _extract_target_embeddings(
        self, target: TargetConfig,
    ) -> List[Any]:
        """Extract face embedding vectors from reference photos."""
        if not target.reference_photo_paths:
            logger.warning(
                "No reference photos for %s", target.name,
            )
            return []

        loop = asyncio.get_event_loop()
        all_embeddings: List[Any] = []

        for photo_path in target.reference_photo_paths:
            if not photo_path.exists():
                continue

            img = await loop.run_in_executor(
                None, lambda p=photo_path: cv2.imread(str(p)),
            )
            if img is None:
                continue

            faces = await loop.run_in_executor(
                None, lambda i=img: self._app.get(i),
            )
            if faces and len(faces) > 0:
                emb = faces[0].embedding
                if emb is not None:
                    all_embeddings.append(emb)
                    logger.debug(
                        "Extracted embedding from ref photo "
                        "%s (%s)",
                        photo_path.name,
                        target.name,
                    )

        logger.info(
            "Target %s: %d reference embeddings extracted",
            target.name,
            len(all_embeddings),
        )
        return all_embeddings

    async def health_check(self) -> Dict[str, Any]:
        """Check model loaded status (always healthy if loaded)."""
        start = time.time()
        return {
            "healthy": self._app is not None,
            "latency_ms": (time.time() - start) * 1000,
            "quota_remaining": -1,
            "message": (
                "Model loaded" if self._app else "Not initialized"
            ),
        }

    async def detect_faces(
        self,
        image_path: str,
        max_faces: int = 20,
    ) -> List[FaceDetection]:
        """Detect faces in image using InsightFace."""
        img = self._load_image(image_path)
        if img is None:
            return []

        loop = asyncio.get_event_loop()
        faces = await loop.run_in_executor(
            None, lambda i=img: self._app.get(i),
        )

        results: List[FaceDetection] = []
        for f in faces[:max_faces]:
            bbox = f.bbox
            results.append(
                FaceDetection(
                    face_id=f"insight_{id(f)}",
                    bounding_box=BoundingBox(
                        x=int(bbox[0]),
                        y=int(bbox[1]),
                        width=int(bbox[2] - bbox[0]),
                        height=int(bbox[3] - bbox[1]),
                    ),
                    confidence=float(f.det_score),
                    face_image_path=None,
                )
            )
        return results

    async def recognize(
        self,
        image_path: str,
        target_names: Optional[List[str]] = None,
    ) -> RecognitionResult:
        """
        Detect faces and match embeddings against target references.
        """
        start_time = time.time()

        img = self._load_image(image_path)
        if img is None:
            return RecognitionResult(
                source_photo_path=image_path,
                total_faces_detected=0,
                contains_target=False,
                best_confidence=0.0,
                provider_name="insight_face_local",
                raw_response={"error": "Image load failed"},
            )

        matches: List[Dict[str, Any]] = []
        detections: List[FaceDetection] = []

        try:
            loop = asyncio.get_event_loop()
            faces = await loop.run_in_executor(
                None, lambda i=img: self._app.get(i),
            )

            check_targets = target_names or [
                t.name for t in self._targets
            ]

            for f in faces:
                bbox = f.bbox
                det_conf = float(f.det_score)
                embedding = f.embedding

                detections.append(
                    FaceDetection(
                        face_id=f"insight_{id(f)}",
                        bounding_box=BoundingBox(
                            x=int(bbox[0]),
                            y=int(bbox[1]),
                            width=int(bbox[2] - bbox[0]),
                            height=int(bbox[3] - bbox[1]),
                        ),
                        confidence=det_conf,
                    )
                )

                # Compare against each target's embeddings
                if embedding is None:
                    continue

                best_match_name = ""
                best_match_score = 0.0

                for target_name in check_targets:
                    refs = self._target_embeddings.get(
                        target_name, [],
                    )
                    if not refs:
                        continue

                    # Cosine similarity
                    max_sim = 0.0
                    for ref_emb in refs:
                        sim = self._cosine_similarity(
                            embedding, ref_emb
                        )
                        if sim > max_sim:
                            max_sim = sim

                    t_min = 0.8
                    for t in self._targets:
                        if t.name == target_name:
                            t_min = t.min_confidence
                            break

                    if max_sim >= t_min and max_sim > best_match_score:
                        best_match_name = target_name
                        best_match_score = max_sim

                if best_match_name:
                    matches.append({
                        "name": best_match_name,
                        "confidence": best_match_score,
                    })

            elapsed = (time.time() - start_time) * 1000
            has_target = len(matches) > 0
            best_conf = (
                max(m["confidence"] for m in matches)
                if matches else 0.0
            )

            return RecognitionResult(
                source_photo_path=image_path,
                total_faces_detected=len(detections),
                target_matches=matches,
                contains_target=has_target,
                best_confidence=best_conf,
                all_face_detections=detections,
                provider_name="insight_face_local",
                processing_time_ms=elapsed,
                raw_response={
                    "face_count": len(detections),
                    "match_count": len(matches),
                },
            )

        except Exception as exc:
            raise ProviderApiError(
                f"InsightFace error: {exc}"
            ) from exc

    async def add_reference_photos(
        self,
        target_name: str,
        photo_paths: List[str],
    ) -> bool:
        """Add new reference photos and update embeddings."""
        target = next(
            (t for t in self._targets if t.name == target_name),
            None,
        )
        if target is None:
            raise TargetNotFoundError(target_name)

        new_embs = []
        for path_str in photo_paths:
            path = Path(path_str)
            if not path.exists():
                continue

            img = cv2.imread(str(path))
            if img is None:
                continue

            loop = asyncio.get_event_loop()
            faces = await loop.run_in_executor(
                None, lambda i=img: self._app.get(i),
            )
            if faces and len(faces) > 0 and faces[0].embedding is not None:
                new_embs.append(faces[0].embedding)

        existing = self._target_embeddings.setdefault(
            target_name, [],
        )
        existing.extend(new_embs)
        target.reference_photo_paths.extend(
            Path(p) for p in photo_paths
        )
        logger.info(
            "Added %d reference embeddings for %s",
            len(new_embs), target_name,
        )
        return True

    async def remove_target(
        self, target_name: str,
    ) -> bool:
        """Remove a target person and their embeddings."""
        self._target_embeddings.pop(target_name, None)
        self._targets = [
            t for t in self._targets
            if t.name != target_name
        ]
        logger.info("Removed target: %s", target_name)
        return True

    async def list_targets(self) -> List[Dict[str, Any]]:
        """List registered targets."""
        result = []
        for t in self._targets:
            embs = self._target_embeddings.get(t.name, [])
            result.append({
                "name": t.name,
                "reference_count": len(embs),
                "feature_vector_cached": len(embs) > 0,
                "last_updated": "-",
            })
        return result

    async def batch_recognize(
        self,
        image_paths: List[str],
        target_names: Optional[List[str]] = None,
        concurrency: int = 5,
    ) -> List[RecognitionResult]:
        sem = asyncio.Semaphore(concurrency)

        async def _one(p: str) -> RecognitionResult:
            async with sem:
                return await self.recognize(p, target_names)

        tasks = [_one(p) for p in image_paths]
        return await asyncio.gather(*tasks)

    async def cleanup(self) -> None:
        """Release resources."""
        self._app = None
        self._target_embeddings.clear()
        self._initialized = False
        self._targets.clear()
        logger.info("InsightFaceLocalProvider cleaned up")

    # ==================== Utilities ====================

    @staticmethod
    def _load_image(file_path: str):
        """Load image using OpenCV."""
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning("Image not found: %s", path)
                return None
            return cv2.imread(str(path))
        except Exception as e:
            logger.error("Failed to load image: %s", e)
            return None

    @staticmethod
    def _cosine_similarity(a: Any, b: Any) -> float:
        """Compute cosine similarity between two vectors."""
        dot_product = float(np.dot(a, b))
        norm_a = float(np.linalg.norm(a))
        norm_b = float(np.linalg.norm(b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)
