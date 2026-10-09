"""Template contract, escaping and design-token validation (ADR-2238, PLAN-0940 P1/P2)."""

import copy
import json
import re

import pytest

from src import web_templates as wt
from src.web_templates import WebSceneError, build_document, load_tokens, validate_scene_data, validate_tokens

SAMPLES = {
    "hero": {"badge": "b", "title": "Title", "accent": "Accent", "subtitle": "Sub"},
    "content": {"eyebrow": "e", "title": "T", "bullets": ["a", "b"]},
    "stat": {"value": 1234.5, "decimals": 1, "suffix": "%", "label": "L", "locale": "de"},
    "diagram": {"title": "T", "nodes": [{"label": "A"}, {"label": "B", "sub": "s"}], "highlight": 1},
    "chart": {"title": "T", "bars": [{"label": "a", "value": 1}, {"label": "b", "value": 3}], "unit": "s"},
    "compare": {"title": "T", "left": {"title": "L", "points": ["x"]}, "right": {"title": "R", "points": ["y"]}},
    "quote": {"quote": "Q", "attribution": "A", "locale": "de"},
    "code": {"title": "T", "language": "sh", "lines": ["$ echo hi", "# comment"]},
    "line": {"title": "T", "labels": ["a", "b", "c"], "series": [{"values": [1, 3, 2]}], "highlight": 1},
    "donut": {"title": "T", "segments": [{"label": "a", "value": 3}, {"label": "b", "value": 1}], "highlight": 0},
    "flow": {"title": "T", "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B", "sub": "s"}],
             "edges": [{"from": "a", "to": "b", "label": "x"}], "highlight": "b"},
    "timeline": {"title": "T", "events": [{"when": "1", "label": "A"}, {"when": "2", "label": "B"}], "current": 0},
    "cycle": {"title": "T", "center": "C", "steps": [{"label": "a"}, {"label": "b"}, {"label": "c"}]},
    "layers": {"title": "T", "layers": [{"label": "a", "tag": "x"}, {"label": "b", "sub": "s"}], "highlight": 0},
    "console_still": {"title": "T", "asset": "audit_compliance", "callouts": [{"spot": "hash_chain_card", "label": "c"}],
                      "zoom": {"spot": "hash_chain_card", "scale": 1.2}},
}


def test_every_template_has_a_sample_and_builds():
    assert set(SAMPLES) == set(wt.TEMPLATES)
    for name, data in SAMPLES.items():
        doc = build_document(name, data, duration_s=6)
        assert doc.startswith("<!doctype html>")


@pytest.mark.parametrize("name", list(SAMPLES))
def test_document_is_self_contained(name):
    doc = build_document(name, SAMPLES[name], duration_s=6)
    assert "<script" not in doc.lower()
    # the only url() are the inlined font data URIs and same-document fragment
    # references (an SVG gradient: "#id" resolves inside the page, never fetches)
    urls = re.findall(r"url\(([^)]*)\)", doc)
    fonts = [u for u in urls if u.startswith("data:font/woff2;base64,")]
    assert fonts and all(u in fonts or re.fullmatch(r"#[a-z][a-z0-9-]*", u) for u in urls)
    assert "http://" not in doc and "https://" not in doc
    assert "@import" not in doc


PAYLOADS = ['<script>alert(1)</script>', '"><img src=x onerror=alert(1)>', "</style><style>*{display:none}",
            "javascript:alert(1)", "{{7*7}} ${x} $title"]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_text_fields_are_escaped_everywhere(payload):
    cases = {
        "hero": {"title": payload[:70], "subtitle": payload},
        "content": {"title": "t", "bullets": [payload]},
        "diagram": {"title": "t", "nodes": [{"label": payload[:28]}, {"label": "b", "sub": payload[:48]}]},
        "chart": {"title": payload[:80], "bars": [{"label": payload[:24], "value": 1}, {"label": "b", "value": 2}]},
        "compare": {"title": "t", "left": {"title": payload[:40], "points": [payload]}, "right": {"title": "r", "points": ["p"]}},
        "quote": {"quote": payload},
        "code": {"title": "t", "lines": [payload]},
        "line": {"title": payload[:80], "labels": [payload[:12], "b", "c"], "unit": payload[:8],
                 "series": [{"name": payload[:24], "values": [1, 2, 3]}, {"name": "n", "values": [3, 2, 1]}]},
        "donut": {"title": "t", "center_label": payload[:28],
                  "segments": [{"label": payload[:28], "value": 1}, {"label": "b", "value": 2}]},
        "flow": {"title": "t", "nodes": [{"id": "a", "label": payload[:24], "sub": payload[:36]}, {"id": "b", "label": "b"}],
                 "edges": [{"from": "a", "to": "b", "label": payload[:18]}]},
        "timeline": {"title": "t", "events": [{"when": payload[:16], "label": payload[:28], "sub": payload[:60]},
                                              {"when": "w", "label": "l"}]},
        "cycle": {"title": payload[:60], "caption": payload, "center": payload[:24],
                  "steps": [{"label": payload[:22], "sub": payload[:40]}, {"label": "b"}, {"label": "c"}]},
        "layers": {"title": "t", "layers": [{"label": payload[:32], "sub": payload[:64], "tag": payload[:12]},
                                            {"label": "b"}]},
    }
    for name, data in cases.items():
        doc = build_document(name, data, duration_s=5)
        body = doc.split("</style>", 1)[1]
        assert "<script" not in body and "<img" not in body and "<style" not in body, name


def test_closed_template_enum_and_unknown_fields():
    with pytest.raises(WebSceneError, match="unknown template"):
        validate_scene_data("slideshow", {})
    with pytest.raises(WebSceneError, match="unknown field"):
        validate_scene_data("hero", {"title": "t", "html": "<b>x</b>"})
    with pytest.raises(WebSceneError, match="unknown field"):
        validate_scene_data("diagram", {"title": "t", "nodes": [{"label": "a", "style": "x"}, {"label": "b"}]})


@pytest.mark.parametrize("name,data,msg", [
    ("hero", {"title": "x" * 71}, "limit"),
    ("hero", {"title": 5}, "string"),
    ("content", {"title": "t", "bullets": []}, "1-5"),
    ("content", {"title": "t", "bullets": ["a"] * 6}, "1-5"),
    ("stat", {"value": float("nan"), "label": "l"}, "finite"),
    ("stat", {"value": True, "label": "l"}, "finite"),
    ("stat", {"value": 1e10, "label": "l"}, "1e9"),
    ("stat", {"value": 1, "label": "l", "decimals": 3}, "decimals"),
    ("stat", {"value": 1, "label": "l", "locale": "fr"}, "locale"),
    ("chart", {"title": "t", "bars": [{"label": "a", "value": -1}, {"label": "b", "value": 1}]}, ">= 0"),
    ("chart", {"title": "t", "bars": [{"label": "a", "value": 0}, {"label": "b", "value": 0}]}, "> 0"),
    ("diagram", {"title": "t", "nodes": [{"label": "a"}, {"label": "b"}], "highlight": 2}, "highlight"),
    ("code", {"title": "t", "lines": ["a\nb"]}, "line break"),
    ("code", {"title": "t", "lines": ["x"] * 13}, "1-12"),
])
def test_field_contract(name, data, msg):
    with pytest.raises(WebSceneError, match=re.escape(msg)):
        validate_scene_data(name, data)


def test_stat_locale_formatting_and_odometer_digits():
    doc = build_document("stat", {"value": 1234.5, "decimals": 1, "label": "l", "locale": "de"}, duration_s=5)
    assert doc.count('class="odo"') == 5  # 1 2 3 4 5
    body = doc.split("</style>", 1)[1]
    assert '<span class="ch">.</span>' in body and '<span class="ch">,</span>' in body


def test_timing_spreads_reveals_inside_the_narration():
    t0, stagger = wt.timing(10.0, 4)
    assert t0 + 6 * stagger <= 10.0 * 0.6 + t0
    assert wt.timing(0.5, 50)[1] >= 0.18 and wt.timing(60, 1)[1] <= 1.6


# ── design tokens ──

def test_bundled_tokens_are_valid():
    tokens = load_tokens()
    assert tokens["dark"]["accent"] == "#e8a83a"  # corvin-labs.com accent


@pytest.mark.parametrize("path,value", [
    (("dark", "accent"), "red;} body{display:none"),
    (("dark", "bg"), "url(https://evil.example/x.png)"),
    (("light", "glow"), "rgba(300, 0, 0, 0.5)"),
    (("dark", "text"), "expression(alert(1))"),
    (("typography", "heading_family"), "Inter"),
    (("typography", "body_family"), "x'; } * { color: red"),
    (("animation", "easing"), "steps(1); background:url(x)"),
    (("animation", "rise_ms"), 10),
])
def test_tokens_reject_css_injection_and_unbundled_fonts(path, value):
    tokens = copy.deepcopy(load_tokens())
    tokens[path[0]][path[1]] = value
    with pytest.raises(WebSceneError):
        validate_tokens(tokens)


def test_missing_theme_rejected():
    tokens = copy.deepcopy(load_tokens())
    del tokens["light"]
    with pytest.raises(WebSceneError, match="light"):
        validate_tokens(tokens)


def test_bundled_fonts_and_licences_ship_with_the_plugin():
    for files in wt.BUNDLED_FONTS.values():
        for filename, _ in files:
            assert (wt.WEB_DIR / "fonts" / filename).stat().st_size > 10_000
    for lic in ("newsreader", "instrumentsans", "jetbrainsmono"):
        assert "SIL Open Font License" in (wt.WEB_DIR / "fonts" / f"OFL-{lic}.txt").read_text()


# ── review round 1 regressions ──

def test_lone_surrogate_is_a_validation_error_not_a_crash():
    with pytest.raises(WebSceneError, match="invalid character"):
        validate_scene_data("hero", {"title": "A\ud800"})
    with pytest.raises(WebSceneError, match="invalid character"):
        validate_scene_data("code", {"title": "t", "lines": ["x\udfff"]})


def test_bidi_and_zero_width_characters_are_removed():
    d = validate_scene_data("hero", {"title": "safe\u202etxt.exe\u200b\ufeff"})
    assert d["title"] == "safetxt.exe"


@pytest.mark.parametrize("value", [10 ** 400, -(10 ** 400)])
def test_huge_integers_are_rejected(value):
    with pytest.raises(WebSceneError, match="range"):
        validate_scene_data("stat", {"value": value, "label": "l"})


def test_negative_zero_renders_as_zero():
    assert validate_scene_data("stat", {"value": -0.0, "label": "l"})["value"] == 0.0
    body = build_document("stat", {"value": -0.0, "label": "l"}, duration_s=3).split("</style>", 1)[1]
    assert ">-<" not in body


@pytest.mark.parametrize("path,value", [(("dark", "accent"), "#000000\n"), (("animation", "easing"), "cubic-bezier(0, 0, 1, 1)\n")])
def test_token_patterns_match_the_whole_value(path, value):
    tokens = copy.deepcopy(load_tokens())
    tokens[path[0]][path[1]] = value
    with pytest.raises(WebSceneError):
        validate_tokens(tokens)


def test_token_file_must_be_a_small_regular_file(tmp_path):
    import os
    big = tmp_path / "big.json"
    big.write_text(" " * (wt.MAX_TOKENS_BYTES + 10))
    with pytest.raises(WebSceneError, match="64 KB"):
        load_tokens(big)
    fifo = tmp_path / "fifo"
    if hasattr(os, "mkfifo"):
        os.mkfifo(fifo)
        with pytest.raises(WebSceneError, match="regular file"):
            load_tokens(fifo)  # must not block on open
    with pytest.raises(WebSceneError) as e:
        load_tokens(tmp_path / "missing.json")
    assert "No such file" not in str(e.value)
