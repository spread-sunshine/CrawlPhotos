# -*- coding: utf-8 -*-
"""
Image preprocessing pipeline.
图片预处理管道 - EXIF方向校正、格式转换、智能缩放、质量压缩.

Processing stages:
1. EXIF orientation correction (auto-rotate)
2. Format normalization (convert non-JPEG to JPEG)
3. Smart resize (max dimension limit)
4. Quality compression (reduce file size)
"""

import io
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image
from PIL.ExifTags import TAGS

# Pillow 10+ removed Orientation; use the standard EXIF tag value
_ORIENTATION_TAG = 274  # EXIF "Orientation" tag ID

from app.config.logging_config import get_logger

logger = get_logger(__name__)


class ImageFormat(Enum):
    JPEG = "JPEG"
    PNG = "PNG"
    WEBP = "WEBP"


@dataclass
class PreprocessConfig:
    """Configuration for image preprocessing pipeline."""
    max_width: int = 2048          # Max image width (px)
    max_height: int = 2048         # Max image height (px)
    jpeg_quality: int = 85         # JPEG quality (1-100)
    output_format: ImageFormat = ImageFormat.JPEG
    strip_exif: bool = False       # Remove EXIF after correction
    preserve_original_filename: bool = True


@dataclass
class PreprocessResult:
    """Result of image preprocessing."""
    success: bool
    output_path: Optional[Path] = None
    original_size_bytes: int = 0
    processed_size_bytes: int = 0
    original_format: str = ""
    was_rotated: bool = False
    was_resized: bool = False
    width: int = 0
    height: int = 0
    error_message: Optional[str] = None


class ImagePreprocessor:
    """
    Image preprocessing pipeline executor.

    Applies a series of transformations to prepare images
    for face recognition and long-term storage.
    """

    def __init__(
        self,
        config: Optional[PreprocessConfig] = None,
    ):
        self._config = config or PreprocessConfig()
        logger.info(
            "ImagePreprocessor initialized: max=%dx%d, "
            "quality=%d",
            self._config.max_width,
            self._config.max_height,
            self._config.jpeg_quality,
        )

    def process(
        self, input_path: Path, output_path: Path,
    ) -> PreprocessResult:
        """
        Run full preprocessing pipeline on an image.

        Pipeline stages:
        1. Load image with EXIF orientation handling
        2. Auto-rotate based on EXIF orientation tag
        3. Resize if dimensions exceed limits
        4. Convert format and compress quality
        5. Save to output path

        Args:
            input_path: Source image file path.
            output_path: Destination file path.

        Returns:
            PreprocessResult with processing details.
        """
        result = PreprocessResult(success=False)
        result.original_format = input_path.suffix.lstrip(".").upper()

        try:
            # Get original file size
            result.original_size_bytes = input_path.stat().st_size

            # Stage 1: Load image
            img = Image.open(input_path)
            original_mode = img.mode

            # Convert palette/grayscale modes to RGB
            if img.mode in ("P", "PA"):
                img = img.convert("RGBA").convert("RGB")
            elif img.mode == "LA":
                img = img.convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Stage 2: EXIF auto-rotation
            img, result.was_rotated = self._apply_exif_orientation(img, input_path)

            orig_width, orig_height = img.size

            # Stage 3: Smart resize
            img, result.was_resized = self._resize_if_needed(img)

            result.width, result.height = img.size

            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Stage 4 & 5: Format conversion + compression
            save_kwargs: dict = {}
            if self._config.output_format == ImageFormat.JPEG:
                save_kwargs["quality"] = self._config.jpeg_quality
                save_kwargs["optimize"] = True
            elif self._config.output_format == ImageFormat.PNG:
                save_kwargs["optimize"] = True
            elif self._config.output_format == ImageFormat.WEBP:
                save_kwargs["quality"] = self._config.jpeg_quality

            # Strip EXIF data after processing if requested
            exif_data = None
            if not self._config.strip_exif and hasattr(img, "info"):
                exif_data = img.info.get("exif")

            if exif_data:
                save_kwargs["exif"] = exif_data

            img.save(output_path, **save_kwargs)
            result.processed_size_bytes = output_path.stat().st_size
            result.output_path = output_path
            result.success = True

            logger.debug(
                "Preprocessed: %s (%dx%d -> %dx%d) "
                "%dB -> %dB rot=%s resize=%s",
                input_path.name,
                orig_width, orig_height,
                result.width, result.height,
                result.original_size_bytes,
                result.processed_size_bytes,
                result.was_rotated,
                result.was_resized,
            )

        except Exception as exc:
            logger.error(
                "Failed to preprocess %s: %s",
                input_path,
                exc,
            )
            result.error_message = str(exc)

        return result

    @staticmethod
    def _apply_exif_orientation(
        img: Image.Image, file_path: Path,
    ) -> Tuple[Image.Image, bool]:
        """
        Auto-rotate image based on EXIF Orientation tag.

        Many phone cameras store rotation metadata instead of
        actually rotating pixel data. This corrects it.

        Returns:
            (rotated_image, whether_rotation_was_applied)
        """
        was_rotated = False

        try:
            exif = img._getexif() if hasattr(img, "_getexif") else None
            if exif is None:
                return img, was_rotated

            # Find orientation tag value (274 = Orientation)
            orientation = exif.get(_ORIENTATION_TAG, 1)

            rotation_map = {
                2: Image.FLIP_LEFT_RIGHT,
                3: Image.ROTATE_180,
                4: Image.FLIP_TOP_BOTTOM,
                5: Image.TRANSPOSE,
                6: Image.ROTATE_270,
                7: Image.TRANSVERSE,
                8: Image.ROTATE_90,
            }

            if orientation in rotation_map:
                img = img.transpose(rotation_map[orientation])
                was_rotated = True
                logger.debug(
                    "Applied EXIF orientation %d for %s",
                    orientation,
                    file_path.name,
                )

        except (AttributeError, KeyError, TypeError) as exc:
            logger.debug(
                "No EXIF orientation data in %s: %s",
                file_path.name,
                exc,
            )

        return img, was_rotated

    def _resize_if_needed(
        self, img: Image.Image,
    ) -> Tuple[Image.Image, bool]:
        """
        Resize image if dimensions exceed configured limits.

        Maintains aspect ratio using thumbnail method.

        Returns:
            (resized_or_original_image, whether_resized)
        """
        width, height = img.size
        max_w = self._config.max_width
        max_h = self._config.max_height

        if width <= max_w and height <= max_h:
            return img, False

        # Use thumbnail for high-quality downsizing
        img.thumbnail((max_w, max_h), Image.LANCZOS)

        logger.debug(
            "Resized %dx%d to %dx%d",
            width, height, img.size[0], img.size[1],
        )
        return img, True
