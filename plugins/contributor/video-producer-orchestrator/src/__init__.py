"""Video Producer Plugin for CorvinOS."""

__version__ = "1.0.0"
__author__ = "CorvinOS Contributors"
__license__ = "Apache-2.0"

from .models import (
    GateState,
    Scene,
    Storyboard,
    Audio,
    QualityBreakdown,
    VideoFile,
    VideoJob,
    WorkerError,
    DesignSystem,
)
from .quality_gates import QualityGate, QualityGateEnforcer, GateDecision
from .quality_scorer import QualityScorer

__all__ = [
    "GateState",
    "Scene",
    "Storyboard",
    "Audio",
    "QualityBreakdown",
    "VideoFile",
    "VideoJob",
    "WorkerError",
    "DesignSystem",
    "QualityGate",
    "QualityGateEnforcer",
    "GateDecision",
    "QualityScorer",
]
