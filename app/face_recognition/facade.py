# -*- coding: utf-8 -*-
"""
Facade class for face recognition - single entry point.
人脸识别门面类 - 业务层唯一交互入口.

Encapsulates provider selection logic, unified exception handling,
and logging. The caller is completely shielded from underlying
differences between providers.
"""

import logging
from typing import Any, Dict, List, Optional

from app.face_recognition.exceptions import FaceRecognizerError
from app.face_recognition.interfaces import IFaceRecognizer
from app.face_recognition.models import (
    ProviderInfo,
    ProviderType,
    RecognitionResult,
    TargetConfig,
)
from app.face_recognition.registry import FaceRecognizerRegistry

logger = logging.getLogger(__name__)


class FaceRecognizerFacade:
    """
    Facade pattern + Strategy combination for face recognition.

    Responsibilities:
    - Read config and select provider via factory.
    - Unified exception handling and logging.
    - Optional circuit-breaker / degradation support.
    - Fully hide provider differences from callers.
    """

    def __init__(self, config: Dict[str, Any]):
        self._config = config
        self._recognizer: Optional[IFaceRecognizer] = None
        self._registry = FaceRecognizerRegistry.get_instance()
        self._initialize_from_config()

    def _initialize_from_config(self) -> None:
        """Load config and create the appropriate provider."""
        provider_name = self._config.get(
            "provider", "tencent_cloud"
        )

        try:
            provider_type = ProviderType(provider_name)
        except ValueError as err:
            raise FaceRecognizerError(
                f"Unsupported provider: {provider_name}. "
                f"Available: "
                f"{[p.value for p in ProviderType]}"
            ) from err

        provider_config = self._config.get(provider_name, {})

        self._recognizer = self._registry.create(
            provider_type, **provider_config
        )

        logger.info(
            "FaceRecognizerFacade initialized with "
            "provider=%s",
            provider_name,
        )

    async def initialize(
        self, targets: List[TargetConfig],
    ) -> bool:
        """Initialize the underlying recognizer with targets."""
        if self._recognizer is None:
            raise FaceRecognizerError("Recognizer not initialized")
        return await self._recognizer.initialize(targets)

    async def recognize(
        self, image_path: str, **kwargs
    ) -> RecognitionResult:
        """Delegate recognition to the active provider."""
        if self._recognizer is None:
            raise FaceRecognizerError("Recognizer not initialized")
        return await self._recognizer.recognize(image_path, **kwargs)

    async def batch_recognize(
        self, paths: List[str], **kwargs
    ) -> List[RecognitionResult]:
        """Batch delegate."""
        if self._recognizer is None:
            raise FaceRecognizerError("Recognizer not initialized")
        return await self._recognizer.batch_recognize(paths, **kwargs)

    async def health_check(self) -> Dict[str, Any]:
        """Check provider health."""
        if self._recognizer is None:
            return {"healthy": False, "message": "Not initialized"}
        return await self._recognizer.health_check()

    @property
    def current_provider_info(self) -> ProviderInfo:
        """Return current provider's info."""
        if self._recognizer:
            return self._recognizer.provider_info
        return ProviderInfo(
            provider_type=ProviderType.CUSTOM,
            display_name="None",
            version="",
            is_local=False,
            max_faces_per_image=0,
            supported_image_formats=[],
            requires_api_key=True,
            has_batch_support=False,
            estimated_cost_per_call=0.0,
            description="No provider loaded",
        )

    async def cleanup(self) -> None:
        """Clean up provider resources."""
        if self._recognizer:
            await self._recognizer.cleanup()
            logger.info("Recognizer cleaned up")

    async def switch_provider(
        self,
        new_provider: str,
        new_config: Dict[str, Any],
    ) -> bool:
        """
        Hot-swap provider at runtime.

        Args:
            new_provider: New provider name string.
            new_config: Configuration for the new provider.

        Returns:
            True on success.
        """
        if self._recognizer:
            await self._recognizer.cleanup()

        self._config["provider"] = new_provider
        self._config[new_provider] = new_config
        self._initialize_from_config()
        logger.info("Switched to provider: %s", new_provider)
        return True
