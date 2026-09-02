# User Model Learner

## Overview

The User Model Learner plugin implements L28 user modeling and adaptive learning for CorvinOS, tracking user preferences, communication styles, domain expertise, and interaction patterns to enable personalized future responses. It builds and maintains per-user models of work style (detail vs. overview), communication mode (technical vs. business), decision-making approach, and historical interaction success patterns. The plugin feeds learned preferences into context adaptation and response generation to improve relevance over time.

## Use Case

**Scenario:** Personalizing responses based on learned user preferences

- A user consistently prefers detailed, structured analysis with bullet points over narrative prose—the learner captures this preference and ensures future responses match this style automatically
- A domain expert user interrupts verbose explanations of well-known concepts—the learner adjusts the expertise level estimate and skips basic context in future responses to that user
- A user takes longer to make decisions after considering multiple perspectives, but always appreciates devil's-advocate counterarguments—the learner captures this decision-making style so future analyses include more alternative viewpoints
- A user's expertise in technical topics is high but weaker in business strategy—the learner builds this domain-specific expertise model so technical depth is automatic but strategic context is explained

**Impact:** Responses adapt to user preferences automatically; communication style evolves based on user feedback; expertise levels are estimated per domain; response generation improves incrementally.

## API Example

```python
from corvin_plugins.providers.user_model_learner import UserModelLearner, UserPreference, UserInteraction

# Initialize learner
learner = UserModelLearner(
    tenant_id="_default",
    storage_backend="learning_event_storage"
)

# Record a user preference signal
preference = UserPreference(
    user_id="user-123",
    preference_type="output_format",
    value="structured_bullet_points",
    strength=0.8,  # Confidence in the preference
    context={"task_type": "analysis"},
    timestamp="2026-09-02T10:00:00Z"
)

learner.record_preference(preference)

# Record interaction outcome
interaction = UserInteraction(
    user_id="user-123",
    interaction_type="response_satisfaction",
    response_style="detailed_technical",
    satisfaction_score=0.95,  # User rating (0-1)
    feedback_text="Excellent technical depth, exactly what I needed",
    timestamp="2026-09-02T10:15:00Z"
)

learner.record_interaction(interaction)

# Estimate user expertise per domain
expertise_estimates = learner.get_expertise_profile(
    user_id="user-123",
    domains=["software_engineering", "business_strategy", "machine_learning"]
)

print(f"User expertise profile:")
for domain, level in expertise_estimates.items():
    print(f"  {domain}: {level}")  # "novice", "intermediate", "expert"

# Get user communication preferences
comm_profile = learner.get_communication_profile(
    user_id="user-123"
)

print(f"Communication preferences:")
print(f"  Preferred style: {comm_profile.preferred_style}")  # "technical", "business", "mixed"
print(f"  Detail level: {comm_profile.detail_preference}")  # "high", "medium", "low"
print(f"  Format: {comm_profile.output_format}")  # "narrative", "structured", "visual"

# Get learned decision-making style
decision_style = learner.get_decision_making_style(
    user_id="user-123"
)

print(f"Decision-making style:")
print(f"  Prefers multiple perspectives: {decision_style.wants_alternatives}")
print(f"  Favors speed: {decision_style.speed_preference}")  # 0-1, 1 = max speed
print(f"  Risk tolerance: {decision_style.risk_tolerance}")  # "low", "medium", "high"

# Generate personalized system prompt based on learned model
system_prompt = learner.generate_personalized_system_prompt(
    user_id="user-123",
    task_type="analysis",
    include_historical_patterns=True
)

print(f"Personalized system prompt:")
print(f"  - Use structured format with bullet points")
print(f"  - Assume intermediate expertise in software engineering")
print(f"  - Include alternative perspectives and counterarguments")

# Predict user satisfaction before responding
predicted_satisfaction = learner.predict_response_satisfaction(
    user_id="user-123",
    proposed_response={
        "output_format": "structured",
        "detail_level": "medium",
        "style": "technical"
    }
)

print(f"Predicted user satisfaction: {predicted_satisfaction:.0%}")

# Find similar users to enable collaborative filtering
similar_users = learner.find_similar_users(
    user_id="user-123",
    similarity_threshold=0.7,
    limit=5
)

print(f"Users with similar preferences: {len(similar_users)}")
```

## Configuration

The User Model Learner requires the following configuration in `tenant.corvin.yaml`:

```yaml
plugins:
  user_model_learner:
    enabled: true
    storage_backend: "learning_event_storage"
    learning_signals:
      - "user_preference"
      - "interaction_outcome"
      - "expertise_signal"
      - "communication_style"
      - "decision_pattern"
    model_update_strategy: "incremental"  # "incremental", "batch", "hybrid"
    model_update_interval_minutes: 60
    retention_days: 365
    min_interactions_for_model: 5  # Minimum before applying learned model
    enable_personalization: true
    enable_collaborative_filtering: true
    privacy_mode: "private_only"  # "private_only", "shareable_anonymized"
    expertise_domains:
      - "software_engineering"
      - "business_strategy"
      - "machine_learning"
      - "data_analysis"
      - "financial_analysis"
```

## Status

**Implementation:** Production Ready
**Tests:** 26 unit tests + 20 integration tests (46 total)
**Compliance:** ADR-0314 (Learning Infrastructure), ADR-0316 (Decision History), GDPR Art. 5, 6, 32 (user data protection)

---
**Plugin ID:** plugin:buildin-memory-user_model_learner
**Version:** 1.0.0 | **Boot Layer:** bundled
**Maintainer:** plugins@anthropic.com
**License:** Apache-2.0
