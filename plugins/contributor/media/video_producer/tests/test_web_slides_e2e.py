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
    assert "srt_path" not in result and not list(video.parent.glob("*.srt")), "subtitles must not be produced"
    assert [s["codec_type"] for s in probe["streams"] if s["codec_type"] == "subtitle"] == []

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


FLOW_NARRATION = " ".join(["Ein Auftrag läuft durch das Storyboard, von dort parallel in die Narration und in die"
                           " Web-Folien, und beide Stränge treffen sich im fertigen Video."] * 2)


async def test_ambient_motion_keeps_moving_until_the_narration_ends(store, tmp_path):
    """A flow slide's data pulses keep travelling after the entrance animation, for
    the whole narration — the clip repeats one rendered period instead of holding
    the last frame."""
    sb = {"id": "sb_amb", "didactic_strategy": "rich_visual", "scenes": [
        {"id": "s1", "kind": "solution", "duration_ms": 20000, "narration_text": FLOW_NARRATION,
         "template": "flow", "data": {"title": "Fluss", "nodes": [
             {"id": "a", "label": "Auftrag"}, {"id": "b", "label": "Storyboard"},
             {"id": "c", "label": "Narration"}, {"id": "d", "label": "Folien"}, {"id": "e", "label": "Video"}],
             "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}, {"from": "b", "to": "d"},
                       {"from": "c", "to": "e"}, {"from": "d", "to": "e"}]}}]}
    result = await _run(store, "job_ambient", storyboard=sb)
    video = Path(result["video_path"])
    duration = float(_ffprobe(video)["format"]["duration"])
    assert duration > 14, "narration must outlast the entrance for this test to mean anything"
    # Two frames half a pulse period (1 s) apart, both well after the entrance settled.
    a = _frame_at(video, duration - 3.0, tmp_path / "a.png")
    b = _frame_at(video, duration - 2.0, tmp_path / "b.png")
    # Count strongly changed pixels: H.264 noise on a held frame is low-amplitude and
    # scattered (measured: a held frame still differs by ~56k summed, but almost no
    # pixel moves by more than 40 levels); a travelling pulse moves hundreds.
    diff = ImageChops.difference(a, b).convert("L")
    moved = sum(diff.point(lambda x: 255 if x > 40 else 0).histogram()[255:])
    assert moved > 300, f"the slide froze after its entrance ({moved} px moved; held frame instead of ambient loop)"


def _fake_claude(tmp_path: Path, monkeypatch, storyboard: dict, exit_code: int = 0) -> Path:
    """An executable standing in for the Claude Code CLI at the real process
    boundary: it records argv + stdin and answers like `claude -p --output-format json`."""
    log = tmp_path / "claude_calls.jsonl"
    script = tmp_path / "claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        f"log = {str(log)!r}\n"
        "prompt = sys.stdin.read()\n"
        "with open(log, 'a') as f: f.write(json.dumps({'argv': sys.argv[1:], 'stdin_len': len(prompt), 'cwd': os.getcwd()}) + '\\n')\n"
        f"sys.stdout.write(json.dumps({{'type': 'result', 'is_error': False, 'result': {json.dumps(json.dumps(storyboard))}}}))\n"
        f"sys.exit({exit_code})\n"
    )
    script.chmod(0o755)
    monkeypatch.setenv("CORVIN_CLAUDE_BIN", str(script))
    return log


CLAUDE_STORYBOARD = {"id": "sb_cli", "didactic_strategy": "rich_visual", "scenes": [
    {"id": "s1", "kind": "title", "duration_ms": 8000, "narration_text": "Die Lernschleife von CorvinOS.",
     "visual_description": "loop", "template": "hero", "data": {"title": "Die Lernschleife"}},
    {"id": "s2", "kind": "solution", "duration_ms": 9000,
     "narration_text": "Jede Entscheidung wird geprüft, bewertet und verbessert die nächste Ausführung.",
     "visual_description": "cycle", "template": "cycle",
     "data": {"title": "Kreislauf", "steps": [{"label": "Planen"}, {"label": "Prüfen"}, {"label": "Lernen"}]}},
]}


async def test_claude_cli_backend_writes_the_storyboard(store, tmp_path, monkeypatch):
    log = _fake_claude(tmp_path, monkeypatch, CLAUDE_STORYBOARD)
    monkeypatch.setattr(skill.requests, "post", lambda *a, **k: pytest.fail("fell back to Ollama"))
    result = await _run(store, "job_cli", storyboard_backend="claude_cli", storyboard_model="claude-sonnet-5-5")

    md = result["metadata"]
    assert md["storyboard_llm"] == "claude_cli:claude-sonnet-5-5"
    assert md["renderers"] == ["web", "web"]
    call = json.loads(log.read_text().splitlines()[0])
    argv = call["argv"]
    # tool-less, settings-less, sessionless, and the prompt never on the command line
    assert argv[:3] == ["-p", "--model", "claude-sonnet-5-5"]
    for flag in ("--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"):
        assert flag in argv
    assert argv[argv.index("--tools") + 1] == "" and argv[argv.index("--setting-sources") + 1] == ""
    assert call["stdin_len"] > 1000 and not any("Web slides E2E" in a for a in argv)
    assert "vp-storyboard-" in call["cwd"]


async def test_claude_cli_failure_falls_back_to_local_and_is_reported(store, tmp_path, monkeypatch):
    _fake_claude(tmp_path, monkeypatch, CLAUDE_STORYBOARD, exit_code=1)

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": json.dumps(CLAUDE_STORYBOARD)}

    monkeypatch.setattr(skill.requests, "post", lambda *a, **k: _Resp())
    result = await _run(store, "job_cli_fb", storyboard_backend="claude_cli", storyboard_model="claude-sonnet-5-5")
    assert result["metadata"]["storyboard_llm"] == f"ollama:{skill._OLLAMA_MODEL}"


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


async def test_frames_are_deleted_and_a_short_narration_keeps_the_full_reveal(store):
    sb = {"id": "sb_short", "scenes": [
        {"id": "s1", "kind": "title", "duration_ms": 1000, "narration_text": "Kurz.",
         "template": "stat", "data": {"value": 98765, "label": "Zahl"}},
    ]}
    result = await _run(store, "job_web_short", storyboard=sb)
    scenes = Path(result["video_path"]).parent / "scenes"
    assert not list(scenes.glob("*_frames")), "frame directories must be removed after encoding"
    audio = float(_ffprobe(scenes / "scene_001.mp3")["format"]["duration"])
    video = float(_ffprobe(Path(result["video_path"]))["format"]["duration"])
    assert video > audio + 1.0, "the clip must run until the odometer has finished, padding the audio"


async def test_llm_values_that_used_to_crash_the_job_are_dropped(store, monkeypatch):
    raw = (
        '{"id": "sb_llm2", "scenes": ['
        '{"id": "s1", "kind": "title", "duration_ms": 8000, "narration_text": "Erste Szene mit Text.",'
        ' "template": "hero", "data": {"title": "A\\ud800"}},'
        '{"id": "s2", "kind": "summary", "duration_ms": 8000, "narration_text": "Zweite Szene mit Text.",'
        ' "template": "stat", "data": {"value": 1' + "0" * 400 + ', "label": "x"}}]}'
    )
    monkeypatch.setattr(skill, "_call_storyboard_llm", lambda *a, **k: raw)
    result = await _run(store, "job_web_llm2")
    assert result["metadata"]["renderers"] == ["pillow", "pillow"]
