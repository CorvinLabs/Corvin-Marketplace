"""The default narration is the chain OpenAI -> edge-tts, and the chain works against the real services.

Operator decision 2026-10-17/19: OpenAI TTS first, edge-tts as the fallback, no Piper, no silent tier. The default
engine used to be ``openai`` (single tier, no fallback), so an exhausted key - a case that happened - refused the
job instead of falling back. These tests pin the default and prove the fallback.

Offline tests always run. The ``live`` tests call the real OpenAI and the real Microsoft edge-tts service with one
fixed, public test sentence; they run only with ``CORVIN_LIVE_TTS=1`` and never print or store a key. The
invalid-key case uses a deliberately fake key, so it needs no secret at all.
"""
import json
import os
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from src import skill

PLUGIN = Path(__file__).resolve().parent.parent
SENTENCE = "Dies ist ein kurzer Test der Sprachausgabe."


# ── offline: the default IS the chain ───────────────────────────────────────

def test_the_default_engine_is_the_chain_everywhere_it_is_declared():
    assert skill.DEFAULT_TTS_ENGINE == "auto"
    assert "auto" in skill.SUPPORTED_TTS_ENGINES
    manifest = json.loads((PLUGIN / "plugin.json").read_text())
    assert manifest["config"]["tts_engine"] == "auto"
    yaml_text = (PLUGIN / "plugin.yaml").read_text()
    block = yaml_text[yaml_text.index("tts_engine:"):]
    assert "default: auto" in block.split("penpot_runtime:")[0]


def test_the_chain_has_exactly_two_tiers_in_this_order_and_no_piper_anywhere():
    assert [name for name, _ in skill._TTS_CHAIN] == ["openai", "edge"]
    for f in ("requirements.txt", "setup.py"):  # the dependency lines, not the comment that explains the removal
        code = "\n".join(line.split("#", 1)[0] for line in (PLUGIN / f).read_text().splitlines())
        assert "piper" not in code.lower(), f
    for f in ("plugin.json", "plugin.yaml"):
        assert "piper" not in (PLUGIN / f).read_text().lower(), f
    assert not [n for n in dir(skill) if "piper" in n.lower()]


def test_the_runtime_dependencies_of_both_tiers_are_declared_with_a_working_edge_floor():
    reqs = (PLUGIN / "requirements.txt").read_text()
    assert "openai>=" in reqs and "edge-tts>=7.3.1" in reqs   # < 7.3.1 gets HTTP 403 from Microsoft
    setup = (PLUGIN / "setup.py").read_text()
    assert '"openai>=' in setup and '"edge-tts>=7.3.1"' in setup


def test_the_declared_egress_hosts_are_the_hosts_a_job_can_really_reach():
    text = (PLUGIN / "plugin.yaml").read_text()
    for host in ("api.openai.com", "speech.platform.bing.com", "api.anthropic.com"):
        assert host in text, host


@pytest.mark.asyncio
async def test_a_job_started_without_a_tts_engine_runs_the_chain_and_falls_back_to_edge(tmp_path, monkeypatch):
    """The real entry point (start_video_production) with NO tts_engine in the config: OpenAI declines (simulated: the
    primary tier is the one under test), the second tier takes over, the video is complete and says which voice spoke."""
    from src.models import VideoJob
    from src.storage import get_storage

    calls = []

    def openai_declines(text, out_path, lang):
        calls.append("openai")
        return False

    def edge_speaks(text, out_path, lang):  # a real, silent WAV of the right length: the voice is the substituted part
        calls.append("edge")
        return skill._tts_tier_mock(text, out_path, lang)

    monkeypatch.setattr(skill, "_TTS_CHAIN", (("openai", openai_declines), ("edge", edge_speaks)))
    base = tmp_path / "tenant"
    base.mkdir()
    get_storage(str(base)).save_job(VideoJob(id="job_default_chain", task="chain"))
    storyboard = {"id": "sb", "didactic_strategy": "rich_visual", "scenes": [
        {"id": "s1", "kind": "title", "duration_ms": 6000, "narration_text": "Ein Satz.",
         "template": "hero", "data": {"title": "Kette"}}]}
    result = await skill.start_video_production(
        "job_default_chain", "chain", {"storage_base": str(base), "max_duration_minutes": 5, "storyboard": storyboard})
    assert calls == ["openai", "edge"], "the default must try OpenAI first and edge-tts second"
    assert result["metadata"]["tts_provider_used"] == "edge"
    assert result["metadata"]["tts_engine"] == "auto"
    report = json.loads((Path(result["video_path"]).parent / "report.json").read_text())
    assert any(d["kind"] == "tts_tier_below" and d.get("tier") == "edge" for d in report["degradations"]), report["degradations"]


# ── live: the real services ─────────────────────────────────────────────────

live = pytest.mark.skipif(os.environ.get("CORVIN_LIVE_TTS") != "1", reason="live TTS: set CORVIN_LIVE_TTS=1")


def _duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def _edge_ok() -> bool:
    try:
        import importlib.metadata as md
        parts = tuple(int(x) for x in md.version("edge-tts").split(".")[:3])
        return parts >= (7, 3, 1)
    except Exception:  # noqa: BLE001
        return False


@live
@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe missing")
def test_live_openai_is_the_first_tier_and_speaks(tmp_path):
    if not skill._openai_api_key():
        pytest.skip("no OpenAI key on this host: the OpenAI-first case needs one")
    out = tmp_path / "openai.mp3"
    assert skill._synthesize_narration_chain(SENTENCE, out, "de") == "openai"
    assert out.stat().st_size > 2000 and _duration(out) > 1.0


@live
@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe missing")
def test_live_an_invalid_openai_key_is_answered_by_the_real_service_and_edge_takes_over(tmp_path, monkeypatch):
    """The real OpenAI returns 401 for a fake key (no secret involved) -> the tier declines -> the real edge-tts speaks."""
    if not _edge_ok():
        pytest.skip("edge-tts >= 7.3.1 is not importable here")
    monkeypatch.setenv("CORVIN_TTS_OPENAI_KEY", "sk-not-a-real-key-for-the-fallback-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = tmp_path / "edge_after_401.mp3"
    assert skill._synthesize_narration_chain(SENTENCE, out, "de") == "edge"
    assert out.stat().st_size > 2000 and _duration(out) > 1.0


@live
@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe missing")
def test_live_no_openai_key_at_all_goes_straight_to_edge(tmp_path, monkeypatch):
    if not _edge_ok():
        pytest.skip("edge-tts >= 7.3.1 is not importable here")
    monkeypatch.delenv("CORVIN_TTS_OPENAI_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = tmp_path / "edge_nokey.mp3"
    assert skill._synthesize_narration_chain(SENTENCE, out, "de") == "edge"
    assert out.stat().st_size > 2000 and _duration(out) > 1.0


def test_a_failing_openai_call_inside_orchestrate_falls_back_and_is_reported_per_scene(run_orchestrate, monkeypatch):
    """Regression (1.7.0 release gate): the OpenAI tier noted its degradation without a scene index, the report refused
    it and the whole job died instead of falling to edge-tts. Real chain code, real report, the OpenAI call fails
    (429) and the second tier is the offline mock: the video is complete and every scene says it was spoken by edge."""
    monkeypatch.setenv("CORVIN_TTS_OPENAI_KEY", "sk-not-a-real-key-for-the-fallback-test")

    def openai_429(text, out_path, api_key):
        raise RuntimeError("429 insufficient_quota")

    monkeypatch.setattr(skill, "_openai_speech", openai_429)
    monkeypatch.setattr(skill, "_TTS_CHAIN", (("openai", skill._tts_tier_openai), ("edge", skill._tts_tier_mock)))
    scenes = [{"id": f"s{i}", "kind": "example", "duration_ms": 6000, "narration_text": "Ein kurzer Satz.",
               "visual_description": "d"} for i in (1, 2)]
    result, _ = run_orchestrate(scenes, tts_engine="auto")
    assert result["metadata"]["tts_provider_used"] == "edge"  # the second tier of the chain (here the offline stand-in)
    report = json.loads((Path(result["video_path"]).parent / "report.json").read_text())
    assert [d["scene"] for d in report["degradations"] if d["kind"] == "tts_tier_below"] == [1, 2]
