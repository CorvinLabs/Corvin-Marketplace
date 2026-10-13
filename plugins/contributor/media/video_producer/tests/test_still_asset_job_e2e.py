"""An uploaded image in a real video job (ADR-2249 D3/D5, T-0111).

The real ``job_main`` in its own process (storyboard model and TTS voice faked, nothing else): the
tenant's store holds a PNG uploaded with EXIF/text metadata; a ``still`` scene names it. The real MP4
must show the image's pixels, the video must carry the asset under ``source/assets/`` without the
uploader, and the report's ``asset_hygiene`` signal must have measured that copy as clean."""
import io
import json
import os
import struct
import zlib

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from src import asset_store as A
from tests.test_canvas_job_e2e import HERO, _duration, _frame, _run_job, base  # noqa: F401  (base = fixture)

pytest.importorskip("playwright")
pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc (Linux)")]

MAGENTA = (230, 20, 200)


def _upload_png() -> bytes:
    info = PngInfo()
    info.add_text("Author", "Jane Doe <jane@example.com>")
    img = Image.new("RGB", (800, 500), MAGENTA)
    img.paste((20, 200, 60), (560, 380, 760, 470))  # the "save button" the user clicked
    buf = io.BytesIO()
    img.save(buf, "PNG", pnginfo=info)
    raw = buf.getvalue()
    exif = b"MM\x00*EXIF-SECRET"
    return raw[:-12] + struct.pack(">I", len(exif)) + b"eXIf" + exif + struct.pack(">I", zlib.crc32(b"eXIf" + exif)) + raw[-12:]


async def test_a_still_job_shows_the_uploaded_image_and_measures_its_hygiene(base, tmp_path):  # noqa: F811
    asset = A.AssetStore(base).add(_upload_png(), caption="The settings page", uploaded_by="console-owner:t",
                                   source="https://u:p@example.com/settings?token=SECRET",
                                   hotspots=[{"name": "save_button", "x": 0.825, "y": 0.85, "description": "save"}])
    scene = {"id": "s2", "kind": "example", "duration_ms": 9000,
             "narration_text": "This is the settings page. The save button stores your changes.",
             "visual_description": "uploaded screenshot", "template": "still",
             "data": {"title": "Your settings page", "asset": asset["id"],
                      "callouts": [{"spot": "save_button", "label": "Save", "mark": "circle", "tone": "success"}]}}
    job_dir, rep = await _run_job(base, tmp_path, "job_still_asset",
                                  {"id": "sb_still_asset", "didactic_strategy": "rich_visual", "scenes": [HERO, scene]})

    s2 = {s["index"]: s for s in rep["scenes"]}[2]
    assert s2["renderer"] == "web" and s2["template"] == "still", s2
    copy_png = job_dir / "source" / "assets" / f"{asset['id']}.png"
    copy_doc = json.loads((job_dir / "source" / "assets" / f"{asset['id']}.json").read_text())
    assert "uploaded_by" not in copy_doc and copy_doc["source"] == "https://example.com/settings"
    raw = copy_png.read_bytes()
    assert b"jane@example.com" not in raw and b"EXIF-SECRET" not in raw

    hyg = {s["id"]: s for s in rep["signals"]}["asset_hygiene"]
    assert (hyg["verdict"], hyg["value"], hyg["basis"]) == ("pass", 0, {"n": 1, "of": 1}), hyg

    clip1 = _duration(job_dir / "scenes" / "scene_001.mp4")
    frame = _frame(job_dir / "output.mp4", clip1 + _duration(job_dir / "scenes" / "scene_002.mp4") * 0.8, tmp_path / "f.png")
    near = sum(1 for p in frame.crop((300, 250, 1620, 900)).getdata()
               if abs(p[0] - MAGENTA[0]) < 40 and abs(p[1] - MAGENTA[1]) < 40 and abs(p[2] - MAGENTA[2]) < 40)
    assert near > 100_000, f"the uploaded image is not on screen (magenta pixels: {near})"
    print(f"\nMEASURE still asset job e2e: magenta pixels={near} asset_hygiene={hyg['verdict']}")
