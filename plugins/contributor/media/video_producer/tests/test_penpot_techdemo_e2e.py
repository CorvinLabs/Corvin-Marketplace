"""Tech demo as an end-to-end test: one complete video that shows what Penpot adds to the Video Producer.

Everything runs for real - the Penpot SVG importer, the per-tenant asset store, the storyboard contract, the cue timeline,
headless Chromium, ffmpeg and a real MP4 on disk. Two things are substituted, both outside the code under test:
the narration voice is the chain's offline mock tier (a real WAV of the right length, silent), and the Penpot board is
the committed export of a real Penpot 2.18 board (``tests/fixtures/penpot_board.svg``) - no Penpot server, no cloud,
no upload of anything to a third party.

The video, in order: the look of the design (a style imported from the same SVG) -> how the import works (a flow) ->
the board revealed step by step (the new ``board`` scene) -> the same design as a picture with a callout (``still``)
-> the numbers behind it (``bento``) -> picture or board (``compare``) -> a closing line.

Set ``CORVIN_TECHDEMO_OUT`` to a directory to keep the MP4 and a contact sheet there.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from src import asset_store as A
from src import penpot_import as pi
from src import skill
from src.models import VideoJob
from src.storage import get_storage

pytestmark = [pytest.mark.e2e]

if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
    pytest.skip("ffmpeg/ffprobe not installed", allow_module_level=True)
pytest.importorskip("playwright")

FIXTURE = Path(__file__).parent / "fixtures" / "penpot_board.svg"

STEPS = [{"shapes": [0, 1], "label": "Brand mark"}, {"shapes": [2, 3, 4, 5], "label": "Colour palette"},
         {"shapes": [6, 7], "label": "Title"}]


def _storyboard(asset: str) -> dict:
    return {"id": "sb_penpot_techdemo", "didactic_strategy": "rich_visual", "scenes": [
        {"id": "s1", "kind": "title", "duration_ms": 8000,
         "narration_text": "Penpot meets the Video Producer. A design made in an open source tool becomes part of a video.",
         "template": "hero", "beats": ["Penpot", "open source"],
         "data": {"badge": "Tech demo", "title": "Penpot meets Corvin", "accent": "Designs become scenes."}},
        {"id": "s2", "kind": "solution", "duration_ms": 12000,
         "narration_text": ("You export a board from Penpot as an SVG file. The producer reads it into a closed model of "
                            "shapes. Only that model is drawn. Nothing from the file reaches the browser."),
         "template": "flow", "beats": [0, 1, 2, 3],
         "data": {"title": "From the export to the video",
                  "nodes": [{"id": "svg", "label": "SVG export", "sub": "from Penpot"},
                            {"id": "model", "label": "Closed model", "sub": "typed shapes"},
                            {"id": "draw", "label": "Drawn slide", "sub": "Chromium"},
                            {"id": "mp4", "label": "Video", "sub": "MP4"}],
                  "edges": [{"from": "svg", "to": "model"}, {"from": "model", "to": "draw"}, {"from": "draw", "to": "mp4"}]}},
        {"id": "s3", "kind": "example", "duration_ms": 14000,
         "narration_text": ("Here is the board itself. First the brand mark. Then the colour palette. "
                            "At the end the title of the slide appears, exactly when it is named."),
         "template": "board", "beats": [None, 0, 1, 2],
         "data": {"eyebrow": "Imported from Penpot", "title": "The board, step by step", "asset": asset}},
        {"id": "s4", "kind": "example", "duration_ms": 10000,
         "narration_text": ("The same design also works as a picture. A callout can point at any place you mark, "
                            "for example the colour palette."),
         "template": "still", "beats": [None, 0],
         "data": {"title": "The design as a picture", "asset": asset,
                  "callouts": [{"spot": "palette", "label": "Brand colours"}]}},
        {"id": "s5", "kind": "solution", "duration_ms": 14000,
         "narration_text": ("What the import keeps. Eight shapes were read from the export. The upload itself is never "
                            "stored. Steps are assigned by hand, then the narration reveals them. Rendering stays fast."),
         "template": "bento", "beats": [0, 1, 2, 3],
         "data": {"eyebrow": "What the import keeps", "title": "Facts at a glance", "featured": 0,
                  "tiles": [{"kind": "number", "value": 8, "decimals": 0, "unit": "", "label": "shapes read from the export"},
                            {"kind": "icon", "name": "shield", "label": "the upload is never stored"},
                            {"kind": "statement", "text": "Steps are assigned by hand, then the narration reveals them."},
                            {"kind": "spark", "values": [3, 4, 3, 4, 3, 4], "label": "frame time stays flat"}]}},
        {"id": "s6", "kind": "solution", "duration_ms": 12000,
         "narration_text": "A picture is quick. A board follows your narration. Choose by what the scene needs.",
         "template": "compare", "beats": [0, 1],
         "data": {"title": "Picture or board", "left": {"title": "Picture", "points": ["One image", "Callouts on marked places"]},
                  "right": {"title": "Board", "points": ["Steps in your order", "Revealed by the narration"]}}},
        {"id": "s7", "kind": "summary", "duration_ms": 8000,
         "narration_text": "That is Penpot in the Video Producer: design once, then tell the story.",
         "template": "quote", "beats": ["Penpot"],
         "data": {"quote": "Design once, then tell the story.", "attribution": "Penpot + Video Producer"}},
    ]}


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(skill, "_TTS_CHAIN", (("mock", skill._tts_tier_mock),))  # the offline tier: a real, silent WAV
    d = tmp_path / "tenant"
    d.mkdir()
    return str(d)


def _frame(video: Path, t: float, out: Path) -> Image.Image:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(out)],
                   check=True)
    return Image.open(out).convert("RGB")


def _near(img: Image.Image, rgb, tol=40) -> int:
    return sum(all(abs(p[i] - rgb[i]) <= tol for i in range(3)) for p in img.resize((480, 270)).getdata())


@pytest.mark.asyncio
async def test_penpot_tech_demo_makes_one_complete_video(base, tmp_path):
    import asyncio

    svg = FIXTURE.read_bytes()
    # 1. the look: a style drafted from the board (same reader as the console's "import from Penpot")
    draft = pi.import_penpot(svg, "Penpot board.svg")
    style = draft.style
    assert style.source["kind"] == "penpot"

    # 2. the board: parse -> render the picture -> store picture + typed model -> assign steps -> mark a place
    design = pi.parse_design(svg)
    assert len(design.shapes) == 8 and design.dropped == {}
    png = await pi.render_png(design)
    store = A.AssetStore(base)
    doc = store.add(png, caption="Penpot board", uploaded_by="techdemo", design=design)
    store.update(doc["id"], steps=STEPS)
    store.update(doc["id"], hotspots=[{"name": "palette", "x": 0.2, "y": 0.9, "description": "the colour swatches"}])
    asset = doc["id"]
    ready = store.board(asset)
    assert ready["labels"] == ["Brand mark", "Colour palette", "Title"] and asset in store.board_catalogue()

    # 3. the video, through the real entry point
    get_storage(base).save_job(VideoJob(id="job_penpot_demo", task="Penpot tech demo"))
    cfg = {"storage_base": base, "tts_engine": "auto", "max_duration_minutes": 5, "storyboard": _storyboard(asset),
           "web_style": style}
    result = await skill.start_video_production("job_penpot_demo", "Penpot tech demo", cfg)
    md = result["metadata"]
    video = Path(result["video_path"])

    # every scene on the web renderer, in the order told, nothing degraded
    assert md["layout_collisions"] == [], md["layout_collisions"]
    assert md["renderers"] == ["web"] * 7, md.get("renderers")
    assert [c["template"] for c in md["cues"]] == ["hero", "flow", "board", "still", "bento", "compare", "quote"]
    assert md["board_fallbacks"] == []
    report = json.loads((video.parent / "report.json").read_text())
    # the only degradation this demo accepts is the one it asks for: the offline (silent) voice, recorded as tts_tier_below
    others = [d for d in report.get("degradations") or [] if d["kind"] != "tts_tier_below"]
    assert others == [], others
    assert md["layout_collisions"] == []

    # a real, complete MP4
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height:format=duration", "-of", "json",
         str(video)], capture_output=True, text=True, check=True).stdout)
    kinds = {s["codec_type"]: s for s in probe["streams"]}
    assert (kinds["video"]["width"], kinds["video"]["height"]) == (1920, 1080) and "audio" in kinds
    duration = float(probe["format"]["duration"])
    assert duration > 25, duration

    # the style travelled: the video carries the board's blue, not Corvin's gold, on the title slide
    work = tmp_path / "frames"
    work.mkdir()
    spans = _scene_spans(report)
    hero = _frame(video, 1.5, work / "hero.png")
    assert _near(hero, (0x00, 0x66, 0xCC), 70) > 100, "the Penpot colours did not reach the title slide"

    # the board scene reveals step n before step n+1 (blue brand mark, then the orange swatch)
    board = md["cues"][2]
    ats = [it["at"] for it in board["items"]]
    assert all(a is not None for a in ats) and ats == sorted(ats) and ats[2] - ats[0] > 2.0, ats
    scene_start = spans[0][2]
    between = _frame(video, scene_start + (ats[0] + ats[1]) / 2 + 0.3, work / "b01.png")
    after = _frame(video, scene_start + ats[1] + 1.2, work / "b1.png")
    assert _near(between, (0x00, 0x66, 0xCC)) > 30, "step 0 (brand mark) not shown at its cue"
    assert _near(between, (0xFF, 0x66, 0x00)) < 5, "step 1 (palette) shown before its cue"
    assert _near(after, (0xFF, 0x66, 0x00)) > 5, "step 1 (palette) never appeared"
    assert ImageChops.difference(between, after).getbbox() is not None

    # the bento reveals its tiles in narration order
    bento = md["cues"][4]
    bats = [it["at"] for it in bento["items"]]
    assert all(a is not None for a in bats) and bats == sorted(bats) and bats[3] - bats[0] > 3.0, bats

    # the source of the video holds the board it showed - even after the asset is deleted
    store.delete(asset)
    src = video.parent / "source" / "assets"
    assert (src / f"{asset}.png").is_file() and (src / f"{asset}.design.json").is_file()
    pi.validate_design(json.loads((src / f"{asset}.design.json").read_text()))

    out = os.environ.get("CORVIN_TECHDEMO_OUT")
    if out:
        dest = Path(out)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(video, dest / "penpot-techdemo.mp4")
        shots = [_frame(video, s + d - 0.4, work / f"s{i}.png").resize((640, 360)) for i, (s, d) in enumerate(zip(*spans))]
        sheet = Image.new("RGB", (1920, 360 * ((len(shots) + 2) // 3)))
        for i, im in enumerate(shots):
            sheet.paste(im, ((i % 3) * 640, (i // 3) * 360))
        sheet.save(dest / "penpot-techdemo-contactsheet.png")


def _scene_spans(report: dict):
    """(starts, lengths) of every scene in the final video, from the job's own report (scenes[i].audio_s)."""
    lengths = [float(sc["audio_s"]) for sc in report["scenes"]]
    starts, t = [], 0.0
    for n in lengths:
        starts.append(t)
        t += n
    return starts, lengths
