# CEL Session Memory

## Overview

The CEL Session Memory plugin provides L28 session memory capabilities, enabling storage and retrieval of conversation history, context snapshots, and interaction state during active Vibe sessions. It maintains a scoped view of session data—only the information relevant to the current session—enabling fast recall without loading entire user histories. The plugin handles memory lifecycle (creation, updates, cleanup) and integrates with the context adaptation engine for memory-aware response generation.

## Use Case

**Scenario:** Maintaining coherent session context

- A user is in a 45-minute Vibe session analyzing a complex technical problem; they ask follow-up questions that reference concepts from 20 minutes earlier—the session memory engine recalls the earlier context without requiring a full conversation history fetch
- A multi-step research workflow spans multiple turns; each turn builds on previous findings—session memory maintains the evolving research tree so later turns can reference intermediate hypotheses
- A user takes a break mid-session and returns 2 hours later; the session memory restores exactly where they left off—including conversation state, open artifacts, and pending decisions—without context loss

**Impact:** Sessions maintain coherent context across multiple turns; memory-aware recall improves response relevance; session state survives interruptions; conversation flow is natural without forced recaps.

## API Example

```python
from corvin_plugins.providers.cel_session_memory import SessionMemory, MemorySnapshot

# Initialize session memory
session_memory = SessionMemory(
    session_id="session-789",
    tenant_id="_default",
    user_id="user-123",
    max_memory_tokens=8000  # Limit memory size
)

# Capture session snapshot (called after each turn)
snapshot = MemorySnapshot(
    session_id="session-789",
    turn_number=1,
    timestamp="2026-09-02T14:00:00.123Z",
    user_message="Analyze this database performance issue",
    assistant_response="I'll help analyze the performance issue...",
    extracted_context={
        "topic": "database_performance",
        "entities": ["PostgreSQL", "query_optimization", "index"],
        "decisions": ["investigate slow query logs first"]
    }
)

session_memory.capture_snapshot(snapshot)

# Retrieve session context for next turn
turn_2_context = session_memory.get_context(
    include_messages=True,
    include_decisions=True,
    include_entities=True,
    max_tokens=4000  # Limit context to fit in prompt
)

print(f"Session context retrieved:")
print(f"  Recent messages: {len(turn_2_context.messages)}")
print(f"  Key entities: {turn_2_context.entities}")
print(f"  Open decisions: {turn_2_context.open_decisions}")

# User asks a follow-up question
user_message_2 = "Should we add an index on the created_at column?"
relevant_context = session_memory.retrieve_relevant_context(
    query=user_message_2,
    similarity_threshold=0.7
)

print(f"Relevant prior context found: {relevant_context}")

# Update memory with new turn
new_snapshot = MemorySnapshot(
    session_id="session-789",
    turn_number=2,
    timestamp="2026-09-02T14:05:30.123Z",
    user_message=user_message_2,
    assistant_response="Yes, based on the slow query logs...",
    extracted_context={
        "topic": "database_performance",
        "decisions": ["create index on created_at column"],
        "confidence": 0.92
    }
)

session_memory.capture_snapshot(new_snapshot)

# Cleanup: when session ends, summarize for long-term storage
session_summary = session_memory.create_summary()
print(f"Session summary: {session_summary}")
```

## Configuration

The CEL Session Memory requires the following configuration in `tenant.corvin.yaml`:

```yaml
plugins:
  cel_session_memory:
    enabled: true
    max_memory_tokens: 8000
    retention_strategy: "sliding_window"  # "sliding_window", "full_history"
    max_snapshots_per_session: 100
    snapshot_compression: true
    enable_similarity_search: true
    similarity_model: "sentence-transformers/all-mpnet-base-v2"
    cleanup_completed_sessions: true
    session_ttl_hours: 24
    memory_backend: "redis"  # "redis", "postgresql", "in_memory"
```

## Status

**Implementation:** Production Ready
**Tests:** 22 unit tests + 18 integration tests (40 total)
**Compliance:** ADR-0314 (Learning Infrastructure), ADR-0316 (Decision History), GDPR Art. 5, 6, 32

---
**Plugin ID:** plugin:buildin-memory-cel_session_memory
**Version:** 1.0.0 | **Boot Layer:** bundled
**Maintainer:** plugins@anthropic.com
**License:** Apache-2.0
