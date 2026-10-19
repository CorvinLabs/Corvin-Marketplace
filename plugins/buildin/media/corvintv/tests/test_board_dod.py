"""Closes the gaps a clause-by-clause audit of the T-0197 definition of done found (2026-10-19).

* the stored model's size cap and its quota (decision 2),
* a board the model names off the list is a still - through a REAL job, not the contract function (decision 2/6),
* the overlap check does not apply to a board's own shapes - through a real job (decision 9),
* every board bound refuses on its own at limit + 1 and passes at the limit (decision 10),
* the template-naming places that deliberately do NOT list ``board`` are pinned, so adding it there is a decision.
"""
import dataclasses
import json
from pathlib import Path

import pytest

from src import asset_store as A
from src import penpot_import as pi
from src import web_layout, web_timeline
from tests import board_cases as cases
from tests.test_board import (THREE, _add_design, _board_storyboard, _png, _run, ffmpeg_ok, job_store, tenant)  # noqa: F401
from tests.test_web_slides_e2e import _fake_claude


# ── the stored model: size cap and quota ─────────────────────────────────────────────────────────────────────────────

def test_the_stored_design_has_a_byte_cap_exactly_at_its_encoded_size(tenant, monkeypatch):  # noqa: F811
    design = pi.parse_design(cases.simple_svg())
    size = len(A._encode_design(design))
    monkeypatch.setattr(A, "MAX_DESIGN_BYTES", size)                  # exactly at the cap: stored
    doc = tenant.add(_png(), caption="fits", uploaded_by="u1", design=design)
    assert tenant.ids() == [doc["id"]]
    monkeypatch.setattr(A, "MAX_DESIGN_BYTES", size - 1)              # one byte over: refused, nothing written
    with pytest.raises(A.AssetError, match="too large"):
        tenant.add(_png(), caption="too big", uploaded_by="u1", design=design)
    assert tenant.ids() == [doc["id"]]


def test_a_design_counts_toward_the_asset_quota(tenant, monkeypatch):  # noqa: F811
    monkeypatch.setattr(A, "MAX_ASSETS", 2)
    design = pi.parse_design(cases.simple_svg())
    tenant.add(_png(), caption="one", uploaded_by="u1", design=design)
    tenant.add(_png(), caption="two", uploaded_by="u1", design=design)
    with pytest.raises(A.AssetQuotaExceeded):
        tenant.add(_png(), caption="three", uploaded_by="u1", design=design)
    assert len(tenant.ids()) == 2


# ── through a real job ───────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not ffmpeg_ok, reason="ffmpeg/ffprobe not installed")
async def test_a_board_the_model_names_off_the_list_is_a_still_in_a_real_job(job_store, tmp_path, monkeypatch):  # noqa: F811
    store = A.AssetStore(job_store)
    aid, _ = _add_design(store)                                       # a design WITHOUT steps: not board-ready
    log = _fake_claude(tmp_path, monkeypatch, _board_storyboard(aid))
    result = await _run(job_store, "job_board_offlist", storyboard_backend="claude_cli", storyboard_model="claude-sonnet-5-5")
    md = result["metadata"]
    assert md["renderers"] == ["web"], "never the classic Pillow slide"
    assert md["cues"][0]["template"] == "still", md["cues"]
    assert md["board_fallbacks"] == []                                # a substitution at the contract, not a render fallback
    assert len(log.read_text().splitlines()) >= 1
    assert "assign steps first" not in json.dumps(md.get("errors", ""))


OVERLAPPING = (cases.SVG_HEAD
               + '<g><rect x="100" y="100" width="900" height="500" fill="#3366cc"/></g>'
               + '<g><text x="160" y="330" font-family="Inter" font-size="64" fill="#ffffff">Text on a card</text></g>'
               + '<g><ellipse cx="900" cy="500" rx="260" ry="180" fill="#ff8800"/></g></svg>').encode()


@pytest.mark.skipif(not ffmpeg_ok, reason="ffmpeg/ffprobe not installed")
async def test_the_overlap_check_does_not_apply_to_a_boards_own_shapes_in_a_real_job(job_store):  # noqa: F811
    store = A.AssetStore(job_store)
    aid, _ = _add_design(store, svg=OVERLAPPING, steps=[{"shapes": [0]}, {"shapes": [1]}, {"shapes": [2]}])
    result = await _run(job_store, "job_board_overlap", storyboard=_board_storyboard(aid, beats=[0, 1, 2]))
    md = result["metadata"]
    assert md["cues"][0]["template"] == "board", md["cues"]
    assert md["layout_collisions"] == [] and md["board_fallbacks"] == []
    kinds = [d["kind"] for d in json.loads((Path(result["video_path"]).parent / "report.json").read_text())["degradations"]]
    assert "board_to_still" not in kinds and "collision_replaced" not in kinds


def test_the_overlap_check_skips_board_art_and_nothing_wider():
    """The skip list names ``.board-art`` and it is the only content selector in it; a broader skip would hide real
    collisions on every other template."""
    skip = [ln for ln in web_layout.LAYOUT_JS.splitlines() if "const SKIP" in ln]
    assert len(skip) == 1
    selectors = [s.strip() for s in skip[0].split("'")[1].split(",")]
    assert ".board-art" in selectors
    assert set(selectors) <= {".stars", ".glow", ".ring", ".amb", ".board-art", "defs", "script", "style"}


# ── every bound refuses on its own ───────────────────────────────────────────────────────────────────────────────────

def _base():
    return pi.parse_design(cases.simple_svg())


def _with_shape(design, i, **changes):
    design = dataclasses.replace(design, shapes=list(design.shapes))
    design.shapes[i] = dataclasses.replace(design.shapes[i], **changes)
    return design


def _text_index(design):
    return next(i for i, sh in enumerate(design.shapes) if sh.kind == "text")


def _path_index(design):
    return next(i for i, sh in enumerate(design.shapes) if sh.kind == "path" and sh.stroke)


def _many(n, **changes):
    base = _base()
    proto = next(sh for sh in base.shapes if sh.kind == "ellipse")
    return dataclasses.replace(base, shapes=[dataclasses.replace(proto, **changes) for _ in range(n)], path_chars=0)


def _gradients(n):
    stops = lambda g: "".join(f'<stop offset="{k / 3:.3f}" stop-color="#{(g * 11 + k * 40) % 256:02x}80ff"/>' for k in range(4))  # noqa: E731
    defs = "".join(f'<linearGradient id="g{g}" x1="0" y1="0" x2="1" y2="1">{stops(g)}</linearGradient>' for g in range(n))
    rects = "".join(f'<rect x="{(g * 60) % 1500}" y="{(g * 90) % 800}" width="50" height="50" fill="url(#g{g})"/>' for g in range(n))
    return pi.parse_design((cases.SVG_HEAD + "<defs>" + defs + "</defs>" + rects + "</svg>").encode())


# bound name -> (design at the limit, design at limit + 1, word the refusal must carry)
BOUNDS = {
    "shapes": (lambda: _many(pi.BOARD_MAX_SHAPES), lambda: _many(pi.BOARD_MAX_SHAPES + 1), str(pi.BOARD_MAX_SHAPES)),
    "path_chars": (lambda: dataclasses.replace(_base(), path_chars=pi.BOARD_MAX_PATH_CHARS),
                   lambda: dataclasses.replace(_base(), path_chars=pi.BOARD_MAX_PATH_CHARS + 1), "path data"),
    "text_chars": (lambda: _with_shape(_base(), _text_index(_base()), text="x" * pi.BOARD_MAX_TEXT_CHARS),
                   lambda: _with_shape(_base(), _text_index(_base()), text="x" * (pi.BOARD_MAX_TEXT_CHARS + 1)), "of text"),
    "stroke": (lambda: _with_shape(_base(), _path_index(_base()), stroke_width=pi.BOARD_MAX_STROKE),
               lambda: _with_shape(_base(), _path_index(_base()), stroke_width=pi.BOARD_MAX_STROKE + 0.5), "stroke"),
    "matrix": (lambda: _with_shape(_base(), 0, matrix=(pi.BOARD_MAX_MATRIX_SCALE, 0.0, 0.0, 1.0, 0.0, 0.0)),
               lambda: _with_shape(_base(), 0, matrix=(pi.BOARD_MAX_MATRIX_SCALE + 0.1, 0.0, 0.0, 1.0, 0.0, 0.0)), "scaled"),
    "font": (lambda: _with_shape(_base(), _text_index(_base()), font_size=pi.BOARD_MAX_FONT),
             lambda: _with_shape(_base(), _text_index(_base()), font_size=pi.BOARD_MAX_FONT + 1), "text is larger"),
    "gradients": (lambda: _gradients(pi.BOARD_MAX_GRADIENTS), lambda: _gradients(pi.BOARD_MAX_GRADIENTS + 1), "gradients"),
    "translucent": (lambda: _many(pi.BOARD_MAX_TRANSLUCENT, opacity=0.5),
                    lambda: _many(pi.BOARD_MAX_TRANSLUCENT + 1, opacity=0.5), "see-through"),
    "text_length": (lambda: _many(pi.BOARD_MAX_TEXT_LENGTH, kind="text", text="t", text_length=100.0, font_size=20.0),
                    lambda: _many(pi.BOARD_MAX_TEXT_LENGTH + 1, kind="text", text="t", text_length=100.0, font_size=20.0),
                    "stretched"),
}


@pytest.mark.parametrize("bound", BOUNDS)
def test_each_board_bound_passes_at_its_limit_and_refuses_one_past_it(bound):
    at_limit, past_limit, word = BOUNDS[bound]
    assert pi.board_refusal(at_limit()) is None, f"{bound}: refused AT its limit"
    reason = pi.board_refusal(past_limit())
    assert reason and word in reason, f"{bound}: {reason!r}"


def test_the_bounds_table_names_every_board_constant():
    """A new BOARD_MAX_* constant without a row in BOUNDS fails here, so a bound can not be added untested."""
    constants = {n for n in dir(pi) if n.startswith("BOARD_MAX_")}
    covered = {"BOARD_MAX_SHAPES", "BOARD_MAX_PATH_CHARS", "BOARD_MAX_TEXT_CHARS", "BOARD_MAX_STROKE", "BOARD_MAX_MATRIX_SCALE",
               "BOARD_MAX_FONT", "BOARD_MAX_GRADIENTS", "BOARD_MAX_TRANSLUCENT", "BOARD_MAX_TEXT_LENGTH"}
    assert constants == covered, constants ^ covered
    assert set(BOUNDS) == {"shapes", "path_chars", "text_chars", "stroke", "matrix", "font", "gradients", "translucent",
                           "text_length"}


# ── places that name templates but deliberately do not list "board" (ADR-2260 context fact 1) ──────────────────────────

def test_board_is_not_a_chip_template_and_not_compactable():
    """The reveal items of a board ARE its timeline (one per step); keyword chips would add events the picture does not
    show. A board that collides never reaches the content trial: it becomes a still first (skill, board_to_still). Adding
    ``board`` to any of these lists is a decision, so it has to change this test."""
    assert "board" not in web_timeline.CHIP_TEMPLATES
    from src import skill
    assert "board" not in skill._COMPACTABLE
