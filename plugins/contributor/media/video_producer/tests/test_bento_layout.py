"""Bento layout matrix (ADR-2260 decision 5, T-0198): every layout with the longest texts every tile kind allows, in
every rotation of the kinds, must render with no collision AND nothing clipped.

The tile type sizes are computed from the cell each layout really gives (``bento.cell_box``); this is the test that
holds that arithmetic to the real browser. Found by the Penpot tech demo (2026-10-18): the first version used one pixel
size for every layout and 10 of 32 worst-case combinations collided or overflowed into the header.
"""
import pytest

pytest.importorskip("playwright")

from src import bento
from src.web_templates import build_document, validate_scene_data

LONG = "Each record links to the one before it, nothing skipped in any step of the whole chain."
KINDS = ("number", "statement", "icon", "spark")
ICONS = tuple(bento.ICONS)


def _tile(kind, i):
    if kind == "number":
        return {"kind": "number", "value": 12345.67, "decimals": 2, "unit": "%/mo",
                "label": ("Average monthly cost per tenant across all regions " * 2)[:60]}
    if kind == "statement":
        return {"kind": "statement", "text": (LONG * 2)[:140]}
    if kind == "icon":
        return {"kind": "icon", "name": ICONS[i % len(ICONS)], "label": ("Verification by every operator in the chain " * 2)[:60]}
    return {"kind": "spark", "values": [1, 5, 3, 9, 4, 12, 7, 15, 11, 18, 14, 20],
            "label": ("Throughput of the worker pool over time " * 2)[:60]}


def _scene(n, featured, rot):
    d = {"eyebrow": "E" * 40, "title": "A title that is as long as the template allows, eighty char"[:80],
         "tiles": [_tile(KINDS[(rot + i) % 4], i) for i in range(n)]}
    if featured:
        d["featured"] = rot % n
    return d


CLIP_JS = """() => [...document.querySelectorAll('.bento .t, .bento .t *')]
  .filter(e => !e.closest('svg'))
  .filter(e => e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1)
  .map(e => String(e.className) + ':' + (e.textContent || '').slice(0, 24))"""


def test_every_layout_has_a_cell_box_that_fits_inside_the_grid():
    for (n, featured), name in bento.LAYOUTS.items():
        for pos in range(n):
            w, h = bento.cell_box(name, featured and pos == 0, pos)
            assert 0 < w <= bento.GRID_W and 0 < h <= bento.GRID_H, (name, pos, w, h)


@pytest.mark.asyncio
async def test_every_layout_with_the_longest_texts_renders_clean_and_unclipped():
    from playwright.async_api import async_playwright
    from src.web_renderer import WebRenderError, WebSlideRenderer
    collisions, clipped = {}, {}
    try:
        async with WebSlideRenderer(fps=12) as r:
            for (n, featured), name in bento.LAYOUTS.items():
                for rot in range(4):
                    found = await r.measure("bento", _scene(n, featured, rot), 8.0)
                    if found:
                        collisions[f"{name}|{rot}"] = [i.get("type") for i in found][:3]
    except WebRenderError as e:
        pytest.skip(f"chromium unavailable: {e}")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        for (n, featured), name in bento.LAYOUTS.items():
            for rot in range(4):
                doc = build_document("bento", _scene(n, featured, rot), duration_s=8)
                await page.set_content(doc.replace(".r {", ".r-settled {"))  # the settled end state
                found = await page.evaluate(CLIP_JS)
                if found:
                    clipped[f"{name}|{rot}"] = found[:2]
        await browser.close()
    assert not collisions, collisions
    assert not clipped, clipped


def test_the_longest_scene_is_still_inside_the_contract():
    d = validate_scene_data("bento", _scene(6, False, 0))
    assert len(d["tiles"]) == 6 and bento.layout_of(d) == "six"
