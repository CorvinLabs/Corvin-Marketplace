"""1.8.0: narration comes only from the CorvinOS TTS chain; subtitles do not exist anywhere in the output.

The host's chain (``corvin_console.native_tts``) is replaced by a stand-in with the SAME surface
(``prepare`` / ``provider_from_stderr`` / ``reasons_from_stderr`` / ``expected_provider``) whose
prepared command is a real subprocess - a tiny "say.py" that writes real audio with ffmpeg in the
format the named provider emits (OpenAI: Ogg-Opus, edge-tts: MP3, Piper: WAV) and reports the tier on
stderr exactly like say.py (``say.py: provider=<tier>``). So the job's real path is driven: spawn under
the job budget, read the marker, normalise to MP3, fail loudly when nothing spoke. The live proof
against the real chain is tests/test_live_native_video_e2e.py.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from src import corvinos_native, skill
from src.models import Scene, VideoJob
from src.storage import get_storage

FAKE_SAY = r'''
import subprocess, sys
out, text, lang, mode = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
if mode == "flaky":  # the first run of the chain comes up empty (edge-tts connect error), the second speaks
    import os
    marker = out + ".tried"
    if not os.path.exists(marker):
        open(marker, "w").close()
        sys.stderr.write("say.py: edge-tts failed: ClientConnectorError\n")
        sys.exit(0)
    mode = "edge"
if mode == "none":
    sys.stderr.write("say.py: openai failed: AuthenticationError key sk-live-secret-ABCDEFGH123\n")
    sys.stderr.write("say.py: edge-tts failed: TimeoutError\n")
    sys.stderr.write("say.py: piper: no model for 'de'\n")
    sys.exit(0)
fmt = {"openai": ["-c:a", "libopus", "-f", "ogg"], "edge": ["-c:a", "libmp3lame", "-f", "mp3"],
       "piper": ["-c:a", "pcm_s16le", "-f", "wav"]}[mode]
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                "-t", "1.0", *fmt, out], check=True)
with open(out + ".argv.txt", "w", encoding="utf-8") as f:
    f.write(text + "\n" + lang)
sys.stderr.write("say.py: openai failed: no key\n" if mode != "openai" else "")
sys.stderr.write("say.py: provider=" + mode + "\n")
sys.stdout.write(out)
'''


class FakeHost:
    """The ``corvin_console.native_tts`` surface, preparing a real subprocess."""

    API_VERSION = 1

    def __init__(self, tmp: Path, mode: str = "edge", pinned=None):
        self.script = tmp / "fake_say.py"
        self.script.write_text(FAKE_SAY, encoding="utf-8")
        self.mode, self.pinned, self.prepared = mode, pinned, []

    def expected_provider(self):
        return self.pinned or "openai"

    def prepare(self, text, out_path, lang):
        self.prepared.append((text, Path(out_path), lang))
        return corvinos_native.TTSPlan(argv=[sys.executable, str(self.script), str(out_path), text, lang, self.mode],
                                       env=dict(os.environ), timeout_s=30.0, out_path=Path(out_path))

    @staticmethod
    def provider_from_stderr(stderr):
        tier = ""
        for line in (stderr or "").splitlines():
            if line.strip().startswith("say.py: provider="):
                tier = line.strip().split("=", 1)[1]
        return tier

    @staticmethod
    def reasons_from_stderr(stderr, limit=8):
        return [ln.strip() for ln in (stderr or "").splitlines()
                if ln.strip().startswith("say.py:") and "provider=" not in ln][-limit:]


needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


@pytest.fixture
def host(tmp_path, monkeypatch):
    def install(mode="edge", pinned=None):
        h = FakeHost(tmp_path, mode, pinned)
        monkeypatch.setattr(corvinos_native, "_TTS_API", h)
        return h
    yield install
    corvinos_native.reset_for_tests()


# ── defaults ──

def test_the_corvinos_chain_is_the_only_engine_and_the_default_everywhere():
    import asyncio
    import inspect

    assert skill.DEFAULT_TTS_ENGINE == "auto" and skill.SUPPORTED_TTS_ENGINES == ("auto",)
    assert inspect.signature(skill.orchestrate_video).parameters["tts_engine"].default == "auto"
    assert [n for n, _ in skill._TTS_CHAIN] == ["native"]
    # pre-1.8 stored settings mean the native chain, an unknown engine is still refused
    for legacy in ("openai", "gtts"):
        assert skill._normalise_tts_engine(legacy) == "auto"
    with pytest.raises(ValueError, match="azure"):
        skill._normalise_tts_engine("azure")
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
    assert seen["tts_engine"] == "auto" and seen["storyboard_backend"] == "claude_cli"


def test_no_own_tts_or_llm_code_is_left_in_the_plugin():
    src = Path(skill.__file__).parent
    text = "\n".join(p.read_text(encoding="utf-8") for p in src.glob("*.py"))
    for gone in ("import gtts", "from gtts", "gTTS(", "edge_tts", "_tts_tier_openai", "_tts_tier_edge",
                 "_tts_tier_gtts", "audio.speech", "import anthropic", "11434", "ollama", "Ollama"):
        assert gone not in text, gone


# ── the native chain, through a real subprocess ──

@needs_ffmpeg
@pytest.mark.parametrize("mode", ["openai", "edge", "piper"])
def test_each_provider_of_the_chain_lands_as_mp3_and_is_named(tmp_path, host, mode):
    h = host(mode)
    out = tmp_path / "scene_001.mp3"
    assert skill._synthesize_narration_chain("Hallo Welt, ein Test.", out, "de") == mode
    assert skill._audio_kind(out) == "mp3" and out.stat().st_size > 1000
    assert skill._ffprobe_duration(out) == pytest.approx(1.0, abs=0.2)
    text, raw, lang = h.prepared[0]
    assert (text, lang) == ("Hallo Welt, ein Test.", "de")
    assert raw.parent == out.parent and not raw.exists(), "the provider's raw file is scratch"
    assert (raw.parent / (raw.name + ".argv.txt")).read_text(encoding="utf-8") == "Hallo Welt, ein Test.\nde"


@needs_ffmpeg
def test_an_empty_chain_run_is_run_once_more_and_then_speaks(tmp_path, host, monkeypatch):
    monkeypatch.setattr(skill, "_TTS_CHAIN_RETRY_PAUSE_S", 0)
    h = host("flaky")
    out = tmp_path / "scene_001.mp3"
    assert skill._synthesize_narration_chain("Hallo.", out, "de") == "edge"
    assert skill._audio_kind(out) == "mp3" and len(h.prepared) == 1  # one plan, the same chain run twice


@needs_ffmpeg
def test_no_voice_fails_with_the_chains_reasons_and_never_leaks_a_key(tmp_path, host, monkeypatch):
    monkeypatch.setattr(skill, "_TTS_CHAIN_RETRY_PAUSE_S", 0)
    host("none")
    with pytest.raises(skill.NoVoiceAvailable) as ei:
        skill._synthesize_narration_chain("x", tmp_path / "a.mp3", "de")
    msg = str(ei.value)
    assert "CorvinOS TTS chain" in msg and "edge-tts failed: TimeoutError" in msg and "piper" in msg
    assert "sk-live-secret" not in msg and "<redacted>" in msg
    assert not (tmp_path / "a.mp3").exists()


def test_a_host_without_the_chain_is_a_named_failure_not_another_voice(tmp_path, monkeypatch):
    def missing():
        raise corvinos_native.NativeTTSMissing("corvin_console.native_tts is not importable")

    monkeypatch.setattr(corvinos_native, "tts_api", missing)
    with pytest.raises(skill.NoVoiceAvailable, match="CorvinOS TTS chain is not available"):
        skill._synthesize_narration_chain("x", tmp_path / "a.mp3", "de")


# ── a whole job ──

STORYBOARD = {"id": "sb1", "scenes": [
    {"id": "s1", "kind": "title", "duration_ms": 8000, "narration_text": "Das ist der gesprochene Text der ersten Szene."},
    {"id": "s2", "kind": "summary", "duration_ms": 8000, "narration_text": "Und hier der gesprochene Text der zweiten Szene.",
     "template": "hero", "data": {"title": "Titel"}},
]}


@needs_ffmpeg
@pytest.mark.e2e
@pytest.mark.parametrize("mode,pinned,below", [("edge", None, True), ("piper", "piper", False)])
async def test_a_default_job_is_narrated_by_the_chain_and_produces_no_subtitles(tmp_path, host, mode, pinned, below):
    h = host(mode, pinned)
    base = str(tmp_path / "t"); Path(base).mkdir()
    get_storage(base).save_job(VideoJob(id="job_nt", task="t"))

    # exactly what the console passes when the operator never touched the settings
    result = await skill.start_video_production(
        "job_nt", "t", {"storage_base": base, "max_duration_minutes": 3, "storyboard": STORYBOARD, "web_slides": False})

    md = result["metadata"]
    assert (md["tts_engine"], md["tts_chain"], md["tts_provider_used"]) == ("auto", "corvinos", mode)
    assert [t for t, _, _ in h.prepared] == [s["narration_text"] for s in STORYBOARD["scenes"]]
    report = json.loads((Path(base) / "videos" / "job_nt" / "report.json").read_text(encoding="utf-8"))
    assert report["configured"]["tts"] == "auto"
    assert [s["tts_tier"] for s in report["scenes"]] == [mode, mode]
    # a tier below the chain's head (or the operator's pin) is a recorded degradation, the pinned tier is not
    assert any(d["kind"] == "tts_tier_below" for d in report["degradations"]) is below

    video = Path(result["video_path"])
    assert "srt_path" not in result and not list(video.parent.rglob("*.srt")) and not list(video.parent.rglob("*.vtt"))
    probe = shutil.which("ffprobe")
    if probe:
        streams = json.loads(subprocess.run([probe, "-v", "error", "-show_streams", "-of", "json", str(video)],
                                            capture_output=True, text=True, check=True).stdout)["streams"]
        assert {s["codec_type"] for s in streams} == {"video", "audio"}
    assert get_storage(base).get_video_output("job_nt").srt_path is None


@needs_ffmpeg
@pytest.mark.e2e
async def test_when_the_chain_is_silent_the_job_fails_instead_of_going_mute(tmp_path, host, monkeypatch):
    monkeypatch.setattr(skill, "_TTS_CHAIN_RETRY_PAUSE_S", 0)
    host("none")
    base = str(tmp_path / "t"); Path(base).mkdir()
    get_storage(base).save_job(VideoJob(id="job_mute", task="t"))
    with pytest.raises(skill.NoVoiceAvailable):
        await skill.start_video_production(
            "job_mute", "t", {"storage_base": base, "max_duration_minutes": 3, "storyboard": STORYBOARD, "web_slides": False})
    job = get_storage(base).get_job("job_mute")
    assert job.status == "error" and "No narration voice" in job.error_message
    assert not (Path(base) / "videos" / "job_mute" / "output.mp4").exists()


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
    text = Path(skill.__file__).read_text(encoding="utf-8")
    assert "_generate_srt" not in text and "output.srt" not in text and "-->" not in text


# ── the Claude Code CLI resolution ──

def test_claude_cli_pin_is_exact_and_a_missing_pin_is_not_second_guessed(tmp_path, monkeypatch):
    monkeypatch.setenv("CORVIN_CLAUDE_BIN", str(tmp_path / "nope"))
    assert corvinos_native.claude_cli_path() is None
    real = tmp_path / ("claude.exe" if os.name == "nt" else "claude")
    real.write_text("x"); real.chmod(0o755)
    monkeypatch.setenv("CORVIN_CLAUDE_BIN", str(real))
    assert corvinos_native.claude_cli_path() == str(real)


def test_a_plain_executable_is_spawned_as_a_list_byte_for_byte():
    argv = ["C:/x/claude.exe" if os.name == "nt" else "/x/claude", "-p", "--system-prompt", 'a "quoted" & text']
    assert corvinos_native.spawnable(argv) == argv


@pytest.mark.skipif(os.name != "nt", reason="Windows .cmd shims only")
def test_a_windows_cmd_shim_goes_through_the_hosts_safe_launcher_or_is_refused(tmp_path, monkeypatch):
    shim = tmp_path / "claude.cmd"
    shim.write_text("@echo off\r\n")
    argv = [str(shim), "-p", "--system-prompt", 'x" & echo PWN & "y']
    shared = Path(__file__).resolve().parents[6] / "CorvinOS" / "corvin_operator" / "bridges" / "shared"
    if shared.is_dir():
        monkeypatch.syspath_prepend(str(shared))
        line = corvinos_native.spawnable(argv)
        assert isinstance(line, str) and line.lower().startswith(("cmd", '"cmd', "c:\\windows"))
        assert '""' in line and "& echo PWN &" in line  # quoted, never a bare metachar
    else:
        monkeypatch.setattr(corvinos_native, "_host_module", lambda name: None)
        monkeypatch.setitem(sys.modules, "agents", None)
        with pytest.raises(corvinos_native.ClaudeEngineUnavailable, match="claude.exe"):
            corvinos_native.spawnable(argv)
