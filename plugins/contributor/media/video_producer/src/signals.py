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
import shutil
import tempfile
from dataclasses import dataclass, field
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
