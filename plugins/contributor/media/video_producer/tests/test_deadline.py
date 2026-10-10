"""The deadline primitive (PLAN-0946 R1b / ADR-2247): every external call is bound, the process GROUP
is killed (SIGTERM, then SIGKILL), and nothing is left running.

Real processes throughout: stub binaries that sleep or ignore SIGTERM and keep a grandchild alive,
and a real Chromium that is SIGSTOPped mid-render. "Nothing left" is measured in /proc, by a unique
marker in the environment (children inherit it) or in the command line. POSIX/Linux only."""
import asyncio
import os
import re
import signal
import stat
import subprocess
import sys
import textwrap
import time
import uuid
from pathlib import Path

import pytest

from src import deadline as dl

pytestmark = pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc (Linux)")
SRC = Path(__file__).resolve().parents[1] / "src"


def procs_with_env(marker: str):
    needle = f"VP_MARK={marker}\0".encode()
    out = []
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                if needle in open(f"/proc/{d}/environ", "rb").read():
                    stat_ = open(f"/proc/{d}/stat").read()
                    if stat_.rsplit(")", 1)[1].split()[0] != "Z":
                        out.append(int(d))
            except OSError:
                pass
    return out


def wait_for(cond, timeout, step=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = cond()
        if v:
            return v
        time.sleep(step)
    return cond()


def stub_bin(tmp_path: Path, name: str, body: str) -> Path:
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_text("#!/bin/sh\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return d


HANG = 'trap "" TERM; sleep 600 & sleep 600\n'   # ignores SIGTERM, keeps a grandchild alive


@pytest.fixture
def mark(monkeypatch):
    m = uuid.uuid4().hex
    monkeypatch.setenv("VP_MARK", m)
    return m


# -- run_process ------------------------------------------------------------------------------

def test_a_sleeping_command_is_stopped_at_the_deadline_with_no_process_left(mark):
    t0 = time.monotonic()
    with pytest.raises(dl.DeadlineExceeded) as ei:
        dl.run_process(["sh", "-c", "sleep 600 & sleep 600"], deadline_s=1.0)
    elapsed = time.monotonic() - t0
    assert 0.9 <= elapsed <= 2.0, elapsed
    assert ei.value.elapsed <= 1.0 + 1.0
    assert wait_for(lambda: procs_with_env(mark) == [], 3), procs_with_env(mark)
    print(f"\nMEASURE sleep: deadline 1.0s, stopped after {elapsed:.2f}s, 0 processes left")


def test_a_command_that_ignores_sigterm_is_killed_with_its_grandchild(mark):
    t0 = time.monotonic()
    with pytest.raises(dl.DeadlineExceeded):
        dl.run_process(["sh", "-c", HANG], deadline_s=1.0)
    elapsed = time.monotonic() - t0
    assert elapsed <= 1.0 + 1.0, elapsed       # SIGTERM ignored -> SIGKILL after the 0.5 s grace
    assert wait_for(lambda: procs_with_env(mark) == [], 3), procs_with_env(mark)
    print(f"\nMEASURE sigterm-ignoring: deadline 1.0s, stopped after {elapsed:.2f}s, 0 processes left")


def test_inside_a_job_process_a_call_shares_the_job_group_and_its_tree_is_killed(mark, monkeypatch):
    """job_main marks the process: the host's kill of the JOB's group must reach every call's children,
    so they stay in that group; a deadline then kills the call's process tree by ancestry."""
    monkeypatch.setattr(dl, "_SHARE_JOB_GROUP", True)
    seen = {}
    real_popen = subprocess.Popen

    def spy(*a, **k):
        p = real_popen(*a, **k)
        seen["pgid"] = os.getpgid(p.pid)
        return p
    monkeypatch.setattr(subprocess, "Popen", spy)
    t0 = time.monotonic()
    with pytest.raises(dl.DeadlineExceeded):
        dl.run_process(["sh", "-c", HANG], deadline_s=1.0)
    assert seen["pgid"] == os.getpgid(0), "the call must stay in the job's process group"
    assert time.monotonic() - t0 <= 1.0 + 1.0
    assert wait_for(lambda: procs_with_env(mark) == [], 3), procs_with_env(mark)


def test_deadline_exceeded_is_the_standard_timeout_for_existing_handlers():
    with pytest.raises(subprocess.TimeoutExpired):
        dl.run_process(["sleep", "30"], deadline_s=0.3)


def test_a_normal_command_returns_output_and_exit_code():
    r = dl.run_process(["sh", "-c", "echo out; echo err >&2; exit 3"], deadline_s=5, text=True)
    assert (r.returncode, r.stdout, r.stderr) == (3, "out\n", "err\n")
    with pytest.raises(subprocess.CalledProcessError) as ei:
        dl.run_process(["sh", "-c", "echo bad >&2; exit 2"], deadline_s=5, text=True, check=True)
    assert ei.value.returncode == 2 and ei.value.cmd[0] == "sh" and "bad" in ei.value.stderr


def test_input_is_fed_on_stdin():
    assert dl.run_process(["cat"], input="hello", deadline_s=5, text=True).stdout == "hello"


def test_output_is_capped_and_the_child_does_not_block():
    t0 = time.monotonic()
    r = dl.run_process(["sh", "-c", "head -c 3000000 /dev/zero"], deadline_s=20, max_output=1000)
    assert len(r.stdout) == 1000 and r.truncated and time.monotonic() - t0 < 15


def test_a_straggler_that_outlives_the_leader_is_reaped(mark):
    # the leader exits at once; a background child keeps running in the group
    dl.run_process(["sh", "-c", "sleep 600 &"], deadline_s=5)
    assert wait_for(lambda: procs_with_env(mark) == [], 3), procs_with_env(mark)


def test_a_stopped_process_is_still_killed(mark):
    with pytest.raises(dl.DeadlineExceeded):
        dl.run_process(["sh", "-c", "kill -STOP $$"], deadline_s=0.8)
    assert wait_for(lambda: procs_with_env(mark) == [], 3), procs_with_env(mark)


def test_the_job_budget_caps_a_call_and_a_cancel_stops_it(mark):
    b = dl.JobBudget(0.8)
    t0 = time.monotonic()
    with pytest.raises(dl.DeadlineExceeded):
        dl.run_process(["sleep", "600"], deadline_s=300, budget=b)
    assert time.monotonic() - t0 <= 0.8 + 1.0
    b2 = dl.JobBudget(300)
    import threading
    threading.Timer(0.5, b2.cancel).start()
    t0 = time.monotonic()
    with pytest.raises(dl.JobCancelled):
        dl.run_process(["sh", "-c", HANG], deadline_s=300, budget=b2)
    assert time.monotonic() - t0 <= 0.5 + 1.0
    assert wait_for(lambda: procs_with_env(mark) == [], 3)
    with pytest.raises(dl.JobCancelled):
        b2.check()
    with pytest.raises(dl.DeadlineExceeded):
        dl.JobBudget(0).check()


def test_budget_seconds_is_three_times_the_limit_capped_at_2700():
    assert dl.job_budget_seconds(1) == 180
    assert dl.job_budget_seconds(5) == 900
    assert dl.job_budget_seconds(15) == 2700
    assert dl.job_budget_seconds(60) == 2700


# -- run_blocking: the deadline holds on BOTH paths ----------------------------------------------

async def _stubborn():
    """A coroutine that ignores cancellation: it blocks the loop thread."""
    time.sleep(30)


def test_run_blocking_without_a_running_loop_honours_the_deadline():
    t0 = time.monotonic()
    with pytest.raises(dl.DeadlineExceeded):
        dl.run_blocking(_stubborn, deadline_s=1.0, what="tts")
    assert time.monotonic() - t0 <= 1.0 + 1.0


def test_run_blocking_inside_a_running_loop_honours_the_deadline():
    async def outer():
        t0 = time.monotonic()
        with pytest.raises(dl.DeadlineExceeded):
            dl.run_blocking(_stubborn, deadline_s=1.0, what="tts")
        return time.monotonic() - t0
    assert asyncio.run(outer()) <= 1.0 + 1.0


def test_run_blocking_returns_values_and_reraises_errors():
    async def ok():
        await asyncio.sleep(0.01)
        return 41 + 1

    async def boom():
        raise KeyError("x")
    assert dl.run_blocking(ok, deadline_s=5) == 42

    async def outer():
        return dl.run_blocking(ok, deadline_s=5)
    assert asyncio.run(outer()) == 42
    with pytest.raises(KeyError):
        dl.run_blocking(boom, deadline_s=5)


def test_run_sync_abandons_a_call_that_cannot_be_killed():
    t0 = time.monotonic()
    with pytest.raises(dl.DeadlineExceeded):
        dl.run_sync(lambda: time.sleep(30), deadline_s=0.7, what="sdk call")
    assert time.monotonic() - t0 <= 0.7 + 1.0
    assert dl.run_sync(lambda: 7, deadline_s=5) == 7


# -- the plugin's own call sites are bound -------------------------------------------------------

def test_the_real_ffmpeg_call_sites_stop_at_their_deadline_and_leave_nothing(tmp_path, monkeypatch, mark):
    from src import skill
    bindir = stub_bin(tmp_path, "ffmpeg", HANG)
    stub_bin(tmp_path, "ffprobe", HANG)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(skill, "_FFMPEG_TIMEOUT_S", 1.0)
    monkeypatch.setattr(skill, "_FFPROBE_TIMEOUT_S", 1.0)
    img, aud = tmp_path / "a.png", tmp_path / "a.mp3"
    img.write_bytes(b"x")
    aud.write_bytes(b"x")
    calls = {
        "clip": lambda: skill._assemble_scene_clip(img, aud, tmp_path / "o.mp4"),
        "concat": lambda: skill._concat_clips([tmp_path / "o.mp4"], tmp_path / "all.mp4", tmp_path),
        "frames": lambda: skill._assemble_frames_clip(tmp_path, 1, aud, 1.0, tmp_path / "f.mp4", 30),
        "ffprobe": lambda: skill._ffprobe_duration(aud),
    }
    for name, call in calls.items():
        t0 = time.monotonic()
        with pytest.raises(dl.DeadlineExceeded):
            call()
        assert time.monotonic() - t0 <= 1.0 + 1.0, name
        assert wait_for(lambda: procs_with_env(mark) == [], 3), (name, procs_with_env(mark))


def test_silence_detection_is_bound_and_degrades_to_no_pauses(tmp_path, monkeypatch, mark):
    from src import web_timeline
    bindir = stub_bin(tmp_path, "ffmpeg", HANG)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    import src.deadline as d
    orig = d.run_process
    monkeypatch.setattr(web_timeline.dl, "run_process", lambda *a, **k: orig(*a, **{**k, "deadline_s": 1.0}))
    t0 = time.monotonic()
    res = web_timeline.detect_pauses(tmp_path / "x.mp3", 5.0)
    assert res.pause_ends == [] and time.monotonic() - t0 <= 2.0
    assert wait_for(lambda: procs_with_env(mark) == [], 3)


# -- a hung Chromium ----------------------------------------------------------------------------

def _playwright_chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.e2e
@pytest.mark.skipif(not _playwright_chromium_available(), reason="Playwright Chromium is not installed")
def test_a_hung_chromium_is_killed_with_its_driver_at_the_deadline(monkeypatch):
    """SIGSTOP the real browser mid-render: it neither answers nor dies. The render must give up at
    its deadline, and neither Chromium nor the Playwright driver may be left."""
    from src import web_renderer as wr

    monkeypatch.setattr(wr, "SCENE_TIMEOUT_S", 3.0)

    async def go():
        async with wr.WebSlideRenderer() as r:
            browsers = dl.find_processes(r._marker)
            assert browsers, "the launch flag must be visible in the browser's command line"
            for pid in browsers:
                os.kill(pid, signal.SIGSTOP)
            t0 = time.monotonic()
            with pytest.raises(wr.WebRenderError):
                await r.render("quote", {"quote": "hello", "attribution": "x"}, 2.0, Path(os.environ["VP_OUT"]))
            elapsed = time.monotonic() - t0
            assert r.dead
            return r._marker, elapsed

    out = Path(os.environ.get("TMPDIR", "/tmp")) / f"vp-hang-{uuid.uuid4().hex}"
    monkeypatch.setenv("VP_OUT", str(out))
    marker, elapsed = asyncio.run(go())
    assert elapsed <= 3.0 + 1.5, elapsed
    assert wait_for(lambda: dl.find_processes(marker) == [], 5), dl.find_processes(marker)
    me = os.getpid()
    drivers = [p for p, v in dl._proc_table().items() if v["ppid"] == me and "run-driver" in v["cmdline"]]
    assert wait_for(lambda: not [d for d in drivers if os.path.exists(f"/proc/{d}")], 5), drivers
    print(f"\nMEASURE hung chromium: deadline 3.0s, render gave up after {elapsed:.2f}s, 0 browser/driver processes left")


# -- lint: no bare subprocess in the plugin source ------------------------------------------------

_BARE = re.compile(r"\b(subprocess\.(run|Popen|call|check_call|check_output)|asyncio\.create_subprocess_(exec|shell)|os\.system|os\.popen)\s*\(")


def bare_subprocess_calls(text: str):
    """Lines that start external work without the deadline primitive. A call is allowed when the line
    or one of the two lines above it carries ``deadline-exempt: <reason>``."""
    lines = text.splitlines()
    bad = []
    for i, line in enumerate(lines):
        code = line.split("#", 1)[0]
        if _BARE.search(code) and not any("deadline-exempt" in x for x in lines[max(0, i - 2): i + 1]):
            bad.append((i + 1, line.strip()))
    return bad


def test_lint_catches_each_bare_form_and_honours_the_exemption():
    for bare in ("subprocess.run(['ls'])", "x = subprocess.Popen(cmd)", "await asyncio.create_subprocess_exec('ls')",
                 "os.system('ls')", "subprocess.check_output(['ls'])"):
        assert bare_subprocess_calls(bare), bare
    assert not bare_subprocess_calls("# deadline-exempt: why\nsubprocess.run(['ls'])")
    assert not bare_subprocess_calls("subprocess.run(['ls'])  # deadline-exempt: why")
    assert not bare_subprocess_calls("x = 'subprocess.run is banned'  # subprocess.run(")


def test_no_bare_subprocess_in_the_plugin_source():
    found = {}
    for f in sorted(SRC.rglob("*.py")):
        if f.name == "deadline.py":
            continue
        bad = bare_subprocess_calls(f.read_text(encoding="utf-8"))
        if bad:
            found[str(f.relative_to(SRC))] = bad
    assert not found, f"use src/deadline.py run_process: {found}"
