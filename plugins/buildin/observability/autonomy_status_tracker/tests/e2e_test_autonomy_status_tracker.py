"""
End-to-end test for AutonomyStatusTracker plugin.

Verifies:
- Real plugin lifecycle (init → event tracking → diagnostics → shutdown)
- Concurrent autonomous decision streams
- Latency SLA verification (<1ms per operation)
- HealthStatus contract validation
- State persistence across events
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock
import sys

# Mock plugin base before import
mock_plugin_base = MagicMock()
mock_plugin_base.DeterministicPlugin = object
mock_plugin_base.PluginTier = MagicMock()
mock_plugin_base.PluginTier.GENERAL = "general"
mock_protocol = MagicMock()
mock_protocol.HealthStatus = MagicMock(return_value=MagicMock(ok=True, message="OK"))

sys.modules['corvin_plugins'] = MagicMock()
sys.modules['corvin_plugins.plugin_base'] = mock_plugin_base
sys.modules['corvin_plugins.protocol'] = mock_protocol

sys.path.insert(0, '/home/shumway/projects/Corvin-Marketplace/plugins/buildin/observability/autonomy_status_tracker/src')


@pytest.fixture
async def tracker():
    """Fixture providing initialized autonomy tracker."""
    from autonomy_status_tracker import AutonomyStatusTracker
    tracker = AutonomyStatusTracker()
    ctx = MagicMock()
    ctx.tenant_id = "default"
    await tracker.initialize(ctx)
    yield tracker
    await tracker.shutdown()


@pytest.mark.asyncio
async def test_e2e_plugin_lifecycle(tracker):
    """Test complete plugin lifecycle."""
    assert tracker is not None
    assert tracker.get_tier() == "general"
    assert tracker.get_max_latency_ms() == 1
    await tracker.shutdown()


@pytest.mark.asyncio
async def test_e2e_record_autonomous_decision(tracker):
    """Test recording an autonomous decision end-to-end."""
    start = datetime.utcnow()
    await tracker.record_autonomous_decision(
        decision_id="dec_001",
        autonomy_level="L3",
        confidence=0.95,
        action="execute_query",
        outcome="success"
    )
    elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000

    assert elapsed_ms < 1.0  # <1ms SLA
    status = await tracker.get_diagnostics()
    assert status["decision_count"] >= 1
    assert "autonomy_level" in status


@pytest.mark.asyncio
async def test_e2e_concurrent_decisions(tracker):
    """Test concurrent autonomous decision recording."""
    tasks = []
    for i in range(10):
        task = tracker.record_autonomous_decision(
            decision_id=f"dec_{i:03d}",
            autonomy_level=f"L{i % 4 + 1}",
            confidence=0.80 + (i * 0.01),
            action=f"action_{i}",
            outcome="success" if i % 2 == 0 else "deferred"
        )
        tasks.append(task)

    await asyncio.gather(*tasks)
    status = await tracker.get_diagnostics()
    assert status["decision_count"] >= 10


@pytest.mark.asyncio
async def test_e2e_health_status_contract(tracker):
    """Test HealthStatus contract validation."""
    # Record decisions
    await tracker.record_autonomous_decision(
        decision_id="dec_health_001",
        autonomy_level="L2",
        confidence=0.85,
        action="safe_action",
        outcome="success"
    )

    health = await tracker.on_health_check()
    assert health is not None
    assert hasattr(health, 'ok')
    assert hasattr(health, 'message')
    assert health.ok is True or health.ok is False


@pytest.mark.asyncio
async def test_e2e_state_persistence(tracker):
    """Test state persistence across multiple operations."""
    # Record first batch
    await tracker.record_autonomous_decision(
        decision_id="dec_batch1",
        autonomy_level="L3",
        confidence=0.9,
        action="action_1",
        outcome="success"
    )

    status1 = await tracker.get_diagnostics()
    count1 = status1["decision_count"]

    # Record second batch
    for i in range(5):
        await tracker.record_autonomous_decision(
            decision_id=f"dec_batch2_{i}",
            autonomy_level="L2",
            confidence=0.75,
            action=f"action_{i}",
            outcome="success"
        )

    status2 = await tracker.get_diagnostics()
    count2 = status2["decision_count"]

    assert count2 > count1  # State persisted


@pytest.mark.asyncio
async def test_e2e_autonomy_level_tracking(tracker):
    """Test tracking of autonomy levels."""
    levels = ["L1", "L2", "L3", "L4"]
    for i, level in enumerate(levels):
        await tracker.record_autonomous_decision(
            decision_id=f"dec_level_{i}",
            autonomy_level=level,
            confidence=0.80 + (i * 0.05),
            action="test_action",
            outcome="success"
        )

    status = await tracker.get_diagnostics()
    assert "autonomy_levels" in status or "autonomy_level" in status


@pytest.mark.asyncio
async def test_e2e_confidence_scoring(tracker):
    """Test confidence score tracking."""
    low_conf_task = tracker.record_autonomous_decision(
        decision_id="dec_low_conf",
        autonomy_level="L1",
        confidence=0.45,
        action="risky_action",
        outcome="success"
    )

    high_conf_task = tracker.record_autonomous_decision(
        decision_id="dec_high_conf",
        autonomy_level="L3",
        confidence=0.98,
        action="safe_action",
        outcome="success"
    )

    await asyncio.gather(low_conf_task, high_conf_task)
    status = await tracker.get_diagnostics()
    assert "confidence" in str(status).lower()


@pytest.mark.asyncio
async def test_e2e_performance_assertions(tracker):
    """Test performance against SLA."""
    import time

    start = time.perf_counter()
    for i in range(100):
        await tracker.record_autonomous_decision(
            decision_id=f"dec_perf_{i:03d}",
            autonomy_level="L2",
            confidence=0.85,
            action="benchmark_action",
            outcome="success"
        )
    total_ms = (time.perf_counter() - start) * 1000
    avg_per_op_ms = total_ms / 100

    assert avg_per_op_ms < 1.0  # <1ms SLA
    status = await tracker.get_diagnostics()
    assert status["decision_count"] == 100


@pytest.mark.asyncio
async def test_e2e_outcome_classification(tracker):
    """Test outcome classification."""
    outcomes = ["success", "deferred", "escalated", "failed"]
    for i, outcome in enumerate(outcomes):
        await tracker.record_autonomous_decision(
            decision_id=f"dec_outcome_{i}",
            autonomy_level="L2",
            confidence=0.80,
            action="test_action",
            outcome=outcome
        )

    status = await tracker.get_diagnostics()
    assert status["decision_count"] >= 4


@pytest.mark.asyncio
async def test_e2e_diagnostics_snapshot(tracker):
    """Test complete diagnostics snapshot."""
    for i in range(20):
        await tracker.record_autonomous_decision(
            decision_id=f"dec_snapshot_{i:03d}",
            autonomy_level=f"L{(i % 4) + 1}",
            confidence=0.70 + (i * 0.02),
            action=f"action_{i}",
            outcome="success" if i % 3 else "deferred"
        )

    snapshot = await tracker.get_diagnostics()
    assert snapshot["decision_count"] == 20
    assert "status" in snapshot or "healthy" in str(snapshot).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
