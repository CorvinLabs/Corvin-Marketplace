"""T-0110 Canvas D1 Completion: continue_from, group reveal sequences, signal registration.

Tests for ADR-2249 D1 (PLAN-0947 P2): canvas_clean and canvas_authoring signals,
continue_from field for revision chaining, abstufungsleiter (group reveal ladder).
"""

import copy
import pytest
from pathlib import Path

pytest.importorskip("playwright")

from src import canvas
from src import signals as sg
from src import web_templates as wt
from src.web_timeline import AudioPauses, build_timeline
from tests.canvas_cases import CLEAN


# ── Test 1: continue_from field validation ────────────────────────────────────────
def test_continue_from_field_is_optional_and_validated():
    """T-0110: continue_from must be a valid scene id or None."""
    # Valid: None (default)
    d = copy.deepcopy(CLEAN)
    assert wt.validate_scene_data("canvas", d)["continue_from"] is None

    # Valid: a scene id
    d = copy.deepcopy(CLEAN)
    d["continue_from"] = "s1"
    validated = wt.validate_scene_data("canvas", d)
    assert validated["continue_from"] == "s1"

    # Valid: other id formats
    for sid in ["previous_scene", "scene_123", "s"]:
        d = copy.deepcopy(CLEAN)
        d["continue_from"] = sid
        validated = wt.validate_scene_data("canvas", d)
        assert validated["continue_from"] == sid

    # Invalid: not a string
    d = copy.deepcopy(CLEAN)
    d["continue_from"] = 123
    with pytest.raises(wt.WebSceneError, match="continue_from must be a valid scene id"):
        wt.validate_scene_data("canvas", d)

    # Invalid: bad format (starts with number)
    d = copy.deepcopy(CLEAN)
    d["continue_from"] = "1scene"
    with pytest.raises(wt.WebSceneError, match="continue_from must be a valid scene id"):
        wt.validate_scene_data("canvas", d)


# ── Test 2: reveal_steps returns the step ladder ────────────────────────────────────
def test_reveal_steps_gives_group_count():
    """T-0110: reveal_steps() returns the number of groups (steps) in the canvas."""
    d = wt.validate_scene_data("canvas", CLEAN)
    steps = wt.reveal_steps("canvas", d)
    assert steps == len(d["steps"]), "reveal_steps should return the step count"
    assert steps == 5, f"CLEAN case should have 5 steps, got {steps}"


# ── Test 3: canvas with 3 groups renders 3 reveal beats ────────────────────────────
def test_canvas_three_group_reveal_sequence():
    """T-0110: A canvas with elements at steps 1, 2, 3 has 3 reveal beats."""
    data = {
        "title": "Three-step canvas",
        "elements": [
            {"type": "box", "id": "g1", "text": "Group 1", "at": {"col": 0, "row": 0, "w": 2, "h": 2}, "step": 1},
            {"type": "box", "id": "g2", "text": "Group 2", "at": {"col": 3, "row": 0, "w": 2, "h": 2}, "step": 2},
            {"type": "box", "id": "g3", "text": "Group 3", "at": {"col": 6, "row": 0, "w": 2, "h": 2}, "step": 3},
        ],
    }
    d = wt.validate_scene_data("canvas", data)
    assert d["steps"] == [1, 2, 3]
    assert len(d["steps"]) == 3
    assert wt.reveal_steps("canvas", d) == 3


# ── Test 4/5: the signals are registered ────────────────────────────────────────
def test_canvas_clean_signal_registered():
    specs = sg.registered("runtime")
    spec = next((s for s in specs if s.id == "canvas_clean"), None)
    assert spec is not None and spec.templates == frozenset({"canvas"}) and spec.gated is True


def test_canvas_authoring_signal_registered():
    specs = sg.registered("runtime")
    spec = next((s for s in specs if s.id == "canvas_authoring"), None)
    assert spec is not None and spec.templates == frozenset({"canvas"}) and spec.gated is False


def test_canvas_clean_skips_without_canvas():
    ctx = sg.SignalContext(job_dir=Path("."), report={"scenes": [{"index": 1, "template": "hero"}]}, templates={"hero"})
    result = sg.run(ctx, only=["canvas_clean"])
    assert len(result) == 1 and result[0]["verdict"] == "skip"
    assert result[0]["reason"] is not None and "template" in result[0]["reason"]


def _canvas_ctx(collisions, rendered=("canvas", "canvas", "canvas")):
    return sg.SignalContext(
        job_dir=Path("."),
        report={"scenes": [{"index": i, "renderer": "web", "template": t} for i, t in enumerate(rendered, start=1)]},
        templates={"canvas"},
        storyboard_scenes=[{"template": "canvas"} for _ in rendered],
        metadata={"layout_collisions": collisions},
    )


def test_canvas_clean_passes_with_clean_canvas():
    rec = sg.run(_canvas_ctx([]), only=["canvas_clean"])[0]
    assert rec["verdict"] == "pass" and rec["basis"] == {"n": 3, "of": 3}


def test_a_canvas_that_walked_its_ladder_is_not_clean():
    """The layout log names the scene by index; the old signal matched it against the scene id and
    so reported every canvas clean. A canvas replaced by a content slide still counts as a canvas."""
    log = [{"scene": "s2", "index": 2, "template": "canvas", "action": "repaired",
            "ladder": [{"rung": "repaired", "result": "clean"}]}]
    rec = sg.run(_canvas_ctx(log, rendered=("canvas", "canvas", "content")), only=["canvas_clean"])[0]
    assert rec["verdict"] == "fail" and rec["basis"] == {"n": 1, "of": 3}
    per = {p["scene"]: p for p in rec["detail"]["per_scene"]}
    assert per[2]["action"] == "repaired" and per[2]["ladder"] == ["repaired"]
    assert per[3]["action"] == "not_rendered_as_canvas"


def test_canvas_authoring_records_accuracy():
    ctx = _canvas_ctx([])
    ctx.metadata["canvas_authoring"] = {"total": 3, "first_try": 2, "after_repair": 3}
    rec = sg.run(ctx, only=["canvas_authoring"])[0]
    assert rec["verdict"] == "info" and rec["value"] == round(2 / 3, 3) and rec["basis"] == {"n": 2, "of": 3}
    assert rec["detail"] == {"after_repair": 3, "after_repair_share": 1.0}


def test_canvas_authoring_skips_an_operator_storyboard():
    ctx = _canvas_ctx([])
    ctx.metadata["storyboard_llm"] = "operator"
    rec = sg.run(ctx, only=["canvas_authoring"])[0]
    assert rec["verdict"] == "skip" and "operator" in rec["reason"]


# ── Test 9: continue_from chains scenes correctly ─────────────────────────────────────
def test_continue_from_chains_scenes():
    """T-0110: A canvas with continue_from references the previous canvas."""
    # Scene 1: base canvas with 3 steps
    scene1 = {
        "id": "s1",
        "template": "canvas",
        "data": {
            "title": "Part 1",
            "elements": [
                {"type": "box", "id": "a", "text": "A", "at": {"col": 0, "row": 0, "w": 1, "h": 1}, "step": 1},
                {"type": "box", "id": "b", "text": "B", "at": {"col": 1, "row": 0, "w": 1, "h": 1}, "step": 2},
                {"type": "box", "id": "c", "text": "C", "at": {"col": 2, "row": 0, "w": 1, "h": 1}, "step": 3},
            ],
        },
    }

    # Scene 2: continuation, starting from beat 2
    scene2 = {
        "id": "s2",
        "template": "canvas",
        "data": {
            "title": "Part 2 (continued)",
            "continue_from": "s1",  # continue from scene 1
            "elements": [
                {"type": "label", "text": "New step", "at": {"col": 3, "row": 0, "w": 1, "h": 1}, "step": 4},
                {"type": "label", "text": "Another step", "at": {"col": 4, "row": 0, "w": 1, "h": 1}, "step": 5},
            ],
        },
    }

    # Both should validate
    d1 = wt.validate_scene_data("canvas", scene1["data"])
    assert d1["continue_from"] is None
    assert d1["steps"] == [1, 2, 3]

    d2 = wt.validate_scene_data("canvas", scene2["data"])
    assert d2["continue_from"] == "s1"
    assert d2["steps"] == [4, 5]  # steps in this scene (elements start at step 4)


# ── Test 10: canvas validates boundary conditions ────────────────────────────────────
def test_canvas_step_boundaries_with_continue_from():
    """T-0110: Canvas steps work correctly with continue_from (no clash of numbering)."""
    # When a canvas continues from another, steps are independent per scene
    base = {
        "title": "Base",
        "elements": [
            {"type": "box", "id": "a", "text": "A", "at": {"col": 0, "row": 0, "w": 1, "h": 1}, "step": 1},
            {"type": "box", "id": "b", "text": "B", "at": {"col": 1, "row": 0, "w": 1, "h": 1}, "step": 12},  # max step
        ],
    }

    continuation = {
        "title": "Continuation",
        "continue_from": "base",
        "elements": [
            {"type": "box", "id": "c", "text": "C", "at": {"col": 2, "row": 0, "w": 1, "h": 1}, "step": 1},  # restart at 1
            {"type": "box", "id": "d", "text": "D", "at": {"col": 3, "row": 0, "w": 1, "h": 1}, "step": 12},  # can use max again
        ],
    }

    d_base = wt.validate_scene_data("canvas", base)
    assert d_base["steps"] == [1, 12]

    d_cont = wt.validate_scene_data("canvas", continuation)
    assert d_cont["continue_from"] == "base"
    assert d_cont["steps"] == [1, 12]  # independent numbering


# ── Test 11: scene_items respects group structure ────────────────────────────────────
def test_scene_items_group_structure():
    """T-0110: scene_items returns labels for each group (step) with cue times."""
    data = {
        "title": "Grouped canvas",
        "elements": [
            {"type": "label", "text": "First group", "at": {"col": 0, "row": 0, "w": 1, "h": 1}, "step": 1},
            {"type": "label", "text": "Second group", "at": {"col": 1, "row": 0, "w": 1, "h": 1}, "step": 2},
            {"type": "label", "text": "Third group", "at": {"col": 2, "row": 0, "w": 1, "h": 1}, "step": 3},
        ],
    }
    validated = wt.validate_scene_data("canvas", data)
    items = wt.scene_items("canvas", validated)

    # One item per step/group
    assert len(items) == 3
    # Each item is (label, cue_step)
    assert all(isinstance(label, str) and isinstance(cue, int) for label, cue in items)
    # Cues start at step 2 (step 1 is at cue 2)
    cues = [cue for _, cue in items]
    assert cues == [2, 3, 4]


# ── Test 12: canvas handles group structure deterministically ────────────────────────
def test_canvas_group_determinism():
    """T-0110: The same canvas data produces identical step ordering (deterministic groups)."""
    data = {
        "title": "Deterministic groups",
        "elements": [
            {"type": "box", "text": "G3", "at": {"col": 0, "row": 0, "w": 1, "h": 1}, "step": 3},
            {"type": "box", "text": "G1", "at": {"col": 1, "row": 0, "w": 1, "h": 1}, "step": 1},
            {"type": "box", "text": "G2", "at": {"col": 2, "row": 0, "w": 1, "h": 1}, "step": 2},
        ],
    }

    # Validate multiple times
    d1 = wt.validate_scene_data("canvas", copy.deepcopy(data))
    d2 = wt.validate_scene_data("canvas", copy.deepcopy(data))

    # Steps should be sorted and identical
    assert d1["steps"] == d2["steps"] == [1, 2, 3]
    assert wt.reveal_steps("canvas", d1) == wt.reveal_steps("canvas", d2) == 3
