"""Data models for Video Producer Plugin."""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from enum import Enum
from datetime import datetime
import uuid


class GateState(Enum):
    """Video quality gate states."""
    DRAFT = "draft"  # 0-50 points: iterate
    PRODUCTION = "production"  # 50-85 points: queue for upload
    BROADCAST = "broadcast"  # 85-100 points: ready for YouTube


@dataclass
class Scene:
    """Single scene in a storyboard."""
    index: int
    title: str
    body_text: str
    notes: str
    expected_duration_ms: int  # Target duration for this scene

    def __post_init__(self):
        if not (5000 <= self.expected_duration_ms <= 60000):
            raise ValueError(f"Scene duration must be 5-60 seconds, got {self.expected_duration_ms}ms")


@dataclass
class Storyboard:
    """Complete narrative structure."""
    id: str
    topic: str
    duration: str  # "1m", "5m", "15m"
    scenes: List[Scene]
    narration: str  # Full script
    fact_check_confidence: float  # 0-1: how confident are facts verified?
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if not self.scenes:
            raise ValueError("Storyboard must have at least 1 scene")
        if self.fact_check_confidence < 0 or self.fact_check_confidence > 1:
            raise ValueError(f"Confidence must be 0-1, got {self.fact_check_confidence}")


@dataclass
class Audio:
    """Generated audio file."""
    path: str
    duration_ms: int
    provider: str  # "google_tts", "piper", "silence"
    sample_rate_hz: int = 16000
    channels: int = 1


@dataclass
class QualityBreakdown:
    """5-component quality score."""
    visual_clarity: int  # 0-20: text readability + contrast
    audio_quality: int  # 0-20: volume + no clipping
    narrative_flow: int  # 0-20: pacing + transitions
    accessibility: int  # 0-20: captions + audio descriptions
    technical_specs: int  # 0-20: codec + bitrate + fps

    def __post_init__(self):
        for component_name in ['visual_clarity', 'audio_quality', 'narrative_flow',
                               'accessibility', 'technical_specs']:
            component_value = getattr(self, component_name)
            if not (0 <= component_value <= 20):
                raise ValueError(f"{component_name} must be 0-20, got {component_value}")

    @property
    def total(self) -> int:
        """Total score (0-100)."""
        return (self.visual_clarity + self.audio_quality +
                self.narrative_flow + self.accessibility +
                self.technical_specs)


@dataclass
class VideoFile:
    """Generated video file."""
    path: str
    duration_ms: int
    width: int
    height: int
    fps: float
    codec: str  # "h264", "h265", "vp9"
    bitrate_kbps: int
    file_size_bytes: int
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class VideoJob:
    """Top-level video generation job."""
    id: str
    topic: str
    duration: str  # "1m", "5m", "15m"
    state: GateState = GateState.DRAFT
    quality_score: int = 0
    quality_breakdown: Optional[QualityBreakdown] = None
    video_path: Optional[str] = None
    storyboard: Optional[Storyboard] = None
    slides: List[str] = field(default_factory=list)  # PNG paths
    audio_path: Optional[str] = None
    generation_time_ms: int = 0
    worker_latencies: Dict[str, int] = field(default_factory=dict)
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    @property
    def is_ready_for_broadcast(self) -> bool:
        """Can this video be published to YouTube?"""
        return self.state == GateState.BROADCAST and self.quality_score >= 85


@dataclass
class WorkerError(Exception):
    """Worker failure with fallback information."""
    code: str  # "tts_api_down", "ffmpeg_missing", etc.
    message: str
    can_retry: bool  # Should orchestrator retry this step?
    fallback_worker: Optional[str]  # Name of fallback worker, if any


@dataclass
class DesignSystem:
    """Design system specification (loaded from design_system.json)."""
    colors: Dict[str, str]
    typography: Dict[str, Any]
    layout: Dict[str, int]

    def __post_init__(self):
        """Validate design system."""
        # Verify required colors
        required_colors = ['primary', 'secondary', 'accent', 'text_dark',
                          'text_light', 'bg_light', 'bg_dark']
        for color in required_colors:
            if color not in self.colors:
                raise ValueError(f"Design system missing required color: {color}")

        # Verify required typography
        required_fonts = ['heading_font', 'body_font']
        for font in required_fonts:
            if font not in self.typography:
                raise ValueError(f"Design system missing required font: {font}")

        # Verify layout
        required_layout = ['slide_width', 'slide_height']
        for layout_item in required_layout:
            if layout_item not in self.layout:
                raise ValueError(f"Design system missing required layout: {layout_item}")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DesignSystem':
        """Load design system from JSON dict."""
        return cls(
            colors=data['colors'],
            typography=data['typography'],
            layout=data['layout']
        )
