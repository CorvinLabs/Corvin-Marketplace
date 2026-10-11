"""Canvas template (ADR-2249 D1, PLAN-0947 P2, T-0110): contract, limits, registration, determinism.
The real-render tests are test_canvas_e2e.py; nothing here counts as E2E."""

import copy
import re

import pytest

from src import canvas
from src import web_templates as wt
from src.web_templates import WebSceneError, build_document, scene_items, validate_scene_data
from tests.canvas_cases import CLEAN


def scene(**patch):
    d = copy.deepcopy(CLEAN)
    d.update(patch)
    return d


def errors(data):
    with pytest.raises(canvas.CanvasError) as e:
        canvas.validate_canvas(data)
    return e.value.errors


def test_the_clean_scene_validates_and_resolves_boxes():
    d = canvas.validate_canvas(CLEAN)
    assert [e["type"] for e in d["elements"]][:3] == ["person", "round", "arrow"]
    assert d["steps"] == [1, 2, 3, 4, 5]
    assert all("box" in e for e in d["elements"] if e["type"] in canvas.SHAPES)


def test_canvas_is_a_registered_template_with_a_real_builder():
    assert "canvas" in wt.TEMPLATES and "canvas" in wt._BUILDERS
    doc = build_document("canvas", CLEAN, duration_s=10)
    assert 'class="cv"' in doc and "A hit skips the database" in doc
    assert wt.reveal_steps("canvas", validate_scene_data("canvas", CLEAN)) == 5


def test_the_web_validator_reports_canvas_errors_as_web_scene_errors():
    with pytest.raises(WebSceneError, match="title is required"):
        validate_scene_data("canvas", {"elements": CLEAN["elements"]})


def test_all_errors_are_collected_in_one_pass():
    bad = scene(title="", sketch="yes", elements=[
        {"type": "blob", "id": "x"},
        {"type": "box", "id": "a", "text": "A", "at": {"col": 11, "row": 5, "w": 3, "h": 1}, "tone": "#ff0000", "step": 99},
        {"type": "arrow", "from": "a", "to": "ghost"},
        {"type": "label", "id": "l", "at": {"col": 0, "row": 0}},
    ])
    errs = errors(bad)
    text = " | ".join(errs)
    for needle in ("title is required", "sketch must be", "unknown type 'blob'", "step must be", "tone must be one of",
                   "a label needs text"):
        assert needle in text, needle
    assert len(errs) >= 6


def test_placement_errors_are_all_reported_too():
    bad = scene(elements=[
        {"type": "box", "id": "a", "text": "A", "at": {"col": 11, "row": 5, "w": 3, "h": 2}},
        {"type": "box", "id": "b", "text": "B", "right_of": "nope"},
        {"type": "box", "id": "c", "text": "C", "right_of": "d"},
        {"type": "box", "id": "d", "text": "D", "right_of": "c"},
    ])
    text = " | ".join(errors(bad))
    assert "outside the 12x6 grid" in text or "at must be" in text
    assert "must name an existing element id" in text
    assert "cycle" in text


def test_shapes_may_not_share_grid_cells_but_an_erased_one_may_be_reused():
    els = [{"type": "box", "id": "a", "text": "A", "at": {"col": 0, "row": 0, "w": 2, "h": 2}, "step": 1},
           {"type": "box", "id": "b", "text": "B", "at": {"col": 1, "row": 1, "w": 2, "h": 2}, "step": 2}]
    assert "occupy the same grid cells" in " ".join(errors(scene(elements=els)))
    els[0]["erase_at"] = 2
    assert canvas.validate_canvas(scene(elements=els))["steps"] == [1, 2]


def test_text_that_cannot_fit_is_refused_at_the_legibility_floor():
    els = [{"type": "box", "id": "a", "text": "Authentication and authorisation layer", "at": {"col": 0, "row": 0, "w": 1, "h": 1}}]
    assert "does not fit" in " ".join(errors(scene(elements=els)))


@pytest.mark.parametrize("els,msg", [
    ([], "non-empty"),
    ([{"type": "label", "text": "x", "at": {"col": 0, "row": 0, "w": 1, "h": 1}}] * 41, "limit 40"),
    ([{"type": "label", "id": "l", "text": "x" * 61, "at": {"col": 0, "row": 0, "w": 3, "h": 1}}], "limit 60"),
    ([{"type": "arrow", "from": "a", "to": "a"}], "elements"),
    ([{"type": "freehand", "points": [[0, 0]]}], "points must be"),
    ([{"type": "freehand", "points": [[0, 0], [13, 1]]}], "points must be"),
    ([{"type": "box", "id": "Bad Id", "text": "x", "at": {"col": 0, "row": 0}}], "id must match"),
    ([{"type": "box", "id": "a", "text": "x", "at": {"col": 0, "row": 0}, "color": "#fff"}], "unknown field"),
])
def test_limits(els, msg):
    assert msg in " ".join(errors(scene(elements=els)))


def test_total_text_is_capped():
    els = [{"type": "label", "id": f"l{i}", "text": "y" * 60, "at": {"col": i % 12, "row": i // 12, "w": 1, "h": 1}}
           for i in range(8)]
    assert "total text" in " ".join(errors(scene(elements=els)))


def test_the_model_cannot_name_a_colour():
    for tone in ("#ff0000", "red", "rgb(1,2,3)", "var(--x)"):
        els = copy.deepcopy(CLEAN["elements"])
        els[1]["tone"] = tone
        assert "tone must be one of" in " ".join(errors(scene(elements=els)))
    doc = build_document("canvas", CLEAN, duration_s=10)
    body = doc[doc.index('<div class="cv">'):doc.index('<div class="chrome">')]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", body), "canvas markup must carry only palette variables"


def test_text_is_escaped_and_cleaned_never_interpreted():
    els = copy.deepcopy(CLEAN["elements"])
    els[1]["text"] = "<img src=x onerror=1>‮"
    doc = build_document("canvas", scene(elements=els), duration_s=10)
    assert "<img src=x" not in doc and "&lt;img src=x" in doc and "‮" not in doc


def test_the_build_is_deterministic_including_the_sketch_wobble():
    a = build_document("canvas", CLEAN, duration_s=10)
    assert a == build_document("canvas", copy.deepcopy(CLEAN), duration_s=10)
    plain = build_document("canvas", scene(sketch=False), duration_s=10)
    assert plain != a


def test_pen_flag_controls_the_sprites():
    assert 'class="pen"' in build_document("canvas", CLEAN, duration_s=10)
    assert 'class="pen"' not in build_document("canvas", scene(pen=False), duration_s=10)


def test_scene_items_name_what_the_narration_can_say():
    d = validate_scene_data("canvas", CLEAN)
    items = scene_items("canvas", d)
    assert [s for _, s in items] == [2, 3, 4, 5, 6]
    assert items[0][0] == "User" and items[4][0] == "A hit skips the database"
    assert wt.scene_item_subs("canvas", d) == [""] * 5


def test_erased_elements_get_their_own_cue():
    els = copy.deepcopy(CLEAN["elements"])
    els[0]["erase_at"] = 3
    d = canvas.validate_canvas(scene(elements=els))
    assert 'class="er"' in canvas.build_canvas(d)


def test_probe_issues_are_prefixed_and_deduplicated():
    res = {"issues": [{"type": "text-shape", "a": "x", "b": "s"}, {"type": "text-shape", "a": "x", "b": "s"},
                      {"type": "oob", "a": "q", "b": ""}]}
    assert canvas.probe_issues(res) == [{"type": "cv-text-shape", "a": "x", "b": "s"}, {"type": "cv-oob", "a": "q", "b": ""}]
    assert canvas.probe_issues(None) == []
