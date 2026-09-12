"""Tests for Video Producer Console Panel integration."""

import pytest
from pathlib import Path
from datetime import datetime
from video_producer.console_panel import (
    VideoProducerPanel,
    VideoProductionRequest,
    VideoProductionStatus,
    VideoProductionMetrics,
    get_panel_config,
)


class TestConsolePanelConfiguration:
    """Test console panel configuration."""

    def test_panel_config_structure(self):
        """Panel configuration should have correct structure."""
        config = get_panel_config()
        assert isinstance(config, dict)
        assert config["id"] == "video-producer-panel"
        assert config["title"] == "Video Producer"
        assert config["icon"] == "film"
        assert config["route"] == "/video-producer"
        assert config["category"] == "media"

    def test_panel_static_attributes(self):
        """Panel should have all required static attributes."""
        assert VideoProducerPanel.panel_id == "video-producer-panel"
        assert VideoProducerPanel.title == "Video Producer"
        assert VideoProducerPanel.icon == "film"
        assert VideoProducerPanel.route == "/video-producer"
        assert VideoProducerPanel.category == "media"

    def test_panel_get_config_method(self):
        """get_config should return dict with all required fields."""
        config = VideoProducerPanel.get_config()
        required_fields = ["id", "title", "icon", "route", "component", "category"]
        for field in required_fields:
            assert field in config, f"Missing field in panel config: {field}"

    def test_panel_tags(self):
        """Panel should have relevant tags."""
        config = get_panel_config()
        assert "tags" in config
        assert "video" in config["tags"]
        assert "media" in config["tags"]


class TestVideoProductionRequest:
    """Test VideoProductionRequest Pydantic model."""

    def test_request_with_required_fields(self):
        """Request should validate with required fields only."""
        req = VideoProductionRequest(
            ppt_url="https://example.com/presentation.pptx",
            video_title="My Video"
        )
        assert req.ppt_url == "https://example.com/presentation.pptx"
        assert req.video_title == "My Video"
        assert req.narration_style == "professional"
        assert req.max_duration_minutes == 30
        assert req.enable_learning is True

    def test_request_with_all_fields(self):
        """Request should validate with all fields specified."""
        req = VideoProductionRequest(
            ppt_url="file:///local/presentation.pptx",
            video_title="Training Video",
            narration_style="casual",
            max_duration_minutes=45,
            enable_learning=False
        )
        assert req.ppt_url == "file:///local/presentation.pptx"
        assert req.narration_style == "casual"
        assert req.max_duration_minutes == 45
        assert req.enable_learning is False

    def test_request_defaults(self):
        """Request should use correct defaults."""
        req = VideoProductionRequest(
            ppt_url="test.pptx",
            video_title="Test"
        )
        assert req.narration_style == "professional"
        assert req.max_duration_minutes == 30
        assert req.enable_learning is True

    def test_request_missing_required_fields(self):
        """Request should fail without required fields."""
        with pytest.raises(ValueError):
            VideoProductionRequest()  # Missing ppt_url and video_title


class TestVideoProductionStatus:
    """Test VideoProductionStatus Pydantic model."""

    def test_status_minimal(self):
        """Status should be creatable with minimal fields."""
        status = VideoProductionStatus(
            job_id="test-job-123",
            status="pending",
            progress_percent=0,
            current_phase="ingestion",
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )
        assert status.job_id == "test-job-123"
        assert status.status == "pending"
        assert status.progress_percent == 0

    def test_status_with_error(self):
        """Status should support error reporting."""
        status = VideoProductionStatus(
            job_id="test-job-456",
            status="failed",
            progress_percent=0,
            current_phase="analyzing",
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            error_message="Asset analysis failed"
        )
        assert status.status == "failed"
        assert status.error_message == "Asset analysis failed"

    def test_status_with_video_urls(self):
        """Status should support video output URLs."""
        status = VideoProductionStatus(
            job_id="test-job-789",
            status="complete",
            progress_percent=100,
            current_phase="uploading",
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            video_url="https://storage.example.com/video.mp4",
            youtube_url="https://youtube.com/watch?v=abc123"
        )
        assert status.video_url == "https://storage.example.com/video.mp4"
        assert status.youtube_url == "https://youtube.com/watch?v=abc123"

    def test_status_progress_validation(self):
        """Status progress should be bounded 0-100."""
        # Should accept valid progress
        status = VideoProductionStatus(
            job_id="test",
            status="pending",
            progress_percent=50,
            current_phase="test",
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )
        assert status.progress_percent == 50

        # Should reject invalid progress
        with pytest.raises(ValueError):
            VideoProductionStatus(
                job_id="test",
                status="pending",
                progress_percent=150,  # Over 100
                current_phase="test",
                created_at=datetime.utcnow().isoformat(),
                updated_at=datetime.utcnow().isoformat(),
            )


class TestVideoProductionMetrics:
    """Test VideoProductionMetrics Pydantic model."""

    def test_metrics_defaults(self):
        """Metrics should have reasonable defaults."""
        metrics = VideoProductionMetrics()
        assert metrics.total_videos_created == 0
        assert metrics.total_duration_minutes == 0.0
        assert metrics.average_processing_time_seconds == 0.0
        assert metrics.success_rate_percent == 100.0
        assert metrics.total_scenes_narrated == 0

    def test_metrics_with_values(self):
        """Metrics should accept concrete values."""
        metrics = VideoProductionMetrics(
            total_videos_created=5,
            total_duration_minutes=120.5,
            average_processing_time_seconds=1800.0,
            success_rate_percent=95.0,
            total_scenes_narrated=32,
            learning_optimizer_score=0.87
        )
        assert metrics.total_videos_created == 5
        assert metrics.total_duration_minutes == 120.5
        assert metrics.success_rate_percent == 95.0
        assert metrics.learning_optimizer_score == 0.87


class TestConsolePanelRouteRegistration:
    """Test that routes can be registered on a mock FastAPI app."""

    def test_register_routes_creates_endpoints(self):
        """register_routes should create all required endpoints."""
        # Mock FastAPI app
        class MockApp:
            def __init__(self):
                self.routes = {}

            def post(self, path):
                def decorator(func):
                    self.routes[f"POST {path}"] = func
                    return func
                return decorator

            def get(self, path):
                def decorator(func):
                    self.routes[f"GET {path}"] = func
                    return func
                return decorator

            def delete(self, path):
                def decorator(func):
                    self.routes[f"DELETE {path}"] = func
                    return func
                return decorator

        app = MockApp()
        VideoProducerPanel.register_routes(app)

        # Verify all expected routes are registered
        expected_routes = [
            "POST /v1/console/video-producer/orchestrate",
            "GET /v1/console/video-producer/jobs/{job_id}",
            "GET /v1/console/video-producer/jobs/{job_id}/events",
            "GET /v1/console/video-producer/metrics",
            "DELETE /v1/console/video-producer/jobs/{job_id}",
            "GET /v1/console/video-producer/health",
        ]
        for route in expected_routes:
            assert route in app.routes, f"Missing route: {route}"


class TestPanelConsoleIntegration:
    """Test panel is ready for Console integration."""

    def test_panel_config_includes_component_name(self):
        """Panel config must specify React component name."""
        config = get_panel_config()
        assert config["component"] == "VideoProducerPanel"

    def test_panel_route_is_valid(self):
        """Panel route should be valid path."""
        config = get_panel_config()
        route = config["route"]
        assert route.startswith("/")
        assert not route.endswith("/") or route == "/"

    def test_panel_status_is_active(self):
        """Panel status should be active."""
        config = get_panel_config()
        assert config.get("status") in ["active", None]  # None means active by default
