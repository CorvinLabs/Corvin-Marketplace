"""Unit tests for vibe_webhook_dispatcher plugin (ADR-0469, L44).

Coverage: Async lifecycle, event queue management, diagnostics.
Compliance: Non-critical observability plugin, graceful shutdown, GDPR Art. 30.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

from vibe_webhook_dispatcher import VibeWebhookDispatcher


class TestVibeWebhookDispatcher:
    """Vibe Engineering webhook dispatcher lifecycle."""

    @pytest.mark.asyncio
    async def test_init_state(self):
        """Initialize with enabled state and empty event queue."""
        dispatcher = VibeWebhookDispatcher()
        assert dispatcher.enabled is True
        assert isinstance(dispatcher.event_queue, list)
        assert len(dispatcher.event_queue) == 0

    @pytest.mark.asyncio
    async def test_initialize_sets_context(self):
        """Initialize hook stores context reference."""
        dispatcher = VibeWebhookDispatcher()
        mock_context = MagicMock()
        await dispatcher.initialize(mock_context)
        assert dispatcher.context is mock_context

    @pytest.mark.asyncio
    async def test_on_vibe_session_event_queues_event(self):
        """Vibe session events are queued."""
        dispatcher = VibeWebhookDispatcher()
        event1 = {"type": "session_start", "session_id": "s1"}
        event2 = {"type": "session_end", "session_id": "s1"}

        await dispatcher.on_vibe_session_event(event1)
        await dispatcher.on_vibe_session_event(event2)

        assert len(dispatcher.event_queue) == 2
        assert event1 in dispatcher.event_queue
        assert event2 in dispatcher.event_queue

    @pytest.mark.asyncio
    async def test_on_brain_metric_queues_metric(self):
        """Brain subsystem metrics are queued."""
        dispatcher = VibeWebhookDispatcher()
        metric1 = {"metric": "latency", "value": 42}
        metric2 = {"metric": "memory", "value": 256}

        await dispatcher.on_brain_metric(metric1)
        await dispatcher.on_brain_metric(metric2)

        assert len(dispatcher.event_queue) == 2
        assert metric1 in dispatcher.event_queue
        assert metric2 in dispatcher.event_queue

    @pytest.mark.asyncio
    async def test_get_diagnostics_reflects_state(self):
        """Diagnostics report queue size and enabled status."""
        dispatcher = VibeWebhookDispatcher()
        await dispatcher.on_vibe_session_event({"type": "test"})
        await dispatcher.on_brain_metric({"metric": "test"})

        diags = await dispatcher.get_diagnostics()
        assert diags["status"] == "operational"
        assert diags["events_collected"] == 2
        assert diags["enabled"] is True

    @pytest.mark.asyncio
    async def test_get_diagnostics_when_disabled(self):
        """Diagnostics reflect disabled state."""
        dispatcher = VibeWebhookDispatcher()
        dispatcher.enabled = False

        diags = await dispatcher.get_diagnostics()
        assert diags["enabled"] is False
        assert diags["status"] == "operational"

    @pytest.mark.asyncio
    async def test_shutdown_graceful(self):
        """Shutdown completes without error."""
        dispatcher = VibeWebhookDispatcher()
        await dispatcher.on_vibe_session_event({"type": "event"})

        # Should not raise
        await dispatcher.shutdown()

        # Event queue still intact (shutdown doesn't clear)
        assert len(dispatcher.event_queue) == 1

    @pytest.mark.asyncio
    async def test_event_queue_accumulation(self):
        """Event queue accumulates multiple events without limit."""
        dispatcher = VibeWebhookDispatcher()

        # Queue many events
        for i in range(100):
            await dispatcher.on_vibe_session_event({"id": i})

        assert len(dispatcher.event_queue) == 100

    @pytest.mark.asyncio
    async def test_concurrent_event_handling(self):
        """Multiple concurrent event handlers work correctly."""
        dispatcher = VibeWebhookDispatcher()

        # Simulate concurrent event submissions
        tasks = [
            dispatcher.on_vibe_session_event({"id": i})
            for i in range(10)
        ]
        await asyncio.gather(*tasks)

        assert len(dispatcher.event_queue) == 10

    def test_compliance_marker_non_critical(self):
        """Non-critical observability plugin documented."""
        import vibe_webhook_dispatcher as mod
        doc = mod.__doc__
        assert "non-critical" in doc.lower()
        assert "optional" in doc.lower()
