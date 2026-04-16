# -*- coding: utf-8 -*-
"""
Face recognition exception hierarchy.
人脸识别异常体系.
"""

from typing import Optional


class FaceRecognizerError(Exception):
    """Base exception for face recognizer module."""
    pass


class ProviderInitError(FaceRecognizerError):
    """Provider initialization failure."""
    pass


class ProviderApiError(FaceRecognizerError):
    """Provider API call failure."""

    def __init__(
        self,
        message: str,
        status_code: int = 0,
        retryable: bool = True,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class QuotaExhaustedError(ProviderApiError):
    """API quota exhausted."""

    def __init__(
        self,
        message: str,
        reset_time: Optional[str] = None,
    ):
        super().__init__(message, retryable=False)
        self.reset_time = reset_time


class ImageInvalidError(FaceRecognizerError):
    """Image is invalid (format error / corrupted / too large)."""
    pass


class NoFaceDetectedError(FaceRecognizerError):
    """No face detected in the image."""
    pass


class TargetNotFoundError(FaceRecognizerError):
    """Target person not found in the registry."""
    pass
