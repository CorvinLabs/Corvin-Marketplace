"""E2E for web slides (ADR-2238, PLAN-0940 DoD 2-4).

Drives ``start_video_production`` — the function the console route's runner
calls — with real Chromium, real ffmpeg and a real MP4 on disk. Only the two
external services are replaced: the TTS cloud (the chain's offline mock tier,
which writes a real WAV) and, in one test, the storyboard LLM.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

from src import skill
from src.models import VideoJob
from src.storage import get_storage
from src.web_renderer import WebRenderError

pytestmark = [pytest.mark.e2e]

if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
    pytest.skip("ffmpeg/ffprobe not installed", allow_module_level=True)


def _ffprobe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate:format=duration",
         "-of", "json", str(path)], capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


def _frame_at(video: Path, t: float, out: Path) -> Image.Image:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(out)],
                   check=True)
    return Image.open(out).convert("RGB")


def _srt_end_seconds(srt: Path) -> float:
    last = [l for l in srt.read_text(encoding="utf-8").splitlines() if "-->" in l][-1]
    end = last.split("-->")[1].strip()
    h, m, rest = end.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


STORYBOARD = {
    "id": "sb_e2e_web",
    "didactic_strategy": "rich_visual",
    "scenes": [
        {"id": "s1", "kind": "title", "duration_ms": 8000,
         "narration_text": "Folien als Webseiten, gerendert als Video in Chromium.",
         "template": "hero", "data": {"badge": "E2E", "title": "Folien als Webseiten.", "accent": "Gerendert als Video."}},
        {"id": "s2", "kind": "solution", "duration_ms": 8000,
         "narration_text": "Die Pipeline führt vom Storyboard über HTML und Chromium zu Frames und schließlich zum fertigen MP4.",
         "template": "diagram", "data": {"title": "Pipeline", "nodes": [{"label": "Storyboard"}, {"label": "Chromium"}, {"label": "MP4"}], "highlight": 1}},
        {"id": "s3", "kind": "example", "duration_ms": 8000, "theme": "light",
         "narration_text": "Zwei Renderläufe derselben Szene liefern bitgleiche Bilder, Frame für Frame.",
         "template": "stat", "data": {"value": 100, "suffix": "%", "label": "bitgleiche Frames", "locale": "de"}},
        {"id": "s4", "kind": "summary", "duration_ms": 8000,
         "narration_text": "Eine Szene ohne Template läuft weiter über den klassischen Renderer.",
         "visual_description": "check icon"},
    ],
}


@pytest.fixture
def store(tmp_path, monkeypatch):
    # The TTS cloud is the external system here: use the chain's offline tier (real WAV, real duration).
    monkeypatch.setattr(skill, "_TTS_CHAIN", (("mock", skill._tts_tier_mock),))
    base = tmp_path / "tenant"
    base.mkdir()
    return str(base)


async def _run(base: str, job_id: str, **config):
    get_storage(base).save_job(VideoJob(id=job_id, task="Web slides E2E"))
    cfg = {"storage_base": base, "tts_engine": "auto", "max_duration_minutes": 5, **config}
    return await skill.start_video_production(job_id, "Web slides E2E", cfg)


async def test_operator_storyboard_renders_web_slides_into_a_real_mp4(store, tmp_path):
    result = await _run(store, "job_web_e2e", storyboard=STORYBOARD)

    video = Path(result["video_path"])
    assert video.is_file() and video.stat().st_size > 50_000
    probe = _ffprobe(video)
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (v["codec_name"], v["width"], v["height"]) == ("h264", 1920, 1080)
    assert any(s["codec_type"] == "audio" for s in probe["streams"])

    md = result["metadata"]
    assert md["renderers"] == ["web", "web", "web", "pillow"]
    assert md["web_scenes"] == 3 and md["web_render_fallbacks"] == []
    assert md["resolution"] == "1920x1080"

    measured = float(probe["format"]["duration"])
    assert abs(measured - result["duration_seconds"]) <= 0.5, "reported duration must be the artifact's"
    assert abs(_srt_end_seconds(Path(result["srt_path"])) - measured) <= 0.25, "captions drift from the video"

    # Scene 1 animates: an early frame differs from a later one, and neither is blank.
    early = _frame_at(video, 0.10, tmp_path / "early.png")
    late = _frame_at(video, 2.50, tmp_path / "late.png")
    assert ImageChops.difference(early, late).getbbox() is not None
    assert ImageStat.Stat(late.convert("L")).stddev[0] > 8, "late frame looks blank"
    # The hero slide is dark-themed; the light-themed stat scene (s3) has a light background.
    assert sum(late.getpixel((20, 20))) < 120
    clips = sorted((video.parent / "scenes").glob("scene_00[12].mp4"))
    assert len(clips) == 2
    s3_start = sum(float(_ffprobe(c)["format"]["duration"]) for c in clips)
    light = _frame_at(video, s3_start + 2.0, tmp_path / "light.png")
    assert sum(light.getpixel((20, 20))) > 600


async def test_browser_unavailable_falls_back_to_classic_slides_and_says_so(store, monkeypatch):
    async def broken_enter(self):
        raise WebRenderError("chromium could not be launched: simulated")
    monkeypatch.setattr("src.web_renderer.WebSlideRenderer.__aenter__", broken_enter)

    result = await _run(store, "job_web_fallback", storyboard=STORYBOARD)

    assert Path(result["video_path"]).is_file()
    md = result["metadata"]
    assert md["renderers"] == ["pillow"] * 4
    assert [f["scene"] for f in md["web_render_fallbacks"]] == [1, 2, 3]
    assert all("browser unavailable" in f["reason"] for f in md["web_render_fallbacks"])
    assert _ffprobe(Path(result["video_path"]))["streams"][0]["width"] == 1920


async def test_web_slides_switched_off_is_configuration_not_a_fallback(store):
    result = await _run(store, "job_web_off", storyboard=STORYBOARD, web_slides=False)
    assert result["metadata"]["renderers"] == ["pillow"] * 4
    assert result["metadata"]["web_render_fallbacks"] == []


async def test_invalid_operator_storyboard_fails_before_any_work(store):
    bad = json.loads(json.dumps(STORYBOARD))
    bad["scenes"][1]["data"]["nodes"][0]["onclick"] = "alert(1)"
    with pytest.raises(ValueError, match="scene s2"):
        await _run(store, "job_web_bad", storyboard=bad)
    job = get_storage(store).get_job("job_web_bad")
    assert job.status == "error" and "unknown field" in job.error_message
    assert not (Path(store) / "videos" / "job_web_bad" / "output.mp4").exists()


async def test_llm_storyboard_invalid_web_spec_is_dropped_not_passed_through(store, monkeypatch):
    llm_json = {
        "id": "sb_llm", "didactic_strategy": "minimal_visual",
        "scenes": [
            {"id": "s1", "kind": "title", "duration_ms": 8000, "narration_text": "Ein kurzer Titel zum Test.",
             "template": "hero", "data": {"title": "<script>alert(1)</script> Titel"}},
            {"id": "s2", "kind": "summary", "duration_ms": 8000, "narration_text": "Diese Szene hat ein erfundenes Template.",
             "template": "slideshow", "data": {"html": "<img src=x onerror=alert(1)>"}},
        ],
    }
    monkeypatch.setattr(skill, "_call_storyboard_llm", lambda *a, **k: json.dumps(llm_json))

    result = await _run(store, "job_web_llm")

    assert result["metadata"]["renderers"] == ["web", "pillow"]
    job = get_storage(store).get_job("job_web_llm")
    assert job.storyboard.scenes[1].template is None and job.storyboard.scenes[1].data is None
    # The script tag reached the slide as escaped text, not markup (asserted on the document).
    from src.web_templates import build_document
    doc = build_document("hero", job.storyboard.scenes[0].data, duration_s=4)
    assert "<script>" not in doc and "&lt;script&gt;" in doc


def test_render_call_site_is_inside_orchestrate_video():
    """PLAN-0940 DoD 4: the renderer is reached from the production path."""
    import inspect
    src = inspect.getsource(skill.orchestrate_video)
    assert "_WebRendererSession(" in src and "web.render(" in src and "_assemble_frames_clip(" in src
