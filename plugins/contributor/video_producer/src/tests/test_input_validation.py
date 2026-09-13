"""Tests for InputValidatorSkill — 8-point validation pipeline."""

import pytest
from pathlib import Path
from PIL import Image
import asyncio

from ..input_validator import InputValidatorSkill, AssetValidationResult


@pytest.fixture
def validator():
    """Create InputValidatorSkill instance."""
    return InputValidatorSkill()


@pytest.fixture
def temp_image(tmp_path):
    """Create temporary test image."""
    img = Image.new('RGB', (1920, 1080), color='red')
    img_path = tmp_path / "test.png"
    img.save(img_path)
    return str(img_path)


@pytest.fixture
def low_res_image(tmp_path):
    """Create low-res test image (640x480)."""
    img = Image.new('RGB', (640, 480), color='blue')
    img_path = tmp_path / "low_res.png"
    img.save(img_path)
    return str(img_path)


@pytest.fixture
def scene_metadata():
    """Sample scene metadata."""
    return {
        "id": "scene_1",
        "type": "narration",
        "description": "Screenshot of CorvinOS console showing plugin system"
    }


@pytest.fixture
def job_context():
    """Sample job context."""
    return {
        "job_id": "job_abc123",
        "tenant_id": "_default"
    }


# ============ Unit Tests ============

def test_file_integrity_valid(validator, temp_image):
    """Test valid PNG file passes integrity check."""
    check = validator._check_file_integrity(temp_image)
    assert check.check_type == "file_integrity"
    assert check.passed is True
    assert check.severity == "info"


def test_file_integrity_missing(validator):
    """Test missing file fails integrity check."""
    check = validator._check_file_integrity("/nonexistent/file.png")
    assert check.check_type == "file_integrity"
    assert check.passed is False
    assert check.severity == "fail"
    assert "not found" in check.message.lower()


def test_resolution_valid(validator, temp_image):
    """Test 1920×1080 (1080p) is valid."""
    check = validator._check_resolution(temp_image)
    assert check.check_type == "resolution"
    assert check.passed is True
    assert "1920" in check.message


def test_resolution_too_low(validator, low_res_image):
    """Test 640×480 is below 720p threshold."""
    check = validator._check_resolution(low_res_image)
    assert check.check_type == "resolution"
    assert check.passed is False
    assert check.severity == "fail"
    assert "too low" in check.message.lower()


def test_colorspace_detection(validator, temp_image):
    """Test colorspace detection defaults to sRGB."""
    check = validator._detect_colorspace(temp_image)
    assert check.check_type == "colorspace_detection"
    assert check.passed is True
    assert "srgb" in check.message.lower() or "default" in check.message.lower()


def test_artifact_detection(validator, temp_image):
    """Test artifact detection (basic check)."""
    check = validator._detect_artifacts(temp_image)
    assert check.check_type == "artifact_detection"
    # Phase 1: basic check always passes
    assert check.passed is True


def test_consistency_check(validator, temp_image):
    """Test consistency check (Phase 2 feature, mock passes)."""
    check = validator._check_consistency(temp_image)
    assert check.check_type == "consistency_check"
    assert check.passed is True


# ============ Integration Tests (Async) ============

@pytest.mark.asyncio
async def test_validate_asset_valid_screenshot(validator, temp_image, scene_metadata, job_context):
    """Test full validation pipeline on valid screenshot."""
    result = await validator.validate_asset(temp_image, scene_metadata, job_context)

    assert isinstance(result, AssetValidationResult)
    assert result.status in ["pass", "warn"]
    assert result.overall_confidence >= 0.7
    assert len(result.checks) == 8
    assert all(c.check_type for c in result.checks)


@pytest.mark.asyncio
async def test_validate_asset_low_resolution(validator, low_res_image, scene_metadata, job_context):
    """Test validation fails on low-resolution image."""
    result = await validator.validate_asset(low_res_image, scene_metadata, job_context)

    assert result.status == "fail"
    assert result.fallback_action == "reject"
    # Resolution check should have failed
    resolution_check = [c for c in result.checks if c.check_type == "resolution"][0]
    assert resolution_check.passed is False


@pytest.mark.asyncio
async def test_validate_asset_missing_file(validator, scene_metadata, job_context):
    """Test validation fails on missing file."""
    result = await validator.validate_asset("/nonexistent.png", scene_metadata, job_context)

    assert result.status == "fail"
    assert result.fallback_action == "reject"


# ============ Confidence Scoring Tests ============

def test_confidence_no_warnings(validator):
    """Test confidence = 0.95 when no warnings."""
    from ..input_validator import ValidationCheck

    checks = [
        ValidationCheck("test1", True, "info", "OK"),
        ValidationCheck("test2", True, "info", "OK"),
    ]

    result = validator._finalize_result(
        validator.AssetValidationResult("a1", "s1", "j1"),
        checks,
        "pass",
        "proceed"
    )
    assert result.overall_confidence >= 0.9


def test_confidence_with_warnings(validator):
    """Test confidence reduces with warnings."""
    from ..input_validator import ValidationCheck

    checks = [
        ValidationCheck("test1", True, "info", "OK"),
        ValidationCheck("test2", False, "warn", "Warning"),
    ]

    result = validator._finalize_result(
        validator.AssetValidationResult("a1", "s1", "j1"),
        checks,
        "warn",
        "proceed"
    )
    assert 0.7 <= result.overall_confidence < 0.95


# ============ Edge Cases ============

@pytest.mark.asyncio
async def test_validate_empty_description(validator, temp_image, job_context):
    """Test validation with empty scene description."""
    metadata = {"id": "s1", "type": "title", "description": ""}
    result = await validator.validate_asset(temp_image, metadata, job_context)

    # Should still pass (description is optional)
    assert result.status in ["pass", "warn"]


@pytest.mark.asyncio
async def test_validate_all_checks_present(validator, temp_image, scene_metadata, job_context):
    """Test that all 8 checks are executed."""
    result = await validator.validate_asset(temp_image, scene_metadata, job_context)

    expected_checks = [
        "file_integrity",
        "resolution",
        "colorspace_detection",
        "contradiction_detection",
        "artifact_detection",
        "layout_validation",
        "scene_specific_validation",
        "consistency_check",
    ]

    actual_checks = [c.check_type for c in result.checks]
    for expected in expected_checks:
        assert expected in actual_checks, f"Missing check: {expected}"


# ============ Performance Tests ============

@pytest.mark.asyncio
async def test_validation_completes_in_timeout(validator, temp_image, scene_metadata, job_context):
    """Test validation completes within 10 second timeout (Phase 1 target)."""
    import time
    start = time.time()
    result = await validator.validate_asset(temp_image, scene_metadata, job_context)
    elapsed = time.time() - start

    # Phase 1: target <5s per asset (Vision API adds ~2s)
    # Allow 10s for test environment
    assert elapsed < 10, f"Validation took {elapsed:.1f}s (target <5s)"
    assert result.status in ["pass", "warn", "fail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
