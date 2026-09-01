"""Unit tests for brain_learning_tracker plugin (ADR-0314, L28).

Coverage: Async lifecycle, event tracking, preferences, diagnostics.
Compliance: Learning layer (ADR-0314), event-store integration, GDPR Art. 30.
"""

import pytest
import asyncio
from unittest.mock import MagicMock

from brain_learning_tracker import BrainLearningTracker


class TestBrainLearningTracker:
    """Brain learning tracker lifecycle and event management."""

    @pytest.mark.asyncio
    async def test_init_state(self):
        """Initialize with enabled state and empty queue."""
        tracker = BrainLearningTracker()
        assert tracker.enabled is True
        assert isinstance(tracker.event_queue, list)
        assert len(tracker.event_queue) == 0

    @pytest.mark.asyncio
    async def test_initialize_sets_context(self):
        """Initialize hook stores Vibe/Brain context."""
        tracker = BrainLearningTracker()
        mock_context = MagicMock()
        await tracker.initialize(mock_context)
        assert tracker.context is mock_context

    @pytest.mark.asyncio
    async def test_on_vibe_session_event(self):
        """Track Vibe session lifecycle events."""
        tracker = BrainLearningTracker()
        event = {"type": "session_created", "session_id": "s1", "model": "claude-opus"}
        await tracker.on_vibe_session_event(event)
        assert len(tracker.event_queue) == 1
        assert event in tracker.event_queue

    @pytest.mark.asyncio
    async def test_on_brain_metric(self):
        """Track Brain subsystem metrics."""
        tracker = BrainLearningTracker()
        metric = {"metric": "confidence_score", "value": 0.85}
        await tracker.on_brain_metric(metric)
        assert len(tracker.event_queue) == 1
        assert metric in tracker.event_queue

    @pytest.mark.asyncio
    async def test_get_diagnostics(self):
        """Diagnostics report collected events and enabled status."""
        tracker = BrainLearningTracker()
        await tracker.on_vibe_session_event({"type": "event"})
        await tracker.on_brain_metric({"metric": "test"})

        diags = await tracker.get_diagnostics()
        assert diags["status"] == "operational"
        assert diags["events_collected"] == 2
        assert diags["enabled"] is True

    @pytest.mark.asyncio
    async def test_shutdown_graceful(self):
        """Shutdown completes gracefully."""
        tracker = BrainLearningTracker()
        await tracker.on_vibe_session_event({"type": "event"})
        await tracker.shutdown()
        # Queue should still be intact after shutdown
        assert len(tracker.event_queue) == 1

    @pytest.mark.asyncio
    async def test_event_accumulation_large_batch(self):
        """Accumulate large batch of events without error."""
        tracker = BrainLearningTracker()
        for i in range(50):
            await tracker.on_vibe_session_event({"event_num": i})
        assert len(tracker.event_queue) == 50

    @pytest.mark.asyncio
    async def test_concurrent_event_processing(self):
        """Concurrent events from multiple handlers."""
        tracker = BrainLearningTracker()

        async def emit_session_events():
            for i in range(5):
                await tracker.on_vibe_session_event({"session": i})

        async def emit_metrics():
            for i in range(5):
                await tracker.on_brain_metric({"metric": i})

        await asyncio.gather(emit_session_events(), emit_metrics())
        assert len(tracker.event_queue) == 10

    def test_compliance_marker_learning_layer(self):
        """ADR-0314 learning infrastructure documented."""
        import brain_learning_tracker as mod
        doc = mod.__doc__
        assert "learning" in doc.lower()
        assert "observability" in doc.lower()
