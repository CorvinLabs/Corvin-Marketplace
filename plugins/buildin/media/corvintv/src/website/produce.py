"""One website tour job: outline -> tour -> speech -> timeline -> frames -> MP4 per language -> bundle.

Runs inside the same job process as a slide video (``skill._orchestrate_from_config`` dispatches here when the job config
says ``mode: "website"``), so it inherits the wall-clock budget, the cancel path, the production report and the job record.
Narration is spoken by ``skill._synthesize_narration_chain`` and nothing else: the CorvinOS chain (openai -> edge -> piper).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
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
    import deadline as dl  # type: ignore[no-redef]
    import report as rp  # type: ignore[no-redef]
    from models import Scene, Storyboard, VideoOutput  # type: ignore[no-redef]
    from storage import get_storage  # type: ignore[no-redef]

from . import audio as au
from . import bundle as bd
from . import effects as fx
from . import page as pg
from . import plan as pl
from . import render as rd
from . import timeline as tlm

logger = logging.getLogger(__name__)

SPEECH_WORKERS = 4
ENCODE_DEADLINE_S = 3600.0
FPS_CHOICES = (24, 30, 60)
PROVIDER_NAME = {"openai": "OpenAI", "edge": "Microsoft Edge", "piper": "Piper", "mock": "test"}
DISCLOSURE = {"en": "Narration voice: AI-generated ({p} text-to-speech)", "de": "Sprecherstimme: KI-generiert ({p} Text-to-Speech)"}


def _sk():
    """The slide pipeline's helpers (TTS chain, job progress, report writer); imported late, no import cycle."""
    try:
        from .. import skill  # noqa: PLC0415
    except ImportError:
        import skill  # noqa: PLC0415
    return skill


def _link_or_copy(src: Path, dst: Path) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def clean_langs(raw: Any, fallback: str) -> List[str]:
    out: List[str] = []
    for lg in (raw if isinstance(raw, list) else [fallback]):
        if lg in pl.LANGS and lg not in out:
            out.append(lg)
    if not out:
        out = [fallback if fallback in pl.LANGS else "en"]
    return out[:2]


async def write_tour(brief: str, outline: Dict[str, Any], langs: List[str], minutes: int, backend: str, model: Optional[str],
                     info: Dict[str, Any]) -> Dict[str, Any]:
    """Ask the native Claude Code engine; one repair round with every finding. Raises ``pl.TourError``."""
    sk = _sk()
    keys = {e["key"] for e in outline["entries"]}
    page_text = " ".join(e["text"] + " " + e["heading"] for e in outline["entries"])
    prompt = pl.build_prompt(brief, outline["entries"], langs, minutes)

    async def call(p: str) -> Optional[Dict[str, Any]]:
        raw = await asyncio.to_thread(sk._call_storyboard_llm, p, backend, model, info, 32000)
        info["raw"] = raw
        return sk._parse_storyboard_json(raw)

    doc = await call(prompt)
    try:
        return pl.validate_tour(doc, keys, langs, page_text)
    except pl.TourError as first:
        logger.info("tour rejected (%d findings), one repair round", len(first.findings))
        doc2 = await call(pl.repair_prompt(prompt, json.dumps(doc, ensure_ascii=False) if doc else info.get("raw", ""), first.findings))
        try:
            tour = pl.validate_tour(doc2, keys, langs, page_text)
        except pl.TourError as second:
            raise pl.TourError(["after one repair round: "] + second.findings) from None
        info["repaired"] = len(first.findings)
        return tour


def _storyboard_of(job_id: str, task: str, tour: Dict[str, Any], tl: Dict[str, Any], lang: str, backend_label: str) -> Storyboard:
    scenes = [Scene(id=f"tour-{s['id']}", kind="narration", duration_ms=int(t["dur"] * 1000),
                    narration_text=" ".join(x["text"].get(lang, "") for x in s["sentences"]))
              for s, t in zip(tour["scenes"], tl["scenes"])]
    return Storyboard(id=job_id, task=task, scenes=scenes, didactic_strategy="minimal_visual", llm_backend=backend_label)


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


async def produce_website(job_id: str, task: str, config: Dict[str, Any]) -> Dict[str, Any]:
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
    backend = config.get("storyboard_backend") or sk.STORYBOARD_BACKEND
    tts_engine = config.get("tts_engine", sk.DEFAULT_TTS_ENGINE)
    report = rp.ProductionReport(job_id, configured_tts=tts_engine if tts_engine in sk.SUPPORTED_TTS_ENGINES else str(tts_engine),
                                 storyboard_backend="operator" if config.get("tour") else backend, style_id=None)
    report_token = rp.set_current(report)
    report_texts: List[str] = [task]
    out_root = storage.videos_dir / job_id
    source: Optional[pg.Source] = None
    try:
        report.begin("setup")
        tts_engine = sk._normalise_tts_engine(tts_engine)
        report.configured_tts = tts_engine
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg binary not found on PATH - required for real video assembly")
        chrome = await asyncio.to_thread(sk.host_env.ensure_chromium_cached)
        if not chrome["ok"]:
            raise RuntimeError(sk.host_env.describe(chrome))
        fps = int(config.get("website_fps", 30))
        if fps not in FPS_CHOICES:
            raise ValueError("website_fps must be 24, 30 or 60")
        langs = clean_langs(config.get("website_langs"), sk._detect_lang(task))
        minutes = max(1, min(int(config.get("website_minutes", 4)), 15, max_minutes))
        effects = fx.clean_effects(config.get("website_effects"))
        work = out_root / "website"
        for sub in ("audio", "frames/shared", "seq"):
            (work / sub).mkdir(parents=True, exist_ok=True)
        for lg in langs:
            (work / "frames" / lg).mkdir(parents=True, exist_ok=True)

        report.begin("storyboard")
        sk._update_job_progress(storage, job, "storyboard_generating", 0, "Opening the page...")
        try:
            source = pg.open_source(config, pl.extract_url(task))
            outline = await pg.outline_for(source)
        except pg.SiteError as e:
            raise ValueError(str(e)) from None
        budget.check("outline")
        info: Dict[str, Any] = {}
        keys = {e["key"] for e in outline["entries"]}
        page_text = " ".join(e["text"] + " " + e["heading"] for e in outline["entries"])
        if config.get("tour"):
            try:
                tour = pl.validate_tour(config["tour"], keys, langs, page_text, check_facts=False)
            except pl.TourError as e:
                raise ValueError("the tour is not valid: " + str(e)) from None
            backend_label, tour_source = "operator", "operator"
        else:
            sk._update_job_progress(storage, job, "storyboard_generating", 30, "Writing the tour...")
            brief = pl.strip_url(task)[:2000] or "Explain what this page offers, step by step."
            tour = await write_tour(brief, outline, langs, minutes, backend, config.get("storyboard_model"), info)
            backend_label, tour_source = info.get("backend", backend), "model"
        report.storyboard_llm = backend_label
        n_scenes = len(tour["scenes"])
        report_texts += [t for s in tour["scenes"] for x in s["sentences"] for t in x["text"].values()]
        (work / "tour.json").write_text(pl.to_json(tour), encoding="utf-8")
        sk._update_job_progress(storage, job, "storyboard_generating", 100, f"Tour: {n_scenes} scenes", total_scenes=n_scenes)

        # speech: one clip per sentence and language, through the CorvinOS chain
        report.begin("scenes")
        sk._update_job_progress(storage, job, "skills_running", 0, "Recording the narration...", total_scenes=n_scenes)
        jobs = [(i, k, lg, s["text"][lg]) for i, sc in enumerate(tour["scenes"]) for k, s in enumerate(sc["sentences"]) for lg in tour["langs"]]
        sem = asyncio.Semaphore(SPEECH_WORKERS)
        providers: List[str] = []
        done_speech = 0

        async def speak(i: int, k: int, lg: str, text: str) -> Tuple[Tuple[int, int, str], Path, float]:
            nonlocal done_speech
            digest = hashlib.sha256(f"{lg}|{text}".encode("utf-8")).hexdigest()[:20]
            mp3, wav = work / "audio" / f"{digest}.mp3", work / "audio" / f"{digest}.wav"
            async with sem:
                budget.check("narration")
                if not mp3.exists() or mp3.stat().st_size < 200:
                    providers.append(await asyncio.to_thread(sk._synthesize_narration_chain, text, mp3, lg))
                if not wav.exists():
                    await asyncio.to_thread(lambda: dl.run_process(
                        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ar", str(au.RATE), "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
                        deadline_s=120, budget=budget, check=True, what="speech to wav"))
                done_speech += 1
                sk._update_job_progress(storage, job, "skills_running", int(30 * done_speech / len(jobs)),
                                        f"Narration {done_speech}/{len(jobs)}", total_scenes=n_scenes)
                return (i, k, lg), wav, _wav_seconds(wav)

        futs = [asyncio.ensure_future(speak(*j)) for j in jobs]
        try:
            results = await asyncio.gather(*futs)
        except BaseException:
            for t in futs:
                t.cancel()
            await asyncio.gather(*futs, return_exceptions=True)
            raise
        wavs = {key: p for key, p, _ in results}
        durs = {key: d for key, _, d in results}
        tl = tlm.build(tour["scenes"], durs, tour["langs"], fps)
        total_s = tl["total_s"]
        if total_s > max_minutes * 60:
            raise ValueError(f"Narrated length {total_s:.0f}s exceeds the {max_minutes}-minute limit")
        (work / "timeline.json").write_text(json.dumps(tl), encoding="utf-8")
        for lg in tour["langs"]:
            au.mix(work / f"audio-{lg}.wav", total_s, [(tl["scenes"][i]["sentences"][k]["at"][lg], wavs[(i, k, lg)])
                                                       for i, sc in enumerate(tour["scenes"]) for k in range(len(sc["sentences"]))])
        distinct = set(providers)
        provider = distinct.pop() if len(distinct) == 1 else ("mixed" if distinct else "unknown")
        p_name = PROVIDER_NAME.get(provider, "various")

        # the frame model and the frame plan
        model = rd.FrameModel(tour, tl, outline, effects)
        intro_texts = {lg: [tour["intro"][lg][0], tour["intro"][lg][1], "", ""] for lg in tour["langs"]}
        outro_texts = {lg: [tour["outro"][lg]["line"], tour["outro"][lg]["sub"], tour.get("outro_url", ""), DISCLOSURE[lg].format(p=p_name)]
                       for lg in tour["langs"]}
        plan: List[Dict[str, Any]] = []
        for f in range(model.frame_count()):
            T = f / fps
            if model.is_language_frame(T):
                for lg in tour["langs"]:
                    plan.append({"f": f, "texts": intro_texts[lg] if T < model.intro["end"] else outro_texts[lg],
                                 "path": work / "frames" / lg / f"{f:06d}.jpg"})
            else:
                plan.append({"f": f, "texts": None, "path": work / "frames" / "shared" / f"{f:06d}.jpg"})
        sk._update_job_progress(storage, job, "skills_running", 30, f"Drawing {len(plan)} frames...", total_scenes=n_scenes)

        def progress(done: int, total: int) -> None:
            budget.check("frames")
            sk._update_job_progress(storage, job, "skills_running", 30 + int(60 * done / total), f"Frames {done}/{total}", total_scenes=n_scenes)

        draw = await rd.draw_frames(source, model, plan, workers=min(6, max(1, (os.cpu_count() or 2) // 2)), on_progress=progress,
                                    page_height=outline["page_height"])

        # encode one MP4 per language
        report.begin("assemble")
        sk._update_job_progress(storage, job, "skills_running", 92, "Encoding...", total_scenes=n_scenes)
        outputs: Dict[str, Path] = {}
        for idx, lg in enumerate(tour["langs"]):
            sdir = work / "seq" / lg
            sdir.mkdir(parents=True, exist_ok=True)
            for f in range(model.frame_count()):
                shared = work / "frames" / "shared" / f"{f:06d}.jpg"
                _link_or_copy(shared if shared.exists() else work / "frames" / lg / f"{f:06d}.jpg", sdir / f"{f:06d}.jpg")
            dest = out_root / ("output.mp4" if idx == 0 else f"output.{lg}.mp4")
            await asyncio.to_thread(lambda: dl.run_process(
                ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(sdir / "%06d.jpg"), "-i", str(work / f"audio-{lg}.wav"),
                 "-t", f"{total_s}", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                 "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                 "-movflags", "+faststart", str(dest)], deadline_s=ENCODE_DEADLINE_S, budget=budget, check=True, what=f"encode {lg}"))
            outputs[lg] = dest
        video_path = outputs[tour["langs"][0]]
        duration_seconds = round(sk._ffprobe_duration(video_path))
        spread_ms = max(abs(sk._ffprobe_duration(p) - sk._ffprobe_duration(video_path)) for p in outputs.values()) * 1000

        # the bundle: a page to put online
        site = out_root / "site"
        site.mkdir(parents=True, exist_ok=True)
        videos = {}
        for lg, p in outputs.items():
            _link_or_copy(p, site / f"video.{lg}.mp4")
            videos[lg] = f"video.{lg}.mp4"
        pf = max(0, min(model.frame_count() - 1, int((tl["scenes"][min(1, n_scenes - 1)]["start"] + 0.45 * tl["scenes"][min(1, n_scenes - 1)]["dur"]) * fps)))
        pframe = work / "frames" / "shared" / f"{pf:06d}.jpg"
        if not pframe.exists():
            pframe = work / "frames" / tour["langs"][0] / f"{pf:06d}.jpg"
        _poster(pframe, site / "poster.jpg")
        chapters = [{"start": t["start"], "end": t["start"] + t["dur"], "title": (outline["entries"] and next(
            (e["heading"] for e in outline["entries"] if e["key"] == s["target"] and e["heading"]), "")) or f"{i + 1}"}
            for i, (s, t) in enumerate(zip(tour["scenes"], tl["scenes"]))]
        transcript: Dict[str, List[str]] = {}
        for lg in tour["langs"]:
            (site / f"chapters.{lg}.vtt").write_text(bd.chapters_vtt(chapters), encoding="utf-8")
            cues = [{"at": t["sentences"][k]["at"][lg], "dur": t["sentences"][k]["dur"][lg], "text": s["text"][lg]}
                    for s, t in zip(tour["scenes"], tl["scenes"]) for k, s in enumerate(s["sentences"])]
            (site / f"captions.{lg}.vtt").write_text(bd.captions_vtt(cues), encoding="utf-8")
            transcript[lg] = [c["text"] for c in cues]
        first_text = tour["scenes"][0]["sentences"][0]["text"][tour["langs"][0]]
        title = outline.get("title") or pl.strip_url(task)[:80] or "Website tour"
        bd.build_site(site, title=title, description=first_text[:200], langs=tour["langs"], videos=videos, chapters=chapters,
                      transcript=transcript, disclosure={lg: DISCLOSURE[lg].format(p=p_name) for lg in tour["langs"]},
                      source_url=source.url if source.kind == "url" else "")
        (site / "README.txt").write_text(bd.README, encoding="utf-8")
        bd.write_zip(site, out_root / "website-bundle.zip")
        shutil.rmtree(work / "frames", ignore_errors=True)
        shutil.rmtree(work / "seq", ignore_errors=True)

        cam_report = model.report()
        meta = {
            "mode": "website", "duration_seconds": duration_seconds, "resolution": "1920x1080", "fps": fps,
            "file_size_mb": round(video_path.stat().st_size / 1048576, 2), "scenes": n_scenes,
            "tts_engine": tts_engine, "tts_chain": "corvinos", "tts_provider_used": provider,
            "language": tour["langs"][0], "languages": tour["langs"], "language_files": {lg: p.name for lg, p in outputs.items()},
            "language_sync_diff_ms": round(spread_ms, 1), "site_dir": "site", "bundle": "website-bundle.zip",
            "camera": cam_report, "effects": effects, "source": source.summary(), "tour_source": tour_source,
            "tour_repaired": info.get("repaired", 0), "layout_drift_px": draw["layout_drift_px"],
            "storyboard_llm": backend_label, "renderers": ["website"],
        }
        job.storyboard = _storyboard_of(job_id, task, tour, tl, tour["langs"][0], backend_label)
        report.begin("signals")
        report.language = tour["langs"][0]
        report.media = {"duration_s": duration_seconds, "file_size_mb": meta["file_size_mb"], "scenes": n_scenes,
                        "camera": cam_report, "effects": effects, "blocked_requests": source.blocked}
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
        return {"success": True, "job_id": job_id, "video_path": str(video_path), "duration_seconds": duration_seconds, "metadata": meta}

    except dl.JobCancelled:
        report.finish("cancelled", error=dl.JobCancelled())
        sk._write_report(report, out_root, report_texts)
        job.status, job.error_message, job.completed_at = "cancelled", "Cancelled.", datetime.now()
        storage.save_job(job)
        return {"success": False, "job_id": job_id, "cancelled": True}
    except Exception as e:  # noqa: BLE001 - the stored job must end in "error", never stay "pending"
        msg = sk._scrub_secrets(str(e))[:500] if hasattr(sk, "_scrub_secrets") else str(e)[:500]
        logger.error("[%s] website tour failed: %s", job_id, msg, exc_info=True)
        report.finish("error", error=e)
        sk._write_report(report, out_root, report_texts)
        job.status, job.error_message, job.completed_at = "error", msg, datetime.now()
        storage.save_job(job)
        sk.emit_feedback(job_id=job_id, event_type="orchestration_failed", metrics={"error": msg})
        raise
    finally:
        if source is not None:
            source.close()
        dl.unregister_job_budget(job_id)
        dl.reset_current_budget(budget_token)
        rp.reset_current(report_token)


def _poster(src: Path, dst: Path) -> None:
    from PIL import Image  # noqa: PLC0415

    im = Image.open(src).convert("RGB")
    im.thumbnail((1280, 720))
    im.save(dst, "JPEG", quality=88)
