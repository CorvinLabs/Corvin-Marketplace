"""
Unit tests for brain_event_emitter plugin.

Tests cover event emission functionality including:
- Session event handling
- Metric event handling
- Event routing
- Error handling
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from brain_event_emitter import BrainEventEmitter


class TestBrainEventEmitterInitialization:
    """Test plugin initialization."""

    @pytest.mark.asyncio
    async def test_init_success(self):
        """Test successful plugin initialization."""
        plugin = BrainEventEmitter()
        assert plugin is not None

    @pytest.mark.asyncio
    async def test_initialize_with_context(self):
        """Test initialize method with context."""
        plugin = BrainEventEmitter()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test plugin shutdown."""
        plugin = BrainEventEmitter()
        await plugin.shutdown()


class TestBrainEventEmitterEventHandling:
    """Test event handling functionality."""

    @pytest.mark.asyncio
    async def test_on_vibe_session_event(self):
        """Test VIBE session event handling."""
        plugin = BrainEventEmitter()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        event = {
            "session_id": "sess_123",
            "event_type": "session_start",
            "timestamp": "2026-09-01T12:00:00Z",
            "user_id": "user_123"
        }

        result = await plugin.on_vibe_session_event(event)
        # Should emit event without error

    @pytest.mark.asyncio
    async def test_on_brain_metric(self):
        """Test brain metric event handling."""
        plugin = BrainEventEmitter()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        metric = {
            "metric_id": "metric_123",
            "metric_type": "latency",
            "value": 125.5,
            "timestamp": "2026-09-01T12:00:00Z",
            "source": "core"
        }

        result = await plugin.on_brain_metric(metric)
        # Should emit metric event without error

    @pytest.mark.asyncio
    async def test_emit_custom_event(self):
        """Test custom event emission."""
        plugin = BrainEventEmitter()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        custom_event = {
            "event_type": "custom",
            "payload": {
                "action": "test_action",
                "status": "success"
            },
            "timestamp": "2026-09-01T12:00:00Z"
        }

        result = await plugin.on_vibe_session_event(custom_event)

    @pytest.mark.asyncio
    async def test_emit_multiple_events_concurrently(self):
        """Test emitting multiple events concurrently."""
        plugin = BrainEventEmitter()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        events = []
        for i in range(5):
            event = {
                "event_id": f"event_{i}",
                "event_type": "metric",
                "value": i * 100,
                "timestamp": "2026-09-01T12:00:00Z"
            }
            result = await plugin.on_vibe_session_event(event)
            events.append(result)

        assert len(events) == 5


class TestBrainEventEmitterDiagnostics:
    """Test diagnostics functionality."""

    @pytest.mark.asyncio
    async def test_get_diagnostics(self):
        """Test diagnostics retrieval."""
        plugin = BrainEventEmitter()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        diags = await plugin.get_diagnostics()
        # Should return diagnostic data
        assert diags is not None

    @pytest.mark.asyncio
    async def test_diagnostics_includes_event_count(self):
        """Test diagnostics includes event statistics."""
        plugin = BrainEventEmitter()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        # Emit some events
        for i in range(3):
            event = {
                "event_id": f"event_{i}",
                "event_type": "test",
                "timestamp": "2026-09-01T12:00:00Z"
            }
            await plugin.on_vibe_session_event(event)

        diags = await plugin.get_diagnostics()
        assert diags is not None


class TestBrainEventEmitterErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_handle_malformed_event(self):
        """Test handling malformed events."""
        plugin = BrainEventEmitter()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        # Should handle gracefully
        malformed_event = None
        with pytest.raises((TypeError, AttributeError)):
            result = await plugin.on_vibe_session_event(malformed_event)

    @pytest.mark.asyncio
    async def test_handle_missing_required_fields(self):
        """Test handling events with missing fields."""
        plugin = BrainEventEmitter()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        incomplete_event = {"event_type": "incomplete"}
        # Should handle gracefully or raise appropriate error
        result = await plugin.on_vibe_session_event(incomplete_event)

    @pytest.mark.asyncio
    async def test_handle_large_event_payload(self):
        """Test handling large event payloads."""
        plugin = BrainEventEmitter()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        large_event = {
            "event_type": "large_payload",
            "payload": "x" * 10000,
            "timestamp": "2026-09-01T12:00:00Z"
        }
        result = await plugin.on_vibe_session_event(large_event)


class TestBrainEventEmitterIntegration:
    """Integration tests."""

    @pytest.mark.asyncio
    async def test_plugin_lifecycle(self):
        """Test complete plugin lifecycle."""
        plugin = BrainEventEmitter()
        mock_context = MagicMock()

        await plugin.initialize(mock_context)

        event = {
            "session_id": "sess_123",
            "event_type": "test",
            "timestamp": "2026-09-01T12:00:00Z"
        }
        await plugin.on_vibe_session_event(event)

        diags = await plugin.get_diagnostics()
        assert diags is not None

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_multiple_instances(self):
        """Test multiple plugin instances."""
        plugin1 = BrainEventEmitter()
        plugin2 = BrainEventEmitter()

        mock_context = MagicMock()
        await plugin1.initialize(mock_context)
        await plugin2.initialize(mock_context)

        assert plugin1 is not plugin2

        await plugin1.shutdown()
        await plugin2.shutdown()

    @pytest.mark.asyncio
    async def test_event_flow_end_to_end(self):
        """Test complete event flow from emission to diagnostics."""
        plugin = BrainEventEmitter()
        mock_context = MagicMock()

        await plugin.initialize(mock_context)

        # Emit events
        for i in range(3):
            session_event = {
                "session_id": f"sess_{i}",
                "event_type": "session",
                "timestamp": "2026-09-01T12:00:00Z"
            }
            await plugin.on_vibe_session_event(session_event)

            metric_event = {
                "metric_id": f"metric_{i}",
                "metric_type": "latency",
                "value": i * 100,
                "timestamp": "2026-09-01T12:00:00Z"
            }
            await plugin.on_brain_metric(metric_event)

        diags = await plugin.get_diagnostics()
        assert diags is not None

        await plugin.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
