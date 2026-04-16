# -*- coding: utf-8 -*-
"""
Face recognition data models.
人脸识别数据模型.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ProviderType(Enum):
    """Supported face recognition provider types."""
    TENCENT_CLOUD = "tencent_cloud"
    BAIDU = "baidu"
    FACE_PLUS = "face_plus"
    INSIGHT_FACE_LOCAL = "insight_face_local"
    ALIYUN = "aliyun"
    CUSTOM = "custom"


@dataclass
class BoundingBox:
    """Face bounding box coordinates."""
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> Dict[str, int]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class FaceDetection:
    """Single face detection result."""
    face_id: str
    bounding_box: BoundingBox
    confidence: float  # 0~1
    face_image_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "face_id": self.face_id,
            "bounding_box": self.bounding_box.to_dict(),
            "confidence": self.confidence,
            "face_image_path": self.face_image_path,
        }


@dataclass
class RecognitionResult:
    """Complete recognition result for one photo."""
    source_photo_path: str
    total_faces_detected: int = 0
    target_matches: List[Dict] = field(default_factory=list)
    # Each match:
    #   {"target_name": "...", "confidence": 0.96,
    #    "face_box": BoundingBox, ...}
    contains_target: bool = False
    best_confidence: float = 0.0
    all_face_detections: List[FaceDetection] = field(
        default_factory=list
    )
    provider_name: str = ""
    processing_time_ms: float = 0.0
    raw_response: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_photo_path": self.source_photo_path,
            "total_faces_detected": self.total_faces_detected,
            "target_matches": self.target_matches,
            "contains_target": self.contains_target,
            "best_confidence": self.best_confidence,
            "provider_name": self.provider_name,
            "processing_time_ms": self.processing_time_ms,
        }


@dataclass
class TargetConfig:
    """Target person configuration for recognition."""
    name: str
    reference_photo_paths: List[Path] = field(
        default_factory=list
    )
    min_confidence: float = 0.80
    enabled: bool = True
    feature_vector: Optional[bytes] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "reference_photo_count": len(self.reference_photo_paths),
            "min_confidence": self.min_confidence,
            "enabled": self.enabled,
            "feature_vector_cached": (
                self.feature_vector is not None
            ),
        }


@dataclass
class ProviderInfo:
    """Provider capability description."""
    provider_type: ProviderType
    display_name: str
    version: str
    is_local: bool
    max_faces_per_image: int
    supported_image_formats: List[str]
    requires_api_key: bool
    has_batch_support: bool
    estimated_cost_per_call: float
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_type": self.provider_type.value,
            "display_name": self.display_name,
            "version": self.version,
            "is_local": self.is_local,
            "max_faces_per_image": self.max_faces_per_image,
            "supported_image_formats": self.supported_image_formats,
            "requires_api_key": self.requires_api_key,
            "has_batch_support": self.has_batch_support,
            "estimated_cost_per_call": self.estimated_cost_per_call,
            "description": self.description,
        }
