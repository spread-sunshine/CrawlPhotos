# -*- coding: utf-8 -*-
"""
Plugin registry + factory for face recognition providers.
插件注册器 + 工厂模式.

Usage:
    registry = FaceRecognizerRegistry.get_instance()
    recognizer = registry.create(ProviderType.TENCENT_CLOUD, config)
"""

import importlib
import logging
from typing import Any, Dict, Optional, Type

from app.face_recognition.interfaces import IFaceRecognizer
from app.face_recognition.models import (
    ProviderInfo,
    ProviderType,
)
from app.face_recognition.providers.no_op_provider import (
    NoOpRecognizer,
)

logger = logging.getLogger(__name__)


class FaceRecognizerRegistry:
    """
    Singleton registry for face recognition providers.

    Responsibilities:
    - Maintain mapping of ProviderType -> implementation class.
    - Factory method to create instances by type.
    - Provide query/list capabilities.
    """

    _instance: Optional["FaceRecognizerRegistry"] = None
    _providers: Dict[
        ProviderType, Type[IFaceRecognizer]
    ] = {}

    def __init__(self):
        self._register_builtin_providers()

    @classmethod
    def get_instance(cls) -> "FaceRecognizerRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(
        self,
        provider_type: ProviderType,
        provider_class: Type[IFaceRecognizer],
    ) -> None:
        """Register a provider implementation class."""
        if not issubclass(provider_class, IFaceRecognizer):
            raise TypeError(
                f"{provider_class.__name__} must implement "
                f"IFaceRecognizer"
            )
        self._providers[provider_type] = provider_class
        logger.debug("Registered provider: %s", provider_type.value)

    def unregister(
        self, provider_type: ProviderType,
    ) -> None:
        """Remove a provider registration."""
        self._providers.pop(provider_type, None)

    def create(
        self,
        provider_type: ProviderType,
        **config_kwargs: Any,
    ) -> IFaceRecognizer:
        """
        Factory method: create instance by provider type.

        Args:
            provider_type: Target provider type.
            **config_kwargs: Provider-specific config params.

        Returns:
            Initialized recognizer instance.

        Raises:
            ValueError: Unknown provider type.
            ProviderInitError: Initialization failed.
        """
        if provider_type not in self._providers:
            available = list(self._providers.keys())
            raise ValueError(
                f"Unknown provider: {provider_type}. "
                f"Available: {[p.value for p in available]}"
            )

        provider_class = self._providers[provider_type]
        instance = provider_class(**config_kwargs)
        logger.info(
            "Created provider: %s (%s)",
            provider_type.value,
            provider_class.__name__,
        )
        return instance

    def list_available(self) -> Dict[ProviderType, ProviderInfo]:
        """List all registered providers with their info."""
        result: Dict[ProviderType, ProviderInfo] = {}
        for ptype, pclass in self._providers.items():
            try:
                # Try getting class-level provider_info
                if hasattr(pclass, "provider_info"):
                    if isinstance(pclass.provider_info, property):
                        # Need instance for property
                        info = ProviderInfo(
                            provider_type=ptype,
                            display_name=pclass.__name__,
                            version="unknown",
                            is_local=False,
                            max_faces_per_image=0,
                            supported_image_formats=[],
                            requires_api_key=True,
                            has_batch_support=False,
                            estimated_cost_per_call=0.0,
                            description="",
                        )
                    else:
                        info = pclass.provider_info
                else:
                    info = ProviderInfo(
                        provider_type=ptype,
                        display_name=pclass.__name__,
                        version="unknown",
                        is_local=False,
                        max_faces_per_image=0,
                        supported_image_formats=[],
                        requires_api_key=True,
                        has_batch_support=False,
                        estimated_cost_per_call=0.0,
                        description="",
                    )
                result[ptype] = info
            except Exception as exc:
                logger.warning(
                    "Failed to get info for %s: %s", ptype, exc
                )
                result[ptype] = ProviderInfo(
                    provider_type=ptype,
                    display_name=pclass.__name__,
                    version="error",
                    is_local=False,
                    max_faces_per_image=0,
                    supported_image_formats=[],
                    requires_api_key=True,
                    has_batch_support=False,
                    estimated_cost_per_call=0.0,
                    description=f"Info fetch failed: {exc}",
                )
        return result

    def _register_builtin_providers(self) -> None:
        """Auto-register built-in provider implementations."""
        builtin_mappings = {
            ProviderType.TENCENT_CLOUD:
                "app.face_recognition.providers.tencent_cloud"
                ".TencentCloudProvider",
            ProviderType.BAIDU:
                "app.face_recognition.providers.baidu"
                ".BaiduProvider",
            ProviderType.INSIGHT_FACE_LOCAL:
                "app.face_recognition.providers.insight_face"
                ".InsightFaceLocalProvider",
            ProviderType.FACE_PLUS:
                "app.face_recognition.providers.face_plus"
                ".FacePlusProvider",
        }

        for ptype, module_path in builtin_mappings.items():
            try:
                parts = module_path.rsplit(".", 1)
                module = importlib.import_module(parts[0])
                cls = getattr(module, parts[1])
                self.register(ptype, cls)
                logger.debug(
                    "Auto-registered builtin provider: %s",
                    ptype.value,
                )
            except ImportError:
                # SDK not installed, fall back to NoOp
                self.register(ptype, NoOpRecognizer)
                logger.info(
                    "Provider %s not installed, "
                    "using NoOp placeholder",
                    ptype.value,
                )
            except Exception as exc:
                # Other error, still fall back to NoOp
                self.register(ptype, NoOpRecognizer)
                logger.warning(
                    "Failed to register %s (%s), "
                    "using NoOp placeholder",
                    ptype.value,
                    exc,
                )
