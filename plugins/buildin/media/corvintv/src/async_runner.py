"""Background async job runner for video production.

The persisted VideoJob (storage) is the source of truth for status; this
runner only tracks which job ids are executing in THIS process, and forgets
them when they finish so memory does not grow with the process lifetime.
"""

import asyncio
import atexit
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

try:
    from . import deadline as dl
    from .skill import start_video_production
    from .storage import TERMINAL_STATUSES, get_storage, hold_job_lock, job_lock_path, release_job_lock
    from .style_store import write_style_snapshot
except ImportError:  # standalone script use (no package context)
    import deadline as dl
    from skill import start_video_production
    from storage import TERMINAL_STATUSES, get_storage, hold_job_lock, job_lock_path, release_job_lock
    from style_store import write_style_snapshot

logger = logging.getLogger(__name__)


class VideoProductionRunner:
    """Runs video production jobs on a small thread pool."""

    def __init__(self, max_workers: int = 3):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._running: Set[str] = set()
        self.lock = threading.Lock()

    async def start_job(self, job_id: str, task: str, config: Dict[str, Any]) -> str:
        """Schedule a job and return immediately. Failures are persisted onto
        the stored job by the orchestrator, never only kept in memory."""
        with self.lock:
            if job_id in self._running:
                raise RuntimeError(f"job {job_id} is already running")
            # held from here until the record is terminal - see storage.hold_job_lock
            job_lock = hold_job_lock(get_storage(config["storage_base"]).jobs_dir, job_id)
            self._running.add(job_id)

        # Never log the task text: it is user content.
        logger.info("[%s] scheduling background job", job_id)
        loop = asyncio.get_running_loop()
        loop.run_in_executor(self.executor, self._run_orchestrator_sync, job_id, task, config, job_lock)
        return job_id

    def _run_orchestrator_sync(self, job_id: str, task: str, config: Dict[str, Any], job_lock=None):
        try:
            asyncio.run(start_video_production(job_id, task, config))
            logger.info("[%s] job complete", job_id)
        except Exception as e:  # noqa: BLE001 — the orchestrator already persisted the error
            logger.error("[%s] job failed: %s", job_id, type(e).__name__)
        finally:
            release_job_lock(job_lock)
            with self.lock:
                self._running.discard(job_id)

    def is_job_running(self, job_id: str) -> bool:
        with self.lock:
            return job_id in self._running

    def running_job_ids(self) -> Set[str]:
        with self.lock:
            return set(self._running)

    def cancel_job(self, job_id: str) -> bool:
        """Thread mode: flag the job's budget. Its in-flight external call stops its process
        group and the job ends ``cancelled`` at the next call/scene boundary. A blocking call that
        has no kill switch (an SDK request) is ABANDONED, not killed - a thread cannot be - and the
        job ends when it returns or its deadline passes. False: this runner does not run it."""
        with self.lock:
            if job_id not in self._running:
                return False
        return dl.cancel_job_budget(job_id)

    def shutdown(self, wait: bool = True):
        logger.info("Shutting down VideoProductionRunner...")
        self.executor.shutdown(wait=wait)


_runner = None
_runner_lock = threading.Lock()


def get_runner(max_workers: int = 3) -> VideoProductionRunner:
    """Get or create the process-wide runner (singleton)."""
    global _runner
    if _runner is None:
        with _runner_lock:
            if _runner is None:
                _runner = VideoProductionRunner(max_workers=max_workers)
    return _runner


def reset_runner():
    """Reset global runner (for testing)."""
    global _runner
    with _runner_lock:
        if _runner:
            _runner.shutdown(wait=True)
        _runner = None


# ---------------------------------------------------------------------------
# ProcessJobRunner: one OS process (and process group) per job.  PLAN-0946 R1.
# ---------------------------------------------------------------------------

_JOB_MAIN = Path(__file__).resolve().with_name("job_main.py")
CANCEL_GRACE_S = 5.0
# The job enforces its own budget (deadline.JobBudget); the host kills the group this long after
# it, for a job process that is wedged somewhere no deadline reaches.
BUDGET_HOST_SLACK_S = 60.0
_IS_POSIX = os.name == "posix"
# Windows has no SIGKILL; there ``_kill_group`` ignores the signal and kills the tree (taskkill /F /T)
_SIGKILL = getattr(signal, "SIGKILL", signal.SIGTERM)
# what of a failed job process's stderr reaches the host log: its last lines, from its last bytes
STDERR_TAIL_BYTES = 8192
STDERR_TAIL_LINES = 5


def _kill_group(pid: int, sig: int) -> bool:
    """Signal a job's whole process group. False when nothing is left to signal."""
    if _IS_POSIX:
        try:
            os.killpg(pid, sig)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return False
    # Windows: the tree (taskkill /T) - UNTESTED in this spike, see the report.
    r = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=10)  # deadline-exempt: the kill itself
    return r.returncode == 0


def _stderr_tail(path: Optional[Path]) -> str:
    """The last lines a job process wrote to stderr - why it died - or "" when there is none."""
    if path is None:
        return ""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - STDERR_TAIL_BYTES))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return " | ".join(lines[-STDERR_TAIL_LINES:])


class _Child:
    __slots__ = ("proc", "storage_base", "cancelled", "over_budget", "started", "lock", "kill_timer",
                 "budget_timer", "stderr_path")

    def __init__(self, proc, storage_base: str, lock=None, stderr_path: Optional[Path] = None):
        self.proc = proc
        self.storage_base = storage_base
        self.stderr_path = stderr_path
        self.cancelled = False
        self.over_budget = False
        self.budget_timer: Optional[threading.Timer] = None
        self.started = time.monotonic()
        self.lock = lock
        self.kill_timer: Optional[threading.Timer] = None


class ProcessJobRunner:
    """Runs every job as ``job_main.py`` in its own process group; same public surface as
    VideoProductionRunner plus ``cancel_job``.

    * concurrency: at most ``max_workers`` children; further jobs queue (FIFO).
    * a reaper thread per child ``wait()``s it (no zombie), sweeps the process group for
      stragglers (a Chromium that outlived the job process) and, if the child died without a
      terminal status, writes one: ``cancelled`` after cancel_job, else ``error`` with the exit
      code / signal. It never overwrites a status the child already made terminal.
    * the job's lock (storage.hold_job_lock) is held by this process from acceptance - queued
      included - until the record is terminal; a cancel's SIGKILL timer dies with the reap.
    * the child inherits the console's environment, as the thread did. Nothing else is shared:
      the task and config reach it through a 0600 file in a 0700 per-job directory which the
      child deletes as soon as it has read it (and the reaper deletes if it never did).
    * children die with the console (job_main's parent watchdog, POSIX); a job that was running
      then is closed ``error`` by the next ``VideoStorage.mark_interrupted_jobs`` - see storage.
    """

    def __init__(self, max_workers: int = 3, *, entry: Optional[List[str]] = None,
                 grace_s: float = CANCEL_GRACE_S, env: Optional[Dict[str, str]] = None):
        self.max_workers = max_workers
        self._entry = list(entry) if entry else [sys.executable, str(_JOB_MAIN)]
        self._grace_s = grace_s
        self.budget_slack_s = BUDGET_HOST_SLACK_S
        self._env = env
        self.lock = threading.Lock()
        self._active: Dict[str, _Child] = {}
        self._queue: Deque[Tuple[str, str, Dict[str, Any], Any]] = deque()
        atexit.register(self._terminate_all)

    # -- public surface -------------------------------------------------------------------
    async def start_job(self, job_id: str, task: str, config: Dict[str, Any]) -> str:
        with self.lock:
            if job_id in self._active or any(q[0] == job_id for q in self._queue):
                raise RuntimeError(f"job {job_id} is already running")
            # held by THIS process from acceptance (queued included) until the record is terminal
            job_lock = hold_job_lock(get_storage(config["storage_base"]).jobs_dir, job_id)
            if len(self._active) >= self.max_workers:
                self._queue.append((job_id, task, config, job_lock))
                logger.info("[%s] queued (%d running)", job_id, len(self._active))
                return job_id
            try:
                self._spawn_locked(job_id, task, config, job_lock)
            except BaseException:
                release_job_lock(job_lock)
                raise
        return job_id

    def is_job_running(self, job_id: str) -> bool:
        with self.lock:
            return job_id in self._active or any(q[0] == job_id for q in self._queue)

    def running_job_ids(self) -> Set[str]:
        with self.lock:
            return set(self._active) | {q[0] for q in self._queue}

    def cancel_job(self, job_id: str) -> bool:
        """Kill the job's whole process group (SIGTERM, SIGKILL after the grace period). The job
        ends ``cancelled`` unless it had already finished. False: the runner does not know it."""
        with self.lock:
            for q in list(self._queue):
                if q[0] == job_id:
                    self._queue.remove(q)
                    self._close_job(q[2].get("storage_base"), job_id, "cancelled", "Cancelled before it started.", "cancelled")
                    release_job_lock(q[3])
                    return True
            child = self._active.get(job_id)
            if child is None:
                return False
            child.cancelled = True
            pid = child.proc.pid
            if _IS_POSIX:
                # cancelled by the reaper once the leader is reaped, so a late SIGKILL can never
                # reach a process group that has since been given to someone else
                child.kill_timer = threading.Timer(self._grace_s, _kill_group, args=(pid, _SIGKILL))
                child.kill_timer.daemon = True
        _kill_group(pid, signal.SIGTERM if _IS_POSIX else signal.SIGINT)
        if child.kill_timer is not None:
            child.kill_timer.start()
        return True

    def shutdown(self, wait: bool = True):
        logger.info("Shutting down ProcessJobRunner...")
        if not wait:
            with self.lock:
                self._queue.clear()
            self._terminate_all()
            return
        while self.running_job_ids():
            time.sleep(0.1)

    # -- internals ------------------------------------------------------------------------
    def _terminate_all(self) -> None:
        with self.lock:
            pids = [c.proc.pid for c in self._active.values()]
        for pid in pids:
            _kill_group(pid, signal.SIGKILL if _IS_POSIX else signal.SIGINT)

    def _spawn_locked(self, job_id: str, task: str, config: Dict[str, Any], job_lock=None) -> None:
        storage_base = config["storage_base"]
        storage = get_storage(storage_base)
        if self._entry[1:2] == [str(_JOB_MAIN)] and not _JOB_MAIN.is_file():
            # the plugin source this module was imported from is gone (a marketplace resync replaced it,
            # or it moved): ``python <gone>/job_main.py`` would only die with exit code 2
            raise FileNotFoundError("the CorvinTV job entry point is missing; the plugin source has moved")
        if not (_JOB_MAIN.parent / "__init__.py").is_file():
            raise FileNotFoundError("the CorvinTV plugin source is incomplete (no __init__.py); it is being replaced")
        if not Path(self._entry[0]).is_file():
            raise FileNotFoundError("the Python interpreter for the job process is gone")
        run_dir = storage.jobs_dir / f"{job_id}.run"
        err_path = storage.jobs_dir / f"{job_id}.stderr"
        err = None
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)
        os.mkdir(run_dir, 0o700)
        try:
            plain = dict(config)
            style = plain.pop("web_style", None)
            payload = {"job_id": job_id, "task": task, "src_dir": str(_JOB_MAIN.parent), "config": plain,
                       "style_dir": None}
            if style is not None:
                write_style_snapshot(style, run_dir / "style")
                payload["style_dir"] = "style"
            cfg = run_dir / "config.json"
            fd = os.open(cfg, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f)  # TypeError here = a non-JSON config member: refuse, do not guess
            # the job's own log and any interpreter error: the reaper reports its tail when the job dies
            err = os.fdopen(os.open(err_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb")
            env = dict(os.environ if self._env is None else self._env)
            env["CORVIN_VIDEO_JOB_ID"] = job_id
            env["PYTHONIOENCODING"] = "utf-8"  # the stderr capture is read as UTF-8 (Windows would write cp1252)
            kw: Dict[str, Any] = {}
            if _IS_POSIX:
                kw["start_new_session"] = True
            else:
                kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            # deadline-exempt: the host starts the job process itself; cancel, budget and reap kill its group
            proc = subprocess.Popen([*self._entry, job_id, str(cfg)], stdin=subprocess.DEVNULL, env=env,
                                    stdout=err, stderr=err, close_fds=True, **kw)
        except BaseException:
            shutil.rmtree(run_dir, ignore_errors=True)
            if err is not None:
                err.close()
            try:
                os.unlink(err_path)
            except OSError:
                pass
            raise
        err.close()  # the child holds its own handle
        child = _Child(proc, storage_base, job_lock, err_path)
        # every OS: on Windows nothing else stops a job wedged where no deadline reaches (taskkill /F /T)
        try:
            budget_s = dl.job_budget_seconds(int(config.get("max_duration_minutes", 60)))
        except (TypeError, ValueError):
            budget_s = dl.MAX_JOB_BUDGET_S
        child.budget_timer = threading.Timer(budget_s + self.budget_slack_s, self._over_budget, args=(child,))
        child.budget_timer.daemon = True
        child.budget_timer.start()
        self._active[job_id] = child
        logger.info("[%s] job process %d started", job_id, proc.pid)  # never the task text
        threading.Thread(target=self._reap, args=(job_id, child, run_dir), daemon=True,
                         name=f"vp-reaper-{job_id}").start()

    def _over_budget(self, child: _Child) -> None:
        """The job process outlived budget + slack: kill its group (the reaper records ``budget``)."""
        if child.proc.poll() is not None:
            return
        child.over_budget = True
        logger.error("job process %d exceeded its budget; killing its group", child.proc.pid)
        _kill_group(child.proc.pid, _SIGKILL)

    def _close_job(self, storage_base: Optional[str], job_id: str, status: str, message: str, reason: str) -> None:
        """Give a job that ended without a terminal status one, through the storage's single write
        path - which refuses to touch a record the child already finished."""
        def _end(job) -> None:
            job.status = status
            job.error_message = message
            job.completed_at = datetime.now()

        try:
            get_storage(storage_base).advance_job(job_id, _end, reason=reason)
        except Exception as e:  # noqa: BLE001
            logger.error("[%s] could not record the job's end (%s)", job_id, type(e).__name__)

    def _reap(self, job_id: str, child: _Child, run_dir: Path) -> None:
        rc = child.proc.wait()                       # reaps the leader: no zombie
        if child.kill_timer is not None:
            child.kill_timer.cancel()
        if child.budget_timer is not None:
            child.budget_timer.cancel()
        if _IS_POSIX:
            # stragglers (an ffmpeg that outlived the job), immediately: the group id stays ours
            # while any member lives, and the window after the last one is microseconds
            _kill_group(child.proc.pid, _SIGKILL)
        shutil.rmtree(run_dir, ignore_errors=True)   # child never started / died before deleting it
        tail = _stderr_tail(child.stderr_path) if rc != 0 and not child.cancelled else ""
        if child.stderr_path is not None:
            try:
                os.unlink(child.stderr_path)
            except OSError:
                pass
        if tail:
            logger.error("[%s] job process rc=%s, last output: %s", job_id, rc, tail)
        if child.cancelled:
            self._close_job(child.storage_base, job_id, "cancelled", "Cancelled.", "cancelled")
        elif child.over_budget:
            self._close_job(child.storage_base, job_id, "error", "The job exceeded its time budget and was stopped.", "budget")
        elif rc != 0:
            try:
                how = f"signal {signal.Signals(-rc).name}" if rc < 0 else f"exit code {rc}"
            except ValueError:  # a real-time signal has no name; the reaper must still close the job
                how = f"signal {-rc}"
            # the stderr tail says WHY (config unreadable, import failed ...); job_main never prints the task
            why = f" {tail[-300:]}" if tail else ""
            self._close_job(child.storage_base, job_id, "error", f"The job process ended unexpectedly ({how}).{why}", "child_exit")
        else:
            self._close_job(child.storage_base, job_id, "error", "The job process ended without a result.", "child_exit")
        logger.info("[%s] job process exited rc=%s", job_id, rc)
        # the record is terminal now: only then may another host see the job as unowned
        try:
            os.unlink(job_lock_path(get_storage(child.storage_base).jobs_dir, job_id))
        except OSError:
            pass
        release_job_lock(child.lock)
        with self.lock:
            self._active.pop(job_id, None)
            while self._queue and len(self._active) < self.max_workers:
                nxt = self._queue.popleft()
                try:
                    self._spawn_locked(*nxt)
                except Exception as e:  # noqa: BLE001
                    self._close_job(nxt[2].get("storage_base"), nxt[0], "error", "The job could not be started.", "start_failed")
                    release_job_lock(nxt[3])
                    logger.error("[%s] queued job could not start (%s)", nxt[0], type(e).__name__)


_process_runner: Optional[ProcessJobRunner] = None


def get_process_runner(max_workers: int = 3) -> ProcessJobRunner:
    """The process-wide ProcessJobRunner (singleton), parallel to ``get_runner``."""
    global _process_runner
    if _process_runner is None:
        with _runner_lock:
            if _process_runner is None:
                _process_runner = ProcessJobRunner(max_workers=max_workers)
    return _process_runner


def reset_process_runner():
    """Reset the global process runner (for testing)."""
    global _process_runner
    with _runner_lock:
        if _process_runner:
            _process_runner.shutdown(wait=False)
        _process_runner = None
