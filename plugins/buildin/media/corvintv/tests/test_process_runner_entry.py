"""ProcessJobRunner start and death diagnosis, on every OS (test_process_runner.py needs /proc).

Regression for "The job process ended unexpectedly (exit code 2)" (2026-10-19): a marketplace resync
replaced the plugin source under a running console, the runner kept starting ``python <gone>/job_main.py``
and every job died in 0.2 s with nothing in any log saying why."""
import logging
import sys
import time
from pathlib import Path

import pytest

from src import async_runner
from src.async_runner import ProcessJobRunner
from src.models import VideoJob
from src.storage import get_storage, reset_storage


@pytest.fixture
def base(tmp_path):
    reset_storage()
    b = tmp_path / "tenant"
    b.mkdir()
    yield str(b)
    reset_storage()


def mkjob(base, job_id):
    get_storage(base).save_job(VideoJob(id=job_id, task="secret task text"))
    return {"storage_base": base, "tts_engine": "auto", "max_duration_minutes": 5}


def wait_for(cond, timeout, step=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()


async def test_a_vanished_job_entry_point_is_refused_before_anything_is_spawned(base, monkeypatch):
    gone = Path(base) / "moved-away" / "job_main.py"
    monkeypatch.setattr(async_runner, "_JOB_MAIN", gone)
    r = ProcessJobRunner()  # the default entry: <python> <_JOB_MAIN>
    with pytest.raises(FileNotFoundError, match="plugin source has moved"):
        await r.start_job("job_gone0001", "secret task text", mkjob(base, "job_gone0001"))
    jobs = Path(base) / "jobs"
    assert not (jobs / "job_gone0001.run").exists()
    assert not (jobs / "job_gone0001.stderr").exists()
    assert not r.is_job_running("job_gone0001")


async def test_a_dying_job_says_why_in_the_host_log_and_leaves_no_capture(base, caplog):
    code = "import sys; sys.stderr.write('first line\\nboom: the real reason\\n'); sys.exit(3)"
    r = ProcessJobRunner(entry=[sys.executable, "-c", code])
    with caplog.at_level(logging.ERROR, logger=async_runner.logger.name):
        await r.start_job("job_dead0003", "secret task text", mkjob(base, "job_dead0003"))
        assert wait_for(lambda: get_storage(base).get_job("job_dead0003").status == "error", 30)
        assert wait_for(lambda: not r.is_job_running("job_dead0003"), 10)
    assert "exit code 3" in get_storage(base).get_job("job_dead0003").error_message
    assert "boom: the real reason" in caplog.text
    assert not (Path(base) / "jobs" / "job_dead0003.stderr").exists()


async def test_a_clean_exit_logs_no_output(base, caplog):
    code = "import sys; sys.stderr.write('chatter\\n')"
    r = ProcessJobRunner(entry=[sys.executable, "-c", code])
    with caplog.at_level(logging.ERROR, logger=async_runner.logger.name):
        await r.start_job("job_okay0000", "t", mkjob(base, "job_okay0000"))
        assert wait_for(lambda: not r.is_job_running("job_okay0000"), 30)
    assert "chatter" not in caplog.text
    assert not (Path(base) / "jobs" / "job_okay0000.stderr").exists()


def test_stderr_tail_keeps_the_last_lines_of_the_last_bytes(tmp_path):
    p = tmp_path / "e"
    p.write_bytes(b"x" * (async_runner.STDERR_TAIL_BYTES * 2) + b"\n" + b"\n".join(b"l%d" % i for i in range(20)))
    assert async_runner._stderr_tail(p) == " | ".join(f"l{i}" for i in range(15, 20))
    assert async_runner._stderr_tail(tmp_path / "missing") == ""
    assert async_runner._stderr_tail(None) == ""
