# User Model Learner Plugin

## Purpose

The **User Model Learner** plugin learns user preferences, communication styles, and decision patterns over time, enabling personalized routing and response generation (ADR-0318, L28).

## Status

**Stub Implementation** — Interface defined; full implementation in progress (Phase 3.4, ADR-0318).

## Planned Usage

```python
from user_model_learner import UserModelLearner

learner = UserModelLearner()
await learner.initialize(plugin_context)

# Record user preference
result = await learner.execute("record_preference", {
    "user_id": "user-123",
    "preference_type": "response_style",
    "value": "concise",
    "confidence": 0.85
})

# Retrieve user model
model = await learner.execute("get_user_model", {
    "user_id": "user-123"
})

# Update based on feedback
await learner.execute("record_outcome", {
    "user_id": "user-123",
    "feedback": "helpful",
    "decision_id": "d456"
})
```

## Integration Points

**Provides:**
- `initialize(context)` — Initialize user model engine
- `execute(operation, args)` — Record/retrieve/update user preferences
- `shutdown()` — Graceful cleanup

**Will integrate with:**
- **Style Preferences** (ADR-0318): Long-term user preference learning
- **Learning Infrastructure** (ADR-0314): Event-driven feedback integration
- **Confidence Intervals** (ADR-0315): Reliability scoring of learned preferences
- **Vibe Engineering** (ADR-0469): Session-level user context

## Compliance Notes

- **ADR-0318**: User model learning — in development
- **ADR-0314**: Learning infrastructure — event store integration
- **GDPR Art. 6**: Lawful basis for collecting preferences (consent or legitimate interest)
- **GDPR Art. 30**: User model updates logged to audit trail (planned)
- **GDPR Art. 17**: Erasure support for user models (planned)
- **Tenant isolation**: All user models scoped by tenant_id

## References

- **Plugin**: `plugin:buildin-memory-user_model_learner` (buildin tier)
- **Source**: `/home/shumway/projects/Corvin-Marketplace/plugins/buildin/memory/user_model_learner/src/user_model_learner.py`
- **Tests**: `tests/test_user_model_learner.py` (5 test cases)
- **ADR Status**: ADR-0318 (Style Preferences) — PROPOSED
