"""Closes the gaps a clause-by-clause audit of the T-0198 / T-0187 definitions of done found (2026-10-19).

* more than one featured tile is refused (the field is one index, never a list),
* hostile strings in EVERY text field of the template, each with its exact outcome,
* the template x theme x style collision matrix (ADR-2248 guard) for every layout,
* two independent browsers draw the same bento frame for frame,
* the produced MP4 shows tile n and not yet tile n+1 at the cue times,
* the one hardened-parser branch the Penpot import tests did not reach (an ENTITY without a DOCTYPE).
"""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from src import penpot_import as pi
from src.web_renderer import WebRenderError, WebSlideRenderer
from src.web_templates import THEMES, WebSceneError, build_document, validate_scene_data
from tests.test_bento import ICON, LAYOUT_TABLE, NUMBER, SPARK, STATEMENT, TILE_CYCLE, _scene
from tests.test_style_pack import make_style
from tests.test_web_slides_e2e import _run, store  # noqa: F401  (store is a fixture)


# ── one featured tile at most ────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("featured", [[0, 1], [0], [], (0, 1), {"a": 0}])
def test_more_than_one_featured_tile_is_refused(featured):
    with pytest.raises(WebSceneError):
        validate_scene_data("bento", _scene(4, featured))


# ── hostile strings in every text field ──────────────────────────────────────────────────────────────────────────────

def _eyebrow(p):
    return {"eyebrow": p, "tiles": [STATEMENT, NUMBER]}


def _title(p):
    return {"title": p, "tiles": [STATEMENT, NUMBER]}


def _unit(p):
    return {"tiles": [{**NUMBER, "unit": p}, STATEMENT]}


def _num_label(p):
    return {"tiles": [{**NUMBER, "label": p}, STATEMENT]}


def _statement(p):
    return {"tiles": [{"kind": "statement", "text": p}, NUMBER]}


def _icon_label(p):
    return {"tiles": [{**ICON, "label": p}, STATEMENT]}


def _spark_label(p):
    return {"tiles": [{**SPARK, "label": p}, STATEMENT]}


# field -> (builder, getter of the validated value)
FIELDS = {
    "eyebrow": (_eyebrow, lambda d: d["eyebrow"]),
    "title": (_title, lambda d: d["title"]),
    "number.unit": (_unit, lambda d: d["tiles"][0]["unit"]),
    "number.label": (_num_label, lambda d: d["tiles"][0]["label"]),
    "statement.text": (_statement, lambda d: d["tiles"][0]["text"]),
    "icon.label": (_icon_label, lambda d: d["tiles"][0]["label"]),
    "spark.label": (_spark_label, lambda d: d["tiles"][0]["label"]),
}
MARKUP = "<i id=z>"                       # eight characters: fits the shortest field (number.unit, limit 8)
INVISIBLE = "a\u202eb\u200bc\ufeffd"          # bidi override + zero-width space + BOM between letters
INVISIBLE_CLEAN = "abcd"


@pytest.mark.parametrize("field", FIELDS)
def test_markup_is_escaped_in_every_text_field(field):
    build, get = FIELDS[field]
    data = validate_scene_data("bento", build(MARKUP))
    assert get(data) == MARKUP                                   # kept as text, never interpreted
    html = build_document("bento", build(MARKUP), duration_s=6)
    assert MARKUP not in html and "&lt;i id=z&gt;" in html


@pytest.mark.parametrize("field", FIELDS)
def test_bidi_and_zero_width_characters_are_removed_in_every_text_field(field):
    build, get = FIELDS[field]
    assert get(validate_scene_data("bento", build(INVISIBLE))) == INVISIBLE_CLEAN
    html = build_document("bento", build(INVISIBLE), duration_s=6)
    for ch in "\u202e\u200b\ufeff":
        assert ch not in html


@pytest.mark.parametrize("field", FIELDS)
def test_a_lone_surrogate_is_a_validation_error_in_every_text_field(field):
    build, _ = FIELDS[field]
    with pytest.raises(WebSceneError, match="lone surrogate"):
        validate_scene_data("bento", build("\ud800"))


# ── collision matrix and determinism (real Chromium) ──────────────────────────────────────────────────────────────────

LAYOUTS = sorted(LAYOUT_TABLE, key=str)


@pytest.mark.parametrize("styled", [False, True], ids=["corvin-look", "style-pack"])
async def test_every_layout_x_theme_renders_without_collisions(tmp_path, styled):
    style = make_style() if styled else None
    try:
        async with WebSlideRenderer(fps=12, style=style) as r:
            for theme in THEMES:
                for n, featured in LAYOUTS:
                    out = tmp_path / f"{theme}-{n}-{featured}"
                    frames = await r.render("bento", _scene(n, featured), 4, out, theme=theme, scene_index=2, total_scenes=8)
                    assert not frames.layout_issues, f"{theme} {n} {featured}: {frames.layout_issues}"
                    assert len(frames) > 10
    except WebRenderError as e:
        pytest.skip(f"chromium unavailable: {e}")


def _sha(paths):
    return [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths]


@pytest.mark.parametrize("n,featured", [(5, 0), (6, None)])
async def test_two_browsers_draw_the_same_bento_frame_for_frame(tmp_path, n, featured):
    runs = []
    for name in ("a", "b"):
        try:
            async with WebSlideRenderer() as r:
                runs.append(await r.render("bento", _scene(n, featured), 6.0, tmp_path / name))
        except WebRenderError as e:
            pytest.skip(f"chromium unavailable: {e}")
    a, b = runs
    assert len(a) == len(b) > 30
    assert _sha(a) == _sha(b)
    assert len(set(_sha(a))) > 10, "a bento reveals its tiles, so its frames must change"


# ── the produced MP4 reveals the tiles in narration order ───────────────────────────────────────────────────────────

HERO = {"id": "s1", "kind": "title", "duration_ms": 6000, "narration_text": "Four facts about the platform.",
        "visual_description": "title", "template": "hero", "data": {"title": "Platform facts"}}
BENTO = {"id": "s2", "kind": "example", "duration_ms": 16000,
         "narration_text": ("Uptime is ninety nine point nine percent. The audit chain stays intact. "
                            "Every tenant stays isolated. Traffic keeps growing week by week."),
         "visual_description": "tiles", "template": "bento", "beats": [0, 1, 2, 3],
         "data": {"title": "Status", "tiles": [
             {"kind": "number", "value": 99.9, "decimals": 1, "unit": "%", "label": "uptime"},
             {"kind": "statement", "text": "Audit chain intact"},
             {"kind": "icon", "name": "shield", "label": "tenants isolated"},
             {"kind": "spark", "values": [1, 3, 2, 5, 8, 13], "label": "traffic"}]}}


def _frame(video, t, out):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(out)],
                   check=True)
    return Image.open(out).convert("RGB")


def _ink(img):
    """Bright pixels in the grid area (below the header), against the slide's own background."""
    small = img.crop((0, 300, 1920, 1080)).resize((480, 195)).convert("L")
    bg = small.getpixel((2, 2))
    return sum(abs(p - bg) > 40 for p in small.getdata())


async def test_the_mp4_shows_tile_n_and_not_yet_tile_n_plus_one_at_the_cues(store, tmp_path):  # noqa: F811
    result = await _run(store, "job_bento_mp4", storyboard={"id": "sb_bento_mp4", "didactic_strategy": "rich_visual",
                                                            "scenes": [HERO, BENTO]})
    md = result["metadata"]
    assert md["renderers"] == ["web", "web"] and md["layout_collisions"] == []
    video = Path(result["video_path"])
    report = json.loads((video.parent / "report.json").read_text())
    start = float(report["scenes"][0]["audio_s"])
    ats = [it["at"] for it in md["cues"][1]["items"]]
    assert len(ats) == 4 and all(a is not None for a in ats) and ats == sorted(ats)
    assert all(b - a > 1.0 for a, b in zip(ats, ats[1:])), ats          # far enough apart to sample between them

    ink_after = [_ink(_frame(video, start + a + 0.9, tmp_path / f"after{k}.png")) for k, a in enumerate(ats)]
    ink_before = [_ink(_frame(video, start + a - 0.3, tmp_path / f"before{k}.png")) for k, a in enumerate(ats)]
    for k in range(4):
        assert ink_after[k] > ink_before[k] + 20, f"tile {k} did not appear at its cue: {ink_before} -> {ink_after}"
    for k in range(1, 4):
        # nothing of tile k is on screen yet while tile k-1 is settled: the frame just before the cue is no fuller than
        # the settled frame of the tile before it
        assert ink_before[k] <= ink_after[k - 1] + 20, f"tile {k} showed before its cue: {ink_after} / {ink_before}"
    assert ink_after == sorted(ink_after)


# ── the hardened XML parser: an ENTITY without a DOCTYPE ───────────────────────────────────────────────────────────────

def test_an_entity_declaration_without_a_doctype_is_refused():
    raw = (b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><!ENTITY a "b"><rect width="4" height="4"/></svg>')
    with pytest.raises(pi.PenpotImportError, match="document type"):
        pi.parse_design(raw)
