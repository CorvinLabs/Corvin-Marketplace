# VIBE Metrics Aggregator

## Overview

The VIBE Metrics Aggregator collects and aggregates VIBE (Voice, Intelligence, Brain, Engine) session events and brain metrics in real-time. It provides diagnostics on session health, performance trends, and anomaly detection.

## Use Case

**Scenario:** A voice session runs for 45 minutes. The aggregator tracks: speech recognition latency, intent classification accuracy, response generation time, and error rates. At session end, it reports a dashboard showing latency spike at minute 23 (root cause: context depth exceeded 80%).

**Impact:** Enables real-time observability; identifies performance bottlenecks.

## Architecture

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg viewBox="0 0 600 400" xmlns="http://www.w3.org/2000/svg">
  <text x="300" y="30" font-size="24" font-weight="bold" text-anchor="middle">
    VIBE Metrics Aggregation Pipeline
  </text>
  
  <!-- Event Sources -->
  <rect x="30" y="70" width="100" height="70" fill="#E0F2F1" stroke="#00897B" stroke-width="2" rx="5"/>
  <text x="80" y="95" font-size="11" font-weight="bold" text-anchor="middle">Sessions</text>
  <text x="80" y="115" font-size="10" text-anchor="middle">Events</text>
  
  <rect x="150" y="70" width="100" height="70" fill="#F3E5F5" stroke="#7B1FA2" stroke-width="2" rx="5"/>
  <text x="200" y="95" font-size="11" font-weight="bold" text-anchor="middle">Brain</text>
  <text x="200" y="115" font-size="10" text-anchor="middle">Metrics</text>
  
  <rect x="270" y="70" width="100" height="70" fill="#FCE4EC" stroke="#C2185B" stroke-width="2" rx="5"/>
  <text x="320" y="95" font-size="11" font-weight="bold" text-anchor="middle">Performance</text>
  <text x="320" y="115" font-size="10" text-anchor="middle">Logs</text>
  
  <rect x="390" y="70" width="100" height="70" fill="#FFF3E0" stroke="#E65100" stroke-width="2" rx="5"/>
  <text x="440" y="95" font-size="11" font-weight="bold" text-anchor="middle">Errors</text>
  <text x="440" y="115" font-size="10" text-anchor="middle">Events</text>
  
  <!-- Aggregator -->
  <rect x="150" y="180" width="300" height="70" fill="#E3F2FD" stroke="#1976D2" stroke-width="2" rx="5"/>
  <text x="300" y="205" font-size="13" font-weight="bold" text-anchor="middle">VIBE Aggregator</text>
  <text x="300" y="225" font-size="11" text-anchor="middle">Collection, normalization, correlation</text>
  
  <!-- Arrows to aggregator -->
  <path d="M 80 140 L 250 180" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  <path d="M 200 140 L 280 180" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  <path d="M 320 140 L 320 180" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  <path d="M 440 140 L 350 180" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  
  <!-- Output -->
  <rect x="150" y="290" width="300" height="60" fill="#E8F5E9" stroke="#388E3C" stroke-width="2" rx="5"/>
  <text x="300" y="315" font-size="12" font-weight="bold" text-anchor="middle">Diagnostics & Dashboard</text>
  <text x="300" y="335" font-size="11" text-anchor="middle">Latency trends, anomalies, alerts</text>
  
  <!-- Arrow to output -->
  <path d="M 300 250 L 300 290" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#333"/>
    </marker>
  </defs>
</svg>
```

## API Example

```python
from vibe_metrics_aggregator import VibeMetricsAggregator

aggregator = VibeMetricsAggregator()
await aggregator.initialize(context)

# Subscribe to VIBE session events
session_event = {
    "session_id": "voice_sess_123",
    "event_type": "session_start",
    "timestamp": "2026-09-01T12:00:00Z",
    "speaker": "user"
}

await aggregator.on_vibe_session_event(session_event)

# Subscribe to brain metrics
metric = {
    "metric_id": "metric_001",
    "metric_type": "latency_ms",
    "value": 145.5,
    "timestamp": "2026-09-01T12:00:05Z",
    "source": "stt_engine"
}

await aggregator.on_brain_metric(metric)

# Get diagnostics
diagnostics = await aggregator.get_diagnostics()
# {
#     "session_count": 1,
#     "average_latency": 145.5,
#     "error_rate": 0.0,
#     "performance_trend": "stable",
#     "anomalies": []
# }
```

## Configuration

No configuration required. Auto-aggregates all events.

## Status

**Implementation:** Partial (event handlers present, core logic TBD)
**Tests:** 5 unit tests (event handling, diagnostics, lifecycle)
**Compliance:** GDPR Art. 30, 32 (audit logging)

---
**Plugin ID:** `plugin:buildin-data_processing-vibe_metrics_aggregator`  
**Version:** 1.0.0 | **Boot Layer:** bundled  
**Maintainer:** plugins@anthropic.com
