"""Unit tests for vibe_session_history plugin (ADR-0316, L28).

Coverage: Async lifecycle, event tracking, diagnostics.
Compliance: Decision history (ADR-0316), Vibe Engineering observability, GDPR Art. 30.
"""

import pytest
import asyncio
from unittest.mock import MagicMock

from vibe_session_history import VibeSessionHistory


class TestVibeSessionHistory:
    """Vibe session history tracking."""

    @pytest.mark.asyncio
    async def test_init_state(self):
        """Initialize with enabled state and empty queue."""
        history = VibeSessionHistory()
        assert history.enabled is True
        assert isinstance(history.event_queue, list)
        assert len(history.event_queue) == 0

    @pytest.mark.asyncio
    async def test_initialize_sets_context(self):
        """Initialize hook stores Vibe/Brain context."""
        history = VibeSessionHistory()
        mock_context = MagicMock()
        await history.initialize(mock_context)
        assert history.context is mock_context

    @pytest.mark.asyncio
    async def test_on_vibe_session_event_queues_decision(self):
        """Vibe session events record decisions and context."""
        history = VibeSessionHistory()
        event = {
            "type": "session_decided",
            "session_id": "s123",
            "decision": "delegate_to_acs",
            "confidence": 0.92
        }
        await history.on_vibe_session_event(event)
        assert len(history.event_queue) == 1
        assert event in history.event_queue

    @pytest.mark.asyncio
    async def test_on_brain_metric_records_outcome(self):
        """Brain metrics record decision outcomes."""
        history = VibeSessionHistory()
        metric = {
            "type": "outcome",
            "metric": "latency_ms",
            "value": 145,
            "session_id": "s123"
        }
        await history.on_brain_metric(metric)
        assert len(history.event_queue) == 1
        assert metric in history.event_queue

    @pytest.mark.asyncio
    async def test_get_diagnostics_session_count(self):
        """Diagnostics report collected session events."""
        history = VibeSessionHistory()
        for i in range(3):
            await history.on_vibe_session_event({"session": i})

        diags = await history.get_diagnostics()
        assert diags["events_collected"] == 3
        assert diags["status"] == "operational"
        assert diags["enabled"] is True

    @pytest.mark.asyncio
    async def test_shutdown_preserves_history(self):
        """Shutdown doesn't clear accumulated history."""
        history = VibeSessionHistory()
        await history.on_vibe_session_event({"id": 1})
        await history.on_vibe_session_event({"id": 2})

        await history.shutdown()
        assert len(history.event_queue) == 2

    @pytest.mark.asyncio
    async def test_concurrent_event_recording(self):
        """Multiple concurrent events are recorded correctly."""
        history = VibeSessionHistory()

        async def emit_events():
            for i in range(5):
                await history.on_vibe_session_event({"seq": i})

        async def emit_metrics():
            for i in range(5):
                await history.on_brain_metric({"seq": i})

        await asyncio.gather(emit_events(), emit_metrics())
        assert len(history.event_queue) == 10

    @pytest.mark.asyncio
    async def test_session_history_accumulation_large(self):
        """Accumulate large session history without error."""
        history = VibeSessionHistory()
        for i in range(100):
            await history.on_vibe_session_event({"session_num": i})

        assert len(history.event_queue) == 100
        diags = await history.get_diagnostics()
        assert diags["events_collected"] == 100

    def test_compliance_marker_decision_history(self):
        """Decision history and Vibe observability documented."""
        import vibe_session_history as mod
        doc = mod.__doc__
        assert "vibe" in doc.lower()
        assert "history" in doc.lower()
