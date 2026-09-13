"""Quality Enhancement Pipeline — orchestrates all validators & encoders."""

import logging
from typing import Dict, Any, Optional
import asyncio

from .input_validator import InputValidatorSkill, AssetValidationResult
from .encoder import AdaptiveEncoderSkill, EncodingProfile
from .color_processor import ColorProcessorSkill, ColorProcessingResult

logger = logging.getLogger(__name__)


class VideoQualityPipeline:
    """Orchestrates input validation → encoding → color processing."""

    def __init__(self, audit_backend=None, presets_path: Optional[str] = None):
        self.validator = InputValidatorSkill(audit_backend)
        self.encoder = AdaptiveEncoderSkill(presets_path)
        self.color_processor = ColorProcessorSkill()
        self.audit_backend = audit_backend

    async def process_scene(
        self,
        asset_path: str,
        scene: Dict[str, Any],
        job_context: Dict[str, Any],
        quality_preset: str = "youtube",
    ) -> Dict[str, Any]:
        """
        Process a scene through the full quality pipeline.

        Returns:
            {
                "validation": AssetValidationResult,
                "encoding": EncodingProfile,
                "color": ColorProcessingResult,
                "status": "success" | "fail",
            }
        """
        logger.info(f"Processing scene {scene.get('id')} through quality pipeline")

        try:
            # 1. Input Validation
            logger.debug("Running input validation...")
            validation = await self.validator.validate_asset(
                asset_path,
                scene,
                job_context,
            )

            if validation.status == "fail":
                logger.warning(f"Scene {scene.get('id')} failed validation: {validation.fallback_action}")
                return {
                    "validation": validation,
                    "status": "fail",
                    "reason": f"Validation failed: {validation.fallback_action}",
                }

            # 2. Color Processing
            logger.debug("Running color processing...")
            color = await self.color_processor.process_scene_colors(
                asset_path,
                scene,
                {"working_space": "sRGB"},
            )

            if color.status == "fail":
                logger.warning(f"Color processing failed for scene {scene.get('id')}")
                # Don't fail on color warning in Phase 1

            # 3. Adaptive Encoding
            logger.debug("Choosing encoding parameters...")
            encoding = self.encoder.choose_encoding(
                scene,
                job_context,
                validation,
                quality_preset=quality_preset,
            )

            logger.info(
                f"Scene {scene.get('id')}: "
                f"validation={validation.overall_confidence:.2f}, "
                f"encoding={encoding.codec}/{encoding.resolution}/{encoding.bitrate}"
            )

            return {
                "validation": validation,
                "encoding": encoding,
                "color": color,
                "status": "success",
            }

        except Exception as e:
            logger.error(f"Quality pipeline error for scene {scene.get('id')}: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }

    async def process_job(
        self,
        scenes: list,
        job_context: Dict[str, Any],
        quality_preset: str = "youtube",
    ) -> Dict[str, Any]:
        """
        Process all scenes in a job.

        Returns per-scene results and aggregated metrics.
        """
        logger.info(f"Processing job {job_context.get('job_id')} ({len(scenes)} scenes)")

        results = {
            "job_id": job_context.get("job_id"),
            "scenes": [],
            "aggregate": {
                "total_scenes": len(scenes),
                "passed_validation": 0,
                "warned_validation": 0,
                "failed_validation": 0,
                "avg_confidence": 0.0,
            }
        }

        confidences = []

        for scene in scenes:
            asset_path = scene.get("asset_path") or scene.get("path")

            result = await self.process_scene(
                asset_path,
                scene,
                job_context,
                quality_preset,
            )

            results["scenes"].append({
                "scene_id": scene.get("id"),
                "result": result,
            })

            # Aggregate validation stats
            if result.get("status") == "success":
                val = result.get("validation")
                if val:
                    if val.status == "pass":
                        results["aggregate"]["passed_validation"] += 1
                    elif val.status == "warn":
                        results["aggregate"]["warned_validation"] += 1
                    confidences.append(val.overall_confidence)
            else:
                results["aggregate"]["failed_validation"] += 1

        if confidences:
            results["aggregate"]["avg_confidence"] = sum(confidences) / len(confidences)

        logger.info(
            f"Job {job_context.get('job_id')} complete: "
            f"{results['aggregate']['passed_validation']}/{len(scenes)} passed, "
            f"avg confidence {results['aggregate']['avg_confidence']:.2f}"
        )

        return results
