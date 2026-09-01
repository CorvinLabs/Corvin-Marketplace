# Brain Learning Tracker Plugin

## Purpose

The **Brain Learning Tracker** plugin monitors Brain subsystem learning and preference evolution, recording confidence scores, decision outcomes, and user feedback for continuous improvement (ADR-0314, L28).

## Usage Example

```python
from brain_learning_tracker import BrainLearningTracker

tracker = BrainLearningTracker()
await tracker.initialize(plugin_context)

# Track session events
await tracker.on_vibe_session_event({
    "type": "session_decided",
    "decision": "delegate_to_acs",
    "confidence": 0.92
})

# Track brain metrics
await tracker.on_brain_metric({
    "metric": "latency_ms",
    "value": 142
})

# Get operational status
diags = await tracker.get_diagnostics()
print(f"Events collected: {diags['events_collected']}")
```

## Integration Points

**Provides:**
- `initialize(context)` — Hook into Brain subsystem
- `on_vibe_session_event(event)` — Track Vibe decisions and outcomes
- `on_brain_metric(metric)` — Track performance metrics
- `get_diagnostics()` — Operational status
- `shutdown()` — Graceful cleanup

**Integrates with:**
- **Learning Infrastructure** (ADR-0314): Central event store for learning loop
- **Vibe Engineering** (ADR-0469): Session decision tracking
- **L28 Conversation Recall**: User preferences and interaction history
- **Confidence Intervals** (ADR-0315): Confidence scoring for decisions

## Compliance Notes

- **ADR-0314**: Learning infrastructure — event schema and persistence
- **ADR-0315**: Confidence intervals for decision reliability
- **L28 Conversation Recall**: User preference learning and modeling
- **GDPR Art. 30**: Learning events logged to audit trail
- **Tenant isolation**: Events include tenant_id for multi-tenant learning models

## References

- **Plugin**: `plugin:buildin-memory-brain_learning_tracker` (buildin tier)
- **Source**: `/home/shumway/projects/Corvin-Marketplace/plugins/buildin/memory/brain_learning_tracker/src/brain_learning_tracker.py`
- **Tests**: `tests/test_brain_learning_tracker.py` (8 test cases)
