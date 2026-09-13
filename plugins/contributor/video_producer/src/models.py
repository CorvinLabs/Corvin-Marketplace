"""Data models for Video Producer plugin."""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional, List
import json


@dataclass
class Scene:
    """A single scene in a storyboard."""
    id: str
    kind: str  # "title", "narration", "screenshot", "screencast"
    duration_ms: int
    narration_text: Optional[str] = None
    visual_description: Optional[str] = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)


@dataclass
class Storyboard:
    """A complete storyboard generated from a task."""
    id: str
    task: str
    scenes: List[Scene] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)

    def to_json(self) -> str:
        return json.dumps({
            "id": self.id,
            "task": self.task,
            "scenes": [s.to_dict() for s in self.scenes],
            "generated_at": self.generated_at.isoformat(),
        })

    @classmethod
    def from_json(cls, json_str: str):
        data = json.loads(json_str)
        scenes = [Scene.from_dict(s) for s in data.get("scenes", [])]
        return cls(
            id=data["id"],
            task=data["task"],
            scenes=scenes,
            generated_at=datetime.fromisoformat(data["generated_at"])
        )

    @classmethod
    def from_dict(cls, data: dict):
        scenes = [Scene.from_dict(s) for s in data.get("scenes", [])]
        return cls(
            id=data["id"],
            task=data["task"],
            scenes=scenes,
            generated_at=datetime.fromisoformat(data["generated_at"])
        )


@dataclass
class VideoJob:
    """A video job request."""
    id: str
    task: str
    status: str = "pending"  # pending, storyboard_generating, skills_running, complete, error
    storyboard: Optional[Storyboard] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    video_output_path: Optional[str] = None
    percent: int = 0
    current_step: Optional[str] = None
    current_scene: Optional[int] = None
    total_scenes: Optional[int] = None

    def to_dict(self):
        return {
            "id": self.id,
            "task": self.task,
            "status": self.status,
            "storyboard": self.storyboard.to_json() if self.storyboard else None,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "video_output_path": self.video_output_path,
            "percent": self.percent,
            "current_step": self.current_step,
            "current_scene": self.current_scene,
            "total_scenes": self.total_scenes,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data["id"],
            task=data["task"],
            status=data["status"],
            storyboard=Storyboard.from_json(data["storyboard"]) if data.get("storyboard") else None,
            created_at=datetime.fromisoformat(data["created_at"]),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            error_message=data.get("error_message"),
            video_output_path=data.get("video_output_path"),
            percent=data.get("percent", 0),
            current_step=data.get("current_step"),
            current_scene=data.get("current_scene"),
            total_scenes=data.get("total_scenes"),
        )


@dataclass
class VideoOutput:
    """Output metadata for a completed video."""
    job_id: str
    video_path: str
    srt_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    metadata: dict = field(default_factory=dict)  # {duration_ms, resolution, fps, file_size_mb}
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self):
        return {
            "job_id": self.job_id,
            "video_path": self.video_path,
            "srt_path": self.srt_path,
            "thumbnail_path": self.thumbnail_path,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            job_id=data["job_id"],
            video_path=data["video_path"],
            srt_path=data.get("srt_path"),
            thumbnail_path=data.get("thumbnail_path"),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
        )
