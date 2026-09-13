"""AdaptiveEncoderSkill — Scene-adaptive codec & bitrate selection.

Selects codec, resolution, bitrate per scene type based on:
- Scene type (title/narration/screenshot/animation)
- Validation confidence
- Quality preset (youtube/linkedin/archive/presentation)
- Input resolution

Includes fallback mechanism for encoding failures.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional
import yaml
import json

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EncodingProfile:
    """Immutable encoding configuration."""
    codec: str  # "h264" or "h265"
    resolution: str  # "1080p", "1440p", "2160p"
    bitrate: str  # "8000k", "12000k"
    ffmpeg_preset: str  # "fast", "medium", "slow"
    color_profile: str  # "BT.709", "sRGB"
    audio_codec: str  # "aac"
    audio_bitrate: str  # "128k"

    def to_ffmpeg_args(self, input_path: str, output_path: str) -> List[str]:
        """Generate FFmpeg command arguments."""
        # Resolution map
        res_map = {
            "720p": "1280:720",
            "1080p": "1920:1080",
            "1440p": "2560:1440",
            "2160p": "3840:2160",
        }
        scale = res_map.get(self.resolution, "1920:1080")

        # Codec-specific settings
        if self.codec == "h264":
            codec_args = [
                "-c:v", "libx264",
                "-preset", self.ffmpeg_preset,
                "-b:v", self.bitrate,
                "-c:a", self.audio_codec,
                "-b:a", self.audio_bitrate,
            ]
        else:  # h265
            codec_args = [
                "-c:v", "libx265",
                "-preset", self.ffmpeg_preset,
                "-b:v", self.bitrate,
                "-c:a", self.audio_codec,
                "-b:a", self.audio_bitrate,
            ]

        return [
            "-i", input_path,
            "-vf", f"scale={scale}:force_original_aspect_ratio=decrease",
            "-colorspace", self.color_profile,
            "-movflags", "+faststart",
            "-y",
        ] + codec_args + [output_path]


class EncodingPresetsLoader:
    """Load encoding presets from YAML."""

    def __init__(self, presets_path: Optional[str] = None):
        """Load presets from file or use defaults."""
        self.presets = {}
        if presets_path:
            self._load_from_file(presets_path)
        else:
            self._load_defaults()

    def _load_from_file(self, path: str):
        """Load presets from YAML file."""
        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
            self.presets = data.get('encoding_profiles', {})
            logger.info(f"Loaded {len(self.presets)} presets from {path}")
        except Exception as e:
            logger.warning(f"Failed to load presets from {path}: {e}. Using defaults.")
            self._load_defaults()

    def _load_defaults(self):
        """Load default presets."""
        self.presets = {
            "youtube": {
                "codec_priority": ["h264", "h265"],
                "resolution": {"default": "1080p", "range": ["1080p", "1440p"]},
                "bitrate": {"target": "8-12 Mbps", "min": "4 Mbps", "max": "12 Mbps"},
                "ffmpeg_preset": "medium",
                "scene_overrides": {
                    "title": {"bitrate": "4000k", "codec": "h264"},
                    "narration": {"bitrate": "6000k", "codec": "h264"},
                    "screenshot": {"bitrate": "10000k", "codec": "h264"},
                    "animation": {"bitrate": "7000k", "codec": "h265"},
                },
                "audio": {"codec": "aac", "bitrate": "128k"},
                "color_profile": "BT.709",
            },
            "linkedin": {
                "codec_priority": ["h264"],
                "resolution": {"default": "1080p", "range": ["720p", "1080p"]},
                "bitrate": {"target": "8 Mbps", "min": "2 Mbps", "max": "8 Mbps"},
                "ffmpeg_preset": "medium",
                "audio": {"codec": "aac", "bitrate": "128k"},
                "color_profile": "BT.709",
            },
            "archive": {
                "codec_priority": ["h265", "h264"],
                "resolution": {"default": "1440p", "range": ["1440p", "2160p"]},
                "bitrate": {"target": "15-25 Mbps", "min": "8 Mbps", "max": "25 Mbps"},
                "ffmpeg_preset": "slow",
                "scene_overrides": {
                    "title": {"bitrate": "14000k", "codec": "h265"},
                    "screenshot": {"bitrate": "18000k", "codec": "h265"},
                },
                "audio": {"codec": "aac", "bitrate": "192k"},
                "color_profile": "BT.2020",
            },
            "presentation": {
                "codec_priority": ["h264", "h265"],
                "resolution": {"default": "1080p", "range": ["720p", "1080p"]},
                "bitrate": {"target": "4-8 Mbps", "min": "2 Mbps", "max": "8 Mbps"},
                "ffmpeg_preset": "medium",
                "audio": {"codec": "aac", "bitrate": "96k"},
                "color_profile": "sRGB",
            },
        }

    def get_preset(self, name: str) -> Dict:
        """Get preset by name."""
        return self.presets.get(name, self.presets.get("youtube"))


class AdaptiveEncoderSkill:
    """Scene-adaptive codec & bitrate selection."""

    def __init__(self, presets_path: Optional[str] = None):
        self.loader = EncodingPresetsLoader(presets_path)

    def choose_encoding(
        self,
        scene: Dict,
        job_context: Dict,
        validation_result,
        quality_preset: str = "youtube",
    ) -> EncodingProfile:
        """
        Determine encoding parameters for a scene.

        Args:
            scene: Scene metadata (type, description, etc.)
            job_context: Job config (job_id, tenant_id)
            validation_result: AssetValidationResult from input validator
            quality_preset: "youtube", "linkedin", "archive", "presentation"

        Returns:
            EncodingProfile (codec, resolution, bitrate, ffmpeg args)
        """
        preset = self.loader.get_preset(quality_preset)
        scene_type = scene.get("type", "screenshot")
        confidence = getattr(validation_result, "overall_confidence", 0.8)

        # 1. Choose codec
        codec = self._choose_codec(preset, scene_type, confidence)

        # 2. Choose resolution
        resolution = self._choose_resolution(preset, scene_type)

        # 3. Choose bitrate
        bitrate = self._choose_bitrate(preset, scene_type)

        # 4. Choose FFmpeg preset
        ffmpeg_preset = preset.get("ffmpeg_preset", "medium")

        # 5. Audio config
        audio_config = preset.get("audio", {})
        audio_codec = audio_config.get("codec", "aac")
        audio_bitrate = audio_config.get("bitrate", "128k")

        # 6. Color profile
        color_profile = preset.get("color_profile", "BT.709")

        # Log decision
        logger.info(f"Encoding: {scene_type} → {codec}/{resolution}/{bitrate}")

        return EncodingProfile(
            codec=codec,
            resolution=resolution,
            bitrate=bitrate,
            ffmpeg_preset=ffmpeg_preset,
            color_profile=color_profile,
            audio_codec=audio_codec,
            audio_bitrate=audio_bitrate,
        )

    def _choose_codec(self, preset: Dict, scene_type: str, confidence: float) -> str:
        """Choose codec from priority list."""
        # Scene-specific override
        overrides = preset.get("scene_overrides", {})
        if scene_type in overrides and "codec" in overrides[scene_type]:
            return overrides[scene_type]["codec"]

        # Confidence-based fallback
        priority = preset.get("codec_priority", ["h264", "h265"])
        if confidence < 0.7 and "h265" in priority:
            # Low confidence: prefer H.264 (safer)
            return "h264"

        return priority[0] if priority else "h264"

    def _choose_resolution(self, preset: Dict, scene_type: str) -> str:
        """Choose output resolution."""
        res_config = preset.get("resolution", {})
        return res_config.get("default", "1080p")

    def _choose_bitrate(self, preset: Dict, scene_type: str) -> str:
        """Choose bitrate based on scene type."""
        # Scene-specific override
        overrides = preset.get("scene_overrides", {})
        if scene_type in overrides and "bitrate" in overrides[scene_type]:
            br = overrides[scene_type]["bitrate"]
            # Convert "6000k" format if needed
            if isinstance(br, str) and "k" in br:
                return br
            return f"{br}k" if isinstance(br, int) else br

        # Default bitrate for preset
        bitrate_config = preset.get("bitrate", {})
        target = bitrate_config.get("target", "8000k")

        # Parse "8-12 Mbps" format and use middle value
        if isinstance(target, str) and "-" in target:
            parts = target.split("-")
            try:
                min_mbps = int(parts[0].strip().split()[0])
                max_mbps = int(parts[1].strip().split()[0])
                mid = (min_mbps + max_mbps) // 2
                return f"{mid}000k"
            except:
                pass

        # Fallback
        if isinstance(target, str) and "k" in target:
            return target
        return "8000k"


def create_encoder_skill(presets_path: Optional[str] = None) -> AdaptiveEncoderSkill:
    """Factory function to create encoder skill."""
    return AdaptiveEncoderSkill(presets_path)
