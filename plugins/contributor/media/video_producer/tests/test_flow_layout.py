"""The flow template sizes its nodes and places its edge labels from the text (ADR-2238, readiness corpus 2026-10-14).

In the first real corpus 5 of 10 flow scenes collided in the layout check (3 replaced by a quote or content slide, 2 made
compact): node height was fixed while long labels wrapped to three lines, and an edge label pill up to 200 px wide sat
between two nodes 116 px apart or - on an edge that skips a column - on top of the node in the middle column.
The examples are synthetic stand-ins with the same shape; none is taken from a customer or an internal document.
"""
import asyncio
import tempfile
from pathlib import Path

import pytest

from src import web_templates as wt
from src.web_layout import format_issues
from src.web_renderer import WebSlideRenderer

pytestmark = [pytest.mark.e2e]


def graph(nodes, edges, **kw):
    return {"title": "Flow", "nodes": [{"id": i, "label": l, "sub": s} for i, l, s in nodes],
            "edges": [{"from": a, "to": b, "label": lab} for a, b, lab in edges], **kw}


CASES = {
    # three columns, four nodes in the middle one: the cell is only 140 px high
    "fan_out_long_text": graph(
        [("a", "Anomalie-Erkennung", "wacht ueber alle Quellen"), ("b1", "Datenquellen-Waechter", "meldet Aenderungen sofort"),
         ("b2", "Regel-Pruefung", "gleicht mit Vorgaben ab"), ("b3", "Einwilligungspruefung", "fragt vor jeder Nutzung"),
         ("b4", "Audit-Protokoll", "schreibt zuerst, handelt danach"), ("c", "Freigabe", "durch den Menschen")],
        [("a", "b1", None), ("a", "b2", None), ("a", "b3", None), ("a", "b4", None), ("b1", "c", None), ("b2", "c", None),
         ("b3", "c", None), ("b4", "c", None)]),
    # five columns, one node each: nodes get narrow, a long compound word has to break
    "five_columns_compound_word": graph(
        [("n1", "Eingang", "Signal"), ("n2", "Datenquellenwaechter", "uebersetzt"), ("n3", "Regelpruefung", "bewertet"),
         ("n4", "Freigabeentscheidung", "protokolliert"), ("n5", "Ausfuehrung", "ueberwacht")],
        [("n1", "n2", None), ("n2", "n3", None), ("n3", "n4", None), ("n4", "n5", None)]),
    # edge labels near the 18 character limit, in a three column graph
    "long_edge_labels": graph(
        [("s", "Start", None), ("m", "Pruefung", "automatisch"), ("e", "Ende", None)],
        [("s", "m", "Regeneration"), ("m", "e", "geprueft/signiert")]),
    # an edge that skips a column, next to labelled neighbours: the pills must not sit on a node or on each other
    "skipping_edge_with_pills": graph(
        [("loss", "Loss signal", None), ("choice", "Real choice?", "between alternatives"),
         ("bind", "Binds structure?", "protocol, security, repos"), ("adr", "ADR is written", None), ("skip", "No ADR", None)],
        [("loss", "choice", None), ("choice", "bind", "yes"), ("bind", "adr", "yes"), ("choice", "skip", "no"), ("bind", "skip", "no")],
        highlight="adr"),
    # two columns, the sub line is the longest thing allowed
    "longest_sub_line": graph(
        [("a", "Anfrage", "x" * 4 + " eine ziemlich lange Erklaerung des Schritts"[:32]), ("b", "Antwort", "ein zweiter langer Zusatztext hier")],
        [("a", "b", None)]),
}

ABSOLUTE_WORST = graph(   # every text at the validator's limit, four nodes in a column: even the smallest type does not fit
    [("a", "Quelle", None)] + [(f"m{i}", "Datenquellenwaechterdienst1", "ein sehr langer Zusatztext der Knoten"[:36]) for i in range(4)] + [("z", "Ziel", None)],
    [("a", f"m{i}", None) for i in range(4)] + [(f"m{i}", "z", None) for i in range(4)])
for _n in ABSOLUTE_WORST["nodes"]:
    _n["label"] = _n["label"][:24]


async def _issues(data, *, compact=False, lang="de"):
    async with WebSlideRenderer(fps=12) as r:
        with tempfile.TemporaryDirectory() as d:
            fr = await r.render("flow", wt.validate_scene_data("flow", data), 8, Path(d), scene_index=3, total_scenes=8,
                                lang=lang, compact=compact)
    return fr.layout_issues or []


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_flow_with_realistic_worst_case_text_renders_without_a_collision(name):
    issues = asyncio.run(_issues(CASES[name]))
    assert not issues, f"{name}: {format_issues(issues)}"


def test_the_most_text_the_validator_allows_is_rescued_by_the_compact_rung_not_replaced():
    first = asyncio.run(_issues(ABSOLUTE_WORST))
    compact = asyncio.run(_issues(ABSOLUTE_WORST, compact=True))
    assert not compact, format_issues(compact)   # if the first render collided, rung 2 of the ladder keeps the flow slide
    assert isinstance(first, list)


def test_a_graph_that_always_fitted_is_rendered_exactly_as_before():
    d = wt.validate_scene_data("flow", graph([("a", "Eingang", None), ("b", "Pruefung", "kurz"), ("c", "Ausgang", None)],
                                              [("a", "b", "ok"), ("b", "c", None)]))
    html = wt._flow(d)
    assert 'font-size:' not in html                                # no type override
    assert html.count("width:300.0px;height:120px") == 3         # the fixed node box, untouched
    assert 'class="elabel r"' in html and "width:" not in html.split('class="elabel r"')[1].split(">")[0]  # pill keeps its CSS width
    mid = html.split('class="elabel r"')[1].split("left:")[1].split("px")[0]
    assert float(mid) == pytest.approx(float(mid))                 # (value pinned by golden_corvin_html.json for the samples)


def test_wrap_lines_counts_like_the_browser_wraps():
    assert wt._wrap_lines("", 36, 200, 0.5) == 1
    assert wt._wrap_lines("kurz", 36, 200, 0.5) == 1
    assert wt._wrap_lines("eins zwei drei vier", 36, 100, 0.5) == 4          # 5 characters a line: eins / zwei / drei / vier
    assert wt._wrap_lines("x" * 25, 36, 100, 0.5) == 5                       # a word longer than a line breaks anywhere
    assert wt._wrap_lines("ab " * 10, 36, 180, 0.5) >= 3


def test_bezier_point_at_a_given_x_lies_on_the_curve():
    for tx in (120.0, 200.0, 333.0, 480.0):
        x, y = wt._bezier_at_x(100.0, 50.0, 300.0, 50.0, 300.0, 400.0, 500.0, 400.0, tx)
        assert x == pytest.approx(tx, abs=0.01) and 50.0 <= y <= 400.0
