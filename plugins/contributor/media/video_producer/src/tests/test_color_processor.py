"""Tests for ColorProcessorSkill."""

import pytest
from PIL import Image
from pathlib import Path

from ..color_processor import ColorProcessorSkill, ColorProcessingResult


@pytest.fixture
def processor():
    return ColorProcessorSkill()


@pytest.fixture
def test_image(tmp_path):
    """Create test image."""
    img = Image.new('RGB', (1920, 1080), color='red')
    img_path = tmp_path / "test.png"
    img.save(img_path)
    return str(img_path)


@pytest.mark.asyncio
async def test_detect_colorspace_defaults_to_srgb(processor, test_image):
    """Test colorspace defaults to sRGB if not in EXIF."""
    space = await processor.detect_colorspace(test_image)
    assert space in processor.SUPPORTED_SPACES
    assert space == "sRGB"


@pytest.mark.asyncio
async def test_convert_to_working_space(processor, test_image):
    """Test conversion to sRGB."""
    result = await processor.convert_to_working_space(test_image, "Adobe RGB", "sRGB")
    assert result == test_image


@pytest.mark.asyncio
async def test_process_scene_colors(processor, test_image):
    """Test full color processing pipeline."""
    result = await processor.process_scene_colors(
        test_image,
        {"id": "scene_1"},
        {"working_space": "sRGB"}
    )

    assert isinstance(result, ColorProcessingResult)
    assert result.scene_id == "scene_1"
    assert result.status in ["success", "warn", "fail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
