"""One cinematic video job: screenplay -> speech per beat -> shared timeline -> frames -> MP4 per language.

Runs inside the same job process as a slide video (``skill._orchestrate_from_config`` dispatches here when the job
config says ``mode: "cinematic"``), so it inherits everything that process gives a job: the wall-clock budget, the
cancel path, the production report and the job record the console polls.

Shared timeline (what keeps two languages identical in picture and length): a beat's slot is the longer of its
spoken lengths plus a gap; an act lasts lead + the slots + tail; the same acts, beat times and frame grid serve every
language, and only acts that carry a ``caption`` (visible text) are drawn once per language.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import shutil
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .. import deadline as dl
    from .. import report as rp
    from ..models import Scene, Storyboard, VideoOutput
    from ..storage import get_storage
except ImportError:  # standalone script use
    import deadline as dl
    import report as rp
    from models import Scene, Storyboard, VideoOutput
    from storage import get_storage

from . import direction as dr
from . import stage

logger = logging.getLogger(__name__)

LEAD_S, TAIL_S, GAP_S = 1.2, 2.0, 0.45
SPEECH_WORKERS = 4
ENCODE_DEADLINE_S = 3600.0


def _sk():
    """The slide pipeline's helpers (TTS chain, probe, job progress, report writer). Imported late: ``skill`` imports
    this package only when a cinematic job runs, so there is no import cycle."""
    try:
        from .. import skill  # noqa: PLC0415
    except ImportError:
        import skill  # noqa: PLC0415
    return skill


def _frame_count(seconds: float, fps: int) -> int:
    return max(1, round(seconds * fps))


def build_timeline(acts: List[Dict[str, Any]], durations: Dict[Tuple[int, int, str], float], langs: List[str],
                   fps: int = stage.FPS) -> Dict[str, Any]:
    """Act start/length/beat times on one frame grid, shared by every language."""
    timeline, t_global = [], 0.0
    for ai, a in enumerate(acts):
        slots = [max(durations[(ai, bi, lg)] for lg in langs) + GAP_S for bi in range(len(a["beats"]))]
        starts, t = [], LEAD_S
        for s in slots:
            starts.append(round(t, 4))
            t += s
        total = _frame_count(t + TAIL_S, fps) / fps
        timeline.append({"act": ai, "id": str(a.get("id", ai)), "start": round(t_global, 4), "dur": total,
                         "beats": starts, "slots": slots})
        t_global += total
    return {"total_s": round(t_global, 4), "fps": fps, "acts": timeline}


def _silence(w: "wave.Wave_write", seconds: float, params) -> None:
    n = max(0, int(round(seconds * params.framerate)))
    w.writeframes(b"\x00" * (n * params.sampwidth * params.nchannels))


def write_audio(path: Path, timeline: Dict[str, Any], wavs: Dict[Tuple[int, int], Path],
                durations: Dict[Tuple[int, int], float]) -> None:
    """Silence + beat speech + silence on the shared grid, one WAV per language (``wavs``/``durations`` keyed (act, beat))."""
    first = next(iter(wavs.values()))
    with wave.open(str(first)) as w0:
        params = w0.getparams()
    with wave.open(str(path), "wb") as wo:
        wo.setparams(params)
        for tl in timeline["acts"]:
            spent = tl["beats"][0]
            _silence(wo, tl["beats"][0], params)
            for bi in range(len(tl["beats"])):
                with wave.open(str(wavs[(tl["act"], bi)])) as wi:
                    wo.writeframes(wi.readframes(wi.getnframes()))
                d = durations[(tl["act"], bi)]
                _silence(wo, tl["slots"][bi] - d, params)
                spent += tl["slots"][bi]
            _silence(wo, max(0.0, tl["dur"] - spent), params)


def frame_plan(acts: List[Dict[str, Any]], timeline: Dict[str, Any], langs: List[str], frames_dir: Path,
               fmt: str) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]]]:
    """The captures to take and, per language, the ordered frame files. Acts without a caption are captured once."""
    fps = timeline["fps"]
    plan: List[Dict[str, Any]] = []
    seq: Dict[str, List[str]] = {lg: [] for lg in langs}
    for tl, a in zip(timeline["acts"], acts):
        texty = any(ac.get("type") == "caption" for ac in a["actors"]) and len(langs) > 1
        for k in range(_frame_count(tl["dur"], fps)):
            t = k / fps
            if texty:
                for lg in langs:
                    f = str(frames_dir / f"{lg}_{tl['act']:03d}_{k:05d}.{fmt}")
                    plan.append({"s": tl["act"], "t": t, "l": lg, "f": f})
                    seq[lg].append(f)
            else:
                f = str(frames_dir / f"c_{tl['act']:03d}_{k:05d}.{fmt}")
                plan.append({"s": tl["act"], "t": t, "l": langs[0], "f": f})
                for lg in langs:
                    seq[lg].append(f)
    return plan, seq


def _link_or_copy(src: str, dst: Path) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


async def _call_director(prompt: str, backend: str, model: Optional[str], info: Dict[str, Any]) -> str:
    sk = _sk()
    return await asyncio.to_thread(sk._call_storyboard_llm, prompt, backend, model, info, 32000)


async def write_screenplay(task: str, minutes: int, langs: List[str], art_names: List[str], backend: str,
                           model: Optional[str], info: Dict[str, Any]) -> Dict[str, Any]:
    """Ask the director; one repair round with every finding of the validator. Raises ``DirectionError``."""
    prompt = dr.build_prompt(task, minutes, langs, art_names)
    raw = await _call_director(prompt, backend, model, info)
    try:
        return dr.validate(raw, minutes, langs, art_names)
    except dr.DirectionError as first:
        logger.info("screenplay rejected (%d findings), one repair round", len(first.findings))
        raw2 = await _call_director(dr.repair_prompt(prompt, raw, first.findings), backend, model, info)
        try:
            doc = dr.validate(raw2, minutes, langs, art_names)
        except dr.DirectionError as second:
            raise dr.DirectionError(["after one repair round: "] + second.findings) from None
        info["repaired"] = len(first.findings)
        return doc


def _storyboard_of(job_id: str, task: str, acts: List[Dict[str, Any]], timeline: Dict[str, Any], lang: str,
                   backend_label: str) -> Storyboard:
    scenes = [Scene(id=f"act-{tl['id']}", kind="narration", duration_ms=int(tl["dur"] * 1000),
                    narration_text=" ".join(str(b.get(lang, "")) for b in a["beats"]))
              for a, tl in zip(acts, timeline["acts"])]
    return Storyboard(id=job_id, task=task, scenes=scenes, didactic_strategy="minimal_visual", llm_backend=backend_label)


async def produce_cinematic(job_id: str, task: str, config: Dict[str, Any]) -> Dict[str, Any]:
    sk = _sk()
    storage = get_storage(config["storage_base"])
    job = storage.get_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")
    if job.status in sk.TERMINAL_STATUSES:
        raise ValueError(f"Job {job_id} is already {job.status}")
    job.started_at = job.started_at or datetime.now()

    max_minutes = config.get("max_duration_minutes", 60)
    if not isinstance(max_minutes, int) or not 1 <= max_minutes <= 60:
        raise ValueError("max_duration_minutes must be an integer between 1 and 60")
    budget = dl.JobBudget(dl.job_budget_seconds(max_minutes))
    budget_token = dl.set_current_budget(budget)
    dl.register_job_budget(job_id, budget)
    backend = config.get("storyboard_backend", "claude_cli")
    tts_engine = config.get("tts_engine", sk.DEFAULT_TTS_ENGINE)
    report = rp.ProductionReport(job_id, configured_tts=tts_engine,
                                 storyboard_backend="operator" if config.get("direction") else backend, style_id=None)
    report_token = rp.set_current(report)
    report_texts: List[str] = [task]
    out_root = storage.videos_dir / job_id
    try:
        report.begin("setup")
        if tts_engine not in sk.SUPPORTED_TTS_ENGINES:
            raise ValueError(f"TTS engine {tts_engine!r} is not available (supported: {', '.join(sk.SUPPORTED_TTS_ENGINES)})")
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg binary not found on PATH - required for real video assembly")
        fps = int(config.get("cinematic_fps", stage.FPS))
        if not 12 <= fps <= 30:
            raise ValueError("cinematic_fps must be between 12 and 30")
        langs = dr.clean_langs(config.get("cinematic_langs") or [sk._detect_lang(task)])
        minutes = min(dr.clamp_minutes(config.get("cinematic_minutes", 4)), max_minutes)
        art = stage.prepare_art(config.get("cinematic_designs"))
        work = out_root / "cinematic"
        for sub in ("audio", "frames", "seq"):
            (work / sub).mkdir(parents=True, exist_ok=True)

        report.begin("storyboard")
        sk._update_job_progress(storage, job, "storyboard_generating", 0, "Writing the screenplay...")
        info: Dict[str, Any] = {}
        if config.get("direction"):
            doc = dr.validate(config["direction"], minutes, langs, list(art))
            backend_label = "operator"
        else:
            doc = await write_screenplay(task, minutes, langs, list(art), backend, config.get("storyboard_model"), info)
            backend_label = info.get("backend", backend)
        acts = doc["acts"]
        (work / "direction.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        report.storyboard_llm = backend_label
        report_texts += [str(b.get(lg, "")) for a in acts for b in a["beats"] for lg in langs]
        n_beats = sum(len(a["beats"]) for a in acts)
        budget.check("screenplay")
        sk._update_job_progress(storage, job, "storyboard_generating", 100, f"Screenplay: {len(acts)} acts, {n_beats} beats",
                                total_scenes=len(acts))

        # speech per beat and language
        report.begin("scenes")
        sk._update_job_progress(storage, job, "skills_running", 0, "Recording the narration...", total_scenes=len(acts))
        jobs = [(ai, bi, lg, str(b[lg])) for ai, a in enumerate(acts) for bi, b in enumerate(a["beats"]) for lg in langs]
        sem = asyncio.Semaphore(SPEECH_WORKERS)
        providers: List[str] = []
        done_speech = 0

        async def speak(ai: int, bi: int, lg: str, text: str) -> Tuple[Tuple[int, int, str], Path, float]:
            nonlocal done_speech
            digest = hashlib.sha256(f"{lg}|{text}".encode("utf-8")).hexdigest()[:20]
            mp3 = work / "audio" / f"{digest}.mp3"
            wav = work / "audio" / f"{digest}.wav"
            async with sem:
                budget.check("narration")
                if not mp3.exists() or mp3.stat().st_size < 200:
                    chain = (sk._synthesize_narration_chain if tts_engine == "auto" else None)
                    if chain is not None:
                        providers.append(await asyncio.to_thread(chain, text, mp3, lg))
                    elif tts_engine == "openai":
                        await asyncio.to_thread(sk._synthesize_narration_openai, text, mp3, lg)
                        providers.append("openai")
                    else:
                        await asyncio.to_thread(sk._synthesize_narration, text, mp3, lg)
                        providers.append("gtts")
                if not wav.exists():
                    await asyncio.to_thread(lambda: dl.run_process(
                        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
                         str(wav)], deadline_s=120, budget=budget, check=True, what="speech to wav"))
                d = await asyncio.to_thread(sk._ffprobe_duration, wav)
                done_speech += 1
                sk._update_job_progress(storage, job, "skills_running", int(35 * done_speech / len(jobs)),
                                        f"Narration {done_speech}/{len(jobs)}", total_scenes=len(acts))
                return (ai, bi, lg), wav, d

        tasks = [asyncio.ensure_future(speak(*j)) for j in jobs]
        try:
            results = await asyncio.gather(*tasks)
        except BaseException:
            for t in tasks:  # one failed clip ends the job: do not keep synthesising (and paying for) the rest
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        wavs = {k: p for k, p, _ in results}
        durs = {k: d for k, _, d in results}
        timeline = build_timeline(acts, durs, langs, fps)
        total_s = timeline["total_s"]
        if total_s > max_minutes * 60:
            raise ValueError(f"Narrated length {total_s:.0f}s exceeds the {max_minutes}-minute limit")
        (work / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
        for lg in langs:
            write_audio(work / f"audio-{lg}.wav", timeline, {(a, b): p for (a, b, l2), p in wavs.items() if l2 == lg},
                        {(a, b): d for (a, b, l2), d in durs.items() if l2 == lg})

        # frames
        fmt = "png" if config.get("cinematic_lossless") else "jpg"
        page_acts = [{"id": str(a.get("id", i)), "dur": tl["dur"], "beats": tl["beats"], "actors": a["actors"],
                      "tweens": a.get("tweens", [])} for i, (a, tl) in enumerate(zip(acts, timeline["acts"]))]
        page = work / "page.html"
        page.write_text(stage.build_page(page_acts, art), encoding="utf-8")
        plan, seq = frame_plan(acts, timeline, langs, work / "frames", fmt)

        def progress(done: int, total: int) -> None:
            budget.check("frames")
            sk._update_job_progress(storage, job, "skills_running", 35 + int(55 * done / total),
                                    f"Frames {done}/{total}", total_scenes=len(acts))

        sk._update_job_progress(storage, job, "skills_running", 35, f"Drawing {len(plan)} frames...", total_scenes=len(acts))
        await stage.capture_frames(page, plan, workers=min(6, os.cpu_count() or 2), fmt=fmt, on_progress=progress)

        # encode one MP4 per language
        report.begin("assemble")
        sk._update_job_progress(storage, job, "skills_running", 92, "Encoding...", total_scenes=len(acts))
        outputs: Dict[str, Path] = {}
        for i, lg in enumerate(langs):
            sdir = work / "seq" / lg
            sdir.mkdir(parents=True, exist_ok=True)
            for n, f in enumerate(seq[lg]):
                _link_or_copy(f, sdir / f"{n:06d}.{fmt}")
            dest = out_root / ("output.mp4" if i == 0 else f"output.{lg}.mp4")
            await asyncio.to_thread(lambda: dl.run_process(
                ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(sdir / f"%06d.{fmt}"),
                 "-i", str(work / f"audio-{lg}.wav"), "-t", f"{total_s}", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                 "-pix_fmt", "yuv420p", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k",
                 "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(dest)],
                deadline_s=ENCODE_DEADLINE_S, budget=budget, check=True, what=f"encode {lg}"))
            outputs[lg] = dest
        video_path = outputs[langs[0]]
        duration_seconds = round(sk._ffprobe_duration(video_path))
        spread_ms = max(abs(sk._ffprobe_duration(p) - sk._ffprobe_duration(video_path)) for p in outputs.values()) * 1000
        shutil.rmtree(work / "frames", ignore_errors=True)
        shutil.rmtree(work / "seq", ignore_errors=True)

        distinct = set(providers)
        meta = {
            "mode": "cinematic", "duration_seconds": duration_seconds, "resolution": "1920x1080", "fps": fps,
            "file_size_mb": round(video_path.stat().st_size / 1048576, 2), "scenes": len(acts), "beats": n_beats,
            "tts_engine": tts_engine, "tts_provider_used": distinct.pop() if len(distinct) == 1 else "mixed",
            "language": langs[0], "languages": langs, "language_files": {lg: p.name for lg, p in outputs.items()},
            "language_sync_diff_ms": round(spread_ms, 1), "designs": sorted(art), "screenplay_repaired": info.get("repaired", 0),
            "storyboard_llm": backend_label, "renderers": ["cinematic"],
        }
        storyboard = _storyboard_of(job_id, task, acts, timeline, langs[0], backend_label)
        job.storyboard = storyboard
        report.begin("signals")
        report.language = langs[0]
        report.media = {"duration_s": duration_seconds, "file_size_mb": meta["file_size_mb"], "scenes": len(acts)}
        report.tools = rp.tool_versions()
        report.finish("complete")
        meta["report"] = rp.REPORT_NAME if sk._write_report(report, out_root, report_texts) else None
        storage.save_video_output(VideoOutput(job_id=job_id, video_path=str(video_path), metadata=meta))
        sk.emit_feedback(job_id=job_id, event_type="video_produced",
                         metrics={"duration_seconds": duration_seconds, "resolution": "1920x1080", "quality_score": 0.85})
        job.status = "complete"
        job.completed_at = datetime.now()
        job.video_output_path = str(video_path)
        sk._update_job_progress(storage, job, "complete", 100, "Video production complete!")
        return {"success": True, "job_id": job_id, "video_path": str(video_path), "duration_seconds": duration_seconds,
                "metadata": meta}

    except dl.JobCancelled:
        report.finish("cancelled", error=dl.JobCancelled())
        sk._write_report(report, out_root, report_texts)
        job.status, job.error_message, job.completed_at = "cancelled", "Cancelled.", datetime.now()
        storage.save_job(job)
        return {"success": False, "job_id": job_id, "cancelled": True}
    except Exception as e:  # noqa: BLE001 - the stored job must end in "error", never stay "pending"
        msg = sk._scrub_secrets(str(e))[:500] if hasattr(sk, "_scrub_secrets") else str(e)[:500]
        logger.error("[%s] cinematic job failed: %s", job_id, msg, exc_info=True)
        report.finish("error", error=e)
        sk._write_report(report, out_root, report_texts)
        job.status, job.error_message, job.completed_at = "error", msg, datetime.now()
        storage.save_job(job)
        sk.emit_feedback(job_id=job_id, event_type="orchestration_failed", metrics={"error": msg})
        raise
    finally:
        dl.unregister_job_budget(job_id)
        dl.reset_current_budget(budget_token)
        rp.reset_current(report_token)
