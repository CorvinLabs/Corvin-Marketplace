"""Style Pack: schema, safety/contrast rules, renderer parameterisation (PLAN-0945 P1)."""

import copy
import hashlib
import io
import json
from pathlib import Path

import pytest

from src import style_pack as sp
from src import web_templates as wt
from src.style_pack import Style, StyleError, validate_style
from src.web_templates import THEMES, build_document, load_tokens
from tests.test_web_templates import SAMPLES

GOLDEN = json.loads((Path(__file__).parent / "golden_corvin_html.json").read_text())


def _png(size=(64, 64), color=(200, 30, 30, 255)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, "PNG")
    return buf.getvalue()


def make_style(**kw) -> Style:
    tokens = copy.deepcopy(load_tokens())
    tokens["dark"].update(bg="#101820", bg_card="#18232e", border="#2a3a4a", accent="#3ba3ff",
                          accent_hi="#8cc8ff", glow="rgba(59, 163, 255, 0.16)")
    tokens["light"].update(bg="#ffffff", bg_card="#f4f6f8", border="#d8dee4", text="#1a2330",
                           text_muted="#566474", accent="#0b5cad", accent_hi="#1f7ad6",
                           glow="rgba(11, 92, 173, 0.18)")
    args = dict(id="sty_0a1b2c3d", name="Acme", tokens=tokens, wordmark="Acme Corp", decor="minimal",
                mark_png=_png())
    args.update(kw)
    return validate_style(Style(**args))


# ── regression: no style == today, byte for byte ─────────────────────────────

@pytest.mark.parametrize("key", sorted(GOLDEN))
def test_corvin_output_is_byte_identical(key):
    name, theme, idx = key.split("|")
    idx = None if idx == "None" else int(idx)
    doc = build_document(name, SAMPLES[name], duration_s=6, theme=theme, scene_index=idx,
                         total_scenes=8 if idx else None)
    assert hashlib.sha256(doc.encode()).hexdigest() == GOLDEN[key]


def test_golden_covers_every_template_and_theme():
    assert {k.split("|")[0] for k in GOLDEN} == set(wt.TEMPLATES)
    assert {k.split("|")[1] for k in GOLDEN} == set(THEMES)


# ── rendering with a style ───────────────────────────────────────────────────

def test_style_replaces_the_corvin_look():
    st = make_style()
    for name, data in SAMPLES.items():
        doc = build_document(name, data, duration_s=6, style=st, scene_index=1, total_scenes=3)
        assert "#3ba3ff" in doc or "#0b5cad" in doc
        assert "Acme Corp" in doc
        assert "corvinOS" not in doc.replace("corvinOS-symbol", "")  # no CorvinOS wordmark text
        assert "C9A227" not in doc, "the Corvin gold dot must not appear"
        assert 'class="stars"' not in doc and 'class="ring"' not in doc  # minimal decor
        assert 'class="glow"' in doc


@pytest.mark.parametrize("decor,has", [("corvin", (True, True, True)), ("minimal", (True, False, False)),
                                       ("none", (False, False, False))])
def test_decor_modes(decor, has):
    doc = build_document("hero", SAMPLES["hero"], duration_s=6, style=make_style(decor=decor))
    assert (('class="glow"' in doc), ('class="ring"' in doc), ('class="stars"' in doc)) == has


def test_intro_mark_uses_the_styles_mark_and_can_be_off():
    st = make_style()
    on = build_document("hero", SAMPLES["hero"], duration_s=6, style=st, scene_index=1, total_scenes=3)
    assert 'class="intro-mark"' in on and "data:image/png;base64" in on
    assert 'class="intro-mark' not in build_document("hero", SAMPLES["hero"], duration_s=6, style=st,
                                                     scene_index=2, total_scenes=3)
    off = build_document("hero", SAMPLES["hero"], duration_s=6, style=make_style(intro_mark=False),
                         scene_index=1, total_scenes=3)
    assert 'class="intro-mark' not in off


def test_style_without_a_mark_has_no_intro_and_no_symbol():
    st = make_style(mark_png=None)
    doc = build_document("hero", SAMPLES["hero"], duration_s=6, style=st, scene_index=1, total_scenes=3)
    assert "intro-mark" not in doc.split("</style>")[1] and "<img" not in doc


def test_credit_is_off_by_default_and_opt_in():
    assert "made with CorvinOS" not in build_document("hero", SAMPLES["hero"], duration_s=6, style=make_style())
    assert "made with CorvinOS" in build_document("hero", SAMPLES["hero"], duration_s=6,
                                                  style=make_style(credit=True))


def test_wordmark_is_escaped_and_markup_is_stripped():
    st = make_style(wordmark='<script>alert(1)</script>"x')
    assert "<" not in st.wordmark and ">" not in st.wordmark and '"' not in st.wordmark
    assert "<script>alert" not in build_document("hero", SAMPLES["hero"], duration_s=6, style=st)


# ── safety and contrast rules ────────────────────────────────────────────────

def _tweak(path, value):
    st = make_style()
    st.tokens = copy.deepcopy(st.tokens)
    theme, key = path
    st.tokens[theme][key] = value
    return st


@pytest.mark.parametrize("path,value,fragment", [
    (("dark", "text"), "#20282f", "text on the background"),
    (("dark", "text_muted"), "#18232e", "muted text"),
    (("light", "accent"), "#f0f0f0", "accent on the background"),
    (("dark", "accent_hi"), "#18232e", "accent highlight"),
])
def test_low_contrast_is_refused(path, value, fragment):
    with pytest.raises(StyleError, match=fragment):
        validate_style(_tweak(path, value))


def test_dimmed_item_must_stay_readable():
    st = make_style()
    st.tokens = copy.deepcopy(st.tokens)
    st.tokens["dark"].update(bg="#808080", text="#ffffff")  # text passes 4.5? no: ensure the dim rule trips first
    with pytest.raises(StyleError):
        validate_style(st)


def test_unbundled_font_is_refused():
    st = make_style()
    st.tokens = copy.deepcopy(st.tokens)
    st.tokens["typography"]["body_family"] = "Arial"
    with pytest.raises(StyleError, match="bundled"):
        validate_style(st)


@pytest.mark.parametrize("bad", ["sty_XYZ", "../x", "corvinx", "", "sty_0a1b2c3"])
def test_bad_style_id_is_refused(bad):
    with pytest.raises(StyleError, match="id"):
        make_style(id=bad)


def test_oversize_and_non_png_assets_are_refused():
    with pytest.raises(StyleError, match="PNG"):
        make_style(mark_png=b"<svg onload=alert(1)/>")
    with pytest.raises(StyleError, match="limit"):
        make_style(mark_png=sp._PNG_MAGIC + b"\x00" * (sp.MAX_ASSET_BYTES + 1))
    with pytest.raises(StyleError, match="decodable"):
        make_style(mark_png=sp._PNG_MAGIC + b"garbage")


def test_decompression_bomb_dimensions_are_refused():
    with pytest.raises(StyleError):
        make_style(mark_png=_png((2000, 2000)))  # logo cap is 1024 px


def test_plate_keys_are_ignored_not_an_error():
    st = make_style()
    wire = sp.draft_to_wire(st)
    assert not any("plate" in k for k in wire) and "plate" not in st.to_json()
    wire.update(plate_png_b64="AAAA", plate_safe={"x": 1})
    back = sp.draft_from_wire(wire, style_id="sty_0a1b2c3d", imported_at="2026-01-01T00:00:00Z")
    assert back.tokens == st.tokens
    doc = st.to_json()
    doc["plate"] = {"safe": {"x": 0, "y": 0, "w": 1920, "h": 1080}}  # an old stored document
    assert sp.style_from_json(doc, mark_png=st.mark_png).name == "Acme"


def test_wordmark_and_name_limits():
    with pytest.raises(StyleError, match="limit"):
        make_style(wordmark="x" * 41)
    with pytest.raises(StyleError, match="limit"):
        make_style(name="x" * 61)
    with pytest.raises(StyleError, match="empty"):
        make_style(name="  ")


def test_json_roundtrip_revalidates():
    st = make_style()
    doc = json.loads(json.dumps(st.to_json()))
    back = sp.style_from_json(doc, mark_png=st.mark_png)
    assert back.tokens == st.tokens and back.wordmark == st.wordmark
    doc["tokens"]["dark"]["text"] = "#101820"
    with pytest.raises(StyleError):
        sp.style_from_json(doc, mark_png=st.mark_png)
    with pytest.raises(StyleError):
        sp.style_from_json({"schema": 99})


def test_corvin_palette_passes_the_same_rules():
    tokens = load_tokens()
    st = Style(id="sty_00000000", name="corvin", tokens=tokens, wordmark="CorvinOS", decor="corvin")
    validate_style(st)  # the rules must not be stricter than the look we ship
