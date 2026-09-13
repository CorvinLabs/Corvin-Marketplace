"""VideoQualityOptimizer — Learn from feedback, tune encoding parameters."""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List
import json
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class OptimizerConfig:
    """Learned encoding parameters."""
    scene_type: str
    bitrate_multiplier: float = 1.0  # 0.8–1.2x baseline
    codec: str = "h264"  # "h264" or "h265"
    grading_strength: float = 1.0  # 0.8–1.2x
    validation_strictness: int = 5  # 0–10
    applied_at: str = ""
    job_ids_trained_on: List[str] = field(default_factory=list)


class VideoQualityOptimizer:
    """Learns from feedback, tunes encoding parameters."""

    def __init__(self, config_path: str = "~/.corvin/video-producer/optimizer-config.json"):
        self.config_path = Path(config_path).expanduser()
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.configs: Dict[str, OptimizerConfig] = self._load_configs()

    async def optimize(
        self,
        job_id: str,
        tenant_id: str,
        feedback_list: List[Dict[str, Any]] = None,
    ) -> Dict[str, OptimizerConfig]:
        """
        Optimize parameters based on feedback.

        Returns: updated configs per scene type
        """
        logger.info(f"Optimizer running for job {job_id}")

        if not feedback_list:
            feedback_list = []

        # Map feedback to loss signals
        loss_signals = self._compute_loss(feedback_list)

        # Update parameters
        updated = {}
        for scene_type, loss in loss_signals.items():
            config = self.configs.get(scene_type, self._default_config(scene_type))

            # Adjust based on feedback
            if "too_blurry" in feedback_list:
                config.bitrate_multiplier = min(1.2, config.bitrate_multiplier + 0.1)

            if "too_compressed" in feedback_list:
                config.codec = "h265"  # Try H.265 for better compression

            if "color_wrong" in feedback_list:
                config.grading_strength = min(1.2, config.grading_strength + 0.1)

            if "approved" in feedback_list:
                config.bitrate_multiplier = max(0.8, config.bitrate_multiplier - 0.05)

            config.job_ids_trained_on.append(job_id)
            self.configs[scene_type] = config
            updated[scene_type] = config

            logger.info(
                f"Updated {scene_type}: "
                f"bitrate_multiplier={config.bitrate_multiplier:.2f}, "
                f"codec={config.codec}"
            )

        # Save to disk
        self._save_configs()

        return updated

    def _compute_loss(self, feedback_list: List[Dict[str, Any]]) -> Dict[str, float]:
        """Compute loss signal from feedback."""
        loss = {}

        # Map feedback types to loss values (0–1, lower is better)
        loss_map = {
            "approved": 0.1,  # Good quality
            "too_blurry": 0.7,  # Bad quality
            "too_compressed": 0.6,  # Bad quality
            "color_wrong": 0.5,  # Medium issue
            "hallucination": 0.8,  # Very bad
        }

        for fb in feedback_list:
            fb_type = fb.get("feedback_type", "unknown")
            if fb_type in loss_map:
                loss[fb_type] = loss_map[fb_type]

        return loss

    def get_config(self, scene_type: str) -> OptimizerConfig:
        """Get current config for scene type."""
        return self.configs.get(scene_type, self._default_config(scene_type))

    def _default_config(self, scene_type: str) -> OptimizerConfig:
        """Get default config for scene type."""
        defaults = {
            "title": OptimizerConfig(
                scene_type="title",
                bitrate_multiplier=0.8,
                codec="h264",
            ),
            "narration": OptimizerConfig(
                scene_type="narration",
                bitrate_multiplier=1.0,
                codec="h264",
            ),
            "screenshot": OptimizerConfig(
                scene_type="screenshot",
                bitrate_multiplier=1.2,
                codec="h264",
            ),
            "animation": OptimizerConfig(
                scene_type="animation",
                bitrate_multiplier=0.9,
                codec="h265",
            ),
        }
        return defaults.get(scene_type, OptimizerConfig(scene_type=scene_type))

    def _load_configs(self) -> Dict[str, OptimizerConfig]:
        """Load saved configs from disk."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                return {
                    k: OptimizerConfig(**v) for k, v in data.items()
                }
            except Exception as e:
                logger.warning(f"Failed to load optimizer config: {e}")

        # Return defaults
        return {
            scene_type: self._default_config(scene_type)
            for scene_type in ["title", "narration", "screenshot", "animation"]
        }

    def _save_configs(self):
        """Save configs to disk."""
        try:
            data = {
                k: {
                    "scene_type": v.scene_type,
                    "bitrate_multiplier": v.bitrate_multiplier,
                    "codec": v.codec,
                    "grading_strength": v.grading_strength,
                    "validation_strictness": v.validation_strictness,
                    "job_ids_trained_on": v.job_ids_trained_on,
                }
                for k, v in self.configs.items()
            }
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Optimizer config saved to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save optimizer config: {e}")
