"""A non-Corvin style travels the whole real path: job config -> orchestrator -> Chromium -> ffmpeg -> MP4
(PLAN-0945 P1 DoD). Real browser, real ffmpeg; only the TTS cloud is replaced by the offline tier."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from src import skill
from src.models import VideoJob
from src.storage import get_storage
from tests.test_style_pack import make_style

pytestmark = [pytest.mark.e2e]

if shutil.which("ffmpeg") is None:
    pytest.skip("ffmpeg not installed", allow_module_level=True)

STORYBOARD = {
    "id": "sb_style_e2e", "didactic_strategy": "rich_visual",
    "scenes": [
        {"id": "s1", "kind": "title", "duration_ms": 8000,
         "narration_text": "Willkommen bei Acme, hier sehen Sie unser eigenes Erscheinungsbild.",
         "template": "hero", "data": {"badge": "Acme", "title": "Unser Look.", "accent": "Nicht Corvin."}},
        {"id": "s2", "kind": "solution", "duration_ms": 8000,
         "narration_text": "Die Pipeline führt vom Auftrag über den Browser zum fertigen Video mit unseren Farben.",
         "template": "diagram", "data": {"title": "Pipeline", "nodes": [{"label": "Auftrag"}, {"label": "Browser"},
                                                                           {"label": "Video"}], "highlight": 1}},
    ],
}


def _frame(video: Path, t: float, out: Path) -> Image.Image:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(out)],
                   check=True)
    return Image.open(out).convert("RGB")


def _near(img: Image.Image, rgb, tol=40) -> int:
    n = 0
    for px in img.resize((480, 270)).getdata():
        if all(abs(px[i] - rgb[i]) <= tol for i in range(3)):
            n += 1
    return n


async def _run(tmp_path, monkeypatch, job_id, **config):
    monkeypatch.setattr(skill, "_TTS_CHAIN", (("mock", skill._tts_tier_mock),))
    base = tmp_path / "tenant"
    base.mkdir(exist_ok=True)
    get_storage(str(base)).save_job(VideoJob(id=job_id, task="style e2e"))
    return await skill.start_video_production(job_id, "style e2e", {
        "storage_base": str(base), "tts_engine": "auto", "max_duration_minutes": 5, "storyboard": STORYBOARD, **config})


async def test_style_reaches_the_pixels_and_travels_with_the_video(tmp_path, monkeypatch):
    st = make_style()
    result = await _run(tmp_path, monkeypatch, "job_styled", web_style=st)
    video = Path(result["video_path"])
    assert video.is_file() and result["metadata"]["web_render_fallbacks"] == []

    blue = (0x3B, 0xA3, 0xFF)       # the style's accent
    gold = (0xE8, 0xA8, 0x3A)       # Corvin's accent
    hero = _frame(video, 1.5, tmp_path / "f.png")    # the large accent headline of scene 1
    diagram = _frame(video, 6.0, tmp_path / "d.png")  # scene 2, highlighted node
    assert _near(hero, blue, tol=70) > 150, "the style's accent never reached the frame"
    for frame in (hero, diagram):
        assert _near(frame, gold) < 30, "Corvin's accent leaked into a custom-styled video"
        assert _near(frame, (0xC9, 0xA2, 0x27)) < 30, "the Corvin gold dot is on the frame"
    assert _near(hero, (0xC8, 0x1E, 0x1E), tol=30) > 300, "the style's own logo is not on the opening frame"

    snap = video.parent / "style"
    assert json.loads((snap / "style.json").read_text())["id"] == st.id
    assert (snap / "logo.png").is_file()


async def test_without_a_style_the_corvin_look_is_unchanged(tmp_path, monkeypatch):
    result = await _run(tmp_path, monkeypatch, "job_plain")
    video = Path(result["video_path"])
    frame = _frame(video, 1.5, tmp_path / "g.png")
    assert _near(frame, (0xE8, 0xA8, 0x3A), tol=70) > 150
    assert not (video.parent / "style").exists()


async def test_an_invalid_style_fails_the_job_instead_of_rendering_it(tmp_path, monkeypatch):
    st = make_style()
    st.tokens["dark"]["text"] = st.tokens["dark"]["bg"]
    with pytest.raises(Exception):
        await _run(tmp_path, monkeypatch, "job_bad", web_style=st)
    job = get_storage(str(tmp_path / "tenant")).get_job("job_bad")
    assert job.status == "error"
