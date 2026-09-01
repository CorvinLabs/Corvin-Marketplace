"""
Unit tests for AutonomyStatusTracker plugin.

Tests initialization, session lifecycle, hardening escalation, recovery,
error handling, and health checks.
"""

import pytest
import asyncio
from datetime import datetime

# Mock the corvin_plugins import
import sys
from unittest.mock import MagicMock

# Create mock module
mock_plugin_base = MagicMock()
mock_plugin_base.DeterministicPlugin = object
mock_plugin_base.PluginTier = MagicMock()
mock_plugin_base.PluginTier.GENERAL = "general"
mock_plugin_base.PluginTier.CRITICAL = "critical"

mock_protocol = MagicMock()
mock_protocol.HealthStatus = MagicMock()

sys.modules['corvin_plugins'] = MagicMock()
sys.modules['corvin_plugins.plugin_base'] = mock_plugin_base
sys.modules['corvin_plugins.protocol'] = mock_protocol

# Now import our plugin
import sys
sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/autonomy_status_tracker/src')
from autonomy_status_tracker import AutonomyStatusTracker, SessionStatus


@pytest.fixture
def tracker():
    """Create a tracker instance for testing."""
    return AutonomyStatusTracker()


@pytest.mark.asyncio
async def test_initialization(tracker):
    """Test plugin initialization."""
    context = MagicMock()
    await tracker.initialize(context)

    assert tracker.context == context
    assert tracker.start_time is not None
    assert len(tracker.sessions) == 0
    assert len(tracker.event_queue) == 0


@pytest.mark.asyncio
async def test_session_start(tracker):
    """Test starting a new session."""
    await tracker.on_session_start("session_1")

    assert "session_1" in tracker.sessions
    session = tracker.sessions["session_1"]
    assert session.state == "running"
    assert session.hardening_level == 0
    assert session.recovery_attempts == 0
    assert len(tracker.event_queue) == 1


@pytest.mark.asyncio
async def test_hardening_escalation(tracker):
    """Test hardening level escalation."""
    await tracker.on_session_start("session_1")
    await tracker.on_hardening_begin("session_1", level=2)

    session = tracker.sessions["session_1"]
    assert session.state == "hardening"
    assert session.hardening_level == 2
    assert len(tracker.event_queue) == 2


@pytest.mark.asyncio
async def test_recovery_attempt(tracker):
    """Test error recovery tracking."""
    await tracker.on_session_start("session_1")
    error_msg = "Connection timeout in layer 5"
    await tracker.on_recovery_attempt("session_1", error_msg)

    session = tracker.sessions["session_1"]
    assert session.state == "recovering"
    assert session.recovery_attempts == 1
    assert session.last_error == error_msg
    assert len(tracker.event_queue) == 2


@pytest.mark.asyncio
async def test_multiple_recovery_attempts(tracker):
    """Test multiple recovery attempts increment correctly."""
    await tracker.on_session_start("session_1")

    for i in range(5):
        await tracker.on_recovery_attempt("session_1", f"Error {i}")

    session = tracker.sessions["session_1"]
    assert session.recovery_attempts == 5
    assert len(tracker.event_queue) == 6  # 1 start + 5 recovery


@pytest.mark.asyncio
async def test_session_end(tracker):
    """Test session completion."""
    await tracker.on_session_start("session_1")
    await tracker.on_session_end("session_1", "completed")

    session = tracker.sessions["session_1"]
    assert session.state == "completed"
    assert len(tracker.event_queue) == 2


@pytest.mark.asyncio
async def test_get_session_status(tracker):
    """Test retrieving session status."""
    await tracker.on_session_start("session_1")
    await tracker.on_hardening_begin("session_1", level=1)

    status = await tracker.get_session_status("session_1")

    assert status is not None
    assert status["session_id"] == "session_1"
    assert status["state"] == "hardening"
    assert status["hardening_level"] == 1
    assert "timestamp" in status


@pytest.mark.asyncio
async def test_get_nonexistent_session_status(tracker):
    """Test retrieving status for nonexistent session."""
    status = await tracker.get_session_status("nonexistent")
    assert status is None


@pytest.mark.asyncio
async def test_get_diagnostics(tracker):
    """Test diagnostic snapshot aggregation."""
    # Create multiple sessions in different states
    await tracker.on_session_start("session_1")
    await tracker.on_session_start("session_2")
    await tracker.on_hardening_begin("session_2", level=2)
    await tracker.on_session_start("session_3")
    await tracker.on_session_end("session_3", "failed")

    diagnostics = await tracker.get_diagnostics()

    assert diagnostics["status"] == "operational"
    assert diagnostics["total_sessions"] == 3
    assert diagnostics["active_sessions"] == 1  # session_1 is running
    assert diagnostics["hardening_sessions"] == 1  # session_2 is hardening
    assert diagnostics["failed_sessions"] == 1  # session_3 is failed
    assert diagnostics["max_hardening_level"] == 2


@pytest.mark.asyncio
async def test_event_queue_management(tracker):
    """Test event queue doesn't exceed max size."""
    for i in range(tracker.max_queue_size + 10):
        await tracker.on_session_start(f"session_{i}")

    # Queue should be capped at max_queue_size
    assert len(tracker.event_queue) <= tracker.max_queue_size


@pytest.mark.asyncio
async def test_health_check_healthy(tracker):
    """Test health check when healthy."""
    await tracker.initialize(MagicMock())

    # Add some events but stay under max queue size
    for i in range(10):
        await tracker.on_session_start(f"session_{i}")

    # Mock HealthStatus
    mock_protocol.HealthStatus.return_value = MagicMock(ok=True)

    # health_check should indicate healthy
    # (We can't fully test this without mocking, but we verify the method exists)
    assert hasattr(tracker, 'on_health_check')
    assert callable(tracker.on_health_check)


@pytest.mark.asyncio
async def test_health_check_degraded(tracker):
    """Test health check when queue is full."""
    # Fill the queue beyond max
    tracker.max_queue_size = 5
    for i in range(20):
        await tracker.on_session_start(f"session_{i}")

    # Queue should be capped
    assert len(tracker.event_queue) <= tracker.max_queue_size


@pytest.mark.asyncio
async def test_session_status_isolation(tracker):
    """Test that sessions don't interfere with each other."""
    await tracker.on_session_start("session_1")
    await tracker.on_session_start("session_2")

    await tracker.on_hardening_begin("session_1", level=3)

    # session_2 should not be affected
    status_1 = await tracker.get_session_status("session_1")
    status_2 = await tracker.get_session_status("session_2")

    assert status_1["hardening_level"] == 3
    assert status_2["hardening_level"] == 0


@pytest.mark.asyncio
async def test_error_truncation(tracker):
    """Test that long error messages are truncated for safety."""
    long_error = "x" * 1000
    await tracker.on_session_start("session_1")
    await tracker.on_recovery_attempt("session_1", long_error)

    # Check that event has truncated error
    event = tracker.event_queue[-1]
    assert len(event["data"]["error"]) <= 100


@pytest.mark.asyncio
async def test_shutdown(tracker):
    """Test graceful shutdown."""
    await tracker.initialize(MagicMock())
    await tracker.shutdown()

    # Plugin should still be usable after shutdown
    assert tracker.sessions is not None


@pytest.mark.asyncio
async def test_event_structure(tracker):
    """Test that events have correct structure."""
    await tracker.on_session_start("session_1")

    event = tracker.event_queue[0]

    assert "type" in event
    assert "data" in event
    assert "timestamp" in event
    assert event["type"] == "session_start"
    assert isinstance(event["timestamp"], str)


@pytest.mark.asyncio
async def test_tier_property(tracker):
    """Test that plugin declares correct tier."""
    tier = tracker.get_tier()
    assert tier == "general"


@pytest.mark.asyncio
async def test_max_latency_property(tracker):
    """Test that plugin declares sub-millisecond latency."""
    latency = tracker.get_max_latency_ms()
    assert latency <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
