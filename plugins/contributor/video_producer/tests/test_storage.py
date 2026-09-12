"""Unit tests for Video Producer storage."""

import tempfile
import shutil
from pathlib import Path
import pytest
from src.models import VideoJob, VideoOutput
from src.storage import VideoStorage, get_storage, reset_storage


class TestVideoStorage:
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        temp_dir = tempfile.mkdtemp()
        storage = VideoStorage(temp_dir)
        yield storage
        shutil.rmtree(temp_dir)

    def test_storage_initialization(self, temp_storage):
        """Test that storage creates necessary directories."""
        assert temp_storage.jobs_dir.exists()
        assert temp_storage.videos_dir.exists()
        assert temp_storage.thumbnails_dir.exists()

    def test_save_and_retrieve_job(self, temp_storage):
        """Test saving and retrieving a job."""
        job = VideoJob(id="job1", task="Create video", status="pending")
        temp_storage.save_job(job)

        retrieved = temp_storage.get_job("job1")
        assert retrieved is not None
        assert retrieved.id == "job1"
        assert retrieved.task == "Create video"
        assert retrieved.status == "pending"

    def test_get_nonexistent_job_returns_none(self, temp_storage):
        """Test retrieving a job that doesn't exist."""
        result = temp_storage.get_job("nonexistent")
        assert result is None

    def test_list_jobs_pagination(self, temp_storage):
        """Test listing jobs with pagination."""
        # Create 5 jobs
        for i in range(5):
            job = VideoJob(id=f"job{i}", task=f"Video {i}")
            temp_storage.save_job(job)

        # List first 2
        jobs = temp_storage.list_jobs(limit=2, offset=0)
        assert len(jobs) == 2

        # List next 2
        jobs = temp_storage.list_jobs(limit=2, offset=2)
        assert len(jobs) == 2

        # List with large offset
        jobs = temp_storage.list_jobs(limit=10, offset=10)
        assert len(jobs) == 0

    def test_list_jobs_empty_storage(self, temp_storage):
        """Test listing jobs from empty storage."""
        jobs = temp_storage.list_jobs()
        assert len(jobs) == 0

    def test_list_jobs_sorted_by_mtime(self, temp_storage):
        """Test that jobs are sorted by modification time (newest first)."""
        import time

        # Create first job
        job1 = VideoJob(id="job1", task="First")
        temp_storage.save_job(job1)
        time.sleep(0.1)

        # Create second job
        job2 = VideoJob(id="job2", task="Second")
        temp_storage.save_job(job2)

        # Retrieve list (should be newest first)
        jobs = temp_storage.list_jobs()
        assert len(jobs) == 2
        # Most recently saved should be first
        assert jobs[0].id == "job2"
        assert jobs[1].id == "job1"

    def test_delete_job(self, temp_storage):
        """Test deleting a job."""
        job = VideoJob(id="job1", task="Delete me")
        temp_storage.save_job(job)

        retrieved = temp_storage.get_job("job1")
        assert retrieved is not None

        temp_storage.delete_job("job1")
        retrieved = temp_storage.get_job("job1")
        assert retrieved is None

    def test_save_and_retrieve_video_output(self, temp_storage):
        """Test saving and retrieving video output metadata."""
        output = VideoOutput(
            job_id="job1",
            video_path="/path/to/video.mp4",
            srt_path="/path/to/video.srt",
            metadata={"duration_ms": 30000}
        )
        temp_storage.save_video_output(output)

        retrieved = temp_storage.get_video_output("job1")
        assert retrieved is not None
        assert retrieved.job_id == "job1"
        assert retrieved.video_path == "/path/to/video.mp4"
        assert retrieved.metadata["duration_ms"] == 30000

    def test_get_nonexistent_video_output_returns_none(self, temp_storage):
        """Test retrieving a video output that doesn't exist."""
        result = temp_storage.get_video_output("nonexistent")
        assert result is None

    def test_get_job_count(self, temp_storage):
        """Test getting total job count."""
        assert temp_storage.get_job_count() == 0

        for i in range(3):
            job = VideoJob(id=f"job{i}", task=f"Video {i}")
            temp_storage.save_job(job)

        assert temp_storage.get_job_count() == 3

    def test_get_video_path(self, temp_storage):
        """Test getting video file path."""
        output = VideoOutput(
            job_id="job1",
            video_path="/path/to/video.mp4"
        )
        temp_storage.save_video_output(output)

        path = temp_storage.get_video_path("job1")
        assert path is not None
        assert str(path) == "/path/to/video.mp4"

    def test_get_video_path_nonexistent_returns_none(self, temp_storage):
        """Test getting video path for nonexistent job."""
        path = temp_storage.get_video_path("nonexistent")
        assert path is None

    def test_job_file_format_is_json(self, temp_storage):
        """Test that job files are valid JSON."""
        job = VideoJob(id="job1", task="Test", status="complete")
        temp_storage.save_job(job)

        job_file = temp_storage.jobs_dir / "job1.json"
        assert job_file.exists()

        # Should be valid JSON
        import json
        with open(job_file) as f:
            data = json.load(f)
            assert data["id"] == "job1"
            assert data["task"] == "Test"
