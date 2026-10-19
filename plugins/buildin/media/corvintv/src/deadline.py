"""The one way the plugin runs external work with a deadline (ADR-2247, PLAN-0946 R1b).

A thread cannot be killed and a bare ``subprocess.run(timeout=)`` only kills the direct child
(ffmpeg's helpers, a shell, a browser driver live on). Everything here therefore works on a
whole PROCESS GROUP:

* ``run_process``  - run a command in its own session; on expiry SIGTERM the group, then SIGKILL
  it after ``KILL_GRACE_S``; raise ``DeadlineExceeded`` with the elapsed time. Output is capped.
* ``run_blocking`` - run a coroutine from synchronous code with a deadline that holds on BOTH
  paths (with or without a running loop) and never waits for a coroutine that ignores
  cancellation: the worker is a daemon thread that is abandoned after the deadline.
* ``await_with_deadline`` - the async twin: ``asyncio.wait_for`` waits for the cancelled task to
  finish, which a hung browser never lets it do; this one gives up, runs ``on_expire`` (the hard
  kill) and only then gives the task a short moment to unwind.
* ``JobBudget``    - one wall-clock budget per job, handed to every call; ``cancel()`` is the
  thread-mode cancel (process mode kills the job's group from outside instead).
* ``kill_process_tree`` / ``find_processes`` - for children the plugin does not start itself
  (Playwright's driver and Chromium start in their own groups).

``DeadlineExceeded`` subclasses ``subprocess.TimeoutExpired`` so a caller that already handles
the standard timeout keeps working.
"""

from __future__ import annotations

import asyncio
import contextvars
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

KILL_GRACE_S = 0.5            # SIGTERM -> SIGKILL
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_JOB_BUDGET_S = 2700.0
_IS_POSIX = os.name == "posix"
_POLL_S = 0.1


# The budget of the job running in this context (set by the orchestrator). Every helper below
# falls back to it, so a call deep inside the pipeline is bound without threading a parameter.
_CURRENT_BUDGET: "contextvars.ContextVar[Optional[JobBudget]]" = contextvars.ContextVar("vp_job_budget", default=None)


def current_budget() -> "Optional[JobBudget]":
    return _CURRENT_BUDGET.get()


def set_current_budget(budget: "Optional[JobBudget]"):
    """Returns the token for ``reset_current_budget``."""
    return _CURRENT_BUDGET.set(budget)


def reset_current_budget(token) -> None:
    _CURRENT_BUDGET.reset(token)


_BUDGETS: Dict[str, "JobBudget"] = {}
_BUDGETS_LOCK = threading.Lock()


def register_job_budget(job_id: str, budget: "JobBudget") -> None:
    with _BUDGETS_LOCK:
        _BUDGETS[job_id] = budget


def unregister_job_budget(job_id: str) -> None:
    with _BUDGETS_LOCK:
        _BUDGETS.pop(job_id, None)


def cancel_job_budget(job_id: str) -> bool:
    """Thread-mode cancel: flag the job's budget; its in-flight call stops its process group and
    the job ends ``cancelled``. False when no job of this process has that id."""
    with _BUDGETS_LOCK:
        b = _BUDGETS.get(job_id)
    if b is None:
        return False
    b.cancel()
    return True


def job_budget_seconds(max_duration_minutes: int) -> float:
    """``min(3 x max_duration_minutes x 60, 2700)`` seconds (PLAN-0946 R1)."""
    return float(min(3 * int(max_duration_minutes) * 60, MAX_JOB_BUDGET_S))


class DeadlineExceeded(subprocess.TimeoutExpired):
    """A deadline ran out. ``elapsed`` is what was actually spent, ``what`` names the step."""

    def __init__(self, cmd: Any, deadline_s: float, elapsed: float, what: str = "", output: Any = None, stderr: Any = None):
        super().__init__(cmd, deadline_s, output=output, stderr=stderr)
        self.elapsed = elapsed
        self.what = what or (cmd[0] if isinstance(cmd, (list, tuple)) and cmd else str(cmd))

    def __str__(self) -> str:
        return f"{self.what} exceeded its {self.timeout:g}s deadline (stopped after {self.elapsed:.1f}s)"


class JobCancelled(Exception):
    """The job was cancelled while a call was in flight (thread mode; process mode kills the group)."""


class JobBudget:
    """One wall-clock budget for a whole job. Thread-safe; ``remaining()`` caps every call."""

    def __init__(self, total_s: float):
        self.total_s = float(total_s)
        self.started = time.monotonic()
        self._cancel = threading.Event()

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def remaining(self) -> float:
        return max(0.0, self.total_s - self.elapsed())

    def expired(self) -> bool:
        return self.remaining() <= 0.0

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def check(self, what: str = "job") -> None:
        if self.cancelled:
            raise JobCancelled(what)
        if self.expired():
            raise DeadlineExceeded(what, self.total_s, self.elapsed(), what=f"job budget ({what})")

    def clamp(self, deadline_s: float) -> float:
        """The effective deadline of one call: its own, but never beyond the job's budget."""
        self.check()
        return min(float(deadline_s), self.remaining())


@dataclass
class ProcessResult:
    returncode: int
    stdout: Any
    stderr: Any
    elapsed: float
    truncated: bool = False

    @property
    def args(self):  # CompletedProcess look-alike
        return None


# --------------------------------------------------------------------------------------
# process-group primitives
# --------------------------------------------------------------------------------------

# Inside a job process (job_main) the host kills the JOB'S process group on cancel, budget expiry
# and console death. A child started in a group of its own would be orphaned by that kill, so there
# a child stays in the job's group and a deadline kills its process TREE (/proc ancestry) instead.
# In the console process (thread mode) every call gets its own session and the group is killed.
_SHARE_JOB_GROUP = False


def mark_job_process() -> None:
    """Called once by ``job_main``: this process is a job process; children share its group."""
    global _SHARE_JOB_GROUP
    _SHARE_JOB_GROUP = True


def _shares_group() -> bool:
    return _IS_POSIX and _SHARE_JOB_GROUP and os.path.isdir("/proc")


def _signal_group(pgid: int, sig: int) -> bool:
    try:
        os.killpg(pgid, sig)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _kill_proc_group(proc: "subprocess.Popen", grace_s: float = KILL_GRACE_S, shared: bool = False) -> None:
    """SIGTERM, wait up to ``grace_s`` for the leader, then SIGKILL - the call's whole group, or (inside
    a job process, ``shared``) its process tree. Always SIGKILLs at the end, also when the leader died,
    because a straggler may outlive it. Reaps the leader."""
    if shared:
        kill_process_tree([proc.pid], grace_s)
    elif _IS_POSIX:
        pgid = proc.pid  # start_new_session=True: the leader's pid is the group id
        _signal_group(pgid, signal.SIGTERM)
        _signal_group(pgid, signal.SIGCONT)  # a stopped process takes SIGTERM only when continued
        try:
            proc.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            pass
        _signal_group(pgid, signal.SIGKILL)  # stragglers + a leader that ignored SIGTERM
    else:  # pragma: no cover - Windows: the whole tree
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=10)  # noqa: S603,S607  # deadline-exempt: the kill itself
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover
        pass


def _read_capped(stream, cap: int, sink: List[bytes], flag: List[bool]) -> None:
    got = 0
    try:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                return
            room = cap - got
            if room > 0:
                sink.append(chunk[:room])
                got += min(room, len(chunk))
            if len(chunk) > room:
                flag[0] = True  # keep draining so the child never blocks on a full pipe
    except (OSError, ValueError):
        return


def run_process(
    cmd: Sequence[str],
    *,
    deadline_s: float,
    input: Any = None,
    budget: Optional[JobBudget] = None,
    text: bool = False,
    check: bool = False,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    max_output: int = MAX_OUTPUT_BYTES,
    what: str = "",
    grace_s: float = KILL_GRACE_S,
) -> ProcessResult:
    """Run ``cmd`` to completion within ``deadline_s`` (and the job budget, if any).

    The command runs in its own session. On expiry the whole group is SIGTERMed, then SIGKILLed,
    and ``DeadlineExceeded`` is raised after at most ``deadline_s + grace_s`` (+ scheduling).
    A cancelled budget raises ``JobCancelled`` the same way. ``check=True`` raises
    ``subprocess.CalledProcessError`` on a non-zero exit, like ``subprocess.run``. Output is
    capped at ``max_output`` bytes per stream (the rest is drained and dropped; ``truncated``)."""
    budget = budget if budget is not None else current_budget()
    if budget is not None:
        deadline_s = budget.clamp(deadline_s)
    deadline_s = float(deadline_s)
    kw: Dict[str, Any] = {}
    shared = _shares_group()
    if _IS_POSIX and not shared:
        kw["start_new_session"] = True
    elif not _IS_POSIX:  # pragma: no cover
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    start = time.monotonic()
    data = None
    if input is not None:
        data = input.encode("utf-8") if isinstance(input, str) else bytes(input)
    proc = subprocess.Popen(  # deadline-exempt: this IS the primitive
        list(cmd), stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env, close_fds=True, **kw,
    )
    out: List[bytes] = []
    err: List[bytes] = []
    trunc = [False]
    threads = [threading.Thread(target=_read_capped, args=(proc.stdout, max_output, out, trunc), daemon=True),
               threading.Thread(target=_read_capped, args=(proc.stderr, max_output, err, trunc), daemon=True)]
    if data is not None:
        def _feed() -> None:
            try:
                proc.stdin.write(data)
            except OSError:
                pass
            finally:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
        threads.append(threading.Thread(target=_feed, daemon=True))
    for t in threads:
        t.start()
    expired = cancelled = False
    try:
        while True:
            left = deadline_s - (time.monotonic() - start)
            if left <= 0:
                expired = True
                break
            if budget is not None and budget.cancelled:
                cancelled = True
                break
            try:
                proc.wait(timeout=min(_POLL_S, left))
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        # always: a normal exit may still have left group members (a helper that outlived it)
        if expired or cancelled or proc.poll() is None:
            _kill_proc_group(proc, grace_s, shared)
        elif _IS_POSIX and not shared:
            _signal_group(proc.pid, signal.SIGKILL)
        for t in threads:
            t.join(timeout=2.0)
        for s in (proc.stdout, proc.stderr):
            try:
                s.close()
            except OSError:
                pass
    elapsed = time.monotonic() - start
    so, se = b"".join(out), b"".join(err)
    if text:
        so, se = so.decode("utf-8", "replace"), se.decode("utf-8", "replace")
    if cancelled:
        raise JobCancelled(what or str(cmd[0]))
    if expired:
        raise DeadlineExceeded(list(cmd), deadline_s, elapsed, what=what, output=so, stderr=se)
    rc = proc.returncode
    if check and rc != 0:
        raise subprocess.CalledProcessError(rc, list(cmd), output=so, stderr=se)
    return ProcessResult(rc, so, se, elapsed, trunc[0])


# --------------------------------------------------------------------------------------
# coroutines
# --------------------------------------------------------------------------------------

def run_blocking(make_coro: Callable[[], Awaitable[Any]], *, deadline_s: float,
                 budget: Optional[JobBudget] = None, what: str = "coroutine") -> Any:
    """Run ``make_coro()`` to completion from synchronous code; give up after ``deadline_s``.

    One code path for both situations the old helper split on: the coroutine always runs on its
    own loop in a daemon worker thread, so the caller is bound by ``deadline_s`` whether or not a
    loop runs in the calling thread, and a coroutine that ignores cancellation cannot hold the
    caller (the worker is abandoned - a thread cannot be killed; in process mode the job's group
    kill ends it). The abandon is logged by the raised ``DeadlineExceeded``."""
    budget = budget if budget is not None else current_budget()
    if budget is not None:
        deadline_s = budget.clamp(deadline_s)
    box: Dict[str, Any] = {}
    done = threading.Event()
    loop_box: List[Any] = []

    def _work() -> None:
        loop = asyncio.new_event_loop()
        loop_box.append(loop)
        try:
            box["value"] = loop.run_until_complete(make_coro())
        except BaseException as e:  # noqa: BLE001 - handed to the caller
            box["error"] = e
        finally:
            try:
                loop.close()
            except Exception:  # noqa: BLE001
                pass
            done.set()

    start = time.monotonic()
    threading.Thread(target=_work, daemon=True, name=f"vp-blocking-{what}").start()
    while True:
        left = deadline_s - (time.monotonic() - start)
        if done.wait(timeout=max(0.0, min(_POLL_S, left))):
            break
        if budget is not None and budget.cancelled:
            _cancel_loop(loop_box)
            raise JobCancelled(what)
        if left <= 0:
            _cancel_loop(loop_box)
            raise DeadlineExceeded(what, deadline_s, time.monotonic() - start, what=what)
    if "error" in box:
        raise box["error"]
    return box.get("value")


def run_sync(fn: Callable[[], Any], *, deadline_s: float, budget: Optional[JobBudget] = None, what: str = "call") -> Any:
    """Run a blocking synchronous callable (an SDK call with no kill switch) with a deadline.
    The callable runs in a daemon thread that is ABANDONED on expiry - it cannot be killed; the
    job process's group kill ends it for real."""
    box: Dict[str, Any] = {}
    done = threading.Event()
    budget = budget if budget is not None else current_budget()
    if budget is not None:
        deadline_s = budget.clamp(deadline_s)

    def _work() -> None:
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001
            box["error"] = e
        finally:
            done.set()

    start = time.monotonic()
    threading.Thread(target=_work, daemon=True, name=f"vp-sync-{what}").start()
    while True:
        left = deadline_s - (time.monotonic() - start)
        if done.wait(timeout=max(0.0, min(_POLL_S, left))):
            break
        if budget is not None and budget.cancelled:
            raise JobCancelled(what)
        if left <= 0:
            raise DeadlineExceeded(what, deadline_s, time.monotonic() - start, what=what)
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _cancel_loop(loop_box: List[Any]) -> None:
    if not loop_box:
        return
    loop = loop_box[0]

    def _cancel_all() -> None:
        for t in asyncio.all_tasks(loop):
            t.cancel()
    try:
        loop.call_soon_threadsafe(_cancel_all)
    except RuntimeError:
        pass


async def await_with_deadline(awaitable: Awaitable[Any], deadline_s: float, *, what: str = "operation",
                              on_expire: Optional[Callable[[], None]] = None, unwind_s: float = 2.0) -> Any:
    """``asyncio.wait_for`` that cannot be held hostage by its own cancellation.

    On expiry ``on_expire`` runs FIRST (kill whatever the task is waiting on - a hung browser),
    then the task is cancelled and given ``unwind_s`` to finish; a task that still has not is
    left behind. Raises ``DeadlineExceeded``."""
    task = asyncio.ensure_future(awaitable)
    start = time.monotonic()
    done, _ = await asyncio.wait({task}, timeout=max(0.0, deadline_s))
    if task in done:
        return task.result()
    if on_expire is not None:
        try:
            on_expire()
        except Exception:  # noqa: BLE001 - the kill must not hide the deadline
            pass
    task.cancel()
    await asyncio.wait({task}, timeout=unwind_s)
    if task.done() and not task.cancelled():
        try:
            task.exception()  # retrieved: no "never retrieved" noise
        except Exception:  # noqa: BLE001
            pass
    raise DeadlineExceeded(what, deadline_s, time.monotonic() - start, what=what)


# --------------------------------------------------------------------------------------
# processes the plugin did not start itself (Playwright driver + Chromium)
# --------------------------------------------------------------------------------------

def _proc_table() -> Dict[int, Dict[str, Any]]:
    table: Dict[int, Dict[str, Any]] = {}
    if not os.path.isdir("/proc"):
        return table
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat", "rb") as f:
                raw = f.read().decode("utf-8", "replace")
            rest = raw[raw.rindex(")") + 2:].split()
            with open(f"/proc/{d}/cmdline", "rb") as f:
                cmdline = f.read().replace(b"\0", b" ").decode("utf-8", "replace")
            table[int(d)] = {"ppid": int(rest[1]), "cmdline": cmdline}
        except (OSError, ValueError, IndexError):
            continue
    return table


def find_processes(marker: str) -> List[int]:
    """Pids whose command line contains ``marker`` (Linux; empty elsewhere)."""
    me = os.getpid()
    return [pid for pid, p in _proc_table().items() if pid != me and marker in p["cmdline"]]


def kill_process_tree(roots: Sequence[int], grace_s: float = KILL_GRACE_S) -> List[int]:
    """SIGTERM (+SIGCONT), then SIGKILL, every process in the trees under ``roots`` (roots
    included). Linux /proc walk; returns the pids it signalled. Never signals this process."""
    if not _IS_POSIX:
        return []
    me = os.getpid()
    table = _proc_table()
    kids: Dict[int, List[int]] = {}
    for pid, p in table.items():
        kids.setdefault(p["ppid"], []).append(pid)
    victims: List[int] = []
    stack = [r for r in roots if r != me]
    while stack:
        pid = stack.pop()
        if pid in victims or pid == me:
            continue
        victims.append(pid)
        stack.extend(kids.get(pid, []))
    for sig in (signal.SIGTERM, signal.SIGCONT):
        for pid in victims:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
    end = time.monotonic() + grace_s
    while time.monotonic() < end and any(os.path.exists(f"/proc/{p}") and not _is_zombie(p) for p in victims):
        time.sleep(0.02)
    for pid in victims:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    return victims


def _is_zombie(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            raw = f.read().decode("utf-8", "replace")
        return raw[raw.rindex(")") + 2:].split()[0] == "Z"
    except (OSError, IndexError):
        return True


def kill_marked(marker: str, *, driver_hint: str = "run-driver") -> List[int]:
    """Kill every process carrying ``marker`` in its command line together with the Playwright
    driver above it (the node process whose command line has ``driver_hint``) and everything
    below. This is how a hung Chromium is ended: Playwright starts it in its own process group,
    so no group kill of ours reaches it. Linux only; returns the pids signalled (empty elsewhere)."""
    table = _proc_table()
    me = os.getpid()
    roots = set()
    for pid, p in table.items():
        if pid == me or marker not in p["cmdline"]:
            continue
        top, cur = pid, pid
        while True:
            parent = table.get(cur, {}).get("ppid")
            if parent is None or parent in (0, 1, me) or parent not in table:
                break
            if driver_hint in table[parent]["cmdline"]:
                top = parent
            cur = parent
        roots.add(top)
    return kill_process_tree(sorted(roots)) if roots else []
