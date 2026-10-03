"""TaskOrchestrator Skill — LLM Storyboarding + real audio/video assembly."""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import uuid

import anthropic
import requests

# No .env loading here: this module runs inside the host's shared console
# process, and a dotenv load would put every token in the host's .env into
# the environment of every tenant's request and every subprocess. Credentials
# reach this plugin only through the host's own service environment.

try:
    from .models import VideoJob, Storyboard, Scene, VideoOutput
    from .storage import get_storage, TERMINAL_STATUSES
except ImportError:  # standalone script use (no package context)
    from models import VideoJob, Storyboard, Scene, VideoOutput
    from storage import get_storage, TERMINAL_STATUSES

logger = logging.getLogger(__name__)

def emit_job_progress(
    job_id: str,
    status: str,
    percent: int,
    message: str = None,
    error: str = None
):
    """Log a progress step (the persisted VideoJob is the source of truth the UI polls)."""
    logger.info("[%s] %s %s%% — %s", job_id, status, percent, message or "")


def _update_job_progress(
    storage,
    job: VideoJob,
    status: str,
    percent: int,
    message: str = None,
    current_scene: int = None,
    total_scenes: int = None,
):
    """Persist progress onto the VideoJob so the console panel can poll real state."""
    job.status = status
    job.percent = percent
    job.current_step = message
    if current_scene is not None:
        job.current_scene = current_scene
    if total_scenes is not None:
        job.total_scenes = total_scenes
    storage.save_job(job)
    emit_job_progress(job.id, status, percent, message)


_OLLAMA_URL = "http://localhost:11434/api/generate"
# Small model: this host runs Ollama on CPU only (no GPU) — qwen2.5:14b took
# >90s per call in testing, qwen3:1.7b returns a usable storyboard in ~11s.
_OLLAMA_MODEL = "qwen3:1.7b"


def _call_storyboard_llm(prompt: str, backend: str = "ollama", model: Optional[str] = None) -> str:
    """
    Call an LLM to turn the prompt into a storyboard JSON string.

    ``backend`` is decided by the HOST, which ran its data-flow / egress gates
    for exactly that destination before starting the job: "anthropic" (needs
    ``model``) or "ollama" (local). The plugin never upgrades a job to a
    remote backend on its own. An "anthropic" call that fails falls back to
    the local Ollama instance (strictly less egress). Both paths are real
    inference — no mocked/fabricated storyboard content.
    """
    if backend not in ("anthropic", "ollama"):
        raise ValueError(f"unknown storyboard backend {backend!r}")
    if backend == "anthropic":
        if not model:
            raise ValueError("storyboard backend 'anthropic' needs a model id from the host")
        try:
            client = anthropic.Anthropic()
            message = client.messages.create(
                model=model,
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except Exception as e:  # noqa: BLE001
            logger.warning("Anthropic storyboard call failed (%s), falling back to local Ollama", type(e).__name__)

    response = requests.post(
        _OLLAMA_URL,
        json={
            "model": _OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        },
        timeout=180,
    )
    response.raise_for_status()
    return response.json()["response"]


async def generate_storyboard_with_llm(
    task: str,
    max_duration_minutes: int = 60,
    backend: str = "ollama",
    model: Optional[str] = None,
) -> Storyboard:
    """
    LLM: Task → Storyboard (JSON)

    Generates a detailed video storyboard from natural language task.
    Enforces constraints: max duration, max 100 scenes, structured format.
    """
    # A hard ceiling of 100 exists for the API contract, but the *requested* count
    # stays small and duration-independent: max_duration_minutes is a ceiling the
    # storyboard must not exceed, not a target, and the local Ollama CPU fallback
    # (no GPU on this host) needs a small scene count to finish in reasonable time.
    max_scenes = min(100, 6)

    prompt = f"""
You are a video storyboard generator. Given a task, generate a detailed video storyboard as JSON.

Task: {task}
Max Duration: {max_duration_minutes} minutes (~{max_duration_minutes * 60000} ms)

Generate scenes of types: "title", "narration", "screenshot", "animation", "screencast".

CONSTRAINTS (MUST ENFORCE):
- Total duration ≤ {max_duration_minutes * 60000} ms
- Maximum {max_scenes} scenes
- Each scene must have: id, kind, duration_ms, narration_text, visual_description
- Narration per scene ≤ 500 characters
- Each scene duration 1000–30000 ms (1–30 seconds)
- Write narration_text in the SAME language as the Task above.

OUTPUT FORMAT (valid JSON only, no markdown):
{{
  "id": "sb_{uuid.uuid4().hex[:8]}",
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

    raw = _call_storyboard_llm(prompt, backend=backend, model=model)

    try:
        raw = raw.strip()
        # Tolerate an LLM wrapping the JSON in a ```json fence despite instructions.
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        storyboard_json = json.loads(raw)

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


# --------------------------------------------------------------------------
# Real audio/image/video pipeline (ffmpeg + gTTS — no external API keys)
# --------------------------------------------------------------------------

def _detect_lang(text: str) -> str:
    """Cheap heuristic: German diacritics/words → 'de', else 'en'."""
    german_markers = "äöüÄÖÜßÜ"
    german_words = (" der ", " die ", " das ", " und ", " ist ", " für ", " ein ", " eine ")
    padded = f" {text} "
    if any(ch in text for ch in german_markers) or any(w in padded for w in german_words):
        return "de"
    return "en"


def _synthesize_narration(text: str, out_path: Path, lang: str) -> None:
    """Real TTS via gTTS (Google Translate public endpoint, no API key required)."""
    from gtts import gTTS

    text = (text or "").strip() or "..."
    tts = gTTS(text=text, lang=lang)
    tts.save(str(out_path))


def _ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def _wrap_text(text: str, width: int = 46) -> List[str]:
    words = (text or "").split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:8]  # cap to keep the slide readable


_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _render_slide_image(scene: Scene, out_path: Path, w: int = 1280, h: int = 720) -> None:
    """
    Render a real 1280x720 PNG slide via Pillow (this ffmpeg static build ships
    without the drawtext filter — confirmed via `ffmpeg -filters`).
    """
    from PIL import Image, ImageDraw, ImageFont

    kind_label = {
        "title": "TITLE",
        "narration": "NARRATION",
        "screenshot": "SCREENSHOT (placeholder — no live capture in this pipeline yet)",
        "screencast": "SCREENCAST (placeholder — no live capture in this pipeline yet)",
        "animation": "ANIMATION (placeholder)",
    }.get(scene.kind, scene.kind.upper())

    body_source = scene.visual_description if scene.kind in ("screenshot", "screencast", "animation") else scene.narration_text
    body_lines = _wrap_text(body_source or scene.narration_text or "")

    bg_color = (29, 42, 68) if scene.kind == "title" else (20, 20, 28)
    img = Image.new("RGB", (w, h), color=bg_color)
    draw = ImageDraw.Draw(img)

    title_font = ImageFont.truetype(_FONT_BOLD_PATH, 40)
    body_font = ImageFont.truetype(_FONT_PATH, 30)

    def centered_x(text: str, font: "ImageFont.FreeTypeFont") -> int:
        bbox = draw.textbbox((0, 0), text, font=font)
        return (w - (bbox[2] - bbox[0])) // 2

    draw.text((centered_x(kind_label, title_font), 90), kind_label, font=title_font, fill=(138, 180, 255))

    line_height = 42
    total_height = line_height * len(body_lines)
    y = (h - total_height) // 2
    for line in body_lines:
        draw.text((centered_x(line, body_font), y), line, font=body_font, fill=(255, 255, 255))
        y += line_height

    img.save(out_path)


def _assemble_scene_clip(image_path: Path, audio_path: Path, out_path: Path) -> None:
    """Combine one still image + narration audio into a scene mp4 (real ffmpeg encode).

    CRF 18 + preset slow adopted from video_ffmpeg.py (ADR-0953 Phase B review) — the
    only piece of that dead cluster worth keeping; its PNG-sequence+single-audio-track
    architecture was not (this function's per-scene-clip-then-concat design handles
    variable per-scene durations, which a single shared audio track cannot)."""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-i", str(audio_path),
        "-c:v", "libx264", "-tune", "stillimage", "-crf", "18", "-preset", "slow",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        "-shortest", "-vf", "fps=30",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)


def _concat_clips(clip_paths: List[Path], out_path: Path, work_dir: Path) -> None:
    """Concat pre-encoded scene clips (same codec/params) via ffmpeg's concat demuxer."""
    filelist = work_dir / "concat.txt"
    with open(filelist, "w") as f:
        for p in clip_paths:
            path = str(p.resolve())
            if "\n" in path or "\r" in path:
                raise ValueError("clip path contains a line break")
            quoted = path.replace("'", "'\\''")
            f.write(f"file '{quoted}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(filelist),
        "-c", "copy", str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)


def _format_srt_timestamp(seconds: float) -> str:
    ms_total = max(0, round(seconds * 1000))
    h, rem = divmod(ms_total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _generate_srt(scenes_with_durations: List[Dict[str, Any]], out_path: Path) -> None:
    lines = []
    cursor = 0.0
    for i, entry in enumerate(scenes_with_durations, start=1):
        start = cursor
        end = cursor + entry["duration_s"]
        text = entry["narration_text"] or ""
        lines.append(str(i))
        lines.append(f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}")
        lines.append(text)
        lines.append("")
        cursor = end
    out_path.write_text("\n".join(lines), encoding="utf-8")


def has_screenshot_scenes(storyboard: Storyboard) -> bool:
    """Check if storyboard has screenshot or screencast scenes."""
    return any(s.kind in ["screenshot", "screencast"] for s in storyboard.scenes)


def emit_feedback(job_id: str, event_type: str, metrics: Dict[str, Any]):
    """Emit learning feedback for optimizer tuning (ADR-0314). Phase 2.2: wire to corvin_learning."""
    event = {
        "job_id": job_id,
        "event_type": event_type,
        "metrics": metrics,
        "timestamp": datetime.now().isoformat(),
    }
    logger.info(f"[{job_id}] Feedback: {event_type} | {metrics}")


SUPPORTED_TTS_ENGINES = ("gtts",)


async def orchestrate_video(
    job_id: str,
    task: str,
    storage_base: str,
    tts_engine: str = "gtts",
    max_duration_minutes: int = 60,
    storyboard_backend: str = "ollama",
    storyboard_model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main orchestrator Skill:
    1. LLM: Task → Storyboard (JSON)
    2. Real synthesis per scene: TTS narration (gTTS) + slide image (ffmpeg drawtext) + scene clip
    3. Real ffmpeg concat → final MP4 + SRT captions
    4. Collect feedback → Learning (ADR-0314)
    """
    storage = get_storage(storage_base)
    job = storage.get_job(job_id)
    if not job:
        # Nothing to persist an error onto: the host created the job before
        # scheduling it, so this is a host/plugin contract violation.
        raise ValueError(f"Job {job_id} not found")
    if job.status in TERMINAL_STATUSES:
        raise ValueError(f"Job {job_id} is already {job.status}")

    job.started_at = job.started_at or datetime.now()

    # Everything that can fail — including setup — runs inside the try, so the
    # stored job (what the UI polls) always ends in "error" on failure instead
    # of staying "pending" forever.
    try:
        if tts_engine not in SUPPORTED_TTS_ENGINES:
            raise ValueError(f"TTS engine {tts_engine!r} is not available (supported: {', '.join(SUPPORTED_TTS_ENGINES)})")
        if not isinstance(max_duration_minutes, int) or not 1 <= max_duration_minutes <= 60:
            raise ValueError("max_duration_minutes must be an integer between 1 and 60")
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg binary not found on PATH — required for real video assembly")

        # Output always lives in this store's own directory — the host cannot
        # be talked into writing a tenant's video anywhere else.
        out_root = storage.videos_dir / job_id
        scenes_dir = out_root / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Generate Storyboard via LLM
        _update_job_progress(storage, job, "storyboard_generating", 0, "Analyzing task...")

        storyboard = await generate_storyboard_with_llm(
            task, max_duration_minutes, backend=storyboard_backend, model=storyboard_model,
        )
        job.storyboard = storyboard
        _update_job_progress(
            storage, job, "storyboard_generating", 100,
            f"Generated {len(storyboard.scenes)} scenes",
            total_scenes=len(storyboard.scenes),
        )

        emit_feedback(
            job_id=job_id,
            event_type="storyboard_generated",
            metrics={
                "scenes_count": len(storyboard.scenes),
                "total_duration_ms": sum(s.duration_ms for s in storyboard.scenes),
                "quality_score": 0.8,
            }
        )

        # Step 2: Real per-scene synthesis (audio + slide + clip)
        _update_job_progress(storage, job, "skills_running", 0, "Starting scene production...")

        total = len(storyboard.scenes)
        clip_paths: List[Path] = []
        srt_entries: List[Dict[str, Any]] = []

        for i, scene in enumerate(storyboard.scenes, start=1):
            pct = int(((i - 1) / total) * 90)  # 0..90% spans scene production
            _update_job_progress(
                storage, job, "skills_running", pct,
                f"Scene {i}/{total}: synthesizing narration...",
                current_scene=i, total_scenes=total,
            )

            audio_path = scenes_dir / f"scene_{i:03d}.mp3"
            image_path = scenes_dir / f"scene_{i:03d}.png"
            clip_path = scenes_dir / f"scene_{i:03d}.mp4"

            narration = scene.narration_text or scene.visual_description or scene.id
            # Detect per-scene (not per-task): the LLM doesn't always honor the
            # "answer in the task's language" instruction, especially the small
            # local fallback model — matching the actual narration text avoids
            # e.g. German TTS phonetics being applied to English narration.
            _synthesize_narration(narration, audio_path, _detect_lang(narration))
            audio_duration = _ffprobe_duration(audio_path)

            _update_job_progress(
                storage, job, "skills_running", pct,
                f"Scene {i}/{total}: rendering slide...",
                current_scene=i, total_scenes=total,
            )
            _render_slide_image(scene, image_path)

            _update_job_progress(
                storage, job, "skills_running", pct,
                f"Scene {i}/{total}: encoding clip...",
                current_scene=i, total_scenes=total,
            )
            _assemble_scene_clip(image_path, audio_path, clip_path)

            clip_paths.append(clip_path)
            srt_entries.append({"narration_text": narration, "duration_s": audio_duration})

        measured_s = sum(e["duration_s"] for e in srt_entries)
        if measured_s > max_duration_minutes * 60:
            raise ValueError(
                f"Narrated length {measured_s:.0f}s exceeds the {max_duration_minutes}-minute limit"
            )

        # Step 3: Concat scenes + captions
        _update_job_progress(storage, job, "skills_running", 92, "Assembling final video...")

        video_path = out_root / "output.mp4"
        srt_path = out_root / "output.srt"
        _concat_clips(clip_paths, video_path, out_root)
        _generate_srt(srt_entries, srt_path)

        duration_seconds = int(sum(e["duration_s"] for e in srt_entries))
        file_size_mb = round(video_path.stat().st_size / (1024 * 1024), 2)

        video_output = VideoOutput(
            job_id=job_id,
            video_path=str(video_path),
            srt_path=str(srt_path),
            metadata={
                "duration_seconds": duration_seconds,
                "resolution": "1280x720",
                "fps": 30,
                "file_size_mb": file_size_mb,
                "scenes": total,
            },
        )
        storage.save_video_output(video_output)

        emit_feedback(
            job_id=job_id,
            event_type="video_produced",
            metrics={
                "duration_seconds": duration_seconds,
                "resolution": video_output.metadata["resolution"],
                "quality_score": 0.85,
            }
        )

        # Step 4: Update job status
        job.status = "complete"
        job.completed_at = datetime.now()
        job.video_output_path = str(video_path)
        _update_job_progress(storage, job, "complete", 100, "Video production complete!")

        return {
            "success": True,
            "job_id": job_id,
            "video_path": str(video_path),
            "srt_path": str(srt_path),
            "duration_seconds": duration_seconds,
            "metadata": video_output.metadata,
        }

    except subprocess.CalledProcessError as e:
        error_msg = f"{e.cmd[0]} failed: {e.stderr.strip()[-500:] if e.stderr else e}"
        logger.error(f"[{job_id}] Orchestration failed: {error_msg}")
        job.status = "error"
        job.error_message = error_msg
        job.completed_at = datetime.now()
        storage.save_job(job)
        emit_job_progress(job_id, "error", job.percent, error=error_msg)
        emit_feedback(job_id=job_id, event_type="orchestration_failed", metrics={"error": error_msg})
        raise

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{job_id}] Orchestration failed: {error_msg}", exc_info=True)

        job.status = "error"
        job.error_message = error_msg
        job.completed_at = datetime.now()
        storage.save_job(job)

        emit_job_progress(job_id, "error", job.percent, error=error_msg)
        emit_feedback(job_id=job_id, event_type="orchestration_failed", metrics={"error": error_msg})

        raise


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
        storage_base=config["storage_base"],
        tts_engine=config.get("tts_engine", "gtts"),
        max_duration_minutes=config.get("max_duration_minutes", 60),
        storyboard_backend=config.get("storyboard_backend", "ollama"),
        storyboard_model=config.get("storyboard_model"),
    )
