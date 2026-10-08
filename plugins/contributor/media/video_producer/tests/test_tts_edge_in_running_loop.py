"""Regression: the edge-tts tier must work when called from inside a running event
loop — which is exactly how production runs it (the job runner wraps
start_video_production in asyncio.run, and the TTS tiers are called from there).
Before the fix every production job fell through this tier."""

import asyncio
import sys
import types

from src import skill


def _fake_edge_tts(calls):
    mod = types.ModuleType("edge_tts")

    class Communicate:
        def __init__(self, text, voice):
            self.text, self.voice = text, voice

        async def save(self, path):
            await asyncio.sleep(0)
            calls.append((self.text, self.voice))
            with open(path, "wb") as f:
                f.write(b"ID3fake-mp3")

    mod.Communicate = Communicate
    return mod


async def test_edge_tier_succeeds_inside_a_running_loop(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "edge_tts", _fake_edge_tts(calls))
    out = tmp_path / "n.mp3"
    assert skill._tts_tier_edge("Hallo Welt", out, "de") is True
    assert out.read_bytes() == b"ID3fake-mp3"
    assert calls == [("Hallo Welt", "de-DE-KatjaNeural")]


def test_edge_tier_succeeds_without_a_loop(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "edge_tts", _fake_edge_tts(calls))
    assert skill._tts_tier_edge("Hello", tmp_path / "e.mp3", "en") is True
    assert calls == [("Hello", "en-US-AvaMultilingualNeural")]


def test_chain_reaches_edge_through_the_runner_shape(tmp_path, monkeypatch):
    """Same shape as async_runner: asyncio.run(...) in a worker thread, chain inside."""
    calls = []
    monkeypatch.setitem(sys.modules, "edge_tts", _fake_edge_tts(calls))
    monkeypatch.setattr(skill, "_TTS_CHAIN", (("edge", skill._tts_tier_edge), ("mock", skill._tts_tier_mock)))

    async def job():
        return skill._synthesize_narration_chain("Text", tmp_path / "c.mp3", "de")

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(1) as pool:
        provider = pool.submit(lambda: asyncio.run(job())).result(timeout=30)
    assert provider == "edge"
