# Learning Event Storage

## Overview

The Learning Event Storage plugin implements L28 persistent storage for learning events generated throughout CorvinOS's operation (ADR-0314). It manages immutable event records, date-partitioned data organization for performance, query APIs for extracting learning signals, and integration with the audit chain for integrity verification. The plugin provides both real-time event ingestion and historical query capabilities for analysis and model retraining.

## Use Case

**Scenario:** Building and maintaining learning infrastructure

- A Skill executes and emits a learning event with confidence score 0.92; the storage plugin persists it, and a downstream optimizer reads it to update routing thresholds
- Over 10,000 similar tasks, patterns emerge (e.g., "complexity >= 3" predicts success for Opus)—the storage plugin enables retrospective analysis to discover these patterns and improve routing
- An audit trail query needs to verify that a Skill's learning happened correctly; the storage plugin returns the complete event log with hash-chain verification for compliance proof
- A custom reporting pipeline needs to extract all feedback events from the past month for a specific persona—the storage plugin queries the date-partitioned event store efficiently

**Impact:** Learning infrastructure has a durable, queryable backend; historical analysis enables model improvements; audit trails prove learning correctness; custom analytics can build on the event store.

## API Example

```python
from corvin_plugins.providers.learning_event_storage import LearningEventStorage, LearningEvent, EventQuery

# Initialize storage
storage = LearningEventStorage(
    tenant_id="_default",
    backend="postgresql",  # "postgresql", "duckdb", "s3"
    data_dir="/var/lib/corvin/learning_events"
)

# Store a learning event (typically called by other plugins)
event = LearningEvent(
    event_type="confidence_score",
    entity_id="os.delegation_router",
    entity_type="skill",
    input_hash="abc123def456",
    output_hash="xyz789uvw012",
    confidence_score=0.92,
    timestamp="2026-09-02T14:15:00.123Z",
    tenant_id="_default",
    lom="assistant.Forge::route_request:L237"  # Line of Moral Responsibility
)

storage.write_event(event)
print(f"Event stored with ID: {event.event_id}")

# Query recent events for a specific skill
query = EventQuery(
    event_type="confidence_score",
    entity_id="os.delegation_router",
    time_range_days=7,
    min_confidence=0.70
)

results = storage.query(query)
print(f"Found {len(results)} high-confidence events in past 7 days")

# Aggregate statistics
stats = storage.aggregate(
    event_type="confidence_score",
    entity_id="os.delegation_router",
    group_by="day",
    metrics=["avg_confidence", "count", "min_confidence", "max_confidence"]
)

for day, day_stats in stats.items():
    print(f"{day}: avg confidence {day_stats['avg_confidence']:.2%}, {day_stats['count']} events")

# Extract feedback events for model retraining
feedback_events = storage.query(
    event_type="feedback",
    time_range_days=30,
    limit=5000
)

print(f"Extracted {len(feedback_events)} feedback events for retraining")

# Verify event hash-chain integrity (compliance)
verification = storage.verify_chain(
    start_timestamp="2026-09-01T00:00:00Z",
    end_timestamp="2026-09-02T23:59:59Z"
)

print(f"Chain verification: {verification.status}")
print(f"Events verified: {verification.event_count}")
print(f"Gaps found: {len(verification.gaps)}")

# Export events for external analysis
export_path = storage.export_events(
    query=EventQuery(event_type="outcome", time_range_days=7),
    format="parquet",  # "parquet", "csv", "json"
    output_path="/tmp/learning_events_export.parquet"
)

print(f"Events exported to {export_path}")
```

## Configuration

The Learning Event Storage requires the following configuration in `tenant.corvin.yaml`:

```yaml
plugins:
  learning_event_storage:
    enabled: true
    backend: "postgresql"  # "postgresql", "duckdb", "s3"
    database:
      host: "localhost"
      port: 5432
      dbname: "corvin_learning"
      user: "corvin"
      password: "${CORVIN_DB_PASSWORD}"
    data_dir: "/var/lib/corvin/learning_events"
    partition_strategy: "daily"  # "daily", "hourly", "monthly"
    retention_days: 365
    enable_compression: true
    enable_query_optimization: true
    batch_write_size: 100
    flush_interval_seconds: 30
    enable_chain_verification: true
```

## Status

**Implementation:** Production Ready
**Tests:** 26 unit tests + 20 integration tests (46 total)
**Compliance:** ADR-0314 (Learning Infrastructure), ADR-0232 (Boot Tripwire), ADR-0233 (Plugin System), GDPR Art. 5, 6, 30, 32

---
**Plugin ID:** plugin:buildin-memory-learning_event_storage
**Version:** 1.0.0 | **Boot Layer:** bundled
**Maintainer:** plugins@anthropic.com
**License:** Apache-2.0
