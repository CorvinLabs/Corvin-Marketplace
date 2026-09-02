# Vibe Session History

## Overview

The Vibe Session History plugin maintains persistent, queryable records of all Vibe session lifecycle events, decisions, context snapshots, and outcomes. It enables users to review past sessions, learn from prior decisions, and discover patterns across multiple sessions. The plugin stores session metadata, decision traces with full provenance, and artifact references for complete session reconstruction and audit trail compliance.

## Use Case

**Scenario:** Reviewing and learning from past Vibe sessions

- A user completed a complex analysis session 2 weeks ago and needs to review the exact reasoning path that led to a decision—the history plugin provides the full trace including intermediate hypotheses and alternatives considered
- A team wants to understand why different team members made conflicting decisions on similar problems—the history plugin enables cross-session comparison to identify decision-making patterns and disagreements
- An auditor needs to verify that a critical business decision was made with appropriate diligence—the history plugin provides complete provenance (who, what, when, why, with what confidence) meeting compliance requirements
- A user notices a recent decision went poorly and wants to compare it with a similar prior decision to see what changed—the history plugin enables historical pattern matching and comparative analysis

**Impact:** Users can audit their own decision-making over time; team patterns become visible and discussable; compliance evidence is automatically captured; learning from mistakes is systematic.

## API Example

```python
from corvin_plugins.providers.vibe_session_history import SessionHistory, SessionQuery, DecisionTrace

# Initialize history plugin
history = SessionHistory(
    tenant_id="_default",
    storage_backend="learning_event_storage"
)

# Retrieve all sessions for a user
sessions = history.list_sessions(
    user_id="user-123",
    time_range_days=30,
    order_by="created_at",
    descending=True
)

print(f"User has {len(sessions)} sessions in past 30 days")
for session in sessions:
    print(f"  {session.created_at}: {session.title} ({session.duration_minutes}m)")

# Get detailed session view
session_detail = history.get_session(
    session_id="session-2026-09-01-market-analysis",
    include_decisions=True,
    include_context_snapshots=True,
    include_artifacts=True
)

print(f"Session: {session_detail.title}")
print(f"Decisions made: {len(session_detail.decisions)}")
print(f"Artifacts created: {len(session_detail.artifacts)}")

# Review decision trace (full provenance)
for decision in session_detail.decisions:
    print(f"\nDecision: {decision.title}")
    print(f"  Timestamp: {decision.timestamp}")
    print(f"  Confidence: {decision.confidence:.0%}")
    print(f"  Reasoning:")
    for step in decision.reasoning_steps:
        print(f"    - {step.description}")

# Search sessions by decision topic
matching_sessions = history.search_sessions(
    user_id="user-123",
    topic="investment_decision",
    min_confidence=0.70
)

print(f"Found {len(matching_sessions)} investment decision sessions")

# Compare two decisions across sessions
decision_1 = history.get_decision(decision_id="decision-abc123")
decision_2 = history.get_decision(decision_id="decision-xyz789")

comparison = history.compare_decisions(
    decision_1=decision_1,
    decision_2=decision_2
)

print(f"Decision comparison:")
print(f"  Topic similarity: {comparison.topic_similarity:.0%}")
print(f"  Context difference: {comparison.context_difference}")
print(f"  Outcome change: {comparison.outcome_delta}")  # Was outcome different?

# Extract session summary for reporting
summary = history.create_session_summary(
    session_id="session-2026-09-01-market-analysis",
    include_key_decisions=True,
    include_confidence_levels=True
)

print(f"Session summary: {summary.text}")
print(f"Key decisions: {summary.key_decisions}")
print(f"Overall confidence: {summary.average_confidence:.0%}")

# Export session for audit/compliance
export = history.export_session(
    session_id="session-2026-09-01-market-analysis",
    format="json",  # "json", "pdf", "csv"
    include_full_provenance=True,
    include_reasoning_details=True
)

print(f"Session exported to {export.path}")
print(f"File size: {export.size_bytes} bytes")

# Get cross-session patterns
patterns = history.discover_patterns(
    user_id="user-123",
    decision_type="investment",
    time_range_days=90,
    min_similarity=0.75
)

print(f"Discovered {len(patterns)} patterns across sessions:")
for pattern in patterns:
    print(f"  Pattern: {pattern.description}")
    print(f"  Occurrences: {pattern.frequency}")
    print(f"  Success rate: {pattern.success_rate:.0%}")
```

## Configuration

The Vibe Session History requires the following configuration in `tenant.corvin.yaml`:

```yaml
plugins:
  vibe_session_history:
    enabled: true
    storage_backend: "learning_event_storage"
    capture_strategies:
      - "session_metadata"
      - "decision_trace"
      - "context_snapshot"
      - "artifact_reference"
    retention_days: 730  # 2 years
    max_sessions_per_user: 5000
    enable_search: true
    enable_similarity_matching: true
    enable_pattern_discovery: true
    compression_strategy: "gzip"
    export_formats:
      - "json"
      - "pdf"
      - "csv"
    privacy_settings:
      allow_session_sharing: true
      anonymize_on_export: false
      allow_team_discovery: true
```

## Status

**Implementation:** Production Ready
**Tests:** 30 unit tests + 24 integration tests (54 total)
**Compliance:** ADR-0314 (Learning Infrastructure), ADR-0316 (Decision History), ADR-0317 (Outcome Feedback), ADR-0511 (Marketplace), GDPR Art. 5, 6, 17 (Erasure), 32

---
**Plugin ID:** plugin:buildin-memory-vibe_session_history
**Version:** 1.0.0 | **Boot Layer:** bundled
**Maintainer:** plugins@anthropic.com
**License:** Apache-2.0
