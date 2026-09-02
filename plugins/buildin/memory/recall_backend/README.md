# Recall Backend

## Overview

The Recall Backend plugin implements session recall and memory persistence for CorvinOS, providing users with the ability to restore prior session context and retrieve historical decisions (ADR-0314, ADR-0316). It manages recalled memories, context injection into new sessions, and integration with the learning infrastructure for outcome tracking. The plugin enables users to pick up work exactly where they left off and learn from prior session decisions.

## Use Case

**Scenario:** Recovering session context and decision history

- A user was analyzing market trends yesterday in a 2-hour session; they want to continue today—the recall backend restores the previous session's context (data, hypotheses, decisions) so they can pick up seamlessly without recaps
- After making a major decision in a Vibe session, the user wants to review why that decision was made 3 weeks later—the recall backend retrieves the decision record including reasoning, confidence, and feedback
- A team member wants to learn from a colleague's prior analysis of a similar problem—the recall backend shares the decision history (anonymized per privacy settings) so patterns can be discovered
- A decision turned out poorly; the user wants to trace back to see where reasoning went wrong—the recall backend provides full decision provenance for post-mortem analysis

**Impact:** Users can resume interrupted work without context loss; historical decisions are auditable and analyzable; learning from past mistakes is systematic; team knowledge sharing is enabled.

## API Example

```python
from corvin_plugins.providers.recall_backend import RecallBackend, SessionRecall, DecisionRecord

# Initialize recall backend
recall = RecallBackend(
    tenant_id="_default",
    storage_backend="learning_event_storage"  # ADR-0314
)

# Retrieve a prior session
prior_session = recall.get_session(
    session_id="session-2026-09-01-market-analysis",
    user_id="user-123"
)

if prior_session:
    print(f"Session found: {prior_session.title}")
    print(f"Duration: {prior_session.duration_minutes} minutes")
    print(f"Key decisions: {len(prior_session.decisions)}")
    
    # Restore session context to new session
    new_session = recall.create_session_from_recall(
        prior_session_id=prior_session.session_id,
        new_session_id="session-2026-09-02-market-analysis-continued",
        user_id="user-123",
        preserve_decisions=True,
        preserve_artifacts=True
    )
    
    print(f"New session created with restored context: {new_session.session_id}")

# Query decision history
decisions = recall.get_decisions(
    user_id="user-123",
    decision_type="investment_recommendation",
    time_range_days=30
)

for decision in decisions:
    print(f"Decision: {decision.title} (confidence: {decision.confidence:.0%})")
    print(f"  Timestamp: {decision.timestamp}")
    print(f"  Outcome: {decision.outcome}")  # "positive", "negative", "neutral", "unknown"

# Find prior similar decisions
similar_decisions = recall.find_similar_decisions(
    query="Should we invest in this startup?",
    similarity_threshold=0.7,
    limit=5
)

for similar in similar_decisions:
    print(f"Similar decision found: {similar.title}")
    print(f"  Similarity: {similar.similarity_score:.0%}")
    print(f"  Outcome: {similar.outcome}")

# Retrieve decision provenance (for post-mortem)
decision_record = recall.get_decision_detail(
    decision_id="decision-abc123"
)

print(f"Decision: {decision_record.title}")
print(f"Reasoning steps: {len(decision_record.reasoning_steps)}")
for i, step in enumerate(decision_record.reasoning_steps, 1):
    print(f"  {i}. {step.description} (confidence: {step.confidence:.0%})")

print(f"Context at decision time:")
for key, value in decision_record.context_snapshot.items():
    print(f"  {key}: {value}")

# Share decision history with team (privacy-filtered)
shared_history = recall.export_decision_history(
    user_id="user-123",
    time_range_days=90,
    anonymize_pii=True,
    include_reasoning=True,
    recipients=["team-lead@example.com"]
)

print(f"Exported {len(shared_history)} decisions for team review")
```

## Configuration

The Recall Backend requires the following configuration in `tenant.corvin.yaml`:

```yaml
plugins:
  recall_backend:
    enabled: true
    storage_backend: "learning_event_storage"
    retention_days: 365
    max_sessions_per_user: 1000
    max_decisions_per_session: 500
    enable_decision_history: true
    enable_session_restoration: true
    enable_similarity_search: true
    similarity_model: "sentence-transformers/all-mpnet-base-v2"
    privacy_filters:
      anonymize_pii: true
      redact_sensitive: true
      allow_public_sharing: true
    export_formats: ["json", "csv", "parquet"]
```

## Status

**Implementation:** Production Ready
**Tests:** 28 unit tests + 22 integration tests (50 total)
**Compliance:** ADR-0314 (Learning Infrastructure), ADR-0316 (Decision History), ADR-0317 (Outcome Feedback), GDPR Art. 5, 6, 17 (Erasure), 32

---
**Plugin ID:** plugin:buildin-memory-recall_backend
**Version:** 1.0.0 | **Boot Layer:** bundled
**Maintainer:** plugins@anthropic.com
**License:** Apache-2.0
