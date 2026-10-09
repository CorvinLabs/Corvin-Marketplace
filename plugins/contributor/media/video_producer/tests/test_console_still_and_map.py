"""console_still template + "you are here" map (PLAN-0942 P3, D10/D11)."""

import hashlib
import re
from pathlib import Path

import pytest

from src import skill
from src import web_templates as wt
from src.web_templates import WebSceneError, build_document, validate_scene_data

BASE = {"title": "Die Kette", "asset": "audit_events"}


def test_catalog_is_bundled_small_and_contained():
    cat = wt._console_catalog()
    assert len(cat) >= 10
    for key, entry in cat.items():
        assert entry["file"].parent == wt.CONSOLE_ASSET_DIR
        assert entry["file"].stat().st_size <= wt.MAX_ASSET_BYTES
    assert cat["audit_compliance"]["spots"]["hash_chain_card"]["x"] == pytest.approx(0.40)
    assert "spots:" in wt.console_assets()["audit_events"]
    assert "no spots" in wt.console_assets()["chat"]


def test_callouts_and_zoom_use_measured_spots_only():
    d = validate_scene_data("console_still", {**BASE, "callouts": [{"spot": "short_hash", "label": "Kurz-Hash"}],
                                              "zoom": {"spot": "short_hash", "scale": 1.3}})
    assert d["callouts"][0] == {"spot": "short_hash", "label": "Kurz-Hash"}
    assert validate_scene_data("console_still", d) == d  # idempotent: the renderer validates again
    assert "left:84.00%" in build_document("console_still", d, duration_s=4)  # position from the catalogue
    with pytest.raises(WebSceneError, match="unknown field"):
        validate_scene_data("console_still", {**BASE, "callouts": [{"x": 0.1, "y": 0.2, "label": "guess"}]})
    with pytest.raises(WebSceneError, match="unknown spot"):
        validate_scene_data("console_still", {**BASE, "callouts": [{"spot": "hash_chain_card", "label": "x"}]})
    with pytest.raises(WebSceneError, match="unknown spot"):
        validate_scene_data("console_still", {"title": "t", "asset": "chat", "zoom": {"spot": "x", "scale": 1.2}})
    with pytest.raises(WebSceneError, match="between 1 and 1.6"):
        validate_scene_data("console_still", {**BASE, "zoom": {"spot": "short_hash", "scale": 2}})
    with pytest.raises(WebSceneError, match="unknown console asset"):
        validate_scene_data("console_still", {"title": "t", "asset": "../../etc/passwd"})
    with pytest.raises(WebSceneError, match="0-3"):
        validate_scene_data("console_still", {**BASE, "callouts": [{"spot": "short_hash", "label": "a"}] * 4})


def test_console_still_escapes_text_and_inlines_only_the_bundled_jpeg():
    payload = '<script>alert(1)</script>"><img src=x onerror=1>'
    doc = build_document("console_still", {"title": payload[:80], "asset": "audit_events", "caption": payload[:120],
                                           "callouts": [{"spot": "event_type", "label": payload[:32]}]}, duration_s=5)
    body = doc.split("</style>", 1)[1]
    assert "<script" not in body
    imgs = re.findall(r"<img[^>]*>", body)
    assert len(imgs) == 1 and imgs[0].startswith('<img alt="" src="data:image/jpeg;base64,')
    assert "http" not in imgs[0]


def test_map_strip_renders_only_with_a_valid_focus():
    doc = build_document("layers", {"title": "t", "layers": [{"label": "a"}, {"label": "b"}]}, duration_s=4, map_focus="audit")
    assert '<div class="mp on">Audit</div>' in doc
    assert 'class="map"' not in build_document("layers", {"title": "t", "layers": [{"label": "a"}, {"label": "b"}]},
                                                duration_s=4)
    with pytest.raises(WebSceneError, match="unknown map focus"):
        build_document("hero", {"title": "t"}, duration_s=4, map_focus="kernel")


def test_scene_contract_normalises_kind_and_drops_bad_map():
    scenes = [
        {"id": "a", "kind": "screenshot", "template": "console_still", "data": dict(BASE)},
        {"id": "b", "kind": "solution", "template": "hero", "data": {"title": "t"}, "map": {"focus": "kernel"}},
        {"id": "c", "kind": "solution", "map": {"focus": "audit"}},
    ]
    warnings = skill._apply_web_scene_contract(scenes, strict=False)
    assert scenes[0]["kind"] == "example"  # a template never triggers live capture
    assert "map" not in scenes[1] and any("invalid map" in w for w in warnings)
    assert scenes[2]["map"] == {"focus": "audit"}
    with pytest.raises(ValueError, match="map must be"):
        skill._apply_web_scene_contract([{"id": "x", "kind": "solution", "map": "audit"}], strict=True)


def test_constant_map_is_dropped():
    same = [{"id": "a", "map": {"focus": "audit"}}, {"id": "b", "map": {"focus": "audit"}}, {"id": "c"}]
    skill._drop_constant_map(same)
    assert all("map" not in s for s in same)
    moving = [{"id": "a", "map": {"focus": "agents"}}, {"id": "b", "map": {"focus": "audit"}}]
    skill._drop_constant_map(moving)
    assert moving[1]["map"] == {"focus": "audit"}


@pytest.mark.e2e
async def test_console_still_renders_deterministically_in_chromium(tmp_path):
    pytest.importorskip("playwright")
    from src.web_renderer import WebRenderError, WebSlideRenderer

    data = {**BASE, "callouts": [{"spot": "event_type", "label": "Ereignistyp"}],
            "zoom": {"spot": "short_hash", "scale": 1.25}}
    digests = []
    for run in range(2):
        try:
            async with WebSlideRenderer(fps=12) as r:
                frames = await r.render("console_still", data, 4.0, tmp_path / f"r{run}", map_focus="audit")
        except WebRenderError as e:
            pytest.skip(f"chromium unavailable: {e}")
        digests.append([hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in frames])
    assert digests[0] == digests[1]
    assert len(set(digests[0])) > 5  # it moves: push-in and callouts
