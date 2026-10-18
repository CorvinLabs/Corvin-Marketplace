"""Board template (ADR-2260 decisions 1-4, 6, 9-11; T-0197): stored model, steps, reveal, fallback, budgets."""

import asyncio
import copy
import json
import shutil
import subprocess
import statistics
import tempfile
import time
from pathlib import Path

import pytest
from PIL import Image

from src import asset_store as A
from src import board
from src import penpot_import as pi
from src import web_templates as wt
from src.penpot_import import DesignError, Shape, StepsError
from src.web_templates import WebSceneError, build_document, validate_scene_data
from tests import board_cases as cases

FIXTURE_TENANT = Path(__file__).parent / "fixtures" / "assets_tenant"
FIXTURE_BOARD = "ast_b0a2d000"


def _png(w=64, h=48):
    import io
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 200, 200)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def tenant(tmp_path):
    """An empty tenant store, bound like a job binds it."""
    store = A.AssetStore(str(tmp_path / "t"))
    token = A._BOUND.set(store)
    yield store
    A._BOUND.reset(token)


def _add_design(store, svg=None, steps=None, caption="A board"):
    d = pi.parse_design(svg or cases.simple_svg())
    doc = store.add(_png(), caption=caption, uploaded_by="u1", design=d)
    if steps is not None:
        store.update(doc["id"], steps=steps)
    return doc["id"], d


THREE = [{"shapes": [0], "label": "Title"}, {"shapes": [1]}, {"shapes": [2, 3]}]


# ── the stored model (decision 2) ───────────────────────────────────────────

def test_design_json_holds_the_whole_typed_design_and_no_steps(tenant):
    aid, d = _add_design(tenant, steps=THREE)
    raw = json.loads((tenant.root / aid / "design.json").read_text())
    assert set(raw) == {"v", "width", "height", "ox", "oy", "background", "shapes"}
    assert "steps" not in raw and raw["background"] == "#ffffff" and len(raw["shapes"]) == 4
    assert tenant.design(aid).shapes == d.shapes
    assert "steps" in tenant.get(aid, with_png=False)


TAMPER = {
    "baseline": ("baseline", 'alphabetic" onload="x'),
    "anchor": ("anchor", 'start"><script>x</script>'),
    "fill": ("fill", '#ffffff"/><image href="http://evil/x.png"/>'),
    "stroke": ("stroke", 'red'),
    "font_family": ("font_family", "Inter'); background:url(http://x"),
    "text": ("text", "ok‮txt"),
    "path": ("d", 'M0 0 L10 10"/><script>'),
    "matrix": ("matrix", [1, 0, 0, 1, 0, float("inf")]),
    "group": ("group", -1),
    "font_weight": ("font_weight", "bold"),
}


@pytest.mark.parametrize("name", sorted(TAMPER))
def test_a_tampered_design_json_is_refused_before_it_reaches_to_svg(tenant, name):
    aid, _ = _add_design(tenant, steps=THREE)
    p = tenant.root / aid / "design.json"
    raw = json.loads(p.read_text())
    key, bad = TAMPER[name]
    idx = {"text": 0, "path": 1, "baseline": 0, "anchor": 0, "font_family": 0, "font_weight": 0}.get(name, 1)
    raw["shapes"][idx][key] = bad
    p.write_text(json.dumps(raw))
    with pytest.raises(A.AssetError, match="stored design is invalid"):
        tenant.design(aid)
    with pytest.raises(A.AssetError):
        tenant.board(aid)
    with pytest.raises(WebSceneError):
        validate_scene_data("board", {"asset": aid})


def test_unknown_keys_and_a_wrong_version_are_refused():
    d = pi.design_to_dict(pi.parse_design(cases.simple_svg()))
    for mutate in (lambda x: x.update(extra=1), lambda x: x.update(v=2), lambda x: x["shapes"][0].update(onload="x"),
                   lambda x: x.update(background="#FFF"), lambda x: x.update(width=float("nan"))):
        bad = copy.deepcopy(d)
        mutate(bad)
        with pytest.raises(DesignError):
            pi.validate_design(bad)


def test_to_svg_refuses_a_hand_built_shape_that_would_write_markup():
    d = pi.parse_design(cases.simple_svg())
    for evil in (Shape("text", text="x", baseline='x" style="y', fill="#000000", font_size=10.0),
                 Shape("rect", w=10.0, h=10.0, fill='#ffffff"/><image href="http://evil/x.png"/>')):
        d.shapes = [evil]
        with pytest.raises(DesignError):
            pi.to_svg(d)
    d.shapes, d.background = [], '#fff" onload="x'
    with pytest.raises(DesignError):
        pi.to_svg(d)


def test_a_symlinked_design_json_is_refused(tenant, tmp_path):
    aid, _ = _add_design(tenant, steps=THREE)
    p = tenant.root / aid / "design.json"
    target = tmp_path / "elsewhere.json"
    target.write_text(p.read_text())
    p.unlink()
    p.symlink_to(target)
    with pytest.raises(A.AssetError):
        tenant.design(aid)


def test_deleting_the_asset_removes_design_json(tenant):
    aid, _ = _add_design(tenant, steps=THREE)
    assert (tenant.root / aid / "design.json").is_file()
    tenant.delete(aid)
    assert not (tenant.root / aid).exists()


# ── steps (decisions 2 and 3) ────────────────────────────────────────────────

@pytest.mark.parametrize("steps,msg", [
    ([{"shapes": [0, 1]}, {"shapes": [1, 2, 3]}], "two steps"),                 # overlap
    ([{"shapes": [0]}, {"shapes": [2, 3]}], "exactly one step"),                 # gap
    ([{"shapes": [i]} for i in range(13)], "1 to 12"),                           # 13 steps
    ([{"shapes": [0, 1, 2, 3], "label": "<b>bold</b>"}], "plain text"),         # markup
    ([{"shapes": [0, 1, 2, 3], "label": "x" * 41}], "at most 40"),
    ([{"shapes": []}, {"shapes": [0, 1, 2, 3]}], "at least one shape"),
    ([{"shapes": [0, 1, 2, True]}], "index"),
    ([{"shapes": [0, 1, 2, 3], "x": 1}], "shapes, label"),
])
def test_steps_must_be_an_ordered_partition(tenant, steps, msg):
    aid, _ = _add_design(tenant)
    with pytest.raises(A.AssetError, match=msg):
        tenant.update(aid, steps=steps)
    assert "steps" not in tenant.get(aid, with_png=False)


def test_a_long_text_shape_gives_a_forty_character_label_on_a_word_boundary():
    words = " ".join(["audit"] * 120)[:600]
    svg = (cases.SVG_HEAD + f'<text x="10" y="50" font-size="20" fill="#000000">{words}</text></svg>').encode()
    d = pi.parse_design(svg)
    assert len(d.shapes[0].text) == 600
    label = pi.derived_label(d, [0])
    assert label == "audit audit audit audit audit audit"  # 35 chars: the 7th word would cut at 41


def test_an_update_that_would_overflow_the_record_is_refused_and_the_picture_stays_readable(tenant):
    aid, _ = _add_design(tenant, svg=cases.many_shapes_svg(12))
    # emoji are written as 12-byte escapes: the hotspots fit, twelve labelled steps on top do not
    spots = [{"name": f"s{i:02d}", "x": 0.5, "y": 0.5, "description": "\U0001F600" * 110} for i in range(8)]
    tenant.update(aid, hotspots=spots)
    before = (tenant.root / aid / "asset.json").read_bytes()
    assert len(before) < A.MAX_JSON_BYTES
    big = [{"shapes": [i], "label": "\U0001F600" * 40} for i in range(12)]
    with pytest.raises(A.AssetError, match="too large"):
        tenant.update(aid, steps=big)
    assert (tenant.root / aid / "asset.json").read_bytes() == before
    assert tenant.get(aid)["png"].startswith(A.PNG_MAGIC)


def test_the_record_key_set_is_closed_with_steps_the_only_optional_key(tenant):
    aid, _ = _add_design(tenant, steps=THREE)
    p = tenant.root / aid / "asset.json"
    good = json.loads(p.read_text())
    assert tenant.get(aid, with_png=False)["steps"] == good["steps"]
    for bad in ({**good, "steps": [{"shapes": [0, 0]}]}, {**good, "steps": "all"}, {**good, "extra": 1}):
        p.write_text(json.dumps(bad))
        with pytest.raises(A.AssetError):
            tenant.get(aid)
    absent = dict(good)
    absent.pop("steps")
    p.write_text(json.dumps(absent))
    assert "steps" not in tenant.get(aid, with_png=False)


def test_steps_on_an_image_without_a_design_are_refused(tenant):
    doc = tenant.add(_png(), caption="plain", uploaded_by="u1")
    with pytest.raises(A.AssetError, match="no stored design"):
        tenant.update(doc["id"], steps=[{"shapes": [0]}])
    p = tenant.root / doc["id"] / "asset.json"
    p.write_text(json.dumps({**json.loads(p.read_text()), "steps": [{"shapes": [0]}]}))
    with pytest.raises(A.AssetError):
        tenant.get(doc["id"])


def test_an_unassigned_design_loads_but_cannot_be_a_board(tenant):
    aid, d = _add_design(tenant)
    assert tenant.design(aid).shapes == d.shapes and tenant.get(aid)["png"]
    with pytest.raises(A.AssetError, match="assign steps first"):
        tenant.board(aid)
    with pytest.raises(WebSceneError, match="assign steps first"):
        validate_scene_data("board", {"asset": aid})
    assert aid not in tenant.board_catalogue()


def test_clearing_steps_unassigns_the_design(tenant):
    aid, _ = _add_design(tenant, steps=THREE)
    assert aid in tenant.board_catalogue()
    tenant.update(aid, steps=None)
    assert aid not in tenant.board_catalogue()


def test_unknown_foreign_and_model_less_assets_get_the_same_refusal(tenant, tmp_path):
    other = A.AssetStore(str(tmp_path / "other"))
    foreign, _ = _add_design(other, steps=THREE)
    plain = tenant.add(_png(), caption="plain", uploaded_by="u1")["id"]
    msgs = []
    for asset in ("ast_00000000", foreign, plain, "../etc", 7):
        with pytest.raises(WebSceneError) as e:
            validate_scene_data("board", {"asset": asset})
        msgs.append(str(e.value).replace(repr(asset), "<id>"))
    assert set(msgs) == {"unknown board asset <id>"}


def test_a_large_design_imports_as_a_picture_and_is_refused_only_as_a_board(tenant):
    for n in (241, 2000):
        aid, d = _add_design(tenant, svg=cases.many_shapes_svg(n))
        assert len(d.shapes) == n and tenant.design(aid) is not None
        with pytest.raises(A.AssetError, match=f"{n} shapes"):
            tenant.update(aid, steps=[{"shapes": list(range(n))}])
        with pytest.raises(A.AssetError, match=f"{n} shapes"):
            tenant.board(aid)
        tenant.delete(aid)


# ── the template (decisions 3 and 4) ────────────────────────────────────────

def test_board_is_registered_everywhere_a_template_is_named(tenant):
    """ADR-2260 context fact 1: every template-naming place handles board."""
    from src import report, skill
    aid, _ = _add_design(tenant, steps=THREE)
    data = {"title": "T", "asset": aid}
    assert "board" in wt.TEMPLATES and "board" in wt._BUILDERS
    d = validate_scene_data("board", data)
    assert validate_scene_data("board", d) == d                     # idempotent: stored back into the scene
    assert wt.reveal_steps("board", d) == 3
    assert wt.scene_items("board", d) == [("Title", 2), ("", 3), ("", 4)]
    assert wt.scene_item_subs("board", d) == ["", "", ""]
    doc = build_document("board", data, duration_s=6)
    assert "board-art" in doc and board.CSS in doc
    assert '"board"' in skill._board_guide() and aid in skill._board_guide()
    assert "board_to_still" in report.DEGRADATION_KINDS and "board_to_still" in report.SCENE_KINDS
    assert ".board-art" in __import__("src.web_layout", fromlist=["LAYOUT_JS"]).LAYOUT_JS


def test_the_prompt_offers_only_board_ready_designs(tenant):
    from src import skill
    ready, _ = _add_design(tenant, steps=THREE, caption="ready one")
    unassigned, _ = _add_design(tenant, caption="not yet")
    big, _ = _add_design(tenant, svg=cases.many_shapes_svg(300), caption="too big")
    guide = skill._board_guide()
    assert ready in guide and unassigned not in guide and big not in guide


def test_each_shape_keeps_its_paint_order_and_carries_its_steps_index(tenant):
    aid, d = _add_design(tenant, steps=[{"shapes": [0, 3]}, {"shapes": [1, 2]}])  # steps not contiguous
    doc = build_document("board", {"asset": aid}, duration_s=6)
    art = doc[doc.index('<svg class="board-art"'):doc.index("</svg>", doc.index('<svg class="board-art"'))]
    order = [art.index(m) for m in ("Pipeline overview", 'stroke="#ff8800"', "<ellipse", 'fill="#22aa55"')]
    assert order == sorted(order), "the drawing order must stay the design's shape order"
    assert art.count('--i:2;') >= 2 and art.count('--i:3;') >= 2


def test_motion_is_one_of_four_and_draw_on_only_for_stroked_paths(tenant):
    aid, d = _add_design(tenant, steps=[{"shapes": [0, 1, 2, 3]}])
    assert [board.motion(s) for s in d.shapes] == ["rise", "draw", "scale", "fade"]
    doc = build_document("board", {"asset": aid}, duration_s=6)
    assert doc.count('class="bdraw" pathLength="1"') == 1           # only the stroked path draws on
    assert "m-scale" in doc and "m-fade" in doc and 'class="bd r m-rise"' in doc
    filled_stroked = pi.parse_design((cases.SVG_HEAD + '<path d="M10 10 L500 10 L500 300 Z" fill="#00ff00" '
                                      'stroke="#000000" stroke-width="8"/></svg>').encode())
    svg = board.board_svg(filled_stroked, [{"shapes": [0]}], 800, 450)
    assert svg.index("m-fade") < svg.index("bdraw"), "the fill fades in behind the stroke drawn on top of it"


def test_the_board_is_written_from_typed_fields_only(tenant):
    svg = (cases.SVG_HEAD + '<style>@font-face{src:url(http://localhost/x.woff)}</style>'
           '<text x="10" y="50" font-family="Inter" font-size="40" fill="#000000">Hi &lt;b&gt;</text>'
           '<image href="http://evil/x.png" width="10" height="10"/></svg>').encode()
    aid, _ = _add_design(tenant, svg=svg, steps=[{"shapes": [0]}])
    doc = build_document("board", {"asset": aid}, duration_s=6)
    assert "http://" not in doc and "<image" not in doc and "&lt;b&gt;" in doc
    assert "<script" not in doc.lower()


# ── through a real job ──────────────────────────────────────────────────────

ffmpeg_ok = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@pytest.fixture
def job_store(tmp_path, monkeypatch):
    from src import skill
    monkeypatch.setattr(skill, "_TTS_CHAIN", (("mock", skill._tts_tier_mock),))
    base = tmp_path / "tenant"
    base.mkdir()
    return str(base)


async def _run(base, job_id, **config):
    from src import skill
    from src.models import VideoJob
    from src.storage import get_storage
    get_storage(base).save_job(VideoJob(id=job_id, task="Board E2E"))
    cfg = {"storage_base": base, "tts_engine": "auto", "max_duration_minutes": 5, **config}
    return await skill.start_video_production(job_id, "Board E2E", cfg)


def _board_storyboard(asset, beats=None):
    scene = {"id": "s1", "kind": "solution", "duration_ms": 12000,
             "narration_text": "Zuerst die Pipeline overview. Dann der Strich. Am Ende die Formen.",
             "template": "board", "data": {"title": "Unser Board", "asset": asset}}
    if beats is not None:
        scene["beats"] = beats
    return {"id": "sb_board", "didactic_strategy": "rich_visual", "scenes": [scene]}


def _job_asset(base, steps=THREE):
    store = A.AssetStore(base)
    aid, _ = _add_design(store, steps=steps)
    return store, aid


@pytest.mark.skipif(not ffmpeg_ok, reason="ffmpeg/ffprobe not installed")
async def test_a_board_scene_renders_and_its_source_survives_deleting_the_asset(job_store):
    store, aid = _job_asset(job_store)
    result = await _run(job_store, "job_board", storyboard=_board_storyboard(aid, beats=[0, 1, 2]))
    md = result["metadata"]
    assert md["renderers"] == ["web"] and md["cues"][0]["template"] == "board", md
    assert md["board_fallbacks"] == []
    src = Path(result["video_path"]).parent / "source" / "assets"
    store.delete(aid)
    assert (src / f"{aid}.png").is_file() and (src / f"{aid}.design.json").is_file()
    rec = json.loads((src / f"{aid}.json").read_text())
    assert rec["steps"] == [{"shapes": [0], "label": "Title"}, {"shapes": [1]}, {"shapes": [2, 3]}]
    assert "uploaded_by" not in rec
    pi.validate_design(json.loads((src / f"{aid}.design.json").read_text()))


@pytest.mark.skipif(not ffmpeg_ok, reason="ffmpeg/ffprobe not installed")
async def test_a_render_error_shows_the_picture_as_a_still_never_the_classic_slide(job_store, monkeypatch):
    _, aid = _job_asset(job_store)

    def broken(*a, **k):
        raise RuntimeError("renderer broke")
    monkeypatch.setattr(board, "board_svg", broken)
    result = await _run(job_store, "job_board_err", storyboard=_board_storyboard(aid))
    md = result["metadata"]
    assert md["renderers"] == ["web"], "never the classic Pillow slide"
    assert md["cues"][0]["template"] == "still"
    assert len(md["board_fallbacks"]) == 1 and md["board_fallbacks"][0]["reason"].startswith("render:")
    kinds = [d["kind"] for d in json.loads((Path(result["video_path"]).parent / "report.json").read_text())["degradations"]]
    assert "board_to_still" in kinds and "web_to_pillow" not in kinds and "collision_replaced" not in kinds


@pytest.mark.skipif(not ffmpeg_ok, reason="ffmpeg/ffprobe not installed")
async def test_a_board_collision_becomes_a_still_never_content_or_quote(job_store, monkeypatch):
    from src.web_renderer import WebSlideRenderer
    _, aid = _job_asset(job_store)
    real = WebSlideRenderer._measure_layout

    async def collide(self, document, *a, **k):
        found = await real(self, document, *a, **k)
        if 'class="board-art"' in document:
            return found + [{"type": "text-box", "a": "h2.title", "b": "div.board"}]
        return found
    monkeypatch.setattr(WebSlideRenderer, "_measure_layout", collide)
    result = await _run(job_store, "job_board_col", storyboard=_board_storyboard(aid))
    md = result["metadata"]
    assert md["cues"][0]["template"] == "still"
    assert [e["action"] for e in md["layout_collisions"]] == ["board_to_still"]
    kinds = [d["kind"] for d in json.loads((Path(result["video_path"]).parent / "report.json").read_text())["degradations"]]
    assert "board_to_still" in kinds and "collision_replaced" not in kinds


def test_a_board_the_model_names_off_the_list_becomes_a_still_of_the_same_image(tenant):
    from src import skill
    aid, _ = _add_design(tenant)  # unassigned: not on the board list, but an uploaded image of this tenant
    scenes = [{"id": "s1", "kind": "solution", "narration_text": "Das Design im Überblick.", "template": "board",
               "data": {"title": "Design", "asset": aid}, "beats": [0]}]
    warnings = skill._apply_web_scene_contract(scenes, strict=False)
    assert scenes[0]["template"] == "still" and scenes[0]["data"]["asset"] == aid
    assert "beats" not in scenes[0] and "still of the same image" in warnings[0]
    with pytest.raises(ValueError, match="assign steps first"):
        skill._apply_web_scene_contract([{"id": "s1", "template": "board", "data": {"asset": aid}}], strict=True)


def test_a_board_without_an_image_of_this_tenant_is_not_turned_into_a_still(tenant):
    from src import skill
    scenes = [{"id": "s1", "kind": "solution", "narration_text": "x.", "template": "board",
               "data": {"asset": "ast_00000000"}}]
    skill._apply_web_scene_contract(scenes, strict=False)
    assert scenes[0].get("template") is None


# ── reveal routes (decision 3) ──────────────────────────────────────────────

def _timeline(d, narration, beats=None):
    from src.web_timeline import AudioPauses, build_timeline
    return build_timeline("board", wt.scene_items("board", d), narration, AudioPauses(duration=12.0, speech_end=12.0),
                          beats=beats, lang="de", subs=wt.scene_item_subs("board", d))


def test_three_reveal_routes_label_beats_and_even_spacing(tenant):
    aid, _ = _add_design(tenant, steps=[{"shapes": [0], "label": "Pipeline"}, {"shapes": [1], "label": "Kontrolle"},
                                        {"shapes": [2, 3]}])
    d = validate_scene_data("board", {"asset": aid})
    # 1) named by label: "Kontrolle" is said late, so step 2 comes late
    named = _timeline(d, "Erst reden wir lange. Sehr lange. Die Pipeline kommt. Viel später die Kontrolle.")
    assert named.step_times[3] > named.step_times[2] + 2.0
    # 2) by beats: sentence k reveals step k
    beats = _timeline(d, "Eins. Zwei. Drei.", beats=[0, 1, 2])
    assert beats.source == "llm" and beats.step_times[2] < beats.step_times[3] < beats.step_times[4]
    # 3) no label, no beats: even spacing between named neighbours
    plain = _timeline(d, "Die Pipeline. Dann die Kontrolle. Dann noch etwas.")
    assert plain.step_times[4] >= plain.step_times[3]


# ── rendering ────────────────────────────────────────────────────────────────

pytest.importorskip("playwright")


async def test_a_stroked_path_is_partly_drawn_mid_draw(tenant, tmp_path):
    from src.web_renderer import WebSlideRenderer
    svg = (cases.SVG_HEAD + '<rect x="0" y="0" width="1600" height="900" fill="#ffffff"/>'
           '<path d="M100 450 L1500 450" fill="none" stroke="#ff0000" stroke-width="16"/></svg>').encode()
    aid, _ = _add_design(tenant, svg=svg, steps=[{"shapes": [0]}])
    async with WebSlideRenderer(fps=30) as r:
        frames = await r.render("board", {"asset": aid}, 6.0, tmp_path / "f")

    def red(p):
        im = Image.open(p).convert("RGB")
        return sum(1 for px in im.getdata() if px[0] > 200 and px[1] < 80 and px[2] < 80)
    counts = [red(p) for p in frames]
    final = counts[-1]
    mids = [c for c in counts if 0.1 * final < c < 0.9 * final]
    assert final > 5000 and len(mids) >= 2, counts
    i, j = counts.index(mids[0]), counts.index(mids[-1])
    assert i < j and counts[i] < counts[j], "the stroke grows over time (two mid-draw timestamps)"


async def test_two_browsers_render_a_board_identically(tmp_path):
    import hashlib
    from src.web_renderer import WebRenderError, WebSlideRenderer
    data = {"title": "T", "asset": FIXTURE_BOARD}
    paths = []
    for name in ("a", "b"):
        try:
            async with WebSlideRenderer() as r:
                paths.append(await r.render("board", data, 6.0, tmp_path / name))
        except WebRenderError as e:
            pytest.skip(f"chromium unavailable: {e}")
    sha = lambda ps: [hashlib.sha256(Path(x).read_bytes()).hexdigest() for x in ps]
    assert len(paths[0]) == len(paths[1]) > 30 and sha(paths[0]) == sha(paths[1])
    assert len(set(sha(paths[0]))) > 5


async def test_the_worst_allowed_board_renders_within_twice_the_median_frame_time(tmp_path):
    """Decision 10: the design that meets EVERY board bound at once, at 1920x1080, against the existing templates."""
    from src.web_renderer import WebSlideRenderer
    from tests.test_web_templates import SAMPLES
    store = A.AssetStore(str(tmp_path / "w"))
    d = pi.parse_design(cases.worst_svg(pi))
    assert pi.board_refusal(d) is None and len(d.shapes) == pi.BOARD_MAX_SHAPES and not d.dropped
    doc = store.add(await pi.render_png(d), caption="worst", uploaded_by="u1", design=d)
    k = len(d.shapes)
    store.update(doc["id"], steps=[{"shapes": list(range(i, min(i + 20, k)))} for i in range(0, k, 20)])

    async def per_frame(r, name, data, binding=None):
        tok = A._BOUND.set(binding) if binding else None
        try:
            with tempfile.TemporaryDirectory() as t:
                t0 = time.perf_counter()
                fr = await r.render(name, data, 6.0, Path(t))
                return (time.perf_counter() - t0) / len(fr)
        finally:
            if tok:
                A._BOUND.reset(tok)

    async with WebSlideRenderer(fps=30) as r:
        base = [await per_frame(r, n, data) for n, data in SAMPLES.items() if n != "board"]
        worst = statistics.median([await per_frame(r, "board", {"title": "W", "asset": doc["id"]}, store)
                                   for _ in range(3)])
    med = statistics.median(base)
    assert worst <= 2.0 * med, f"worst board {worst * 1000:.0f} ms/frame vs median {med * 1000:.0f} ms/frame"
