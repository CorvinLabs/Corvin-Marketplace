#!/usr/bin/env python3
"""Measure the ``still_time`` signal against the script it was moved from, on the corpus (T-0094).

For every corpus entry of ``tests/corpus/baseline.json`` whose video is in ``<videos_dir>`` this runs
the signal's code (``src/signals.py``) over the job's scene clips, timed, and compares its dead share
with (a) the dead share the script recorded in baseline.json (2026-10-10) and (b), with ``--reference``,
the pre-move script re-run now on the same clips. Both are aggregated the script's way (per scene
rounded to 0.01 s, dead / duration over the job).

DoD (PLAN-0946 R5): agreement within 1 percentage point per job, runtime <= 15 s per minute of video.
Exit 0 when both hold, 1 when not, 2 when no corpus video was found.

Usage: still_time_agreement.py <videos_dir> [--reference <pre-move measure_engagement.py>] [--json out]
       (<videos_dir> = <tenant>/video_producer/videos)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import signals as sg  # noqa: E402

MAX_DIFF_POINTS = 1.0
MAX_S_PER_MIN = 15.0


def corpus_jobs(baseline: Path) -> List[Dict[str, Any]]:
    out = []
    for e in json.loads(baseline.read_text(encoding="utf-8"))["entries"]:
        m = re.search(r"(job_[0-9a-f]{8})", e["id"] + " " + e.get("source", ""))
        if m:
            out.append({"entry": e["id"], "job": m.group(1), "recorded_dead_share": e["measured"].get("dead_share")})
    return out


def _load_reference(path: Path):
    spec = importlib.util.spec_from_file_location("measure_engagement_reference", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dead_share(rows: List[Dict[str, Any]]) -> Optional[float]:
    total = sum(r["duration_s"] for r in rows)
    return round(sum(r["dead_s"] for r in rows) / total, 3) if total else None


def measure(videos_dir: Path, job: str, reference=None) -> Dict[str, Any]:
    clips = sorted((videos_dir / job / "scenes").glob("scene_*.mp4"))
    t0 = time.monotonic()
    rows = [sg.still_time_of_scene(c) for c in clips]
    elapsed = time.monotonic() - t0
    out: Dict[str, Any] = {"scenes": len(rows), "duration_s": round(sum(r["duration_s"] for r in rows), 2),
                           "dead_share": _dead_share(rows), "signal_s": round(elapsed, 2)}
    out["s_per_min"] = round(elapsed / (out["duration_s"] / 60.0), 2) if out["duration_s"] else None
    if reference is not None:
        ref_rows = []
        for c in clips:
            still = reference.still_stretches(c)
            ref_rows.append({"duration_s": round(reference._duration(c), 2),
                             "dead_s": round(sum(b - a for a, b in still if b - a >= reference.DEAD_MIN_S), 2)})
        out["reference_dead_share"] = _dead_share(ref_rows)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("videos_dir", type=Path)
    ap.add_argument("--baseline", type=Path, default=ROOT / "tests" / "corpus" / "baseline.json")
    ap.add_argument("--reference", type=Path, help="the pre-move scripts/measure_engagement.py")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    ref = _load_reference(a.reference) if a.reference else None
    jobs = []
    for j in corpus_jobs(a.baseline):
        if not (a.videos_dir / j["job"] / "scenes").is_dir():
            print(f"{j['entry']}: {j['job']} not in {a.videos_dir} - not measured", file=sys.stderr)
            continue
        r = {**j, **measure(a.videos_dir, j["job"], ref)}
        if r["recorded_dead_share"] is not None and r["dead_share"] is not None:
            r["diff_points_vs_recorded"] = round(abs(r["dead_share"] - r["recorded_dead_share"]) * 100, 1)
        if r.get("reference_dead_share") is not None and r["dead_share"] is not None:
            r["diff_points_vs_reference"] = round(abs(r["dead_share"] - r["reference_dead_share"]) * 100, 1)
        jobs.append(r)
        print(f"{r['entry']:<40} {r['job']} dead {r['dead_share']:.3f} recorded {r['recorded_dead_share']} "
              f"reference {r.get('reference_dead_share')} signal {r['signal_s']} s ({r['s_per_min']} s/min)")
    if not jobs:
        return 2
    total_min = sum(j["duration_s"] for j in jobs) / 60.0
    diffs = [j[k] for j in jobs for k in ("diff_points_vs_recorded", "diff_points_vs_reference") if k in j]
    summary = {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "host": {"python": platform.python_version(),
                                                                       "cpus": os.cpu_count(),
                                                                       "loadavg": list(os.getloadavg())},
        "jobs": len(jobs), "of": len(corpus_jobs(a.baseline)), "video_min": round(total_min, 2),
        "max_diff_points_vs_recorded": max((j["diff_points_vs_recorded"] for j in jobs if "diff_points_vs_recorded" in j), default=None),
        "max_diff_points_vs_reference": max((j["diff_points_vs_reference"] for j in jobs if "diff_points_vs_reference" in j), default=None),
        "pooled_s_per_min": round(sum(j["signal_s"] for j in jobs) / total_min, 2),
        "max_s_per_min": max(j["s_per_min"] for j in jobs),
        "limits": {"diff_points": MAX_DIFF_POINTS, "s_per_min": MAX_S_PER_MIN},
    }
    ok = bool(diffs) and max(diffs) <= MAX_DIFF_POINTS and summary["max_s_per_min"] <= MAX_S_PER_MIN
    summary["verdict"] = "pass" if ok else "fail"
    print("SUMMARY", json.dumps(summary))
    if a.json:
        a.json.write_text(json.dumps({"summary": summary, "jobs": jobs}, indent=1) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
