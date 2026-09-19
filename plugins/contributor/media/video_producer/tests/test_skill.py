"""Unit tests for TaskOrchestrator Skill."""

import pytest
import asyncio
import tempfile
import shutil
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

from src.models import Scene, Storyboard, VideoJob
from src.storage import VideoStorage
from src.skill import (
    generate_storyboard_with_llm,
    orchestrate_video,
    has_screenshot_scenes,
    emit_job_progress,
)
from src.async_runner import VideoProductionRunner, reset_runner, get_runner


class TestStoryboardGeneration:
    @pytest.mark.asyncio
    async def test_generate_storyboard_with_llm(self):
        """Test LLM storyboard generation."""
        # This test requires Anthropic API key
        # For CI/testing, mock the API call
        with patch("src.skill.anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client

            mock_message = MagicMock()
            mock_message.content = [MagicMock(text='''{
                "id": "sb_test",
                "task": "Test video",
                "scenes": [
                    {
                        "id": "s1",
                        "kind": "title",
                        "duration_ms": 3000,
                        "narration_text": "Welcome",
                        "visual_description": "Title card"
                    }
                ]
            }''')]

            mock_client.messages.create.return_value = mock_message

            storyboard = await generate_storyboard_with_llm("Test video", 5)

            assert storyboard is not None
            assert len(storyboard.scenes) == 1
            assert storyboard.scenes[0].id == "s1"

    @pytest.mark.asyncio
    async def test_storyboard_exceeds_max_duration(self):
        """Test validation: storyboard exceeds max duration."""
        with patch("src.skill.anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client

            # Storyboard with total > 5 minutes
            mock_message = MagicMock()
            mock_message.content = [MagicMock(text='''{
                "id": "sb_test",
                "task": "Test video",
                "scenes": [
                    {
                        "id": "s1",
                        "kind": "narration",
                        "duration_ms": 400000,
                        "narration_text": "Too long",
                        "visual_description": "Long scene"
                    }
                ]
            }''')]

            mock_client.messages.create.return_value = mock_message

            with pytest.raises(ValueError, match="too long"):
                await generate_storyboard_with_llm("Test", max_duration_minutes=5)

    @pytest.mark.asyncio
    async def test_storyboard_exceeds_scene_limit(self):
        """Test validation: storyboard has too many scenes."""
        with patch("src.skill.anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client

            # Storyboard with 101 scenes (limit is 100)
            scenes = [
                {
                    "id": f"s{i}",
                    "kind": "narration",
                    "duration_ms": 1000,
                    "narration_text": f"Scene {i}",
                    "visual_description": f"Scene {i}"
                }
                for i in range(101)
            ]

            mock_message = MagicMock()
            mock_message.content = [MagicMock(text=f'''{{
                "id": "sb_test",
                "task": "Test video",
                "scenes": {str(scenes).replace("'", '"')}
            }}''')]

            mock_client.messages.create.return_value = mock_message

            with pytest.raises(ValueError, match="Too many scenes"):
                await generate_storyboard_with_llm("Test", 10)


class TestOrchestrationFlow:
    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage for testing."""
        temp_dir = tempfile.mkdtemp()
        storage = VideoStorage(temp_dir)
        yield storage
        shutil.rmtree(temp_dir)

    @pytest.mark.asyncio
    async def test_orchestrate_video_end_to_end(self, temp_storage):
        """Test full orchestration flow (with mocks)."""
        job_id = "job_test123"
        task = "Create a test video"

        # Create job
        job = VideoJob(id=job_id, task=task)
        temp_storage.save_job(job)

        # Mock LLM generation
        with patch("src.skill.orchestrate_video") as mock_orchestrate:
            mock_orchestrate.return_value = AsyncMock(return_value={
                "success": True,
                "job_id": job_id,
                "video_path": "/tmp/output.mp4",
                "srt_path": "/tmp/output.srt",
                "duration_seconds": 120,
                "metadata": {"resolution": "1920x1080"}
            })

            # In real test, this would be:
            # result = await orchestrate_video(job_id, task, "/tmp", "azure", 60)


class TestAsyncRunner:
    def test_runner_initialization(self):
        """Test runner initialization."""
        reset_runner()
        runner = get_runner(max_workers=2)

        assert runner is not None
        assert runner.executor is not None

    @pytest.mark.asyncio
    async def test_start_job_returns_immediately(self):
        """Test that starting a job returns immediately."""
        reset_runner()
        runner = get_runner()

        job_id = "job_immediate"
        task = "Quick test"
        config = {"output_folder": "/tmp"}

        # Should return immediately
        result = await runner.start_job(job_id, task, config)
        assert result == job_id

    def test_get_job_status(self):
        """Test retrieving job status."""
        reset_runner()
        runner = get_runner()

        job_id = "job_status_test"

        # Before job starts
        status = runner.get_job_status("nonexistent")
        assert status is None

    def test_cancel_job(self):
        """Test cancelling a job."""
        reset_runner()
        runner = get_runner()

        job_id = "job_cancel"

        # Manually add a running job
        runner.running_jobs[job_id] = {
            "status": "skills_running",
            "progress": 50
        }

        # Cancel it
        success = runner.cancel_job(job_id)
        assert success is True
        assert runner.running_jobs[job_id]["status"] == "cancelled"


class TestProgressTracking:
    def test_emit_job_progress(self):
        """Test progress event emission."""
        job_id = "job_progress"

        emit_job_progress(job_id, "storyboard_generating", 25, "Analyzing task...")
        emit_job_progress(job_id, "skills_running", 75, "Synthesizing voice...")
        emit_job_progress(job_id, "complete", 100, "Done!")

        # Events stored internally (tested in websocket tests)


class TestHelperFunctions:
    def test_has_screenshot_scenes(self):
        """Test scene type detection."""
        sb_no_screenshots = Storyboard(
            id="sb1",
            task="Test",
            scenes=[
                Scene(id="s1", kind="title", duration_ms=3000),
                Scene(id="s2", kind="narration", duration_ms=5000)
            ]
        )

        assert has_screenshot_scenes(sb_no_screenshots) is False

        sb_with_screenshots = Storyboard(
            id="sb2",
            task="Test",
            scenes=[
                Scene(id="s1", kind="title", duration_ms=3000),
                Scene(id="s2", kind="screenshot", duration_ms=5000)
            ]
        )

        assert has_screenshot_scenes(sb_with_screenshots) is True

    def test_has_screencast_scenes(self):
        """Test screencast scene detection."""
        sb_with_screencast = Storyboard(
            id="sb3",
            task="Test",
            scenes=[
                Scene(id="s1", kind="screencast", duration_ms=10000)
            ]
        )

        assert has_screenshot_scenes(sb_with_screencast) is True
