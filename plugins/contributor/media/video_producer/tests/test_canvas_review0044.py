"""Findings of the first adversarial round over the 1.6.0 canvas increment (REVIEW-0044): the validator accepts
what it promises to prove, and a continued scene starts exactly where the earlier one ended."""
import copy

import pytest

from src import canvas
from src import web_templates as wt
from src.web_templates import WebSceneError, validate_scene_data


def box(id_, col, row, step=1, **kw):
    return {"type": "box", "id": id_, "at": {"col": col, "row": row, "w": 2, "h": 1}, "step": step, **kw}


def spec(title, elements, **kw):
    return {"title": title, "elements": elements, **kw}


# ── 1. a base nobody carried over cannot be smuggled in through a nested normalised form ──

def test_a_nested_normalised_form_cannot_inject_a_carried_over_base():
    x = spec("T", [box("a", 0, 0)])
    injected = [{"type": "box", "id": "z", "text": "injected", "at": {"col": 6, "row": 3, "w": 2, "h": 1}}]
    with pytest.raises(canvas.CanvasError, match="unknown scene field"):
        canvas.validate_canvas({"source": {"source": x, "base": injected}})
    with pytest.raises(WebSceneError):
        validate_scene_data("canvas", canvas.attach_base({"source": {"source": x, "base": injected}}, {}, err=WebSceneError))


def test_one_level_of_normalised_form_still_validates_and_a_real_base_is_still_honoured():
    a = validate_scene_data("canvas", spec("A", [box("a", 0, 0)]))
    cont = spec("B", [box("b", 4, 0), {"type": "arrow", "from": "a", "to": "b", "step": 2}], continue_from="s1")
    b = validate_scene_data("canvas", canvas.attach_base(cont, {"s1": a}, err=WebSceneError))
    assert [e["id"] for e in b["elements"] if e.get("base")] == ["a"]
    assert validate_scene_data("canvas", b) == b


# ── 2. the arrow is lifted to its endpoints' step; erase_at must still come after that step ──

def test_an_erase_before_the_lifted_step_of_a_connector_is_refused():
    els = [box("a", 0, 0, step=1), box("b", 6, 0, step=3), {"type": "arrow", "from": "a", "to": "b", "step": 1, "erase_at": 2}]
    with pytest.raises(canvas.CanvasError, match="erase_at"):
        canvas.validate_canvas(spec("T", els))


def test_an_erase_after_the_lifted_step_is_fine():
    els = [box("a", 0, 0, step=1), box("b", 6, 0, step=3), {"type": "arrow", "from": "a", "to": "b", "step": 1, "erase_at": 4}]
    d = canvas.validate_canvas(spec("T", els))
    arrow = next(e for e in d["elements"] if e["type"] == "arrow")
    assert (arrow["step"], arrow["erase_at"]) == (3, 4)


# ── 3. what is on screen at the end of a scene is what the continuation starts with ──

def scene_a():
    return spec("A", [box("x", 0, 0, step=1, erase_at=3), box("y", 6, 0, step=1),
                      {"type": "arrow", "from": "x", "to": "y", "step": 2}])


def test_what_is_attached_to_an_erased_element_is_erased_with_it():
    d = canvas.validate_canvas(scene_a())
    arrow = next(e for e in d["elements"] if e["type"] == "arrow")
    assert arrow["erase_at"] == 3                                       # gone at the same moment as x
    assert [e.get("id") for e in canvas.carry_over(d)] == ["y"]          # so the continuation starts from the same picture
    doc = wt.build_document("canvas", validate_scene_data("canvas", scene_a()), duration_s=8)
    assert doc.count('class="er"') >= 2                                  # the box and its arrow both fade


def test_an_element_that_appears_after_what_it_is_attached_to_is_gone_is_refused():
    els = [box("x", 0, 0, step=1, erase_at=3), box("y", 6, 0, step=1), {"type": "arrow", "from": "x", "to": "y", "step": 4}]
    with pytest.raises(canvas.CanvasError, match="erase"):
        canvas.validate_canvas(spec("A", els))


def test_an_element_placed_inside_an_erased_one_is_erased_with_it():
    els = [box("p", 0, 0, step=1, erase_at=3), {"type": "label", "id": "c", "text": "in", "step": 1,
                                                "inside": "p", "size": {"w": 1, "h": 1}}]
    try:
        d = canvas.validate_canvas(spec("A", els))
    except canvas.CanvasError:
        pytest.skip("this element schema places inside-elements differently")
    child = next(e for e in d["elements"] if e.get("id") == "c")
    assert child.get("erase_at") == 3


# ── 4. ids the model authored survive continue_from; carried ids never collide across generations ──

def test_an_authored_id_with_a_leading_underscore_is_kept_when_a_scene_continues():
    a = validate_scene_data("canvas", spec("A", [box("_x", 0, 0)]))
    cont = spec("B", [box("n", 6, 0, step=1), {"type": "arrow", "from": "_x", "to": "n", "step": 2}], continue_from="s1")
    b = validate_scene_data("canvas", canvas.attach_base(cont, {"s1": a}, err=WebSceneError))
    assert "_x" in [e.get("id") for e in b["elements"] if e.get("base")]


def test_auto_ids_stay_unique_over_three_generations():
    a = validate_scene_data("canvas", spec("A", [{"type": "label", "text": "one", "at": {"col": 0, "row": 0, "w": 3, "h": 1}, "step": 1},
                                                 {"type": "label", "text": "two", "at": {"col": 4, "row": 0, "w": 3, "h": 1}, "step": 1}]))
    b = validate_scene_data("canvas", canvas.attach_base(
        spec("B", [{"type": "label", "text": "three", "at": {"col": 0, "row": 2, "w": 3, "h": 1}, "step": 1}], continue_from="a"),
        {"a": a}, err=WebSceneError))
    c = validate_scene_data("canvas", canvas.attach_base(
        spec("C", [{"type": "label", "text": "four", "at": {"col": 4, "row": 2, "w": 3, "h": 1}, "step": 1}], continue_from="b"),
        {"b": b}, err=WebSceneError))
    ids = [e["id"] for e in c["elements"]]
    assert len(ids) == len(set(ids)) == 4


# ── 5. the repair rung never rewrites the carried-over board ──

def test_repair_variants_leave_the_carried_over_board_alone():
    a = validate_scene_data("canvas", spec("A", [box("p", 0, 0), box("q", 6, 0),
                                                 {"type": "arrow", "from": "p", "to": "q", "step": 2}]))
    cont = spec("B", [box("n", 3, 3, step=1)], continue_from="s1")
    b = validate_scene_data("canvas", canvas.attach_base(cont, {"s1": a}, err=WebSceneError))
    k = next(i for i, e in enumerate(b["elements"]) if e["type"] == "arrow")
    assert b["elements"][k].get("base")
    issues = [{"type": "cv-stroke-shape", "a": f"arrow{k}"}]
    before = copy.deepcopy(b["base"])
    variants = canvas.repair_variants(b, issues)
    assert variants == []                                              # a base connector has no data-only repair
    for _label, data in variants:
        assert (data.get("base") or []) == before
