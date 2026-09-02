# Notification Backend

## Overview

The Notification Backend plugin provides event-driven pub/sub messaging for CorvinOS subsystems, enabling loose coupling between components that need to coordinate asynchronously. It handles message queuing, topic subscription, delivery guarantees (at-least-once), and event filtering based on topic patterns. The plugin abstracts the underlying message transport (in-memory, Redis, RabbitMQ, Kafka) and provides a uniform API for publishers and subscribers.

## Use Case

**Scenario:** Coordinating asynchronous multi-step workflows

- A learning event is emitted when a Skill executes (ADR-0314); multiple subscribers (telemetry client, metrics aggregator, decision history tracker) need to react independently without the Skill needing to know about each
- A long-running data processing job completes; multiple systems (artifact indexer, analytics dashboard, notification dispatcher, audit logger) need to be notified immediately and in parallel
- A user preference changes; subscriber modules (context adapter, recommendation engine, telemetry consent checker) need to be updated without explicit function calls from the preference manager

**Impact:** Subsystems communicate through well-defined events rather than tight coupling; new subscribers can be added without modifying publishers; event processing is parallelizable and resilient to individual subscriber failures.

## API Example

```python
from corvin_plugins.providers.notification_backend import NotificationBackend, EventMessage

# Initialize the backend
backend = NotificationBackend(
    transport="redis",  # or "in_memory", "rabbitmq", "kafka"
    transport_config={
        "redis_url": "redis://localhost:6379",
        "max_retries": 3,
        "delivery_timeout_seconds": 30
    }
)

# Publisher: emit a learning event
async def publish_skill_executed():
    event = EventMessage(
        topic="skills/executed",
        event_type="skill_executed",
        payload={
            "skill_id": "os.delegation_router",
            "version": "1.2.3",
            "execution_time_ms": 42,
            "success": True,
            "tenant_id": "_default"
        },
        priority="normal"
    )
    await backend.publish(event)
    print("Event published to skills/executed")

# Subscriber 1: update telemetry
async def on_skill_executed(event):
    print(f"Telemetry: {event.payload['skill_id']} took {event.payload['execution_time_ms']}ms")
    # Send to metrics collector

# Subscriber 2: record outcome for learning
async def on_skill_executed_learning(event):
    print(f"Learning: Recording feedback for {event.payload['skill_id']}")
    # Update learning event store (ADR-0314)

# Subscriber 3: audit trail
async def on_skill_executed_audit(event):
    print(f"Audit: Skill execution logged for {event.payload['skill_id']}")
    # Append to audit chain

# Register subscribers with pattern matching
await backend.subscribe(
    topic_pattern="skills/executed",
    handler=on_skill_executed,
    subscriber_id="telemetry_client"
)
await backend.subscribe(
    topic_pattern="skills/executed",
    handler=on_skill_executed_learning,
    subscriber_id="learning_event_storage"
)
await backend.subscribe(
    topic_pattern="skills/*",  # Wildcard pattern
    handler=on_skill_executed_audit,
    subscriber_id="audit_backend"
)

# Start event processing
await backend.run()
```

## Configuration

The Notification Backend requires the following configuration in `tenant.corvin.yaml`:

```yaml
plugins:
  notification_backend:
    enabled: true
    transport: "redis"  # "in_memory", "redis", "rabbitmq", "kafka"
    transport_config:
      redis_url: "redis://localhost:6379"
      db: 0
      max_retries: 3
      delivery_timeout_seconds: 30
    queue_size: 10000
    worker_threads: 8
    enable_delivery_guarantees: true
    dead_letter_queue_enabled: true
    dead_letter_queue_ttl_days: 7
```

## Status

**Implementation:** Production Ready
**Tests:** 26 unit tests + 20 integration tests (46 total)
**Compliance:** ADR-0510 (Hub Wiring), ADR-0511 (Marketplace), ADR-0232 (Boot Tripwire)

---
**Plugin ID:** plugin:buildin-integration-notification_backend
**Version:** 1.0.0 | **Boot Layer:** bundled
**Maintainer:** plugins@anthropic.com
**License:** Apache-2.0
