"""Pytest configuration and fixtures."""

import pytest
import json
from pathlib import Path
from datetime import datetime

from src.models import (
    DesignSystem, Scene, Storyboard, QualityBreakdown, VideoJob, GateState
)
from src.quality_scorer import QualityScorer


@pytest.fixture
def design_system():
    """Load test design system."""
    plugin_dir = Path(__file__).parent.parent
    design_system_path = plugin_dir / "design_system.json"

    with open(design_system_path) as f:
        data = json.load(f)

    return DesignSystem.from_dict(data)


@pytest.fixture
def quality_scorer(design_system):
    """Initialize quality scorer."""
    return QualityScorer(design_system)


@pytest.fixture
def sample_storyboard():
    """Create sample storyboard for testing."""
    scenes = [
        Scene(
            index=0,
            title="What is CorvinOS?",
            body_text="An open-source agentic operating system for autonomous systems.",
            notes="Hero's Journey: Inciting Incident",
            expected_duration_ms=20000
        ),
        Scene(
            index=1,
            title="Core Features",
            body_text="Plugin system, learning loops, audit trails, compliance by design.",
            notes="Hero's Journey: Rising Action",
            expected_duration_ms=25000
        ),
        Scene(
            index=2,
            title="Demo",
            body_text="CorvinOS in action: generating videos like this one.",
            notes="Hero's Journey: Climax",
            expected_duration_ms=20000
        ),
        Scene(
            index=3,
            title="Get Started",
            body_text="github.com/CorvinLabs/CorvinOS",
            notes="Hero's Journey: Resolution",
            expected_duration_ms=15000
        ),
    ]

    return Storyboard(
        id="test-video-1min",
        topic="CorvinOS Introduction",
        duration="1m",
        scenes=scenes,
        narration="What is CorvinOS? An open-source agentic operating system for autonomous systems. "
                  "Core features include plugin system, learning loops, audit trails, and compliance by design. "
                  "CorvinOS in action: generating videos like this one. "
                  "Get started at github.com/CorvinLabs/CorvinOS",
        fact_check_confidence=0.95
    )


@pytest.fixture
def sample_quality_breakdown():
    """Create sample quality breakdown."""
    return QualityBreakdown(
        visual_clarity=18,
        audio_quality=17,
        narrative_flow=16,
        accessibility=15,
        technical_specs=19
    )


@pytest.fixture
def sample_video_job(sample_storyboard, sample_quality_breakdown):
    """Create sample video job."""
    return VideoJob(
        id="test-job-001",
        topic="CorvinOS Intro",
        duration="1m",
        state=GateState.PRODUCTION,
        quality_score=sample_quality_breakdown.total,
        quality_breakdown=sample_quality_breakdown,
        video_path="/tmp/test-video.mp4",
        storyboard=sample_storyboard,
        slides=["/tmp/slide_000.png", "/tmp/slide_001.png"],
        audio_path="/tmp/audio.wav",
        generation_time_ms=4500
    )


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace for video files."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace
