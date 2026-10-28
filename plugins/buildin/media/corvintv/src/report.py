"""Production Report: the single record of one video job (ADR-2247, PLAN-0946 R2).

``<store>/videos/<job>/report.json``, schema 1, at most ``MAX_REPORT_BYTES``. Written when a job
completes AND when it fails or is cancelled in-process (a failed job's report names the stage that
failed). It holds identity, stage timings, the storyboard model's reported token usage, one record per scene, every degradation the pipeline took
(recorded where it happens, never reconstructed afterwards), tool versions and the runtime signals
(``signals.py``).

What it never holds: the task text, narration, slide text, file paths outside the job directory or an
exception message (messages can carry user content; only the exception's class name is kept). The
builder only accepts closed vocabularies, numbers and short identifiers, and ``validate`` refuses a
report in which any 24-character window of the task or a narration appears - a backstop, not the
mechanism.

A degradation is recorded through ``note_degradation`` by the code that takes the fallback. The report
of the running job is reachable through a context variable (like ``deadline.current_budget``), so a
function deep in the storyboard or render path records its own fallback without a parameter threaded
through every caller; outside a job the call is a no-op.
"""
from __future__ import annotations

import contextvars
import json
import os
import platform
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

SCHEMA = 1
MAX_REPORT_BYTES = 64 * 1024
REPORT_NAME = "report.json"

# Every kind of "it did not turn out as intended" the pipeline records (ADR-2247, degradation_rate).
DEGRADATION_KINDS = frozenset({
    "web_to_pillow",                # a web slide failed and the classic Pillow slide was used
    "no_template",                  # a scene had no web template/data at render time: Pillow, nothing failed
    "template_to_quote",            # the model's template was invalid; the scene became a quote of its narration
    "collision_replaced",           # a colliding slide was replaced by a simpler one (content/quote)
    "collision_kept",               # a colliding slide stayed in the video
    "tts_tier_below",               # the scene was spoken by a lower TTS tier than the configured one
    "storyboard_backend_fallback",  # the requested storyboard model failed; another one wrote it
    "grounding_lost",               # a grounded task ended without its grounding
    "storyboard_repaired",          # the model got scene specs wrong and a repair pass fixed some
    "canvas_degraded",              # a canvas collided after layout and walked a rung of its ladder (ADR-2249 D1)
    "board_to_still",               # a board scene failed (model, render, collision) and its picture was shown (ADR-2260 d9)
})
# Degradations that count against a SCENE (the others are job-level).
SCENE_KINDS = frozenset({"web_to_pillow", "no_template", "template_to_quote", "collision_replaced",
                         "collision_kept", "tts_tier_below", "canvas_degraded", "board_to_still"})
STAGES = ("setup", "storyboard", "scenes", "assemble", "signals")
STATUSES = frozenset({"complete", "error", "cancelled"})

# The configured tier of each engine: ``auto`` aims for the first tier of the chain (ADR-2211).
TTS_TIER_ORDER = ("openai", "edge", "gtts", "mock")

_TOKEN = re.compile(r"^[A-Za-z0-9_.:+\-/ ]{0,80}$")
_TEXT_WINDOW = 24


class ReportError(ValueError):
    """The report would break its contract (size, content, schema)."""


def _token(value: Any, what: str) -> Optional[str]:
    """A short identifier from a closed or machine-made vocabulary - never prose."""
    if value is None:
        return None
    s = str(value)
    if not _TOKEN.match(s):
        raise ReportError(f"{what} is not a short identifier")
    return s


def _token_or_none(value: Any) -> Optional[str]:
    try:
        return _token(value, "value")
    except ReportError:
        return None


def _plugin_version() -> Optional[str]:
    try:
        return json.loads((Path(__file__).resolve().parents[1] / "plugin.json").read_text())["version"]
    except Exception:  # noqa: BLE001 - an identity field, not worth failing a job over
        return None


@dataclass
class _Stage:
    name: str
    started: float
    seconds: Optional[float] = None


class ProductionReport:
    """Built while the job runs; ``finish`` + ``write`` at the end."""

    def __init__(self, job_id: str, *, configured_tts: Optional[str] = None,
                 storyboard_backend: Optional[str] = None, style_id: Optional[str] = None):
        self.job_id = _token(job_id, "job id")
        self.created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # set before the job validates its inputs: an unusable value is dropped, never raised
        self.configured_tts = _token_or_none(configured_tts)
        self.storyboard_backend = _token_or_none(storyboard_backend)
        self.style_id = _token_or_none(style_id)
        self.language: Optional[str] = None
        self.storyboard_llm: Optional[str] = None
        self.stages: List[_Stage] = []
        self.scenes: Dict[int, Dict[str, Any]] = {}
        self.degradations: List[Dict[str, Any]] = []
        self.signals: List[Dict[str, Any]] = []
        self.status: Optional[str] = None
        self.failed_stage: Optional[str] = None
        self.error_class: Optional[str] = None
        self.tools: Dict[str, Optional[str]] = {}
        self.media: Dict[str, Any] = {}
        # token usage of the storyboard model calls, as the backend REPORTED it (never estimated);
        # ``calls_without_usage`` counts answers that carried none
        self.llm_usage: Dict[str, int] = {"calls": 0, "calls_without_usage": 0, "input_tokens": 0,
                                          "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0}
        self._t0 = time.monotonic()

    # -- recording ------------------------------------------------------------------------
    def begin(self, name: str) -> None:
        """Close the open stage (if any) and open ``name``."""
        if name not in STAGES:
            raise ReportError(f"unknown stage {name!r}")
        self.end()
        self.stages.append(_Stage(name, time.monotonic()))

    def end(self) -> None:
        for st in self.stages:
            if st.seconds is None:
                st.seconds = round(time.monotonic() - st.started, 3)

    def current_stage(self) -> Optional[str]:
        open_ = [s.name for s in self.stages if s.seconds is None]
        return open_[-1] if open_ else None

    def note_degradation(self, kind: str, *, scene: Optional[int] = None, reason: Optional[str] = None,
                         tier: Optional[str] = None, count: Optional[int] = None,
                         source: Optional[str] = None, target: Optional[str] = None) -> None:
        if kind not in DEGRADATION_KINDS:
            raise ReportError(f"unknown degradation {kind!r}")
        if kind in SCENE_KINDS and not isinstance(scene, int):
            raise ReportError(f"{kind} needs a scene index")
        entry: Dict[str, Any] = {"kind": kind}
        if scene is not None:
            entry["scene"] = int(scene)
        for key, val in (("reason", reason), ("tier", tier), ("from", source), ("to", target)):
            if val is not None:
                entry[key] = _reason(val) if key == "reason" else _token(val, key)
        if count is not None:
            entry["count"] = int(count)
        self.degradations.append(entry)

    def note_llm_usage(self, usage: Optional[Dict[str, Any]]) -> None:
        """Add one model call's reported usage. Accepts the Claude CLI / Anthropic shape
        (``input_tokens``, ``output_tokens``, ``cache_read_input_tokens``,
        ``cache_creation_input_tokens``)."""
        u = self.llm_usage
        u["calls"] += 1
        if not isinstance(usage, dict):
            u["calls_without_usage"] += 1
            return
        def n(*keys: str) -> int:
            for k in keys:
                v = usage.get(k)
                if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
                    return v
            return 0
        got = {"input_tokens": n("input_tokens"),
               "output_tokens": n("output_tokens"),
               "cache_read_tokens": n("cache_read_input_tokens"),
               "cache_write_tokens": n("cache_creation_input_tokens")}
        if not any(got.values()):
            u["calls_without_usage"] += 1
        for k, v in got.items():
            u[k] += v

    def scene(self, index: int, **fields: Any) -> None:
        """Facts about one scene: numbers, booleans and identifiers only."""
        rec = self.scenes.setdefault(int(index), {"index": int(index)})
        for k, v in fields.items():
            if isinstance(v, bool) or v is None or isinstance(v, (int, float)):
                rec[k] = round(v, 3) if isinstance(v, float) else v
            else:
                rec[k] = _token(v, f"scene field {k}")

    def finish(self, status: str, *, error: Optional[BaseException] = None) -> None:
        if status not in STATUSES:
            raise ReportError(f"unknown status {status!r}")
        self.status = status
        if error is not None and self.failed_stage is None:
            self.failed_stage = self.current_stage() or "setup"
        self.end()
        if error is not None:
            self.error_class = type(error).__name__

    # -- output ---------------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        scene_count = len(self.scenes)
        degraded_scenes = sorted({d["scene"] for d in self.degradations if d["kind"] in SCENE_KINDS})
        return {
            "schema": SCHEMA,
            "job_id": self.job_id,
            "plugin_version": _plugin_version(),
            "created_at": self.created_at,
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": self.status,
            "failed_stage": self.failed_stage,
            "error_class": self.error_class,
            "language": self.language,
            "style_id": self.style_id,
            "configured": {"tts": self.configured_tts, "storyboard_backend": self.storyboard_backend},
            "storyboard_llm": self.storyboard_llm,
            "llm_usage": dict(self.llm_usage),
            "stages": [{"name": s.name, "seconds": s.seconds} for s in self.stages],
            "total_seconds": round(time.monotonic() - self._t0, 3),
            "scenes": [self.scenes[k] for k in sorted(self.scenes)],
            "degradations": self.degradations,
            "degraded_scenes": {"n": len(degraded_scenes), "of": scene_count, "indexes": degraded_scenes},
            "media": self.media,
            "tools": self.tools,
            "signals": self.signals,
        }

    def write(self, job_dir: Path, *, forbidden_texts: Iterable[str] = ()) -> Path:
        data = self.to_dict()
        text = validate(data, forbidden_texts=forbidden_texts)
        job_dir.mkdir(parents=True, exist_ok=True)
        path = job_dir / REPORT_NAME
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
        return path


def _reason(value: Any) -> str:
    """A fallback reason: the exception class or a fixed phrase, cut to 60 characters, and with
    anything that is not a plain identifier character removed (no quotes, no paths, no prose)."""
    s = str(value)
    s = s.split(":", 1)[0] if ":" in s else s
    return re.sub(r"[^A-Za-z0-9_. \-]", "", s)[:60]


def _windows(text: str) -> Iterator[str]:
    t = " ".join(str(text).split())
    if len(t) < _TEXT_WINDOW:
        if len(t) >= 12:
            yield t
        return
    for i in range(0, len(t) - _TEXT_WINDOW + 1, 8):
        yield t[i:i + _TEXT_WINDOW]


def validate(data: Dict[str, Any], *, forbidden_texts: Iterable[str] = ()) -> str:
    """Schema, size and content check; returns the serialised report."""
    if data.get("schema") != SCHEMA:
        raise ReportError("wrong schema")
    for key in ("job_id", "status", "scenes", "degradations", "signals", "stages"):
        if key not in data:
            raise ReportError(f"missing {key}")
    for d in data["degradations"]:
        if d.get("kind") not in DEGRADATION_KINDS:
            raise ReportError("unknown degradation kind")
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1)
    if len(text.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ReportError(f"report exceeds {MAX_REPORT_BYTES} bytes")
    flat = " ".join(text.split())
    for src in forbidden_texts:
        for w in _windows(src or ""):
            if w in flat:
                raise ReportError("report contains task or narration text")
    return text


def read(job_dir: Path) -> Optional[Dict[str, Any]]:
    p = Path(job_dir) / REPORT_NAME
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def tool_versions() -> Dict[str, Optional[str]]:
    """First version token of the external tools that shaped the video (cheap; bounded)."""
    out: Dict[str, Optional[str]] = {"python": platform.python_version()}
    try:
        from . import deadline as dl
    except ImportError:  # pragma: no cover - script use
        import deadline as dl
    try:
        r = dl.run_process(["ffmpeg", "-version"], text=True, deadline_s=10, what="ffmpeg -version")
        m = re.search(r"ffmpeg version (\S+)", r.stdout or "")
        out["ffmpeg"] = m.group(1)[:40] if m else None
    except Exception:  # noqa: BLE001
        out["ffmpeg"] = None
    try:
        from importlib.metadata import version
        out["playwright"] = version("playwright")
    except Exception:  # noqa: BLE001
        out["playwright"] = None
    return out


# -- the running job's report (context variable) --------------------------------------------
_CURRENT: contextvars.ContextVar[Optional[ProductionReport]] = contextvars.ContextVar("vp_report", default=None)


def current() -> Optional[ProductionReport]:
    return _CURRENT.get()


def set_current(rep: Optional[ProductionReport]):
    return _CURRENT.set(rep)


def reset_current(token) -> None:
    _CURRENT.reset(token)


def note_llm_usage(usage: Optional[Dict[str, Any]]) -> None:
    """Record one model call's reported token usage on the running job's report; no-op outside a job."""
    rep = current()
    if rep is not None:
        rep.note_llm_usage(usage)


def note_degradation(kind: str, **fields: Any) -> None:
    """Record a degradation on the running job's report; a no-op outside a job."""
    rep = current()
    if rep is not None:
        rep.note_degradation(kind, **fields)
