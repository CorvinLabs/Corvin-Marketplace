"""Canvas P2 contract pieces (ADR-2249 D1, T-0110) that need no browser: the normalised form is
accepted again, continue_from carries the settled board. The real-render and real-job proofs are
test_canvas_e2e.py / test_canvas_job_e2e.py."""
import copy
import json

import pytest

from src import canvas, skill
from src import web_templates as wt
from src.web_templates import WebSceneError, build_document, validate_scene_data
from tests.canvas_cases import CLEAN

CONT = {"title": "Second request", "continue_from": "s2", "elements": [
    {"type": "label", "id": "fast", "text": "Second request: 2 ms", "at": {"col": 0, "row": 0, "w": 5, "h": 1},
     "font": "s", "step": 1},
    {"type": "arrow", "from": "cache", "to": "fast", "step": 2}]}


def test_the_normalised_form_validates_again_to_the_same_result():
    """Every caller in the render path re-validates (timeline, document, ladder): before T-0110 the
    normalised form was refused, so no canvas ever rendered through the job pipeline."""
    d = validate_scene_data("canvas", CLEAN)
    again = validate_scene_data("canvas", d)
    assert again == d
    assert json.loads(json.dumps(d)) == d  # it is stored with the job record
    assert build_document("canvas", d, duration_s=8) == build_document("canvas", CLEAN, duration_s=8)


def test_nothing_derived_is_trusted_from_a_normalised_looking_input():
    d = validate_scene_data("canvas", CLEAN)
    forged = copy.deepcopy(d)
    forged["elements"][0]["box"] = {"col": 0, "row": 0, "w": 12, "h": 6}  # ignored: the source is re-validated
    forged["steps"] = [1]
    assert validate_scene_data("canvas", forged) == d
    bad = copy.deepcopy(d)
    bad["source"]["elements"][0]["tone"] = "#ff0000"
    with pytest.raises(WebSceneError, match="tone must be one of"):
        validate_scene_data("canvas", bad)


def test_continue_from_carries_the_settled_board_without_beats():
    d2 = validate_scene_data("canvas", CLEAN)
    d3 = validate_scene_data("canvas", canvas.attach_base(CONT, {"s2": d2}, err=WebSceneError))
    base = [e for e in d3["elements"] if e.get("base")]
    assert len(base) == len(CLEAN["elements"]) and {e["step"] for e in base} == {0}
    assert d3["steps"] == [1, 2]  # only the new elements are beats
    assert [lb for lb, _ in wt.scene_items("canvas", d3)] == ["Second request: 2 ms", "step 2"]
    arrow = next(e for e in d3["elements"] if e["type"] == "arrow" and not e.get("base"))
    assert arrow["from"] == "cache"  # the new arrow points at the carried "cache": one board, one id space
    doc = build_document("canvas", d3, duration_s=8)
    assert doc.count('class="base"') >= len([e for e in base if e["type"] != "label"])
    assert ".cv .base .st" in doc  # the rules that show it at once, only in a continued board
    assert ".cv .base .st" not in build_document("canvas", CLEAN, duration_s=8)


def test_a_carried_board_keeps_its_wobble():
    d2 = validate_scene_data("canvas", CLEAN)
    d3 = validate_scene_data("canvas", canvas.attach_base(CONT, {"s2": d2}))
    doc2, doc3 = build_document("canvas", d2, duration_s=8), build_document("canvas", d3, duration_s=8)
    g = lambda doc: doc[doc.index('data-id="db"'):].split("</g>")[0]  # noqa: E731
    paths = lambda s: [p.split('"')[0] for p in s.split(' d="M')[1:]]  # noqa: E731
    assert paths(g(doc2)) and paths(g(doc2)) == paths(g(doc3))  # same seeded wobble, stroke for stroke


def test_erased_elements_and_what_points_at_them_are_not_carried():
    src = copy.deepcopy(CLEAN)
    src["elements"][1]["erase_at"] = 5  # the app server is wiped before the scene ends
    d2 = validate_scene_data("canvas", src)
    carried = canvas.carry_over(d2)
    assert "app" not in [e.get("id") for e in carried]
    assert [e for e in carried if e["type"] == "arrow"] == []  # all three arrows touched "app"


def test_continue_from_must_name_an_earlier_canvas_and_the_board_keeps_its_limits():
    with pytest.raises(WebSceneError, match="not an earlier canvas scene"):
        canvas.attach_base(CONT, {}, err=WebSceneError)
    d2 = validate_scene_data("canvas", CLEAN)
    many = {"title": "Too much", "continue_from": "s2", "elements": [
        {"type": "label", "text": f"n{k}", "at": {"col": k % 12, "row": 5 if k < 12 else 4, "w": 1, "h": 1}, "font": "s", "step": 1}
        for k in range(35)]}
    with pytest.raises(WebSceneError, match="carried over by continue_from, limit 40"):
        validate_scene_data("canvas", canvas.attach_base(many, {"s2": d2}, err=WebSceneError))
    clash = {"title": "Clash", "continue_from": "s2", "elements": [
        {"type": "box", "id": "db", "text": "x", "at": {"col": 0, "row": 0, "w": 1, "h": 1}}]}
    with pytest.raises(WebSceneError, match="duplicate id 'db'"):
        validate_scene_data("canvas", canvas.attach_base(clash, {"s2": d2}, err=WebSceneError))


def test_the_storyboard_contract_resolves_continue_from_in_order():
    scenes = [{"id": "s2", "template": "canvas", "data": copy.deepcopy(CLEAN)},
              {"id": "s3", "template": "canvas", "data": copy.deepcopy(CONT)}]
    assert skill._apply_web_scene_contract(scenes, strict=True) == []
    assert sum(1 for e in scenes[1]["data"]["elements"] if e.get("base")) == len(CLEAN["elements"])
    with pytest.raises(ValueError, match="not an earlier canvas scene"):  # a forward reference is refused
        skill._apply_web_scene_contract([{"id": "s3", "template": "canvas", "data": copy.deepcopy(CONT)},
                                         {"id": "s2", "template": "canvas", "data": copy.deepcopy(CLEAN)}], strict=True)


def test_repair_reroutes_the_connector_the_probe_named_and_compact_drops_floating_labels():
    from tests.canvas_cases import THROUGH_A_BOX
    d = validate_scene_data("canvas", THROUGH_A_BOX)
    issues = [{"type": "cv-stroke-shape", "a": "arrow3", "b": "b"}]
    variants = canvas.repair_variants(d, issues)
    routes = [validate_scene_data("canvas", v)["elements"][3]["route"] for _, v in variants]
    assert routes == ["elbow", "curved", "curved"]  # straight is what collided
    assert canvas.repair_variants(d, [{"type": "cv-text-shape", "a": "Alpha", "b": "b"}]) == []  # shape text: no repair
    c = validate_scene_data("canvas", canvas.compact_variant(d))
    assert all(not e.get("text") for e in c["elements"] if e["type"] == "arrow")
    assert [e["text"] for e in c["elements"] if e["type"] == "box"] == ["Alpha", "Bravo", "Charlie"]
    assert canvas.step_bullets(d) == ["Alpha — Bravo — Charlie", "passes through"]
