# CEL Session Memory Plugin

## Purpose

The **CEL Session Memory** plugin provides a pluggable interface for CEL (Claud Expression Language) session memory management, recording conversation context and decision history for multi-turn reasoning (ADR-0316, L28).

## Status

**Stub Implementation** — Interface defined; full implementation in progress (Phase 3.2, ADR-0316).

## Planned Usage

```python
from cel_session_memory import CELSessionMemory

memory = CELSessionMemory()
await memory.initialize(plugin_context)

# Store session context
result = await memory.execute("store_session", {
    "session_id": "s123",
    "context": {"conversation": [...], "decisions": [...]},
    "timestamp": 1234567890
})

# Retrieve context
context = await memory.execute("get_session", {"session_id": "s123"})
```

## Integration Points

**Provides:**
- `initialize(context)` — Hook into CEL session engine
- `execute(operation, args)` — Perform memory operations (store/retrieve/forget)
- `shutdown()` — Graceful cleanup

**Will integrate with:**
- **Decision History** (ADR-0316): Record user and system decisions
- **Vibe Engineering** (ADR-0469): Multi-turn session state management
- **L28 Conversation Recall**: Persistent session context storage
- **Learning Infrastructure** (ADR-0314): Feedback loop integration

## Compliance Notes

- **ADR-0316**: Decision history layer — in development
- **L28**: Conversation recall layer integration pending
- **GDPR Art. 30**: Session records logged to audit trail (planned)
- **GDPR Art. 17**: Erasure support for session context (planned)

## References

- **Plugin**: `plugin:buildin-memory-cel_session_memory` (buildin tier)
- **Source**: `/home/shumway/projects/Corvin-Marketplace/plugins/buildin/memory/cel_session_memory/src/cel_session_memory.py`
- **Tests**: `tests/test_cel_session_memory.py` (5 test cases covering stub behavior)
- **ADR Status**: ADR-0316 (Decision History) — PROPOSED
