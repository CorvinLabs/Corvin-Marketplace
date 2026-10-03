"""Background async job runner for video production.

The persisted VideoJob (storage) is the source of truth for status; this
runner only tracks which job ids are executing in THIS process, and forgets
them when they finish so memory does not grow with the process lifetime.
"""

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Set

try:
    from .skill import start_video_production
except ImportError:  # standalone script use (no package context)
    from skill import start_video_production

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
            self._running.add(job_id)

        # Never log the task text: it is user content.
        logger.info("[%s] scheduling background job", job_id)
        loop = asyncio.get_running_loop()
        loop.run_in_executor(self.executor, self._run_orchestrator_sync, job_id, task, config)
        return job_id

    def _run_orchestrator_sync(self, job_id: str, task: str, config: Dict[str, Any]):
        try:
            asyncio.run(start_video_production(job_id, task, config))
            logger.info("[%s] job complete", job_id)
        except Exception as e:  # noqa: BLE001 — the orchestrator already persisted the error
            logger.error("[%s] job failed: %s", job_id, type(e).__name__)
        finally:
            with self.lock:
                self._running.discard(job_id)

    def is_job_running(self, job_id: str) -> bool:
        with self.lock:
            return job_id in self._running

    def running_job_ids(self) -> Set[str]:
        with self.lock:
            return set(self._running)

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
