# Telemetry Client

**Category:** Observability  
**Type:** Deterministic Plugin  
**Tier:** High  
**Status:** Production Ready

## Overview

The Telemetry Client collects performance, error, and custom events from across the system, batches them into time-windowed or size-triggered flushes, and prepares them for external forwarding. It implements a circular buffer with type-based filtering, automatic batching logic, and configurable flush policies.

This plugin provides event collection and batching infrastructure for system-wide telemetry through a non-blocking observation pipeline.

### Key Capabilities

- **Multi-type event collection** — Ingest performance, error, and custom events
- **Circular buffering** — Bounded memory with automatic overflow handling
- **Type-based filtering** — Selectively collect or ignore event types
- **Auto-batching** — Size-based and time-based flush triggers

## Architecture

```
Events (performance, error, custom)
    ├→ Type Filter
    ├→ PII Check (content-free signatures only)
    └→ Circular Buffer (10k-100k events)
    ↓
Batch Manager
    ├→ Size-based trigger (when buffer ≥ N)
    ├→ Time-based trigger (every M seconds)
    └→ Manual flush() on demand
    ↓
Diagnostics API
    ├→ get_diagnostics() → batch status
    ├→ flush_ready() → ready for forward
    └→ health_check() → client status
```

### Diagram

See `diagram.svg` for detailed architecture showing event collection and batching flow.

## Usage

### Initialize

```python
from telemetry_client.src.telemetry_client import TelemetryClient

client = TelemetryClient(
    buffer_size=50000,
    batch_size=1000,
    flush_interval_sec=60
)
await client.initialize(context)
```

### Collect Events

```python
# Record performance event
await client.on_performance_event(event)

# Record error event
await client.on_error_event(event)

# Record custom event
await client.on_custom_event(event_name, event_data)

# Get collection diagnostics
diagnostics = await client.get_diagnostics()
print(diagnostics)
# Output: {
#   "buffer_size": 50000,
#   "buffered_events": 12345,
#   "events_by_type": {
#     "performance": 6000,
#     "error": 4500,
#     "custom": 1845
#   },
#   "pending_batches": 2,
#   "next_flush_in_sec": 23,
#   "total_flushed": 487500,
#   "latency_ms": 0.05,
#   "health": "ok"
# }
```

### Retrieve Batches

```python
# Check if batch is ready to flush
if await client.flush_ready():
    batch = await client.get_pending_batch()
    # Forward batch to external telemetry system
    await forward_to_telemetry_backend(batch)
    await client.mark_flushed(batch.id)

# Manual flush on demand
batch = await client.flush_now()
print(f"Flushed {batch.event_count} events")

health = await client.on_health_check()
print(health.ok)  # True if client operational
```

## Performance

| Metric | Target | Actual |
|--------|--------|--------|
| Event Ingestion Latency | <1ms | ~0.05ms |
| Buffer Size | 10k-100k | Configurable |
| Batch Size | 100-5k | Configurable |
| Flush Interval | 10-300s | Configurable |
| Memory | <50MB | ~20-40MB |

## Testing

```bash
# Unit tests
pytest tests/test_telemetry_client.py -v

# With coverage
pytest tests/test_telemetry_client.py --cov=src/telemetry_client

# Test event filtering
pytest tests/test_telemetry_client.py::test_type_filtering -v

# Test batching logic
pytest tests/test_telemetry_client.py::test_batch_creation -v

# Test circular buffer overflow
pytest tests/test_telemetry_client.py::test_buffer_overflow -v
```

## Error Handling

The plugin handles errors gracefully:

- **Buffer full** — Circular buffer evicts oldest events automatically
- **Batch creation failure** — Events retained, retry on next flush
- **Type filter error** — Events default to collection, logged for review
- **PII detection** — Events containing PII-shaped content are dropped, logged

## Compliance

- ✅ GDPR Art. 30 (event collection records what telemetry was sent)
- ✅ GDPR Art. 32 (audit trail of batches and forwarding decisions)
- ✅ Fail-closed on PII — events with PII signatures are dropped, never forwarded
- ✅ Content-free only — only scrubbed code-level signatures transmitted (exception types, file names, function names — never prompts, transcripts, or user data)

## Related Plugins

- Brain Diagnostics (performance event source)
- Error Healing (error event source)
- Brain Layer Monitor (layer latency event source)
- Diagnostics Dashboard (batch status aggregation)

## ADR Reference

See [ADR-0543](../../../../../../../Corvin-ADR/decisions/ADR-0543-observability-telemetry-client.md) for architectural decisions.

---

**Version:** 1.0.0  
**License:** Apache-2.0  
**Maintainer:** Anthropic PBC
