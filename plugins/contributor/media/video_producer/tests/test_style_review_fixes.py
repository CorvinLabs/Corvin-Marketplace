"""Regression tests for the adversarial review of the user-styles feature (PLAN-0945 / ADR-2248)."""

import asyncio
import copy
import hashlib
import io
import json
import random
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image

from src import skill
from src import style_import_pptx as imp
from src import style_pack as sp
from src import style_preview
from src.models import Scene
from src.style_import_pptx import PptxImportError, import_pptx
from src.style_pack import Style, StyleError, validate_style
from src.style_store import MAX_STYLES, StyleQuotaExceeded, StyleStore, load_snapshot, write_style_snapshot
from src.web_templates import WebSceneError, build_document, load_tokens, validate_tokens
from tests import style_fixtures as fx
from tests.test_style_pack import SAMPLES, _png, make_style

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "style_sources_section.py"


# ── 1. card contrast ─────────────────────────────────────────────────────────

def _with(style, theme, **colors):
    tokens = copy.deepcopy(style.tokens)
    tokens[theme].update(colors)
    return Style(id=style.id, name=style.name, tokens=tokens, mark_png=style.mark_png)


def test_text_must_be_readable_on_cards_too():
    base = make_style()
    # background fine for the text, card the same colour as the text
    with pytest.raises(StyleError, match="on a card"):
        validate_style(_with(base, "dark", bg_card=base.tokens["dark"]["text"]))
    # panel edit: light background + dark text, card left dark (the reviewer's reproduction)
    with pytest.raises(StyleError, match="on a card"):
        validate_style(_with(base, "dark", bg="#ffffff", text="#111111", text_muted="#444444",
                             accent="#0b5cad", accent_hi="#1f7ad6"))
    # muted text on a card
    with pytest.raises(StyleError, match="muted text on a card"):
        validate_style(_with(base, "light", bg_card="#8895a3"))


def test_card_colour_must_be_hex_for_the_check():
    with pytest.raises(StyleError, match="bg_card must be #rrggbb"):
        validate_style(_with(make_style(), "dark", bg_card="rgba(255, 255, 255, 0.5)"))


def test_shipped_corvin_tokens_still_pass_the_card_rule():
    validate_style(Style(id="sty_00000000", name="corvin", tokens=load_tokens(), wordmark="CorvinOS", decor="corvin"))


def test_importer_palettes_satisfy_the_card_rule_by_construction():
    rnd = random.Random(7)
    hexes = lambda: "#%06x" % rnd.randrange(0x1000000)  # noqa: E731
    for _ in range(400):
        bg, text, acc = hexes(), hexes(), hexes()
        pal, _ = imp._palette(bg, text, [acc], "#2ecc71")
        assert sp.contrast(pal["bg_card"], pal["text"]) >= 4.5, (bg, text)
        assert sp.contrast(pal["bg_card"], pal["text_muted"]) >= 3.0, (bg, text)


# ── 2. snapshot absent vs invalid ────────────────────────────────────────────

def test_snapshot_absent_is_none_but_corrupt_or_invalid_raises(tmp_path):
    assert load_snapshot(tmp_path / "none") is None
    (tmp_path / "empty").mkdir()
    assert load_snapshot(tmp_path / "empty") is None  # a directory without style.json: no snapshot
    good = tmp_path / "good"
    write_style_snapshot(make_style(), good)
    assert load_snapshot(good).name == "Acme"
    bad = tmp_path / "bad"
    write_style_snapshot(make_style(), bad)
    (bad / "style.json").write_text("{not json")
    with pytest.raises(StyleError):
        load_snapshot(bad)
    inv = tmp_path / "inv"
    write_style_snapshot(make_style(), inv)
    doc = json.loads((inv / "style.json").read_text())
    doc["tokens"]["dark"]["text"] = doc["tokens"]["dark"]["bg"]
    (inv / "style.json").write_text(json.dumps(doc))
    with pytest.raises(StyleError):
        load_snapshot(inv)
    (good / "logo.png").write_bytes(b"not a png")
    with pytest.raises(StyleError):
        load_snapshot(good)


def test_sources_section_script_fails_loudly_on_a_corrupt_snapshot(tmp_path):
    snap = tmp_path / "style"
    write_style_snapshot(make_style(), snap)
    (snap / "style.json").write_text("{broken")
    r = subprocess.run([sys.executable, str(SCRIPT), str(snap)], capture_output=True, text=True)
    assert r.returncode == 1 and "Built-in" not in r.stdout
    assert "unreadable or invalid" in r.stderr


# ── 3. brand-neutral prompt ──────────────────────────────────────────────────

def _captured_prompt(monkeypatch, brand_neutral):
    seen = {}

    def fake(prompt, **kw):
        seen["prompt"] = prompt
        raise RuntimeError("stop")
    monkeypatch.setattr(skill, "_call_storyboard_llm", fake)
    with pytest.raises(RuntimeError, match="stop"):
        asyncio.run(skill.generate_storyboard_with_llm("a task", backend="claude_cli", brand_neutral=brand_neutral))
    return seen["prompt"]


def test_neutral_prompt_has_no_corvin_wording_and_no_theme_choice(monkeypatch):
    neutral = _captured_prompt(monkeypatch, True)
    default = _captured_prompt(monkeypatch, False)
    assert "Corvin" not in neutral
    assert '"theme"' not in neutral and "Welcome to Corvin" not in neutral
    assert "Corvin" in default and '"theme": "dark" (default) or "light"' in default


# ── 4. one look per video ────────────────────────────────────────────────────

def test_import_warns_when_the_logo_is_hard_to_see_on_the_background():
    # a near-white logo on the deck's white background
    deck = fx.make_deck(logo_color=(250, 250, 250, 255))
    res = import_pptx(deck, "x.pptx")
    assert any("hard to see" in w for w in res.style.warnings)
    assert res.style.tokens[res.style.default_theme]["bg"] == "#ffffff"  # the palette is NOT changed for it
    assert not any("hard to see" in w for w in import_pptx(fx.make_deck(), "x.pptx").style.warnings)


# ── 5. Pillow fallback is style-aware ────────────────────────────────────────

# sha256 of the no-style classic slides, pinned before the style parameter existed
GOLDEN_CLASSIC = {
    "rich": "ff8401ff60dab1728d8df12a755ad8cf5f8b3196ae0ea7867f5be624ca662d83",
    "title": "ba94480079dc0cf30eecb3004d8a70e31ad20f5838fca335b71f7cb9c4c67eac",
    "shot": "39f6d252f25152817911029c66f3e6fc9afe068c2c90225e1021b6b3a9d17c09",
}


def test_classic_slide_without_a_style_is_byte_identical(tmp_path):
    cases = {
        "rich": (Scene(id="s", kind="example", duration_ms=8000, visual_description="check icon"),
                 dict(strategy="rich_visual", scene_index=2, total_scenes=5)),
        "title": (Scene(id="s", kind="title", duration_ms=8000), dict(strategy="minimal_visual")),
        "shot": (Scene(id="s", kind="screenshot", duration_ms=8000, visual_description="a shield"),
                 dict(strategy="rich_visual", scene_index=1, total_scenes=3)),
    }
    for name, (scene, kw) in cases.items():
        out = tmp_path / f"{name}.png"
        skill._render_slide_image(scene, out, **kw)
        assert hashlib.sha256(out.read_bytes()).hexdigest() == GOLDEN_CLASSIC[name], name


def test_classic_slide_with_a_style_uses_its_palette_and_wordmark(tmp_path):
    st = make_style(wordmark="Acme Corp")
    scene = Scene(id="s", kind="example", duration_ms=8000, visual_description="check icon")
    plain, styled = tmp_path / "p.png", tmp_path / "s.png"
    skill._render_slide_image(scene, plain, strategy="rich_visual", scene_index=2, total_scenes=5)
    skill._render_slide_image(scene, styled, strategy="rich_visual", scene_index=2, total_scenes=5, style=st)
    img = Image.open(styled).convert("RGB")
    colors = {c for _, c in img.getcolors(maxcolors=1_000_000)}
    assert (0x10, 0x18, 0x20) == img.getpixel((0, 0))                       # the style's background, not navy
    assert (0x3B, 0xA3, 0xFF) in colors                                      # its accent (divider, icon, dots)
    corvin = set(skill._KIND_ACCENT.values()) | {(138, 180, 255), skill._COLOR_NAVY_DARK, skill._COLOR_ICE}
    assert not (colors & corvin), "a Corvin colour is on a styled fallback slide"
    assert (0xC8, 0x1E, 0x1E) in colors                                      # the style's logo (small, top-left)
    assert styled.read_bytes() != plain.read_bytes()


# ── 6. preview shows the intro mark and page counter ─────────────────────────

def test_hero_with_scene_one_shows_the_intro_mark_and_counter():
    on = build_document("hero", SAMPLES["hero"], duration_s=6, scene_index=1, total_scenes=3,
                        style=make_style(intro_mark=True))
    off = build_document("hero", SAMPLES["hero"], duration_s=6, scene_index=1, total_scenes=3,
                         style=make_style(intro_mark=False))
    assert 'class="intro-mark"' in on and 'class="intro-mark"' not in off and "01 / 03" in on


def test_preview_samples_are_numbered_like_a_video(monkeypatch):
    calls = []

    class Fake:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def render_still(self, template, data, **kw):
            calls.append((template, kw.get("scene_index"), kw.get("total_scenes")))
            buf = io.BytesIO()
            Image.new("RGB", (64, 36)).save(buf, "PNG")
            return buf.getvalue()
    monkeypatch.setattr(style_preview, "WebSlideRenderer", Fake)
    out = asyncio.run(style_preview.render_previews(make_style()))
    assert len(out["previews"]) == 3
    assert calls == [("hero", 1, 3), ("diagram", 2, 3), ("quote", 3, 3)]


def test_real_preview_differs_with_and_without_the_intro_mark():
    async def go(flag):
        return await style_preview.render_previews(make_style(intro_mark=flag))
    on, off = asyncio.run(go(True)), asyncio.run(go(False))
    if not on["previews"]:
        pytest.skip("no headless browser on this host")
    assert on["previews"][0]["data_uri"] != off["previews"][0]["data_uri"]  # hero: mark or none
    assert on["previews"][1]["data_uri"] == off["previews"][1]["data_uri"]  # later samples unaffected


# ── 8. poisoned style ────────────────────────────────────────────────────────

def test_unknown_token_keys_and_oversized_styles_are_refused():
    base = make_style()
    t = copy.deepcopy(base.tokens)
    t["pad"] = "x" * 200_000
    with pytest.raises(StyleError, match="unknown design token group"):
        validate_style(Style(id=base.id, name="p", tokens=t))
    for key in ("version", "source"):
        t = copy.deepcopy(base.tokens)
        t[key] = "x" * 121
        with pytest.raises(StyleError, match="120"):
            validate_style(Style(id=base.id, name="p", tokens=t))
        t[key] = ["x"]
        with pytest.raises(StyleError):
            validate_style(Style(id=base.id, name="p", tokens=t))
    t = copy.deepcopy(base.tokens)
    t["typography"]["pad"] = "x" * 200_000  # allowed key, huge value
    with pytest.raises(StyleError, match="larger than"):
        validate_style(Style(id=base.id, name="p", tokens=t))


def test_every_style_that_validates_can_be_stored_and_loaded(tmp_path):
    store = StyleStore(str(tmp_path))
    base = make_style()
    lo, hi = 0, 200_000
    while lo < hi - 1:  # largest accepted padding
        mid = (lo + hi) // 2
        t = copy.deepcopy(base.tokens)
        t["typography"]["pad"] = "x" * mid
        try:
            validate_style(Style(id=base.id, name="p", tokens=t))
            lo = mid
        except StyleError:
            hi = mid
    t = copy.deepcopy(base.tokens)
    t["typography"]["pad"] = "x" * lo
    st = Style(id=store.new_id(), name="p", tokens=t)
    store.save(st)
    assert store.load(st.id).tokens["typography"]["pad"] == "x" * lo


def test_wire_draft_with_an_oversized_extra_key_is_refused():
    wire = sp.draft_to_wire(make_style())
    wire["tokens"]["junk"] = "x" * 200_000
    with pytest.raises(StyleError):
        sp.draft_from_wire(wire, style_id="sty_0a1b2c3d", imported_at="2026-01-01T00:00:00Z")


# ── 9. validate_tokens TypeError ─────────────────────────────────────────────

@pytest.mark.parametrize("value", [[], {}, [1], {"a": 1}, 1, 1.5, True, None, ["Newsreader"]])
@pytest.mark.parametrize("key", ["heading_family", "body_family", "mono_family"])
def test_non_string_font_families_are_a_scene_error_not_a_type_error(key, value):
    tokens = copy.deepcopy(load_tokens())
    tokens["typography"][key] = value
    with pytest.raises(WebSceneError):
        validate_tokens(tokens)
    with pytest.raises(StyleError):
        validate_style(Style(id="sty_0a1b2c3d", name="f", tokens=tokens))


@pytest.mark.parametrize("fonts", [5, "x", {"a": 1}, None])
def test_font_mapping_must_be_a_list(fonts):
    with pytest.raises(StyleError):
        make_style(fonts=fonts)


# ── 10. decode cost ──────────────────────────────────────────────────────────

def test_oversized_logo_is_refused_from_the_header_without_decoding_pixels(monkeypatch):
    import base64
    big = base64.b64encode(_png((3000, 3000))).decode()
    wire = sp.draft_to_wire(make_style())
    wire["mark_png_b64"] = big
    loads = []
    real = Image.Image.load

    def spy(self, *a, **k):
        loads.append(1)
        return real(self, *a, **k)
    monkeypatch.setattr(Image.Image, "load", spy)
    with pytest.raises(StyleError, match="dimensions"):
        sp.draft_from_wire(wire, style_id="sty_0a1b2c3d", imported_at="2026-01-01T00:00:00Z")
    assert loads == [], "pixels were decoded before the size cap refused the logo"


# ── 11. importer CPU bound ───────────────────────────────────────────────────

_NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
       'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def _node_bomb(layouts=60, nodes=140_000) -> bytes:
    """Every part is under the per-part cap; together they are millions of nodes in a tiny zip."""
    rels = "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" '
                   f'Target="../slideLayouts/slideLayout{i}.xml"/>' for i in range(1, layouts + 1))
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/></Types>')
        z.writestr("ppt/presentation.xml", f'<p:presentation {_NS}><p:sldSz cx="12192000" cy="6858000"/></p:presentation>')
        z.writestr("ppt/slideMasters/slideMaster1.xml", f"<p:sldMaster {_NS}><p:cSld/></p:sldMaster>")
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels",
                   f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        body = "<p:x/>" * nodes
        for i in range(1, layouts + 1):
            z.writestr(f"ppt/slideLayouts/slideLayout{i}.xml", f"<p:sldLayout {_NS}><p:cSld><p:spTree>{body}</p:spTree></p:cSld></p:sldLayout>")
    return b.getvalue()


def test_many_parts_below_the_per_part_cap_hit_the_total_node_budget():
    deck = _node_bomb()
    assert len(deck) < 200_000
    t0 = time.monotonic()
    with pytest.raises(PptxImportError, match="too complex to read"):
        import_pptx(deck, "bomb.pptx")
    assert time.monotonic() - t0 < 8.5


def test_total_node_budget_and_wall_clock_budget_are_enforced(monkeypatch):
    deck = fx.make_deck()
    import_pptx(deck, "ok.pptx")
    monkeypatch.setattr(imp, "MAX_XML_NODES_TOTAL", 5)
    with pytest.raises(PptxImportError, match="too complex to read"):
        import_pptx(deck, "x.pptx")
    monkeypatch.setattr(imp, "MAX_XML_NODES_TOTAL", 1_500_000)
    monkeypatch.setattr(imp, "MAX_IMPORT_SECONDS", -1.0)
    with pytest.raises(PptxImportError, match="too complex to read"):
        import_pptx(deck, "x.pptx")


# ── 12. quota race ───────────────────────────────────────────────────────────

def _save_one(base):
    store = StyleStore(base)
    try:
        store.save(make_style(id=store.new_id()))
        return "ok"
    except StyleQuotaExceeded:
        return "quota"


def _prefilled(tmp_path, n):
    store = StyleStore(str(tmp_path))
    for _ in range(n):
        store.save(make_style(id=store.new_id()))
    return store


def test_quota_holds_under_concurrent_saves_in_threads(tmp_path):
    store = _prefilled(tmp_path, MAX_STYLES - 6)
    with ThreadPoolExecutor(12) as ex:
        res = list(ex.map(lambda _: _save_one(str(tmp_path)), range(12)))
    assert len(store.ids()) == MAX_STYLES and res.count("ok") == 6 and res.count("quota") == 6
    assert not [p for p in store.root.iterdir() if p.name.endswith(".new")]


def test_quota_holds_under_concurrent_saves_in_processes(tmp_path):
    store = _prefilled(tmp_path, MAX_STYLES - 6)
    with ProcessPoolExecutor(6) as ex:
        res = list(ex.map(_save_one, [str(tmp_path)] * 12))
    assert len(store.ids()) == MAX_STYLES and res.count("ok") == 6
