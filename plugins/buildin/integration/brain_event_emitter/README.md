# Brain Event Emitter

## Overview

The Brain Event Emitter publishes VIBE session and brain metrics to downstream systems (dashboards, analytics, event buses). It maintains a fire-and-forget queue to avoid blocking the event source and supports multiple event types (session_start, session_end, metric_recorded, anomaly_detected).

## Use Case

**Scenario:** A session completes. The emitter publishes events to: (1) Vibe Dashboard (live chart update), (2) Prometheus (metrics export), (3) Datadog (log ingest). Each destination gets its own non-blocking queue; if Datadog is slow, Prometheus still gets fast delivery.

**Impact:** Enables real-time event distribution; maintains system responsiveness.

## Architecture

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg viewBox="0 0 600 400" xmlns="http://www.w3.org/2000/svg">
  <text x="300" y="30" font-size="24" font-weight="bold" text-anchor="middle">
    Brain Event Emission Pipeline
  </text>
  
  <!-- Event Sources -->
  <rect x="40" y="70" width="100" height="70" fill="#E0F2F1" stroke="#00897B" stroke-width="2" rx="5"/>
  <text x="90" y="95" font-size="11" font-weight="bold" text-anchor="middle">VIBE</text>
  <text x="90" y="115" font-size="10" text-anchor="middle">Session</text>
  
  <rect x="160" y="70" width="100" height="70" fill="#E8F5E9" stroke="#388E3C" stroke-width="2" rx="5"/>
  <text x="210" y="95" font-size="11" font-weight="bold" text-anchor="middle">Brain</text>
  <text x="210" y="115" font-size="10" text-anchor="middle">Metrics</text>
  
  <rect x="280" y="70" width="100" height="70" fill="#FFF3E0" stroke="#E65100" stroke-width="2" rx="5"/>
  <text x="330" y="95" font-size="11" font-weight="bold" text-anchor="middle">Anomaly</text>
  <text x="330" y="115" font-size="10" text-anchor="middle">Detector</text>
  
  <rect x="400" y="70" width="100" height="70" fill="#FCE4EC" stroke="#C2185B" stroke-width="2" rx="5"/>
  <text x="450" y="95" font-size="11" font-weight="bold" text-anchor="middle">Custom</text>
  <text x="450" y="115" font-size="10" text-anchor="middle">Events</text>
  
  <!-- Event Queue -->
  <rect x="100" y="180" width="400" height="70" fill="#F3E5F5" stroke="#7B1FA2" stroke-width="2" rx="5"/>
  <text x="300" y="205" font-size="13" font-weight="bold" text-anchor="middle">Event Queue (Fire-and-Forget)</text>
  <text x="300" y="225" font-size="11" text-anchor="middle">Non-blocking async queue, max 10k events</text>
  
  <!-- Arrows to queue -->
  <path d="M 90 140 L 200 180" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  <path d="M 210 140 L 280 180" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  <path d="M 330 140 L 330 180" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  <path d="M 450 140 L 400 180" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  
  <!-- Destinations -->
  <rect x="40" y="290" width="100" height="60" fill="#E3F2FD" stroke="#1976D2" stroke-width="2" rx="5"/>
  <text x="90" y="315" font-size="11" font-weight="bold" text-anchor="middle">Vibe</text>
  <text x="90" y="330" font-size="10" text-anchor="middle">Dashboard</text>
  
  <rect x="160" y="290" width="100" height="60" fill="#E3F2FD" stroke="#1976D2" stroke-width="2" rx="5"/>
  <text x="210" y="315" font-size="11" font-weight="bold" text-anchor="middle">Prometheus</text>
  <text x="210" y="330" font-size="10" text-anchor="middle">Metrics</text>
  
  <rect x="280" y="290" width="100" height="60" fill="#E3F2FD" stroke="#1976D2" stroke-width="2" rx="5"/>
  <text x="330" y="315" font-size="11" font-weight="bold" text-anchor="middle">Datadog</text>
  <text x="330" y="330" font-size="10" text-anchor="middle">Logs</text>
  
  <rect x="400" y="290" width="100" height="60" fill="#E3F2FD" stroke="#1976D2" stroke-width="2" rx="5"/>
  <text x="450" y="315" font-size="11" font-weight="bold" text-anchor="middle">Custom</text>
  <text x="450" y="330" font-size="10" text-anchor="middle">Backend</text>
  
  <!-- Arrows to destinations -->
  <path d="M 200 250 L 90 290" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  <path d="M 250 250 L 210 290" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  <path d="M 300 250 L 330 290" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  <path d="M 350 250 L 450 290" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#333"/>
    </marker>
  </defs>
</svg>
```

## API Example

```python
from brain_event_emitter import BrainEventEmitter

emitter = BrainEventEmitter()
await emitter.initialize(context)

# Receive and emit VIBE session events
session_event = {
    "session_id": "voice_sess_123",
    "event_type": "session_start",
    "timestamp": "2026-09-01T12:00:00Z",
    "speaker": "user",
    "engine": "ClaudeEngine"
}

await emitter.on_vibe_session_event(session_event)
# Event queued for distribution to all subscribers

# Emit brain metrics
metric_event = {
    "metric_id": "metric_001",
    "metric_type": "latency_ms",
    "value": 125.5,
    "timestamp": "2026-09-01T12:00:05Z",
    "source": "stt_engine"
}

await emitter.on_brain_metric(metric_event)
# Queued non-blocking; returns immediately

# Get diagnostics
diagnostics = await emitter.get_diagnostics()
# {
#     "total_events_emitted": 2,
#     "queue_size": 2,
#     "destinations_active": 4,
#     "last_emission": "2026-09-01T12:00:05Z",
#     "error_rate": 0.0
# }
```

## Configuration

No configuration required. Auto-discovers downstream subscribers.

## Status

**Implementation:** Partial (event handlers present, queue logic TBD)
**Tests:** 6 unit tests (event handling, diagnostics, concurrency, lifecycle)
**Compliance:** GDPR Art. 30, 32 (audit trail)

---
**Plugin ID:** `plugin:buildin-integration-brain_event_emitter`  
**Version:** 1.0.0 | **Boot Layer:** bundled  
**Maintainer:** plugins@anthropic.com
