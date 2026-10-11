"""Code v2 (ADR-2249 D2, PLAN-0947 P1, T-0109): contract, byte-identity of v1, derived colours,
beats, degrade ladder and the ``code_fidelity`` measure. The real-render E2E is test_code_v2_e2e.py."""

import copy
import hashlib
import html
import json
import random
import re
import sysconfig
from pathlib import Path

import pytest

from src import code_v2, skill
from src import web_templates as wt
from src.style_pack import Style, contrast, validate_style
from src.web_templates import WebSceneError, build_document, load_tokens, scene_items, validate_scene_data
from src.web_timeline import AudioPauses, build_timeline
from tests import code_v1_cases

V2 = {
    "eyebrow": "Python", "title": "Read a config file", "language": "python", "highlight": True,
    "lines": [
        "import json",
        "",
        "def load(path):",
        "    with open(path) as f:",
        "        return json.load(f)",
        "",
        "cfg = load(\"corvin.json\")  # 42 keys",
        "print(cfg[\"port\"])",
    ],
    "groups": [{"lines": [1, 1], "label": "import"}, {"lines": [3, 5], "label": "the loader"},
               {"lines": [7, 8], "label": "the call"}],
    "annotations": [{"line": 4, "cols": [10, 19], "label": "closes the file for us"}],
    "output": {"lines": ["8765"]},
}


# ── invariant 1: a scene without the opt-in is byte-identical to 1.4.x ─────────

GOLDEN_V1 = json.loads(code_v1_cases.GOLDEN_PATH.read_text())


@pytest.mark.parametrize("key,kw", list(code_v1_cases.cases()), ids=lambda x: x if isinstance(x, str) else "")
def test_v1_code_scenes_are_byte_identical_to_1_4(key, kw):
    assert code_v1_cases.digest(kw) == GOLDEN_V1[key]


def test_golden_v1_cover_every_case():
    assert set(GOLDEN_V1) == {k for k, _ in code_v1_cases.cases()} and len(GOLDEN_V1) == 24


def test_highlight_false_is_the_v1_scene():
    base = code_v1_cases.DATA["python"]
    a = build_document("code", base, duration_s=6)
    b = build_document("code", {**base, "highlight": False}, duration_s=6)
    assert a == b
    assert "highlight" not in validate_scene_data("code", {**base, "highlight": False})


def test_v1_validation_output_has_no_new_keys():
    d = validate_scene_data("code", code_v1_cases.DATA["shell"])
    assert set(d) == {"eyebrow", "title", "language", "lines"}


# ── contract ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("patch,msg", [
    ({"highlight": None, "groups": [{"lines": [1, 1]}]}, "need \"highlight\": true"),
    ({"highlight": "yes"}, "highlight"),
    ({"groups": [{"lines": [2, 1]}]}, "outside"),
    ({"groups": [{"lines": [1, 3]}, {"lines": [3, 4]}]}, "overlap"),
    ({"groups": [{"lines": [1, 99]}]}, "outside 1..8"),
    ({"groups": [{"lines": [1]}]}, "[first, last]"),
    ({"groups": [{"lines": [True, 2]}]}, "[first, last]"),
    ({"diff": True}, "diff line 1 must start"),
    ({"annotations": [{"line": 9, "label": "x"}]}, "1..8"),
    ({"annotations": [{"line": 1, "cols": [5, 40], "label": "x"}]}, "outside line 1"),
    ({"annotations": [{"line": 1, "label": "x" * 37}]}, "limit 36"),
    ({"annotations": [{"line": 1, "label": "a"}] * 5}, "1-4 items"),
    ({"output": ["8765"]}, "must be an object"),
    ({"output": {"lines": ["x"] * 7}}, "1-6 items"),
    ({"lines": ["x"] * 25, "groups": None, "annotations": None}, "1-24 items"),
    ({"color": "#ff0000"}, "unknown field"),
    ({"groups": [{"lines": [1, 1], "colour": "red"}]}, "unknown field"),
])
def test_v2_contract(patch, msg):
    data = {**copy.deepcopy(V2), **patch}
    data = {k: v for k, v in data.items() if v is not None}
    with pytest.raises(WebSceneError, match=re.escape(msg)):
        validate_scene_data("code", data)


def test_v2_validation_is_idempotent_and_normalised():
    d = validate_scene_data("code", V2)
    assert validate_scene_data("code", d) == d
    assert d["highlight"] is True and d["diff"] is False
    assert d["annotations"][0]["cols"] == [10, 19]


def test_twenty_four_short_lines_fit_and_too_much_code_is_refused_with_a_reason():
    ok = {"title": "Twenty-four lines", "highlight": True, "language": "python",
          "lines": [f"x{k} = {k} * 2  # step {k}" for k in range(24)]}
    d = validate_scene_data("code", ok)
    assert code_v2.font_px(d) >= code_v2.MIN_FONT_PX
    wide = {**ok, "lines": ["y" * 90] * 24, "annotations": [{"line": 1, "label": "a note"}],
            "output": {"lines": ["z" * 90] * 6}}
    with pytest.raises(WebSceneError, match="too much code for one slide"):
        validate_scene_data("code", wide)


def test_diff_markers_are_validated_and_rendered_outside_the_code():
    d = validate_scene_data("code", {"title": "Patch", "highlight": True, "diff": True, "language": "python",
                                     "lines": [" def f(x):", "-    return x", "+    return x + 1"]})
    doc = build_document("code", d, duration_s=6)
    assert doc.count('class="ln2 add"') == 1 and doc.count('class="ln2 del"') == 1
    assert '<span class="mk">+</span>' in doc
    assert code_v2.fidelity(d)["identical"]


# ── no model-chosen markup, no execution ───────────────────────────────────

def test_hostile_code_is_text_and_never_executed(tmp_path):
    canary = tmp_path / "ran"
    # Shorter payload that fits: the test proves HTML escaping, not fitting large code
    payload = f'__import__("os").system("x")  # </span></pre><script>alert(1)</script>'
    data = {"title": "<img src=x onerror=alert(1)>", "highlight": True, "language": "python",
            "lines": [payload]}
    doc = build_document("code", data, duration_s=6)
    assert "<script" not in doc and "<img" not in doc and "</script>" not in doc
    assert not canary.exists()
    f = code_v2.fidelity(validate_scene_data("code", data))
    assert f["identical"], f


def test_output_is_labelled_as_written_not_executed():
    doc = build_document("code", V2, duration_s=6, lang="de")
    assert "Ausgabe" in doc and "nicht ausgeführt" in doc
    doc_en = build_document("code", V2, duration_s=6, lang="en")
    assert "Output" in doc_en and "not executed" in doc_en


def test_unknown_language_says_it_is_not_highlighted():
    doc = build_document("code", {"title": "Rust", "highlight": True, "language": "rust", "lines": ["fn main() {}"]},
                         duration_s=6)
    assert "rust · not highlighted" in doc


# ── colours: derived roles, contrast floor, validate_style untouched ──────────

def _styles():
    tokens = load_tokens()
    yield "corvin-dark", tokens["dark"]
    yield "corvin-light", tokens["light"]
    t = copy.deepcopy(tokens)
    # a legal user style whose base colors have lower saturation; code_v2 derives final colours to 4.5:1
    t["light"].update(bg="#ffffff", bg_card="#ffffff", text="#1a1a1a", text_muted="#5a5a5a",
                      accent="#a85c00", accent_hi="#c97800", success="#5a9544")
    st = validate_style(Style(id="sty_00000001", name="pale", tokens=t))
    yield "pale-user-style", st.tokens["light"]


@pytest.mark.parametrize("name,palette", list(_styles()))
def test_every_token_colour_reaches_4_5_on_every_surface(name, palette):
    surf = code_v2.surfaces(palette)
    cols = code_v2.token_colours(palette)
    for kind, c in cols.items():
        worst = min(contrast(c, s) for s in surf)
        # the floor holds unless the style's own text colour is below it on a tint (then text is used)
        assert worst >= 4.5 or c == palette["text"].lower(), (name, kind, c, worst)


def test_colours_follow_the_role_not_the_model():
    pal = load_tokens()["dark"]
    cols = code_v2.token_colours(pal)
    assert cols["keyword"] == pal["accent"].lower()  # already >= 4.5: unchanged
    doc = build_document("code", V2, duration_s=6)
    assert f"--tk-kw:{cols['keyword']}" in doc and f"--tk-st:{cols['string']}" in doc


def test_validate_style_rules_are_unchanged():
    import src.style_pack as sp
    assert (sp.MIN_TEXT, sp.MIN_MUTED, sp.MIN_ACCENT, sp.MIN_HIGHLIGHT) == (4.5, 3.0, 3.0, 1.8)


# ── beats (ADR-2245) ────────────────────────────────────────────────────────

def test_items_are_groups_then_annotations_then_output():
    d = validate_scene_data("code", V2)
    assert scene_items("code", d) == [("import", 2), ("the loader", 3), ("the call", 4),
                                      ("closes the file for us", 5), ("Output", 6)]
    assert wt.reveal_steps("code", d) == 5


def test_without_groups_every_line_is_a_beat_like_v1():
    d = validate_scene_data("code", {"title": "t", "highlight": True, "lines": ["a = 1", "", "b = 2"]})
    assert [s for _, s in scene_items("code", d)] == [2, 3, 4]


def test_narration_reveals_groups_in_order_and_focus_leads_the_eye():
    d = validate_scene_data("code", V2)
    narration = ("Zuerst der Import. Dann der Loader, der die Datei liest. Das with schließt die Datei. "
                 "Zum Schluss der Aufruf. Die Ausgabe ist der Port.")
    pauses = AudioPauses(duration=15.0, pause_ends=[2.0, 5.5, 8.5, 11.0], speech_start=0.0, speech_end=15.0,
                         silent_ratio=0.1)
    tl = build_timeline("code", scene_items("code", d), narration, pauses, beats=[0, 1, 3, 2, 4],
                        subs=wt.scene_item_subs("code", d))
    times = [tl.step_times[s] for s in (2, 3, 4, 6)]
    assert times == sorted(times) and len(set(times)) == 4
    assert {t for _, t in tl.focus} >= {3, 5}
    doc = build_document("code", d, duration_s=15, timeline=tl)
    for step in (2, 3, 4):
        at = re.search(rf'class="grp" style="--i:{step};--at:([\d.]+)s', doc)
        assert at and abs(float(at.group(1)) - tl.time_of(step)) < 1e-3
    # the annotated group stays lit while its note is in focus
    assert "filter:opacity(max(var(--f3,1),var(--f5,0)))" in doc
    assert re.search(r'class="anno r" style="--i:5;--at:[\d.]+s;filter:opacity\(var\(--f5\)\)', doc)


# ── degrade ladder ──────────────────────────────────────────────────────────

def test_invalid_v2_degrades_to_the_v1_code_scene_and_says_so():
    bad = {**copy.deepcopy(V2), "groups": [{"lines": [5, 9]}]}
    bad["lines"] = bad["lines"][:8]
    scenes = [{"id": "s1", "template": "code", "data": bad}]
    warnings = skill._apply_web_scene_contract(scenes, strict=False)
    assert scenes[0]["template"] == "code" and "highlight" not in scenes[0]["data"]
    assert any("code v2 dropped" in w for w in warnings), warnings


def test_invalid_v2_that_v1_cannot_show_either_takes_the_normal_path():
    bad = {"title": "t", "highlight": True, "lines": ["x"] * 20, "groups": [{"lines": [3, 1]}]}
    scenes = [{"id": "s1", "template": "code", "data": bad}]
    warnings = skill._apply_web_scene_contract(scenes, strict=False)
    assert "template" not in scenes[0] and warnings


def test_operator_storyboard_with_invalid_v2_is_refused():
    with pytest.raises(ValueError, match="scene s1"):
        skill._apply_web_scene_contract([{"id": "s1", "template": "code", "data": {**V2, "diff": True}}], strict=True)


# ── code_fidelity (ADR-2249 D5) ─────────────────────────────────────────────

def _stdlib_fragments(n: int, seed: int = 7):
    root = Path(sysconfig.get_paths()["stdlib"])
    files = sorted(p for p in root.glob("*.py"))[:200]
    rng = random.Random(seed)
    for _ in range(n):
        src = rng.choice(files).read_text(encoding="utf-8", errors="replace").splitlines()
        if not src:
            continue
        a = rng.randrange(len(src))
        chunk = src[a:a + rng.randint(1, 24)]
        cut = rng.randrange(0, max(1, min(30, len(chunk[0]))))
        chunk[0] = chunk[0][cut:]  # cut mid-token, mid-string
        yield [ln.replace("\t", "    ")[:90] for ln in chunk] or ["x"]


def test_code_fidelity_over_stdlib_fragments_is_100_percent():
    results = []
    for lines in _stdlib_fragments(300):
        data = {"title": "fragment", "highlight": True, "language": "python",
                "lines": [wt._code_line(ln, 90) for ln in lines]}
        try:
            d = validate_scene_data("code", data)
        except WebSceneError:
            continue  # e.g. too wide to fit: refused before rendering, not a fidelity question
        results.append(code_v2.fidelity(d))
    summary = code_v2.summarize(results)
    assert summary["scenes"] >= 200 and summary["pass"], summary


def test_summary_without_v2_scenes_is_none_not_a_pass():
    assert code_v2.summarize([]) is None
