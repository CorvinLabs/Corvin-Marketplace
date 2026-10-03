"""File-based storage for video jobs and outputs.

One store per base directory. The HOST decides the base (CorvinOS passes
``<tenant_home(tenant_id)>/video_producer``), so jobs of two tenants never
share a directory; there is no implicit ``~/.corvin`` default.
"""

import json
import logging
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from .models import VideoJob, VideoOutput
except ImportError:  # standalone script use (no package context)
    from models import VideoJob, VideoOutput

logger = logging.getLogger(__name__)

# Statuses after which nothing will touch the job again.
TERMINAL_STATUSES = frozenset({"complete", "error", "cancelled"})


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

    def save_job(self, job: VideoJob):
        """Save VideoJob to disk (atomic)."""
        _atomic_write_json(self.jobs_dir / f"{job.id}.json", job.to_dict())

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
        """Mark every non-terminal job as failed. Called once, when this
        process first opens the store: no job of this store can be running in
        a process that has not opened it yet, so a non-terminal job here was
        orphaned by a restart and would otherwise poll as running forever."""
        n = 0
        for job in self._all_jobs():
            if job.status not in TERMINAL_STATUSES:
                job.status = "error"
                job.error_message = "Interrupted: the console process restarted while this job was running."
                job.completed_at = job.completed_at or datetime.now()
                self.save_job(job)
                n += 1
        return n


_stores: Dict[str, VideoStorage] = {}
_stores_lock = threading.Lock()


def get_storage(base_path: str) -> VideoStorage:
    """The store for ``base_path`` (one instance per directory per process)."""
    if not base_path:
        raise ValueError("get_storage() needs the host's tenant base path")
    key = str(Path(base_path).resolve())
    with _stores_lock:
        store = _stores.get(key)
        if store is None:
            store = VideoStorage(key)
            interrupted = store.mark_interrupted_jobs()
            if interrupted:
                logger.warning("video storage: marked %d orphaned job(s) as interrupted in %s", interrupted, key)
            _stores[key] = store
        return store


def reset_storage():
    """Forget all store instances (for testing)."""
    with _stores_lock:
        _stores.clear()
