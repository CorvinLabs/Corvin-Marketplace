"""Unit tests for Video Producer models."""

import json
from datetime import datetime
import pytest
from src.models import Scene, Storyboard, VideoJob, VideoOutput


class TestScene:
    def test_scene_creation(self):
        scene = Scene(id="s1", kind="title", duration_ms=3000)
        assert scene.id == "s1"
        assert scene.kind == "title"
        assert scene.duration_ms == 3000
        assert scene.narration_text is None

    def test_scene_with_narration(self):
        scene = Scene(
            id="s2",
            kind="narration",
            duration_ms=5000,
            narration_text="Welcome to Corvin"
        )
        assert scene.narration_text == "Welcome to Corvin"

    def test_scene_to_dict(self):
        scene = Scene(id="s1", kind="title", duration_ms=3000, narration_text="Test")
        d = scene.to_dict()
        assert d["id"] == "s1"
        assert d["kind"] == "title"
        assert d["duration_ms"] == 3000
        assert d["narration_text"] == "Test"

    def test_scene_from_dict(self):
        data = {
            "id": "s1",
            "kind": "title",
            "duration_ms": 3000,
            "narration_text": "Test",
            "visual_description": "A title card"
        }
        scene = Scene.from_dict(data)
        assert scene.id == "s1"
        assert scene.narration_text == "Test"
        assert scene.visual_description == "A title card"


class TestStoryboard:
    def test_storyboard_creation(self):
        sb = Storyboard(id="sb1", task="Create a video")
        assert sb.id == "sb1"
        assert sb.task == "Create a video"
        assert len(sb.scenes) == 0
        assert sb.generated_at is not None

    def test_storyboard_with_scenes(self):
        scenes = [
            Scene(id="s1", kind="title", duration_ms=3000),
            Scene(id="s2", kind="narration", duration_ms=5000, narration_text="Welcome")
        ]
        sb = Storyboard(id="sb1", task="Test", scenes=scenes)
        assert len(sb.scenes) == 2
        assert sb.scenes[0].id == "s1"

    def test_storyboard_to_json(self):
        sb = Storyboard(
            id="sb1",
            task="Test video",
            scenes=[Scene(id="s1", kind="title", duration_ms=3000)]
        )
        json_str = sb.to_json()
        data = json.loads(json_str)
        assert data["id"] == "sb1"
        assert data["task"] == "Test video"
        assert len(data["scenes"]) == 1
        assert data["scenes"][0]["kind"] == "title"

    def test_storyboard_json_roundtrip(self):
        sb = Storyboard(
            id="sb1",
            task="Test video",
            scenes=[
                Scene(id="s1", kind="title", duration_ms=3000),
                Scene(id="s2", kind="narration", duration_ms=5000, narration_text="Welcome")
            ]
        )
        json_str = sb.to_json()
        sb2 = Storyboard.from_json(json_str)
        assert sb2.id == sb.id
        assert sb2.task == sb.task
        assert len(sb2.scenes) == 2
        assert sb2.scenes[1].narration_text == "Welcome"


class TestVideoJob:
    def test_video_job_creation(self):
        job = VideoJob(id="job1", task="Create video")
        assert job.id == "job1"
        assert job.task == "Create video"
        assert job.status == "pending"
        assert job.created_at is not None

    def test_video_job_status_default(self):
        job = VideoJob(id="job1", task="Test")
        assert job.status == "pending"
        assert job.started_at is None
        assert job.completed_at is None

    def test_video_job_to_dict(self):
        job = VideoJob(id="job1", task="Test", status="complete")
        d = job.to_dict()
        assert d["id"] == "job1"
        assert d["task"] == "Test"
        assert d["status"] == "complete"
        assert d["created_at"] is not None

    def test_video_job_from_dict(self):
        data = {
            "id": "job1",
            "task": "Test",
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "error_message": None,
            "storyboard": None,
            "video_output_path": None
        }
        job = VideoJob.from_dict(data)
        assert job.id == "job1"
        assert job.task == "Test"
        assert job.status == "pending"

    def test_video_job_with_error(self):
        job = VideoJob(
            id="job1",
            task="Test",
            status="error",
            error_message="Failed to synthesize voice"
        )
        assert job.status == "error"
        assert job.error_message == "Failed to synthesize voice"


class TestVideoOutput:
    def test_video_output_creation(self):
        output = VideoOutput(job_id="job1", video_path="/path/to/video.mp4")
        assert output.job_id == "job1"
        assert output.video_path == "/path/to/video.mp4"
        assert output.created_at is not None

    def test_video_output_with_metadata(self):
        output = VideoOutput(
            job_id="job1",
            video_path="/path/to/video.mp4",
            metadata={
                "duration_ms": 30000,
                "resolution": "1920x1080",
                "fps": 30
            }
        )
        assert output.metadata["duration_ms"] == 30000

    def test_video_output_to_dict(self):
        output = VideoOutput(
            job_id="job1",
            video_path="/path/to/video.mp4",
            srt_path="/path/to/video.srt"
        )
        d = output.to_dict()
        assert d["job_id"] == "job1"
        assert d["video_path"] == "/path/to/video.mp4"
        assert d["srt_path"] == "/path/to/video.srt"

    def test_video_output_from_dict(self):
        data = {
            "job_id": "job1",
            "video_path": "/path/to/video.mp4",
            "srt_path": "/path/to/video.srt",
            "thumbnail_path": None,
            "metadata": {"duration_ms": 30000},
            "created_at": datetime.now().isoformat()
        }
        output = VideoOutput.from_dict(data)
        assert output.job_id == "job1"
        assert output.metadata["duration_ms"] == 30000
