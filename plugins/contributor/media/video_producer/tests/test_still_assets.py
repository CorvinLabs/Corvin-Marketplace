"""`still` over uploaded images and the asset_hygiene signal (ADR-2249 D3/D5, T-0111)."""
import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from src import asset_store as A
from src import signals as sg
from src import skill
from src import web_templates as wt
from src.web_templates import WebSceneError, build_document, scene_items, validate_scene_data

FIX = "ast_5ee1ab1e"  # the committed fixture asset (conftest binds its tenant)


def ok(**over):
    d = {"title": "The settings page", "asset": FIX, "caption": "Where you save",
         "callouts": [{"spot": "save_button", "label": "Save", "mark": "circle", "tone": "success"}],
         "zoom": {"spot": "save_button", "scale": 1.3}}
    d.update(over)
    return d


def test_still_validates_against_the_bound_catalogue_and_is_idempotent():
    v = validate_scene_data("still", ok())
    assert v["callouts"] == [{"spot": "save_button", "label": "Save", "mark": "circle", "tone": "success"}]
    assert validate_scene_data("still", v) == v
    assert scene_items("still", v) == [("Save", 3)]


@pytest.mark.parametrize("bad,why", [
    ({"asset": "ast_deadbeef"}, "unknown image asset"),
    ({"asset": "audit_compliance"}, "unknown image asset"),
    ({"callouts": [{"spot": "nowhere", "label": "x"}]}, "unknown spot"),
    ({"callouts": [{"spot": "header", "label": "x", "x": 0.2, "y": 0.3}]}, "unknown field"),
    ({"callouts": [{"spot": "header", "label": "x", "tone": "#ff0000"}]}, "tone"),
    ({"callouts": [{"spot": "header", "label": "x", "mark": "arrow"}]}, "mark"),
    ({"zoom": {"spot": "header", "scale": 3}}, "zoom.scale"),
    ({"callouts": [{"spot": "header", "label": "x"}] * 5}, "callouts"),
])
def test_still_refuses_what_is_not_user_authored_or_out_of_bounds(bad, why):
    with pytest.raises(WebSceneError, match=why):
        validate_scene_data("still", ok(**bad))


def test_without_a_bound_store_there_are_no_uploaded_images():
    with A.bound(None), pytest.raises(WebSceneError, match="no uploaded images"):
        validate_scene_data("still", ok())


def test_another_tenants_asset_is_unknown(tmp_path):
    with A.bound(str(tmp_path / "other")), pytest.raises(WebSceneError, match="no uploaded images"):
        validate_scene_data("still", ok())


def test_build_embeds_the_stored_png_with_hotspot_callouts_tone_and_pen():
    doc = build_document("still", validate_scene_data("still", ok()), duration_s=8)
    png = A.AssetStore(str(Path(__file__).parent / "fixtures" / "assets_tenant")).get(FIX)["png"]
    assert f"data:image/png;base64,{base64.b64encode(png).decode()}" in doc
    assert "left:81.00%;top:86.00%" in doc  # the hotspot the user clicked, not a model coordinate
    assert "--co:var(--success)" in doc and 'class="pen circle"' in doc and "still-pen" in doc
    assert 'class="frame still still-u"' in doc
    plain = build_document("still", validate_scene_data("still", ok(callouts=[{"spot": "header", "label": "h"}])), duration_s=8)
    assert "--co:var(--accent)" in plain and "still-pen" not in plain


def test_a_console_still_without_a_mark_carries_no_pen_css():
    d = validate_scene_data("console_still", {"title": "T", "asset": "audit_compliance",
                                              "callouts": [{"spot": "hash_chain_card", "label": "c"}]})
    assert "still-pen" not in build_document("console_still", d, duration_s=6)
    d["callouts"][0]["mark"] = "circle"
    assert "still-pen" in build_document("console_still", d, duration_s=6)


def test_the_storyboard_prompt_offers_still_only_with_uploaded_images(tmp_path):
    guide = skill._still_guide()
    assert '"still"' in guide and FIX in guide and "the green save button" in guide
    with A.bound(str(tmp_path / "empty")):
        assert skill._still_guide() == "" and wt.user_assets() == {}


def _png_with_metadata():
    info = PngInfo()
    info.add_text("Author", "Jane")
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (1, 2, 3)).save(buf, "PNG", pnginfo=info)
    return buf.getvalue()


def test_snapshot_copies_the_used_assets_without_the_uploader(tmp_path):
    sb = SimpleNamespace(scenes=[SimpleNamespace(template="still", data={"asset": FIX}),
                                 SimpleNamespace(template="still", data={"asset": "ast_deadbeef"}),
                                 SimpleNamespace(template="hero", data={})])
    assert skill._snapshot_assets(sb, tmp_path) == [FIX]
    doc = json.loads((tmp_path / "source" / "assets" / f"{FIX}.json").read_text())
    assert "uploaded_by" not in doc and doc["caption"].startswith("The settings page")
    assert (tmp_path / "source" / "assets" / f"{FIX}.png").read_bytes().startswith(A.PNG_MAGIC)


def _ctx(job_dir):
    return sg.SignalContext(job_dir=job_dir, report={"scenes": []}, templates={"still"})


def test_asset_hygiene_passes_on_a_clean_snapshot_and_fails_on_metadata_or_a_query(tmp_path):
    sb = SimpleNamespace(scenes=[SimpleNamespace(template="still", data={"asset": FIX})])
    skill._snapshot_assets(sb, tmp_path)
    rec = {r["id"]: r for r in sg.run(_ctx(tmp_path), only=["asset_hygiene"])}["asset_hygiene"]
    assert (rec["verdict"], rec["value"], rec["basis"]) == ("pass", 0, {"n": 1, "of": 1})

    folder = tmp_path / "source" / "assets"
    (folder / f"{FIX}.png").write_bytes(_png_with_metadata())
    doc = json.loads((folder / f"{FIX}.json").read_text())
    (folder / f"{FIX}.json").write_text(json.dumps({**doc, "source": "https://h.test/p?token=x"}))
    rec = {r["id"]: r for r in sg.run(_ctx(tmp_path), only=["asset_hygiene"])}["asset_hygiene"]
    assert rec["verdict"] == "fail" and rec["value"] == 1
    found = rec["detail"]["per_asset"][0]["findings"]
    assert any(f.startswith("metadata:") and "tEXt" in f for f in found) and "provenance" in found


def test_asset_hygiene_skips_without_still_or_without_an_image(tmp_path):
    recs = {r["id"]: r for r in sg.run(sg.SignalContext(job_dir=tmp_path, report={"scenes": []}), only=["asset_hygiene"])}
    assert recs["asset_hygiene"]["verdict"] == "skip"
    recs = {r["id"]: r for r in sg.run(_ctx(tmp_path), only=["asset_hygiene"])}
    assert recs["asset_hygiene"]["verdict"] == "skip" and "no uploaded image" in recs["asset_hygiene"]["reason"]
