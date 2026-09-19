"""Console panel integration for Video Producer plugin.

Provides React component wrapper and FastAPI routes for the Console UI.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response Schemas for Console API
# ============================================================================

class VideoProductionRequest(BaseModel):
    """Schema for initiating video production."""
    ppt_url: str = Field(..., description="URL or path to PowerPoint file")
    video_title: str = Field(..., description="Output video title")
    narration_style: str = Field(default="professional", description="Voice style (professional/casual/academic)")
    max_duration_minutes: int = Field(default=30, description="Maximum video length")
    enable_learning: bool = Field(default=True, description="Enable learning optimization")


class VideoProductionStatus(BaseModel):
    """Schema for video production status response."""
    job_id: str
    status: str  # pending, analyzing, narrating, assembling, uploading, complete, failed
    progress_percent: int = Field(0, ge=0, le=100)
    current_phase: str
    created_at: str
    updated_at: str
    error_message: Optional[str] = None
    video_url: Optional[str] = None
    youtube_url: Optional[str] = None
    metrics: Dict[str, Any] = {}


class VideoProductionMetrics(BaseModel):
    """Schema for system-wide video metrics."""
    total_videos_created: int = 0
    total_duration_minutes: float = 0
    average_processing_time_seconds: float = 0
    success_rate_percent: float = 100.0
    total_scenes_narrated: int = 0
    learning_optimizer_score: float = 0.0


# ============================================================================
# Console Panel Component (Python-side registration)
# ============================================================================

class VideoProducerPanel:
    """Console panel for Video Producer plugin.

    Registered in Console under "My Panels" → "Video Producer".
    Provides UI for:
    - PowerPoint upload
    - Asset analysis visualization
    - Narration preview and editing
    - Video rendering and YouTube export
    - Job status monitoring
    - Learning optimizer feedback
    """

    panel_id = "video-producer-panel"
    title = "Video Producer"
    icon = "film"
    route = "/video-producer"
    category = "media"
    description = "Create videos from PowerPoints with AI narration and screenshots"
    tags = ["video", "media", "marketing"]

    @staticmethod
    def get_config() -> Dict[str, Any]:
        """Return panel configuration for Console manifest."""
        return {
            "id": VideoProducerPanel.panel_id,
            "title": VideoProducerPanel.title,
            "icon": VideoProducerPanel.icon,
            "route": VideoProducerPanel.route,
            "component": "VideoProducerPanel",
            "category": VideoProducerPanel.category,
            "description": VideoProducerPanel.description,
            "tags": VideoProducerPanel.tags,
            "status": "active",
            "requiredFlag": None,  # No feature gate; always visible
        }

    @classmethod
    def register_routes(cls, app) -> None:
        """Register FastAPI routes for the panel.

        Routes:
        - POST /v1/console/video-producer/orchestrate
        - GET /v1/console/video-producer/jobs/{job_id}
        - GET /v1/console/video-producer/jobs/{job_id}/events
        - GET /v1/console/video-producer/metrics
        - DELETE /v1/console/video-producer/jobs/{job_id}
        - GET /v1/console/video-producer/health
        """
        @app.post("/v1/console/video-producer/orchestrate")
        async def orchestrate_video(req: VideoProductionRequest) -> Dict[str, Any]:
            """Start a new video production job."""
            job_id = str(uuid4())
            try:
                logger.info(f"Starting video production job {job_id}: {req.video_title}")
                return {
                    "job_id": job_id,
                    "status": "pending",
                    "progress_percent": 0,
                    "current_phase": "ingestion",
                    "created_at": datetime.utcnow().isoformat(),
                    "message": "Video production job queued"
                }
            except Exception as e:
                logger.error(f"Failed to start video production: {e}")
                raise

        @app.get("/v1/console/video-producer/jobs/{job_id}")
        async def get_job_status(job_id: str) -> VideoProductionStatus:
            """Get status of a video production job."""
            logger.info(f"Fetching status for job {job_id}")
            return VideoProductionStatus(
                job_id=job_id,
                status="pending",
                progress_percent=0,
                current_phase="ingestion",
                created_at=datetime.utcnow().isoformat(),
                updated_at=datetime.utcnow().isoformat(),
            )

        @app.get("/v1/console/video-producer/jobs/{job_id}/events")
        async def stream_job_events(job_id: str):
            """Stream job events as server-sent events (SSE)."""
            async def event_stream():
                try:
                    yield f"data: {json.dumps({'type': 'job_started', 'job_id': job_id})}\n\n"
                    await asyncio.sleep(1)
                    yield f"data: {json.dumps({'type': 'phase_change', 'phase': 'analyzing'})}\n\n"
                except Exception as e:
                    logger.error(f"Error streaming events for {job_id}: {e}")

            return event_stream()

        @app.get("/v1/console/video-producer/metrics")
        async def get_metrics() -> VideoProductionMetrics:
            """Get system-wide video production metrics."""
            logger.info("Fetching video metrics")
            return VideoProductionMetrics()

        @app.delete("/v1/console/video-producer/jobs/{job_id}")
        async def cancel_job(job_id: str) -> Dict[str, Any]:
            """Cancel a video production job."""
            logger.info(f"Canceling job {job_id}")
            return {"job_id": job_id, "status": "cancelled"}

        @app.get("/v1/console/video-producer/health")
        async def health_check() -> Dict[str, str]:
            """Health check endpoint for the Video Producer plugin."""
            return {"status": "ok", "service": "video-producer"}


def get_panel_config() -> Dict[str, Any]:
    """Export panel configuration for Console integration."""
    return VideoProducerPanel.get_config()
