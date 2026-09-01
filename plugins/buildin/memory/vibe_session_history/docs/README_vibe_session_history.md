# Vibe Session History Plugin

## Purpose

The **Vibe Session History** plugin maintains persistent history of Vibe session decisions, context snapshots, and outcomes for observability, auditing, and post-hoc analysis (ADR-0316, L28).

## Usage Example

```python
from vibe_session_history import VibeSessionHistory

history = VibeSessionHistory()
await history.initialize(plugin_context)

# Track session decision
await history.on_vibe_session_event({
    "type": "session_decided",
    "session_id": "s123",
    "decision": "delegate_to_acs",
    "confidence": 0.92,
    "context": {
        "input_type": "data_analysis",
        "complexity": "high",
        "requested_model": "claude-opus"
    }
})

# Track decision outcome
await history.on_brain_metric({
    "type": "outcome",
    "session_id": "s123",
    "metric": "latency_ms",
    "value": 245,
    "status": "success"
})

# Get diagnostics
diags = await history.get_diagnostics()
print(f"History size: {diags['events_collected']}")
```

## Integration Points

**Provides:**
- `initialize(context)` — Hook into Vibe session manager
- `on_vibe_session_event(event)` — Record session lifecycle and decisions
- `on_brain_metric(metric)` — Record decision outcomes and metrics
- `get_diagnostics()` — Operational status and event count
- `shutdown()` — Graceful cleanup

**Integrates with:**
- **Vibe Engineering** (ADR-0469): Session observability and decision tracking
- **Decision History** (ADR-0316): Persistent record of all decisions and outcomes
- **Brain Subsystems**: Latency, confidence, and performance metrics
- **Audit Trail**: All session history logged to central audit chain

## Session History Flow

```svg
<svg width="640" height="320" xmlns="http://www.w3.org/2000/svg">
  <text x="10" y="25" font-size="16" font-weight="bold">Vibe Session History</text>
  
  <!-- User request -->
  <rect x="20" y="60" width="100" height="40" fill="#e8f4f8" stroke="#333" stroke-width="2"/>
  <text x="30" y="85" font-size="11" font-weight="bold">User Request</text>
  
  <!-- Vibe decides -->
  <path d="M 120 80 L 170 110" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="130" y="95" font-size="9">route + decide</text>
  
  <!-- Session history recorder -->
  <rect x="170" y="80" width="160" height="80" fill="#fff8dc" stroke="#333" stroke-width="2"/>
  <text x="180" y="105" font-size="11" font-weight="bold">VibeSessionHistory</text>
  <text x="180" y="120" font-size="9">event_queue</text>
  <text x="180" y="133" font-size="9">on_vibe_session_event()</text>
  <text x="180" y="146" font-size="9">on_brain_metric()</text>
  
  <!-- Decision recorded -->
  <path d="M 330 120 L 380 100" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="340" y="115" font-size="9">record</text>
  
  <!-- Execute -->
  <rect x="380" y="60" width="110" height="40" fill="#e8f8e8" stroke="#333" stroke-width="2"/>
  <text x="390" y="85" font-size="11" font-weight="bold">Execute Decision</text>
  
  <!-- Outcome -->
  <path d="M 440 100 L 440 150" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="450" y="125" font-size="9">outcome</text>
  
  <path d="M 420 160 L 300 160" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  
  <!-- Audit trail -->
  <rect x="170" y="210" width="320" height="80" fill="#ffe8e8" stroke="#333" stroke-width="2" stroke-dasharray="5,5"/>
  <text x="180" y="235" font-size="10" font-weight="bold">Audit Trail (ADR-0316)</text>
  <text x="180" y="252" font-size="9">- Session ID, decision, confidence</text>
  <text x="180" y="267" font-size="9">- Context snapshot, execution time</text>
  <text x="180" y="282" font-size="9">- Outcome metrics, timestamp</text>
  
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#333"/>
    </marker>
  </defs>
</svg>
```

## Compliance Notes

- **ADR-0316**: Decision history layer — persistent record of all decisions and outcomes
- **ADR-0469**: Vibe Engineering — session-level observability
- **L28 Conversation Recall**: Session context and multi-turn history
- **GDPR Art. 30**: Session history logged to audit trail
- **GDPR Art. 17**: Erasure support (planned) — delete session history by session_id
- **Async Design**: All methods are async; safe for concurrent session handling
- **No-raise contract**: Event handling failures logged but never propagated

## References

- **Plugin**: `plugin:buildin-memory-vibe_session_history` (buildin tier)
- **Source**: `/home/shumway/projects/Corvin-Marketplace/plugins/buildin/memory/vibe_session_history/src/vibe_session_history.py`
- **Tests**: `tests/test_vibe_session_history.py` (8 test cases covering event tracking, diagnostics, concurrency)
