#!/usr/bin/env python3
"""Measure how much of a produced video stands still (ADR-2245 release gate).

Per scene clip of a finished job:
  still       (the ``still_time`` signal of src/signals.py) stretches in which the slide's content does not change. A frame
              state is the per-pixel median over ±1 s (this removes ambient dots,
              orbits and ring pulses — motion without information); a state change
              is > 0.15 % of pixels moving by more than 12 levels against the state
              1 s earlier. Reported: dead_s (time in still stretches ≥ 5 s) and the
              longest still stretch.
  frozen_s    ffmpeg freezedetect n=0.002 d=1.5 — the method of the first
              2026-10-09 baseline (77 %). Kept for comparison only: it compares
              consecutive frames, so a 0.9 s fade-in reads as frozen.
  cue_gap     the longest stretch without a scheduled visual event (reveal, focus
              move, chip), from the job metadata's cue log — 0 s and the scene end count
  align       (with --whisper) |cue + lead - spoken time| for every item whose label
              the transcript contains; word times from OpenAI whisper-1, an
              independent clock, not the estimate the cues were built from

Usage:
  measure_engagement.py <videos_dir> <job_id> [<job_id> ...] [--whisper] [--json out.json]
  (<videos_dir> = <tenant>/video_producer/videos; OPENAI_API_KEY for --whisper)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import signals as sg  # noqa: E402

REVEAL_LEAD_S = 0.25


def _duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def frozen_intervals(clip: Path) -> List[tuple]:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(clip), "-vf",
                          "freezedetect=n=0.002:d=1.5", "-an", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", err)]
    if len(starts) > len(ends):
        ends.append(_duration(clip))
    return list(zip(starts, ends))


# The still-time logic lives in the plugin (src/signals.py, the ``still_time`` signal) since T-0094; this
# script calls it so there is one definition. Constants are re-exported for readers of this file.
SAMPLE_FPS = sg.STILL_SAMPLE_FPS
STATE_WINDOW = sg.STILL_STATE_WINDOW
CHANGE_LEVEL = sg.STILL_CHANGE_LEVEL
CHANGE_SHARE = sg.STILL_CHANGE_SHARE
DEAD_MIN_S = sg.DEAD_MIN_S

SKIP_NUMPY = {"verdict": "skip", "reason": "numpy missing"}
NumpyMissing = sg.NumpyMissing


def still_stretches(clip: Path) -> List[tuple]:
    """Intervals (s) in which the median-filtered content state does not change (src/signals.py)."""
    return sg.still_stretches(clip)


def _norm(s: str) -> str:
    return re.sub(r"[^\w]", "", s.lower())


def whisper_words(mp3: Path, api_key: str) -> List[Dict[str, Any]]:
    return sg.whisper_words(mp3, api_key)


def spoken_time(label: str, words: List[Dict[str, Any]]) -> Optional[float]:
    """First occurrence anywhere in the scene (the script's historical measure; the ``cue_alignment``
    signal in src/signals.py searches from the sentence that names the item instead)."""
    return sg.spoken_time(label, words)


def measure_job(videos_dir: Path, job_id: str, api_key: Optional[str]) -> Dict[str, Any]:
    root = videos_dir / job_id
    meta = json.loads((root / "metadata.json").read_text()).get("metadata", {})
    cues = {c["scene"]: c for c in meta.get("cues") or []}
    scenes = []
    for clip in sorted((root / "scenes").glob("scene_*.mp4")):
        n = int(clip.stem.split("_")[1])
        dur = _duration(clip)
        iv = frozen_intervals(clip)
        try:
            still = still_stretches(clip)
        except NumpyMissing:
            still = None
        row: Dict[str, Any] = {"scene": n, "duration": round(dur, 2),
                               "dead_s": None if still is None else round(sum(b - a for a, b in still if b - a >= DEAD_MIN_S), 2),
                               "longest_still": None if still is None else round(max((b - a for a, b in still), default=0.0), 2),
                               "frozen_s": round(sum(b - a for a, b in iv), 2),
                               "longest_frozen": round(max((b - a for a, b in iv), default=0.0), 2)}
        c = cues.get(n)
        if c:
            events = sorted({0.0, dur, *[it["at"] for it in c.get("items", []) if it.get("at") is not None],
                             *c.get("focus_at", []), *c.get("chips_at", [])})
            row.update(template=c["template"], beats_source=c["beats_source"],
                       cue_gap=round(max(b - a for a, b in zip(events, events[1:])), 2))
            if api_key and c.get("items"):
                words = whisper_words(root / "scenes" / f"scene_{n:03d}.mp3", api_key)
                errs = []
                for it in c["items"]:
                    t = spoken_time(it["label"], words)
                    if t is not None and it.get("at") is not None:
                        errs.append(round(abs(it["at"] + REVEAL_LEAD_S - t), 2))
                row["align_errors"] = errs
        scenes.append(row)
    total = sum(s["duration"] for s in scenes) or 1.0
    frozen = sum(s["frozen_s"] for s in scenes)
    no_still = any(s["dead_s"] is None for s in scenes)
    dead = 0 if no_still else sum(s["dead_s"] for s in scenes)
    errs = sorted(e for s in scenes for e in s.get("align_errors", []))
    return {
        "job": job_id, "scenes": scenes, "duration": round(total, 1), "frozen_share": round(frozen / total, 3),
        "still": SKIP_NUMPY if no_still else {"verdict": "measured"},
        "dead_share": None if no_still else round(dead / total, 3),
        "longest_still": None if no_still else max((s["longest_still"] for s in scenes), default=0.0),
        "scenes_still_ge_5s": None if no_still else sum(s["longest_still"] >= DEAD_MIN_S for s in scenes),
        "max_cue_gap": max((s["cue_gap"] for s in scenes if "cue_gap" in s), default=None),
        "scenes_frozen_ge_5s": sum(s["longest_frozen"] >= 5 for s in scenes),
        "beats_fallback_rate": meta.get("beats_fallback_rate"),
        "align_p50": errs[len(errs) // 2] if errs else None,
        "align_p90": errs[min(len(errs) - 1, int(len(errs) * 0.9))] if errs else None,
        "align_n": len(errs),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("videos_dir", type=Path)
    ap.add_argument("jobs", nargs="+")
    ap.add_argument("--whisper", action="store_true", help="measure cue alignment against whisper-1 word times")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    key = os.environ.get("OPENAI_API_KEY") if a.whisper else None
    if a.whisper and not key:
        print("--whisper needs OPENAI_API_KEY", file=sys.stderr)
        return 2
    results = [measure_job(a.videos_dir, j, key) for j in a.jobs]
    total = sum(r["duration"] for r in results) or 1.0
    frozen = sum(r["frozen_share"] * r["duration"] for r in results)
    no_still = any(r["dead_share"] is None for r in results)
    dead = 0 if no_still else sum(r["dead_share"] * r["duration"] for r in results)
    errs = sorted(e for r in results for s in r["scenes"] for e in s.get("align_errors", []))
    stills = [] if no_still else sorted(s["longest_still"] for r in results for s in r["scenes"])
    summary = {
        "jobs": len(results), "scenes": sum(len(r["scenes"]) for r in results), "duration_s": round(total, 1),
        "still": SKIP_NUMPY if no_still else {"verdict": "measured"},
        "dead_share": None if no_still else round(dead / total, 3),
        "longest_still_p50": stills[len(stills) // 2] if stills else None,
        "longest_still_max": stills[-1] if stills else None,
        "scenes_still_ge_5s": None if no_still else sum(r["scenes_still_ge_5s"] for r in results),
        "frozen_share": round(frozen / total, 3),
        "scenes_frozen_ge_5s": sum(r["scenes_frozen_ge_5s"] for r in results),
        "max_cue_gap": max((r["max_cue_gap"] or 0 for r in results), default=None),
        "align_p50": errs[len(errs) // 2] if errs else None,
        "align_p90": errs[min(len(errs) - 1, int(len(errs) * 0.9))] if errs else None,
        "align_n": len(errs),
    }
    for r in results:
        print(f"{r['job']}: {r['duration']:.0f}s dead {'skip (numpy missing)' if r['dead_share'] is None else format(r['dead_share'] * 100, '.0f') + '%'} longest_still {r['longest_still']} "
              f"frozen {r['frozen_share'] * 100:.0f}% "
              f"max_cue_gap {r['max_cue_gap']} fallback {r['beats_fallback_rate']} align_p90 {r['align_p90']}")
    print("SUMMARY", json.dumps(summary))
    if a.json:
        a.json.write_text(json.dumps({"summary": summary, "jobs": results}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
