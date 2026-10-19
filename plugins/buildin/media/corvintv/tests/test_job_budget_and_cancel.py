"""Job budget and cancel (PLAN-0946 R1b), driven through real runners and real child processes.

A stub ``ffmpeg`` on PATH hangs (ignores SIGTERM, keeps a grandchild) at the first call a job makes - the
silence scan of scene 1 - so the job is stuck in exactly the place the old code could not leave. Then:
the job budget ends it; a cancel ends it; and in both cases not one process of the job is left."""
import asyncio
import os
import stat
import sys
import time
import uuid
from pathlib import Path

import pytest

from src import deadline as dl
from src.async_runner import ProcessJobRunner, VideoProductionRunner
from src.storage import get_storage, reset_storage
from tests.test_process_runner import REAL, mkjob, procs_for, status, wait_for, zombie_children
from tests.test_style_e2e import STORYBOARD

pytestmark = pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc (Linux)")
HERE = Path(__file__).resolve().parent
SHORT = [sys.executable, str(HERE / "_vp_job_main_short_budget.py")]


@pytest.fixture
def base(tmp_path):
    reset_storage()
    b = tmp_path / "tenant"
    b.mkdir()
    yield str(b)
    reset_storage()


def hanging_ffmpeg_path(tmp_path: Path) -> str:
    d = tmp_path / "bin"
    d.mkdir()
    p = d / "ffmpeg"
    p.write_text('#!/bin/sh\ntrap "" TERM\nsleep 600 &\nsleep 600\n')
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return f"{d}{os.pathsep}{os.environ['PATH']}"


def cfg(base, job_id):
    c = mkjob(base, job_id)
    c["storyboard"] = STORYBOARD
    return c


def hung_ffmpeg_running(job_id):
    return wait_for(lambda: any(name == "sleep" for _, name in procs_for(job_id)), 60)


async def test_budget_expiry_ends_the_job_with_its_cause_and_nothing_is_left(base, tmp_path):
    env = dict(os.environ, PATH=hanging_ffmpeg_path(tmp_path), VP_TEST_BUDGET_S="5")
    r = ProcessJobRunner(entry=SHORT, env=env)
    t0 = time.monotonic()
    await r.start_job("job_bud", "t", cfg(base, "job_bud"))
    assert wait_for(lambda: status(base, "job_bud").status in ("error", "cancelled", "complete"), 60)
    elapsed = time.monotonic() - t0
    job = status(base, "job_bud")
    assert job.status == "error", job.status
    assert "budget" in (job.error_message or "").lower() or "deadline" in (job.error_message or "").lower(), job.error_message
    assert wait_for(lambda: procs_for("job_bud") == [], 10), procs_for("job_bud")
    assert elapsed <= 5 + 20, elapsed       # budget + job start-up/teardown
    assert zombie_children() == []
    print(f"\nMEASURE budget 5s: job ended 'error' after {elapsed:.1f}s ({job.error_message!r}), 0 processes left")


async def test_cancel_a_job_hung_in_ffmpeg_kills_the_group(base, tmp_path):
    env = dict(os.environ, PATH=hanging_ffmpeg_path(tmp_path))
    r = ProcessJobRunner(entry=REAL, env=env, grace_s=1.0)
    await r.start_job("job_cx", "t", cfg(base, "job_cx"))
    assert hung_ffmpeg_running("job_cx"), procs_for("job_cx")
    n = len(procs_for("job_cx"))
    t0 = time.monotonic()
    assert r.cancel_job("job_cx")
    assert wait_for(lambda: status(base, "job_cx").status == "cancelled", 10)
    assert wait_for(lambda: procs_for("job_cx") == [] and not r.is_job_running("job_cx"), 10), procs_for("job_cx")
    print(f"\nMEASURE cancel of a job hung in ffmpeg: {n} processes -> 0 in {time.monotonic() - t0:.2f}s")


async def test_thread_mode_cancel_stops_the_hung_call_and_ends_cancelled(base, tmp_path, monkeypatch):
    """The documented fallback (thread runner): the budget's cancel flag stops the in-flight external call
    (its process group is killed) and the job ends `cancelled`. Needs the offline TTS chain."""
    from src import skill
    monkeypatch.setattr(skill, "_TTS_CHAIN", (("mock", skill._tts_tier_mock),))
    monkeypatch.setenv("PATH", hanging_ffmpeg_path(tmp_path))
    marker = uuid.uuid4().hex
    monkeypatch.setenv("VP_MARK", marker)
    r = VideoProductionRunner(max_workers=1)
    c = cfg(base, "job_th")
    await r.start_job("job_th", "t", c)

    def sleepers():
        needle = f"VP_MARK={marker}\0".encode()
        out = []
        for d in os.listdir("/proc"):
            if d.isdigit():
                try:
                    if needle in open(f"/proc/{d}/environ", "rb").read() and open(f"/proc/{d}/comm").read().strip() == "sleep":
                        out.append(int(d))
                except OSError:
                    pass
        return out
    assert wait_for(lambda: sleepers(), 60)
    assert r.cancel_job("job_th") is True
    assert wait_for(lambda: status(base, "job_th").status == "cancelled", 15), status(base, "job_th").status
    assert wait_for(lambda: sleepers() == [], 10), sleepers()
    assert wait_for(lambda: not r.is_job_running("job_th"), 10)
    assert r.cancel_job("job_th") is False        # nothing running any more
    r.shutdown(wait=True)
