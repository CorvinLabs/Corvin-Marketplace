"""E2E Tests — Full video production workflow (create → play → upload)."""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from src.models import VideoJob, Storyboard, Scene, VideoOutput
from src.storage import VideoStorage
from src.async_runner import VideoProductionRunner, reset_runner
from src.youtube_uploader import YouTubeUploadManager
from src.settings_manager import SettingsManager, reset_settings_manager


class TestE2EWorkflow:
    """End-to-end workflow tests."""

    @pytest.fixture
    def temp_env(self):
        """Temporary environment for E2E testing."""
        temp_dir = tempfile.mkdtemp()
        storage = VideoStorage(temp_dir)
        runner = VideoProductionRunner(max_workers=1)
        yield {
            "temp_dir": temp_dir,
            "storage": storage,
            "runner": runner,
        }
        shutil.rmtree(temp_dir)
        runner.shutdown()

    @pytest.mark.asyncio
    async def test_full_workflow_create_to_complete(self, temp_env):
        """Test: Create → Progress → Complete."""
        job_id = "job_e2e_001"
        task = "Create test video"

        storage = temp_env["storage"]
        runner = temp_env["runner"]

        # Step 1: Create job
        job = VideoJob(id=job_id, task=task)
        storage.save_job(job)

        # Verify job created
        retrieved = storage.get_job(job_id)
        assert retrieved is not None
        assert retrieved.status == "pending"

        # Step 2: Start async production
        await runner.start_job(job_id, task, {
            "output_folder": temp_env["temp_dir"],
            "tts_engine": "azure",
            "max_duration_minutes": 5
        })

        # Wait for job to start
        await asyncio.sleep(0.2)

        # Verify job running
        status = runner.get_job_status(job_id)
        assert status is not None
        assert status.get("status") in ["starting", "storyboard_generating"]

    @pytest.mark.asyncio
    async def test_concurrent_jobs(self, temp_env):
        """Test: Multiple concurrent jobs."""
        runner = temp_env["runner"]

        job_ids = [f"job_concurrent_{i}" for i in range(3)]

        # Start 3 concurrent jobs
        tasks = []
        for job_id in job_ids:
            task = await runner.start_job(job_id, f"Task {job_id}", {
                "output_folder": temp_env["temp_dir"]
            })
            tasks.append(task)

        # All should return immediately
        assert len(tasks) == 3
        assert all(jid in job_ids for jid in tasks)

    def test_download_workflow(self, temp_env):
        """Test: Video file download path."""
        job_id = "job_download_001"
        storage = temp_env["storage"]

        # Create output metadata
        video_output = VideoOutput(
            job_id=job_id,
            video_path=f"{temp_env['temp_dir']}/{job_id}/output.mp4",
            srt_path=f"{temp_env['temp_dir']}/{job_id}/output.srt",
            metadata={
                "duration_ms": 120000,
                "resolution": "1920x1080",
            }
        )
        storage.save_video_output(video_output)

        # Verify downloadable
        retrieved = storage.get_video_output(job_id)
        assert retrieved is not None
        assert retrieved.video_path.endswith(".mp4")

    @pytest.mark.asyncio
    async def test_youtube_upload_workflow(self):
        """Test: YouTube upload queuing + status tracking."""
        uploader = YouTubeUploadManager()

        # Step 1: Enqueue upload
        result = await uploader.enqueue_upload(
            job_id="job_youtube_001",
            video_path="/tmp/video.mp4",
            srt_path="/tmp/video.srt",
            metadata={
                "title": "Test Video",
                "tags": ["test", "corvin"],
                "privacy_status": "unlisted"
            }
        )

        assert result["status"] == "queued"
        assert "task_id" in result

        task_id = result["task_id"]

        # Step 2: Get upload status
        status = await uploader.get_upload_status(task_id)
        assert status["status"] == "queued"
        assert status["job_id"] == "job_youtube_001"

    def test_settings_persistence_workflow(self):
        """Test: Settings save/load cycle."""
        temp_config = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        config_path = temp_config.name
        temp_config.close()

        try:
            # Step 1: Create manager and save settings
            manager1 = SettingsManager(config_path)
            manager1.save_settings({
                "output_folder": "/custom/path",
                "tts_engine": "google",
                "max_duration_minutes": 30
            })

            # Step 2: Create new manager (simulates restart)
            manager2 = SettingsManager(config_path)

            # Verify settings persisted
            assert manager2.get_setting("output_folder") == "/custom/path"
            assert manager2.get_setting("tts_engine") == "google"
            assert manager2.get_setting("max_duration_minutes") == 30

        finally:
            Path(config_path).unlink()

    @pytest.mark.asyncio
    async def test_error_recovery_workflow(self, temp_env):
        """Test: Job error handling and recovery."""
        job_id = "job_error_001"
        storage = temp_env["storage"]

        # Create job
        job = VideoJob(id=job_id, task="Failing task")
        storage.save_job(job)

        # Simulate error
        job.status = "error"
        job.error_message = "Voice synthesis failed: API error"
        storage.save_job(job)

        # Verify error recorded
        retrieved = storage.get_job(job_id)
        assert retrieved.status == "error"
        assert "synthesis failed" in retrieved.error_message

    @pytest.mark.asyncio
    async def test_large_storyboard_workflow(self):
        """Test: Large storyboard (100 scenes) handling."""
        # Create large storyboard
        scenes = [
            Scene(
                id=f"s{i}",
                kind="narration" if i % 2 == 0 else "screenshot",
                duration_ms=1000,
                narration_text=f"Scene {i}",
                visual_description=f"Visual {i}"
            )
            for i in range(100)
        ]

        storyboard = Storyboard(
            id="sb_large",
            task="Large workflow",
            scenes=scenes
        )

        # Verify storyboard
        assert len(storyboard.scenes) == 100
        assert sum(s.duration_ms for s in storyboard.scenes) == 100000  # 100 sec

    @pytest.mark.asyncio
    async def test_job_cancellation_workflow(self, temp_env):
        """Test: Cancel in-flight job."""
        runner = temp_env["runner"]
        job_id = "job_cancel_001"

        # Start job
        await runner.start_job(job_id, "Cancel me", {
            "output_folder": temp_env["temp_dir"]
        })

        # Cancel it
        success = runner.cancel_job(job_id)
        assert success is True

        # Verify cancelled
        status = runner.get_job_status(job_id)
        assert status["status"] == "cancelled"
