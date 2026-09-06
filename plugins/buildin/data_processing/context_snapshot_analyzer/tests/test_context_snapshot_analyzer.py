"""Tests for the context_snapshot_analyzer plugin — the REAL API.

The previous test module exercised an ``execute()`` / ``analyze_snapshot()``
API this plugin never had (it is an event-collecting observability stub with
``on_vibe_session_event`` / ``on_brain_metric`` / ``get_diagnostics``). Tests
that describe a fictional API never fail for the right reason; these describe
what ships.
"""
import pytest
from unittest.mock import MagicMock

from context_snapshot_analyzer import ContextSnapshotAnalyzer


@pytest.fixture
async def plugin():
    p = ContextSnapshotAnalyzer()
    await p.initialize(MagicMock())
    yield p
    await p.shutdown()


async def test_init_defaults():
    p = ContextSnapshotAnalyzer()
    assert p.enabled is True
    assert p.event_queue == []


async def test_initialize_keeps_context(plugin):
    assert plugin.context is not None


async def test_events_and_metrics_are_collected(plugin):
    await plugin.on_vibe_session_event({"type": "session_start", "session_id": "s1"})
    await plugin.on_brain_metric({"component": "layer_0", "latency_ms": 1.2})
    diag = await plugin.get_diagnostics()
    assert diag["status"] == "operational"
    assert diag["events_collected"] == 2
    assert diag["enabled"] is True


async def test_diagnostics_empty(plugin):
    diag = await plugin.get_diagnostics()
    assert diag["events_collected"] == 0


async def test_shutdown_is_idempotent(plugin):
    await plugin.shutdown()
    await plugin.shutdown()
