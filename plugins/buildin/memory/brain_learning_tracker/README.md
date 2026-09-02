# Brain Learning Tracker

## Overview

The Brain Learning Tracker plugin monitors and records the evolution of the Brain subsystem's learning state, user preferences, and cognitive patterns over time. It tracks persona-specific confidence scores, user interaction history, and decision outcomes to enable continuous improvement of the Brain's internal models. The plugin integrates with ADR-0314's learning infrastructure to store, query, and analyze learning signals that feed the system's self-optimization mechanisms.

## Use Case

**Scenario:** Tracking Brain subsystem cognitive evolution

- The Brain's persona router learns which personas work best for different task types—the tracker records classification accuracy over time so underperforming routing patterns can be detected and adjusted
- A user consistently prefers certain analysis styles (e.g., "structured bullet points" vs. "narrative prose")—the tracker records preference signals so future Brain responses adapt to user taste without explicit retraining
- A specific reasoning pattern (e.g., five-step hypothesis-driven analysis) yields better user satisfaction for research tasks—the tracker records this outcome so the Brain learns to apply similar reasoning to future research requests

**Impact:** Brain subsystem improves based on real user feedback; preference patterns are captured and applied automatically; learning is measurable (confidence scores improve over time); failed strategies are detected and replaced.

## API Example

```python
from corvin_plugins.providers.brain_learning_tracker import BrainLearningTracker, LearningSignal

# Initialize tracker
tracker = BrainLearningTracker(
    tenant_id="_default",
    storage_backend="learning_event_storage"  # References ADR-0314
)

# Record a persona classification outcome
classification_signal = LearningSignal(
    signal_type="persona_classification",
    persona_id="analyst",
    task_id="task-001",
    user_id="user-123",
    input_features={
        "task_category": "data_analysis",
        "task_complexity": "high",
        "domain": "financial_reporting"
    },
    predicted_persona="analyst",
    actual_persona="analyst",  # Ground truth from user feedback
    confidence: 0.87,
    timestamp="2026-09-02T10:15:30.123Z"
)

tracker.record_signal(classification_signal)

# Record a user preference signal
preference_signal = LearningSignal(
    signal_type="user_preference",
    user_id="user-123",
    preference_type="output_format",
    value="structured",  # vs "narrative"
    strength=0.75,  # Confidence in the preference (0-1)
    context={
        "task_type": "analysis",
        "document_type": "report",
        "session_id": "session-456"
    }
)

tracker.record_signal(preference_signal)

# Record an outcome feedback signal
outcome_signal = LearningSignal(
    signal_type="outcome_feedback",
    task_id="task-002",
    user_id="user-123",
    reasoning_pattern="hypothesis_driven",  # The approach used
    output_quality=0.89,  # User-rated quality (0-1)
    feedback_text="Excellent structured analysis, exactly what I needed",
    timestamp="2026-09-02T11:45:00.123Z"
)

tracker.record_signal(outcome_signal)

# Query learning progress
progress = tracker.get_learning_progress(
    metric="persona_classification_accuracy",
    time_window_days=30,
    granularity="daily"
)

print(f"Persona routing accuracy (30d): {progress.metric_value:.2%}")
print(f"Confidence interval: {progress.confidence_interval}")

# Get persona-specific insights
persona_insights = tracker.get_persona_insights(
    persona_id="analyst",
    metrics=["success_rate", "average_confidence", "improvement_trend"]
)

print(f"Analyst success rate: {persona_insights['success_rate']:.2%}")
print(f"Recent trend: {persona_insights['improvement_trend']}")  # "improving", "stable", "declining"

# Identify learning gaps
gaps = tracker.identify_learning_gaps(
    confidence_threshold=0.70,
    min_samples=10
)

for gap in gaps:
    print(f"Low confidence on {gap.task_type}: {gap.confidence:.2%}")
```

## Configuration

The Brain Learning Tracker requires the following configuration in `tenant.corvin.yaml`:

```yaml
plugins:
  brain_learning_tracker:
    enabled: true
    storage_backend: "learning_event_storage"
    learning_signals:
      - "persona_classification"
      - "user_preference"
      - "outcome_feedback"
      - "reasoning_pattern"
      - "confidence_score"
    retention_days: 365
    enable_real_time_updates: true
    batch_size: 100
    flush_interval_seconds: 30
    confidence_thresholds:
      high: 0.85
      medium: 0.65
      low: 0.40
```

## Status

**Implementation:** Production Ready
**Tests:** 24 unit tests + 14 integration tests (38 total)
**Compliance:** ADR-0314 (Learning Infrastructure), ADR-0316 (Decision History), ADR-0317 (Outcome Feedback), GDPR Art. 5, 6, 32

---
**Plugin ID:** plugin:buildin-memory-brain_learning_tracker
**Version:** 1.0.0 | **Boot Layer:** bundled
**Maintainer:** plugins@anthropic.com
**License:** Apache-2.0
