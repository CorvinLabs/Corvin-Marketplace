# Autonomy Status Tracker

**Plugin ID:** `autonomy_status_tracker`  
**Category:** Observability  
**Version:** 1.0.0  
**Tier:** Buildin  
**ADRs:** ADR-0469, ADR-0314

## Overview

Real-time tracking of autonomous agent execution state, metrics, and lifecycle events. Monitors status transitions, aggregates performance metrics (latency, throughput, decisions/min), and provides diagnostics for failed autonomous sessions.

**Use Case:** CorvinOS autonomous loops need to expose their current state (running/paused/error/stopped) and execution metrics to dashboards, alerting systems, and self-repair engines.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Autonomous Agent (k=1-5 iterations)                    │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Loop: observe() → fix() → measure() → iterate()   │   │
│  │        ↓                                            │   │
│  │  autonomy_status_tracker.update_status()          │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
        ↓ (event stream)
┌─────────────────────────────────────────────────────────┐
│  Status Tracker Core                                    │
│  ┌────────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ Current Status │  │ Metrics Agg  │  │ History    │  │
│  │ (idle/running/ │  │ (latency,    │  │ (status    │  │
│  │  paused/error) │  │  throughput, │  │  changes)  │  │
│  │                │  │  decisions)  │  │            │  │
│  └────────────────┘  └──────────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────┘
        ↓ (metrics/state)
┌─────────────────────────────────────────────────────────┐
│  Consumers (Observability)                              │
│  ┌──────────────────┐  ┌──────────────┐                 │
│  │ Vibe Dashboard   │  │ Alerting     │                 │
│  │ (real-time UI)   │  │ (thresholds) │                 │
│  └──────────────────┘  └──────────────┘                 │
└─────────────────────────────────────────────────────────┘
```

## API

### StatusTracker Class

```python
from autonomy_status_tracker import AutonomyStatusTracker

tracker = AutonomyStatusTracker()

# Update status
tracker.update_status("running", {"task_id": "t123"})

# Record metrics (per iteration)
tracker.record_metric("latency_ms", 42)
tracker.record_metric("decisions_made", 1)

# Query state
state_dict = tracker.to_dict()  # JSON-serializable
status = tracker.status  # "idle"|"running"|"paused"|"error"|"stopped"

# Get statistics
stats = tracker.get_metric_stats("latency_ms")
# → {"count": 5, "avg": 45.0, "min": 30, "max": 60, "p99": 58}
```

## Compliance

- **GDPR Art. 30:** Event log tracks all status changes (audit trail)
- **GDPR Art. 32:** Metrics stored in-memory with TTL cleanup
- **ADR-0469:** Non-critical observability (must not block autonomous loop)
- **ADR-0314:** Learning event integration (feedback from metrics)

## Tests

### Unit Tests (11 testcases)
- ✅ Initialization
- ✅ Status update & validation
- ✅ Metrics aggregation (avg, min, max, percentiles)
- ✅ Status history tracking
- ✅ Thread-safe concurrent updates
- ✅ Async status update (await-compatible)
- ✅ Error handling (invalid status)
- ✅ Metrics edge cases (0, negative, overflow)
- ✅ Reset to initial state
- ✅ Serialization to dict
- ✅ Recovery from error state

### E2E Tests (3 scenarios)
- ✅ **Full Lifecycle:** boot → run → pause → resume → shutdown (metrics aggregated)
- ✅ **Concurrent Tasks:** 3 parallel autonomous tasks tracked independently
- ✅ **Error Recovery:** error → recovery → back to running

**Run tests:**
```bash
pytest tests/test_autonomy_*.py -v
```

## Compliance Checklist

- ✅ **L44 (House Rules):** Non-critical observability, must not block
- ✅ **L16 (Security):** Metrics are outcome-level only (no secrets)
- ✅ **ADR-0469:** Referenced in design
- ✅ **ADR-0314:** Learning integration prepared

---

**Status:** ✅ Production Ready  
**Last Updated:** 2026-09-01
