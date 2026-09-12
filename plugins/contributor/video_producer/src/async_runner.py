"""Background async job runner for video production."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, Any, Optional, Callable
import threading

from .skill import start_video_production

logger = logging.getLogger(__name__)


class VideoProductionRunner:
    """Manages async video production jobs in background."""

    def __init__(self, max_workers: int = 3):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.running_jobs: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.progress_callback: Optional[Callable] = None

    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates (for WebSocket broadcast)."""
        self.progress_callback = callback

    async def start_job(
        self,
        job_id: str,
        task: str,
        config: Dict[str, Any]
    ) -> str:
        """
        Start a video production job in background.

        Returns immediately with job_id.
        Orchestration happens asynchronously.
        """
        with self.lock:
            self.running_jobs[job_id] = {
                "status": "starting",
                "created_at": datetime.now(),
                "task": task,
                "progress": 0,
                "error": None,
            }

        logger.info(f"[{job_id}] Starting background job: {task[:50]}...")

        # Run orchestrator in background
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            self.executor,
            self._run_orchestrator_sync,
            job_id,
            task,
            config
        )

        return job_id

    def _run_orchestrator_sync(
        self,
        job_id: str,
        task: str,
        config: Dict[str, Any]
    ):
        """Wrapper to run async orchestrator in sync context."""
        try:
            asyncio.run(start_video_production(job_id, task, config))

            with self.lock:
                self.running_jobs[job_id]["status"] = "complete"
                self.running_jobs[job_id]["completed_at"] = datetime.now()
                self.running_jobs[job_id]["progress"] = 100

            logger.info(f"[{job_id}] Job complete")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[{job_id}] Job failed: {error_msg}", exc_info=True)

            with self.lock:
                self.running_jobs[job_id]["status"] = "error"
                self.running_jobs[job_id]["error"] = error_msg
                self.running_jobs[job_id]["completed_at"] = datetime.now()

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get current job status."""
        with self.lock:
            return self.running_jobs.get(job_id)

    def list_running_jobs(self) -> Dict[str, Dict[str, Any]]:
        """Get all running jobs."""
        with self.lock:
            return {
                jid: status
                for jid, status in self.running_jobs.items()
                if status.get("status") != "complete"
            }

    def is_job_running(self, job_id: str) -> bool:
        """Check if job is currently running."""
        with self.lock:
            status = self.running_jobs.get(job_id, {})
            return status.get("status") in ["starting", "storyboard_generating", "skills_running"]

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job (best-effort)."""
        with self.lock:
            if job_id in self.running_jobs:
                status = self.running_jobs[job_id].get("status")
                if status not in ["complete", "error"]:
                    self.running_jobs[job_id]["status"] = "cancelled"
                    self.running_jobs[job_id]["completed_at"] = datetime.now()
                    logger.info(f"[{job_id}] Job cancelled")
                    return True
        return False

    def shutdown(self, wait: bool = True):
        """Shutdown the runner and cleanup resources."""
        logger.info("Shutting down VideoProductionRunner...")
        self.executor.shutdown(wait=wait)
        logger.info("VideoProductionRunner shutdown complete")


# Global runner instance
_runner: Optional[VideoProductionRunner] = None
_runner_lock = threading.Lock()


def get_runner(max_workers: int = 3) -> VideoProductionRunner:
    """Get or create global runner instance (singleton)."""
    global _runner

    if _runner is None:
        with _runner_lock:
            if _runner is None:
                _runner = VideoProductionRunner(max_workers=max_workers)
                logger.info(f"VideoProductionRunner initialized (max_workers={max_workers})")

    return _runner


def reset_runner():
    """Reset global runner (for testing)."""
    global _runner
    if _runner:
        _runner.shutdown(wait=True)
    _runner = None
