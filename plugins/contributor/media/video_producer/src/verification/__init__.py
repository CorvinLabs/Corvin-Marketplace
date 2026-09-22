"""Video Content Verification (Tier 1–3) — CONCEPT-0051 Implementation

Three-tier verification system to ensure videos contain real content, not just
well-formed containers with test patterns.

Tier 1: Fast content existence checks (500ms, ~95% accuracy)
Tier 2: Thorough structural analysis (2.5s, ~98% accuracy)
Tier 3: Definitive extraction proof (5s, ~100% accuracy)

Load-bearing invariant: No video is marked "VERIFIED" without passing at least Tier 1.
"""

from .models import AudioVerificationResult, VideoVerificationResult, VerificationMetrics
from .thresholds import AUDIO_TIER1, VIDEO_TIER1
from .audio_inspector_tier1 import AudioContentInspectorTier1
from .video_inspector_tier1 import VideoContentInspectorTier1
from .orchestrator import VerificationOrchestrator

__all__ = [
    "AudioVerificationResult",
    "VideoVerificationResult",
    "VerificationMetrics",
    "AUDIO_TIER1",
    "VIDEO_TIER1",
    "AudioContentInspectorTier1",
    "VideoContentInspectorTier1",
    "VerificationOrchestrator",
]
