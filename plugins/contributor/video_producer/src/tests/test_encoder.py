"""Tests for AdaptiveEncoderSkill."""

import pytest
from dataclasses import dataclass

from ..encoder import AdaptiveEncoderSkill, EncodingProfile, EncodingPresetsLoader


@pytest.fixture
def encoder():
    """Create encoder skill."""
    return AdaptiveEncoderSkill()


@pytest.fixture
def mock_validation_result():
    """Mock validation result."""
    @dataclass
    class MockResult:
        overall_confidence: float = 0.85
    return MockResult()


@pytest.fixture
def scene_metadata():
    """Sample scene metadata."""
    return {"type": "narration", "description": "Screenshot of CorvinOS"}


@pytest.fixture
def job_context():
    """Sample job context."""
    return {"job_id": "job_123", "tenant_id": "_default"}


# ============ Preset Loading Tests ============

def test_presets_load_defaults():
    """Test default presets load correctly."""
    loader = EncodingPresetsLoader()
    assert "youtube" in loader.presets
    assert "linkedin" in loader.presets
    assert "archive" in loader.presets
    assert "presentation" in loader.presets


def test_get_preset_youtube():
    """Test youtube preset exists."""
    loader = EncodingPresetsLoader()
    preset = loader.get_preset("youtube")
    assert preset is not None
    assert "codec_priority" in preset
    assert "bitrate" in preset


# ============ Codec Selection Tests ============

def test_codec_h264_for_linkedin(encoder):
    """Test H.264 chosen for LinkedIn (strict H.264 only)."""
    preset = {"codec_priority": ["h264"]}
    codec = encoder._choose_codec(preset, "narration", 0.9)
    assert codec == "h264"


def test_codec_h265_for_archive(encoder):
    """Test H.265 chosen for archive preset."""
    preset = {"codec_priority": ["h265", "h264"]}
    codec = encoder._choose_codec(preset, "narration", 0.9)
    assert codec == "h265"


def test_codec_fallback_on_low_confidence(encoder):
    """Test H.264 fallback when confidence < 0.7."""
    preset = {"codec_priority": ["h265", "h264"]}
    codec = encoder._choose_codec(preset, "narration", 0.5)
    assert codec == "h264"


def test_codec_scene_override(encoder):
    """Test scene-specific codec override."""
    preset = {
        "codec_priority": ["h264"],
        "scene_overrides": {"title": {"codec": "h265"}},
    }
    codec = encoder._choose_codec(preset, "title", 0.9)
    assert codec == "h265"


# ============ Bitrate Selection Tests ============

def test_bitrate_from_override(encoder):
    """Test bitrate from scene override."""
    preset = {
        "bitrate": {"target": "8000k"},
        "scene_overrides": {"title": {"bitrate": "4000k"}},
    }
    bitrate = encoder._choose_bitrate(preset, "title")
    assert bitrate == "4000k"


def test_bitrate_from_target_range(encoder):
    """Test bitrate extracted from range (e.g., '8-12 Mbps')."""
    preset = {"bitrate": {"target": "8-12 Mbps"}}
    bitrate = encoder._choose_bitrate(preset, "narration")
    assert "k" in bitrate
    assert bitrate == "10000k"  # (8+12)/2 * 1000


def test_bitrate_default(encoder):
    """Test fallback bitrate."""
    preset = {"bitrate": {}}
    bitrate = encoder._choose_bitrate(preset, "screenshot")
    assert bitrate == "8000k"


# ============ Full Encoding Profile Tests ============

def test_encoding_profile_youtube(encoder, scene_metadata, mock_validation_result, job_context):
    """Test full encoding profile for YouTube."""
    preset = encoder.loader.get_preset("youtube")

    profile = encoder.choose_encoding(
        scene_metadata,
        job_context,
        mock_validation_result,
        quality_preset="youtube"
    )

    assert isinstance(profile, EncodingProfile)
    assert profile.codec in ["h264", "h265"]
    assert profile.resolution in ["1080p", "1440p"]
    assert "k" in profile.bitrate
    assert profile.ffmpeg_preset == "medium"
    assert profile.color_profile == "BT.709"


def test_encoding_profile_linkedin(encoder, scene_metadata, mock_validation_result, job_context):
    """Test full encoding profile for LinkedIn."""
    profile = encoder.choose_encoding(
        scene_metadata,
        job_context,
        mock_validation_result,
        quality_preset="linkedin"
    )

    assert profile.codec == "h264"  # LinkedIn enforces H.264
    assert profile.resolution == "1080p"
    assert int(profile.bitrate.rstrip("k")) <= 8000  # Max 8 Mbps


def test_encoding_profile_archive(encoder, scene_metadata, mock_validation_result, job_context):
    """Test full encoding profile for archive."""
    profile = encoder.choose_encoding(
        scene_metadata,
        job_context,
        mock_validation_result,
        quality_preset="archive"
    )

    # Archive prefers H.265
    assert profile.codec == "h265"
    assert profile.resolution in ["1440p", "2160p"]
    assert profile.color_profile == "BT.2020"


# ============ FFmpeg Args Generation ============

def test_ffmpeg_args_generation():
    """Test FFmpeg arguments generated correctly."""
    profile = EncodingProfile(
        codec="h264",
        resolution="1080p",
        bitrate="8000k",
        ffmpeg_preset="medium",
        color_profile="BT.709",
        audio_codec="aac",
        audio_bitrate="128k",
    )

    args = profile.to_ffmpeg_args("input.mp4", "output.mp4")

    assert "-c:v" in args
    assert "libx264" in args or "h264" in args
    assert "-b:v" in args
    assert "8000k" in args
    assert "-c:a" in args
    assert "aac" in args
    assert "output.mp4" in args


# ============ Integration Tests ============

def test_full_workflow_youtube(encoder, scene_metadata, mock_validation_result, job_context):
    """Test full workflow: scene → encoding profile → ffmpeg args."""
    profile = encoder.choose_encoding(
        scene_metadata,
        job_context,
        mock_validation_result,
        "youtube"
    )

    args = profile.to_ffmpeg_args("test.png", "output.mp4")

    assert len(args) > 10
    assert "test.png" in args
    assert "output.mp4" in args
    assert all(isinstance(arg, str) for arg in args)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
