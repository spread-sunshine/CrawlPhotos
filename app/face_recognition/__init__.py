# -*- coding: utf-8 -*-
"""
Face recognition module with pluggable provider architecture.
人脸识别模块 - 可插拔架构.
"""

from app.face_recognition.interfaces import (
    IFaceRecognizer,
    ProviderType,
    ProviderInfo,
    RecognitionResult,
    FaceDetection,
    BoundingBox,
    TargetConfig,
)
from app.face_recognition.exceptions import (
    FaceRecognizerError,
    ProviderInitError,
    ProviderApiError,
    QuotaExhaustedError,
    ImageInvalidError,
    NoFaceDetectedError,
    TargetNotFoundError,
)
from app.face_recognition.facade import FaceRecognizerFacade

__all__ = [
    "IFaceRecognizer",
    "ProviderType",
    "ProviderInfo",
    "RecognitionResult",
    "FaceDetection",
    "BoundingBox",
    "TargetConfig",
    "FaceRecognizerError",
    "ProviderInitError",
    "ProviderApiError",
    "QuotaExhaustedError",
    "ImageInvalidError",
    "NoFaceDetectedError",
    "TargetNotFoundError",
    "FaceRecognizerFacade",
]
