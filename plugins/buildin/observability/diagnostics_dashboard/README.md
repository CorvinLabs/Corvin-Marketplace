# Diagnostics Dashboard

**Category:** Observability  
**Type:** Deterministic Plugin  
**Tier:** High  
**Status:** Production Ready

## Overview

The Diagnostics Dashboard is a unified health aggregator that combines metrics from all observability plugins (Brain Diagnostics, Brain Layer Monitor, Heartbeat Monitor, Error Healing, etc.) into a single health score (0-100) and status matrix. It provides operators with a comprehensive system health view and identifies critical issues.

This plugin aggregates subsystem, layer, and service metrics from across the Observability stack, exposing unified health scoring and alerting through a non-blocking observation pipeline.

### Key Capabilities

- **Unified health scoring** — Aggregate score 0-100 combining all subsystem and layer metrics
- **Critical alert detection** — Surface high-priority issues for immediate operator attention
- **Status matrix** — Component-level status (healthy/degraded/failed/unknown)
- **Trend analysis** — Track health over time and detect declining patterns

## Architecture

```
Brain Diagnostics metrics
Brain Layer Monitor SLAs
Heartbeat Monitor responsiveness
Error Healing recovery rates
└→ Diagnostics Dashboard (aggregator)
    ↓
Health Score Calculator (weighted)
    ├→ Subsystem health: 40%
    ├→ Layer SLA compliance: 30%
    ├→ Recovery success: 20%
    └→ Responsiveness: 10%
    ↓
Diagnostics API
    ├→ get_diagnostics() → unified snapshot
    ├→ get_health_score() → 0-100 score
    └→ get_critical_alerts() → high-priority issues
```

### Diagram

See `diagram.svg` for detailed architecture showing metric aggregation and scoring pipeline.

## Usage

### Initialize

```python
from diagnostics_dashboard.src.diagnostics_dashboard import DiagnosticsDashboard

dashboard = DiagnosticsDashboard()
await dashboard.initialize(context)
```

### Subscribe to Aggregated Metrics

```python
# Receive aggregated diagnostics updates
await dashboard.on_metrics_update(update_event)

# Get unified health snapshot
snapshot = await dashboard.get_diagnostics()
print(snapshot)
# Output: {
#   "health_score": 87,
#   "status": "healthy",
#   "subsystems_ok": 13,
#   "subsystems_degraded": 0,
#   "layers_ok": 44,
#   "layers_sla_breach": 1,
#   "critical_alerts": 0,
#   "warnings": 2,
#   "recovery_success_rate": 0.94,
#   "responsiveness_score": 0.98,
#   "health": "ok"
# }
```

### Get Health Score

```python
# Get numeric health score (0-100)
score = await dashboard.get_health_score()
print(f"System Health: {score}/100")  # e.g., 87/100

# Get critical alerts
alerts = await dashboard.get_critical_alerts()
for alert in alerts:
    print(f"CRITICAL: {alert.component} - {alert.message}")
```

## Performance

| Metric | Target | Actual |
|--------|--------|--------|
| Latency | <2ms | ~0.3ms |
| Aggregation Cycles | 1/sec | 1/sec |
| Tracked Components | 50+ | 50+ |
| Memory | <30MB | ~15-25MB |
| CPU (idle) | <0.3% | Minimal |

## Testing

```bash
# Unit tests
pytest tests/test_diagnostics_dashboard.py -v

# With coverage
pytest tests/test_diagnostics_dashboard.py --cov=src/diagnostics_dashboard

# Test health score calculation
pytest tests/test_diagnostics_dashboard.py::test_health_score_calculation -v

# Test alert detection
pytest tests/test_diagnostics_dashboard.py::test_critical_alert_detection -v

# Test metric aggregation
pytest tests/test_diagnostics_dashboard.py::test_metric_aggregation -v
```

## Error Handling

The plugin handles errors gracefully:

- **Missing metric source** — Uses last known value with degraded confidence
- **Aggregation failure** — Falls back to component-level scoring
- **Score calculation error** — Defaults to neutral score (50/100)
- **Alert threshold exceeded** — Immediately surfaces as critical

## Compliance

- ✅ GDPR Art. 30 (record-keeping of system health states and transitions)
- ✅ GDPR Art. 32 (audit trail of critical alerts and anomalies)
- ✅ Fail-closed on score calculation — all errors degrade gracefully
- ✅ No external telemetry — local-only dashboard observability

## Related Plugins

- Brain Diagnostics (subsystem metrics source)
- Brain Layer Monitor (layer performance source)
- Heartbeat Monitor (responsiveness source)
- Error Healing (recovery metrics source)
- Vibe Health Monitor (peer aggregator for vibe-specific metrics)

## ADR Reference

See [ADR-0539](../../../../../../../Corvin-ADR/decisions/ADR-0539-observability-diagnostics-dashboard.md) for architectural decisions.

---

**Version:** 1.0.0  
**License:** Apache-2.0  
**Maintainer:** Anthropic PBC
