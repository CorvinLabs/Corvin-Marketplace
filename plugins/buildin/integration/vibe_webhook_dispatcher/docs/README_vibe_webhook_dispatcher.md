# Vibe Webhook Dispatcher Plugin

## Purpose

The **Vibe Webhook Dispatcher** plugin monitors Vibe session lifecycle events and Brain subsystem metrics, dispatching them to external webhooks for real-time observability and audit trail integration (ADR-0469, L44).

## Usage Example

```python
from vibe_webhook_dispatcher import VibeWebhookDispatcher

dispatcher = VibeWebhookDispatcher()
await dispatcher.initialize(plugin_context)

# Dispatcher automatically hooks into:
# - Vibe session events (session_start, session_end, decision_made)
# - Brain metrics (latency, confidence, delegation_score)

# Check diagnostics
diags = await dispatcher.get_diagnostics()
print(f"Status: {diags['status']}, Events: {diags['events_collected']}")

await dispatcher.shutdown()
```

## Integration Points

**Provides:**
- `initialize(context)` — Hook into Vibe/Brain event bus
- `on_vibe_session_event(event)` — Handle session lifecycle events
- `on_brain_metric(metric)` — Handle subsystem metrics
- `get_diagnostics()` — Return operational status
- `shutdown()` — Graceful cleanup

**Integrates with:**
- **Vibe Engineering** (ADR-0469): Session observability and decision history
- **Brain Subsystems**: Latency, confidence, and learning metrics
- **L44 House Rules**: Non-critical observability component (always-on but optional)
- **Audit Trail**: Events recorded to central audit log via webhook dispatch

## Event Flow

```svg
<svg width="640" height="300" xmlns="http://www.w3.org/2000/svg">
  <text x="10" y="25" font-size="16" font-weight="bold">Vibe Webhook Dispatcher</text>
  
  <!-- Vibe session -->
  <rect x="20" y="60" width="120" height="40" fill="#e8f4f8" stroke="#333" stroke-width="2"/>
  <text x="30" y="85" font-size="11" font-weight="bold">Vibe Session</text>
  
  <!-- Brain subsystem -->
  <rect x="20" y="120" width="120" height="40" fill="#f0e8f4" stroke="#333" stroke-width="2"/>
  <text x="30" y="145" font-size="11" font-weight="bold">Brain Metrics</text>
  
  <!-- Dispatcher -->
  <path d="M 140 80 L 200 140" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <path d="M 140 140 L 200 140" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  
  <rect x="200" y="100" width="140" height="80" fill="#fff8dc" stroke="#333" stroke-width="2"/>
  <text x="210" y="125" font-size="11" font-weight="bold">Dispatcher</text>
  <text x="210" y="140" font-size="9">event_queue</text>
  <text x="210" y="153" font-size="9">enabled: true</text>
  <text x="210" y="166" font-size="9">context: ref</text>
  
  <!-- Webhook dispatch -->
  <path d="M 340 140 L 400 140" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="360" y="135" font-size="9">dispatch</text>
  
  <!-- External webhooks -->
  <rect x="400" y="60" width="120" height="40" fill="#e8f8e8" stroke="#333" stroke-width="2"/>
  <text x="410" y="85" font-size="11" font-weight="bold">Webhook</text>
  <text x="410" y="97" font-size="9">External Service</text>
  
  <rect x="400" y="120" width="120" height="40" fill="#e8f8e8" stroke="#333" stroke-width="2"/>
  <text x="410" y="145" font-size="11" font-weight="bold">Webhook</text>
  <text x="410" y="157" font-size="9">Monitoring</text>
  
  <!-- Audit trail -->
  <rect x="200" y="220" width="320" height="50" fill="#ffe8e8" stroke="#333" stroke-width="2" stroke-dasharray="5,5"/>
  <text x="210" y="245" font-size="10" font-weight="bold">Audit Trail (L44)</text>
  <text x="210" y="260" font-size="9">Non-critical observability; optional; always-on by default</text>
  
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#333"/>
    </marker>
  </defs>
</svg>
```

## Compliance Notes

- **ADR-0469**: Security Layer Architecture — non-critical observability component
- **L44 House Rules**: Always-on observability; never disable (but optional to implement custom handlers)
- **GDPR Art. 30**: Event dispatch logged to audit trail
- **Async Design**: All methods are async; safe for concurrent event handling
- **No-raise contract**: Exceptions logged but never propagated (fail-closed)

## References

- **Plugin**: `plugin:buildin-integration-vibe_webhook_dispatcher` (buildin tier, bundled boot layer)
- **Source**: `/home/shumway/projects/Corvin-Marketplace/plugins/buildin/integration/vibe_webhook_dispatcher/src/vibe_webhook_dispatcher.py`
- **Tests**: `tests/test_vibe_webhook_dispatcher.py` (8 test cases)
