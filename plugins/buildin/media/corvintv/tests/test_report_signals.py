"""Production Report + signals engine (ADR-2247, PLAN-0946 R2a, T-0089).

Every signal that can gate has a POSITIVE CONTROL here: a deliberately broken input that makes it
fail (a kept collision, a grounded task without its claim check, a clip cut short, a Pillow scene, a
wrong accent / a Corvin mark). ``plan_estimate_error`` and ``beats_provenance`` are information by
definition (ADR-2247 table: "none" / shown) and are checked to never fail. Media fixtures are real
ffmpeg output, not mocks."""
import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src import report as rp
from src import signals as sg

FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg/ffprobe not installed")


# ── report ────────────────────────────────────────────────────────────────────────────────────

def test_report_round_trip_schema_and_size(tmp_path):
    r = rp.ProductionReport("job_abc", configured_tts="auto", storyboard_backend="claude_cli")
    r.begin("setup")
    r.begin("storyboard")
    r.note_llm_usage({"input_tokens": 1200, "output_tokens": 800, "cache_read_input_tokens": 5})
    r.note_llm_usage(None)
    r.begin("scenes")
    r.scene(1, tts_tier="openai", audio_s=3.21, renderer="web", template="hero")
    r.note_degradation("web_to_pillow", scene=1, reason="WebRenderError: some path /home/x")
    r.finish("complete")
    path = r.write(tmp_path)
    data = rp.read(tmp_path)
    assert path.name == "report.json" and data["schema"] == 1 and data["status"] == "complete"
    assert [s["name"] for s in data["stages"]] == ["setup", "storyboard", "scenes"]
    assert all(isinstance(s["seconds"], float) for s in data["stages"])
    assert data["llm_usage"] == {"calls": 2, "calls_without_usage": 1, "input_tokens": 1200,
                                 "output_tokens": 800, "cache_read_tokens": 5, "cache_write_tokens": 0}
    # a reason keeps the class only: no path, no message
    assert data["degradations"] == [{"kind": "web_to_pillow", "scene": 1, "reason": "WebRenderError"}]
    assert data["degraded_scenes"] == {"n": 1, "of": 1, "indexes": [1]}
    assert path.stat().st_size <= rp.MAX_REPORT_BYTES


def test_report_refuses_task_or_narration_text(tmp_path):
    task = "Erklaere in zwei Minuten, wie die geheime Kundenliste von ACME verarbeitet wird."
    r = rp.ProductionReport("job_t")
    r.finish("complete")
    r.write(tmp_path, forbidden_texts=[task])  # clean: written
    r.style_id = "Erklaere in zwei Minuten"  # a short token, below the window: allowed by the builder
    r.media = {"note": task[:40]}  # 40 chars of the task smuggled in
    with pytest.raises(rp.ReportError, match="task or narration"):
        r.write(tmp_path, forbidden_texts=[task])


def test_report_refuses_prose_identifiers_and_unknown_vocabulary():
    r = rp.ProductionReport("job_v")
    with pytest.raises(rp.ReportError):
        r.scene(1, template="a sentence, with punctuation; and more!")
    with pytest.raises(rp.ReportError):
        r.note_degradation("something_new", scene=1)
    with pytest.raises(rp.ReportError):
        r.note_degradation("web_to_pillow")  # a scene kind needs its scene
    with pytest.raises(rp.ReportError):
        r.finish("done")


def test_report_size_cap():
    r = rp.ProductionReport("job_big")
    for i in range(3000):
        r.scene(i, tts_tier="openai", audio_s=1.0, renderer="web", template="hero")
    r.finish("complete")
    with pytest.raises(rp.ReportError, match="exceeds"):
        rp.validate(r.to_dict())


def test_note_degradation_reaches_the_running_jobs_report_and_is_a_no_op_outside():
    rp.note_degradation("grounding_lost", reason="x")  # no job: nothing happens, nothing raises
    rep = rp.ProductionReport("job_ctx")
    tok = rp.set_current(rep)
    try:
        rp.note_degradation("storyboard_backend_fallback", source="claude_cli", target="anthropic")
        rp.note_llm_usage({"input_tokens": 3, "output_tokens": 4})
    finally:
        rp.reset_current(tok)
    rp.note_degradation("grounding_lost", reason="after")  # gone again
    assert rep.degradations == [{"kind": "storyboard_backend_fallback", "from": "claude_cli", "to": "anthropic"}]
    assert rep.llm_usage["input_tokens"] == 3


def test_a_failed_job_writes_its_report_naming_the_failed_stage(tmp_path):
    """The real orchestrator, failing in setup (an unsupported TTS engine): the report exists, says
    ``error`` / ``setup`` / the exception class, and carries no task text."""
    from src import skill
    from src.models import VideoJob
    from src.storage import get_storage, reset_storage

    reset_storage()
    base = tmp_path / "tenant"
    base.mkdir()
    task = "Ein sehr geheimer Auftragstext, der niemals im Report stehen darf, auch nicht in Teilen."
    get_storage(str(base)).save_job(VideoJob(id="job_fail", task=task))
    with pytest.raises(ValueError):
        asyncio.run(skill.orchestrate_video("job_fail", task, str(base), tts_engine="no_such_engine"))
    data = rp.read(base / "videos" / "job_fail")
    assert data is not None, "a failed job must leave a report"
    assert (data["status"], data["failed_stage"], data["error_class"]) == ("error", "setup", "ValueError")
    assert "geheim" not in json.dumps(data)
    assert get_storage(str(base)).get_job("job_fail").status == "error"
    reset_storage()


# ── engine ────────────────────────────────────────────────────────────────────────────────────

def _ctx(tmp_path, scenes, degradations=(), **kw):
    report = {"scenes": scenes, "degradations": list(degradations)}
    return sg.SignalContext(job_dir=tmp_path, report=report, **kw)


WEB2 = [{"index": 1, "renderer": "web", "audio_s": 3.0}, {"index": 2, "renderer": "web", "audio_s": 4.0}]


def test_degradation_rate_pass_and_positive_control_pillow_fails():
    ok = sg._degradation_rate(_ctx(Path("."), WEB2))
    assert ok.verdict == "pass" and (ok.n, ok.of) == (0, 2)
    bad = sg._degradation_rate(_ctx(Path("."), WEB2, [{"kind": "web_to_pillow", "scene": 2}]))
    assert bad.verdict == "fail" and "pillow fallback" in bad.reason and (bad.n, bad.of) == (1, 2)
    lost = sg._degradation_rate(_ctx(Path("."), WEB2, [{"kind": "grounding_lost"}]))
    assert lost.verdict == "fail" and "grounding lost" in lost.reason  # a job-level degradation alone fails it


def test_a_failing_degradation_rate_invalidates_the_gated_signals(tmp_path):
    """ADR-2247: the other signals are only valid when degradation_rate passes."""
    ctx = _ctx(tmp_path, WEB2, [{"kind": "tts_tier_below", "scene": 1, "tier": "mock"}],
               metadata={"layout_collisions": []}, plan_ms=[3000, 4000])
    recs = {r["id"]: r for r in sg.run(ctx, only=["degradation_rate", "layout_clean", "plan_estimate_error"])}
    assert recs["degradation_rate"]["verdict"] == "fail" and recs["degradation_rate"]["valid"] is True
    assert recs["layout_clean"]["verdict"] == "pass"
    assert recs["layout_clean"]["valid"] is False and recs["layout_clean"]["invalidated_by"] == "degradation_rate"
    assert recs["plan_estimate_error"]["valid"] is True  # information is not gated
    # control: without the degradation, the same layout_clean is valid
    clean = {r["id"]: r for r in sg.run(_ctx(tmp_path, WEB2, metadata={"layout_collisions": []}),
                                        only=["degradation_rate", "layout_clean"])}
    assert clean["layout_clean"]["valid"] is True


def test_layout_clean_positive_control_kept_collision_fails():
    meta = {"layout_collisions": [{"scene": 1, "action": "replaced_with_content"}]}
    assert sg._layout_clean(_ctx(Path("."), WEB2, metadata=meta)).verdict == "pass"
    meta["layout_collisions"].append({"scene": 2, "action": "kept"})
    v = sg._layout_clean(_ctx(Path("."), WEB2, metadata=meta))
    assert v.verdict == "fail" and v.value == 1 and (v.n, v.of) == (1, 2)


def test_fact_support_positive_controls():
    grounded = {"status": "grounded", "unverified": {"count": 0, "scenes": []}}
    assert sg._fact_support(_ctx(Path("."), WEB2, grounding_requested=False)).verdict == "skip"
    assert sg._fact_support(_ctx(Path("."), WEB2, metadata={"grounding": grounded},
                                 grounding_requested=True)).verdict == "pass"
    unsup = {"status": "grounded_with_unverified", "unverified": {"count": 2, "scenes": ["s2"]}}
    v = sg._fact_support(_ctx(Path("."), WEB2, metadata={"grounding": unsup}, grounding_requested=True))
    assert v.verdict == "warn" and v.value == 2  # ADR-2247: "warn on the job"
    # a grounded task whose claim check never ran is a FAIL, not a skip and not a pass
    lost = sg._fact_support(_ctx(Path("."), WEB2, metadata={"grounding": {"status": "unavailable"}},
                                 grounding_requested=True))
    assert lost.verdict == "fail"
    none = sg._fact_support(_ctx(Path("."), WEB2, metadata={}, grounding_requested=True))
    assert none.verdict == "fail"


def test_information_signals_never_fail():
    v = sg._plan_estimate_error(_ctx(Path("."), WEB2, plan_ms=[1000, 1000]))
    assert v.verdict == "info" and v.value == 2.5  # 7 s narrated vs 2 s planned
    cues = [{"beats_source": "fallback"}, {"beats_source": "narration"}]
    b = sg._beats_provenance(_ctx(Path("."), WEB2, metadata={"cues": cues}))
    assert b.verdict == "info" and (b.n, b.of) == (1, 2)


def test_an_instrument_error_is_a_skip_never_a_pass(tmp_path):
    @sg.register("boom_probe")
    def _boom(ctx):
        raise RuntimeError("instrument broke")
    try:
        rec = sg.run(_ctx(tmp_path, WEB2), only=["boom_probe"])[0]
        assert rec["verdict"] == "skip" and rec["reason"] == "instrument error: RuntimeError"
    finally:
        sg.unregister("boom_probe")


def test_a_later_template_registers_its_own_signal_without_engine_change(tmp_path):
    """1.6.0 needs canvas_clean / canvas_authoring: they register against the template and the engine
    runs them only where that template is in the video."""
    calls = []

    @sg.register("canvas_clean_probe", unit="strokes off-grid", templates={"canvas"})
    def _canvas_clean(ctx):
        calls.append(1)
        return sg.SignalValue(0, "pass", n=1, of=1, threshold=0)
    try:
        assert any(s.id == "canvas_clean_probe" for s in sg.registered("runtime"))
        without = sg.run(_ctx(tmp_path, WEB2, templates={"hero"}), only=["canvas_clean_probe"])[0]
        assert without["verdict"] == "skip" and calls == []
        with_ = sg.run(_ctx(tmp_path, WEB2, templates={"hero", "canvas"}), only=["canvas_clean_probe"])[0]
        assert with_["verdict"] == "pass" and calls == [1] and with_["unit"] == "strokes off-grid"
        with pytest.raises(ValueError):  # no silent overwrite of a name
            sg.register("canvas_clean_probe")(lambda c: None)
    finally:
        sg.unregister("canvas_clean_probe")


def test_posthoc_signals_do_not_run_at_the_end_of_a_job(tmp_path):
    @sg.register("expensive_probe", kind="posthoc")
    def _exp(ctx):
        return sg.SignalValue(1, "pass")
    try:
        assert "expensive_probe" not in {r["id"] for r in sg.run(_ctx(tmp_path, WEB2))}
        assert sg.run(_ctx(tmp_path, WEB2), kind="posthoc", only=["expensive_probe"])[0]["verdict"] == "pass"
    finally:
        sg.unregister("expensive_probe")


# ── media signals over real ffmpeg output ─────────────────────────────────────────────────────

def _ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True, timeout=60)


def _clip(path, seconds, colour="0x3ba3ff", box=None):
    vf = f"color=c={colour}:s=320x180:d={seconds}:r=12"
    if box:
        vf += f",drawbox=x=0:y=0:w=120:h=120:color={box}@1:t=fill"
    _ff("-f", "lavfi", "-i", vf, "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path))


def _voice(path, seconds):
    _ff("-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}", "-c:a", "libmp3lame", str(path))


def _job(tmp_path, clip_s, voice_s=2.0, **clipkw):
    d = tmp_path / "job"
    (d / "scenes").mkdir(parents=True)
    _voice(d / "scenes" / "scene_001.mp3", voice_s)
    _clip(d / "scenes" / "scene_001.mp4", clip_s, **clipkw)
    shutil.copyfile(d / "scenes" / "scene_001.mp4", d / "output.mp4")
    return d


@needs_ffmpeg
def test_mux_integrity_passes_and_positive_control_cut_clip_fails(tmp_path):
    good = _job(tmp_path / "a", clip_s=2.0)
    v = sg._mux_integrity(_ctx(good, [{"index": 1}]))
    assert v.verdict == "pass", v.detail
    cut = _job(tmp_path / "b", clip_s=1.0)  # the clip is a second shorter than its narration
    v = sg._mux_integrity(_ctx(cut, [{"index": 1}]))
    assert v.verdict == "fail" and v.detail["problems"][0]["why"] == "clip shorter than voice"
    (cut / "scenes" / "scene_001.mp3").unlink()
    assert sg._mux_integrity(_ctx(cut, [{"index": 1}])).detail["problems"][0]["why"] == "missing"


@needs_ffmpeg
def test_style_fidelity_passes_and_positive_controls_fail(tmp_path):
    scenes = [{"index": 1, "renderer": "web"}]
    ok = _job(tmp_path / "a", 2.0, colour="0x3ba3ff")
    v = sg._style_fidelity(_ctx(ok, scenes, style_accent="#3ba3ff"))
    assert v.verdict == "pass" and v.value <= sg.STYLE_DELTA_E_MAX, v
    wrong = _job(tmp_path / "b", 2.0, colour="0xff3b3b")  # the accent never appears
    assert sg._style_fidelity(_ctx(wrong, scenes, style_accent="#3ba3ff")).verdict == "fail"
    marked = _job(tmp_path / "c", 2.0, colour="0x3ba3ff", box="0xe8a83a")  # Corvin's amber in a custom style
    v = sg._style_fidelity(_ctx(marked, scenes, style_accent="#3ba3ff"))
    assert v.verdict == "fail" and v.detail["corvin_mark_frames"] > 0
    assert sg._style_fidelity(_ctx(ok, scenes, style_accent=None)).verdict == "skip"
