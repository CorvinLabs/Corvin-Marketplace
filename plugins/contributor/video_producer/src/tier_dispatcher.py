"""Tier Dispatcher — Unified Tier Selection & Rendering

Manages all 4 tiers of rendering:
- TIER_1_QUICK: Fast, low-quality (Manim basic)
- TIER_1_5_THREEJS: GPU 3D (Three.js + Puppeteer)
- TIER_2_MANIM: Medium quality (Manim + color grading)
- TIER_3_BLENDER: Premium (Blender, non-blocking async)

Implements adaptive tier selection + fallback chain.
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class TierCapabilities:
    """Capabilities for each tier."""
    name: str
    quality_level: int  # 1–5 (low to high)
    estimated_duration_seconds: float  # Per 60s video
    requires_gpu: bool
    requires_blender: bool
    max_duration_seconds: int  # Max supported


# Define tier capabilities
TIER_CAPABILITIES = {
    "TIER_1_QUICK": TierCapabilities(
        name="Quick (Manim basic)",
        quality_level=1,
        estimated_duration_seconds=30,
        requires_gpu=False,
        requires_blender=False,
        max_duration_seconds=120,
    ),
    "TIER_1_5_THREEJS": TierCapabilities(
        name="GPU 3D (Three.js)",
        quality_level=2,
        estimated_duration_seconds=20,
        requires_gpu=True,
        requires_blender=False,
        max_duration_seconds=180,
    ),
    "TIER_2_MANIM": TierCapabilities(
        name="Medium (Manim + grading)",
        quality_level=3,
        estimated_duration_seconds=45,
        requires_gpu=False,
        requires_blender=False,
        max_duration_seconds=300,
    ),
    "TIER_3_BLENDER": TierCapabilities(
        name="Premium (Blender)",
        quality_level=5,
        estimated_duration_seconds=90,
        requires_gpu=True,
        requires_blender=True,
        max_duration_seconds=600,
    ),
}


class TierDispatcher:
    """Select and dispatch to appropriate rendering tier."""

    def __init__(
        self,
        learning_optimizer=None,
        threejs_renderer=None,
        blender_executor=None,
    ):
        """Initialize dispatcher with optional renderers.

        Args:
            learning_optimizer: TierLearningOptimizer for adaptive selection
            threejs_renderer: ThreeJSRenderer for Tier 1.5
            blender_executor: BlenderAsyncExecutor for Tier 3
        """
        self.optimizer = learning_optimizer
        self.threejs = threejs_renderer
        self.blender = blender_executor
        self.fallback_chain = [
            "TIER_3_BLENDER",
            "TIER_2_MANIM",
            "TIER_1_5_THREEJS",
            "TIER_1_QUICK",  # Always available (fallback)
        ]

    def select_tier(self, tenant_id: str, preferred_quality: Optional[int] = None) -> str:
        """Select best tier for this render.

        Args:
            tenant_id: Tenant ID for learning metrics
            preferred_quality: Desired quality (1–5), or None for optimizer default

        Returns: Selected tier ("TIER_1_QUICK", "TIER_1_5_THREEJS", "TIER_2_MANIM", "TIER_3_BLENDER")
        """
        # If preferred quality specified, find lowest-cost tier meeting it
        if preferred_quality:
            for tier, caps in TIER_CAPABILITIES.items():
                if caps.quality_level >= preferred_quality and self._is_tier_available(tier):
                    return tier
            # Fallback to highest available quality
            for tier in reversed(self.fallback_chain):
                if self._is_tier_available(tier):
                    return tier

        # Use learning optimizer if available
        if self.optimizer:
            recommended = self.optimizer.recommend_tier()
            if self._is_tier_available(recommended):
                return recommended

        # Default: use TIER_2_MANIM if available, else fall back
        if self._is_tier_available("TIER_2_MANIM"):
            return "TIER_2_MANIM"

        # Fallback chain
        for tier in self.fallback_chain:
            if self._is_tier_available(tier):
                logger.info(f"Tier {tier} selected (fallback)")
                return tier

        # Should never happen
        logger.error("No tiers available; defaulting to TIER_1_QUICK")
        return "TIER_1_QUICK"

    def dispatch(self, tier: str, request: Dict) -> Optional[Dict]:
        """Dispatch render request to selected tier.

        Args:
            tier: Selected tier
            request: Render request dict

        Returns: Result dict with video_file, success, etc. or None
        """
        logger.info(f"Dispatching to {tier}")

        try:
            if tier == "TIER_1_QUICK":
                return self._dispatch_tier1_quick(request)
            elif tier == "TIER_1_5_THREEJS":
                return self._dispatch_tier1_5_threejs(request)
            elif tier == "TIER_2_MANIM":
                return self._dispatch_tier2_manim(request)
            elif tier == "TIER_3_BLENDER":
                return self._dispatch_tier3_blender(request)
            else:
                logger.error(f"Unknown tier: {tier}")
                return None

        except Exception as e:
            logger.error(f"Dispatch failed for {tier}: {e}")
            # Try next tier in fallback chain
            current_idx = self.fallback_chain.index(tier)
            if current_idx < len(self.fallback_chain) - 1:
                next_tier = self.fallback_chain[current_idx + 1]
                logger.info(f"Trying fallback tier: {next_tier}")
                return self.dispatch(next_tier, request)
            return None

    def _dispatch_tier1_quick(self, request: Dict) -> Optional[Dict]:
        """Dispatch to Tier 1 (Manim basic)."""
        # Placeholder: would call actual Manim renderer
        logger.info("Tier 1 (quick) rendering")
        return {
            "tier": "TIER_1_QUICK",
            "video_file": "/tmp/tier1_output.mp4",
            "duration_seconds": request.get("duration_seconds", 60),
            "success": True,
        }

    def _dispatch_tier1_5_threejs(self, request: Dict) -> Optional[Dict]:
        """Dispatch to Tier 1.5 (Three.js GPU)."""
        if not self.threejs:
            logger.warning("Three.js renderer not available")
            return None

        from .threejs_renderer import ThreeJSRenderRequest

        render_request = ThreeJSRenderRequest(
            scene_name=request.get("scene_name", "maestro-3d"),
            duration_seconds=request.get("duration_seconds", 10),
        )

        result = self.threejs.render(render_request)

        return {
            "tier": "TIER_1_5_THREEJS",
            "video_file": str(result.video_file) if result.video_file else None,
            "duration_seconds": result.duration_seconds,
            "success": result.success,
            "error": result.error,
        }

    def _dispatch_tier2_manim(self, request: Dict) -> Optional[Dict]:
        """Dispatch to Tier 2 (Manim with color grading)."""
        # Placeholder: would call actual Manim + grading pipeline
        logger.info("Tier 2 (Manim) rendering")
        return {
            "tier": "TIER_2_MANIM",
            "video_file": "/tmp/tier2_output.mp4",
            "duration_seconds": request.get("duration_seconds", 60),
            "success": True,
        }

    def _dispatch_tier3_blender(self, request: Dict) -> Optional[Dict]:
        """Dispatch to Tier 3 (Blender async)."""
        if not self.blender:
            logger.warning("Blender executor not available")
            return None

        job_id = self.blender.submit_job(
            blend_file=request.get("blend_file", ""),
            output_path=request.get("output_path", "/tmp/blender_output.mp4"),
            scene_name=request.get("scene_name", "default"),
        )

        if not job_id:
            logger.warning("Blender job submission failed; checking for downgrade")
            downgrade = self.blender.auto_downgrade()
            if downgrade:
                logger.info("Downgrading to Tier 2 due to Blender unavailability")
                return self._dispatch_tier2_manim(request)
            return None

        # Return async job info
        return {
            "tier": "TIER_3_BLENDER",
            "job_id": job_id,
            "async": True,
            "poll_endpoint": f"/api/v1/video-producer/blender-job/{job_id}",
        }

    def _is_tier_available(self, tier: str) -> bool:
        """Check if tier is available (dependencies met)."""
        # Placeholder: real implementation would check GPU availability, Blender installation, etc.
        if tier == "TIER_1_QUICK":
            return True  # Always available
        elif tier == "TIER_1_5_THREEJS":
            return self.threejs is not None
        elif tier == "TIER_2_MANIM":
            return True  # Assume Manim installed
        elif tier == "TIER_3_BLENDER":
            return self.blender is not None and self.blender._is_blender_healthy()
        return False

    def get_tier_stats(self, tenant_id: str) -> Dict:
        """Get stats for all tiers."""
        if not self.optimizer:
            return {}

        return {
            "tier_weights": self.optimizer.get_tier_distribution(),
            "tier_capabilities": {
                tier: {
                    "name": caps.name,
                    "quality_level": caps.quality_level,
                    "estimated_duration_seconds": caps.estimated_duration_seconds,
                    "available": self._is_tier_available(tier),
                }
                for tier, caps in TIER_CAPABILITIES.items()
            },
        }
