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


async def _tile_rects(data, theme="dark"):
    """Pixel rectangles of the tiles (data order, featured placed first by the layout) from the real layout in Chromium."""
    from playwright.async_api import async_playwright
    doc = build_document("bento", data, duration_s=12, theme=theme)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await (await browser.new_context(viewport={"width": 1920, "height": 1080})).new_page()
        await page.set_content(doc)
        rects = await page.evaluate("""() => [...document.querySelectorAll('.bento .t')].map(e => {
            const r = e.getBoundingClientRect(); return {i: +getComputedStyle(e).getPropertyValue('--i') - 2,
                                                         x: r.x, y: r.y, w: r.width, h: r.height}; })""")
        await browser.close()
    return {r["i"]: (r["x"], r["y"], r["w"], r["h"]) for r in rects}


def _tile_ink(img, rect):
    """Pixels inside the tile's rectangle that differ from the slide background (the tile's card and content)."""
    x, y, w, h = rect
    bg = img.getpixel((3, 3))
    crop = img.crop((int(x) + 4, int(y) + 4, int(x + w) - 4, int(y + h) - 4)).resize((max(int(w) // 4, 1), max(int(h) // 4, 1)))
    return sum(max(abs(c[i] - bg[i]) for i in range(3)) > 24 for c in crop.getdata())


async def _assert_tiles_reveal_in(video, start, cue_at, rects, order, tmp_path):
    """``order`` = tile indices in the order they must appear; ``cue_at[k]`` the cue time of tile k. At each cue time the
    tile's own area goes from (almost) empty to filled, and a tile whose cue is later is still empty at that moment."""
    for pos, k in enumerate(order):
        t = start + cue_at[k]
        before = _tile_ink(_frame(video, t - 0.3, tmp_path / f"b{pos}.png"), rects[k])
        after = _tile_ink(_frame(video, t + 1.2, tmp_path / f"a{pos}.png"), rects[k])
        assert after > 40 and before < after * 0.2, f"tile {k} was not revealed at its cue: ink {before} -> {after}"
        for later in order[pos + 1:]:
            ahead = _tile_ink(_frame(video, t + 0.9, tmp_path / f"c{pos}_{later}.png"), rects[later])
            assert ahead < 0.2 * max(after, 40), f"tile {later} (cue {cue_at[later]:.1f}s) showed at {cue_at[k]:.1f}s: ink {ahead}"


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
    rects = await _tile_rects(validate_scene_data("bento", BENTO["data"]))
    await _assert_tiles_reveal_in(video, start, ats, rects, [0, 1, 2, 3], tmp_path)


# ── the hardened XML parser: an ENTITY without a DOCTYPE ───────────────────────────────────────────────────────────────

def test_an_entity_declaration_without_a_doctype_is_refused():
    raw = (b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><!ENTITY a "b"><rect width="4" height="4"/></svg>')
    with pytest.raises(pi.PenpotImportError, match="document type"):
        pi.parse_design(raw)


# ── "icon (the existing set)": every icon the classic slide set draws is a bento icon ───────────────────────────────────

def test_every_icon_of_the_classic_slide_set_is_a_bento_icon_and_the_guides_list_exactly_the_set():
    from src import bento as bento_mod
    from src import grounded_storyboard as gs
    from src import skill as skill_mod
    classic = set(skill_mod._ICON_KEYWORDS.values())
    assert classic <= set(bento_mod.ICONS), classic - set(bento_mod.ICONS)
    listed = "|".join(bento_mod.ICONS)
    assert f"one of {listed}," in skill_mod._TEMPLATE_GUIDE
    assert f"one of {listed}," in gs.GROUNDED_TEMPLATE_GUIDE


@pytest.mark.parametrize("name", sorted(__import__("src.bento", fromlist=["ICONS"]).ICONS))
def test_every_bento_icon_validates_and_draws_its_glyph(name):
    from src import bento as bento_mod
    data = validate_scene_data("bento", {"tiles": [{"kind": "icon", "name": name, "label": "x"}, STATEMENT]})
    html = build_document("bento", data, duration_s=6)
    assert f'd="{bento_mod.ICONS[name]}"' in html


# ── without beats the narration decides: tiles appear in the order the narration NAMES them ─────────────────────────────

NAMED_ORDER = ("First look at traffic, which keeps growing week by week. Then uptime, at ninety nine point nine percent. "
               "After that tenants isolated, every single one. Last, Audit chain intact, verified every day.")


async def test_without_beats_the_tiles_appear_in_the_order_the_narration_names_them(store, tmp_path):  # noqa: F811
    import copy
    scene = copy.deepcopy(BENTO)
    scene.pop("beats")
    scene["narration_text"] = NAMED_ORDER
    result = await _run(store, "job_bento_named", storyboard={"id": "sb_named", "didactic_strategy": "rich_visual",
                                                              "scenes": [HERO, scene]})
    md = result["metadata"]
    cue = md["cues"][1]
    assert cue["beats_source"] == "fallback" and md["layout_collisions"] == []   # no beats were given: the narration drives
    at = {it["label"]: it["at"] for it in cue["items"]}
    expected = sorted(at, key=lambda lbl: NAMED_ORDER.lower().index(lbl.lower()))
    assert expected == ["traffic", "uptime", "tenants isolated", "Audit chain intact"]    # differs from the data order
    assert sorted(at, key=at.get) == expected, at
    assert [lbl for lbl in at] != expected                                                # (so this is not the data order)

    video = Path(result["video_path"])
    report = json.loads((video.parent / "report.json").read_text())
    start = float(report["scenes"][0]["audio_s"])
    labels = ["uptime", "Audit chain intact", "tenants isolated", "traffic"]           # data order of BENTO's tiles
    cue_at = [at[lbl] for lbl in labels]
    assert all(b - a > 1.0 for a, b in zip(sorted(cue_at), sorted(cue_at)[1:])), cue_at
    rects = await _tile_rects(validate_scene_data("bento", scene["data"]))
    order = [labels.index(lbl) for lbl in expected]                                    # tile indices in narration order
    await _assert_tiles_reveal_in(video, start, cue_at, rects, order, tmp_path)
