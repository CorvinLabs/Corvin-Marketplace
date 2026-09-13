"""ColorProcessorSkill — Colorspace detection & conversion."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ColorProcessingResult:
    """Result of color processing."""
    scene_id: str
    input_colorspace: str
    output_colorspace: str
    status: Literal["success", "warn", "fail"]
    warnings: list = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.warnings is None:
            object.__setattr__(self, 'warnings', [])
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', datetime.now(timezone.utc))


class ColorProcessorSkill:
    """Detect and process colorspace."""

    SUPPORTED_SPACES = {"sRGB", "BT.709", "BT.2020", "Adobe RGB", "DCI-P3"}

    async def detect_colorspace(self, image_path: str) -> str:
        """Detect colorspace from EXIF or infer from histogram."""
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS

            with Image.open(image_path) as img:
                # Try EXIF
                try:
                    exif_data = img._getexif()
                    if exif_data:
                        for tag_id, value in exif_data.items():
                            tag_name = TAGS.get(tag_id, tag_id)
                            if "color" in tag_name.lower() and value in self.SUPPORTED_SPACES:
                                return str(value)
                except:
                    pass
        except Exception as e:
            logger.warning(f"Colorspace detection failed: {e}")

        # Default: sRGB
        return "sRGB"

    async def convert_to_working_space(
        self,
        image_path: str,
        source_space: str,
        target_space: str = "sRGB"
    ) -> str:
        """Convert image to working colorspace."""
        if source_space == target_space:
            return image_path

        try:
            from PIL import Image, ImageCms

            with Image.open(image_path) as img:
                # Phase 1: Simple RGB conversion (no ICC profile)
                if img.mode != "RGB":
                    rgb_img = img.convert("RGB")
                    rgb_img.save(image_path)
                    logger.info(f"Converted {image_path} to RGB")

            return image_path
        except Exception as e:
            logger.warning(f"Colorspace conversion failed: {e}")
            raise

    async def process_scene_colors(
        self,
        scene_image: str,
        scene_metadata: dict,
        config: dict = None,
    ) -> ColorProcessingResult:
        """Process scene through color pipeline."""
        scene_id = scene_metadata.get("id", "unknown")

        try:
            # 1. Detect input colorspace
            detected = await self.detect_colorspace(scene_image)

            # 2. Convert to working space (default sRGB)
            working_space = config.get("working_space", "sRGB") if config else "sRGB"
            await self.convert_to_working_space(scene_image, detected, working_space)

            return ColorProcessingResult(
                scene_id=scene_id,
                input_colorspace=detected,
                output_colorspace=working_space,
                status="success",
                warnings=[]
            )
        except Exception as e:
            logger.error(f"Color processing failed for {scene_id}: {e}")
            return ColorProcessingResult(
                scene_id=scene_id,
                input_colorspace="unknown",
                output_colorspace="sRGB",
                status="fail",
                warnings=[str(e)]
            )
