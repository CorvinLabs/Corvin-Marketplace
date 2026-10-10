"""One video job in its own process (PLAN-0946 R1 spike).

Started by the host's ``ProcessJobRunner`` as ``<sys.executable> job_main.py <job_id> <config.json>``
with ``start_new_session=True``, so the process is the leader of its own process group:
``ProcessJobRunner.cancel_job`` or the death of the console kills the group, and with it ffmpeg and
any blocked network call. There is no job deadline yet and no cancel route on the host (PLAN-0946
R1b), and the host still runs jobs on threads by default (``_JOB_RUNNER`` in the console route). The job persists its progress into the job record exactly as the thread did; the host
polls that record.

Security notes
- The config file holds the task text. It is created by the host with mode 0600 inside the job's
  own directory (mode 0700), is read ONCE and deleted before any work starts; the whole run directory
  (config + style snapshot) goes with it. The task is never in argv.
- The environment is the console's (the thread shared it); nothing is added to it but
  CORVIN_VIDEO_JOB_ID. No secret is written to disk by this module.
- Parent death: a watchdog thread polls the parent pid; when the console is gone it SIGKILLs the
  process group (POSIX). There is NO Windows watchdog - see ProcessJobRunner.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import logging
import os
import shutil
import signal
import stat
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

JOB_PARENT_POLL_S = 0.2
_PKG = "corvin_video_producer_job"

logger = logging.getLogger("video_producer.job")


def _drop_script_dir_from_path() -> None:
    """Run as a script, sys.path[0] is src/ - whose models.py/storage.py/web/ would shadow other
    top-level modules. The plugin is imported as a package, like the host does."""
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != here]


def load_package(src_dir: str):
    """Import the plugin source as one private package (the host's ``_load_plugin`` approach).
    The package itself pulls in only models + storage; the heavy ``skill`` import comes later."""
    src = Path(src_dir)
    spec = importlib.util.spec_from_file_location(_PKG, src / "__init__.py", submodule_search_locations=[str(src)])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[_PKG] = pkg
    spec.loader.exec_module(pkg)
    return pkg


def _read_private_json(path: Path) -> Dict[str, Any]:
    st = os.stat(path)
    if hasattr(os, "getuid"):
        if st.st_uid != os.getuid():
            raise PermissionError("job config is not owned by this user")
        if stat.S_IMODE(st.st_mode) & 0o077:
            raise PermissionError("job config is readable by others")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _watch_parent(original_ppid: int) -> None:
    """POSIX: when the console dies this process is re-parented; kill our own group (Chromium and
    ffmpeg included) rather than let a job run unobserved. SIGKILL: nothing in a dead host's job is
    worth a grace period; the job's lock was the host's and went with it."""
    while True:
        time.sleep(JOB_PARENT_POLL_S)
        if os.getppid() != original_ppid:
            try:
                if os.getpgrp() == os.getpid():
                    os.killpg(os.getpid(), signal.SIGKILL)
            finally:
                os._exit(70)


def main(argv: Optional[List[str]] = None, *, before_run: Optional[Callable[[Any], None]] = None) -> int:
    """``before_run(skill_module)`` is a test seam (e.g. swap the TTS chain); production passes none."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print("usage: job_main.py <job_id> <config.json>", file=sys.stderr)
        return 2
    job_id, cfg_path = argv[0], Path(argv[1])
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    run_dir = cfg_path.parent
    try:
        payload = _read_private_json(cfg_path)
    except Exception as e:  # noqa: BLE001
        print(f"job {job_id}: unreadable config ({type(e).__name__})", file=sys.stderr)
        shutil.rmtree(run_dir, ignore_errors=True)
        return 2

    ppid = os.getppid()
    try:
        config: Dict[str, Any] = dict(payload["config"])
        task: str = payload["task"]
        load_package(payload["src_dir"])
        storage_mod = importlib.import_module(f"{_PKG}.storage")
        # This process is not "a console that just started": it must not close the other jobs
        # of the store, nor its own not-yet-locked one.
        storage_mod.get_storage(config["storage_base"], mark_interrupted=False)
        # The job's lock is held by the host's runner from acceptance to the terminal record
        # (storage.hold_job_lock); this process dies with that host (watchdog below).
        skill = importlib.import_module(f"{_PKG}.skill")
        style_store = importlib.import_module(f"{_PKG}.style_store")
        if payload.get("style_dir"):
            config["web_style"] = style_store.load_snapshot(run_dir / payload["style_dir"])
        # everything needed is in memory: nothing sensitive stays on disk while the job runs
        shutil.rmtree(run_dir, ignore_errors=True)
        if os.name == "posix":
            threading.Thread(target=_watch_parent, args=(ppid,), daemon=True, name="parent-watch").start()
        if before_run is not None:
            before_run(skill)
        asyncio.run(skill.start_video_production(job_id, task, config))
        return 0
    except Exception as e:  # noqa: BLE001 - the orchestrator already persisted its own failure
        logger.error("[%s] job process failed: %s", job_id, type(e).__name__)
        return 1
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == "__main__":
    _drop_script_dir_from_path()
    sys.exit(main())
