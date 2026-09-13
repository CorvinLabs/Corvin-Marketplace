"""E2E Tests for Phase 2 — Feedback Loop + Learning Optimizer."""

import pytest
import asyncio
from ..feedback_handler import FeedbackHandlerSkill, SceneQualityFeedback
from ..optimizer import VideoQualityOptimizer


@pytest.fixture
def optimizer():
    return VideoQualityOptimizer()


@pytest.fixture
def feedback_handler(optimizer):
    return FeedbackHandlerSkill(optimizer=optimizer)


@pytest.mark.asyncio
async def test_submit_feedback_approved(feedback_handler):
    """Test submitting approval feedback."""
    feedback_id = await feedback_handler.submit_feedback(
        scene_id="scene_1",
        job_id="job_test_001",
        feedback_type="approved",
        tenant_id="_default",
    )

    assert feedback_id != ""

    # Check feedback stored
    feedbacks = feedback_handler.get_job_feedback("job_test_001")
    assert len(feedbacks) == 1
    assert feedbacks[0].feedback_type == "approved"


@pytest.mark.asyncio
async def test_submit_feedback_rejection(feedback_handler):
    """Test submitting rejection feedback."""
    feedback_id = await feedback_handler.submit_feedback(
        scene_id="scene_2",
        job_id="job_test_002",
        feedback_type="too_blurry",
        tenant_id="_default",
    )

    assert feedback_id != ""
    feedbacks = feedback_handler.get_job_feedback("job_test_002")
    assert feedbacks[0].feedback_type == "too_blurry"


def test_optimizer_default_configs():
    """Test optimizer has sensible defaults."""
    opt = VideoQualityOptimizer()

    # Check all scene types have configs
    for scene_type in ["title", "narration", "screenshot", "animation"]:
        config = opt.get_config(scene_type)
        assert config.scene_type == scene_type
        assert 0.8 <= config.bitrate_multiplier <= 1.2
        assert config.codec in ["h264", "h265"]


@pytest.mark.asyncio
async def test_optimizer_learns_from_feedback():
    """Test optimizer adjusts parameters based on feedback."""
    opt = VideoQualityOptimizer()

    # Initial config
    initial = opt.get_config("narration")
    initial_bitrate = initial.bitrate_multiplier

    # Simulate feedback (too blurry → increase bitrate)
    feedback_list = [
        {"feedback_type": "too_blurry", "scene_type": "narration"}
    ]

    await opt.optimize("job_test_003", "_default", feedback_list)

    # Check parameter adjusted
    updated = opt.get_config("narration")
    assert updated.bitrate_multiplier > initial_bitrate
    assert "job_test_003" in updated.job_ids_trained_on


@pytest.mark.asyncio
async def test_optimizer_learns_compression(optimizer):
    """Test optimizer switches codec on compression complaint."""
    opt = VideoQualityOptimizer()

    feedback_list = [
        {"feedback_type": "too_compressed", "scene_type": "screenshot"}
    ]

    await opt.optimize("job_test_004", "_default", feedback_list)

    # Should prefer H.265 for better compression
    updated = opt.get_config("screenshot")
    assert updated.codec == "h265"


def test_feedback_validation():
    """Test feedback validation."""
    handler = FeedbackHandlerSkill()

    # Valid feedback
    fb = SceneQualityFeedback(
        scene_id="s1",
        job_id="j1",
        feedback_type="approved",
        confidence=0.9,
        timestamp=asyncio.get_event_loop().time(),
        tenant_id="_default",
    )

    assert handler._validate_feedback(fb) is True

    # Invalid type
    fb2 = SceneQualityFeedback(
        scene_id="s1",
        job_id="j1",
        feedback_type="invalid_type",  # type: ignore
        confidence=0.9,
        timestamp=asyncio.get_event_loop().time(),
        tenant_id="_default",
    )

    assert handler._validate_feedback(fb2) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
