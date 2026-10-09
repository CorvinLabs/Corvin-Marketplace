"""Overlap detection for web slides (src/web_layout.py): the check itself, the
templates against it, and the pipeline reaction to a real collision."""

import shutil
import tempfile
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from src import skill
from src.models import VideoJob
from src.storage import get_storage
from src.web_layout import LAYOUT_JS, format_issues
from src.web_renderer import WebSlideRenderer
from tests.test_web_templates import SAMPLES

pytestmark = [pytest.mark.e2e]

ABS = "position:absolute;"
CONTROLS = {  # name -> (html, expected issue type or None)
    "text over text": (f'<div style="{ABS}left:100px;top:100px;font:40px sans-serif">Hello world</div>'
                       f'<div style="{ABS}left:150px;top:110px;font:40px sans-serif">Overlap</div>', "text-text"),
    "cards half overlap": (f'<div style="{ABS}left:100px;top:100px;width:300px;height:200px;border:2px solid #fff"></div>'
                           f'<div style="{ABS}left:300px;top:150px;width:300px;height:200px;border:2px solid #fff"></div>', "box-box"),
    "text pokes out of card": (f'<div style="{ABS}left:100px;top:100px;width:150px;height:80px;border:2px solid #fff;'
                               'font:40px sans-serif;white-space:nowrap">Einwilligungsprüfung</div>', "text-box"),
    "text across card edge": (f'<div style="{ABS}left:100px;top:100px;width:200px;height:100px;background:#333"></div>'
                              f'<div style="{ABS}left:250px;top:130px;font:40px sans-serif">Straddle</div>', "text-box"),
    "ellipsis clip": (f'<div style="{ABS}left:100px;top:100px;width:120px;overflow:hidden;white-space:nowrap;'
                      'font:30px sans-serif">a very long label here</div>', "clipped"),
    "off stage": (f'<div style="{ABS}left:1800px;top:100px;font:40px sans-serif;white-space:nowrap">too far right</div>', "off-stage"),
    "clean": (f'<div style="{ABS}left:100px;top:100px;width:400px;height:100px;border:2px solid #fff;font:30px sans-serif;'
              f'padding:20px">Fits fine</div><div style="{ABS}left:600px;top:100px;font:30px sans-serif">Separate</div>', None),
}


async def test_the_check_flags_every_kind_of_collision_and_passes_a_clean_page():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await (await browser.new_context(viewport={"width": 1920, "height": 1080}, java_script_enabled=False)).new_page()
        for name, (body, expected) in CONTROLS.items():
            await page.set_content(f'<body style="margin:0;background:#000;color:#fff">{body}</body>')
            types = {i["type"] for i in await page.evaluate(LAYOUT_JS, 2)}
            assert (expected in types) if expected else not types, f"{name}: {types}"
        await browser.close()


async def test_every_template_sample_renders_without_collisions():
    async with WebSlideRenderer(fps=12) as r:
        for name, data in SAMPLES.items():
            with tempfile.TemporaryDirectory() as d:
                frames = await r.render(name, data, 6, Path(d), scene_index=2, total_scenes=8)
                assert not frames.layout_issues, f"{name}: {format_issues(frames.layout_issues)}"


DENSE = {  # the realistic worst cases an LLM storyboard produces
    "diagram": {"title": "Pipeline", "nodes": [{"label": w} for w in
                ("Plugin laden", "Skill-Entscheidung", "Einwilligungsprüfung", "Datenfluss-Gate", "A2A-Aufgabe", "Auditchain-Datei")]},
    "chart": {"title": "Vergleich", "bars": [{"label": f"Kategorie Nummer {i}", "value": 10 + i} for i in range(8)], "locale": "de"},
}


async def test_dense_realistic_slides_fit():
    async with WebSlideRenderer(fps=12) as r:
        for name, data in DENSE.items():
            with tempfile.TemporaryDirectory() as d:
                frames = await r.render(name, data, 8, Path(d), lang="de")
                assert not frames.layout_issues, f"{name}: {format_issues(frames.layout_issues)}"


_L = lambda n: ("Wortxxx " * 20)[:n].rstrip()  # the longest text each field allows
COLLIDING = {"title": _L(80), "left": {"title": _L(40), "points": [_L(90)] * 4},
             "right": {"title": _L(40), "points": [_L(90)] * 4}}


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(skill, "_TTS_CHAIN", (("mock", skill._tts_tier_mock),))
    base = tmp_path / "tenant"
    base.mkdir()
    return str(base)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
async def test_a_colliding_scene_is_replaced_by_a_clean_slide_and_reported(store):
    with tempfile.TemporaryDirectory() as d:
        async with WebSlideRenderer(fps=12) as r:
            assert (await r.render("compare", COLLIDING, 6, Path(d), scene_index=1, total_scenes=2)).layout_issues, "fixture must really collide"
    sb = {"id": "sb_layout", "scenes": [
        {"id": "s1", "kind": "problem", "duration_ms": 8000,
         "narration_text": "Zwei Spalten mit sehr langen Aussagen passen nicht auf eine Folie. Deshalb wird sie ersetzt.",
         "template": "compare", "data": COLLIDING},
        {"id": "s2", "kind": "title", "duration_ms": 8000, "narration_text": "Eine saubere Titelfolie bleibt unverändert.",
         "template": "hero", "data": {"title": "Sauber"}},
    ]}
    get_storage(store).save_job(VideoJob(id="job_layout", task="Layout E2E"))
    result = await skill.start_video_production(
        "job_layout", "Layout E2E", {"storage_base": store, "tts_engine": "auto", "max_duration_minutes": 5, "storyboard": sb})
    md = result["metadata"]
    assert md["renderers"] == ["web", "web"]
    assert [e["scene"] for e in md["layout_collisions"]] == ["s1"]
    assert md["layout_collisions"][0]["action"] == "replaced_with_quote"
    assert md["layout_collisions"][0]["issues"], "the report names what collided"
    assert Path(result["video_path"]).stat().st_size > 50_000
