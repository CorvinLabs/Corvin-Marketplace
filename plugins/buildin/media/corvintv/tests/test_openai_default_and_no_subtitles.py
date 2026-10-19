"""OpenAI TTS is the default narration engine; subtitles do not exist anywhere in the output.

OpenAI itself is replaced by a fake `openai` module (no network, no spend) so the
tests can inject failures; a separate opt-in test (RUN_LIVE_TTS=1) makes one real call.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest
from PIL import Image

from src import skill
from src.models import Scene, VideoJob
from src.storage import get_storage


def install_fake_openai(monkeypatch, fail=None, calls=None):
    """A stand-in for `openai.OpenAI` whose audio.speech.create writes a real WAV."""
    calls = calls if calls is not None else []
    mod = types.ModuleType("openai")

    class _Speech:
        def create(self, model, voice, input):
            calls.append({"model": model, "voice": voice, "input": input})
            if fail:
                raise fail
            seconds = max(1.0, len(input.split()) / 2.5)

            class R:
                def stream_to_file(self, path):
                    import wave
                    with wave.open(str(path), "wb") as w:
                        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
                        w.writeframes(b"\x00\x00" * int(24000 * seconds))
            return R()

    class OpenAI:
        def __init__(self, api_key=None, timeout=None, max_retries=None):
            # a call without a timeout could hold a job worker forever (review 2026-10-10)
            assert timeout is not None and timeout <= 120, timeout
            calls.append({"api_key_given": bool(api_key)})
            self.audio = types.SimpleNamespace(speech=_Speech())

    mod.OpenAI = OpenAI
    monkeypatch.setitem(sys.modules, "openai", mod)
    return calls


# ── defaults ──

def test_openai_is_the_default_engine_everywhere():
    import inspect
    assert skill.DEFAULT_TTS_ENGINE == "openai"
    assert skill.SUPPORTED_TTS_ENGINES[0] == "openai"
    assert inspect.signature(skill.orchestrate_video).parameters["tts_engine"].default == "openai"
    # the host's entry point: a config without tts_engine reaches the orchestrator as "openai"
    import asyncio
    seen = {}

    async def spy(**kw):
        seen.update(kw)
        return {}

    real = skill.orchestrate_video
    skill.orchestrate_video = spy
    try:
        asyncio.run(skill.start_video_production("job_x", "t", {"storage_base": "/nonexistent"}))
    finally:
        skill.orchestrate_video = real
    assert seen["tts_engine"] == "openai"


# ── strict engine ──

def test_strict_openai_uses_tts_1_hd_onyx_and_the_host_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-1234567890")
    monkeypatch.delenv("CORVIN_TTS_OPENAI_KEY", raising=False)
    calls = install_fake_openai(monkeypatch)
    skill._synthesize_narration_openai("Hallo Welt", tmp_path / "a.mp3", "de")
    assert {"model": "tts-1-hd", "voice": "onyx", "input": "Hallo Welt"} in calls
    assert {"api_key_given": True} in calls


def test_dedicated_tts_key_wins_over_the_generic_one(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-generic-000000000")
    monkeypatch.setenv("CORVIN_TTS_OPENAI_KEY", "sk-dedicated-111111")
    assert skill._openai_api_key() == "sk-dedicated-111111"


def test_missing_key_fails_the_narration_instead_of_switching_voice(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CORVIN_TTS_OPENAI_KEY", raising=False)
    install_fake_openai(monkeypatch)
    with pytest.raises(RuntimeError, match="no key is configured"):
        skill._synthesize_narration_openai("x", tmp_path / "a.mp3", "de")
    assert not (tmp_path / "a.mp3").exists()


def test_api_failure_is_reported_and_the_key_never_leaks(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-secret-ABCDEFGH123")
    install_fake_openai(monkeypatch, fail=RuntimeError("401 Incorrect API key provided: sk-live-secret-ABCDEFGH123"))
    with pytest.raises(RuntimeError) as e:
        skill._synthesize_narration_openai("x", tmp_path / "a.mp3", "de")
    assert "sk-live" not in str(e.value) and "ABCDEFGH123" not in str(e.value)
    assert "OpenAI TTS failed" in str(e.value)


def test_chain_tier_declines_quietly_and_logs_no_key(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-secret-ABCDEFGH123")
    install_fake_openai(monkeypatch, fail=RuntimeError("quota: sk-live-secret-ABCDEFGH123"))
    assert skill._tts_tier_openai("x", tmp_path / "a.mp3", "de") is False
    assert "ABCDEFGH123" not in caplog.text


# ── no subtitles ──

STORYBOARD = {"id": "sb1", "scenes": [
    {"id": "s1", "kind": "title", "duration_ms": 8000, "narration_text": "Das ist der gesprochene Text der ersten Szene."},
    {"id": "s2", "kind": "summary", "duration_ms": 8000, "narration_text": "Und hier der gesprochene Text der zweiten Szene.",
     "template": "hero", "data": {"title": "Titel"}},
]}


@pytest.mark.e2e
async def test_default_job_speaks_with_openai_and_produces_no_subtitles(tmp_path, monkeypatch):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg missing")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-1234567890")
    monkeypatch.delenv("CORVIN_TTS_OPENAI_KEY", raising=False)
    calls = install_fake_openai(monkeypatch)
    base = str(tmp_path / "t"); Path(base).mkdir()
    get_storage(base).save_job(VideoJob(id="job_oa", task="t"))

    # exactly what the console passes when the operator never touched the settings
    result = await skill.start_video_production("job_oa", "t", {"storage_base": base, "max_duration_minutes": 3, "storyboard": STORYBOARD})

    assert result["metadata"]["tts_engine"] == "openai" and result["metadata"]["tts_provider_used"] == "openai"
    spoken = [c["input"] for c in calls if "input" in c]
    assert spoken == [s["narration_text"] for s in STORYBOARD["scenes"]]
    assert all(c["voice"] == "onyx" and c["model"] == "tts-1-hd" for c in calls if "model" in c)

    video = Path(result["video_path"])
    assert "srt_path" not in result and not list(video.parent.rglob("*.srt")) and not list(video.parent.rglob("*.vtt"))
    streams = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(video)],
                                        capture_output=True, text=True, check=True).stdout)["streams"]
    assert {s["codec_type"] for s in streams} == {"video", "audio"}
    assert get_storage(base).get_video_output("job_oa").srt_path is None


@pytest.mark.e2e
async def test_openai_failure_fails_the_job_it_does_not_change_the_narrator(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-1234567890")
    install_fake_openai(monkeypatch, fail=RuntimeError("429 insufficient_quota"))
    base = str(tmp_path / "t"); Path(base).mkdir()
    get_storage(base).save_job(VideoJob(id="job_fail", task="t"))
    with pytest.raises(RuntimeError, match="OpenAI TTS failed"):
        await skill.start_video_production("job_fail", "t", {"storage_base": base, "max_duration_minutes": 3, "storyboard": STORYBOARD})
    job = get_storage(base).get_job("job_fail")
    assert job.status == "error" and "insufficient_quota" in job.error_message
    assert not (Path(base) / "videos" / "job_fail" / "output.mp4").exists()


def test_classic_slide_never_draws_the_spoken_text(tmp_path):
    """Same scene, two different narrations -> byte-identical slide: the narration is not on it."""
    def render(narration, name):
        out = tmp_path / name
        scene = Scene(id="s", kind="example", duration_ms=8000, narration_text=narration, visual_description="check icon")
        skill._render_slide_image(scene, out, strategy="rich_visual", scene_index=2, total_scenes=5)
        return hashlib.sha256(out.read_bytes()).hexdigest()
    assert render("Erster gesprochener Satz.", "a.png") == render("Völlig anderer Text, der nicht erscheinen darf.", "b.png")
    # and the minimal layout (no icon) as well
    def render_min(narration, name):
        out = tmp_path / name
        scene = Scene(id="s", kind="problem", duration_ms=8000, narration_text=narration)
        skill._render_slide_image(scene, out, strategy="minimal_visual")
        return hashlib.sha256(out.read_bytes()).hexdigest()
    assert render_min("Eins zwei drei.", "c.png") == render_min("Anderes Wort anderes Bild?", "d.png")
    # the label is still there: not an empty frame
    assert len(Image.open(tmp_path / "c.png").convert("L").getcolors(maxcolors=100000)) > 20


def test_no_caption_code_is_left_in_the_plugin():
    text = Path(skill.__file__).read_text()
    assert "_generate_srt" not in text and "output.srt" not in text and "-->" not in text


@pytest.mark.skipif(os.environ.get("RUN_LIVE_TTS") != "1", reason="live OpenAI call: set RUN_LIVE_TTS=1 (costs ~$0.0001)")
def test_live_openai_call_returns_real_audio(tmp_path):
    out = tmp_path / "live.mp3"
    skill._synthesize_narration_openai("Ein kurzer Test.", out, "de")
    assert out.stat().st_size > 5_000
