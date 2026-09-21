"""Pydantic models for workflow routes — request/response payloads."""
from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Constants ──────────────────────────────────────────────────────

_MAX_YAML_BYTES = 256 * 1024   # 256 KiB
_MAX_CHAT_MSG_CHARS = 4000


# ── CRUD Models ────────────────────────────────────────────────────

class CreateWorkflowRequest(BaseModel):
    """POST /workflows request."""
    title: str = Field(..., max_length=120)
    description: str = Field("", max_length=1000)
    yaml: Optional[str] = Field(None, max_length=_MAX_YAML_BYTES)
    model_config = {"extra": "forbid"}


class PatchWorkflowRequest(BaseModel):
    """PATCH /workflows/{wid} request."""
    title: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = Field(None, max_length=1000)
    model_config = {"extra": "forbid"}


class WorkflowResponse(BaseModel):
    """Workflow object response."""
    wid: str
    title: str
    description: str
    status: str
    created_at: str
    updated_at: str
    node_count: int
    phase: str


# ── YAML Models ────────────────────────────────────────────────────

class UpdateYamlRequest(BaseModel):
    """PUT /workflows/{wid}/yaml request."""
    yaml: str = Field(..., max_length=_MAX_YAML_BYTES)
    model_config = {"extra": "forbid"}


# ── Runs Models ────────────────────────────────────────────────────

class StartRunRequest(BaseModel):
    """POST /workflows/{wid}/runs request."""
    inputs: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False
    model_config = {"extra": "forbid"}


class ApproveRunRequest(BaseModel):
    """POST /workflows/{wid}/runs/{rid}/approve request."""
    comment: str = Field("", max_length=1000)
    model_config = {"extra": "forbid"}


class ResumeRunRequest(BaseModel):
    """POST /workflows/{wid}/runs/{rid}/resume request."""
    inputs: dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "forbid"}


class RunResponse(BaseModel):
    """Run object response."""
    rid: str
    wid: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    node_results: dict[str, Any] = Field(default_factory=dict)
