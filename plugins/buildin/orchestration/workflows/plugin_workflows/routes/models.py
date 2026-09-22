"""Pydantic models for workflow routes — request/response payloads."""
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
import croniter
import pytz


# ── Constants ──────────────────────────────────────────────────────

_MAX_YAML_BYTES = 256 * 1024   # 256 KiB
_MAX_CHAT_MSG_CHARS = 4000


# ── CRUD Models ────────────────────────────────────────────────────

class CreateWorkflowRequest(BaseModel):
    """POST /workflows request."""
    title: str = Field(..., max_length=120, description="Workflow title (required, non-empty)")
    description: str = Field("", max_length=1000, description="Optional description")
    yaml: Optional[str] = Field(None, max_length=_MAX_YAML_BYTES, description="Optional YAML definition")
    model_config = {"extra": "forbid"}

    @field_validator('title')
    @classmethod
    def validate_title_not_empty(cls, v: str) -> str:
        """Ensure title is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("title cannot be empty")
        return v.strip()


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


# ── Schedule Models ────────────────────────────────────────────────────

class SetScheduleRequest(BaseModel):
    """PUT /workflows/{wid}/schedule request."""
    cron_schedule: str = Field(..., description="Cron expression (e.g., '0 9 * * 1-5')")
    timezone: str = Field(default="UTC", description="IANA timezone (e.g., 'America/New_York')")
    overrun_policy: str = Field(
        default="skip",
        description="Behavior when task overruns: 'skip' | 'parallel' | 'wait'"
    )
    model_config = {"extra": "forbid"}

    @field_validator('cron_schedule')
    @classmethod
    def validate_cron(cls, v: str) -> str:
        """Validate cron expression using croniter."""
        if not v or not v.strip():
            raise ValueError("cron_schedule cannot be empty")
        try:
            croniter.croniter(v)
            return v
        except (ValueError, KeyError) as e:
            raise ValueError(f"Invalid cron expression: {v}. Error: {e}") from e

    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate timezone using pytz."""
        if not v or not v.strip():
            raise ValueError("timezone cannot be empty")
        try:
            pytz.timezone(v)
            return v
        except pytz.exceptions.UnknownTimeZoneError as e:
            raise ValueError(f"Invalid timezone: {v}") from e

    @field_validator('overrun_policy')
    @classmethod
    def validate_overrun_policy(cls, v: str) -> str:
        """Validate overrun policy."""
        valid_policies = {"skip", "parallel", "wait"}
        if v not in valid_policies:
            raise ValueError(
                f"Invalid overrun_policy: {v}. Must be one of: {', '.join(valid_policies)}"
            )
        return v


class ScheduleResponse(BaseModel):
    """Schedule GET response."""
    workflow_id: str
    cron_schedule: str
    timezone: str
    overrun_policy: str
    next_run: Optional[str] = None
    last_run: Optional[str] = None
    status: str


class ScheduleUpdateResponse(BaseModel):
    """Schedule PUT response."""
    ok: bool
    workflow_id: str
    cron_schedule: str
    timezone: str
    next_run: Optional[str] = None
    scheduler_registered: bool = False
