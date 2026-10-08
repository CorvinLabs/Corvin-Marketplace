"""Data models for Video Producer plugin."""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Optional, List
import json


@dataclass(frozen=True)
class FactualClaim:
    """A single sourced factual claim from asset analysis.

    Ported from CorvinOS core (``core/skills/os_skills/video_producer/types.py``,
    consolidation plan 2026-10-06) so the plugin is self-contained — this file
    imports nothing from CorvinOS. Field shape kept byte-identical to the core
    version so a future caller can move between the two without translation.
    """
    id: str
    text: str
    source_asset: str
    source_page: Optional[str] = None
    confidence: str = "medium"  # high, medium, low
    contradictions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "source_asset": self.source_asset,
            "source_page": self.source_page,
            "confidence": self.confidence,
            "contradictions": list(self.contradictions),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FactualClaim":
        return cls(
            id=data["id"],
            text=data["text"],
            source_asset=data["source_asset"],
            source_page=data.get("source_page"),
            confidence=data.get("confidence", "medium"),
            contradictions=list(data.get("contradictions", [])),
        )


@dataclass(frozen=True)
class Contradiction:
    """A contradiction between two factual claims.

    Ported from CorvinOS core alongside ``FactualClaim`` (see its docstring).
    """
    sources: List[str]
    claim_a: str
    claim_b: str
    resolution: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "sources": list(self.sources),
            "claim_a": self.claim_a,
            "claim_b": self.claim_b,
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Contradiction":
        return cls(
            sources=list(data["sources"]),
            claim_a=data["claim_a"],
            claim_b=data["claim_b"],
            resolution=data.get("resolution"),
        )


@dataclass
class AssetAnalysisResult:
    """Complete analysis output from the asset_analyzer worker.

    Ported from CorvinOS core alongside ``FactualClaim`` (see its docstring).
    Mutable (unlike ``FactualClaim``/``Contradiction``) because the core
    version is assembled incrementally by the analyzer worker.
    """
    metadata: dict
    audience: Optional[str] = None
    purpose: Optional[str] = None
    factual_claims: List[FactualClaim] = field(default_factory=list)
    asset_roles: dict = field(default_factory=dict)
    terminology: dict = field(default_factory=dict)
    contradictions: List[Contradiction] = field(default_factory=list)
    ready_for_narration: bool = False
    blockers: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dict."""
        return {
            "metadata": self.metadata,
            "audience": self.audience,
            "purpose": self.purpose,
            "factual_claims": [c.to_dict() for c in self.factual_claims],
            "asset_roles": self.asset_roles,
            "terminology": self.terminology,
            "contradictions": [c.to_dict() for c in self.contradictions],
            "ready_for_narration": self.ready_for_narration,
            "blockers": self.blockers,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AssetAnalysisResult":
        return cls(
            metadata=data.get("metadata", {}),
            audience=data.get("audience"),
            purpose=data.get("purpose"),
            factual_claims=[FactualClaim.from_dict(c) for c in data.get("factual_claims", [])],
            asset_roles=data.get("asset_roles", {}),
            terminology=data.get("terminology", {}),
            contradictions=[Contradiction.from_dict(c) for c in data.get("contradictions", [])],
            ready_for_narration=data.get("ready_for_narration", False),
            blockers=data.get("blockers", []),
        )


@dataclass
class Scene:
    """A single scene in a storyboard."""
    id: str
    kind: str  # "title", "opening", "problem", "solution", "example", "summary", "anchor", "narration", "screenshot", "screencast"
    duration_ms: int
    narration_text: Optional[str] = None
    visual_description: Optional[str] = None
    # Didactic metadata (ADR-0004): set by the storyboard LLM when it follows
    # the didactic constraints, read by NarrationValidator and the renderer.
    # Never required — a scene without them is simply unvalidated/unstyled,
    # not invalid.
    character_count: Optional[int] = None
    pacing_note: Optional[str] = None
    # Screenshot capture (CONCEPT-0095): only meaningful when kind=="screenshot".
    # screenshot_url replaces a keyword-guessed URL map — it is explicit, so a
    # wrong URL fails loudly (selector lookup fails) instead of silently
    # screenshotting the wrong page. highlight_selector is a CSS selector
    # resolved against the real DOM to a bounding box for the spotlight
    # call-out; a selector that doesn't resolve is a hard error, never a
    # silently un-annotated screenshot.
    screenshot_url: Optional[str] = None
    highlight_selector: Optional[str] = None
    # Web slide (ADR-2238): a scene carrying a template is rendered as an
    # animated HTML slide; ``kind`` keeps its didactic meaning. ``data`` is
    # validated against the template contract in web_templates before use.
    template: Optional[str] = None
    data: Optional[dict] = None
    theme: Optional[str] = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class Storyboard:
    """A complete storyboard generated from a task."""
    id: str
    task: str
    scenes: List[Scene] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    # Didactic strategy (ADR-0004): "minimal_visual" (concept-first, 150-250
    # chars/scene, narration carries the content) or "rich_visual"
    # (system/architecture, 300-400 chars/scene, diagrams carry the content).
    # Defaults to "rich_visual" for storyboards predating this field.
    didactic_strategy: str = "rich_visual"
    # Which LLM actually wrote it ("claude_cli:<model>", "ollama:<model>", ...);
    # None for an operator-supplied storyboard. Job metadata, not serialised.
    llm_backend: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps({
            "id": self.id,
            "task": self.task,
            "scenes": [s.to_dict() for s in self.scenes],
            "generated_at": self.generated_at.isoformat(),
            "didactic_strategy": self.didactic_strategy,
        })

    @classmethod
    def from_json(cls, json_str: str):
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def from_dict(cls, data: dict):
        scenes = [Scene.from_dict(s) for s in data.get("scenes", [])]
        return cls(
            id=data["id"],
            task=data["task"],
            scenes=scenes,
            generated_at=datetime.fromisoformat(data["generated_at"]),
            didactic_strategy=data.get("didactic_strategy", "rich_visual"),
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
