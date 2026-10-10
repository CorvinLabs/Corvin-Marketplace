"""The single write path for a job record (VideoStorage.advance_job; ADR-2242 rules applied to a job).

A job PROCESS and the host's reaper write the same record. Proven here: the rules in isolation, a
200-sequence property test with two real writer processes, and call-site proofs through the real entry
points (the orchestrator's own progress writer, the reaper, cancel, mark_interrupted_jobs) including a
positive control showing the call-site test fails when the primitive is replaced by the old plain write."""
import asyncio
import multiprocessing as mp
import os
import random
import sys
import time
from pathlib import Path

import pytest

from src import skill
from src import storage as storage_mod
from src.async_runner import ProcessJobRunner
from src.models import VideoJob
from src.storage import STATUS_RANK, TERMINAL_STATUSES, VideoStorage, get_storage, reset_storage

HERE = Path(__file__).resolve().parent
STATUSES = list(STATUS_RANK)


@pytest.fixture
def store(tmp_path):
    reset_storage()
    s = VideoStorage(str(tmp_path / "t"))
    yield s
    reset_storage()


def put(store, status="pending", percent=0, jid="j1"):
    store.save_job(VideoJob(id=jid, task="t", status=status, percent=percent))
    return jid


def go(store, jid, status, percent=None, **kw):
    def m(j):
        j.status = status
        if percent is not None:
            j.percent = percent
    return store.advance_job(jid, m, **kw)


# ── the rules ────────────────────────────────────────────────────────────────────────────────
def test_terminal_is_immutable_and_late_writes_are_counted(store):
    jid = put(store)
    go(store, jid, "cancelled", reason="cancelled")
    for late in ("skills_running", "complete", "error", "pending"):
        job, applied = go(store, jid, late, 99)
        assert not applied and job.status == "cancelled"
    j = store.get_job(jid)
    assert (j.status, j.reason, j.dropped_events) == ("cancelled", "cancelled", 4)


def test_same_terminal_repeat_is_idempotent_and_not_counted(store):
    jid = put(store)
    _, a = go(store, jid, "complete", 100)
    job, b = store.advance_job(jid, lambda j: None)
    assert a and not b and job.dropped_events == 0 and job.status == "complete"


def test_lower_rank_is_dropped_and_percent_is_monotone_within_a_status(store):
    jid = put(store, "skills_running", 45)
    assert not go(store, jid, "pending", 0)[1]
    go(store, jid, "skills_running", 10)
    assert store.get_job(jid).percent == 45
    go(store, jid, "storyboard_generating", 0)       # equal rank, new status: restarts its own scale
    assert store.get_job(jid).status == "storyboard_generating" and store.get_job(jid).dropped_events == 1


def test_unknown_status_and_reason_are_rejected_nothing_written(store):
    jid = put(store)
    with pytest.raises(ValueError):
        go(store, jid, "teleported")
    with pytest.raises(ValueError):
        go(store, jid, "error", reason="because")
    assert store.get_job(jid).status == "pending"
    with pytest.raises(ValueError):
        store.save_job(VideoJob(id="new", task="t", status="nonsense"))


def test_missing_record_is_none(store):
    assert store.advance_job("nope", lambda j: None) == (None, False)


# ── property test: random interleavings from two processes ───────────────────────────────────────
def _worker(args):
    base, jid, events = args
    s = VideoStorage(base)
    seen = []
    for status, pct in events:
        go(s, jid, status, pct)
        j = s.get_job(jid)
        seen.append((j.status, j.percent))
        time.sleep(0)
    return seen


def _model(events):
    """Serial reference: the rules as a pure function."""
    st, pct, term = "pending", 0, False
    for status, p in events:
        if term:
            continue
        if STATUS_RANK[status] < STATUS_RANK[st]:
            continue
        pct = max(pct, p) if status == st else p
        st = status
        term = st in TERMINAL_STATUSES
    return st, pct


def test_property_200_sequences_two_processes(tmp_path):
    rng = random.Random(20261010)
    ctx = mp.get_context("fork")
    with ctx.Pool(2) as pool:
        for n in range(200):
            base = str(tmp_path / f"p{n}")
            s = VideoStorage(base)
            jid = put(s)
            evs = [[(rng.choice(STATUSES), rng.randint(0, 100)) for _ in range(rng.randint(1, 8))] for _ in range(2)]
            seens = pool.map(_worker, [(base, jid, evs[0]), (base, jid, evs[1])])
            final = s.get_job(jid)
            top = max(STATUS_RANK[st] for e in evs for st, _ in e)
            submitted = {st for e in evs for st, _ in e if STATUS_RANK[st] == top}
            # the highest-rank event always lands (a terminal one that landed first wins among terminals)
            assert STATUS_RANK[final.status] == top, (n, evs, final.status)
            assert final.status in submitted
            for seen in seens:                              # nobody ever observed a regression
                rank = -1
                terminal = None
                for st, pct in seen:
                    assert STATUS_RANK[st] >= rank, (n, seen)
                    rank = STATUS_RANK[st]
                    if terminal:
                        assert st == terminal, (n, seen)
                    if st in TERMINAL_STATUSES:
                        terminal = st
            if top < 2:                                      # only with no terminal is the order irrelevant to percent
                assert final.percent >= max(p for e in evs for st, p in e if st == final.status)
    # serial agreement with the model on 200 more sequences (single process, exact)
    for n in range(200):
        s = VideoStorage(str(tmp_path / f"s{n}"))
        jid = put(s)
        evs = [(rng.choice(STATUSES), rng.randint(0, 100)) for _ in range(rng.randint(1, 10))]
        for st, p in evs:
            go(s, jid, st, p)
        j = s.get_job(jid)
        assert (j.status, j.percent) == _model(evs), (n, evs)


# ── call-site proofs ─────────────────────────────────────────────────────────────────────────────
def _stale_orchestrator_scenario(tmp_path):
    """The reaper cancels a job while the orchestrator (in the child) still holds an old object and
    reports progress through the REAL skill._update_job_progress."""
    s = VideoStorage(str(tmp_path / "cs"))
    jid = put(s, "skills_running", 40)
    stale = s.get_job(jid)
    go(s, jid, "cancelled", reason="cancelled")
    skill._update_job_progress(s, stale, "skills_running", 45, "Scene 2/2: rendering slide...")
    return s.get_job(jid)


def test_the_orchestrators_progress_writer_goes_through_the_primitive(tmp_path, monkeypatch):
    j = _stale_orchestrator_scenario(tmp_path)
    assert j.status == "cancelled" and j.dropped_events == 1 and j.percent == 40
    # positive control: with the primitive replaced by the old plain overwrite the same scenario FAILS
    monkeypatch.setattr(VideoStorage, "save_job",
                        lambda self, job: storage_mod._atomic_write_json(self.jobs_dir / f"{job.id}.json", job.to_dict()))
    legacy = _stale_orchestrator_scenario(tmp_path.parent / (tmp_path.name + "_legacy"))
    assert legacy.status == "skills_running", "control: the legacy writer does resurrect a cancelled job"


def test_update_job_progress_calls_advance_job(tmp_path, monkeypatch):
    s = VideoStorage(str(tmp_path / "spy"))
    jid = put(s)
    calls = []
    real = VideoStorage.advance_job
    monkeypatch.setattr(VideoStorage, "advance_job", lambda self, *a, **k: calls.append(a[0]) or real(self, *a, **k))
    skill._update_job_progress(s, s.get_job(jid), "storyboard_generating", 5, "x")
    assert calls == [jid]


STUB = [sys.executable, str(HERE / "_vp_stub_job.py")]


def _runner(tmp_path, mode):
    env = dict(os.environ, STUB_MODE=mode, STUB_MARKS=str(tmp_path / "marks"))
    return ProcessJobRunner(entry=STUB, env=env, grace_s=1.0)


def _wait(cond, t):
    end = time.monotonic() + t
    while time.monotonic() < end and not cond():
        time.sleep(0.05)
    return cond()


async def test_reaper_does_not_overwrite_a_finished_child_that_exits_nonzero(tmp_path):
    reset_storage()
    base = str(tmp_path / "t")
    st = get_storage(base)
    put(st, jid="job_x3")
    r = _runner(tmp_path, "complete_exit3")
    await r.start_job("job_x3", "t", {"storage_base": base})
    assert _wait(lambda: not r.running_job_ids(), 15)
    j = get_storage(base).get_job("job_x3")
    assert j.status == "complete" and j.reason is None and j.dropped_events == 1   # the reaper's error was refused


async def test_cancel_after_the_child_finished_leaves_complete(tmp_path):
    reset_storage()
    base = str(tmp_path / "t")
    st = get_storage(base)
    put(st, jid="job_dh")
    r = _runner(tmp_path, "done_then_hang")
    await r.start_job("job_dh", "t", {"storage_base": base})
    assert _wait(lambda: get_storage(base).get_job("job_dh").status == "complete", 15)
    assert r.cancel_job("job_dh")
    assert _wait(lambda: not r.running_job_ids(), 15)
    j = get_storage(base).get_job("job_dh")
    assert j.status == "complete" and j.dropped_events == 1


async def test_reasons_are_recorded_by_cancel_child_exit_and_interrupt(tmp_path):
    reset_storage()
    base = str(tmp_path / "t")
    st = get_storage(base)
    for j in ("job_r1", "job_r2", "job_r3"):
        put(st, jid=j)
    r = _runner(tmp_path, "die7")
    await r.start_job("job_r1", "t", {"storage_base": base})
    assert _wait(lambda: not r.running_job_ids(), 15)
    assert st.get_job("job_r1").reason == "child_exit"
    r2 = _runner(tmp_path, "sleep")
    await r2.start_job("job_r2", "t", {"storage_base": base})
    assert _wait(lambda: (tmp_path / "marks" / "job_r2.start").exists(), 15)
    r2.cancel_job("job_r2")
    assert _wait(lambda: not r2.running_job_ids(), 15)
    assert st.get_job("job_r2").reason == "cancelled"
    reset_storage()
    assert get_storage(base).get_job("job_r3").reason == "interrupted"          # never started: closed at open
    assert get_storage(base).get_job("job_r2").status == "cancelled"            # terminal: left alone


def test_mark_interrupted_never_touches_a_terminal_job(tmp_path):
    reset_storage()
    s = VideoStorage(str(tmp_path / "t"))
    put(s, "complete", 100)
    assert s.mark_interrupted_jobs() == 0 and s.get_job("j1").status == "complete"
