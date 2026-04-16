# -*- coding: utf-8 -*-
"""
Baidu AI Face Recognition Provider.
百度AI人脸识别提供商实现.

APIs used:
    1. Detect     - Detect faces in image
    2. Search     - Match faces against face group (FaceSet)
    3. UserAdd    - Add reference photos to FaceSet

Dependencies:
    pip install baidu-aip

Config (from config.yaml):
    face_recognition.baidu:
        app_id: "${BAIDU_APP_ID}"
        api_key: "${BAIDU_API_KEY}"
        secret_key: "${BAIDU_SECRET_KEY}"
        group_id: "baby_photos_group"
"""

import asyncio
import base64
import logging
import time
from typing import Any, Dict, List, Optional

from app.face_recognition.exceptions import (
    ImageInvalidError,
    ProviderApiError,
    ProviderInitError,
    QuotaExhaustedError,
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
    from aip import AipFace

    BAIDU_SDK_AVAILABLE = True
except ImportError:
    AipFace = None  # type: ignore[assignment,misc]
    BAIDU_SDK_AVAILABLE = False


class BaiduProvider(IFaceRecognizer):
    """
    Baidu AI Face Recognition provider implementation.

    Uses Baidu Cloud AI's REST API for face detection and
    recognition. Free within QPS limits for certified users.
    """

    def __init__(
        self,
        app_id: str = "",
        api_key: str = "",
        secret_key: str = "",
        group_id: str = "baby_photos_group",
        **kwargs: Any,
    ) -> None:
        if not BAIDU_SDK_AVAILABLE:
            raise ProviderInitError(
                "baidu-aip not installed. "
                "Run: pip install baidu-aip"
            )

        if not api_key or not secret_key or not app_id:
            raise ProviderInitError(
                "Baidu AI requires app_id, api_key, and "
                "secret_key. Set via config or environment "
                "variables."
            )

        self._client = AipFace(app_id, api_key, secret_key)
        self._group_id = group_id
        self._targets: List[TargetConfig] = []
        self._initialized = False

        # Set options
        self._client.setConnectionTimeoutInMillis(5000)
        self._client.setSocketTimeoutInMillis(10000)

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.BAIDU

    @property
    def provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            provider_type=ProviderType.BAIDU,
            display_name="Baidu AI Face Recognition",
            version="3.0",
            is_local=False,
            max_faces_per_image=10,
            supported_image_formats=[
                "jpg", "jpeg", "png", "bmp",
            ],
            requires_api_key=True,
            has_batch_support=False,
            estimated_cost_per_call=0.0007,
            description="Baidu AI free-tier face "
                       "(QPS-limited)",
        )

    async def initialize(
        self, targets: List[TargetConfig],
    ) -> bool:
        """Initialize client and register target persons."""
        try:
            self._targets = [t for t in targets if t.enabled]
            for target in self._targets:
                await self._register_target(target)

            self._initialized = True
            logger.info(
                "BaiduProvider initialized: "
                "group=%s, targets=%d",
                self._group_id,
                len(self._targets),
            )
            return True

        except Exception as exc:
            raise ProviderInitError(
                f"Baidu AI init failed: {exc}"
            ) from exc

    async def _register_target(self, target: TargetConfig) -> None:
        """Register a target with reference photos."""
        if not target.reference_photo_paths:
            logger.warning(
                "No reference photos for target: %s",
                target.name,
            )
            return

        loop = asyncio.get_event_loop()

        for photo_path in target.reference_photo_paths:
            if not photo_path.exists():
                continue

            img_data = self._read_image(photo_path)
            if img_data is None:
                continue

            try:
                await loop.run_in_executor(
                    None,
                    lambda: self._client.addUser(
                        img_data, "BASE64",
                        self._group_id, target.name,
                        {"user_info": target.name},
                    ),
                )
                logger.info(
                    "Registered ref photo for %s: %s",
                    target.name, photo_path.name,
                )
            except Exception as e:
                err_str = str(e).lower()
                if "already" in err_str or "existed" in err_str:
                    pass
                else:
                    logger.warning(
                        "Register failed %s: %s",
                        target.name, e,
                    )

    async def health_check(self) -> Dict[str, Any]:
        """Check Baidu API availability."""
        start = time.time()
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._client.getUserList(
                    self._group_id, 1, 1,
                ),
            )
            return {
                "healthy": True,
                "latency_ms": (time.time() - start) * 1000,
                "quota_remaining": -1,
                "message": "Baidu API reachable",
            }
        except Exception as exc:
            return {
                "healthy": False,
                "latency_ms": (time.time() - start) * 1000,
                "quota_remaining": 0,
                "message": str(exc),
            }

    async def detect_faces(
        self,
        image_path: str,
        max_faces: int = 10,
    ) -> List[FaceDetection]:
        """Detect faces in an image."""
        img_data = self._read_image(image_path)
        if img_data is None:
            return []

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._client.detect(
                img_data, "BASE64",
                options={"max_face_num": max_faces},
            ),
        )

        results: List[FaceDetection] = []
        faces = resp.get("result", {}).get("face_list", [])
        for f in faces:
            location = f.get("location", {})
            results.append(
                FaceDetection(
                    face_id=f.get("face_token", ""),
                    bounding_box=BoundingBox(
                        x=int(location.get("left", 0)),
                        y=int(location.get("top", 0)),
                        width=int(location.get("width", 0)),
                        height=int(location.get("height", 0)),
                    ),
                    confidence=f.get("probability", 0) / 100.0,
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
        Detect + Search faces against registered targets.

        Baidu uses detect + search (two-step).
        """
        start_time = time.time()
        img_data = self._read_image(image_path)

        if img_data is None:
            return RecognitionResult(
                source_photo_path=image_path,
                total_faces_detected=0,
                contains_target=False,
                best_confidence=0.0,
                provider_name="baidu",
                raw_response={"error": "Image read failed"},
            )

        matches: List[Dict[str, Any]] = []
        detections: List[FaceDetection] = []
        check_targets = target_names or [
            t.name for t in self._targets
        ]

        try:
            loop = asyncio.get_event_loop()

            # Step 1: Detect faces
            detect_resp = await loop.run_in_executor(
                None,
                lambda: self._client.detect(
                    img_data, "BASE64",
                    options={
                        "max_face_num": 10,
                        "face_field": "",
                    },
                ),
            )

            faces = (
                detect_resp.get("result", {})
                .get("face_list", [])
            )

            if not faces:
                elapsed = (time.time() - start_time) * 1000
                return RecognitionResult(
                    source_photo_path=image_path,
                    total_faces_detected=0,
                    contains_target=False,
                    best_confidence=0.0,
                    all_face_detections=[],
                    provider_name="baidu",
                    processing_time_ms=elapsed,
                    raw_response={"face_count": 0},
                )

            # Step 2: Search each face
            for f in faces:
                location = f.get("location", {})
                det_conf = f.get("probability", 80) / 100.0
                face_token = f.get("face_token", "")

                detections.append(
                    FaceDetection(
                        face_id=face_token,
                        bounding_box=BoundingBox(
                            x=int(location.get("left", 0)),
                            y=int(location.get("top", 0)),
                            width=int(location.get("width", 0)),
                            height=int(location.get("height", 0)),
                        ),
                        confidence=det_conf,
                    )
                )

                search_resp = await loop.run_in_executor(
                    None,
                    lambda ft=face_token: self._client.search(
                        img_data, "BASE64",
                        self._group_id,
                        options={"max_user_num": 3},
                    ),
                )

                users = (
                    search_resp.get("result", {})
                    .get("user_list", [])
                )
                for u in users:
                    user_name = u.get("user_id", "")
                    score = u.get("score", 0) / 100.0

                    if user_name in check_targets:
                        t_min = 0.8
                        for t in self._targets:
                            if t.name == user_name:
                                t_min = t.min_confidence
                                break

                        if score >= t_min:
                            matches.append({
                                "name": user_name,
                                "confidence": score,
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
                provider_name="baidu",
                processing_time_ms=elapsed,
                raw_response={
                    "face_count": len(detections),
                    "match_count": len(matches),
                },
            )

        except Exception as exc:
            err_str = str(exc).lower()
            if any(kw in err_str for kw in ("limit", "qps", "quota")):
                raise QuotaExhaustedError(
                    message=f"Baidu quota limit: {exc}",
                    reset_time="Next day/minute",
                )
            raise ProviderApiError(
                f"Baidu API error: {exc}"
            ) from exc

    async def add_reference_photos(
        self,
        target_name: str,
        photo_paths: List[str],
    ) -> bool:
        """Add reference photos for a target person."""
        target = next(
            (t for t in self._targets if t.name == target_name),
            None,
        )
        if target is None:
            raise TargetNotFoundError(target_name)

        loop = asyncio.get_event_loop()
        for path_str in photo_paths:
            path = Path(path_str)
            if not path.exists():
                continue

            img_data = self._read_image(path)
            if img_data is None:
                continue

            try:
                await loop.run_in_executor(
                    None,
                    lambda: self._client.addUser(
                        img_data, "BASE64",
                        self._group_id, target_name,
                        {"user_info": target_name},
                    ),
                )
                logger.info("Added ref photo for %s", target_name)
            except Exception as e:
                logger.error(
                    "Add ref failed for %s: %s",
                    target_name, e,
                )
                return False
        return True

    async def remove_target(
        self, target_name: str,
    ) -> bool:
        """Remove a target from the FaceSet."""
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: self._client.deleteUser(
                    self._group_id, target_name,
                ),
            )
            self._targets = [
                t for t in self._targets
                if t.name != target_name
            ]
            logger.info("Removed target: %s", target_name)
            return True
        except Exception as e:
            logger.error("Remove target failed: %s", e)
            return False

    async def list_targets(self) -> List[Dict[str, Any]]:
        """List all registered targets."""
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                lambda: self._client.getUserList(
                    self._group_id, 1, 100,
                ),
            )
            result = []
            users = (
                resp.get("result", {}).get("user_id_list", [])
            )
            for u in users:
                result.append({
                    "name": u,
                    "reference_count": 0,
                    "feature_vector_cached": True,
                    "last_updated": "-",
                })
            return result
        except Exception as e:
            logger.error("List targets failed: %s", e)
            return [
                {"name": t.name,
                 "reference_count": len(t.reference_photo_paths),
                 "feature_vector_cached": False,
                 "last_updated": "-"}
                for t in self._targets
            ]

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
        self._client = None
        self._initialized = False
        self._targets.clear()
        logger.info("BaiduProvider cleaned up")

    # ==================== Utilities ====================

    @staticmethod
    def _read_image(file_path: Any) -> Optional[bytes]:
        """Read image file as bytes."""
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning("Image not found: %s", path)
                return None

            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb > 5:
                logger.warning("Image too large: %.1fMB", size_mb)
                return None

            with open(path, "rb") as f:
                return f.read()

        except Exception as e:
            logger.error("Read image failed: %s", e)
            return None
