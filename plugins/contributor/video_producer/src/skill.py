"""TaskOrchestrator Skill — LLM Storyboarding + Skills 2.0 Orchestration."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import uuid

import anthropic

# Support both relative and absolute imports
try:
    from models import VideoJob, Storyboard, Scene, VideoOutput
    from storage import get_storage
except ImportError:
    from .models import VideoJob, Storyboard, Scene, VideoOutput
    from .storage import get_storage

logger = logging.getLogger(__name__)

# Global progress tracking (will be wired to WebSocket in Phase 2.2)
_progress_events = {}


def emit_job_progress(
    job_id: str,
    status: str,
    percent: int,
    message: str = None,
    error: str = None
):
    """Emit job progress event (for WebSocket broadcast)."""
    event = {
        "job_id": job_id,
        "status": status,
        "percent": percent,
        "message": message,
        "error": error,
        "timestamp": datetime.now().isoformat(),
    }
    _progress_events[job_id] = event
    logger.info(f"[{job_id}] {status} {percent}% — {message or ''}")


async def generate_storyboard_with_llm(
    task: str,
    max_duration_minutes: int = 60
) -> Storyboard:
    """
    LLM: Task → Storyboard (JSON)

    Generates a detailed video storyboard from natural language task.
    Enforces constraints: max duration, max 100 scenes, structured format.
    """
    client = anthropic.Anthropic()

    prompt = f"""
You are a video storyboard generator. Given a task, generate a detailed video storyboard as JSON.

Task: {task}
Max Duration: {max_duration_minutes} minutes (~{max_duration_minutes * 60000} ms)

Generate scenes of types: "title", "narration", "screenshot", "animation", "screencast".

CONSTRAINTS (MUST ENFORCE):
- Total duration ≤ {max_duration_minutes * 60000} ms
- Maximum 100 scenes
- Each scene must have: id, kind, duration_ms, narration_text, visual_description
- Narration per scene ≤ 500 characters
- Each scene duration 1000–30000 ms (1–30 seconds)

OUTPUT FORMAT (valid JSON only, no markdown):
{{
  "id": "sb_{uuid.uuid4().hex[:8]}",
  "task": "{task}",
  "scenes": [
    {{
      "id": "s1",
      "kind": "title",
      "duration_ms": 3000,
      "narration_text": "Welcome to Corvin",
      "visual_description": "Corvin logo on dark background"
    }},
    ...
  ]
}}

RETURN ONLY THE JSON, NO EXPLANATIONS.
"""

    message = client.messages.create(
        model="claude-opus-5",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        storyboard_json = json.loads(message.content[0].text)

        # Validate storyboard
        if not storyboard_json.get("scenes"):
            raise ValueError("No scenes in storyboard")

        if len(storyboard_json["scenes"]) > 100:
            raise ValueError(f"Too many scenes: {len(storyboard_json['scenes'])} > 100")

        total_duration = sum(s.get("duration_ms", 0) for s in storyboard_json["scenes"])
        max_ms = max_duration_minutes * 60000
        if total_duration > max_ms:
            raise ValueError(f"Storyboard too long: {total_duration}ms > {max_ms}ms")

        # Create Storyboard object
        scenes = [Scene(**s) for s in storyboard_json["scenes"]]
        return Storyboard(
            id=storyboard_json.get("id", f"sb_{uuid.uuid4().hex[:8]}"),
            task=task,
            scenes=scenes,
            generated_at=datetime.now()
        )

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM storyboard: {e}")
        raise ValueError(f"Invalid JSON from LLM: {e}")


async def orchestrate_video(
    job_id: str,
    task: str,
    output_folder: str = None,
    tts_engine: str = "azure",
    max_duration_minutes: int = 60
) -> Dict[str, Any]:
    """
    Main orchestrator Skill:
    1. LLM: Task → Storyboard (JSON)
    2. Skills orchestration: call workers in sequence
    3. Collect feedback → Learning (ADR-0314)
    4. Return VideoOutput
    """

    storage = get_storage()
    job = storage.get_job(job_id)

    if not job:
        raise ValueError(f"Job {job_id} not found")

    if output_folder is None:
        output_folder = "~/.corvin/video-producer/videos"

    try:
        # Step 1: Generate Storyboard via LLM
        emit_job_progress(job_id, "storyboard_generating", 0, "Analyzing task...")

        storyboard = await generate_storyboard_with_llm(task, max_duration_minutes)
        job.storyboard = storyboard
        job.status = "storyboard_generating"
        storage.save_job(job)

        emit_job_progress(
            job_id,
            "storyboard_generating",
            50,
            f"Generated {len(storyboard.scenes)} scenes"
        )

        # Emit feedback: storyboard generated
        emit_feedback(
            job_id=job_id,
            event_type="storyboard_generated",
            metrics={
                "scenes_count": len(storyboard.scenes),
                "total_duration_ms": sum(s.duration_ms for s in storyboard.scenes),
                "quality_score": 0.8,
            }
        )

        emit_job_progress(job_id, "storyboard_generating", 100, "Storyboard ready")

        # Step 2: Orchestrate Skills 2.0 (Phase 2.3 — skill integration)
        # NOTE: Phase 2.3 will wire actual skill calls here
        # For Phase 2.1, we mock the skills

        emit_job_progress(job_id, "skills_running", 0, "Starting skill orchestration...")
        job.status = "skills_running"
        storage.save_job(job)

        results = {}

        # Mock: Voice Synthesizer
        emit_job_progress(job_id, "skills_running", 33, "Synthesizing voice...")
        results["voice"] = {
            "voice_dir": f"{output_folder}/{job_id}/voice",
            "timings_path": f"{output_folder}/{job_id}/timings.json",
        }

        # Mock: Screenshot Capturer (optional)
        if has_screenshot_scenes(storyboard):
            emit_job_progress(job_id, "skills_running", 66, "Capturing screenshots...")
            results["screenshots"] = {
                "screenshots_dir": f"{output_folder}/{job_id}/screenshots",
            }

        # Mock: Video Assembler
        emit_job_progress(job_id, "skills_running", 85, "Assembling video...")
        results["video"] = {
            "video_path": f"{output_folder}/{job_id}/output.mp4",
            "srt_path": f"{output_folder}/{job_id}/output.srt",
            "duration_seconds": sum(s.duration_ms for s in storyboard.scenes) // 1000,
            "metadata": {
                "resolution": "1920x1080",
                "fps": 30,
                "bitrate_kbps": 6000,
            }
        }

        emit_job_progress(job_id, "skills_running", 100, "Skills complete")

        # Step 3: Emit completion feedback
        emit_feedback(
            job_id=job_id,
            event_type="video_produced",
            metrics={
                "duration_seconds": results["video"]["duration_seconds"],
                "resolution": results["video"]["metadata"]["resolution"],
                "quality_score": 0.85,
            }
        )

        # Step 4: Update job status
        job.status = "complete"
        job.completed_at = datetime.now()
        job.video_output_path = results["video"]["video_path"]
        storage.save_job(job)

        emit_job_progress(job_id, "complete", 100, "Video production complete!")

        return {
            "success": True,
            "job_id": job_id,
            "video_path": results["video"]["video_path"],
            "srt_path": results["video"]["srt_path"],
            "duration_seconds": results["video"]["duration_seconds"],
            "metadata": results["video"]["metadata"],
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{job_id}] Orchestration failed: {error_msg}", exc_info=True)

        job.status = "error"
        job.error_message = error_msg
        job.completed_at = datetime.now()
        storage.save_job(job)

        emit_job_progress(job_id, "error", 100, error=error_msg)

        # Emit failure feedback
        emit_feedback(
            job_id=job_id,
            event_type="orchestration_failed",
            metrics={
                "error": error_msg,
            }
        )

        raise


def has_screenshot_scenes(storyboard: Storyboard) -> bool:
    """Check if storyboard has screenshot or screencast scenes."""
    return any(s.kind in ["screenshot", "screencast"] for s in storyboard.scenes)


def emit_feedback(
    job_id: str,
    event_type: str,
    metrics: Dict[str, Any]
):
    """
    Emit learning feedback for optimizer tuning (ADR-0314).

    Phase 2.2: Wire to corvin_learning.emit_feedback()
    """
    event = {
        "job_id": job_id,
        "event_type": event_type,
        "metrics": metrics,
        "timestamp": datetime.now().isoformat(),
    }
    logger.info(f"[{job_id}] Feedback: {event_type} | {metrics}")
    # TODO: emit_skill_feedback(
    #     skill_id="os.video_producer_task_orchestrator",
    #     event_type=event_type,
    #     metrics=metrics
    # )


# Async orchestrator wrapper
async def start_video_production(
    job_id: str,
    task: str,
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """Wrapper for async orchestration."""
    return await orchestrate_video(
        job_id=job_id,
        task=task,
        output_folder=config.get("output_folder"),
        tts_engine=config.get("tts_engine", "azure"),
        max_duration_minutes=config.get("max_duration_minutes", 60),
    )
