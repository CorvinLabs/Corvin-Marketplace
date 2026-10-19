"""A storyboard model can CHOOSE ``bento`` and an invalid bento is repaired exactly once (ADR-2260 decision 5, T-0198).

Same boundary as the donut repair tests in ``test_web_slides_e2e.py``: ``start_video_production`` with real Chromium and
ffmpeg, the Claude Code CLI replaced by an executable at the process boundary, TTS by the offline mock tier."""

import json

import pytest

from tests.test_web_slides_e2e import _fake_claude, _run, store  # noqa: F401  (store is a fixture)

pytestmark = [pytest.mark.e2e]

HERO = {"id": "s1", "kind": "title", "duration_ms": 8000, "narration_text": "Where the platform stands today.",
        "visual_description": "title", "template": "hero", "data": {"title": "Platform status"}}
NARRATION = "Uptime is high. The audit chain is intact. Tenants stay isolated. Traffic keeps growing."
TILES = [
    {"kind": "number", "value": 99.9, "decimals": 1, "unit": "%", "label": "uptime"},
    {"kind": "statement", "text": "Audit chain intact"},
    {"kind": "icon", "name": "shield", "label": "tenants isolated"},
    {"kind": "spark", "values": [1, 3, 2, 5, 8], "label": "traffic"},
]


def _board(tiles, **extra):
    return {"id": "sb_bento", "didactic_strategy": "rich_visual", "scenes": [HERO, {
        "id": "s2", "kind": "example", "duration_ms": 10000, "narration_text": NARRATION,
        "visual_description": "bento", "template": "bento", "beats": [0, 1, 2, 3],
        "data": {"title": "Status", "tiles": tiles, **extra}}]}


async def test_a_model_can_choose_bento_and_it_renders_as_a_web_scene(store, tmp_path, monkeypatch):  # noqa: F811
    log = _fake_claude(tmp_path, monkeypatch, _board(TILES))
    result = await _run(store, "job_bento_ok", storyboard_backend="claude_cli", storyboard_model="claude-sonnet-5-5")
    md = result["metadata"]
    assert md["renderers"] == ["web", "web"]
    assert md["storyboard_template_repairs"] == 0 and md["storyboard_template_warnings"] == []
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert [c["repair"] for c in calls] == [False]          # no repair round was needed
    # (the CLI stand-in logs only the tail of the prompt; that the guide offers bento is asserted in test_bento.py)
    assert calls[0]["stdin_len"] > 1000 and not calls[0]["repair"]


async def test_an_invalid_bento_is_repaired_once(store, tmp_path, monkeypatch):  # noqa: F811
    seven = TILES + TILES[:3]                                # 7 tiles: outside the 2..6 vocabulary
    fixed = {"scenes": [{"id": "s2", "template": "bento", "data": {"title": "Status", "tiles": TILES}}]}
    log = _fake_claude(tmp_path, monkeypatch, _board(seven), repair=fixed)
    result = await _run(store, "job_bento_repair", storyboard_backend="claude_cli", storyboard_model="claude-sonnet-5-5")
    md = result["metadata"]
    assert md["renderers"] == ["web", "web"]
    assert md["storyboard_template_repairs"] == 1 and md["storyboard_template_warnings"] == []
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert [c["repair"] for c in calls] == [False, True]    # exactly one repair round
    assert "tiles" in calls[1]["prompt"]


async def test_a_bento_that_stays_invalid_after_the_one_repair_is_reported(store, tmp_path, monkeypatch):  # noqa: F811
    seven = TILES + TILES[:3]
    still_bad = {"scenes": [{"id": "s2", "template": "bento", "data": {"title": "x", "tiles": seven}}]}
    log = _fake_claude(tmp_path, monkeypatch, _board(seven), repair=still_bad)
    result = await _run(store, "job_bento_bad", storyboard_backend="claude_cli", storyboard_model="claude-sonnet-5-5")
    md = result["metadata"]
    assert md["storyboard_template_repairs"] == 0
    assert len(md["storyboard_template_warnings"]) == 1 and "tiles" in md["storyboard_template_warnings"][0]
    assert md["renderers"] == ["web", "web"], "an unrepairable bento degrades to a web slide, never the placeholder"
    assert sum(1 for line in log.read_text().splitlines() if json.loads(line)["repair"]) == 1   # asked once, not twice
