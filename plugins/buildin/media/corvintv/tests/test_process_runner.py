"""ProcessJobRunner spike (PLAN-0946 R1a): every job in its own process group.

Real child processes throughout. Runner-level tests use a stub job process (tests/_vp_stub_job.py) that
keeps a grandchild in its group; the e2e tests run the REAL job_main (real Chromium, ffmpeg, MP4) with the
TTS chain reduced to the offline mock tier through the runner's ``entry`` argument. POSIX only (/proc)."""
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.async_runner import ProcessJobRunner
from src.models import VideoJob
from src.storage import get_storage, reset_storage, job_lock_path

pytestmark = pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc (Linux)")
HERE = Path(__file__).resolve().parent
STUB = [sys.executable, str(HERE / "_vp_stub_job.py")]
REAL = [sys.executable, str(HERE / "_vp_job_main_mock_tts.py")]


def procs_for(job_id):
    needle = f"CORVIN_VIDEO_JOB_ID={job_id}\0".encode()
    out = []
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                if needle in open(f"/proc/{d}/environ", "rb").read():
                    out.append((int(d), open(f"/proc/{d}/comm").read().strip()))
            except OSError:
                pass
    return out


def zombie_children():
    me, z = os.getpid(), []
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                f = open(f"/proc/{d}/stat").read()
                rest = f[f.rindex(")") + 2:].split()
                if rest[0] == "Z" and int(rest[1]) == me:
                    z.append(int(d))
            except OSError:
                pass
    return z


def wait_for(cond, timeout, step=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = cond()
        if v:
            return v
        time.sleep(step)
    return cond()


@pytest.fixture
def base(tmp_path):
    reset_storage()
    b = tmp_path / "tenant"
    b.mkdir()
    yield str(b)
    reset_storage()


def stub_runner(tmp_path, mode, secs="600", **kw):
    env = dict(os.environ, STUB_MODE=mode, STUB_SECS=secs, STUB_MARKS=str(tmp_path / "marks"))
    return ProcessJobRunner(entry=STUB, env=env, **kw)


def mkjob(base, job_id):
    get_storage(base).save_job(VideoJob(id=job_id, task="secret task text"))
    return {"storage_base": base, "tts_engine": "auto", "max_duration_minutes": 5}


def status(base, job_id):
    return get_storage(base).get_job(job_id)


async def test_nonzero_exit_before_any_write_ends_error_with_the_code(base, tmp_path):
    r = stub_runner(tmp_path, "die7")
    await r.start_job("job_d7", "secret task text", mkjob(base, "job_d7"))
    assert wait_for(lambda: status(base, "job_d7").status == "error", 15)
    assert "exit code 7" in status(base, "job_d7").error_message
    assert not (Path(base) / "jobs" / "job_d7.run").exists()


async def test_silent_exit_zero_without_result_is_an_error(base, tmp_path):
    r = stub_runner(tmp_path, "silent")
    await r.start_job("job_si", "t", mkjob(base, "job_si"))
    assert wait_for(lambda: status(base, "job_si").status == "error", 15)
    assert "without a result" in status(base, "job_si").error_message


async def test_child_status_is_never_overwritten_and_no_zombies_after_20_jobs(base, tmp_path):
    r = stub_runner(tmp_path, "quick", max_workers=3)
    ids = [f"job_q{i:02d}" for i in range(20)]
    for j in ids:
        await r.start_job(j, "t", mkjob(base, j))
    assert wait_for(lambda: not r.running_job_ids(), 60)
    assert {status(base, j).status for j in ids} == {"complete"}
    assert zombie_children() == []
    assert not list((Path(base) / "jobs").glob("*.run"))


async def test_cap_of_three_with_a_fourth_queued(base, tmp_path):
    r = stub_runner(tmp_path, "sleep", secs="600")
    for j in ("job_c1", "job_c2", "job_c3", "job_c4"):
        await r.start_job(j, "t", mkjob(base, j))
    marks = tmp_path / "marks"
    assert wait_for(lambda: len(list(marks.glob("*.start"))) == 3, 15)
    time.sleep(1.0)
    assert len(list(marks.glob("*.start"))) == 3, "a fourth child started beyond the cap"
    assert r.running_job_ids() == {"job_c1", "job_c2", "job_c3", "job_c4"}
    assert r.cancel_job("job_c1")
    assert wait_for(lambda: (marks / "job_c4.start").exists(), 15), "the queued job never got the free slot"
    for j in ("job_c2", "job_c3", "job_c4"):
        r.cancel_job(j)
    assert wait_for(lambda: not r.running_job_ids(), 20)
    assert status(base, "job_c1").status == "cancelled"
    for j in ("job_c1", "job_c2", "job_c3", "job_c4"):
        assert procs_for(j) == []


async def test_cancel_a_queued_job_never_starts_it(base, tmp_path):
    r = stub_runner(tmp_path, "sleep", max_workers=1)
    await r.start_job("job_a", "t", mkjob(base, "job_a"))
    await r.start_job("job_b", "t", mkjob(base, "job_b"))
    assert r.cancel_job("job_b") and status(base, "job_b").status == "cancelled"
    r.cancel_job("job_a")
    assert wait_for(lambda: not r.running_job_ids(), 20)
    assert not (tmp_path / "marks" / "job_b.start").exists()


async def test_cancel_kills_the_group_including_a_sigterm_ignoring_grandchild(base, tmp_path):
    r = stub_runner(tmp_path, "ignore_term", grace_s=1.0)
    await r.start_job("job_it", "t", mkjob(base, "job_it"))
    assert wait_for(lambda: len(procs_for("job_it")) >= 3, 15), procs_for("job_it")  # python, sh, sleep
    t0 = time.monotonic()
    assert r.cancel_job("job_it")
    assert wait_for(lambda: procs_for("job_it") == [] and not r.is_job_running("job_it"), 15)
    assert time.monotonic() - t0 < 5
    assert status(base, "job_it").status == "cancelled"
    assert zombie_children() == []


async def test_config_file_is_private_and_gone(base, tmp_path):
    seen = {}
    real_popen = subprocess.Popen

    class Spy(real_popen):
        def __init__(self, argv, **kw):
            cfg = Path(argv[-1])
            seen["mode"] = cfg.stat().st_mode & 0o777
            seen["dir_mode"] = cfg.parent.stat().st_mode & 0o777
            seen["argv"] = " ".join(argv)
            super().__init__(argv, **kw)

    import src.async_runner as ar
    ar.subprocess.Popen = Spy
    try:
        r = stub_runner(tmp_path, "quick")
        await r.start_job("job_pv", "secret task text", mkjob(base, "job_pv"))
    finally:
        ar.subprocess.Popen = real_popen
    assert seen["mode"] == 0o600 and seen["dir_mode"] == 0o700
    assert "secret task text" not in seen["argv"]
    assert wait_for(lambda: not r.running_job_ids(), 15)
    assert not (Path(base) / "jobs" / "job_pv.run").exists()


def test_a_non_json_config_member_is_refused_and_leaves_no_directory(base, tmp_path):
    r = stub_runner(tmp_path, "quick")
    cfg = mkjob(base, "job_nj")
    cfg["bad"] = object()
    with pytest.raises(TypeError):
        asyncio.run(r.start_job("job_nj", "t", cfg))
    assert not (Path(base) / "jobs" / "job_nj.run").exists()
    assert not r.is_job_running("job_nj")


# ── real job_main: real Chromium + ffmpeg + MP4 ─────────────────────────────────────────────────
from tests.test_style_e2e import STORYBOARD, _frame, _near  # noqa: E402
from tests.test_style_pack import make_style  # noqa: E402

pytestmark_real = pytest.mark.e2e


def real_cfg(base, job_id, **extra):
    c = mkjob(base, job_id)
    c["storyboard"] = STORYBOARD
    c.update(extra)
    return c


@pytest.mark.e2e
async def test_real_child_produces_a_styled_mp4_progress_visible_and_nothing_left(base, tmp_path):
    r = ProcessJobRunner(entry=REAL)
    st = make_style()
    t0 = time.monotonic()
    await r.start_job("job_real", "style e2e", real_cfg(base, "job_real", web_style=st))
    first = wait_for(lambda: status(base, "job_real").status != "pending", 30, 0.005)
    t_first = time.monotonic() - t0
    assert first
    seen = set()
    end = time.monotonic() + 240
    while time.monotonic() < end and status(base, "job_real").status not in ("complete", "error"):
        seen.add(status(base, "job_real").percent)
        time.sleep(0.1)
    job = status(base, "job_real")
    assert job.status == "complete", job.error_message
    assert len(seen) >= 2, f"progress never moved: {seen}"
    video = Path(job.video_output_path)
    assert video.is_file()
    hero = _frame(video, 1.5, tmp_path / "f.png")
    assert _near(hero, (0x3B, 0xA3, 0xFF), tol=70) > 150, "the style did not travel through the child"
    assert _near(hero, (0xE8, 0xA8, 0x3A)) < 30
    assert (video.parent / "style" / "style.json").is_file()
    assert wait_for(lambda: procs_for("job_real") == [], 10)
    assert not (Path(base) / "jobs" / "job_real.run").exists()
    assert not job_lock_path(Path(base) / "jobs", "job_real").exists()
    print(f"\nMEASURE first_progress_s={t_first:.3f}")


def _descendants(root: int):
    """Every live process below ``root`` (by /proc ppid)."""
    kids = {}
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                ppid = int(open(f"/proc/{d}/stat").read().rsplit(")", 1)[1].split()[1])
            except (OSError, IndexError, ValueError):
                continue
            kids.setdefault(ppid, []).append(int(d))
    out, todo = [], [root]
    while todo:
        for c in kids.get(todo.pop(), []):
            out.append(c)
            todo.append(c)
    return out


def _chromium_of(leader: int):
    """The job's browser processes. Playwright starts Chromium in its OWN process group and without the
    job's environment, so neither the group nor CORVIN_VIDEO_JOB_ID finds it - ancestry does."""
    out = []
    for pid in _descendants(leader):
        try:
            argv0 = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0", 1)[0].decode("utf-8", "replace").lower()
        except OSError:
            continue
        if "chrom" in argv0 or "headless" in argv0:
            out.append(pid)
    return out


def _alive(pids):
    return [p for p in pids if os.path.exists(f"/proc/{p}") and "Z" not in open(f"/proc/{p}/stat").read().rsplit(")", 1)[1].split()[:1]]


@pytest.mark.e2e
async def test_cancel_mid_render_leaves_no_chromium(base, tmp_path):
    r = ProcessJobRunner(entry=REAL)
    await r.start_job("job_cr", "t", real_cfg(base, "job_cr"))
    leader = r._active["job_cr"].proc.pid
    browsers = wait_for(lambda: _chromium_of(leader), 90)
    assert browsers, procs_for("job_cr")
    n_before = len(procs_for("job_cr")) + len(browsers)
    assert r.cancel_job("job_cr")
    assert wait_for(lambda: procs_for("job_cr") == [] and not r.is_job_running("job_cr"), 20), procs_for("job_cr")
    assert wait_for(lambda: _alive(browsers) == [], 20), _alive(browsers)
    assert status(base, "job_cr").status == "cancelled"
    assert zombie_children() == []
    print(f"\nMEASURE cancel: {n_before} processes in the group (incl. chromium) -> 0")


@pytest.mark.e2e
def test_parent_sigkill_children_die_and_next_open_closes_the_job(base, tmp_path):
    sb = tmp_path / "sb.json"
    sb.write_text(json.dumps(STORYBOARD))
    # the job stalls in its first narration call: it is provably running when the parent dies
    drv = subprocess.Popen([sys.executable, str(HERE / "_vp_parent_driver.py"), base, "job_pk", str(sb),
                            "_vp_job_main_stall_tts.py"],
                           stdout=subprocess.PIPE, stderr=open(tmp_path / "driver.err", "w"), text=True,
                           start_new_session=True)
    try:
        assert drv.stdout.readline().strip() == "READY"
        assert wait_for(lambda: procs_for("job_pk") and get_storage(base).get_job("job_pk").status == "skills_running", 90), (
            procs_for("job_pk"), get_storage(base).get_job("job_pk").__dict__.get("status"),
            (tmp_path / "driver.err").read_text()[-1500:])
        t0 = time.monotonic()
        os.kill(drv.pid, signal.SIGKILL)
        drv.wait()
        # the next console opens the store IMMEDIATELY, inside the children's death window
        reset_storage()
        job = get_storage(base).get_job("job_pk")
        t_open = time.monotonic() - t0
        assert job.status == "error" and "Interrupted" in job.error_message
        assert wait_for(lambda: procs_for("job_pk") == [], 10)
        t_gone = time.monotonic() - t0
        assert get_storage(base).get_job("job_pk").status == "error"  # nothing flipped it back
        assert not list((Path(base) / "jobs").glob("*.run"))  # the next store open sweeps a dead job's run dir
        print(f"\nMEASURE parent SIGKILL: store opened+closed job after {t_open:.2f}s, all processes gone after {t_gone:.2f}s")
    finally:
        if drv.poll() is None:
            drv.kill()
        for pid, _ in procs_for("job_pk"):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
