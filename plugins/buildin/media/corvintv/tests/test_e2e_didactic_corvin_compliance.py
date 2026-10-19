"""E2E: real didactic video production about "Corvin + Compliance" (ADR-0004).

This is the e2e-wiring-proof + e2e-driven-iteration test for the didactic
integration (narration_validator, didactic-constrained prompt, vector-icon
renderer). It deliberately does NOT mock the pipeline: real Ollama inference
(qwen3:1.7b, local, no API key), real gTTS synthesis, real Pillow rendering,
real ffmpeg assembly — because a mocked "E2E" test proves the mock works, not
the pipeline.

Testing feedback applied (session memory):
  - "Fehlerbehandlung auf Primitive-Ebene, nicht Callsite-Band-Aid": the
    call-site-proof test below asserts validate_storyboard_dict/
    validate_storyboard are the ONLY duration/scene-count checks in skill.py
    — a regression that reintroduces an inline `if len(scenes) > 100: raise`
    at a call site fails this test, not just a code-review nit.
  - "Test-Metriken die Summe messen, nicht Backend einzeln": the pipeline
    test asserts the SUMMED, ffprobe-measured facts of the final output.mp4
    (total duration, total scenes muxed) — not each worker's self-reported
    number in isolation, which is exactly what let a prior video-quality
    panel show a fabricated score while ffprobe would have caught it
    (ADR-0696 amendment).
  - "Tote Mechanismen brauchen Call-Site-Tests": every new function
    (detect_didactic_strategy, validate_storyboard_dict, validate_storyboard,
    _draw_icon, _detect_icon) gets an explicit grep-based proof that
    orchestrate_video()/generate_storyboard_with_llm() actually calls it —
    not just a unit test that imports and calls it directly.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from src.models import Scene, Storyboard
from src.narration_validator import (
    validate_storyboard_dict,
    validate_storyboard,
    CHAR_BUDGETS,
)
from src.skill import (
    detect_didactic_strategy,
    generate_storyboard_with_llm,
    orchestrate_video,
    _render_slide_image,
    _detect_icon,
)
from src.storage import VideoStorage, get_storage, reset_storage
from src.models import VideoJob


SKILL_PY = Path(__file__).parent.parent / "src" / "skill.py"
OLLAMA_REACHABLE = shutil.which("curl") is not None
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _ollama_up() -> bool:
    try:
        r = subprocess.run(
            ["curl", "-s", "-m", "2", "http://localhost:11434/api/tags"],
            capture_output=True, timeout=3,
        )
        return r.returncode == 0 and b"models" in r.stdout
    except Exception:
        return False


# ===========================================================================
# PART 1 — Call-site-wiring proof (the "tote Mechanismen" feedback)
# ===========================================================================

class TestCallSiteWiring:
    """Proves the new mechanisms have a real caller, not just a unit test
    that imports them directly. Dead-mechanism class of bug: a function that
    is defined, unit-tested in isolation, and never invoked by production
    code."""

    def test_validator_is_called_from_generate_storyboard(self, monkeypatch):
        """Behavioural: an LLM storyboard over the scene ceiling is refused by
        generate_storyboard_with_llm — removing its validate_storyboard_dict call lets it through."""
        import asyncio
        import json

        from src import skill

        scenes = [{"id": f"s{i}", "kind": "problem", "duration_ms": 8000,
                   "narration_text": "x" * 200, "visual_description": "d"} for i in range(150)]
        monkeypatch.setattr(skill, "_call_storyboard_llm", lambda *a, **k: json.dumps({"scenes": scenes}))
        with pytest.raises(Exception, match=r"(?i)scene"):
            asyncio.run(skill.generate_storyboard_with_llm("t", 60, backend="claude_cli"))

    def test_validator_is_called_from_orchestrate_video(self, run_orchestrate):
        """Behavioural: orchestrate_video runs the didactic validation on the storyboard it produces."""
        scenes = [{"id": "s1", "kind": "problem", "duration_ms": 8000,
                   "narration_text": "Ein kurzer Satz fuer den Test, der lang genug ist um sauber zu validieren.",
                   "visual_description": "shield icon"}]
        result, spies = run_orchestrate(scenes, spies_for=("validate_storyboard",))
        assert result["success"] is True
        assert len(spies["validate_storyboard"]) == 1

    def test_no_duplicated_ad_hoc_scene_count_check(self):
        """The single-primitive invariant: MAX_SCENES / duration-ceiling
        checks must exist in exactly one place (narration_validator), not
        re-implemented as an inline `if ...: raise` at any call site."""
        src = SKILL_PY.read_text()
        inline_violations = re.findall(r"if\s+len\([^)]*scenes[^)]*\)\s*>\s*\d+", src)
        assert not inline_violations, (
            f"Found {len(inline_violations)} inline scene-count check(s) in skill.py "
            f"— these duplicate narration_validator.MAX_SCENES and will drift: {inline_violations}"
        )
        inline_duration_violations = re.findall(r"if\s+total_duration\s*>\s*max_ms", src)
        assert not inline_duration_violations, (
            "Found inline total-duration check in skill.py — duplicates "
            "narration_validator's primitive, must call validate_storyboard_dict() instead"
        )

    def test_icon_renderer_is_called_from_render_slide_image(self, tmp_path):
        """Behavioural: a rich_visual slide whose visual_description names an icon has icon pixels
        in the icon region; the same slide without a recognisable icon word does not. Removing the
        _detect_icon/_draw_icon call makes the two renders identical there."""
        from PIL import Image, ImageChops

        def render(desc, name, strategy="rich_visual"):
            out = tmp_path / name
            _render_slide_image(Scene(id="s", kind="solution", duration_ms=8000, narration_text="n",
                                      visual_description=desc), out, strategy=strategy)
            return Image.open(out).convert("RGB").crop((540, 100, 740, 260))  # 140 px icon at (640, 180)

        assert _detect_icon("shield icon") == "shield" and _detect_icon("calm mood") is None
        with_icon = render("shield icon", "a.png")
        without = render("calm mood", "b.png")
        assert ImageChops.difference(with_icon, without).getbbox() is not None, "no icon pixels drawn"
        # the icon is a rich_visual feature: minimal_visual stays text-first
        minimal = render("shield icon", "c.png", strategy="minimal_visual")
        assert ImageChops.difference(minimal, without).getbbox() is None

    def test_strategy_detection_is_called_from_generate_storyboard(self, monkeypatch):
        """Behavioural: the prompt sent to the model carries the strategy detected from the task."""
        import asyncio

        from src import skill

        prompts = []

        def capture(prompt, *a, **k):
            prompts.append(prompt)
            raise RuntimeError("stop after capture")

        monkeypatch.setattr(skill, "_call_storyboard_llm", capture)
        for task, expected in (("Explain the loop principle", "minimal_visual"),
                               ("Explain the system architecture", "rich_visual")):
            assert detect_didactic_strategy(task) == expected
            with pytest.raises(RuntimeError):
                asyncio.run(skill.generate_storyboard_with_llm(task, 5, backend="claude_cli"))
            assert f"Didactic strategy: {expected}" in prompts[-1]
        # an explicit strategy wins over detection
        with pytest.raises(RuntimeError):
            asyncio.run(skill.generate_storyboard_with_llm("Explain the system architecture", 5,
                                                           backend="claude_cli", didactic_strategy="minimal_visual"))
        assert "Didactic strategy: minimal_visual" in prompts[-1]


# ===========================================================================
# PART 2 — Unit-level proof that the primitive actually enforces the rules
# ===========================================================================

class TestNarrationValidatorPrimitive:
    def test_rejects_oversized_scene_count(self):
        sb = {
            "didactic_strategy": "rich_visual",
            "scenes": [{"id": f"s{i}", "kind": "solution", "duration_ms": 5000, "narration_text": "x"} for i in range(101)],
        }
        result = validate_storyboard_dict(sb, max_duration_minutes=60)
        assert not result.valid
        assert any(e.rule == "max_scenes" for e in result.errors)

    def test_rejects_total_duration_over_cap(self):
        sb = {
            "didactic_strategy": "rich_visual",
            "scenes": [{"id": "s1", "kind": "solution", "duration_ms": 400_000, "narration_text": "x"}],
        }
        result = validate_storyboard_dict(sb, max_duration_minutes=5)
        assert not result.valid
        assert any(e.rule == "max_total_duration" for e in result.errors)

    def test_warns_on_char_budget_violation_minimal_visual(self):
        long_text = "word " * 100  # way over 250ch minimal_visual budget
        sb = {
            "didactic_strategy": "minimal_visual",
            "scenes": [{"id": "s1", "kind": "solution", "duration_ms": 12000, "narration_text": long_text}],
        }
        result = validate_storyboard_dict(sb, max_duration_minutes=10)
        assert result.valid  # soft warning, not a hard error
        assert any(w.rule == "char_budget_high" for w in result.warnings)

    def test_detect_didactic_strategy_system_task_is_rich_visual(self):
        assert detect_didactic_strategy("Erkläre die Compliance-Architektur von CorvinOS") == "rich_visual"

    def test_detect_didactic_strategy_concept_task_is_minimal_visual(self):
        assert detect_didactic_strategy("Why does the learning loop work?") == "minimal_visual"


# ===========================================================================
# PART 3 — Icon rendering proof (real PNG, real pixels, no font-glyph risk)
# ===========================================================================

class TestIconRendering:
    def test_detect_icon_from_visual_description(self):
        assert _detect_icon("shield icon for identity") == "shield"
        assert _detect_icon("chain with four links") == "chain"
        assert _detect_icon("nothing relevant here") is None

    def test_render_slide_produces_real_png_with_accent_color(self, tmp_path):
        scene = Scene(
            id="s1", kind="solution", duration_ms=12000,
            narration_text="Zero-Trust-Architektur verifiziert jede Anfrage.",
            visual_description="shield icon for security",
        )
        out = tmp_path / "slide.png"
        _render_slide_image(scene, out, strategy="rich_visual")

        assert out.exists()
        with open(out, "rb") as f:
            assert f.read(8) == b"\x89PNG\r\n\x1a\n"

        from PIL import Image
        img = Image.open(out)
        assert img.size == (1280, 720)
        # "solution" kind must use the trust-teal accent (0,168,150) somewhere
        # in the rendered pixels — proves _draw_icon/_KIND_ACCENT actually ran,
        # not just "a PNG exists".
        pixels = img.load()
        found_accent = any(
            pixels[x, y] == (0, 168, 150)
            for x in range(0, img.width, 4)
            for y in range(0, img.height, 4)
        )
        assert found_accent, "Expected trust-teal accent color (0,168,150) in rendered slide pixels"


# ===========================================================================
# PART 4 — Full pipeline E2E: real video about "Corvin + Compliance"
# ===========================================================================

@pytest.mark.e2e
@pytest.mark.integration
class TestFullPipelineCorvinCompliance:
    """The deliverable this task asked for: an E2E test that produces a real
    video about Corvin + Compliance and validates the result with SUMMED,
    independently measured facts (ffprobe) — not trusting any one worker's
    self-report."""

    @pytest.mark.asyncio
    async def test_produces_real_video_about_corvin_compliance(self, tmp_path):
        if not _ollama_up():
            pytest.skip("Ollama not reachable on localhost:11434 — cannot generate a real storyboard")
        if not FFMPEG_AVAILABLE:
            pytest.skip("ffmpeg not on PATH — cannot assemble a real video")

        reset_storage()
        # video-storage-convention: the HOST passes a tenant-scoped base dir;
        # the plugin never defaults to ~/.corvin. tmp_path stands in for
        # <tenant_home>/video_producer here.
        storage_base = str(tmp_path / "video_producer")
        storage = get_storage(storage_base)

        job_id = "job_corvin_compliance_e2e"
        task = (
            "Erkläre in einem kurzen Video, wie CorvinOS Compliance für "
            "autonome KI-Agenten sicherstellt: Identität, Audit-Trail und "
            "Zero-Trust-Architektur."
        )
        job = VideoJob(id=job_id, task=task)
        storage.save_job(job)

        result = await orchestrate_video(
            job_id=job_id,
            task=task,
            storage_base=storage_base,
            tts_engine="gtts",
            max_duration_minutes=3,
            storyboard_backend="ollama",
        )

        # --- Primitive-level proof: the job's own validator ran and the
        # storyboard carries a real didactic_strategy (not a hardcoded default
        # that never changes).
        final_job = storage.get_job(job_id)
        assert final_job.status == "complete", final_job.error_message
        assert final_job.storyboard is not None
        assert final_job.storyboard.didactic_strategy in ("minimal_visual", "rich_visual")

        validation = validate_storyboard(final_job.storyboard, max_duration_minutes=3)
        assert validation.valid, f"Produced storyboard fails its own validator: {validation.errors}"

        # --- SUMMED, independently measured facts (not any single worker's
        # self-report) — the "miss den Summen-Wert, nicht das Backend"
        # feedback applied for real:
        video_path = Path(result["video_path"])
        assert video_path.exists(), "output.mp4 was not created"
        assert video_path.stat().st_size > 10_000, "output.mp4 suspiciously small — likely not a real encode"

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
             "-show_entries", "stream=codec_type,codec_name",
             "-of", "json", str(video_path)],
            capture_output=True, text=True, check=True,
        )
        import json as _json
        probe_data = _json.loads(probe.stdout)
        measured_duration_s = float(probe_data["format"]["duration"])
        measured_size_bytes = int(probe_data["format"]["size"])

        # Sum over all scenes (the worker's own report) must be close to the
        # ffprobe-measured total — this is the actual aggregate check, done
        # against an INDEPENDENT measurement, not the worker's say-so.
        reported_duration_s = result["duration_seconds"]
        assert abs(measured_duration_s - reported_duration_s) <= 2.0, (
            f"ffprobe measured {measured_duration_s:.1f}s but orchestrate_video reported "
            f"{reported_duration_s}s — worker-reported sum drifted from the real artifact"
        )

        codecs = {s["codec_type"]: s["codec_name"] for s in probe_data["stream"]} if isinstance(probe_data.get("stream"), list) else {
            s["codec_type"]: s["codec_name"] for s in ([probe_data["stream"]] if "stream" in probe_data else [])
        }
        # ffprobe -show_entries stream=... with -of json nests under "streams" (plural);
        # re-probe defensively with the documented key.
        probe2 = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(video_path)],
            capture_output=True, text=True, check=True,
        )
        streams = _json.loads(probe2.stdout)["streams"]
        codec_types = {s["codec_type"] for s in streams}
        assert "video" in codec_types and "audio" in codec_types, (
            f"Expected a real muxed video+audio stream, got codec_types={codec_types}"
        )

        # No subtitles: no caption file, no subtitle stream.
        assert "srt_path" not in result
        assert not list(video_path.parent.glob("*.srt"))
        assert "subtitle" not in codec_types

        # Compliance-content sanity: this video was commissioned to be ABOUT
        # Corvin + Compliance — assert the actual generated narration (not
        # the task string) mentions the domain, proving the LLM call produced
        # on-topic content rather than a generic placeholder.
        all_narration = " ".join((s.narration_text or "") for s in final_job.storyboard.scenes).lower()
        domain_terms = ("compliance", "audit", "identität", "identity", "zero-trust", "corvin", "agent")
        assert any(term in all_narration for term in domain_terms), (
            f"Generated narration does not mention any compliance/Corvin domain term: {all_narration[:300]!r}"
        )

        print(f"\n✓ E2E video produced: {video_path} ({measured_size_bytes} bytes, {measured_duration_s:.1f}s measured)")
        print(f"✓ Scenes: {len(final_job.storyboard.scenes)}, strategy: {final_job.storyboard.didactic_strategy}")
        print(f"✓ Validation: {validation.metrics}")
