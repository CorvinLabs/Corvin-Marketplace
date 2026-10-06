"""Unit tests for Video Producer models."""

import json
from datetime import datetime
import pytest
from src.models import (
    AssetAnalysisResult,
    Contradiction,
    FactualClaim,
    Scene,
    Storyboard,
    VideoJob,
    VideoOutput,
)


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


class TestFactualClaim:
    """FactualClaim ported from CorvinOS core (consolidation plan 2026-10-06)."""

    def test_claim_creation_defaults(self):
        claim = FactualClaim(id="c1", text="The sky is blue", source_asset="doc.pdf")
        assert claim.id == "c1"
        assert claim.confidence == "medium"
        assert claim.source_page is None
        assert claim.contradictions == []

    def test_claim_is_frozen(self):
        claim = FactualClaim(id="c1", text="x", source_asset="a.pdf")
        with pytest.raises(Exception):
            claim.text = "y"

    def test_claim_to_dict_from_dict_roundtrip(self):
        claim = FactualClaim(
            id="c1",
            text="The sky is blue",
            source_asset="doc.pdf",
            source_page="3",
            confidence="high",
            contradictions=["c2"],
        )
        d = claim.to_dict()
        restored = FactualClaim.from_dict(d)
        assert restored == claim

    def test_claim_to_dict_json_serializable(self):
        claim = FactualClaim(id="c1", text="x", source_asset="a.pdf")
        # Must not raise — the dict is plain str/bool/list/None.
        json.dumps(claim.to_dict())


class TestContradiction:
    """Contradiction ported from CorvinOS core (consolidation plan 2026-10-06)."""

    def test_contradiction_creation(self):
        c = Contradiction(sources=["a.pdf", "b.pdf"], claim_a="x", claim_b="not x")
        assert c.sources == ["a.pdf", "b.pdf"]
        assert c.resolution is None

    def test_contradiction_is_frozen(self):
        c = Contradiction(sources=["a"], claim_a="x", claim_b="y")
        with pytest.raises(Exception):
            c.resolution = "resolved"

    def test_contradiction_to_dict_from_dict_roundtrip(self):
        c = Contradiction(sources=["a.pdf", "b.pdf"], claim_a="x", claim_b="not x", resolution="a.pdf wins")
        restored = Contradiction.from_dict(c.to_dict())
        assert restored == c


class TestAssetAnalysisResult:
    """AssetAnalysisResult ported from CorvinOS core (consolidation plan 2026-10-06)."""

    def test_creation_defaults(self):
        result = AssetAnalysisResult(metadata={"source": "doc.pdf"})
        assert result.audience is None
        assert result.purpose is None
        assert result.factual_claims == []
        assert result.ready_for_narration is False
        assert result.blockers == []

    def test_to_dict_includes_nested_claims_and_contradictions(self):
        claim = FactualClaim(id="c1", text="x", source_asset="a.pdf")
        contradiction = Contradiction(sources=["a.pdf"], claim_a="x", claim_b="y")
        result = AssetAnalysisResult(
            metadata={"source": "doc.pdf"},
            audience="beginners",
            purpose="explain x",
            factual_claims=[claim],
            contradictions=[contradiction],
            ready_for_narration=True,
        )
        d = result.to_dict()
        assert d["audience"] == "beginners"
        assert d["ready_for_narration"] is True
        assert d["factual_claims"][0]["id"] == "c1"
        assert d["contradictions"][0]["claim_a"] == "x"

    def test_to_dict_json_serializable(self):
        claim = FactualClaim(id="c1", text="x", source_asset="a.pdf")
        result = AssetAnalysisResult(metadata={}, factual_claims=[claim])
        json.dumps(result.to_dict())  # must not raise

    def test_from_dict_roundtrip(self):
        claim = FactualClaim(id="c1", text="x", source_asset="a.pdf", confidence="high")
        contradiction = Contradiction(sources=["a.pdf", "b.pdf"], claim_a="x", claim_b="not x")
        result = AssetAnalysisResult(
            metadata={"source": "doc.pdf"},
            audience="beginners",
            purpose="explain x",
            factual_claims=[claim],
            asset_roles={"a.pdf": "primary"},
            terminology={"x": "definition of x"},
            contradictions=[contradiction],
            ready_for_narration=True,
            blockers=["none"],
        )
        restored = AssetAnalysisResult.from_dict(result.to_dict())
        assert restored.metadata == result.metadata
        assert restored.audience == result.audience
        assert restored.factual_claims == result.factual_claims
        assert restored.contradictions == result.contradictions
        assert restored.ready_for_narration == result.ready_for_narration

    def test_from_dict_defaults_on_missing_keys(self):
        result = AssetAnalysisResult.from_dict({})
        assert result.metadata == {}
        assert result.factual_claims == []
        assert result.ready_for_narration is False
