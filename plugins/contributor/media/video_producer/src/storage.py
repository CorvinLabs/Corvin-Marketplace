"""File-based storage for video jobs and outputs."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Support both relative and absolute imports
try:
    from models import VideoJob, VideoOutput
except ImportError:
    from .models import VideoJob, VideoOutput


class VideoStorage:
    """File-based storage for jobs and videos."""

    def __init__(self, base_path: Optional[str] = None):
        if base_path is None:
            base_path = os.path.expanduser("~/.corvin/video-producer")
        self.base_path = Path(base_path)
        self.jobs_dir = self.base_path / "jobs"
        self.videos_dir = self.base_path / "videos"
        self.thumbnails_dir = self.base_path / "thumbnails"

        # Create directories
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)

    def save_job(self, job: VideoJob):
        """Save VideoJob to disk."""
        job_file = self.jobs_dir / f"{job.id}.json"
        with open(job_file, "w") as f:
            json.dump(job.to_dict(), f, indent=2)

    def get_job(self, job_id: str) -> Optional[VideoJob]:
        """Retrieve VideoJob from disk."""
        job_file = self.jobs_dir / f"{job_id}.json"
        if not job_file.exists():
            return None
        with open(job_file, "r") as f:
            data = json.load(f)
            return VideoJob.from_dict(data)

    def list_jobs(self, limit: int = 20, offset: int = 0) -> List[VideoJob]:
        """List all jobs (paginated, sorted by creation time, newest first)."""
        job_files = sorted(
            self.jobs_dir.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        jobs_data = []
        for job_file in job_files[offset : offset + limit]:
            with open(job_file, "r") as f:
                jobs_data.append(json.load(f))
        return [VideoJob.from_dict(d) for d in jobs_data]

    def get_job_count(self) -> int:
        """Get total number of jobs."""
        return len(list(self.jobs_dir.glob("*.json")))

    def delete_job(self, job_id: str):
        """Delete job metadata."""
        job_file = self.jobs_dir / f"{job_id}.json"
        if job_file.exists():
            job_file.unlink()

    def save_video_output(self, video_output: VideoOutput):
        """Save video metadata."""
        output_dir = self.videos_dir / video_output.job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "metadata.json"
        with open(output_file, "w") as f:
            json.dump(video_output.to_dict(), f, indent=2)

    def get_video_output(self, job_id: str) -> Optional[VideoOutput]:
        """Retrieve video metadata."""
        output_file = self.videos_dir / job_id / "metadata.json"
        if not output_file.exists():
            return None
        with open(output_file, "r") as f:
            data = json.load(f)
            return VideoOutput.from_dict(data)

    def get_video_path(self, job_id: str) -> Optional[Path]:
        """Get path to video file."""
        video_output = self.get_video_output(job_id)
        if video_output and video_output.video_path:
            return Path(video_output.video_path)
        return None


# Global storage instance
_storage: Optional[VideoStorage] = None


def get_storage(base_path: Optional[str] = None) -> VideoStorage:
    """Get or create global storage instance."""
    global _storage
    if _storage is None:
        _storage = VideoStorage(base_path)
    return _storage


def reset_storage():
    """Reset global storage instance (for testing)."""
    global _storage
    _storage = None
