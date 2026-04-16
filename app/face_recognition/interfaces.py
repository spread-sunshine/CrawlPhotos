# -*- coding: utf-8 -*-
"""
Abstract interface for face recognition providers.
人脸识别引擎 - 统一抽象接口.

All providers must implement this interface so the business
layer is fully decoupled from implementation details.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.face_recognition.models import (
    BoundingBox,
    FaceDetection,
    ProviderInfo,
    ProviderType,
    RecognitionResult,
    TargetConfig,
)


class IFaceRecognizer(ABC):
    """
    Abstract base class for face recognition providers.

    All concrete providers must inherit from this class and
    implement every abstractmethod.

    Design principles:
    - Single Responsibility: only handles face-related ops.
    - Open/Closed: new provider = new subclass, no existing changes.
    - Dependency Inversion: upper layers depend on this abstraction.
    - Interface Segregation: methods are focused and minimal.
    """

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        """Return the provider type identifier."""
        pass

    @property
    @abstractmethod
    def provider_info(self) -> ProviderInfo:
        """Return provider capability description."""
        pass

    @abstractmethod
    async def initialize(
        self, targets: List[TargetConfig],
    ) -> bool:
        """
        Initialize the recognition engine.

        Args:
            targets: Target person configs for pre-loading features.

        Returns:
            Whether initialization succeeded.

        Raises:
            ProviderInitError: On initialization failure.
        """
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Check service availability.

        Returns:
            {"healthy": bool, "latency_ms": float,
             "quota_remaining": Optional[int], "message": str}
        """
        pass

    @abstractmethod
    async def detect_faces(
        self,
        image_path: str,
        max_faces: int = 10,
    ) -> List[FaceDetection]:
        """
        Detect faces in an image (no recognition/matching).

        Args:
            image_path: Local file path or URL.
            max_faces: Maximum number of faces to detect.

        Returns:
            Detected faces sorted by confidence descending.

        Raises:
            ImageInvalidError: Image too large or invalid format.
            ProviderApiError: API call failed.
        """
        pass

    @abstractmethod
    async def recognize(
        self,
        image_path: str,
        target_names: Optional[List[str]] = None,
    ) -> RecognitionResult:
        """
        Core method: detect if image contains target person(s).

        Internally executes: detect_faces -> extract_features
        -> search_targets.

        Args:
            image_path: Path to image to recognize.
            target_names: Specific targets to check;
                          None checks all registered targets.

        Returns:
            Full recognition result.

        Raises:
            ProviderApiError: API call failed.
            ImageInvalidError: Unsupported or corrupt image.
        """
        pass

    @abstractmethod
    async def add_reference_photos(
        self,
        target_name: str,
        photo_paths: List[str],
    ) -> bool:
        """
        Add/update reference photos for a target person.

        Typical use-cases:
        - Initial import of baby reference photos.
        - Periodic updates as child's appearance changes.
        - Adding supplementary photos after missed detections.

        Args:
            target_name: Must match TargetConfig.name.
            photo_paths: File paths of reference images.

        Returns:
            Success status.

        Raises:
            TargetNotFoundError: Person not registered.
            ImageInvalidError: Photo does not meet requirements.
        """
        pass

    @abstractmethod
    async def remove_target(
        self, target_name: str,
    ) -> bool:
        """
        Remove a target person and all their feature data.

        Args:
            target_name: Name of the target to remove.

        Returns:
            Success status.
        """
        pass

    @abstractmethod
    async def list_targets(self) -> List[Dict[str, Any]]:
        """
        List all currently registered targets and their status.

        Returns:
            [{"name": "...", "reference_count": N,
              "feature_vector_cached": bool,
              "last_updated": "..."}, ...]
        """
        pass

    @abstractmethod
    async def batch_recognize(
        self,
        image_paths: List[str],
        target_names: Optional[List[str]] = None,
        concurrency: int = 5,
    ) -> List[RecognitionResult]:
        """
        Batch recognition (optional optimization).

        For providers that support batch APIs (e.g., Tencent Cloud
        BatchDetectFace), this can optimize throughput.
        Default can be asyncio.gather over recognize() calls.

        Args:
            image_paths: List of image paths.
            target_names: Targets to match.
            concurrency: Max concurrent operations.

        Results in same order as input.
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """
        Release resources on program exit.

        Free connection pools, caches, temp files, etc.
        """
        pass
