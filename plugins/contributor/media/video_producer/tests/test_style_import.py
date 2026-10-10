"""PowerPoint style importer: extraction, mapping, hardening (PLAN-0945 P2)."""

import json
import socket
import subprocess
import tracemalloc
from concurrent.futures import ThreadPoolExecutor

import pytest

from src import style_import_pptx as imp
from src.style_import_pptx import PptxImportError, import_pptx
from src.style_pack import StyleError, contrast, draft_from_wire, draft_to_wire, validate_style
from tests import style_fixtures as fx


@pytest.fixture(autouse=True)
def no_network_or_processes(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("importer must not use the network or spawn processes")
    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)


def run_with_timeout(fn, *args, timeout=60):
    with ThreadPoolExecutor(1) as ex:
        return ex.submit(fn, *args).result(timeout=timeout)


def own(res):
    return res.style.tokens[res.style.default_theme]


# ── positive ────────────────────────────────────────────────────────────────

def test_distinct_deck_extraction():
    res = import_pptx(fx.make_deck(), "Acme Q3 Template.pptx")
    st = res.style
    assert st.id == "sty_00000000" and st.name == "Acme Q3 Template"
    assert st.source["kind"] == "pptx" and st.source["deck_aspect"] == "16:9"
    assert st.default_theme == "light" and own(res)["bg"] == "#ffffff"
    assert own(res)["accent"] == "#c2185b" and own(res)["text"] == "#1a1a2e"
    typo = st.tokens["typography"]
    assert (typo["heading_family"], typo["body_family"]) == ("Newsreader", "Instrument Sans")
    assert {m["from"] for m in st.fonts} == {"Georgia", "Verdana"}
    assert st.mark_png and st.intro_mark and st.wordmark == "" and st.credit is False and st.decor == "minimal"
    from PIL import Image
    import io
    assert Image.open(io.BytesIO(st.mark_png)).size == (200, 100)
    assert res.notes == st.warnings and not any("default Office" in w for w in st.warnings)
    validate_style(st)


def test_wire_roundtrip_and_no_private_content():
    res = import_pptx(fx.make_deck(), "x.pptx")
    wire = draft_to_wire(res.style)
    back = draft_from_wire(json.loads(json.dumps(wire)), style_id="sty_0a1b2c3d", imported_at="2026-10-10T00:00:00Z")
    assert back.tokens == res.style.tokens and back.mark_png == res.style.mark_png
    blob = json.dumps(wire)
    for secret in (fx.SECRET_TEXT, fx.SECRET_NOTE, fx.SECRET_AUTHOR):
        assert secret not in blob


def test_source_sha_is_of_upload():
    import hashlib
    data = fx.make_deck()
    assert import_pptx(data).style.source["sha256"] == hashlib.sha256(data).hexdigest()


def test_43_deck_aspect_and_warning():
    res = import_pptx(fx.make_deck(aspect="4:3"))
    assert res.style.source["deck_aspect"] == "4:3"
    assert any("4:3" in w for w in res.notes)


def test_template_kind_is_potx():
    assert import_pptx(fx.make_deck(template=True)).style.source["kind"] == "potx"


def test_extension_is_not_trusted():
    assert import_pptx(fx.make_deck(), "deck.txt").style.name == "deck"
    assert import_pptx(fx.make_deck(), "").style.name == "Imported style"


@pytest.mark.parametrize("raw,expect", [
    ("../../<script>alert(1)</script>.pptx", "script"),
    ("a" * 200 + ".pptx", "a" * 60),
    ("evil\x00\x1b name & \"q\".pptx", "evil name q"),
    ("...pptx", "Imported style"),
])
def test_name_sanitised(raw, expect):
    name = import_pptx(fx.make_deck(), raw).style.name
    assert name == expect
    assert not set(name) & set("<>&\"'\x00\x1b/\\") and len(name) <= 60


def test_dark_deck_by_background_and_clrmap():
    res = import_pptx(fx.make_deck(bg="0b0f1a"))
    assert res.style.default_theme == "dark" and own(res)["bg"] == "#0b0f1a"
    assert res.style.tokens["light"]["bg"] != "#0b0f1a"
    inv = import_pptx(fx.make_deck(clrmap=("dk1", "lt1"), scheme=dict(fx.DISTINCT_SCHEME, dk1="101820", lt1="f2f2f2")))
    assert inv.style.default_theme == "dark" and own(inv)["bg"] == "#101820"


def test_both_themes_pass_contrast():
    for kw in ({}, {"bg": "0b0f1a"}, {"bg": "808080"}, {"scheme": fx.OFFICE_2013_SCHEME}):
        st = import_pptx(fx.make_deck(**kw)).style
        for theme in ("dark", "light"):
            p = st.tokens[theme]
            assert contrast(p["bg"], p["text"]) >= 4.5 and contrast(p["bg"], p["accent"]) >= 3.0


def test_low_contrast_accent_is_adjusted_and_said():
    scheme = dict(fx.DISTINCT_SCHEME, accent1="ffee88", accent2="ffee99", accent3="ffeeaa",
                  accent4="ffeebb", accent5="ffeecc", accent6="ffeedd")
    res = import_pptx(fx.make_deck(scheme=scheme))
    assert contrast("#ffffff", own(res)["accent"]) >= 3.0
    assert any("accent colour was adjusted" in w for w in res.notes)


def test_first_readable_accent_wins():
    scheme = dict(fx.DISTINCT_SCHEME, accent1="ffee88")
    assert own(import_pptx(fx.make_deck(scheme=scheme)))["accent"] == "#0f3460"


# ── office defaults ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("pair,name", [(("4f81bd", "c0504d"), "Office 2007-2010"), (("4472c4", "ed7d31"), "Office 2013-2022"),
                                       (("156082", "e97132"), "Office 2023"), (("c2185b", "0f3460"), None)])
def test_office_default_detection(pair, name):
    assert imp.office_default_name({"accent1": pair[0], "accent2": pair[1]}) == name


def test_default_palette_samples_logo_colour():
    res = import_pptx(fx.make_deck(scheme=fx.OFFICE_2013_SCHEME, major="Calibri Light", minor="Calibri",
                                   logo_color=(11, 114, 133, 255)))
    acc = own(res)["accent"]
    assert any("default Office colours" in w and "sampled" in w for w in res.notes)
    r, g, b = (int(acc[i:i + 2], 16) for i in (1, 3, 5))
    assert abs(r - 11) < 24 and abs(g - 114) < 24 and abs(b - 133) < 24
    assert acc not in ("#4472c4", "#ed7d31")


def test_default_palette_samples_master_shape():
    res = import_pptx(fx.make_deck(scheme=fx.OFFICE_2007_SCHEME, logo=None, shape_fill="7a1fa2"))
    assert own(res)["accent"] == "#7a1fa2"


def test_default_palette_without_hints_is_flagged_neutral_never_default_blue():
    res = import_pptx(fx.make_deck(scheme=fx.OFFICE_2013_SCHEME, logo=None))
    assert any("neutral accent" in w for w in res.notes)
    assert own(res)["accent"] not in ("#4472c4", "#4f81bd")
    assert not res.style.mark_png and not res.style.intro_mark


# ── fonts ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,family", [
    ("Arial", "Instrument Sans"), ("Calibri Light", "Instrument Sans"), ("Aptos Display", "Instrument Sans"),
    ("Times New Roman", "Newsreader"), ("Georgia", "Newsreader"), ("Cambria", "Newsreader"),
    ("Consolas", "JetBrains Mono"), ("Courier New", "JetBrains Mono"), ("Segoe UI", "Instrument Sans"),
    ("Source Sans Pro", "Instrument Sans"), ("Zzyzx Display", "Instrument Sans"), ("", "Instrument Sans")])
def test_font_mapping(name, family):
    assert imp.map_font(name)[0] == family


def test_external_rels_and_embedded_fonts_reported_not_followed():
    res = import_pptx(fx.make_deck(external_rels=3, embedded_fonts=4))
    assert any("3 linked external" in w for w in res.notes)
    assert any("4 embedded font" in w for w in res.notes)


# ── determinism ─────────────────────────────────────────────────────────────

def test_deterministic():
    data = fx.make_deck(scheme=fx.OFFICE_2013_SCHEME)
    a = json.dumps(draft_to_wire(import_pptx(data, "d.pptx").style), sort_keys=True)
    b = json.dumps(draft_to_wire(import_pptx(data, "d.pptx").style), sort_keys=True)
    assert a == b


# ── hostile corpus ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(fx.HOSTILE_REFUSED))
def test_hostile_refused_without_hanging(name):
    data = fx.HOSTILE_REFUSED[name]()
    with pytest.raises(PptxImportError) as e:
        run_with_timeout(import_pptx, data, "evil.pptx")
    assert isinstance(e.value, StyleError) and str(e.value) and "Traceback" not in str(e.value)


@pytest.mark.parametrize("name", ["zip_bomb", "total_size_bomb", "dtd_entity_bomb", "node_bomb"])
def test_refusal_happens_before_inflation(name):
    data = fx.HOSTILE_REFUSED[name]()
    tracemalloc.start()
    try:
        with pytest.raises(PptxImportError):
            import_pptx(data)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 40 * 1024 * 1024, f"{name}: peak {peak}"


def test_svg_logo_is_dropped_with_a_note():
    res = run_with_timeout(import_pptx, fx.svg_script_logo())
    assert res.style.mark_png is None and not res.style.intro_mark
    assert any("vector logo" in w for w in res.notes)
    assert "script" not in json.dumps(draft_to_wire(res.style))


def test_declared_huge_image_is_dropped_not_decoded():
    res = run_with_timeout(import_pptx, fx.image_bomb())
    assert res.style.mark_png is None


def test_large_logo_is_downscaled_and_capped():
    from PIL import Image
    import io
    res = import_pptx(fx.make_deck(logo=fx.png_bytes(size=(3000, 1500))))
    im = Image.open(io.BytesIO(res.style.mark_png))
    assert max(im.size) <= 1024 and len(res.style.mark_png) <= 2 * 1024 * 1024


def test_xml_parser_rules():
    for bad in (b"<!DOCTYPE a><a/>", b"<?xml version='1.0'?><!ENTITY x 'y'><a/>", "<a/>".encode("utf-16"), b"<a><b></a>", b""):
        with pytest.raises(PptxImportError):
            imp.parse_xml(bad)
    assert imp.parse_xml(b"<a><b/></a>").tag == "a"


def test_unsupported_compression_refused():
    import zipfile
    data = fx.zip_of({"[Content_Types].xml": b"<a/>"}, compression=zipfile.ZIP_BZIP2)
    with pytest.raises(PptxImportError):
        import_pptx(data)


def test_non_deck_zip_refused():
    with pytest.raises(PptxImportError):
        import_pptx(fx.zip_of({"hello.txt": b"hi"}))
