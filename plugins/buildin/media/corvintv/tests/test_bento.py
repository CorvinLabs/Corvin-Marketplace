"""``bento`` template (ADR-2260 decision 5, T-0198): two to six tiles, closed vocabulary, fail-closed."""

import pytest

from src import bento as bento_mod
from src import skill as skill_mod
from src import web_templates as wt
from src.web_templates import WebSceneError, build_document, reveal_steps, scene_items, validate_scene_data

NUMBER = {"kind": "number", "value": 12.5, "decimals": 1, "unit": "%", "label": "uptime"}
STATEMENT = {"kind": "statement", "text": "Audit chain intact"}
ICON = {"kind": "icon", "name": "shield", "label": "tenant isolated"}
SPARK = {"kind": "spark", "values": [1, 4, 2, 6], "label": "traffic"}
TILE_CYCLE = [NUMBER, STATEMENT, ICON, SPARK, NUMBER, STATEMENT]

# The ADR-2260 decision 5 table: tile count x featured -> layout name. Every other cell is refused.
LAYOUT_TABLE = {
    (2, None): "two",
    (3, None): "three", (3, 0): "feature3",
    (4, None): "quad", (4, 0): "feature4",
    (5, None): "five", (5, 0): "feature5",
    (6, None): "six",
}


def _scene(n, featured=None):
    data = {"title": "T", "tiles": [TILE_CYCLE[k % len(TILE_CYCLE)] for k in range(n)]}
    if featured is not None:
        data["featured"] = featured
    return data


@pytest.mark.parametrize("cell", sorted(LAYOUT_TABLE, key=str), ids=lambda c: f"{c[0]}-{c[1]}")
def test_every_table_cell_is_accepted_and_maps_to_its_layout(cell):
    n, featured = cell
    d = validate_scene_data("bento", _scene(n, featured))
    assert bento_mod.layout_of(d) == LAYOUT_TABLE[cell]
    assert "layout" not in d, "the layout is derived from the table, never part of the data"
    assert len(d["tiles"]) == n


@pytest.mark.parametrize("n", [1, 7])
@pytest.mark.parametrize("featured", [None, 0])
def test_tile_count_outside_two_to_six_is_refused(n, featured):
    with pytest.raises(WebSceneError):
        validate_scene_data("bento", _scene(n, featured))


@pytest.mark.parametrize("n,featured", [(2, 0), (6, 0), (2, 1), (6, 5)])
def test_featured_combinations_outside_the_table_are_refused(n, featured):
    # one refusal per refused cell: 2 and 6 tiles have no featured layout
    with pytest.raises(WebSceneError, match="not a layout"):
        validate_scene_data("bento", _scene(n, featured))


@pytest.mark.parametrize("featured", [-1, 4, True, "0", 0.0])
def test_featured_must_be_an_index_of_a_tile(featured):
    with pytest.raises(WebSceneError):
        validate_scene_data("bento", _scene(4, featured))


def test_no_free_coordinates_and_no_unknown_keys():
    for extra in ({"x": 0}, {"layout": "quad"}, {"columns": 3}):
        with pytest.raises(WebSceneError, match="unknown field"):
            validate_scene_data("bento", {**_scene(2), **extra})
    tile = {**NUMBER, "x": 1}
    with pytest.raises(WebSceneError, match="unknown field"):
        validate_scene_data("bento", {"tiles": [tile, STATEMENT]})


@pytest.mark.parametrize("tile,msg", [
    ({"kind": "chart", "text": "x"}, "tile kind"),
    ({"kind": "html", "text": "<b>x</b>"}, "tile kind"),
    ({"text": "no kind"}, "tile kind"),
    ({"kind": "icon", "name": "skull", "label": "x"}, "icon"),
    ({"kind": "number", "value": True, "label": "x"}, "finite number"),
    ({"kind": "number", "value": 1e9, "label": "x"}, "below"),
    ({"kind": "number", "value": float("nan"), "label": "x"}, "finite number"),
    ({"kind": "number", "value": 1, "decimals": 3, "label": "x"}, "decimals"),
    ({"kind": "spark", "values": [1, 2], "label": "x"}, "items"),
    ({"kind": "spark", "values": [1] * 13, "label": "x"}, "items"),
    ({"kind": "spark", "values": [1, "2", 3], "label": "x"}, "finite number"),
    ({"kind": "statement", "text": "x" * 141}, "limit"),
    ({"kind": "statement"}, "missing required"),
])
def test_tile_contract_refuses_outside_the_closed_vocabulary(tile, msg):
    with pytest.raises(WebSceneError, match=msg):
        validate_scene_data("bento", {"tiles": [tile, STATEMENT]})


def test_tiles_must_be_objects():
    with pytest.raises(WebSceneError, match="objects"):
        validate_scene_data("bento", {"tiles": ["a", STATEMENT]})


HOSTILE = [
    "<script>alert(1)</script>",
    '"><img src=x onerror=alert(1)>',
    "‮abc‬",            # bidi override
    "a​b﻿c",            # zero-width characters
    "\ud800",                     # lone surrogate: a validation error, never a crash
]


@pytest.mark.parametrize("payload", HOSTILE)
def test_hostile_strings_are_escaped_or_refused_in_every_text_field(payload):
    tiles = [{"kind": "statement", "text": payload}, {"kind": "number", "value": 1, "label": payload}]
    try:
        html = build_document("bento", {"title": payload, "tiles": tiles}, duration_s=6)
    except WebSceneError:
        return  # the lone surrogate path: refused, which is the contract
    assert "<script" not in html and "<img" not in html
    assert "‮" not in html and "​" not in html and "﻿" not in html


def test_reveal_steps_and_items_follow_the_tiles_in_data_order():
    d = validate_scene_data("bento", _scene(4, 2))
    assert reveal_steps("bento", d) == 4
    items = scene_items("bento", d)
    assert [step for _, step in items] == [2, 3, 4, 5]
    assert items[0][0] == "uptime"           # number: its label
    assert items[1][0] == "Audit chain intact"  # statement: its text
    assert items[2][0] == "tenant isolated"  # icon: its label


def test_render_is_the_real_build_path_and_is_deterministic():
    data = _scene(5, 1)
    a = build_document("bento", data, duration_s=8)
    b = build_document("bento", data, duration_s=8)
    assert a == b
    assert 'class="bento five' in a or 'class="bento feature5' in a
    assert 'class="bento feature5"' in a
    # the featured tile is the first cell of the layout (placed first), each tile keeps its reveal index
    assert a.index('class="t r feat"') < a.index("Audit chain intact")
    for k in range(5):
        assert f'--i:{2 + k};' in a
    assert "grid-row" not in a.split("</style>")[1]  # layout rules live in the stylesheet, not the markup


def test_every_layout_renders_with_its_class():
    for (n, featured), layout in LAYOUT_TABLE.items():
        html = build_document("bento", _scene(n, featured), duration_s=6)
        assert f'class="bento {layout}"' in html


def test_storyboard_guide_offers_bento_and_the_registry_knows_it():
    assert "bento" in wt.TEMPLATES
    assert "bento" in skill_mod.TEMPLATES
    assert '- "bento":' in skill_mod.__dict__.get("SCENE_GUIDE", "") or '- "bento":' in open(skill_mod.__file__, encoding="utf-8").read()


def test_normalised_data_validates_again_unchanged():
    """The job stores the validated data back into the scene and validates it again for the cues: a bento that does not
    survive that second pass silently becomes a classic slide (found by the Penpot tech demo, 2026-10-18)."""
    for n, featured in ((2, None), (3, 0), (4, None), (5, 0), (6, None)):
        d = validate_scene_data("bento", _scene(n, featured))
        assert validate_scene_data("bento", d) == d
