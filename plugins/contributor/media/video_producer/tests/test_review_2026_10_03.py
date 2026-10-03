"""Regression proofs for the 2026-10-03 adversarial review of the live modules
(storage / async_runner / skill). Real threads, real ffmpeg, a real subprocess
import — no mocks except where a test would otherwise reach the network.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src import skill
from src.models import VideoJob
from src.storage import VideoStorage, get_storage, reset_storage

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _fresh_stores():
    reset_storage()
    yield
    reset_storage()


# ── storage ──────────────────────────────────────────────────────────────────

def test_storage_needs_an_explicit_base_and_bases_are_isolated(tmp_path):
    with pytest.raises(ValueError):
        get_storage("")
    a = get_storage(str(tmp_path / "tenant_a"))
    b = get_storage(str(tmp_path / "tenant_b"))
    a.save_job(VideoJob(id="job_aaaaaaaa", task="t", status="pending"))
    assert b.get_job("job_aaaaaaaa") is None
    assert b.get_job_count() == 0
    assert get_storage(str(tmp_path / "tenant_a")) is a


def test_concurrent_progress_saves_never_tear_a_read(tmp_path):
    store = VideoStorage(str(tmp_path))
    job = VideoJob(id="job_tearproo", task="x" * 200_000, status="pending")
    store.save_job(job)
    stop = threading.Event()

    def writer():
        i = 0
        while not stop.is_set():
            job.percent = i % 100
            store.save_job(job)
            i += 1

    t = threading.Thread(target=writer)
    t.start()
    torn = 0
    try:
        for _ in range(1500):
            try:
                store.get_job(job.id)
            except json.JSONDecodeError:
                torn += 1
    finally:
        stop.set()
        t.join()
    assert torn == 0
    assert not list(tmp_path.joinpath("jobs").glob(".*.tmp")), "temp files left behind"


def test_one_corrupt_job_file_does_not_break_the_listing(tmp_path):
    store = VideoStorage(str(tmp_path))
    store.save_job(VideoJob(id="job_00000001", task="ok", status="complete"))
    (store.jobs_dir / "job_00000002.json").write_text('{"id": "job_000')
    jobs = store.list_jobs()
    assert [j.id for j in jobs] == ["job_00000001"]


def test_listing_order_is_creation_time_and_stable_under_progress_saves(tmp_path):
    store = VideoStorage(str(tmp_path))
    t0 = datetime(2026, 10, 1, 12, 0, 0)
    jobs = [VideoJob(id=f"job_0000000{i}", task="t", status="complete", created_at=t0 + timedelta(minutes=i))
            for i in range(4)]
    for j in jobs:
        store.save_job(j)
    page1 = [j.id for j in store.list_jobs(limit=2, offset=0)]
    store.save_job(jobs[0])  # a progress save on the OLDEST job
    page2 = [j.id for j in store.list_jobs(limit=2, offset=2)]
    assert page1 == ["job_00000003", "job_00000002"]
    assert page2 == ["job_00000001", "job_00000000"]


def test_first_open_marks_orphaned_running_jobs_as_interrupted(tmp_path):
    seed = VideoStorage(str(tmp_path))
    seed.save_job(VideoJob(id="job_0rphan01", task="t", status="skills_running"))
    seed.save_job(VideoJob(id="job_d0ne0001", task="t", status="complete"))
    store = get_storage(str(tmp_path))  # first open in this "process"
    orphan = store.get_job("job_0rphan01")
    assert orphan.status == "error"
    assert "restarted" in orphan.error_message
    assert store.get_job("job_d0ne0001").status == "complete"


# ── orchestrate_video: failures always land on the stored job ───────────────

def _run(job_store_base, job_id, **kw):
    return asyncio.run(skill.orchestrate_video(job_id=job_id, task="t", storage_base=job_store_base, **kw))


def test_missing_ffmpeg_marks_the_stored_job_error_not_pending(tmp_path, monkeypatch):
    base = str(tmp_path)
    get_storage(base).save_job(VideoJob(id="job_noffmpeg", task="t", status="pending"))
    monkeypatch.setattr(skill.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="ffmpeg"):
        _run(base, "job_noffmpeg")
    job = get_storage(base).get_job("job_noffmpeg")
    assert job.status == "error"
    assert "ffmpeg" in job.error_message


def test_unsupported_tts_engine_fails_the_job_instead_of_being_ignored(tmp_path):
    base = str(tmp_path)
    get_storage(base).save_job(VideoJob(id="job_ttsazure", task="t", status="pending"))
    with pytest.raises(ValueError, match="azure"):
        _run(base, "job_ttsazure", tts_engine="azure")
    assert get_storage(base).get_job("job_ttsazure").status == "error"


def test_storyboard_backend_is_the_hosts_choice(monkeypatch):
    def no_anthropic(*a, **k):
        raise AssertionError("Anthropic client constructed for an 'ollama' job")

    monkeypatch.setattr(skill.anthropic, "Anthropic", no_anthropic)

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": "{}"}

    seen = []
    monkeypatch.setattr(skill.requests, "post", lambda url, **k: seen.append(url) or _Resp())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "set-but-not-chosen")
    assert skill._call_storyboard_llm("p", backend="ollama") == "{}"
    assert seen and "localhost" in seen[0]
    with pytest.raises(ValueError):
        skill._call_storyboard_llm("p", backend="anthropic")  # no model from the host
    with pytest.raises(ValueError):
        skill._call_storyboard_llm("p", backend="openai")


# ── concat list quoting (real ffmpeg) ────────────────────────────────────────

@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_concat_handles_a_quote_in_the_path(tmp_path):
    work = tmp_path / "it's a dir"
    work.mkdir()
    clips = []
    for i in range(2):
        clip = work / f"c{i}.mp4"
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x64:d=0.5",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)], capture_output=True, check=True)
        clips.append(clip)
    out = work / "out.mp4"
    skill._concat_clips(clips, out, work)
    assert out.is_file() and out.stat().st_size > 0


# ── no .env side effect on import ────────────────────────────────────────────

def test_importing_skill_does_not_load_a_dotenv_into_the_process(tmp_path):
    (tmp_path / ".env").write_text("VP_REVIEW_DOTENV_PROBE=leaked\n")
    code = (
        "import os, sys; sys.path.insert(0, %r); import src.skill; "
        "print(os.environ.get('VP_REVIEW_DOTENV_PROBE', 'absent'))" % str(PLUGIN_ROOT)
    )
    env = {k: v for k, v in os.environ.items() if k != "VP_REVIEW_DOTENV_PROBE"}
    out = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path), env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "absent"
