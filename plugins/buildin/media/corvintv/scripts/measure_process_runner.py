#!/usr/bin/env python3
"""Measure the process runner against the thread runner (PLAN-0946 R1a go/no-go, T-0087).

Real runs only: the REAL ``job_main`` in a child process (real Chromium, real ffmpeg, a real MP4),
the TTS chain reduced to the offline mock tier through the runner's ``entry`` seam (no network, no
spend) and a fixed two-scene storyboard in the config (no model call). Nothing is estimated; every
number printed is a measurement of this run. POSIX only (/proc, process groups).

    python scripts/measure_process_runner.py [--repeat 5] [--burst 5] [--restarts 3] [--json out.json]

Sections
  startup      time from ``start_job`` to the job's first own write to its record (status leaves
               ``pending``), process vs thread runner, ``--repeat`` sequential jobs each
  wall         start_job -> terminal record, same jobs
  memory       peak RSS of a job's whole process group (leader + Chromium + ffmpeg), sampled every
               50 ms; and the host's own RSS growth when the same job runs as a thread
  concurrency  ``--burst`` jobs submitted at once: the most job leaders alive at one time (must be 3),
               all terminal, queue order
  reaping      after the burst: zombie children of this host, processes still carrying a job's id,
               leftover lock files / run directories
  restart      ``--restarts`` times: a stand-in console (tests/_vp_parent_driver.py) runs a job that is
               provably mid-flight, is SIGKILLed; time until the job's processes are gone, and what the
               next store open (``mark_interrupted_jobs``) does with the record
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import psutil

MP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MP))
from src import skill  # noqa: E402
from src.async_runner import ProcessJobRunner, VideoProductionRunner  # noqa: E402
from src.models import VideoJob  # noqa: E402
from src.storage import TERMINAL_STATUSES, get_storage, job_lock_path, reset_storage  # noqa: E402

TESTS = MP / "tests"
REAL = [sys.executable, str(TESTS / "_vp_job_main_mock_tts.py")]
STORYBOARD = {
    "id": "sb_measure", "didactic_strategy": "rich_visual",
    "scenes": [
        {"id": "s1", "kind": "title", "duration_ms": 6000,
         "narration_text": "Ein kurzer Messlauf fuer den Prozess-Runner.",
         "template": "hero", "data": {"badge": "R1a", "title": "Messlauf", "accent": "ein Prozess pro Job"}},
        {"id": "s2", "kind": "solution", "duration_ms": 6000,
         "narration_text": "Auftrag, Browser und Video laufen im eigenen Prozess.",
         "template": "diagram", "data": {"title": "Pipeline", "nodes": [{"label": "Auftrag"}, {"label": "Browser"},
                                                                          {"label": "Video"}], "highlight": 1}},
    ],
}


def procs_for(job_id: str):
    needle = f"CORVIN_VIDEO_JOB_ID={job_id}\0".encode()
    out = []
    for p in psutil.process_iter(["pid"]):
        try:
            if needle in open(f"/proc/{p.pid}/environ", "rb").read():
                out.append(p)
        except OSError:
            pass
    return out


def zombies_of_me():
    return [c.pid for c in psutil.Process().children() if c.status() == psutil.STATUS_ZOMBIE]


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def summary(xs):
    return {"n": len(xs), "median": round(statistics.median(xs), 3), "p90": round(pct(xs, 0.9), 3),
            "min": round(min(xs), 3), "max": round(max(xs), 3)} if xs else {"n": 0}


def mkjob(base: str, job_id: str):
    get_storage(base).save_job(VideoJob(id=job_id, task="measure"))
    return {"storage_base": base, "tts_engine": "auto", "max_duration_minutes": 5, "storyboard": STORYBOARD}


class GroupSampler(threading.Thread):
    """Peak summed RSS of every process carrying the job id (the job's process group)."""

    def __init__(self, job_id: str):
        super().__init__(daemon=True)
        self.job_id, self.peak, self.leader_peak, self.max_procs = job_id, 0, 0, 0
        self.stop_ev = threading.Event()

    def run(self):
        while not self.stop_ev.is_set():
            total, leader = 0, 0
            ps = procs_for(self.job_id)
            for p in ps:
                try:
                    rss = p.memory_info().rss
                    total += rss
                    if os.getpgid(p.pid) == p.pid:  # the job_main leader of its own group
                        leader = max(leader, rss)
                except (psutil.Error, OSError):
                    pass
            self.peak, self.leader_peak = max(self.peak, total), max(self.leader_peak, leader)
            self.max_procs = max(self.max_procs, len(ps))
            time.sleep(0.05)


def run_one(runner, base: str, job_id: str, *, sample: bool):
    sampler = GroupSampler(job_id) if sample else None
    if sampler:
        sampler.start()
    t0 = time.monotonic()
    asyncio.run(runner.start_job(job_id, "measure", mkjob(base, job_id)))
    store = get_storage(base)
    t_first = None
    while True:
        j = store.get_job(job_id)
        if t_first is None and j.status != "pending":
            t_first = time.monotonic() - t0
        if j.status in TERMINAL_STATUSES:
            break
        if time.monotonic() - t0 > 600:
            raise RuntimeError(f"{job_id} did not finish in 600 s")
        time.sleep(0.005)
    wall = time.monotonic() - t0
    # the record is terminal; wait until the runner has let go of the job too
    while runner.is_job_running(job_id):
        time.sleep(0.01)
    if sampler:
        sampler.stop_ev.set()
        sampler.join()
    return {"job": job_id, "status": j.status, "error": j.error_message, "first_write_s": t_first,
            "wall_s": wall, "group_peak_rss_mb": sampler and round(sampler.peak / 2**20, 1),
            "leader_peak_rss_mb": sampler and round(sampler.leader_peak / 2**20, 1),
            "max_procs_in_group": sampler and sampler.max_procs}


def measure_startup(base: str, repeat: int):
    proc_runner = ProcessJobRunner(entry=REAL)
    thread_runner = VideoProductionRunner(max_workers=3)
    skill._TTS_CHAIN = (("mock", skill._tts_tier_mock),)  # same offline tier the child uses
    me = psutil.Process()
    rows = {"process": [], "thread": []}
    for i in range(repeat):
        rows["process"].append(run_one(proc_runner, base, f"job_p{i:02d}", sample=True))
        rss_before = me.memory_info().rss
        peak = [rss_before]
        stop = threading.Event()

        def watch():
            while not stop.is_set():
                peak[0] = max(peak[0], me.memory_info().rss)
                time.sleep(0.05)
        w = threading.Thread(target=watch, daemon=True)
        w.start()
        r = run_one(thread_runner, base, f"job_t{i:02d}", sample=False)
        stop.set()
        w.join()
        r["host_rss_growth_mb"] = round((peak[0] - rss_before) / 2**20, 1)
        r["host_rss_after_mb"] = round(me.memory_info().rss / 2**20, 1)
        rows["thread"].append(r)
    thread_runner.shutdown(wait=True)
    return rows


def measure_burst(base: str, burst: int):
    runner = ProcessJobRunner(entry=REAL)
    ids = [f"job_b{i:02d}" for i in range(burst)]
    leaders_alive, order = 0, []
    t0 = time.monotonic()
    for jid in ids:
        asyncio.run(runner.start_job(jid, "measure", mkjob(base, jid)))
    store = get_storage(base)
    seen_running = set()
    while True:
        with runner.lock:
            active = set(runner._active)
        leaders_alive = max(leaders_alive, len(active))
        for jid in active - seen_running:
            seen_running.add(jid)
            order.append(jid)
        if all(store.get_job(j).status in TERMINAL_STATUSES for j in ids) and not runner.running_job_ids():
            break
        if time.monotonic() - t0 > 900:
            raise RuntimeError("burst did not finish in 900 s")
        time.sleep(0.01)
    wall = time.monotonic() - t0
    time.sleep(0.5)
    left = {j: [p.pid for p in procs_for(j)] for j in ids}
    jobs_dir = Path(base) / "jobs"
    return {
        "submitted": burst, "max_leaders_alive_at_once": leaders_alive, "start_order": order,
        "statuses": {j: store.get_job(j).status for j in ids}, "wall_s": round(wall, 2),
        "zombie_children_of_host": zombies_of_me(),
        "processes_left_with_a_job_id": {j: v for j, v in left.items() if v},
        "lock_files_left": [p.name for p in jobs_dir.glob("*.lock") if any(p.name.startswith(j) for j in ids)
                            and job_lock_path(jobs_dir, p.stem).exists()],
        "run_dirs_left": [p.name for p in jobs_dir.glob("*.run")],
    }


def measure_restart(base: str, n: int, tmp: Path):
    rows = []
    sb = tmp / "sb.json"
    sb.write_text(json.dumps(STORYBOARD))
    for i in range(n):
        jid = f"job_r{i:02d}"
        drv = subprocess.Popen([sys.executable, str(TESTS / "_vp_parent_driver.py"), base, jid, str(sb),
                                "_vp_job_main_stall_tts.py"], stdout=subprocess.PIPE,
                               stderr=open(tmp / f"driver{i}.err", "w"), text=True, start_new_session=True)
        try:
            assert drv.stdout.readline().strip() == "READY"
            end = time.monotonic() + 120
            while time.monotonic() < end:
                reset_storage()
                if procs_for(jid) and get_storage(base, mark_interrupted=False).get_job(jid).status == "skills_running":
                    break
                time.sleep(0.05)
            n_before = len(procs_for(jid))
            t0 = time.monotonic()
            os.kill(drv.pid, signal.SIGKILL)
            drv.wait()
            reset_storage()
            store = get_storage(base)  # a restarted console's first open -> mark_interrupted_jobs
            t_open = time.monotonic() - t0
            job = store.get_job(jid)
            while procs_for(jid) and time.monotonic() - t0 < 30:
                time.sleep(0.01)
            t_gone = time.monotonic() - t0
            rows.append({"job": jid, "processes_before_kill": n_before, "status_after_reopen": job.status,
                         "message": job.error_message, "store_open_closed_it_after_s": round(t_open, 3),
                         "all_processes_gone_after_s": round(t_gone, 3), "left": [p.pid for p in procs_for(jid)],
                         "run_dirs_left": [p.name for p in (Path(base) / "jobs").glob("*.run")]})
        finally:
            if drv.poll() is None:
                drv.kill()
            for p in procs_for(jid):
                try:
                    p.kill()
                except psutil.Error:
                    pass
    return rows


def main() -> int:
    if os.name != "posix" or not os.path.isdir("/proc"):
        print("needs Linux (/proc, process groups)", file=sys.stderr)
        return 2
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=5)
    ap.add_argument("--burst", type=int, default=5)
    ap.add_argument("--restarts", type=int, default=3)
    ap.add_argument("--json")
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="vp_measure_"))
    reset_storage()
    base = str(tmp / "tenant")
    os.makedirs(base)
    out = {"host": {"cpus": os.cpu_count(), "python": sys.version.split()[0],
                    "loadavg_at_start": [round(x, 2) for x in os.getloadavg()]}}
    rows = measure_startup(base, a.repeat)
    out["startup_and_wall"] = rows
    pr = [r for r in rows["process"] if r["status"] == "complete"]
    th = [r for r in rows["thread"] if r["status"] == "complete"]
    out["summary"] = {
        "complete": {"process": f"{len(pr)} of {len(rows['process'])}", "thread": f"{len(th)} of {len(rows['thread'])}"},
        "first_write_s": {"process": summary([r["first_write_s"] for r in pr]),
                          "thread": summary([r["first_write_s"] for r in th])},
        "wall_s": {"process": summary([r["wall_s"] for r in pr]), "thread": summary([r["wall_s"] for r in th])},
        "group_peak_rss_mb": summary([r["group_peak_rss_mb"] for r in pr]),
        "leader_peak_rss_mb": summary([r["leader_peak_rss_mb"] for r in pr]),
        "thread_host_rss_growth_mb": summary([r["host_rss_growth_mb"] for r in th]),
    }
    out["concurrency_and_reaping"] = measure_burst(base, a.burst)
    out["restart"] = measure_restart(base, a.restarts, tmp)
    out["host"]["loadavg_at_end"] = [round(x, 2) for x in os.getloadavg()]
    text = json.dumps(out, indent=1, default=str)
    print(text)
    if a.json:
        Path(a.json).write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
