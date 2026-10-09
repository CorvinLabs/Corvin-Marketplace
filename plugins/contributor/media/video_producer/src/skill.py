"""TaskOrchestrator Skill — LLM Storyboarding + real audio/video assembly."""

import asyncio
import copy
import json
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
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
    from .narration_validator import validate_storyboard_dict, validate_storyboard, CHAR_BUDGETS
    from .screenshot_capturer import capture_screenshot, ScreenshotCaptureError
    from .screenshot_annotator import annotate_screenshot
    from .web_templates import TEMPLATES, THEMES, WebSceneError, load_tokens, validate_scene_data
    from .web_renderer import FPS_DEFAULT, MAX_SCENE_SECONDS, WebRenderError, WebSlideRenderer
    from .web_layout import format_issues
    from .web_templates import MAP_LAYERS, console_assets
    from .grounding import render_pack, validate_pack
    from . import grounded_storyboard as gsb
except ImportError:  # standalone script use (no package context)
    from models import VideoJob, Storyboard, Scene, VideoOutput
    from storage import get_storage, TERMINAL_STATUSES
    from narration_validator import validate_storyboard_dict, validate_storyboard, CHAR_BUDGETS
    from screenshot_capturer import capture_screenshot, ScreenshotCaptureError
    from screenshot_annotator import annotate_screenshot
    from web_templates import TEMPLATES, THEMES, WebSceneError, load_tokens, validate_scene_data
    from web_renderer import FPS_DEFAULT, MAX_SCENE_SECONDS, WebRenderError, WebSlideRenderer
    from web_layout import format_issues
    from web_templates import MAP_LAYERS, console_assets
    from grounding import render_pack, validate_pack
    import grounded_storyboard as gsb

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


_CLAUDE_CLI_TIMEOUT_S = 300
_CLAUDE_MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-\[\]]{0,79}")
_STORYBOARD_SYSTEM = ("You write didactic explainer-video storyboards. Follow the user's "
                      "format exactly and reply with one JSON object only.")


def claude_cli_path() -> Optional[str]:
    """The Claude Code CLI the host runs: its canonical pin CORVIN_CLAUDE_BIN, else PATH."""
    pinned = (os.environ.get("CORVIN_CLAUDE_BIN") or "").strip()
    if pinned:
        return pinned if os.path.isfile(pinned) and os.access(pinned, os.X_OK) else None
    return shutil.which("claude")


def _call_claude_cli(prompt: str, model: str) -> str:
    """One tool-less, settings-less ``claude -p`` call (the host's Claude Code login).

    The prompt goes over stdin, never argv; the call runs in an empty temp dir with
    no tools, no MCP servers, no settings files and no saved session, so the model
    only ever sees the storyboard prompt."""
    exe = claude_cli_path()
    if not exe:
        raise RuntimeError("claude CLI not found (CORVIN_CLAUDE_BIN or PATH)")
    if not isinstance(model, str) or not _CLAUDE_MODEL_RE.fullmatch(model):
        raise ValueError("invalid model id for the claude CLI")
    with tempfile.TemporaryDirectory(prefix="vp-storyboard-") as cwd:
        proc = subprocess.run(
            [exe, "-p", "--model", model, "--output-format", "json", "--tools", "",
             "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence",
             "--disable-slash-commands", "--system-prompt", _STORYBOARD_SYSTEM],
            input=prompt, capture_output=True, text=True, timeout=_CLAUDE_CLI_TIMEOUT_S, cwd=cwd,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI exited {proc.returncode}")
    out = json.loads(proc.stdout)
    if out.get("is_error") or not isinstance(out.get("result"), str):
        raise RuntimeError(f"claude CLI reported an error ({out.get('terminal_reason') or out.get('subtype')})")
    return out["result"]


def _call_storyboard_llm(prompt: str, backend: str = "ollama", model: Optional[str] = None,
                         report: Optional[Dict[str, Any]] = None, local_fallback: bool = True) -> str:
    """
    Call an LLM to turn the prompt into a storyboard JSON string.

    ``backend`` is decided by the HOST, which ran its data-flow / egress gates
    for exactly that destination before starting the job: "claude_cli" (the
    host's Claude Code login, needs ``model``), "anthropic" (API key, needs
    ``model``) or "ollama" (local). The plugin never upgrades a job to a
    remote backend on its own. A remote call that fails falls back to the
    local Ollama instance (strictly less egress). Both paths are real
    inference — no mocked/fabricated storyboard content. ``report["backend"]``
    receives the backend that actually answered.
    """
    if backend not in ("claude_cli", "anthropic", "ollama"):
        raise ValueError(f"unknown storyboard backend {backend!r}")
    if backend != "ollama" and not model:
        raise ValueError(f"storyboard backend {backend!r} needs a model id from the host")
    if report is None:
        report = {}
    if backend == "claude_cli":
        try:
            text = _call_claude_cli(prompt, model)
            report["backend"] = f"claude_cli:{model}"
            return text
        except Exception as e:  # noqa: BLE001
            logger.warning("claude CLI storyboard call failed (%s), falling back to local Ollama", type(e).__name__)
    if backend == "anthropic":
        try:
            client = anthropic.Anthropic()
            message = client.messages.create(
                model=model,
                max_tokens=6000,
                messages=[{"role": "user", "content": prompt}],
            )
            report["backend"] = f"anthropic:{model}"
            return message.content[0].text
        except Exception as e:  # noqa: BLE001
            logger.warning("Anthropic storyboard call failed (%s), falling back to local Ollama", type(e).__name__)
    if backend != "ollama" and not local_fallback:
        # A grounded prompt must not land on the small local model: its context window
        # truncates the SOURCES silently (PLAN-0942 D2).
        raise RuntimeError(f"remote storyboard backend {backend!r} unavailable")

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
    report["backend"] = f"ollama:{_OLLAMA_MODEL}"
    return response.json()["response"]


_SYSTEM_KEYWORDS = ("system", "architecture", "pipeline", "flow", "layer", "chain", "stack", "kette", "architektur")
_CONCEPT_KEYWORDS = ("concept", "loop", "why", "how", "principle", "algorithm", "konzept", "warum", "prinzip")


def detect_didactic_strategy(task: str) -> str:
    """
    Auto-detect "minimal_visual" (concept-first: narration carries the
    content, 150-250 chars/scene) vs "rich_visual" (system/architecture:
    diagrams carry the content, 300-400 chars/scene).

    Heuristic derived from measuring /home/shumway/projects/videos: the
    adscale-LDD series (concept explainers) averaged 1.6 shapes/slide and
    177 chars/slide; the Compliance series (system/architecture) averaged
    16-20 shapes/slide and 335-345 chars/slide. Task keywords are the only
    signal available before a single scene exists.
    """
    task_lower = task.lower()
    if any(kw in task_lower for kw in _SYSTEM_KEYWORDS):
        return "rich_visual"
    if any(kw in task_lower for kw in _CONCEPT_KEYWORDS):
        return "minimal_visual"
    return "rich_visual"  # default: most tasks describe a system/process


_TEMPLATE_GUIDE = """WEB SLIDES (preferred visual for every scene): add "template" and "data".
Templates and their data (plain text only, never HTML; keep texts short):
- "hero":    {"badge"?, "title", "accent"?, "subtitle"?}  (title slide; accent = italic highlight line)
- "content": {"eyebrow"?, "title", "bullets": [1-5 short strings]}
- "stat":    {"eyebrow"?, "value": number, "decimals"?: 0-2, "prefix"?, "suffix"?, "label", "caption"?, "locale"?: "de"|"en"}
             (only for a number stated in the task or narration; never invent figures)
- "diagram": {"eyebrow"?, "title", "nodes": [2-6 {"label", "sub"?}], "highlight"?: index}  (left-to-right flow)
- "chart":   {"eyebrow"?, "title", "bars": [2-8 {"label", "value": number >= 0}], "unit"?, "decimals"?, "highlight"?, "locale"?}
             (only with real numbers from the task; never invent data)
- "compare": {"eyebrow"?, "title", "left": {"title", "points": [1-4]}, "right": {"title", "points": [1-4]}}
- "quote":   {"eyebrow"?, "quote", "attribution"?, "locale"?}
- "code":    {"eyebrow"?, "title", "language"?, "lines": [1-12 strings]}
- "flow":    {"eyebrow"?, "title", "nodes": [2-8 {"id": "a-z0-9_", "label", "sub"?}],
              "edges": [1-12 {"from": id, "to": id, "label"?}], "highlight"?: id}
             (a graph with branches/merges, laid out left to right; no cycles; at most 5 columns
              and 4 nodes per column; data pulses run along the edges)
- "cycle":   {"eyebrow"?, "title", "caption"?, "center"?, "steps": [3-6 {"label", "sub"?}], "highlight"?: index}
             (a loop: feedback, learning, iteration)
- "layers":  {"eyebrow"?, "title", "layers": [2-6 {"label", "sub"?, "tag"?}], "highlight"?: index}
             (a stack, first = top: architecture layers, tiers)
- "timeline": {"eyebrow"?, "title", "events": [2-6 {"when", "label", "sub"?}], "current"?: index}
             (history, roadmap, phases)
- "line":    {"eyebrow"?, "title", "labels": [3-12 x-axis labels], "series": [1-3 {"name", "values": [numbers, one per label]}],
              "unit"?, "decimals"?, "highlight"?: index, "locale"?}  (a trend; only with real numbers from the task)
- "donut":   {"eyebrow"?, "title", "segments": [2-6 {"label", "value": number >= 0}], "center_value"?, "center_label"?,
              "unit"?, "decimals"?, "highlight"?: index, "locale"?}  (shares of a whole; only real numbers)
Limits: title 70-80 chars (cycle 60), bullet 110, node label 28 (flow 24), bar label 24, layer label 32.
Optional per scene: "theme": "dark" (default) or "light".

CHOOSING A VISUAL — pick the template that SHOWS the idea instead of listing it:
- branching process / architecture with several parts -> "flow"; a straight 2-6 step pipeline -> "diagram"
- feedback loop / iteration -> "cycle"; layered architecture / tiers -> "layers"; history / roadmap -> "timeline"
- a trend over time -> "line"; parts of a whole -> "donut"; quantities side by side -> "chart"; one key number -> "stat"
- before/after or option A vs. B -> "compare"; a command or config -> "code"; one memorable sentence -> "quote"
- "content" (bullets) only when nothing above fits — at most once per video; "hero" for the title scene.
- Never invent numbers: "line", "donut", "chart" and "stat" only with figures stated in the task.
- Write template text in the same language as the narration ("locale": "de" for German numbers).
"""


async def generate_storyboard_with_llm(
    task: str,
    max_duration_minutes: int = 60,
    backend: str = "ollama",
    model: Optional[str] = None,
    didactic_strategy: Optional[str] = None,
    grounding: Optional[Dict[str, Any]] = None,
) -> Storyboard:
    """
    LLM: Task → Storyboard (JSON)

    Generates a detailed video storyboard from natural language task.
    Enforces constraints: max duration, max scenes, per-scene text budget,
    per-scene timing — all via narration_validator.validate_storyboard_dict(),
    the single validation primitive (ADR-0004). This function no longer
    duplicates those checks inline.
    """
    # A hard ceiling of 100 exists for the API contract, but the *requested* count
    # stays small and duration-independent: max_duration_minutes is a ceiling the
    # storyboard must not exceed, not a target, and the local Ollama CPU fallback
    # (no GPU on this host) needs a small scene count to finish in reasonable time.
    # A remote model writes a longer storyboard in seconds; the CPU-only local
    # fallback needs the small count.
    max_scenes = 6 if backend == "ollama" else 8
    # PLAN-0942: a host-gated grounding pack is used with a remote model only.
    grounded = grounding is not None and backend != "ollama"
    if grounded:
        max_scenes = gsb.GROUNDED_MAX_SCENES

    strategy = didactic_strategy or detect_didactic_strategy(task)
    budget = CHAR_BUDGETS.get(strategy, CHAR_BUDGETS["rich_visual"])

    prompt = f"""
You are a didactic video storyboard generator. Given a task, generate a detailed,
pedagogically effective video storyboard as JSON.

Task: {task}
Max Duration: {max_duration_minutes} minutes (~{max_duration_minutes * 60000} ms)
Didactic strategy: {strategy} — target {budget['min']}-{budget['max']} characters of
narration per scene (sweet spot {budget['target']}).

Generate scenes of types: "title", "opening", "problem", "solution", "example",
"summary", "anchor" (use "screenshot"/"screencast"/"animation" only if the task
is literally about a UI walkthrough).

DESIGN RULES (measured from real didactic videos, apply them):
- Scene 1 is "title" (short hook, under {budget['min']}ch).
- Scene 2 is "opening" or "problem": set context, state why this matters.
- Middle scenes are "solution"/"example": one idea per scene.
- Last scene is "summary" or "anchor": a memorable one-sentence takeaway.
- Each scene duration: 8000-20000 ms (8-20 seconds) — long enough to read,
  short enough to hold attention.
- Narration per scene: {budget['min']}-{budget['max']} characters (hard ceiling 500).
- Write narration_text in the SAME language as the Task above.
- visual_description should name a concrete icon or diagram concept (e.g.
  "shield icon" for security, "chain with four links" for a 4-step process),
  not a vague mood description.

{_TEMPLATE_GUIDE}

CONSTRAINTS (MUST ENFORCE):
- Total duration ≤ {max_duration_minutes * 60000} ms
- Maximum {max_scenes} scenes
- Each scene must have: id, kind, duration_ms, narration_text, visual_description

OUTPUT FORMAT (valid JSON only, no markdown):
{{
  "id": "sb_{uuid.uuid4().hex[:8]}",
  "didactic_strategy": "{strategy}",
  "scenes": [
    {{
      "id": "s1",
      "kind": "title",
      "duration_ms": 8000,
      "narration_text": "Welcome to Corvin",
      "visual_description": "Corvin logo on dark background",
      "template": "hero",
      "data": {{"title": "Welcome to Corvin", "accent": "The agentic OS"}}
    }},
    ...
  ]
}}

RETURN ONLY THE JSON, NO EXPLANATIONS.
"""

    report: Dict[str, Any] = {}
    pack_text = ""
    if grounded:
        pack_text = render_pack(grounding)
        grounded_prompt = prompt.replace(
            "\nCONSTRAINTS (MUST ENFORCE):",
            gsb.build_sources_block(pack_text, console_assets(), task) + "\nCONSTRAINTS (MUST ENFORCE):", 1,
        )
        try:
            raw = _call_storyboard_llm(grounded_prompt, backend=backend, model=model, report=report,
                                       local_fallback=False)
        except Exception as e:  # noqa: BLE001 — remote down: the ordinary path, recorded as unavailable
            logger.warning("grounded storyboard unavailable (%s); writing an ungrounded one", type(e).__name__)
            sb = await generate_storyboard_with_llm(task, max_duration_minutes, backend=backend, model=model,
                                                    didactic_strategy=didactic_strategy)
            sb.grounding = {"status": "unavailable", "reason": "remote_storyboard_failed"}
            return sb
    else:
        raw = _call_storyboard_llm(prompt, backend=backend, model=model, report=report)

    try:
        raw = raw.strip()
        # Tolerate an LLM wrapping the JSON in a ```json fence despite instructions.
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        storyboard_json = json.loads(raw)
        storyboard_json.setdefault("didactic_strategy", strategy)

        if not storyboard_json.get("scenes"):
            raise ValueError("No scenes in storyboard")

        # Single validation primitive (ADR-0004): structural errors (scene
        # count, total duration, hard char/duration ceilings) raise here.
        # Didactic warnings (soft text-budget/timing/flow) do not block
        # generation — they are returned to the caller via emit_feedback()
        # in orchestrate_video() so the operator sees them without the
        # pipeline refusing a usable-but-imperfect storyboard.
        validation = validate_storyboard_dict(storyboard_json, max_duration_minutes)
        validation.raise_if_invalid()

        # LLM output is untrusted: an invalid web-slide spec is dropped (the
        # scene then renders on the Pillow path), never passed through. A remote
        # model gets one chance to repair exactly the scenes that failed.
        template_warnings = _repair_web_scenes(storyboard_json["scenes"], report, model)
        for warning in template_warnings:
            logger.warning("storyboard web-slide warning: %s", warning)
        if template_warnings:
            report["degraded_to_quote"] = _degrade_to_web_slides(storyboard_json["scenes"])
        grounding_info = (
            _ground_storyboard(storyboard_json, grounding, pack_text, report, model, max_duration_minutes)
            if grounded else None
        )

        scenes = [Scene.from_dict(s) for s in storyboard_json["scenes"]]
        return Storyboard(
            id=storyboard_json.get("id", f"sb_{uuid.uuid4().hex[:8]}"),
            task=task,
            scenes=scenes,
            generated_at=datetime.now(),
            didactic_strategy=storyboard_json["didactic_strategy"],
            llm_backend=report.get("backend", backend),
            template_warnings=template_warnings,
            template_repairs=report.get("repaired", 0),
            grounding=grounding_info,
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


OPENAI_TTS_MODEL = "tts-1-hd"
OPENAI_TTS_VOICE = "onyx"  # ADR-2211: calm, low male voice — consistent across de/en
_SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{6,}|Bearer\s+\S+)")


def _scrub_secrets(text: str) -> str:
    """Remove anything key-shaped from a message before it can reach a job record."""
    return _SECRET_RE.sub("<redacted>", str(text))[:300]


def _openai_api_key() -> Optional[str]:
    return os.environ.get("CORVIN_TTS_OPENAI_KEY") or os.environ.get("OPENAI_API_KEY") or None


def _openai_speech(text: str, out_path: Path, api_key: str) -> None:
    """One OpenAI TTS call; raises on any failure (callers decide: decline or fail)."""
    from openai import OpenAI

    response = OpenAI(api_key=api_key).audio.speech.create(
        model=OPENAI_TTS_MODEL, voice=OPENAI_TTS_VOICE, input=(text or "").strip() or "...",
    )
    response.stream_to_file(str(out_path))
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError("OpenAI returned no audio")


def _synthesize_narration_openai(text: str, out_path: Path, lang: str) -> None:
    """Narration via OpenAI TTS, strictly: any problem fails the job with a clear message.

    No silent substitution of another voice — a video whose narrator changes
    mid-way is worse than a refused job. Use tts_engine="auto" for the
    fallback chain (openai -> edge-tts -> piper -> mock, ADR-2211)."""
    api_key = _openai_api_key()
    if not api_key:
        raise RuntimeError(
            "OpenAI TTS is the narration engine, but no key is configured (CORVIN_TTS_OPENAI_KEY or "
            "OPENAI_API_KEY in the host environment). Choose another engine in the Video Producer settings."
        )
    try:
        _openai_speech(text, out_path, api_key)
    except ImportError:
        raise RuntimeError("OpenAI TTS needs the 'openai' Python package in the host environment") from None
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"OpenAI TTS failed ({type(e).__name__}): {_scrub_secrets(e)}") from None


def _synthesize_narration(text: str, out_path: Path, lang: str) -> None:
    """Real TTS via gTTS (Google Translate public endpoint, no API key required)."""
    from gtts import gTTS

    text = (text or "").strip() or "..."
    tts = gTTS(text=text, lang=lang)
    tts.save(str(out_path))


# --------------------------------------------------------------------------
# TTS fallback chain (ADR-2211): openai -> edge-tts -> piper-tts -> mock.
# Each tier returns True on success, False on "decline" (missing key/package,
# network error, timeout) — a decline falls through to the next tier, it
# never raises past the chain. "mock" is the only tier that cannot decline
# (no external dependency), so the chain always produces an audio_path.
# --------------------------------------------------------------------------

_PIPER_VOICE_MODELS = {
    "de": "de_DE-thorsten-medium",
    "en": "en_US-lessac-medium",
}


def _tts_tier_openai(text: str, out_path: Path, lang: str) -> bool:
    """Tier 1: OpenAI TTS. Declines if no key or package, or the call fails."""
    api_key = _openai_api_key()
    if not api_key:
        return False
    try:
        _openai_speech(text, out_path, api_key)
        return True
    except ImportError:
        logger.info("tts chain: openai package not installed, declining")
        return False
    except Exception as e:  # noqa: BLE001 — any failure declines, never crashes the chain
        logger.warning("tts chain: openai tier declined (%s: %s)", type(e).__name__, _scrub_secrets(e))
        return False


def _run_coroutine_blocking(make_coro, timeout: float = 180.0):
    """Run a coroutine to completion from synchronous code, whether or not this
    thread already runs an event loop. The TTS tiers are sync and are called from
    orchestrate_video, which the job runner executes under asyncio.run in a worker
    thread; a bare asyncio.run() there raises "cannot be called from a running
    event loop" — which made the edge-tts tier decline on every production job."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(make_coro())
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(make_coro())).result(timeout=timeout)


def _tts_tier_edge(text: str, out_path: Path, lang: str) -> bool:
    """Tier 2: edge-tts (Microsoft cloud voices, free, no API key, needs network)."""
    try:
        import edge_tts
    except ImportError:
        logger.info("tts chain: edge-tts package not installed, declining")
        return False

    voice = "de-DE-KatjaNeural" if lang == "de" else "en-US-AvaMultilingualNeural"
    try:
        async def _run() -> None:
            communicate = edge_tts.Communicate((text or "").strip() or "...", voice)
            await communicate.save(str(out_path))

        _run_coroutine_blocking(_run)
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception as e:  # noqa: BLE001
        logger.warning("tts chain: edge-tts tier declined (%s: %s)", type(e).__name__, e)
        return False


def _tts_tier_piper(text: str, out_path: Path, lang: str) -> bool:
    """Tier 3: piper-tts (fully local/offline, needs a downloaded voice model)."""
    try:
        from piper import PiperVoice
    except ImportError:
        logger.info("tts chain: piper-tts package not installed, declining")
        return False

    model_name = _PIPER_VOICE_MODELS.get(lang, _PIPER_VOICE_MODELS["en"])
    model_path = Path.home() / ".local" / "share" / "piper-voices" / f"{model_name}.onnx"
    if not model_path.exists():
        logger.info("tts chain: piper voice model %s not downloaded, declining", model_name)
        return False

    try:
        import wave
        voice = PiperVoice.load(str(model_path))
        with wave.open(str(out_path), "wb") as wav_file:
            voice.synthesize((text or "").strip() or "...", wav_file)
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception as e:  # noqa: BLE001
        logger.warning("tts chain: piper tier declined (%s: %s)", type(e).__name__, e)
        return False


def _tts_tier_mock(text: str, out_path: Path, lang: str) -> bool:
    """Tier 4: last resort — a silent placeholder WAV, duration estimated from
    text length (~150 words/minute), so a network-isolated CI environment
    still produces a pipeline result instead of a hard failure."""
    import wave
    import struct

    word_count = max(1, len((text or "").split()))
    duration_s = max(1.0, word_count / 150.0 * 60.0)
    sample_rate = 16000
    n_frames = int(duration_s * sample_rate)

    with wave.open(str(out_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(struct.pack(f"<{n_frames}h", *([0] * n_frames)))
    logger.warning("tts chain: all real tiers declined, wrote %.1fs silent mock", duration_s)
    return True


_TTS_CHAIN = (
    ("openai", _tts_tier_openai),
    ("edge", _tts_tier_edge),
    ("piper", _tts_tier_piper),
    ("mock", _tts_tier_mock),
)


def _synthesize_narration_chain(text: str, out_path: Path, lang: str) -> str:
    """Try each TTS tier in priority order (ADR-2211); returns the provider
    name that actually produced audio_path, for audit/feedback attribution."""
    for provider_name, tier_fn in _TTS_CHAIN:
        if tier_fn(text, out_path, lang):
            return provider_name
    # Unreachable: the mock tier never declines, but keep the contract explicit.
    raise RuntimeError("tts chain: every tier declined, including mock")


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


# Color-to-meaning system (ADR-0004, measured from /home/shumway/projects/videos
# Compliance series): orange/trust=solution, red=risk/problem, steel=neutral.
_COLOR_NAVY = (29, 42, 68)
_COLOR_NAVY_DARK = (18, 32, 43)
_COLOR_ICE = (232, 238, 247)
_COLOR_STEEL = (91, 107, 130)
_COLOR_RISK = (214, 69, 80)
_COLOR_TRUST = (0, 168, 150)
_COLOR_WARN = (224, 160, 50)

_KIND_ACCENT = {
    "problem": _COLOR_RISK,
    "solution": _COLOR_TRUST,
    "summary": _COLOR_TRUST,
    "anchor": _COLOR_TRUST,
    "opening": _COLOR_WARN,
    "example": _COLOR_STEEL,
}

# Vector icon keywords → drawing function name. DejaVuSans has NO emoji
# glyphs (verified: U+1F512 lock, U+26D3 chains, U+1F6E1 shield, U+1F50D
# magnifier, U+1F4CB clipboard are all MISSING — they would render as empty
# tofu boxes). Icons are therefore drawn as PIL vector primitives, not text
# glyphs, so they render identically regardless of font coverage.
_ICON_KEYWORDS = {
    "shield": "shield", "security": "shield", "identity": "shield",
    "chain": "chain", "link": "chain", "kette": "chain",
    "audit": "magnifier", "search": "magnifier", "review": "magnifier",
    "policy": "document", "document": "document", "rule": "document",
    "warning": "warning", "risk": "warning", "danger": "warning",
    "check": "check", "success": "check", "solved": "check", "trust": "check",
    "arrow": "arrow", "process": "arrow", "flow": "arrow",
    "loop": "loop", "cycle": "loop",
}


def _detect_icon(visual_description: str) -> Optional[str]:
    """Parse visual_description for a known icon keyword (English or German)."""
    desc_lower = (visual_description or "").lower()
    for keyword, icon_name in _ICON_KEYWORDS.items():
        if keyword in desc_lower:
            return icon_name
    return None


def _draw_vertical_gradient(img: "Image.Image", top_color: tuple, bottom_color: tuple) -> None:
    """Paint a vertical gradient in place (flat fills read as a slide
    template placeholder, not a produced video — the /home/shumway/projects/videos
    reference series never uses flat single-color backgrounds)."""
    from PIL import ImageDraw

    w, h = img.size
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        row = tuple(int(top_color[c] + (bottom_color[c] - top_color[c]) * t) for c in range(3))
        draw.line([(0, y), (w, y)], fill=row)


def _draw_progress_dots(draw: "ImageDraw.ImageDraw", w: int, h: int, scene_index: int, total_scenes: int, accent_color: tuple) -> None:
    """Small dot row near the bottom edge showing position in the storyboard
    (filled = current/passed, hollow = upcoming) — the one orientation cue a
    viewer otherwise only gets from counting narration beats."""
    if total_scenes <= 1:
        return
    dot_r = 5
    gap = 22
    total_width = (total_scenes - 1) * gap
    start_x = (w - total_width) // 2
    y = h - 28
    for i in range(total_scenes):
        cx = start_x + i * gap
        if i < scene_index:
            draw.ellipse([cx - dot_r, y - dot_r, cx + dot_r, y + dot_r], fill=accent_color)
        else:
            draw.ellipse([cx - dot_r, y - dot_r, cx + dot_r, y + dot_r], outline=accent_color, width=2)


_ICON_SUPERSAMPLE = 4  # shared by _draw_icon and _draw_icon_primitives' stroke widths


def _draw_icon(draw_unused: "ImageDraw.ImageDraw", icon_name: str, cx: int, cy: int, size: int, color: tuple) -> None:
    """Draw a vector icon centered at (cx, cy), roughly `size` px across,
    anti-aliased via 4x supersampling (PIL's draw primitives have no AA —
    at native resolution icon edges/curves came out visibly jagged) then
    alpha-composited onto the caller's image. `draw_unused` kept so the
    call site in _render_slide_image doesn't need to change."""
    from PIL import Image, ImageDraw

    img = draw_unused._image  # the Image.Image backing the caller's ImageDraw
    ss = _ICON_SUPERSAMPLE
    r = (size * ss) // 2
    layer = Image.new("RGBA", (size * ss, size * ss), (0, 0, 0, 0))
    ldraw = ImageDraw.Draw(layer)
    ccx = ccy = (size * ss) // 2
    rgba = color + (255,) if len(color) == 3 else color
    _draw_icon_primitives(ldraw, icon_name, ccx, ccy, r, rgba)
    layer = layer.resize((size, size), Image.LANCZOS)
    img.paste(layer, (cx - size // 2, cy - size // 2), layer)


def _draw_icon_primitives(draw: "ImageDraw.ImageDraw", icon_name: str, cx: int, cy: int, r: int, color: tuple) -> None:
    """The actual icon geometry, parameterized by radius `r` (half of the
    target bounding box). Stroke widths are scaled by _ICON_SUPERSAMPLE since
    this always runs at supersampled resolution (called only from _draw_icon)."""
    size = r * 2
    ss = _ICON_SUPERSAMPLE
    if icon_name == "shield":
        pts = [
            (cx, cy - r), (cx + r, cy - r // 2), (cx + r, cy + r // 4),
            (cx, cy + r), (cx - r, cy + r // 4), (cx - r, cy - r // 2),
        ]
        draw.polygon(pts, outline=color, width=6 * ss)
    elif icon_name == "chain":
        link_r = size // 5
        for i, dx in enumerate((-2, -1, 0, 1)):
            lx = cx + dx * link_r * 2
            draw.ellipse([lx - link_r, cy - link_r, lx + link_r, cy + link_r], outline=color, width=6 * ss)
    elif icon_name == "magnifier":
        glass_r = int(r * 0.7)
        draw.ellipse([cx - glass_r, cy - glass_r - r // 4, cx + glass_r, cy + glass_r - r // 4], outline=color, width=6 * ss)
        draw.line([cx + glass_r // 2, cy + glass_r - r // 4, cx + r, cy + r], fill=color, width=8 * ss)
    elif icon_name == "document":
        draw.rectangle([cx - r // 2, cy - r, cx + r // 2, cy + r], outline=color, width=5 * ss)
        for i in range(3):
            ly = cy - r // 2 + i * (r // 2)
            draw.line([cx - r // 3, ly, cx + r // 3, ly], fill=color, width=4 * ss)
    elif icon_name == "warning":
        draw.polygon([(cx, cy - r), (cx + r, cy + r), (cx - r, cy + r)], outline=color, width=6 * ss)
        draw.line([cx, cy - r // 3, cx, cy + r // 4], fill=color, width=6 * ss)
        draw.ellipse([cx - 3 * ss, cy + r // 2, cx + 3 * ss, cy + r // 2 + 6 * ss], fill=color)
    elif icon_name == "check":
        draw.line([cx - r, cy, cx - r // 4, cy + r // 2], fill=color, width=10 * ss)
        draw.line([cx - r // 4, cy + r // 2, cx + r, cy - r // 2], fill=color, width=10 * ss)
    elif icon_name == "arrow":
        draw.line([cx - r, cy, cx + r // 2, cy], fill=color, width=8 * ss)
        draw.polygon([(cx + r, cy), (cx + r // 3, cy - r // 2), (cx + r // 3, cy + r // 2)], fill=color)
    elif icon_name == "loop":
        draw.arc([cx - r, cy - r, cx + r, cy + r], start=30, end=300, fill=color, width=8 * ss)
        draw.polygon([(cx + r, cy - r // 3), (cx + int(r * 1.3), cy - r // 2), (cx + int(r * 0.9), cy - int(r * 0.9))], fill=color)
    else:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=6 * ss)


def _render_slide_image(
    scene: Scene,
    out_path: Path,
    w: int = 1280,
    h: int = 720,
    strategy: Optional[str] = None,
    scene_index: Optional[int] = None,
    total_scenes: Optional[int] = None,
) -> None:
    """
    Render a real 1280x720 PNG slide via Pillow (this ffmpeg static build ships
    without the drawtext filter — confirmed via `ffmpeg -filters`).

    ``strategy`` ("minimal_visual" | "rich_visual", ADR-0004) selects the
    layout: rich_visual draws a vector icon derived from visual_description
    plus a kind-colored accent bar; minimal_visual stays text-first (the
    narration carries the content, per the video-production analysis of
    /home/shumway/projects/videos — the adscale-LDD series averaged 1.6
    shapes/slide vs. the Compliance series' 16-20).

    ``scene_index``/``total_scenes`` (both 1-based, optional) draw a
    progress-dot row — omitted entirely when the caller doesn't have them
    (e.g. a standalone test rendering a single scene), so this stays
    backward compatible.
    """
    from PIL import Image, ImageDraw, ImageFont

    kind_label = {
        "title": "TITLE",
        "opening": "OPENING",
        "problem": "PROBLEM",
        "solution": "SOLUTION",
        "example": "EXAMPLE",
        "summary": "SUMMARY",
        "anchor": "ANCHOR",
        "narration": "NARRATION",
        # Real capture (CONCEPT-0095) happens in _render_screenshot_scene(),
        # called from orchestrate_video() BEFORE this function for
        # kind=="screenshot" — this label only shows if _render_slide_image
        # is called directly for a screenshot scene (bypassing the real
        # capture path, e.g. in a test), which is why it still says
        # "placeholder" here and nowhere else.
        "screenshot": "SCREENSHOT (placeholder — call _render_screenshot_scene via orchestrate_video for a real capture)",
        "screencast": "SCREENCAST (not implemented — CONCEPT-0095 Tier 2/video capture is out of scope)",
        "animation": "ANIMATION (placeholder)",
    }.get(scene.kind, scene.kind.upper())

    # The spoken text is never drawn on a slide — that would be a burned-in subtitle.
    # Only the placeholder kinds show their visual_description (a description, not narration).
    body_source = scene.visual_description if scene.kind in ("screenshot", "screencast", "animation") else ""
    body_lines = _wrap_text(body_source) if body_source else []

    bg_top = _COLOR_NAVY_DARK if scene.kind == "title" else tuple(c + 6 for c in _COLOR_NAVY)
    bg_bottom = (8, 14, 22) if scene.kind == "title" else _COLOR_NAVY_DARK
    accent_color = _KIND_ACCENT.get(scene.kind, (138, 180, 255))

    img = Image.new("RGB", (w, h))
    _draw_vertical_gradient(img, bg_top, bg_bottom)
    draw = ImageDraw.Draw(img)

    title_font = ImageFont.truetype(_FONT_BOLD_PATH, 40)
    body_font = ImageFont.truetype(_FONT_PATH, 30)

    def centered_x(text: str, font: "ImageFont.FreeTypeFont") -> int:
        bbox = draw.textbbox((0, 0), text, font=font)
        return (w - (bbox[2] - bbox[0])) // 2

    def draw_label_with_divider(y: int) -> None:
        # Kind label plus a short accent-colored rule beneath it — the one
        # hierarchy cue the flat-text layout was missing entirely (label and
        # body previously read as the same visual weight once narration ran
        # past one line).
        draw.text((centered_x(kind_label, title_font), y), kind_label, font=title_font, fill=accent_color)
        bbox = draw.textbbox((0, y), kind_label, font=title_font)
        divider_y = bbox[3] + 10
        divider_half_w = min(90, (bbox[2] - bbox[0]) // 2)
        draw.line([(w // 2 - divider_half_w, divider_y), (w // 2 + divider_half_w, divider_y)], fill=accent_color, width=3)

    icon_name = _detect_icon(scene.visual_description or "")

    if strategy == "rich_visual" and icon_name:
        # Icon-rich layout: icon top, label below icon, narration at bottom.
        _draw_icon(draw, icon_name, w // 2, 180, 140, accent_color)
        draw_label_with_divider(280)
        line_height = 42
        total_height = line_height * len(body_lines)
        y = h - 80 - total_height
        for line in body_lines:
            draw.text((centered_x(line, body_font), y), line, font=body_font, fill=_COLOR_ICE)
            y += line_height
    else:
        # Minimal/default layout: the kind label, large and centred, plus any placeholder text.
        draw_label_with_divider(90 if body_lines else (h - 100) // 2 - 20)
        line_height = 42
        total_height = line_height * len(body_lines)
        y = (h - total_height) // 2 + 20
        for line in body_lines:
            draw.text((centered_x(line, body_font), y), line, font=body_font, fill=_COLOR_ICE)
            y += line_height

    if scene_index is not None and total_scenes is not None:
        _draw_progress_dots(draw, w, h, scene_index, total_scenes, accent_color)

    img.save(out_path)


async def _render_screenshot_scene(scene: Scene, image_path: Path) -> None:
    """Capture a real screenshot for a kind=='screenshot' scene (CONCEPT-0095),
    optionally annotated with a spotlight call-out around
    ``scene.highlight_selector``'s resolved bounding box.

    Hard errors (ScreenshotCaptureError, or a missing screenshot_url)
    propagate to the caller — a scene that can't be captured correctly must
    fail the job, not silently fall back to a placeholder slide shipped as
    if it were correct.
    """
    if not scene.screenshot_url:
        raise ValueError(
            f"Scene {scene.id!r} has kind='screenshot' but no screenshot_url set "
            f"— cannot capture nothing"
        )

    capture = await capture_screenshot(
        scene.screenshot_url,
        image_path,
        highlight_selector=scene.highlight_selector,
    )

    if capture.bounding_box:
        # Annotate into a temp file, then atomically replace — never leave
        # image_path in a partially-written state if annotation fails
        # partway through (CLAUDE.md: every write goes through a fresh temp
        # + swap, not an in-place overwrite of the file a reader might see).
        tmp_path = image_path.with_suffix(".annotated.png.tmp")
        annotate_screenshot(image_path, capture.bounding_box, tmp_path)
        os.replace(tmp_path, image_path)


def _ground_storyboard(storyboard_json: Dict[str, Any], pack: Dict[str, Any], pack_text: str,
                       report: Dict[str, Any], model: Optional[str], max_duration_minutes: int) -> Dict[str, Any]:
    """Claims check + one repair round (PLAN-0942 D9). Returns the job-safe grounding
    record: entity ids/titles/truth labels and counts — never pack or claim text."""
    scenes = storyboard_json["scenes"]
    failures = gsb.check_claims(scenes, pack_text)
    repaired = 0
    used = str(report.get("backend", ""))
    if failures and used.startswith(("claude_cli:", "anthropic:")):
        backend, _, used_model = used.partition(":")

        def _scene_ok(scene: Dict[str, Any]) -> bool:
            return not _apply_web_scene_contract([copy.deepcopy(scene)], strict=False)

        repaired = gsb.repair_grounded_scenes(
            storyboard_json, failures, pack_text, console_assets(),
            call_llm=lambda p: _call_storyboard_llm(p, backend=backend, model=used_model or model,
                                                    report={}, local_fallback=False),
            validate_storyboard=lambda sb: validate_storyboard_dict(sb, max_duration_minutes).valid,
            validate_scene=_scene_ok,
        )
        if repaired:
            # the repaired scenes' web specs are normalised exactly like the first pass
            _apply_web_scene_contract(storyboard_json["scenes"], strict=False)
            failures = gsb.check_claims(storyboard_json["scenes"], pack_text)
    unverified = gsb.summarise(failures, [str(s.get("id")) for s in storyboard_json["scenes"]])
    _drop_constant_map(storyboard_json["scenes"])
    return {
        "status": "grounded" if not failures else "grounded_with_unverified",
        "entities": [{"id": s["id"], "title": s["title"], "truth": s["truth"]} for s in pack["sections"]],
        "claim_repairs": repaired,
        "unverified": unverified,
    }


def _drop_constant_map(scenes: List[Dict[str, Any]]) -> None:
    """The "you are here" strip only teaches when the focus moves (PLAN-0942 D11)."""
    foci = {(s.get("map") or {}).get("focus") for s in scenes if isinstance(s, dict) and s.get("map")}
    if len(foci) <= 1:
        for s in scenes:
            if isinstance(s, dict):
                s.pop("map", None)


def _degrade_to_web_slides(scenes: List[Dict[str, Any]]) -> int:
    """LLM scenes that still have no valid web spec get a quote slide built from
    their own narration, so no scene falls back to the plain placeholder slide
    (which looks nothing like the rest of the video). Returns how many."""
    n = 0
    for scene in scenes:
        if not isinstance(scene, dict) or scene.get("template") is not None:
            continue
        if scene.get("kind") in ("screenshot", "screencast"):
            continue
        text = " ".join(str(scene.get("narration_text") or "").split())
        if not text:
            continue
        first = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
        if len(first) > 200:
            first = first[:197].rstrip() + "..."
        trial = {"template": "quote", "data": {"quote": first, "locale": _detect_lang(text)}}
        if not _apply_web_scene_contract([trial], strict=False):
            scene["template"], scene["data"] = trial["template"], trial["data"]
            n += 1
    return n


def _repair_web_scenes(scenes: List[Dict[str, Any]], report: Dict[str, Any], model: Optional[str]) -> List[str]:
    """Validate LLM web-slide specs; when a remote model wrote them, send the
    scenes that failed back once with their exact validation errors and keep
    the repaired specs that now pass. Returns the warnings that remain.

    The repair answer is as untrusted as the first one: it is validated by the
    same contract, may only touch the failed scenes' template/data, and any
    failure of the repair call leaves those scenes on the classic slide."""
    originals = {s.get("id"): (s.get("template"), s.get("data")) for s in scenes if isinstance(s, dict)}
    warnings = _apply_web_scene_contract(scenes, strict=False)
    used = str(report.get("backend", ""))
    if not warnings or not used.startswith(("claude_cli:", "anthropic:")):
        return warnings
    failed = []
    for s in scenes:
        sid = s.get("id") if isinstance(s, dict) else None
        tmpl, data = originals.get(sid, (None, None))
        if sid is not None and tmpl is not None and s.get("template") is None:
            err = next((w for w in warnings if w.startswith(f"scene {sid}: ")), "")
            failed.append({"id": sid, "template": tmpl, "data": data, "error": err})
    if not failed:
        return warnings
    prompt = (
        "Some web-slide specs in a video storyboard failed validation. Fix ONLY these scenes: keep "
        "their meaning and language, satisfy the contract below exactly (field names, list sizes, "
        "character limits), or switch to a template that fits better. Never invent numbers.\n\n"
        + _TEMPLATE_GUIDE
        + "\nFAILED SCENES (JSON):\n" + json.dumps(failed, ensure_ascii=False)
        + '\n\nReturn ONLY JSON: {"scenes": [{"id": "...", "template": "...", "data": {...}}]}'
    )
    backend, _, used_model = used.partition(":")
    try:
        raw = _call_storyboard_llm(prompt, backend=backend, model=used_model or model, report={})
        raw = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", raw.strip())
        fixes = {f.get("id"): f for f in json.loads(raw).get("scenes", []) if isinstance(f, dict)}
    except Exception as e:  # noqa: BLE001 — a failed repair keeps the classic slide
        logger.warning("web-slide repair call failed (%s)", type(e).__name__)
        return warnings
    remaining = list(warnings)
    for s in scenes:
        fix = fixes.get(s.get("id")) if isinstance(s, dict) else None
        if not fix or s.get("template") is not None or s.get("id") not in {f["id"] for f in failed}:
            continue
        trial = {"id": s["id"], "template": fix.get("template"), "data": fix.get("data")}
        if not _apply_web_scene_contract([trial], strict=False):
            s["template"], s["data"] = trial["template"], trial["data"]
            remaining = [w for w in remaining if not w.startswith(f"scene {s['id']}: ")]
            report["repaired"] = report.get("repaired", 0) + 1
    return remaining


def _apply_web_scene_contract(scenes: List[Dict[str, Any]], strict: bool) -> List[str]:
    """Validate each scene's web-slide fields (template/data/theme) in place.

    strict=True (operator-supplied storyboard): the first violation raises
    ValueError before any work starts. strict=False (LLM output): an invalid
    spec is removed from the scene, which then renders on the Pillow path;
    the returned warnings say what was dropped and why.
    """
    warnings: List[str] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        sid = scene.get("id", "?")
        template, data, theme = scene.get("template"), scene.get("data"), scene.get("theme")
        mp = scene.get("map")
        if mp is not None and not (isinstance(mp, dict) and set(mp) == {"focus"} and mp.get("focus") in MAP_LAYERS):
            if strict:
                raise ValueError(f"scene {sid}: map must be {{'focus': one of {', '.join(MAP_LAYERS)}}}")
            warnings.append(f"scene {sid}: invalid map overlay (dropped)")
            scene.pop("map", None)
        if template is not None and scene.get("kind") in ("screenshot", "screencast"):
            # a web template never triggers live capture (PLAN-0942 D10)
            scene["kind"] = "example"
        try:
            if theme is not None and theme not in THEMES:
                raise WebSceneError(f"unknown theme {theme!r}")
            if template is None:
                if data is not None:
                    raise WebSceneError("'data' given without a 'template'")
                continue
            scene["data"] = validate_scene_data(template, data if data is not None else {})
        except (WebSceneError, ValueError, TypeError, OverflowError) as e:
            if strict:
                raise ValueError(f"scene {sid}: {e}") from None
            warnings.append(f"scene {sid}: {e} (rendered without web template)")
            for key in ("template", "data", "theme"):
                scene.pop(key, None)
    return warnings


def _video_args() -> List[str]:
    """Encoder settings shared by every scene clip, so the concat demuxer can
    stream-copy them: 1920x1080, 30 fps, yuv420p, H.264 CRF 18, AAC 160k."""
    return [
        "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
    ]


def _link_or_copy(src: Path, dst: Path) -> None:
    try:
        os.link(src, dst)
    except OSError:  # filesystem without hard links
        shutil.copyfile(src, dst)


def _assemble_frames_clip(frames_dir: Path, n_frames: int, audio_path: Path, audio_duration: float,
                          out_path: Path, fps: int, loop_start: Optional[int] = None) -> float:
    """Animated frame sequence + narration -> scene clip; returns the clip length.

    The sequence ends with the slide's entrance animation. If the narration is
    longer, the last frame is held — or, when the slide has ambient motion
    (``loop_start``), frames[loop_start:] repeat seamlessly until the narration
    ends. If it is shorter, the audio is padded with silence so the reveal is
    never cut off mid-animation."""
    total = max(audio_duration, n_frames / fps)
    pattern = frames_dir / "%05d.png"
    needed = math.ceil(total * fps) + 1
    if loop_start is not None and 0 < loop_start < n_frames and needed > n_frames:
        # Hard links, not copies: a 60 s scene is 1800 entries pointing at ~150 files.
        seq = frames_dir / "seq"
        seq.mkdir(exist_ok=True)
        period = n_frames - loop_start
        for j in range(needed):
            src = j if j < n_frames else loop_start + (j - loop_start) % period
            _link_or_copy(frames_dir / f"{src:05d}.png", seq / f"{j:05d}.png")
        pattern = seq / "%05d.png"
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps), "-i", str(pattern),
        "-i", str(audio_path),
        "-filter_complex",
        f"[0:v]tpad=stop_mode=clone:stop_duration={total + 1.0:.3f},fps=30,format=yuv420p[v];"
        f"[1:a]apad=whole_dur={total:.3f}[a]",
        "-map", "[v]", "-map", "[a]",
        *_video_args(),
        "-t", f"{total:.3f}",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return total


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
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease:flags=lanczos,"
               "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p",
        *_video_args(),
        "-tune", "stillimage",
        "-shortest",
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


SUPPORTED_TTS_ENGINES = ("openai", "auto", "gtts")
DEFAULT_TTS_ENGINE = "openai"


def _storyboard_from_operator(raw: Any, task: str, max_duration_minutes: int) -> Storyboard:
    """An operator-supplied storyboard skips the LLM but not a single check:
    the same validation primitive as LLM output, plus a strict web-slide contract."""
    if not isinstance(raw, dict) or not isinstance(raw.get("scenes"), list) or not raw["scenes"]:
        raise ValueError("storyboard must be an object with a non-empty 'scenes' list")
    sb = json.loads(json.dumps(raw))  # deep copy, JSON types only
    sb.setdefault("didactic_strategy", "rich_visual")
    validate_storyboard_dict(sb, max_duration_minutes).raise_if_invalid()
    _apply_web_scene_contract(sb["scenes"], strict=True)
    return Storyboard(
        id=str(sb.get("id") or f"sb_{uuid.uuid4().hex[:8]}"),
        task=task,
        scenes=[Scene.from_dict(sc) for sc in sb["scenes"]],
        generated_at=datetime.now(),
        didactic_strategy=sb["didactic_strategy"],
    )


class _WebRendererSession:
    """Opens the browser on the first web scene and keeps it for the job.
    A browser that cannot start disables web rendering for the rest of the job;
    every affected scene is reported as a fallback, never silently swapped."""

    def __init__(self, enabled: bool, fps: int, tokens: Optional[Dict[str, Any]]):
        self.enabled = bool(enabled)
        self.fps = fps
        self.tokens = tokens
        self._renderer: Optional[WebSlideRenderer] = None
        self._unavailable: Optional[str] = None
        self.layout_log: List[Dict[str, Any]] = []  # one entry per scene whose layout collided

    async def render(self, scene: Scene, duration_s: float, out_dir: Path, **kw) -> tuple:
        """(frames, None) on success; (None, reason) on a fallback; (None, None) when
        web slides are switched off for the job (configuration, not a fallback)."""
        if not self.enabled:
            return None, None
        if self._unavailable:
            return None, self._unavailable
        if duration_s > MAX_SCENE_SECONDS:
            return None, f"narration longer than {MAX_SCENE_SECONDS:.0f}s"
        if self._renderer is None:
            renderer = WebSlideRenderer(fps=self.fps, tokens=self.tokens)
            try:
                self._renderer = await renderer.__aenter__()
            except WebRenderError as e:
                self._unavailable = f"browser unavailable: {e}"
                logger.warning("web slides disabled for this job: %s", e)
                return None, self._unavailable
        try:
            frames = await self._renderer.render(scene.template, scene.data or {}, duration_s, out_dir, **kw)
            if frames.layout_issues:
                frames = await self._resolve_collision(scene, frames, duration_s, out_dir, kw)
            return frames, None
        except Exception as e:  # noqa: BLE001 — specs may come from an LLM: any failure = classic slide
            logger.warning("web slide render failed (%s), using classic slide", type(e).__name__)
            shutil.rmtree(out_dir, ignore_errors=True)
            return None, f"{type(e).__name__}: {e}"[:200]

    async def _resolve_collision(self, scene: Scene, frames, duration_s: float, out_dir: Path, kw: dict):
        """Text, shapes or boxes collide (web_layout). Swap in a quote slide built from the
        scene's narration when that one is clean; otherwise keep the original and say so."""
        entry = {"scene": scene.id, "template": scene.template, "issues": format_issues(frames.layout_issues)[:6],
                 "action": "kept"}
        text = " ".join((scene.narration_text or "").split())
        if text and scene.template != "quote":
            first = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
            first = first if len(first) <= 200 else first[:197].rstrip() + "..."
            trial = {"template": "quote", "data": {"quote": first, "locale": _detect_lang(text)}}
            if not _apply_web_scene_contract([trial], strict=False):
                alt_dir = out_dir.parent / (out_dir.name + "_alt")
                try:
                    alt = await self._renderer.render("quote", trial["data"], duration_s, alt_dir, **kw)
                except Exception:  # noqa: BLE001 — the original frames stay
                    alt = None
                if alt is not None and not alt.layout_issues:
                    shutil.rmtree(out_dir, ignore_errors=True)
                    alt_dir.rename(out_dir)
                    moved = type(alt)(out_dir / f.name for f in alt)
                    moved.loop_start = alt.loop_start
                    entry["action"] = "replaced_with_quote"
                    self.layout_log.append(entry)
                    return moved
                shutil.rmtree(alt_dir, ignore_errors=True)
        self.layout_log.append(entry)
        return frames

    async def close(self) -> None:
        if self._renderer is not None:
            await self._renderer.__aexit__(None, None, None)
            self._renderer = None


async def orchestrate_video(
    job_id: str,
    task: str,
    storage_base: str,
    tts_engine: str = DEFAULT_TTS_ENGINE,
    max_duration_minutes: int = 60,
    storyboard_backend: str = "ollama",
    storyboard_model: Optional[str] = None,
    storyboard: Optional[Dict[str, Any]] = None,
    web_slides: bool = True,
    web_theme: str = "dark",
    web_fps: int = FPS_DEFAULT,
    web_tokens_path: Optional[str] = None,
    grounding_pack: Optional[Dict[str, Any]] = None,
    grounding_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Main orchestrator Skill:
    1. LLM: Task → Storyboard (JSON)
    2. Real synthesis per scene: TTS narration (gTTS) + slide image (ffmpeg drawtext) + scene clip
    3. Real ffmpeg concat → final MP4 (no subtitles: no caption file, nothing burned in)
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
        if web_theme not in THEMES:
            raise ValueError(f"web_theme must be one of {THEMES}")
        if isinstance(web_fps, bool) or not isinstance(web_fps, int) or not 12 <= web_fps <= 60:
            raise ValueError("web_fps must be an integer between 12 and 60")
        web_tokens = load_tokens(Path(web_tokens_path)) if web_tokens_path else None

        # Output always lives in this store's own directory — the host cannot
        # be talked into writing a tenant's video anywhere else.
        out_root = storage.videos_dir / job_id
        scenes_dir = out_root / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Generate Storyboard via LLM
        _update_job_progress(storage, job, "storyboard_generating", 0, "Analyzing task...")

        # PLAN-0942: the host built and gated the pack; anything malformed is ignored.
        pack = validate_pack(grounding_pack) if grounding_pack is not None else None
        if storyboard is not None:
            storyboard = _storyboard_from_operator(storyboard, task, max_duration_minutes)
            storyboard.grounding = {"status": "not_applicable", "reason": "operator_storyboard"} if pack else None
        else:
            storyboard = await generate_storyboard_with_llm(
                task, max_duration_minutes, backend=storyboard_backend, model=storyboard_model,
                grounding=pack,
            )
            if storyboard.grounding is None:
                if pack is not None:  # a pack, but the backend is local
                    storyboard.grounding = {"status": "unavailable", "reason": "local_storyboard_model"}
                elif isinstance(grounding_status, dict) and grounding_status.get("status") in ("refused", "unavailable"):
                    storyboard.grounding = {"status": grounding_status["status"],
                                            "reason": str(grounding_status.get("reason", ""))[:60]}
        if storyboard.grounding and storyboard.grounding.get("status") in ("grounded", "grounded_with_unverified"):
            g_info = storyboard.grounding
            note = f"Grounded in {len(g_info['entities'])} knowledge-base decisions"
            if g_info["status"] == "grounded_with_unverified":
                note += f"; {g_info['unverified']['count']} detail(s) not found in the sources"
            _update_job_progress(storage, job, "storyboard_generating", 100, note)
        job.storyboard = storyboard
        _update_job_progress(
            storage, job, "storyboard_generating", 100,
            f"Generated {len(storyboard.scenes)} scenes",
            total_scenes=len(storyboard.scenes),
        )

        # Didactic validation (ADR-0004): re-runs the same cheap, LLM-free
        # primitive generate_storyboard_with_llm() already used for the hard
        # gate, this time to surface soft warnings (text-budget, timing,
        # narrative flow) into the audit/feedback trail. Never raises here —
        # a storyboard that passed the hard gate is usable; warnings inform,
        # they don't block.
        didactic_validation = validate_storyboard(storyboard, max_duration_minutes)

        emit_feedback(
            job_id=job_id,
            event_type="storyboard_generated",
            metrics={
                "scenes_count": len(storyboard.scenes),
                "total_duration_ms": sum(s.duration_ms for s in storyboard.scenes),
                "quality_score": 0.8,
                "didactic_strategy": storyboard.didactic_strategy,
                "didactic_warnings": len(didactic_validation.warnings),
                **didactic_validation.metrics,
            }
        )
        if didactic_validation.warnings:
            logger.info(
                "[%s] Didactic warnings (%d): %s", job_id, len(didactic_validation.warnings),
                "; ".join(f"{w.scene_id}:{w.rule}" for w in didactic_validation.warnings),
            )

        # Step 2: Real per-scene synthesis (audio + slide + clip)
        _update_job_progress(storage, job, "skills_running", 0, "Starting scene production...")

        total = len(storyboard.scenes)
        clip_paths: List[Path] = []
        scene_audio_s: List[float] = []
        tts_providers_used: List[str] = []
        renderers_used: List[str] = []
        web_fallbacks: List[Dict[str, Any]] = []
        web = _WebRendererSession(enabled=web_slides, fps=web_fps, tokens=web_tokens)

        try:
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
                lang = _detect_lang(narration)
                if tts_engine == "auto":
                    tts_provider_used = _synthesize_narration_chain(narration, audio_path, lang)
                elif tts_engine == "openai":
                    _synthesize_narration_openai(narration, audio_path, lang)
                    tts_provider_used = "openai"
                else:
                    _synthesize_narration(narration, audio_path, lang)
                    tts_provider_used = "gtts"
                audio_duration = _ffprobe_duration(audio_path)

                _update_job_progress(
                    storage, job, "skills_running", pct,
                    f"Scene {i}/{total}: rendering slide...",
                    current_scene=i, total_scenes=total,
                )
                frames: Optional[List[Path]] = None
                if scene.kind == "screenshot":
                    await _render_screenshot_scene(scene, image_path)
                    renderers_used.append("screenshot")
                else:
                    if scene.template:
                        frames, reason = await web.render(
                            scene, audio_duration, scenes_dir / f"scene_{i:03d}_frames",
                            theme=scene.theme or web_theme, scene_index=i, total_scenes=total, lang=lang,
                            map_focus=(scene.map or {}).get("focus") if isinstance(scene.map, dict) else None,
                        )
                        if frames is None and reason:
                            web_fallbacks.append({"scene": i, "reason": reason})
                            emit_feedback(job_id=job_id, event_type="web_render_fallback",
                                          metrics={"scene": i, "reason": reason})
                            _update_job_progress(
                                storage, job, "skills_running", pct,
                                f"Scene {i}/{total}: web slide unavailable ({reason}) — using classic slide",
                                current_scene=i, total_scenes=total,
                            )
                    if frames:
                        loop_start = getattr(frames, "loop_start", None)
                        shutil.copyfile(frames[loop_start - 1] if loop_start else frames[-1], image_path)
                        renderers_used.append("web")
                    else:
                        _render_slide_image(
                            scene, image_path, strategy=storyboard.didactic_strategy,
                            scene_index=i, total_scenes=total,
                        )
                        renderers_used.append("pillow")

                _update_job_progress(
                    storage, job, "skills_running", pct,
                    f"Scene {i}/{total}: encoding clip...",
                    current_scene=i, total_scenes=total,
                )
                if frames:
                    try:
                        _assemble_frames_clip(frames[0].parent, len(frames), audio_path, audio_duration,
                                              clip_path, web_fps, loop_start=getattr(frames, "loop_start", None))
                    finally:
                        # ~0.5-1 MB per frame; the clip is the artifact, the frames are scratch
                        shutil.rmtree(frames[0].parent, ignore_errors=True)
                else:
                    _assemble_scene_clip(image_path, audio_path, clip_path)

                clip_paths.append(clip_path)
                scene_audio_s.append(audio_duration)
                tts_providers_used.append(tts_provider_used)
        finally:
            await web.close()

        measured_s = sum(scene_audio_s)
        if measured_s > max_duration_minutes * 60:
            raise ValueError(
                f"Narrated length {measured_s:.0f}s exceeds the {max_duration_minutes}-minute limit"
            )

        # Step 3: Concat scenes
        _update_job_progress(storage, job, "skills_running", 92, "Assembling final video...")

        video_path = out_root / "output.mp4"
        _concat_clips(clip_paths, video_path, out_root)

        # The artifact is the truth: report what ffprobe measures on the final file.
        duration_seconds = round(_ffprobe_duration(video_path))
        file_size_mb = round(video_path.stat().st_size / (1024 * 1024), 2)

        # ADR-2211 auditability: record which TTS tier actually spoke each
        # scene, not just which engine was configured — "openai" if every
        # scene reached tier 1, "mixed" if the chain fell through on some
        # scenes (e.g. a transient API failure), or the single provider name
        # when tts_engine wasn't "auto" (no chain, no fallback possible).
        distinct_providers = set(tts_providers_used)
        provider_used = distinct_providers.pop() if len(distinct_providers) == 1 else "mixed"

        video_output = VideoOutput(
            job_id=job_id,
            video_path=str(video_path),
            metadata={
                "duration_seconds": duration_seconds,
                "resolution": "1920x1080",
                "fps": 30,
                "file_size_mb": file_size_mb,
                "scenes": total,
                "tts_engine": tts_engine,
                "tts_provider_used": provider_used,
                "renderers": renderers_used,
                "layout_collisions": web.layout_log,
                "web_scenes": renderers_used.count("web"),
                "web_render_fallbacks": web_fallbacks,
                "storyboard_llm": storyboard.llm_backend or "operator",
                "storyboard_template_repairs": storyboard.template_repairs,
                "storyboard_template_warnings": storyboard.template_warnings,
                "grounding": storyboard.grounding,
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
        tts_engine=config.get("tts_engine", DEFAULT_TTS_ENGINE),
        max_duration_minutes=config.get("max_duration_minutes", 60),
        storyboard_backend=config.get("storyboard_backend", "ollama"),
        storyboard_model=config.get("storyboard_model"),
        storyboard=config.get("storyboard"),
        web_slides=config.get("web_slides", True),
        web_theme=config.get("web_theme", "dark"),
        web_fps=config.get("web_fps", FPS_DEFAULT),
        web_tokens_path=config.get("web_tokens_path"),
        grounding_pack=config.get("grounding_pack"),
        grounding_status=config.get("grounding_status"),
    )
