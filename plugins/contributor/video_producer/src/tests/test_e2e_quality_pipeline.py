"""End-to-End Test — Full Quality Pipeline with Real Video."""

import pytest
import asyncio
from pathlib import Path
from PIL import Image

from ..quality_pipeline import VideoQualityPipeline


@pytest.fixture
def pipeline():
    """Create quality pipeline."""
    return VideoQualityPipeline()


@pytest.fixture
def test_video_asset(tmp_path):
    """Create realistic test video asset."""
    img = Image.new('RGB', (1920, 1080), color='blue')
    asset_path = tmp_path / "video_scene_1.png"
    img.save(asset_path)
    return str(asset_path)


@pytest.fixture
def scene_data():
    """Sample scene metadata."""
    return {
        "id": "scene_1",
        "type": "narration",
        "description": "Screenshot of CorvinOS console showing the video producer plugin in action",
    }


@pytest.fixture
def job_context():
    """Sample job context."""
    return {
        "job_id": "job_e2e_test_001",
        "tenant_id": "_default",
    }


# ============ E2E Tests ============

@pytest.mark.asyncio
async def test_e2e_full_pipeline_youtube(pipeline, test_video_asset, scene_data, job_context):
    """Test full pipeline: validate → color → encode (YouTube preset)."""
    result = await pipeline.process_scene(
        test_video_asset,
        scene_data,
        job_context,
        quality_preset="youtube"
    )

    # Should succeed
    assert result["status"] == "success"

    # Validation should pass
    val = result["validation"]
    assert val.overall_confidence > 0.7
    assert len(val.checks) == 8

    # Encoding should be chosen
    enc = result["encoding"]
    assert enc.codec in ["h264", "h265"]
    assert enc.resolution in ["1080p", "1440p"]
    assert "k" in enc.bitrate

    # Color should be processed
    col = result["color"]
    assert col.status in ["success", "warn"]


@pytest.mark.asyncio
async def test_e2e_full_pipeline_archive(pipeline, test_video_asset, scene_data, job_context):
    """Test full pipeline with Archive preset (higher quality)."""
    result = await pipeline.process_scene(
        test_video_asset,
        scene_data,
        job_context,
        quality_preset="archive"
    )

    assert result["status"] == "success"

    # Archive should prefer H.265
    enc = result["encoding"]
    assert enc.codec == "h265"

    # Archive should use higher resolution
    assert enc.resolution in ["1440p", "2160p"]


@pytest.mark.asyncio
async def test_e2e_job_processing(pipeline, test_video_asset, job_context):
    """Test processing a full job with multiple scenes."""
    scenes = [
        {
            "id": "scene_1",
            "type": "title",
            "description": "Title scene",
            "asset_path": test_video_asset,
        },
        {
            "id": "scene_2",
            "type": "narration",
            "description": "Narration with screenshot",
            "asset_path": test_video_asset,
        },
        {
            "id": "scene_3",
            "type": "screenshot",
            "description": "UI screenshot",
            "asset_path": test_video_asset,
        },
    ]

    result = await pipeline.process_job(
        scenes,
        job_context,
        quality_preset="youtube"
    )

    # Aggregate stats
    assert result["job_id"] == job_context["job_id"]
    assert result["aggregate"]["total_scenes"] == 3
    assert result["aggregate"]["passed_validation"] + result["aggregate"]["warned_validation"] > 0
    assert result["aggregate"]["avg_confidence"] > 0.5

    # Per-scene results
    assert len(result["scenes"]) == 3
    for scene_result in result["scenes"]:
        assert scene_result["scene_id"] in ["scene_1", "scene_2", "scene_3"]
        assert scene_result["result"]["status"] in ["success", "error"]


@pytest.mark.asyncio
async def test_e2e_ffmpeg_args_generation(pipeline, test_video_asset, scene_data, job_context):
    """Test that FFmpeg args are generated correctly from encoding profile."""
    result = await pipeline.process_scene(
        test_video_asset,
        scene_data,
        job_context,
        quality_preset="youtube"
    )

    assert result["status"] == "success"
    enc = result["encoding"]

    # Generate FFmpeg args
    ffmpeg_args = enc.to_ffmpeg_args(test_video_asset, "/tmp/output.mp4")

    # Verify essential FFmpeg arguments
    assert "-i" in ffmpeg_args
    assert test_video_asset in ffmpeg_args
    assert "-c:v" in ffmpeg_args
    assert "-b:v" in ffmpeg_args
    assert "-c:a" in ffmpeg_args
    assert "/tmp/output.mp4" in ffmpeg_args


@pytest.mark.asyncio
async def test_e2e_performance_latency(pipeline, test_video_asset, scene_data, job_context):
    """Test that pipeline completes within performance target."""
    import time

    start = time.time()
    result = await pipeline.process_scene(
        test_video_asset,
        scene_data,
        job_context,
    )
    elapsed = time.time() - start

    # Phase 1 target: <5 seconds per scene (Vision API adds ~2s)
    # Allow 10s for test environment
    assert elapsed < 10, f"Pipeline took {elapsed:.1f}s (target <5s)"
    assert result["status"] == "success"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
