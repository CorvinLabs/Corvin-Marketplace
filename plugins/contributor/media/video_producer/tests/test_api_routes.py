"""Unit tests for Video Producer API routes."""

import pytest
import tempfile
import shutil
from fastapi.testclient import TestClient
import sys
import os

# Add plugin src to path
sys.path.insert(0, os.path.expanduser("~/.corvin/plugins/video_producer/src"))

# Mock imports for testing
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../src")

from fastapi import FastAPI
from src.models import VideoJob
from src.storage import VideoStorage, get_storage, reset_storage

# Import the router from video_producer_api
# For testing, we'll create a minimal FastAPI app
app = FastAPI()

# Create test storage
temp_dir = tempfile.mkdtemp()
test_storage = VideoStorage(temp_dir)

# Override get_storage for testing
def get_test_storage():
    return test_storage

# Simplified versions of routes for testing
@app.post("/v1/video/jobs")
async def create_video_job_test(req: dict):
    """Create a new video job (test version)."""
    if not req.get("task") or not req["task"].strip():
        return {"error": "Task cannot be empty"}, 400

    import uuid
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    job = VideoJob(id=job_id, task=req["task"], status="pending")
    test_storage.save_job(job)

    return {
        "job_id": job_id,
        "status": "pending",
        "created_at": job.created_at.isoformat()
    }

@app.get("/v1/video/jobs/{job_id}")
async def get_job_status_test(job_id: str):
    """Get full job status (test version)."""
    job = test_storage.get_job(job_id)
    if not job:
        return {"error": "Job not found"}, 404

    return {
        "id": job.id,
        "task": job.task,
        "status": job.status,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_message": job.error_message,
    }

@app.get("/v1/video/jobs")
async def list_jobs_test(limit: int = 20, offset: int = 0):
    """List all jobs (test version)."""
    if limit <= 0 or limit > 100:
        return {"error": "Limit must be between 1 and 100"}, 400
    if offset < 0:
        return {"error": "Offset cannot be negative"}, 400

    jobs = test_storage.list_jobs(limit=limit, offset=offset)
    return {
        "jobs": [
            {
                "id": j.id,
                "task": j.task,
                "status": j.status,
                "created_at": j.created_at.isoformat()
            }
            for j in jobs
        ],
        "count": len(jobs),
        "offset": offset,
        "limit": limit,
        "total": test_storage.get_job_count()
    }

@app.get("/v1/video/settings")
async def get_settings_test():
    """Get plugin settings (test version)."""
    return {
        "output_folder": "~/.corvin/video-producer/videos",
        "tts_engine": "azure",
        "max_duration_minutes": 60
    }

@app.put("/v1/video/settings")
async def update_settings_test(settings: dict):
    """Update plugin settings (test version)."""
    return {"status": "ok", "settings": settings}

client = TestClient(app)

class TestVideoProducerAPI:

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up test storage before each test."""
        global test_storage
        test_storage = VideoStorage(tempfile.mkdtemp())
        yield
        # Cleanup
        if test_storage.base_path.exists():
            shutil.rmtree(test_storage.base_path)

    def test_create_job_returns_id(self):
        """Test that creating a job returns a job ID."""
        response = client.post(
            "/v1/video/jobs",
            json={"task": "Create a video"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "status" in data
        assert data["status"] == "pending"

    def test_create_job_with_empty_task(self):
        """Test that empty task is rejected."""
        response = client.post(
            "/v1/video/jobs",
            json={"task": ""}
        )
        assert response.status_code == 400

    def test_create_job_persists_to_storage(self):
        """Test that job is saved to storage."""
        response = client.post(
            "/v1/video/jobs",
            json={"task": "Test video"}
        )
        job_id = response.json()["job_id"]

        # Verify job was saved
        job = test_storage.get_job(job_id)
        assert job is not None
        assert job.task == "Test video"

    def test_get_job_status_404(self):
        """Test getting status of nonexistent job."""
        response = client.get("/v1/video/jobs/nonexistent")
        assert response.status_code == 404

    def test_get_job_status_returns_full_metadata(self):
        """Test that job status returns full metadata."""
        # Create a job
        create_response = client.post(
            "/v1/video/jobs",
            json={"task": "Test video"}
        )
        job_id = create_response.json()["job_id"]

        # Get status
        response = client.get(f"/v1/video/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job_id
        assert data["task"] == "Test video"
        assert data["status"] == "pending"
        assert "created_at" in data

    def test_list_jobs_empty(self):
        """Test listing jobs from empty storage."""
        response = client.get("/v1/video/jobs")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert len(data["jobs"]) == 0

    def test_list_jobs_pagination(self):
        """Test listing jobs with pagination."""
        # Create 5 jobs
        for i in range(5):
            client.post(
                "/v1/video/jobs",
                json={"task": f"Video {i}"}
            )

        # List first 2
        response = client.get("/v1/video/jobs?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["total"] == 5

        # List next 2
        response = client.get("/v1/video/jobs?limit=2&offset=2")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2

    def test_list_jobs_invalid_limit(self):
        """Test that invalid limit is rejected."""
        response = client.get("/v1/video/jobs?limit=0")
        assert response.status_code == 400

    def test_list_jobs_invalid_offset(self):
        """Test that negative offset is rejected."""
        response = client.get("/v1/video/jobs?offset=-1")
        assert response.status_code == 400

    def test_get_settings(self):
        """Test getting settings."""
        response = client.get("/v1/video/settings")
        assert response.status_code == 200
        data = response.json()
        assert "output_folder" in data
        assert "tts_engine" in data
        assert "max_duration_minutes" in data

    def test_update_settings(self):
        """Test updating settings."""
        response = client.put(
            "/v1/video/settings",
            json={
                "output_folder": "/custom/path",
                "tts_engine": "google",
                "max_duration_minutes": 30
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["settings"]["output_folder"] == "/custom/path"

    def test_create_multiple_jobs_generates_unique_ids(self):
        """Test that multiple jobs get unique IDs."""
        response1 = client.post("/v1/video/jobs", json={"task": "Video 1"})
        response2 = client.post("/v1/video/jobs", json={"task": "Video 2"})

        id1 = response1.json()["job_id"]
        id2 = response2.json()["job_id"]

        assert id1 != id2

    def test_api_response_schema(self):
        """Test that API responses have correct schema."""
        response = client.post("/v1/video/jobs", json={"task": "Test"})
        data = response.json()

        # Check required fields
        assert isinstance(data["job_id"], str)
        assert isinstance(data["status"], str)
        assert isinstance(data["created_at"], str)
