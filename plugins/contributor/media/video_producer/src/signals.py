"""Named quality signals over one finished job (ADR-2247 "Signals", PLAN-0946 R2).

A signal is a pure function ``fn(ctx) -> SignalValue`` registered under a name. The engine turns it
into one record ``{id, value, unit, threshold, verdict, basis: {n, of}, valid, ...}`` and stores the
list in the job's ``report.json``. Verdicts: ``pass | warn | fail | skip | info``. ``skip`` is a
signal that could not be measured (its reason is given) - the ready-gate counts it as a miss, never
as a pass. ``info`` is a number the ADR shows but never gates on (``plan_estimate_error``,
``beats_provenance``).

``degradation_rate`` gates the others: when it fails, every signal registered ``gated=True`` keeps
its value and verdict but is marked ``valid: false, invalidated_by: degradation_rate`` - a degraded
scene (a Pillow slide, a quote in place of a diagram) would otherwise flatter them (ADR-2247).

Extension: a template module registers its own signals with ``register(..., templates={"canvas"})``.
Such a signal only runs when one of those templates is in the video and is ``skip`` otherwise, so a
later template (e.g. ADR-2249's ``canvas_clean`` / ``canvas_authoring``) needs no change here.
``kind="posthoc"`` signals (an external service, expensive) are not run at the end of a job; they
run on demand through ``run(..., kind="posthoc")`` and are merged into the same report.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set

try:
    from . import deadline as dl
except ImportError:  # pragma: no cover - script use
    import deadline as dl

VERDICTS = ("pass", "warn", "fail", "skip", "info")
KINDS = ("runtime", "posthoc")
GATE = "degradation_rate"
_FFPROBE_S = 30.0
_FFMPEG_FRAME_S = 60.0
CLIP_TOLERANCE_S = 0.1     # one encoder frame at 30 fps is 0.033 s; a clip shorter than its voice by more is cut
AV_TOLERANCE = 0.03        # final audio vs final video length (ADR-2247 mux_integrity, +-3 %)
DEGRADED_SCENE_MAX = 0.10  # ADR-2247 degradation_rate gate
STYLE_DELTA_E_MAX = 3.0    # ADR-2247 style_fidelity gate
CORVIN_MARKS = ("#e8a83a", "#c9a227")  # Corvin's accent and its gold dot


@dataclass
class SignalContext:
    """Everything a runtime signal may read about one job. Built by the orchestrator; a signal never
    reaches outside it (no store, no network)."""
    job_dir: Path
    report: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    plan_ms: List[int] = field(default_factory=list)
    grounding_requested: bool = False
    style_accent: Optional[str] = None       # "#rrggbb" of the theme the video used; None = no custom style
    templates: Set[str] = field(default_factory=set)
    # storyboard per scene: template, narration_text, beats, data - read by signals, never stored
    storyboard_scenes: List[Dict[str, Any]] = field(default_factory=list)
    narrations: List[str] = field(default_factory=list)
    base_narrations: Optional[List[str]] = None      # a revision's base video; None = not a revision
    transcribe: Optional[Callable[[Path], List[Dict[str, Any]]]] = None  # post-hoc only (whisper-1)

    @property
    def scenes(self) -> List[Dict[str, Any]]:
        return list(self.report.get("scenes") or [])


@dataclass
class SignalValue:
    value: Any
    verdict: str
    n: Optional[int] = None
    of: Optional[int] = None
    threshold: Any = None
    reason: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class SignalSpec:
    id: str
    fn: Callable[[SignalContext], SignalValue]
    unit: str
    kind: str = "runtime"
    templates: Optional[frozenset] = None
    gated: bool = True
    description: str = ""


_REGISTRY: Dict[str, SignalSpec] = {}


def register(signal_id: str, *, unit: str = "", kind: str = "runtime", templates: Optional[Iterable[str]] = None,
             gated: bool = True, description: str = "", replace: bool = False):
    """Decorator: add a signal to the registry. ``templates``: run only when one of them is in the
    video (else ``skip``). ``gated``: invalidated when ``degradation_rate`` fails."""
    if kind not in KINDS:
        raise ValueError(f"unknown signal kind {kind!r}")
    if not signal_id or not signal_id.replace("_", "").isalnum():
        raise ValueError("a signal id is a snake_case name")

    def deco(fn: Callable[[SignalContext], SignalValue]):
        if signal_id in _REGISTRY and not replace:
            raise ValueError(f"signal {signal_id!r} is already registered")
        _REGISTRY[signal_id] = SignalSpec(signal_id, fn, unit, kind, frozenset(templates) if templates else None,
                                          gated and signal_id != GATE, description)
        return fn
    return deco


def unregister(signal_id: str) -> None:
    _REGISTRY.pop(signal_id, None)


def registered(kind: Optional[str] = None) -> List[SignalSpec]:
    return [s for s in _REGISTRY.values() if kind is None or s.kind == kind]


def _record(spec: SignalSpec, v: SignalValue) -> Dict[str, Any]:
    if v.verdict not in VERDICTS:
        raise ValueError(f"signal {spec.id} returned verdict {v.verdict!r}")
    rec: Dict[str, Any] = {"id": spec.id, "kind": spec.kind, "value": v.value, "unit": spec.unit,
                           "threshold": v.threshold, "verdict": v.verdict,
                           "basis": {"n": v.n, "of": v.of}, "valid": True}
    if v.reason:
        rec["reason"] = str(v.reason)[:80]
    if v.detail:
        rec["detail"] = v.detail
    return rec


def run(ctx: SignalContext, *, kind: str = "runtime", only: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """Evaluate every registered signal of ``kind`` (or ``only`` these ids). A signal that raises is
    recorded as ``skip`` with the exception class - an instrument fault never passes and never fails
    the job."""
    out: List[Dict[str, Any]] = []
    for spec in registered(kind):
        if only is not None and spec.id not in only:
            continue
        if spec.templates is not None and not (spec.templates & ctx.templates):
            out.append(_record(spec, SignalValue(None, "skip", reason="template not in this video")))
            continue
        try:
            v = spec.fn(ctx)
        except Exception as e:  # noqa: BLE001
            v = SignalValue(None, "skip", reason=f"instrument error: {type(e).__name__}")
        out.append(_record(spec, v))
    apply_gate(out)
    return out


def apply_gate(records: List[Dict[str, Any]]) -> None:
    gate = next((r for r in records if r["id"] == GATE), None)
    if gate is None or gate["verdict"] != "fail":
        return
    for r in records:
        spec = _REGISTRY.get(r["id"])
        if spec is not None and spec.gated:
            r["valid"] = False
            r["invalidated_by"] = GATE


# ── helpers ───────────────────────────────────────────────────────────────────────────────

def _probe(path: Path) -> Dict[str, Any]:
    r = dl.run_process(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration:format=duration",
                        "-of", "json", str(path)], text=True, check=True, deadline_s=_FFPROBE_S,
                       what="ffprobe signal")
    return json.loads(r.stdout or "{}")


def _stream_s(info: Dict[str, Any], kind: str) -> Optional[float]:
    for s in info.get("streams") or []:
        if s.get("codec_type") == kind and s.get("duration") not in (None, "N/A"):
            return float(s["duration"])
    return None


def _format_s(info: Dict[str, Any]) -> Optional[float]:
    d = (info.get("format") or {}).get("duration")
    return float(d) if d not in (None, "N/A") else None


def _hex_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lab(rgb):
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a, b) -> float:
    """CIE76 colour difference of two sRGB triples."""
    la, lb = _lab(a), _lab(b)
    return math.sqrt(sum((p - q) ** 2 for p, q in zip(la, lb)))


def _frame(video: Path, t: float, out: Path):
    from PIL import Image
    dl.run_process(["ffmpeg", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(video), "-frames:v", "1", "-y",
                    str(out)], check=True, deadline_s=_FFMPEG_FRAME_S, what="ffmpeg frame (signal)")
    return Image.open(out).convert("RGB")


# ── the built-in runtime signals ─────────────────────────────────────────────────────────────

@register(GATE, unit="share of scenes", gated=False,
          description="scenes and jobs that did not turn out as intended (report.degradations)")
def _degradation_rate(ctx: SignalContext) -> SignalValue:
    degr = ctx.report.get("degradations") or []
    n_scenes = len(ctx.scenes)
    scenes = {d["scene"] for d in degr if isinstance(d.get("scene"), int)}
    by_kind: Dict[str, int] = {}
    for d in degr:
        by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1
    if n_scenes == 0:
        return SignalValue(None, "skip", reason="no scene was produced", detail={"by_kind": by_kind})
    share = round(len(scenes) / n_scenes, 3)
    pillow = by_kind.get("web_to_pillow", 0) + by_kind.get("no_template", 0)
    misses = [k for k, bad in (("scene share above 10 %", share > DEGRADED_SCENE_MAX),
                               ("pillow fallback", pillow > 0),
                               ("storyboard backend fallback", by_kind.get("storyboard_backend_fallback", 0) > 0),
                               ("grounding lost", by_kind.get("grounding_lost", 0) > 0)) if bad]
    return SignalValue(share, "fail" if misses else "pass", n=len(scenes), of=n_scenes,
                       threshold={"max_share": DEGRADED_SCENE_MAX, "pillow": 0, "backend_fallback": 0,
                                  "grounding_lost": 0},
                       reason="; ".join(misses) or None, detail={"by_kind": by_kind})


@register("layout_clean", unit="collisions kept",
          description="slide collisions that stayed in the final video (web_layout, action kept)")
def _layout_clean(ctx: SignalContext) -> SignalValue:
    web = [s for s in ctx.scenes if s.get("renderer") == "web"]
    if not web:
        return SignalValue(None, "skip", n=0, of=len(ctx.scenes), threshold=0, reason="no web slide in this video")
    kept = [e for e in (ctx.metadata.get("layout_collisions") or []) if e.get("action") == "kept"]
    return SignalValue(len(kept), "pass" if not kept else "fail", n=len(web) - len(kept), of=len(web), threshold=0)


@register("fact_support", unit="unsupported claims",
          description="narration claims the grounding pack does not support (grounded tasks only)")
def _fact_support(ctx: SignalContext) -> SignalValue:
    if not ctx.grounding_requested:
        return SignalValue(None, "skip", threshold=0, reason="not a grounded task")
    g = ctx.metadata.get("grounding")
    status = (g or {}).get("status")
    unverified = (g or {}).get("unverified")
    if status not in ("grounded", "grounded_with_unverified") or not isinstance(unverified, dict):
        # ADR-2247: a grounded task whose claim check never ran is a fail, not a skip
        return SignalValue(None, "fail", threshold=0, reason=f"grounding not applied ({status or 'none'})")
    count = int(unverified.get("count") or 0)
    scenes = len(ctx.scenes)
    bad = len(unverified.get("scenes") or [])
    return SignalValue(count, "pass" if count == 0 else "warn", n=scenes - bad, of=scenes, threshold=0)


@register("mux_integrity", unit="scenes intact", gated=False,
          description="clip >= voice per scene, final audio within 3 % of final video, no truncated clip")
def _mux_integrity(ctx: SignalContext) -> SignalValue:
    scenes_dir = ctx.job_dir / "scenes"
    out = ctx.job_dir / "output.mp4"
    if not out.is_file():
        return SignalValue(None, "skip", reason="no final video")
    n = len(ctx.scenes)
    bad: List[Dict[str, Any]] = []
    for s in ctx.scenes:
        i = s["index"]
        clip, voice = scenes_dir / f"scene_{i:03d}.mp4", scenes_dir / f"scene_{i:03d}.mp3"
        if not clip.is_file() or not voice.is_file():
            bad.append({"scene": i, "why": "missing"})
            continue
        ci, vi = _probe(clip), _probe(voice)
        c_v, c_a, v_s = _stream_s(ci, "video"), _stream_s(ci, "audio"), _format_s(vi)
        if not c_v or not c_a or not v_s:
            bad.append({"scene": i, "why": "truncated"})
        elif min(c_v, c_a) + CLIP_TOLERANCE_S < v_s:
            bad.append({"scene": i, "why": "clip shorter than voice", "clip_s": round(min(c_v, c_a), 3),
                        "voice_s": round(v_s, 3)})
    fi = _probe(out)
    f_v, f_a = _stream_s(fi, "video") or _format_s(fi), _stream_s(fi, "audio")
    av = None
    if not f_v or not f_a:
        bad.append({"scene": None, "why": "final video lacks a stream"})
    else:
        av = round(abs(f_a - f_v) / f_v, 4)
        if av > AV_TOLERANCE:
            bad.append({"scene": None, "why": "final audio and video lengths differ", "share": av})
    return SignalValue(n - len({b["scene"] for b in bad if b["scene"] is not None}), "fail" if bad else "pass",
                       n=n - len({b["scene"] for b in bad if b["scene"] is not None}), of=n,
                       threshold={"clip_vs_voice_s": CLIP_TOLERANCE_S, "final_av_share": AV_TOLERANCE},
                       detail={"final_av_share": av, "problems": bad[:10]})


@register("plan_estimate_error", unit="share", gated=False,
          description="the storyboard model's estimated length vs the narrated length (information only)")
def _plan_estimate_error(ctx: SignalContext) -> SignalValue:
    voice = [s.get("audio_s") for s in ctx.scenes]
    if not ctx.plan_ms or not voice or any(v is None for v in voice):
        return SignalValue(None, "skip", reason="no plan or no measured narration")
    plan_s, real_s = sum(ctx.plan_ms) / 1000.0, sum(voice)
    if plan_s <= 0:
        return SignalValue(None, "skip", reason="plan has no length")
    return SignalValue(round((real_s - plan_s) / plan_s, 3), "info", n=len(voice), of=len(voice),
                       detail={"plan_s": round(plan_s, 1), "narrated_s": round(real_s, 1)})


@register("beats_provenance", unit="share of web scenes on fallback beats",
          description="web scenes whose reveal cues were placed by the fallback, not from the narration (information)")
def _beats_provenance(ctx: SignalContext) -> SignalValue:
    cues = ctx.metadata.get("cues") or []
    if not cues:
        return SignalValue(None, "skip", reason="no web scene with cues")
    fb = sum(1 for c in cues if c.get("beats_source") == "fallback")
    by: Dict[str, int] = {}
    for c in cues:
        by[str(c.get("beats_source"))] = by.get(str(c.get("beats_source")), 0) + 1
    return SignalValue(round(fb / len(cues), 3), "info", n=fb, of=len(cues), detail={"by_source": by})


@register("style_fidelity", unit="delta E (CIE76)",
          description="rendered accent vs the style's accent, and no Corvin mark in a custom-styled video")
def _style_fidelity(ctx: SignalContext) -> SignalValue:
    if not ctx.style_accent:
        return SignalValue(None, "skip", threshold=STYLE_DELTA_E_MAX, reason="no custom style")
    web = [s for s in ctx.scenes if s.get("renderer") == "web"]
    if not web:
        return SignalValue(None, "skip", threshold=STYLE_DELTA_E_MAX, reason="no web slide in this video")
    accent = _hex_rgb(ctx.style_accent)
    marks = [_hex_rgb(m) for m in CORVIN_MARKS]
    best: Optional[float] = None
    mark_frames = 0
    tmp = Path(tempfile.mkdtemp(prefix="vp_sig_"))
    try:
        for s in web:
            clip = ctx.job_dir / "scenes" / f"scene_{s['index']:03d}.mp4"
            if not clip.is_file():
                continue
            dur = _format_s(_probe(clip)) or 0
            for t in (min(1.5, dur * 0.5), dur * 0.75):
                img = _frame(clip, t, tmp / f"f{s['index']}_{t:.2f}.png").resize((480, 270))
                colours = img.getcolors(480 * 270) or []
                near = [(c, rgb) for c, rgb in colours if delta_e(rgb, accent) < 20]
                if sum(c for c, _ in near) >= 40:
                    mode = max(near, key=lambda x: x[0])[1]
                    d = delta_e(mode, accent)
                    best = d if best is None else min(best, d)
                if sum(c for c, rgb in colours if any(delta_e(rgb, m) < 6 for m in marks)) >= 8:
                    mark_frames += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if best is None:
        return SignalValue(None, "fail", n=0, of=len(web), threshold=STYLE_DELTA_E_MAX,
                           reason="the style's accent was not found on any sampled frame",
                           detail={"corvin_mark_frames": mark_frames})
    ok = best <= STYLE_DELTA_E_MAX and mark_frames == 0
    return SignalValue(round(best, 2), "pass" if ok else "fail", n=len(web), of=len(web),
                       threshold={"delta_e_max": STYLE_DELTA_E_MAX, "corvin_mark_frames": 0},
                       reason=None if ok else ("Corvin mark on a frame" if mark_frames else "accent off by more than 3"),
                       detail={"corvin_mark_frames": mark_frames})


# ── still_time (ADR-2245 definition, moved here from scripts/measure_engagement.py, T-0094) ─────
#
# A frame state is the per-pixel median over +-1 s (that removes ambient dots, orbits and ring pulses -
# motion without information); a state change is > 0.15 % of pixels moving by more than 12 grey levels
# against the state 1 s earlier. Still stretches are the runs without a change; the dead time of a scene
# is the time in still stretches of at least 5 s. The numbers are the script's, unchanged: the script now
# calls this code, and the agreement with the pre-move script is measured on the corpus
# (scripts/still_time_agreement.py, tests/corpus/still_time_agreement.json).

STILL_SAMPLE_FPS = 4
STILL_STATE_WINDOW = 4        # +-1 s at STILL_SAMPLE_FPS
STILL_CHANGE_LEVEL = 12
STILL_CHANGE_SHARE = 0.0015
DEAD_MIN_S = 5.0
STILL_DEAD_SHARE_MAX = 0.20   # ADR-2247 still_time gate: dead share <= 20 %
STILL_LONGEST_P90_MAX_S = 8.0  # ... and p90 over scenes of the longest still stretch <= 8 s
_STILL_DECODE_S = 300.0
_STILL_W, _STILL_H = 480, 270
_STILL_MAX_BYTES = 512 * 1024 * 1024


class NumpyMissing(RuntimeError):
    """Still time cannot be measured without numpy: a skip, never a number."""


def still_stretches(clip: Path) -> List[tuple]:
    """Intervals (s) of ``clip`` in which the median-filtered content state does not change."""
    try:
        import numpy as np
    except ImportError as e:
        raise NumpyMissing("numpy missing") from e
    raw = dl.run_process(["ffmpeg", "-v", "error", "-i", str(clip), "-vf",
                          f"fps={STILL_SAMPLE_FPS},scale={_STILL_W}:{_STILL_H}", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], check=True, deadline_s=_STILL_DECODE_S,
                         max_output=_STILL_MAX_BYTES, what="ffmpeg decode (still_time)")
    if getattr(raw, "truncated", False):
        raise RuntimeError("clip too long for the still-time decode")
    frames = np.frombuffer(raw.stdout, dtype=np.uint8).reshape(-1, _STILL_H, _STILL_W)
    n = len(frames)
    if n < 2:
        return []
    w = STILL_STATE_WINDOW
    state = np.stack([np.median(frames[max(0, i - w): i + w + 1], axis=0) for i in range(n)]).astype(np.int16)
    lag = STILL_SAMPLE_FPS
    changed = [False] * n
    for i in range(lag, n):
        share = (np.abs(state[i] - state[i - lag]) > STILL_CHANGE_LEVEL).mean()
        if share > STILL_CHANGE_SHARE:
            for k in range(i - lag, i + 1):
                changed[k] = True
    out, start = [], None
    for i, c in enumerate(changed + [True]):
        if not c and start is None:
            start = i
        elif c and start is not None:
            out.append((start / STILL_SAMPLE_FPS, i / STILL_SAMPLE_FPS))
            start = None
    return out


def clip_duration_s(clip: Path) -> float:
    return _format_s(_probe(clip)) or 0.0


def still_time_of_scene(clip: Path) -> Dict[str, Any]:
    """``{duration_s, dead_s, longest_still_s}`` of one scene clip (raises NumpyMissing)."""
    dur = clip_duration_s(clip)
    still = still_stretches(clip)
    return {"duration_s": round(dur, 2),
            "dead_s": round(sum(b - a for a, b in still if b - a >= DEAD_MIN_S), 2),
            "longest_still_s": round(max((b - a for a, b in still), default=0.0), 2)}


def _p90(values: Sequence[float]) -> Optional[float]:
    v = sorted(values)
    return v[min(len(v) - 1, int(len(v) * 0.9))] if v else None


def still_time_summary(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    total = sum(r["duration_s"] for r in rows)
    dead = sum(r["dead_s"] for r in rows)
    return {"dead_share": round(dead / total, 3) if total > 0 else None,
            "longest_still_p90_s": _p90([r["longest_still_s"] for r in rows]),
            "longest_still_max_s": max((r["longest_still_s"] for r in rows), default=None),
            "scenes_still_ge_5s": sum(r["longest_still_s"] >= DEAD_MIN_S for r in rows),
            "duration_s": round(total, 2)}


@register("still_time", unit="share of runtime in still stretches >= 5 s",
          description="time in which the slide's content does not change (ADR-2245); a degraded scene counts")
def _still_time(ctx: SignalContext) -> SignalValue:
    threshold = {"dead_share_max": STILL_DEAD_SHARE_MAX, "longest_still_p90_max_s": STILL_LONGEST_P90_MAX_S}
    clips = [(s["index"], ctx.job_dir / "scenes" / f"scene_{s['index']:03d}.mp4") for s in ctx.scenes]
    clips = [(i, c) for i, c in clips if c.is_file()]
    if not clips:
        return SignalValue(None, "skip", threshold=threshold, reason="no scene clip")
    try:
        rows = [{"scene": i, **still_time_of_scene(c)} for i, c in clips]
    except NumpyMissing:
        return SignalValue(None, "skip", threshold=threshold, reason="numpy missing")
    summ = still_time_summary(rows)
    if summ["dead_share"] is None:
        return SignalValue(None, "skip", threshold=threshold, reason="scenes have no length")
    misses = [m for m, bad in (("dead share above 20 %", summ["dead_share"] > STILL_DEAD_SHARE_MAX),
                               ("p90 longest still above 8 s",
                                (summ["longest_still_p90_s"] or 0) > STILL_LONGEST_P90_MAX_S)) if bad]
    return SignalValue(summ["dead_share"], "warn" if misses else "pass",
                       n=len(rows) - summ["scenes_still_ge_5s"], of=len(rows), threshold=threshold,
                       reason="; ".join(misses) or None,
                       detail={"longest_still_p90_s": summ["longest_still_p90_s"],
                               "longest_still_max_s": summ["longest_still_max_s"],
                               "scenes_still_ge_5s": summ["scenes_still_ge_5s"],
                               "per_scene": [{k: r[k] for k in ("scene", "dead_s", "longest_still_s")}
                                             for r in rows][:40]})


# ── revision_locality (ADR-2247: information) ───────────────────────────────────────────────

def _words(text: Any) -> List[str]:
    return " ".join(str(text or "").split()).split(" ") if str(text or "").strip() else []


def revision_locality(base_narrations: Sequence[str], narrations: Sequence[str]) -> Dict[str, Any]:
    """Share of the base video's scenes whose narration the revision kept word-identical (whitespace
    ignored; position free - a kept scene may move)."""
    pool: Dict[str, int] = {}
    for t in narrations:
        k = " ".join(_words(t))
        pool[k] = pool.get(k, 0) + 1
    kept = 0
    for t in base_narrations:
        k = " ".join(_words(t))
        if k and pool.get(k, 0) > 0:
            pool[k] -= 1
            kept += 1
    n = len(base_narrations)
    return {"kept": kept, "of": n, "share": round(kept / n, 3) if n else None}


@register("revision_locality", unit="share of the base video's scenes kept word-identical", gated=False,
          description="how much of the base video a revision kept (information; a change may touch everything)")
def _revision_locality(ctx: SignalContext) -> SignalValue:
    if ctx.base_narrations is None:
        return SignalValue(None, "skip", reason="not a revision")
    if not ctx.base_narrations or not ctx.narrations:
        return SignalValue(None, "skip", reason="a storyboard has no scene")
    r = revision_locality(ctx.base_narrations, ctx.narrations)
    return SignalValue(r["share"], "info", n=r["kept"], of=r["of"],
                       detail={"base_scenes": r["of"], "revision_scenes": len(ctx.narrations)})


# ── language_parity (ADR-2247; checked at storage time, Corvin-Videos convention) ───────────────

PARITY_SCENE_DELTA = 1          # scene counts may differ by one
PARITY_TEMPLATE_SHARE = 0.80    # >= 80 % identical template positions
_NUM_WORDS = {
    # 2..20 written out (0 and 1 are articles/pronouns too often to count as facts)
    "zwei": "2", "drei": "3", "vier": "4", "fünf": "5", "sechs": "6", "sieben": "7", "acht": "8", "neun": "9",
    "zehn": "10", "elf": "11", "zwölf": "12", "dreizehn": "13", "vierzehn": "14", "fünfzehn": "15",
    "sechzehn": "16", "siebzehn": "17", "achtzehn": "18", "neunzehn": "19", "zwanzig": "20",
    "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14", "fifteen": "15",
    "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19", "twenty": "20",
}
_NUM_RE = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,\u202f\u00a0]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
                     r"(\s?(?:%|prozent|percent))?", re.IGNORECASE)


def _norm_number(tok: str) -> str:
    """Locale-free form of a number token: ``1.234,5`` = ``1,234.5`` = ``1234.5``; ``4,5`` = ``4.5``;
    ``1.000`` = ``1,000`` = ``1000`` (one separator before exactly three digits reads as thousands)."""
    t = tok.replace("\u202f", ".").replace("\u00a0", ".")
    seps = [c for c in t if c in ".,"]
    if not seps:
        return t.lstrip("0") or "0"
    groups = re.split(r"[.,]", t)
    if len(set(seps)) == 1 and all(len(g) == 3 for g in groups[1:]):
        return "".join(groups).lstrip("0") or "0"
    k = max(t.rfind("."), t.rfind(","))
    whole = re.sub(r"[.,]", "", t[:k]).lstrip("0") or "0"
    frac = t[k + 1:].rstrip("0")
    return whole + ("." + frac if frac else "")


def numeric_facts(text: str) -> Dict[str, int]:
    """Every number / percentage in a narration, locale-normalised (``77 %`` = ``77%`` = ``77 Prozent``)."""
    out: Dict[str, int] = {}
    s = str(text or "")
    for m in _NUM_RE.finditer(s):
        key = _norm_number(m.group(1)) + ("%" if m.group(2) else "")
        out[key] = out.get(key, 0) + 1
    for w in re.findall(r"[^\W\d_]+", s.lower()):
        if w in _NUM_WORDS:
            out[_NUM_WORDS[w]] = out.get(_NUM_WORDS[w], 0) + 1
    return out


def _bare(fact: str) -> str:
    return fact[:-1] if fact.endswith("%") else fact


def language_parity(a: Sequence[Dict[str, Any]], b: Sequence[Dict[str, Any]], *,
                    langs: Sequence[str] = ("de", "en")) -> Dict[str, Any]:
    """Parity of two language versions of one video (storyboard scenes: ``template``, ``narration_text``).

    pass = scene counts within one, >= 80 % identical template positions, and every numeric fact of one
    narration in the other (a percentage matches the same number written without the sign: locales
    differ in whether they say "Prozent"). Independent of grounding by design (ADR-2247)."""
    ta = [str((s or {}).get("template") or "-") for s in a]
    tb = [str((s or {}).get("template") or "-") for s in b]
    longest = max(len(ta), len(tb))
    same = sum(1 for x, y in zip(ta, tb) if x == y)
    share = round(same / longest, 3) if longest else None
    fa = numeric_facts(" ".join(str((s or {}).get("narration_text") or "") for s in a))
    fb = numeric_facts(" ".join(str((s or {}).get("narration_text") or "") for s in b))
    bare_a, bare_b = {_bare(k) for k in fa}, {_bare(k) for k in fb}
    only_a = sorted(k for k in fa if _bare(k) not in bare_b)
    only_b = sorted(k for k in fb if _bare(k) not in bare_a)
    misses = []
    if abs(len(ta) - len(tb)) > PARITY_SCENE_DELTA:
        misses.append("scene count differs by more than one")
    if share is None or share < PARITY_TEMPLATE_SHARE:
        misses.append("template sequence below 80 % identical")
    if only_a or only_b:
        misses.append("numeric facts differ")
    la, lb = (list(langs) + ["a", "b"])[:2]
    return {"id": "language_parity", "verdict": "fail" if misses else "pass", "reasons": misses,
            "scenes": {la: len(ta), lb: len(tb)},
            "templates": {"identical_positions": same, "of": longest, "share": share,
                          "threshold": PARITY_TEMPLATE_SHARE, la: ta, lb: tb},
            "numeric_facts": {la: sorted(fa), lb: sorted(fb), f"only_{la}": only_a, f"only_{lb}": only_b}}


# ── cue_alignment (post-hoc, opt-in: whisper-1 word times; ADR-2247 / PLAN-0946 R5) ──────────────

ALIGN_MEDIAN_GOAL_S = 1.0
ALIGN_P90_GOAL_S = 1.5
WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"
_WHISPER_S = 120.0


def whisper_words(mp3: Path, api_key: str) -> List[Dict[str, Any]]:
    """Word times of one scene's narration from OpenAI whisper-1 (an independent clock, not the
    estimate the cues were built from). Network; bounded by the deadline primitive."""
    import requests

    def call():
        with open(mp3, "rb") as f:
            r = requests.post(WHISPER_URL, headers={"Authorization": f"Bearer {api_key}"},
                              data={"model": "whisper-1", "response_format": "verbose_json",
                                    "timestamp_granularities[]": "word"},
                              files={"file": (mp3.name, f, "audio/mpeg")}, timeout=(10, _WHISPER_S))
        r.raise_for_status()
        return r.json()
    return list((dl.run_sync(call, deadline_s=_WHISPER_S + 15, what="whisper-1") or {}).get("words") or [])


def _norm_word(s: str) -> str:
    return re.sub(r"[^\w]", "", str(s).lower())


def _label_tokens(label: str) -> List[str]:
    return [_norm_word(t) for t in re.split(r"[\s\-+/]+|(?<=[a-zäöü])(?=[A-ZÄÖÜ])", label) if len(_norm_word(t)) >= 4]


def spoken_time(label: str, words: List[Dict[str, Any]], start: int = 0) -> Optional[float]:
    """Start of the first word (or run of up to 4 words) at or after ``start`` matching the whole label,
    else the first matching label token at or after ``start``."""
    toks = _label_tokens(label)
    whole = _norm_word(label)
    normed = [_norm_word(w.get("word", "")) for w in words]
    for i in range(max(0, start), len(words)):
        run = ""
        for j in range(i, min(i + 4, len(words))):
            run += normed[j]
            if whole and run == whole:
                return float(words[i]["start"])
    for t in sorted(toks, key=len, reverse=True):
        for i in range(max(0, start), len(normed)):
            w = normed[i]
            if t in w or (len(w) >= 5 and w in t):
                return float(words[i]["start"])
    return None


def _word_index_of(char_pos: int, text: str, words: List[Dict[str, Any]]) -> int:
    """Index into the whisper words of the narration word that starts at ``char_pos`` of ``text``
    (sequence alignment of the two word lists; whisper may split, merge or mishear words)."""
    import difflib
    narr = [_norm_word(w) for w in text[:char_pos].split()]
    n = len([w for w in narr if w])
    a = [w for w in (_norm_word(x) for x in text.split()) if w]
    b = [_norm_word(w.get("word", "")) for w in words]
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        if blk.size and blk.a + blk.size > n:
            return blk.b + max(0, n - blk.a)
    return len(b)


def align_scene(narration: str, beats: Any, items: Sequence[Dict[str, Any]], words: List[Dict[str, Any]],
                *, lead_s: float = 0.25) -> List[Dict[str, Any]]:
    """Per item ``{label, error_s | None}``: |cue + lead - spoken time|. The spoken time is the first
    occurrence of the item AFTER THE START OF THE SENTENCE THAT NAMES IT - the beat sentence the cue was
    placed on, else the first sentence mentioning it - never simply the first in the scene (an item
    named in an introductory sentence would otherwise be measured against the wrong time)."""
    try:
        from .web_timeline import find_mentions, split_sentences
    except ImportError:  # pragma: no cover - script use
        from web_timeline import find_mentions, split_sentences
    text = " ".join(str(narration or "").split())
    spans = split_sentences(text)
    beat_list = beats if isinstance(beats, list) and len(beats) == len(spans) else None
    mentions = find_mentions(text, [str(it.get("label") or "") for it in items]) if items else []
    out: List[Dict[str, Any]] = []
    for j, it in enumerate(items):
        label = str(it.get("label") or "")
        at = it.get("at")
        if at is None or not label:
            out.append({"label": label, "error_s": None, "why": "no cue"})
            continue
        k = None
        if beat_list is not None:
            k = next((s for s, b in enumerate(beat_list) if isinstance(b, int) and not isinstance(b, bool) and b == j), None)
        char = spans[k][0] if k is not None and k < len(spans) else (mentions[j][0] if j < len(mentions) and mentions[j] else 0)
        if k is None and j < len(mentions) and mentions[j]:
            # the sentence holding the first mention: search from that sentence's start
            char = next((a for a, e in spans if a <= mentions[j][0] < e), mentions[j][0])
        t = spoken_time(label, words, _word_index_of(char, text, words) if char else 0)
        if t is None:
            out.append({"label": label, "error_s": None, "why": "not heard"})
        else:
            out.append({"label": label, "error_s": round(abs(float(at) + lead_s - t), 2)})
    return out


def _scene_item_count(template: Optional[str], data: Any) -> int:
    if not template or not isinstance(data, dict):
        return 0
    try:
        try:
            from .web_templates import scene_items, validate_scene_data
        except ImportError:  # pragma: no cover
            from web_templates import scene_items, validate_scene_data
        return len(scene_items(template, validate_scene_data(template, data)))
    except Exception:  # noqa: BLE001 - data the template refused has no countable items
        return 0


@register("cue_alignment", unit="s between a reveal and the spoken word (median)", kind="posthoc",
          description="whisper-1 word times vs the reveal cues; coverage = matched / all items with a cue "
                      "(Pillow scenes and uncued items count as unmatched)")
def _cue_alignment(ctx: SignalContext) -> SignalValue:
    threshold = {"median_max_s": ALIGN_MEDIAN_GOAL_S, "p90_max_s": ALIGN_P90_GOAL_S, "coverage": "ratchet"}
    if ctx.transcribe is None:
        return SignalValue(None, "skip", threshold=threshold, reason="not run (opt-in, needs the operator)")
    cues = {c.get("scene"): c for c in (ctx.metadata.get("cues") or []) if isinstance(c, dict)}
    sb = ctx.storyboard_scenes or []
    errs: List[float] = []
    total = 0
    per_scene: List[Dict[str, Any]] = []
    for idx, scene in enumerate(sb, start=1):
        c = cues.get(idx)
        if c is None:
            n_items = _scene_item_count(scene.get("template"), scene.get("data"))
            total += n_items
            if n_items:
                per_scene.append({"scene": idx, "items": n_items, "matched": 0, "why": "no cue (classic slide)"})
            continue
        items = [it for it in (c.get("items") or []) if isinstance(it, dict)]
        total += len(items)
        if not items:
            continue
        mp3 = ctx.job_dir / "scenes" / f"scene_{idx:03d}.mp3"
        if not mp3.is_file():
            per_scene.append({"scene": idx, "items": len(items), "matched": 0, "why": "no narration audio"})
            continue
        words = ctx.transcribe(mp3)
        same_template = c.get("template") == scene.get("template")
        rows = align_scene(scene.get("narration_text") or "", scene.get("beats") if same_template else None,
                           items, words)
        got = [r["error_s"] for r in rows if r["error_s"] is not None]
        errs.extend(got)
        per_scene.append({"scene": idx, "items": len(items), "matched": len(got)})
    if total == 0:
        return SignalValue(None, "skip", threshold=threshold, reason="no item with a cue in this video")
    errs.sort()
    median = errs[len(errs) // 2] if errs else None
    p90 = _p90(errs)
    coverage = round(len(errs) / total, 3)
    ok = median is not None and median <= ALIGN_MEDIAN_GOAL_S and (p90 or 0) <= ALIGN_P90_GOAL_S
    return SignalValue(median, "pass" if ok else "warn", n=len(errs), of=total, threshold=threshold,
                       reason=None if ok else ("no item matched" if median is None else "above the goal"),
                       detail={"p90_s": p90, "coverage": coverage, "per_scene": per_scene[:40]})


# ── post-hoc run on a finished job (the host calls this after its gates; T-0094) ────────────────

def storyboard_scene_dicts(storyboard: Any) -> List[Dict[str, Any]]:
    """``template``, ``narration_text``, ``beats``, ``data`` per storyboard scene (dict, JSON or object)."""
    if isinstance(storyboard, str):
        try:
            storyboard = json.loads(storyboard)
        except ValueError:
            return []
    scenes = storyboard.get("scenes") if isinstance(storyboard, dict) else getattr(storyboard, "scenes", None)
    out = []
    for s in scenes or []:
        g = (lambda k: s.get(k)) if isinstance(s, dict) else (lambda k: getattr(s, k, None))
        out.append({"template": g("template"), "narration_text": g("narration_text") or "",
                    "beats": g("beats"), "data": g("data")})
    return out


def measure_posthoc(job_dir: Path, storyboard: Any, metadata: Dict[str, Any], *,
                    transcribe: Optional[Callable[[Path], List[Dict[str, Any]]]] = None,
                    only: Sequence[str] = ("cue_alignment",), refused: Optional[str] = None) -> Dict[str, Any]:
    """Run post-hoc signals over a finished job and merge them into its ``report.json`` (same record,
    same validation - no narration text can enter it). Returns ``{signals, stored, reason}``; a job
    without a report gets the numbers back but nothing is stored (``stored: False``). ``refused``: the
    host's gate refused the measurement - every signal in ``only`` is recorded as ``skip`` with that
    reason, nothing runs."""
    try:
        from . import report as rp
    except ImportError:  # pragma: no cover
        import report as rp
    job_dir = Path(job_dir)
    scenes = storyboard_scene_dicts(storyboard)
    rep = rp.read(job_dir) if (job_dir / rp.REPORT_NAME).is_file() and not (job_dir / rp.REPORT_NAME).is_symlink() else None
    ctx = SignalContext(job_dir=job_dir, report=rep or {"scenes": [{"index": i} for i in range(1, len(scenes) + 1)]},
                        metadata=metadata or {}, storyboard_scenes=scenes, transcribe=transcribe,
                        narrations=[s["narration_text"] for s in scenes])
    if refused is not None:
        recs = [_record(spec, SignalValue(None, "skip", reason=refused)) for spec in registered("posthoc") if spec.id in only]
    else:
        recs = run(ctx, kind="posthoc", only=only)
    if rep is None:
        return {"signals": recs, "stored": False, "reason": "no report"}
    keep = [s for s in rep.get("signals") or [] if s.get("id") not in {r["id"] for r in recs}]
    rep["signals"] = keep + recs
    rep["posthoc_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    text = rp.validate(rep, forbidden_texts=[s["narration_text"] for s in scenes])
    tmp = job_dir / (rp.REPORT_NAME + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, job_dir / rp.REPORT_NAME)
    return {"signals": recs, "stored": True, "reason": None}
