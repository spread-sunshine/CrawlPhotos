# -*- coding: utf-8 -*-
"""
Tencent Cloud Face Recognition Provider.
腾讯云人脸识别提供商实现.

APIs used:
    1. DetectFace      - Detect faces in image
    2. SearchFaces     - Match faces against target group
    3. CreateGroup     - Create face group (if not exists)
    4. CreatePerson    - Add reference photos to group

Dependencies:
    pip install tencentcloud-sdk-python

Config (from config.yaml):
    face_recognition.tencent_cloud:
        secret_id: "${TENCENT_SECRET_ID}"
        secret_key: "${TENCENT_SECRET_KEY}"
        region: "ap-guangzhou"
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
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import (
        ClientProfile,
    )
    from tencentcloud.common.profile.http_profile import (
        HttpProfile,
    )
    from tencentcloud.iai.v20200303 import iai_client, models

    TENCENT_SDK_AVAILABLE = True
except ImportError:
    iai_client = None
    models = None
    TENCENT_SDK_AVAILABLE = False


class TencentCloudProvider(IFaceRecognizer):
    """
    Tencent Cloud Face Recognition provider implementation.

    Uses Tencent Cloud IAI (Intelligent Analytics) service for
    face detection and recognition against pre-registered targets.
    """

    def __init__(
        self,
        secret_id: str = "",
        secret_key: str = "",
        region: str = "ap-guangzhou",
        group_id: str = "baby_photos_group",
        **kwargs: Any,
    ) -> None:
        if not TENCENT_SDK_AVAILABLE:
            raise ProviderInitError(
                "tencentcloud-sdk-python not installed. "
                "Run: pip install tencentcloud-sdk-python"
            )

        if not secret_id or not secret_key:
            raise ProviderInitError(
                "Tencent Cloud requires secret_id and "
                "secret_key. Set via config or environment "
                "variables TENCENT_SECRET_ID / "
                "TENCENT_SECRET_KEY."
            )

        self._secret_id = secret_id
        self._secret_key = secret_key
        self._region = region
        self._group_id = group_id
        self._targets: List[TargetConfig] = []
        self._client: Optional[Any] = None
        self._initialized = False

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.TENCENT_CLOUD

    @property
    def provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            provider_type=ProviderType.TENCENT_CLOUD,
            display_name="Tencent Cloud Face Recognition",
            version="3.0",
            is_local=False,
            max_faces_per_image=10,
            supported_image_formats=[
                "jpg", "jpeg", "png", "bmp",
            ],
            requires_api_key=True,
            has_batch_support=True,
            estimated_cost_per_call=0.001,
            description="Tencent Cloud IAI face recognition "
                       "(1000 free calls/month)",
        )

    # ==================== Initialization ====================

    async def initialize(
        self, targets: List[TargetConfig],
    ) -> bool:
        """Initialize client and register target persons."""
        try:
            cred = credential.Credential(
                self._secret_id, self._secret_key,
            )
            httpProfile = HttpProfile()
            httpProfile.endpoint = "iai.tencentcloudapi.com"
            clientProfile = ClientProfile()
            clientProfile.httpProfile = httpProfile
            self._client = iai_client.IaiClient(
                cred, self._region, clientProfile,
            )

            # Ensure face group exists
            await self._ensure_group_exists()

            # Register targets with reference photos
            self._targets = [t for t in targets if t.enabled]
            for target in self._targets:
                await self._register_target(target)

            self._initialized = True
            logger.info(
                "TencentCloudProvider initialized: "
                "group=%s, targets=%d",
                self._group_id,
                len(self._targets),
            )
            return True

        except Exception as exc:
            raise ProviderInitError(
                f"Tencent Cloud init failed: {exc}"
            ) from exc

    async def _ensure_group_exists(self) -> None:
        """Create face group if it doesn't exist."""
        req = models.CreateGroupRequest()
        req.from_json_string(
            f'{{"GroupId":"{self._group_id}"}}'
        )
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None, lambda: self._client.CreateGroup(req),
            )
            logger.info("Created/verified group: %s", self._group_id)
        except Exception as e:
            err_msg = str(e).lower()
            if "already" in err_msg or "existed" in err_msg:
                logger.debug("Group already exists: %s", self._group_id)
            else:
                logger.warning(
                    "Group creation warning: %s", e,
                )

    async def _register_target(self, target: TargetConfig) -> None:
        """Register a target person with reference photos."""
        if not target.reference_photo_paths:
            logger.warning(
                "No reference photos for target: %s",
                target.name,
            )
            return

        for photo_path in target.reference_photo_paths:
            if not photo_path.exists():
                logger.warning(
                    "Reference photo not found: %s",
                    photo_path,
                )
                continue

            img_base64 = self._encode_image(photo_path)
            if not img_base64:
                continue

            req = models.CreatePersonRequest()
            req.from_json_string(
                f'{{'
                f'"GroupId":"{self._group_id}",'
                f'"PersonName":"{target.name}",'
                f'"Image":"{img_base64}"'
                f'}}'
            )

            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(
                    None,
                    lambda: self._client.CreatePerson(req),
                )
                logger.info(
                    "Registered reference photo for "
                    "target=%s (%s)",
                    target.name,
                    photo_path.name,
                )
            except Exception as e:
                err_str = str(e)
                if "already" in err_str.lower():
                    logger.debug(
                        "Person already registered: %s",
                        target.name,
                    )
                else:
                    logger.warning(
                        "Failed to register ref photo for "
                        "%s: %s",
                        target.name,
                        e,
                    )

    # ==================== Health Check ====================

    async def health_check(self) -> Dict[str, Any]:
        """Check Tencent Cloud API availability."""
        start = time.time()
        try:
            req = models.GetGroupListRequest()
            req.from_json_string("{}")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: self._client.GetGroupList(req),
            )
            latency = (time.time() - start) * 1000
            return {
                "healthy": True,
                "latency_ms": latency,
                "quota_remaining": -1,
                "message": "Tencent Cloud API reachable",
            }
        except Exception as exc:
            return {
                "healthy": False,
                "latency_ms": (time.time() - start) * 1000,
                "quota_remaining": 0,
                "message": str(exc),
            }

    # ==================== Core Recognition ====================

    async def detect_faces(
        self,
        image_path: str,
        max_faces: int = 10,
    ) -> List[FaceDetection]:
        """Detect all faces in an image."""
        img_base64 = self._encode_image(image_path)
        if not img_base64:
            return []

        req = models.DetectFaceRequest()
        req.from_json_string(
            f'{{"Image":"{img_base64}",'
            f'"MaxFaceNum":{max_faces},'
            f'"NeedFaceAttributes":0}}'
        )

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, lambda: self._client.DetectFace(req),
        )

        results: List[FaceDetection] = []
        if resp and hasattr(resp, "FaceInfos"):
            for info in resp.FaceInfos or []:
                bbox = info.FaceRect or type(
                    "obj", (), {"X": 0, "Y": 0, "Width": 0, "Height": 0},
                )()
                results.append(
                    FaceDetection(
                        face_id=getattr(info, "FaceId", ""),
                        bounding_box=BoundingBox(
                            x=bbox.X,
                            y=bbox.Y,
                            width=bbox.Width,
                            height=bbox.Height,
                        ),
                        confidence=getattr(
                            info, "FaceConfidence", 0,
                        ) / 100.0,
                        face_image_path=None,
                    ),
                )
        return results

    async def recognize(
        self,
        image_path: str,
        target_names: Optional[List[str]] = None,
    ) -> RecognitionResult:
        """
        Detect faces and search for target matches.

        Two-step process:
        1. DetectFace - find all faces
        2. SearchFaces - match each face against group
        """
        start_time = time.time()

        img_base64 = self._encode_image(image_path)
        if not img_base64:
            return RecognitionResult(
                source_photo_path=image_path,
                total_faces_detected=0,
                contains_target=False,
                best_confidence=0.0,
                provider_name="tencent_cloud",
                raw_response={"error": "Image encoding failed"},
            )

        matches: List[Dict[str, Any]] = []

        try:
            # Step 1: Detect faces
            detect_req = models.DetectFaceRequest()
            detect_req.from_json_string(
                f'{{"Image":"{img_base64}",'
                f'"MaxFaceNum":10,'
                f'"NeedFaceAttributes":0}}'
            )

            loop = asyncio.get_event_loop()
            detect_resp = await loop.run_in_executor(
                None,
                lambda: self._client.DetectFace(detect_req),
            )

            if not detect_resp or not getattr(
                detect_resp, "FaceInfos", None,
            ):
                elapsed = (time.time() - start_time) * 1000
                return RecognitionResult(
                    source_photo_path=image_path,
                    total_faces_detected=0,
                    contains_target=False,
                    best_confidence=0.0,
                    target_matches=[],
                    all_face_detections=[],
                    provider_name="tencent_cloud",
                    processing_time_ms=elapsed,
                    raw_response={"face_count": 0},
                )

            face_count = len(detect_resp.FaceInfos)
            detections: List[FaceDetection] = []

            # Step 2: Search each face against group
            check_targets = target_names or [
                t.name for t in self._targets
            ]

            for face_info in detect_resp.FaceInfos:
                face_rect = face_info.FaceRect
                det_conf = getattr(
                    face_info, "FaceConfidence", 80,
                ) / 100.0

                detection = FaceDetection(
                    face_id=str(getattr(
                        face_info, "FaceId", "",
                    )),
                    bounding_box=BoundingBox(
                        x=face_rect.X,
                        y=face_rect.Y,
                        width=face_rect.Width,
                        height=face_rect.Height,
                    ),
                    confidence=det_conf,
                    face_image_path=None,
                )
                detections.append(detection)

                # SearchFaces for this detected face
                search_req = models.SearchFacesRequest()
                # Use FaceRect for searching
                search_req.from_json_string(
                    f'{{'
                    f'"GroupId":"{self._group_id}",'
                    f'"Image":"{img_base64}",'
                    f'"MinFaceSize":40,'
                    f'"MaxFaceNum":5,'
                    f'"MatchThreshold":60,'
                    f'"QualityControl":1'
                    f'}}'
                )

                search_resp = await loop.run_in_executor(
                    None,
                    lambda: self._client.SearchFaces(search_req),
                )

                if search_resp and getattr(
                    search_resp, "Results", None,
                ):
                    for result in search_resp.Results:
                        candidate = result.Candidates[0] \
                            if result.Candidates else None
                        if candidate is None:
                            continue

                        match_name = getattr(
                            candidate, "PersonName", "",
                        )
                        match_score = getattr(
                            candidate, "Score", 0,
                        ) / 100.0

                        # Check if this matches any of our targets
                        if match_name in check_targets:
                            target_min_conf = 0.8
                            for t in self._targets:
                                if t.name == match_name:
                                    target_min_conf = (
                                        t.min_confidence
                                    )
                                    break

                            if match_score >= target_min_conf:
                                matches.append({
                                    "name": match_name,
                                    "confidence": match_score,
                                })

            elapsed = (time.time() - start_time) * 1000
            has_target = len(matches) > 0
            best_conf = (
                max(m["confidence"] for m in matches)
                if matches else 0.0
            )

            return RecognitionResult(
                source_photo_path=image_path,
                total_faces_detected=face_count,
                target_matches=matches,
                contains_target=has_target,
                best_confidence=best_conf,
                all_face_detections=detections,
                provider_name="tencent_cloud",
                processing_time_ms=elapsed,
                raw_response={
                    "face_count": face_count,
                    "match_count": len(matches),
                },
            )

        except Exception as exc:
            err_str = str(exc)
            if "quota" in err_str.lower() or "limit" in err_str.lower():
                raise QuotaExhaustedError(
                    message=f"Tencent Cloud quota exceeded: {exc}",
                    reset_time="Next month",
                )
            raise ProviderApiError(
                f"Tencent Cloud API error: {exc}"
            ) from exc

    async def add_reference_photos(
        self,
        target_name: str,
        photo_paths: List[str],
    ) -> bool:
        """Add additional reference photos for a target person."""
        target = next(
            (t for t in self._targets if t.name == target_name),
            None,
        )
        if target is None:
            raise TargetNotFoundError(target_name)

        for path_str in photo_paths:
            path = Path(path_str)
            if not path.exists():
                continue

            img_base64 = self._encode_image(path)
            if not img_base64:
                continue

            req = models.CreatePersonRequest()
            req.from_json_string(
                f'{{'
                f'"GroupId":"{self._group_id}",'
                f'"PersonName":"{target_name}",'
                f'"Image":"{img_base64}"'
                f'}}'
            )

            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(
                    None,
                    lambda: self._client.CreatePerson(req),
                )
                logger.info(
                    "Added reference photo for %s: %s",
                    target_name, path.name,
                )
            except Exception as e:
                logger.error(
                    "Failed to add reference for %s: %s",
                    target_name, e,
                )
                return False

        return True

    async def remove_target(
        self, target_name: str,
    ) -> bool:
        """Remove a target person from the face group."""
        req = models.DeletePersonRequest()
        req.from_json_string(
            f'{{'
            f'"GroupId":"{self._group_id}",'
            f'"PersonName":"{target_name}"'
            f'}}'
        )

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: self._client.DeletePerson(req),
            )
            self._targets = [
                t for t in self._targets
                if t.name != target_name
            ]
            logger.info("Removed target: %s", target_name)
            return True
        except Exception as e:
            logger.error(
                "Failed to remove target %s: %s",
                target_name, e,
            )
            return False

    async def list_targets(self) -> List[Dict[str, Any]]:
        """List all registered target persons."""
        req = models.GetPersonListRequest()
        req.from_json_string(
            f'{{"GroupId":"{self._group_id}"}}'
        )

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                lambda: self._client.GetPersonList(req),
            )
            result = []
            if resp and getattr(resp, "PersonInfos", None):
                for p in resp.PersonInfos:
                    result.append({
                        "name": getattr(p, "PersonName", ""),
                        "reference_count": getattr(
                            p, "FaceNum", 0,
                        ),
                        "feature_vector_cached": True,
                        "last_updated": getattr(
                            p, "CreateTime", "-",
                        ),
                    })
            return result
        except Exception as e:
            logger.error("List targets failed: %s", e)
            return [
                {
                    "name": t.name,
                    "reference_count": len(
                        t.reference_photo_paths
                    ),
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
        """
        Batch recognition using concurrent tasks.

        Tencent Cloud doesn't have a true batch API for
        SearchFaces, so we use controlled concurrency.
        """
        sem = asyncio.Semaphore(concurrency)

        async def _recognize_one(path: str) -> RecognitionResult:
            async with sem:
                return await self.recognize(path, target_names)

        tasks = [_recognize_one(p) for p in image_paths]
        return await asyncio.gather(*tasks)

    async def cleanup(self) -> None:
        """Release resources."""
        self._client = None
        self._initialized = False
        self._targets.clear()
        logger.info("TencentCloudProvider cleaned up")

    # ==================== Utilities ====================

    @staticmethod
    def _encode_image(file_path: Any) -> Optional[str]:
        """
        Encode an image file to base64 string.

        Args:
            file_path: Path-like object pointing to image.

        Returns:
            Base64-encoded string or None on failure.
        """
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning("Image not found: %s", path)
                return None

            # Limit image size to 5MB (Tencent Cloud limit)
            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb > 5:
                logger.warning(
                    "Image too large (%.1fMB): %s",
                    size_mb, path,
                )
                return None

            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode("utf-8")
            return data

        except Exception as e:
            logger.error(
                "Failed to encode image %s: %s",
                file_path, e,
            )
            return None
