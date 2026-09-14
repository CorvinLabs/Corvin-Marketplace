"""Unit tests for data models."""

import pytest
from src.models import (
    Scene, Storyboard, QualityBreakdown, VideoJob, GateState,
    DesignSystem, Audio
)


class TestScene:
    """Test Scene model."""

    def test_valid_scene(self):
        """Test creating valid scene."""
        scene = Scene(
            index=0,
            title="Intro",
            body_text="Introduction to CorvinOS",
            notes="Hero's Journey: Inciting Incident",
            expected_duration_ms=20000
        )
        assert scene.index == 0
        assert scene.expected_duration_ms == 20000

    def test_scene_duration_too_short(self):
        """Test scene with too-short duration."""
        with pytest.raises(ValueError, match="Scene duration must be 5-60 seconds"):
            Scene(
                index=0,
                title="Too short",
                body_text="...",
                notes="",
                expected_duration_ms=2000  # <5 seconds
            )

    def test_scene_duration_too_long(self):
        """Test scene with too-long duration."""
        with pytest.raises(ValueError, match="Scene duration must be 5-60 seconds"):
            Scene(
                index=0,
                title="Too long",
                body_text="...",
                notes="",
                expected_duration_ms=120000  # >60 seconds
            )


class TestStoryboard:
    """Test Storyboard model."""

    def test_valid_storyboard(self, sample_storyboard):
        """Test creating valid storyboard."""
        assert sample_storyboard.id == "test-video-1min"
        assert len(sample_storyboard.scenes) == 4
        assert sample_storyboard.fact_check_confidence == 0.95

    def test_storyboard_no_scenes(self):
        """Test storyboard with no scenes."""
        with pytest.raises(ValueError, match="Storyboard must have at least 1 scene"):
            Storyboard(
                id="empty",
                topic="Test",
                duration="1m",
                scenes=[],
                narration="...",
                fact_check_confidence=0.9
            )

    def test_storyboard_invalid_confidence(self, sample_storyboard):
        """Test storyboard with invalid confidence."""
        with pytest.raises(ValueError, match="Confidence must be 0-1"):
            Storyboard(
                id="test",
                topic="Test",
                duration="1m",
                scenes=sample_storyboard.scenes,
                narration="...",
                fact_check_confidence=1.5  # >1
            )


class TestQualityBreakdown:
    """Test QualityBreakdown model."""

    def test_valid_breakdown(self, sample_quality_breakdown):
        """Test valid quality breakdown."""
        assert sample_quality_breakdown.total == 85
        assert 0 <= sample_quality_breakdown.total <= 100

    def test_breakdown_component_too_high(self):
        """Test component score >20."""
        with pytest.raises(ValueError, match="must be 0-20"):
            QualityBreakdown(
                visual_clarity=25,  # >20
                audio_quality=15,
                narrative_flow=15,
                accessibility=15,
                technical_specs=15
            )

    def test_breakdown_component_negative(self):
        """Test negative component score."""
        with pytest.raises(ValueError, match="must be 0-20"):
            QualityBreakdown(
                visual_clarity=-1,
                audio_quality=15,
                narrative_flow=15,
                accessibility=15,
                technical_specs=15
            )

    def test_max_score(self):
        """Test maximum possible score (100)."""
        breakdown = QualityBreakdown(
            visual_clarity=20,
            audio_quality=20,
            narrative_flow=20,
            accessibility=20,
            technical_specs=20
        )
        assert breakdown.total == 100

    def test_min_score(self):
        """Test minimum possible score (0)."""
        breakdown = QualityBreakdown(
            visual_clarity=0,
            audio_quality=0,
            narrative_flow=0,
            accessibility=0,
            technical_specs=0
        )
        assert breakdown.total == 0


class TestVideoJob:
    """Test VideoJob model."""

    def test_valid_job(self, sample_video_job):
        """Test valid video job."""
        assert sample_video_job.id == "test-job-001"
        assert sample_video_job.state == GateState.PRODUCTION
        assert sample_video_job.quality_score == 85

    def test_job_auto_generates_id(self):
        """Test that job auto-generates ID if not provided."""
        job = VideoJob(
            id="",
            topic="Test",
            duration="1m"
        )
        assert len(job.id) > 0

    def test_job_ready_for_broadcast(self, sample_video_job):
        """Test broadcast readiness check."""
        # Current: PRODUCTION, score 85 → not ready
        assert not sample_video_job.is_ready_for_broadcast

        # Change to BROADCAST, score >=85 → ready
        sample_video_job.state = GateState.BROADCAST
        assert sample_video_job.is_ready_for_broadcast

        # Lower score → not ready
        sample_video_job.quality_score = 80
        assert not sample_video_job.is_ready_for_broadcast


class TestAudio:
    """Test Audio model."""

    def test_valid_audio(self):
        """Test creating valid audio."""
        audio = Audio(
            path="/tmp/audio.wav",
            duration_ms=60000,
            provider="google_tts",
            sample_rate_hz=16000,
            channels=1
        )
        assert audio.duration_ms == 60000
        assert audio.provider == "google_tts"

    def test_audio_provider_options(self):
        """Test different provider options."""
        for provider in ["google_tts", "piper", "silence"]:
            audio = Audio(
                path="/tmp/audio.wav",
                duration_ms=30000,
                provider=provider
            )
            assert audio.provider == provider
