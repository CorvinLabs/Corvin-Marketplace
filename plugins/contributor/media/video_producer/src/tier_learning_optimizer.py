"""Tier Learning Optimizer — Learn tier preferences from feedback

Implements ADR-0314 learning loop for tier selection:
- Track tier-specific metrics (success, duration, quality feedback)
- Compute tier weights based on quality + speed tradeoff
- Recommend next tier with highest expected value
- Persist learned weights for reproducibility
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class TierWeights:
    """Learned tier selection weights."""
    TIER_1_QUICK: float = 0.25
    TIER_1_5_THREEJS: float = 0.25
    TIER_2_MANIM: float = 0.25
    TIER_3_BLENDER: float = 0.25
    updated_at: str = ""

    def normalize(self):
        """Ensure weights sum to 1.0."""
        tiers = ["TIER_1_QUICK", "TIER_1_5_THREEJS", "TIER_2_MANIM", "TIER_3_BLENDER"]
        values = [getattr(self, tier) for tier in tiers]
        total = sum(values)
        if total <= 0:
            # Reset to uniform if broken
            for tier in tiers:
                setattr(self, tier, 0.25)
        else:
            for tier in tiers:
                current = getattr(self, tier)
                setattr(self, tier, max(0.1, min(0.9, current / total)))

    def to_dict(self) -> Dict[str, float]:
        """Convert to dict for JSON serialization."""
        return {
            "TIER_1_QUICK": self.TIER_1_QUICK,
            "TIER_1_5_THREEJS": self.TIER_1_5_THREEJS,
            "TIER_2_MANIM": self.TIER_2_MANIM,
            "TIER_3_BLENDER": self.TIER_3_BLENDER,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "TierWeights":
        """Create from dict."""
        return cls(
            TIER_1_QUICK=d.get("TIER_1_QUICK", 0.25),
            TIER_1_5_THREEJS=d.get("TIER_1_5_THREEJS", 0.25),
            TIER_2_MANIM=d.get("TIER_2_MANIM", 0.25),
            TIER_3_BLENDER=d.get("TIER_3_BLENDER", 0.25),
            updated_at=d.get("updated_at", ""),
        )


class TierLearningOptimizer:
    """Learn tier preferences from execution + feedback events."""

    def __init__(self, event_store, config_path: str = "~/.corvin/video-producer/tier-weights.json"):
        self.event_store = event_store
        self.config_path = Path(config_path).expanduser()
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.weights: TierWeights = self._load_weights()

    def optimize_tier_selection(self, tenant_id: str):
        """Update tier weights based on recent feedback and metrics.

        Weights are computed as:
            score = (success_rate * 0.4) +
                   (1 - normalized_duration * 0.3) +
                   (quality_score / 100 * 0.3)
        """
        tiers = ["TIER_1_QUICK", "TIER_1_5_THREEJS", "TIER_2_MANIM", "TIER_3_BLENDER"]
        metrics = self.event_store.get_all_metrics(tenant_id)

        # Compute scores for each tier
        scores = {}
        for tier in tiers:
            tier_metrics = metrics.get(tier, {})

            # Handle case where no data exists yet
            if tier_metrics.get("count", 0) == 0:
                scores[tier] = 0.25  # Uniform default
                continue

            success_rate = tier_metrics.get("success_rate", 0.0)
            avg_duration_ms = tier_metrics.get("avg_duration_ms", 0)
            avg_quality = tier_metrics.get("avg_quality", 50)

            # Normalize duration (assume 60s = 60000ms is max acceptable)
            max_duration_ms = 60000
            duration_factor = min(1.0, avg_duration_ms / max_duration_ms)
            speed_score = 1.0 - duration_factor

            # Compute weighted score
            score = (
                success_rate * 0.4 +  # 40% weight on reliability
                speed_score * 0.3 +   # 30% weight on speed
                (avg_quality / 100.0) * 0.3  # 30% weight on quality
            )

            scores[tier] = max(0.1, min(0.9, score))  # Clamp to [0.1, 0.9]

            logger.info(
                f"Tier {tier}: success={success_rate:.2f}, "
                f"duration={avg_duration_ms:.0f}ms, quality={avg_quality:.0f}, "
                f"score={score:.3f}"
            )

        # Normalize scores to weights
        total = sum(scores.values())
        if total <= 0:
            # All tiers failed, reset to uniform
            for tier in tiers:
                setattr(self.weights, tier, 0.25)
        else:
            for tier in tiers:
                normalized = scores[tier] / total
                setattr(self.weights, tier, max(0.1, min(0.9, normalized)))

        # Persist weights
        self.weights.normalize()
        self._save_weights()

        logger.info(f"Tier weights updated: {self.weights.to_dict()}")

    def recommend_tier(self) -> str:
        """Return tier with highest weight (greedy selection)."""
        tiers = ["TIER_1_QUICK", "TIER_1_5_THREEJS", "TIER_2_MANIM", "TIER_3_BLENDER"]
        weights_dict = self.weights.to_dict()
        return max(tiers, key=lambda t: weights_dict[t])

    def get_tier_distribution(self) -> Dict[str, float]:
        """Get current tier weights as probability distribution."""
        return self.weights.to_dict()

    def _load_weights(self) -> TierWeights:
        """Load saved weights from disk."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                return TierWeights.from_dict(data)
            except Exception as e:
                logger.warning(f"Failed to load tier weights: {e}")

        # Return defaults (uniform distribution)
        return TierWeights()

    def _save_weights(self):
        """Persist weights to disk."""
        try:
            from datetime import datetime
            weights_dict = self.weights.to_dict()
            weights_dict["updated_at"] = datetime.utcnow().isoformat() + "Z"
            with open(self.config_path, "w") as f:
                json.dump(weights_dict, f, indent=2)
            logger.info(f"Tier weights saved to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save tier weights: {e}")
