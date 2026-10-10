"""File-based storage for video jobs and outputs.

One store per base directory. The HOST decides the base (CorvinOS passes
``<tenant_home(tenant_id)>/video_producer``), so jobs of two tenants never
share a directory; there is no implicit ``~/.corvin`` default.
"""

import json
import logging
import os
import shutil
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from .models import VideoJob, VideoOutput
except ImportError:  # standalone script use (no package context)
    from models import VideoJob, VideoOutput

import contextlib
import copy

try:
    import fcntl  # POSIX only: the per-job liveness lock below has no Windows equivalent here
except ImportError:  # pragma: no cover - Windows
    fcntl = None
try:
    import msvcrt  # Windows: byte-range lock for the record lock. NOT RUN in this spike.
except ImportError:
    msvcrt = None

logger = logging.getLogger(__name__)

# How long a store open waits for a job process whose parent is already dead to
# finish dying (a child polls its parent every JOB_PARENT_POLL_S in job_main).
INTERRUPT_GRACE_S = 2.5

# Statuses after which nothing will touch the job again.
TERMINAL_STATUSES = frozenset({"complete", "error", "cancelled"})

# Status rank (the ADR-2242 message-lifecycle rule applied to a job): a record only moves up.
STATUS_RANK = {
    "pending": 0,
    "storyboard_generating": 1, "skills_running": 1,
    "complete": 2, "error": 2, "cancelled": 2,
}
# Why a job was closed by someone other than itself - a closed vocabulary, never free text.
REASONS = frozenset({"interrupted", "cancelled", "child_exit", "budget"})


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write via a same-directory temp file + os.replace, so a concurrent
    reader sees either the old or the new file, never a truncated one."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def job_lock_path(jobs_dir: Path, job_id: str) -> Path:
    return Path(jobs_dir) / f"{job_id}.lock"


def hold_job_lock(jobs_dir: Path, job_id: str):
    """Called by the HOST's runner when it accepts a job (before the job can be queued, spawned or
    run): take an exclusive flock on ``jobs/<id>.lock`` and keep the returned file object open
    until the job's record is terminal. The kernel drops the lock when the host dies for any
    reason (SIGKILL included) - and a job process dies with its host (job_main's watchdog) - so
    "is anyone still running this job" is answerable without pids, heartbeats or clocks, from any
    process, also from a second host on the same store. Taking it in the job process instead left
    a start-up window (and thread jobs had no lock at all) in which another host closed a live job
    as interrupted. Returns None where flock does not exist (Windows)."""
    if fcntl is None:
        return None
    f = open(job_lock_path(jobs_dir, job_id), "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise RuntimeError(f"job {job_id} already has a running process") from None
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    return f  # not inheritable (PEP 446): job / ffmpeg / Chromium children do not keep the lock alive


def release_job_lock(lock) -> None:
    if lock is not None:
        try:
            lock.close()
        except OSError:
            pass


def _job_process_gone(jobs_dir: Path, job_id: str, deadline: float) -> bool:
    """True when no process holds the job's lock (or there never was one). A holder is waited for
    until ``deadline``: it may be a child of a console that has just died and is about to notice."""
    if fcntl is None:
        return True
    try:
        fd = os.open(job_lock_path(jobs_dir, job_id), os.O_RDWR)
    except FileNotFoundError:
        return True
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.05)
    finally:
        os.close(fd)


class VideoStorage:
    """File-based storage for jobs and videos under one base directory."""

    def __init__(self, base_path: str):
        if not base_path:
            raise ValueError("VideoStorage needs an explicit base_path (the host's tenant directory)")
        self.base_path = Path(base_path)
        self.jobs_dir = self.base_path / "jobs"
        self.videos_dir = self.base_path / "videos"
        self.thumbnails_dir = self.base_path / "thumbnails"

        for d in (self.jobs_dir, self.videos_dir, self.thumbnails_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ── the ONE write path for a job record ──────────────────────────────────────────────────
    @contextlib.contextmanager
    def _record_lock(self, job_id: str):
        """Cross-process exclusive lock on ``jobs/.<id>.rw`` (flock; msvcrt on Windows, not run)."""
        path = self.jobs_dir / f".{job_id}.rw"
        f = open(path, "a+b")
        try:
            if fcntl is not None:
                fcntl.flock(f, fcntl.LOCK_EX)
            elif msvcrt is not None:  # pragma: no cover - Windows, untested
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            yield
        finally:
            try:
                if fcntl is None and msvcrt is not None:  # pragma: no cover
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            finally:
                f.close()

    def advance_job(self, job_id: str, mutator, *, reason: Optional[str] = None):
        """Locked read-modify-write of a job record; EVERY status write goes through here
        (``save_job`` included) so a child process and the host's reaper can write the same record.

        ``mutator(job)`` edits a fresh copy of the stored record. Rules (ADR-2242, per job):
        * unknown status -> ValueError, nothing written;
        * a terminal record is immutable: any change is dropped and counted in ``dropped_events``;
          repeating the same terminal state exactly is an idempotent no-op;
        * a lower-ranked status than the stored one is dropped and counted;
        * within one status, ``percent`` never decreases (a new status may restart its own scale);
        * the write is an atomic replace.
        ``reason`` (one of REASONS) is recorded when this call makes the record terminal.
        Returns ``(job, applied)``; ``(None, False)`` when the record does not exist."""
        if reason is not None and reason not in REASONS:
            raise ValueError(f"unknown reason {reason!r}")
        with self._record_lock(job_id):
            cur = self.get_job(job_id)
            if cur is None:
                return None, False
            new = copy.deepcopy(cur)
            mutator(new)
            if new.status not in STATUS_RANK:
                raise ValueError(f"unknown job status {new.status!r}")
            if cur.status in TERMINAL_STATUSES:
                if new.to_dict() != cur.to_dict():
                    cur.dropped_events += 1
                    _atomic_write_json(self.jobs_dir / f"{job_id}.json", cur.to_dict())
                return cur, False
            if STATUS_RANK[new.status] < STATUS_RANK[cur.status]:
                cur.dropped_events += 1
                _atomic_write_json(self.jobs_dir / f"{job_id}.json", cur.to_dict())
                return cur, False
            if new.status == cur.status:
                new.percent = max(new.percent or 0, cur.percent or 0)
            new.dropped_events = cur.dropped_events
            new.reason = cur.reason
            if new.status in TERMINAL_STATUSES:
                new.reason = reason
            _atomic_write_json(self.jobs_dir / f"{job_id}.json", new.to_dict())
            return new, True

    def save_job(self, job: VideoJob):
        """Save VideoJob to disk. A new record is created; an existing one only ever advances
        (see advance_job) - a stale writer cannot undo a newer status. The caller's object is
        updated to what was actually stored."""
        if not (self.jobs_dir / f"{job.id}.json").exists():
            with self._record_lock(job.id):
                if not (self.jobs_dir / f"{job.id}.json").exists():
                    if job.status not in STATUS_RANK:
                        raise ValueError(f"unknown job status {job.status!r}")
                    _atomic_write_json(self.jobs_dir / f"{job.id}.json", job.to_dict())
                    return

        def _take(cur: VideoJob) -> None:
            for k, v in job.__dict__.items():
                if k not in ("reason", "dropped_events"):
                    setattr(cur, k, copy.deepcopy(v))

        stored, _ = self.advance_job(job.id, _take)
        if stored is not None:
            for k, v in stored.__dict__.items():
                setattr(job, k, v)

    def get_job(self, job_id: str) -> Optional[VideoJob]:
        """Retrieve VideoJob from disk."""
        job_file = self.jobs_dir / f"{job_id}.json"
        if not job_file.exists():
            return None
        with open(job_file, "r") as f:
            return VideoJob.from_dict(json.load(f))

    def _all_jobs(self) -> List[VideoJob]:
        jobs: List[VideoJob] = []
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file, "r") as f:
                    jobs.append(VideoJob.from_dict(json.load(f)))
            except (OSError, ValueError, KeyError, TypeError) as e:
                # One unreadable file must not take the whole listing down;
                # it is reported, not silently repaired.
                logger.warning("video storage: skipping unreadable job file %s (%s)", job_file.name, type(e).__name__)
        return jobs

    def list_jobs(self, limit: int = 20, offset: int = 0) -> List[VideoJob]:
        """List jobs, newest first by creation time (stable under progress saves)."""
        jobs = sorted(self._all_jobs(), key=lambda j: (j.created_at, j.id), reverse=True)
        return jobs[offset: offset + limit]

    def count_by_status(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for j in self._all_jobs():
            counts[j.status] = counts.get(j.status, 0) + 1
        return counts

    def get_job_count(self) -> int:
        """Get total number of jobs."""
        return len(list(self.jobs_dir.glob("*.json")))

    def delete_job(self, job_id: str):
        """Delete job metadata."""
        job_file = self.jobs_dir / f"{job_id}.json"
        if job_file.exists():
            job_file.unlink()
        for side in (f".{job_id}.rw", f"{job_id}.lock"):
            try:
                (self.jobs_dir / side).unlink()
            except OSError:
                pass

    def save_video_output(self, video_output: VideoOutput):
        """Save video metadata (atomic)."""
        output_dir = self.videos_dir / video_output.job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(output_dir / "metadata.json", video_output.to_dict())

    def get_video_output(self, job_id: str) -> Optional[VideoOutput]:
        """Retrieve video metadata."""
        output_file = self.videos_dir / job_id / "metadata.json"
        if not output_file.exists():
            return None
        with open(output_file, "r") as f:
            return VideoOutput.from_dict(json.load(f))

    def get_video_path(self, job_id: str) -> Optional[Path]:
        """Get path to video file."""
        video_output = self.get_video_output(job_id)
        if video_output and video_output.video_path:
            return Path(video_output.video_path)
        return None

    def mark_interrupted_jobs(self) -> int:
        """Close every non-terminal job whose process is gone. Called once, when this process
        first opens the store. A job run by a thread of a previous console has no process left
        and no lock: closed, as before. A job run by a job process (ProcessJobRunner) holds
        ``jobs/<id>.lock`` while it lives: if the lock is free it is closed; if it is held, the
        holder is given INTERRUPT_GRACE_S to die (children die with their console) and a holder
        that is still alive then belongs to another live host and is left alone."""
        n = 0
        deadline = time.monotonic() + INTERRUPT_GRACE_S
        for job in self._all_jobs():
            if job.status in TERMINAL_STATUSES:
                continue
            if not _job_process_gone(self.jobs_dir, job.id, deadline):
                logger.warning("video storage: job %s is still running in another process, left alone", job.id)
                continue
            def _close(j: VideoJob) -> None:
                j.status = "error"
                j.error_message = "Interrupted: the console process restarted while this job was running."
                j.completed_at = j.completed_at or datetime.now()

            _, applied = self.advance_job(job.id, _close, reason="interrupted")
            n += 1 if applied else 0
            # a job process killed before it read its config leaves the task text (0600) behind
            shutil.rmtree(self.jobs_dir / f"{job.id}.run", ignore_errors=True)
        return n


_stores: Dict[str, VideoStorage] = {}
_stores_lock = threading.Lock()


def get_storage(base_path: str, *, mark_interrupted: bool = True) -> VideoStorage:
    """The store for ``base_path`` (one instance per directory per process). The host's first open
    closes orphaned jobs; a job PROCESS opens with ``mark_interrupted=False`` (it is not a restart)."""
    if not base_path:
        raise ValueError("get_storage() needs the host's tenant base path")
    key = str(Path(base_path).resolve())
    with _stores_lock:
        store = _stores.get(key)
        if store is None:
            store = VideoStorage(key)
            interrupted = store.mark_interrupted_jobs() if mark_interrupted else 0
            if interrupted:
                logger.warning("video storage: marked %d orphaned job(s) as interrupted in %s", interrupted, key)
            _stores[key] = store
        return store


def reset_storage():
    """Forget all store instances (for testing)."""
    with _stores_lock:
        _stores.clear()
