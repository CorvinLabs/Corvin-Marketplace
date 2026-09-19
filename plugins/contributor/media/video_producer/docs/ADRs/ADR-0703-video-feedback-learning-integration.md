---
id: ADR-0703
status: proposed
supersedes: []
depends_on: [ADR-0702, ADR-0703, ADR-0701, ADR-0314]
related: [CONCEPT-0041, ADR-0702]
commits: []
paths:
  - "core/skills/video_producer_skill/feedback_handler.py"
  - "core/console/corvin_console/web-next/src/components/VideoQualityFeedback.tsx"
  - "core/skills/video_producer_skill/tests/test_feedback_learning.py"
docs:
  - "docs/video-producer/feedback-learning.md"
---

# ADR-0703 — Per-Scene Feedback & Learning Integration

**Status:** Proposed  
**Date:** 2026-09-13  

## Summary

Closes the learning loop: users review completed videos, approve/reject individual scenes, and the system learns to improve encoding/grading parameters.

**Workflow:**
```
Video Produced
  ↓
[Console Panel] User Reviews Scenes
  ↓
[Per-Scene] User: [✓ Approve] [✗ Reject: Reason] [Edit]
  ↓
[Learning] Feedback Event emitted → Optimizer tunes config
  ↓
[Next Job] Uses tuned parameters
```

## Decision

### Feedback Collection UI

**Console Component:** `VideoQualityFeedback.tsx`

```tsx
<div className="scene-review-grid">
  {job.scenes.map(scene => (
    <div key={scene.id} className="scene-card">
      <img src={scene.thumbnail} className="scene-preview" />
      <div className="feedback-buttons">
        <Button onClick={() => approvScene(scene.id)}>✓ Approve</Button>
        <Button onClick={() => openRejectDialog(scene.id)}>✗ Reject</Button>
        <Button onClick={() => editScene(scene.id)}>Edit</Button>
      </div>
      <div className="metrics">
        <span>Quality: {scene.predicted_quality.toFixed(2)}</span>
        <span>Bitrate: {scene.encoding.bitrate}</span>
      </div>
    </div>
  ))}
</div>

<RejectDialog>
  <select>
    <option>Too Blurry</option>
    <option>Too Compressed</option>
    <option>Color Wrong</option>
    <option>Hallucination</option>
    <option>Other</option>
  </select>
  <textarea placeholder="Additional comments..." />
  <Button onClick={submitFeedback}>Submit</Button>
</RejectDialog>
```

### Feedback Event Schema

```python
@dataclass(frozen=True)
class SceneQualityFeedback:
    """User feedback on a single scene's quality."""
    scene_id: str
    job_id: str
    feedback_type: Literal[
        "approved",
        "too_blurry",
        "too_compressed",
        "color_wrong",
        "hallucination",
        "edited",
        "rejected_other"
    ]
    confidence: float  # 0–1, user's confidence in feedback
    # Note: reason/comments NOT persisted (GDPR — user text never in audit chain)
    timestamp: datetime
    tenant_id: str
    
    # Derived metrics (computed, not from user input)
    predicted_quality_before: float  # model's prediction before feedback
    actual_quality_after: float  # computed from feedback signal
```

### Learning Signals

**The optimizer reads feedback and adjusts:**

| Feedback | Signal | Action | Tuned Parameter |
|---|---|---|---|
| "Too Blurry" | quality_score = 0.3 | Increase bitrate 20% | scene_type.bitrate_multiplier += 0.2 |
| "Too Compressed" | quality_score = 0.4 | Switch codec H.264→H.265 | scene_type.codec = h265 |
| "Color Wrong" | quality_score = 0.5 | Adjust color grading | grading.strength *= 1.1 |
| "Hallucination" | validation_confidence = 0.2 | Increase input validation | validation_strictness += 1 |
| "Approved" (>5 in a row) | quality_score = 0.9 | Reduce bitrate (cost savings) | scene_type.bitrate_multiplier -= 0.1 |

### Optimizer Integration (ADR-0314)

The Learning Infrastructure (ADR-0314) reads SceneQualityFeedback events and:

1. **Aggregates feedback** per scene type (title/narration/screenshot/animation)
2. **Computes loss signal** (mean quality score per type)
3. **Runs optimizer** (gradient descent on bitrate/codec/grading parameters)
4. **Emits config_updated event** (new parameters for next job)

**Optimizer Config:**
```python
@dataclass
class VideoQualityOptimizer:
    learning_rate: float = 0.01  # step size for parameter updates
    moving_average_window: int = 10  # last N jobs
    convergence_threshold: float = 0.05  # <5% loss improvement, converged
    
    # Constraints (fail-closed)
    min_bitrate: Dict[str, int] = field(default_factory=lambda: {
        "title": 2000,  # 2 Mbps
        "narration": 4000,  # 4 Mbps
        "screenshot": 6000,  # 6 Mbps
        "animation": 4000,  # 4 Mbps
    })
    max_bitrate: Dict[str, int] = field(default_factory=lambda: {
        "title": 16000,  # 16 Mbps
        "narration": 15000,
        "screenshot": 25000,
        "animation": 15000,
    })
```

### Feedback Validation (Fail-Closed)

```python
def validate_feedback(feedback: SceneQualityFeedback) -> bool:
    """Validate feedback before optimizer processes it."""
    # Check 1: Scene exists in job
    if not job_has_scene(feedback.job_id, feedback.scene_id):
        return False
    
    # Check 2: Feedback submitted within 24h of job completion
    job = get_job(feedback.job_id)
    if datetime.now() - job.completed_at > timedelta(days=1):
        return False
    
    # Check 3: Feedback type is valid
    if feedback.feedback_type not in VALID_FEEDBACK_TYPES:
        return False
    
    # Check 4: User hasn't spammed (max 5 feedback per hour)
    recent_count = count_recent_feedback(feedback.tenant_id, hours=1)
    if recent_count > 5:
        return False
    
    return True
```

### Console Dashboard Panel

**"Video Quality & Learning" Tab:**

```
┌─ Video Quality & Learning ───────────────────────────────┐
│                                                           │
│ Recent Job: job_abc123                                   │
│ Status: ✓ Complete (4m 32s)                             │
│                                                           │
│ SCENE FEEDBACK GRID:                                     │
│ ┌─────────────┬─────────────┬─────────────┐             │
│ │ Scene 1     │ Scene 2     │ Scene 3     │             │
│ │ (Title)     │ (Narration) │ (Screenshot)│             │
│ │ [preview]   │ [preview]   │ [preview]   │             │
│ │ ✓ Approve   │ ✗ Reject ▼  │ ✓ Approve   │             │
│ │ Quality: 8.5│ Blurry      │ Quality: 9.0│             │
│ └─────────────┴─────────────┴─────────────┘             │
│                                                           │
│ LEARNING STATUS:                                          │
│ Scene Type: Narration                                    │
│ Feedback Count: 12 scenes                                │
│ Avg Quality: 0.87 (up from 0.82 last job)               │
│ Converged: NO (still improving)                          │
│                                                           │
│ OPTIMIZER TUNING (Last Update):                          │
│ Parameter       | Before   | After  | Status              │
│ ─────────────────────────────────────────────────────────│
│ Bitrate (narr.) | 8 Mbps   | 8.5 Mb │ +0.5 Mbps          │
│ Codec (title)   | H.264    | H.265  │ Changed            │
│ Grading (color) | 1.0      | 1.05   │ +5%                │
│                                                           │
│ [View Full Learning History] [Reset Parameters]          │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

### Data Model

```python
@dataclass(frozen=True)
class FeedbackAggregation:
    """Per-scene-type feedback summary."""
    scene_type: str  # "title", "narration", etc.
    feedback_count: int
    mean_quality_score: float
    std_quality_score: float
    most_common_issue: str  # "too_blurry", etc.
    convergence_status: Literal["improving", "converged", "diverging"]
    timestamp: datetime

@dataclass(frozen=True)
class OptimizerConfig:
    """Learned encoding parameters for next job."""
    scene_type: str
    bitrate_multiplier: float  # 0.8–1.2x baseline
    codec: str  # "h264", "h265"
    grading_strength: float  # 0.8–1.2x
    validation_strictness: int  # 0–10
    applied_at: datetime
    job_ids_trained_on: List[str]
```

### Implementation Outline

```python
class FeedbackHandlerSkill:
    async def submit_scene_feedback(
        self,
        scene_id: str,
        job_id: str,
        feedback_type: str,
        tenant_id: str
    ):
        """User submits feedback on a scene."""
        # Validate
        if not self.validate_feedback(...):
            raise HTTPException(400, "Invalid feedback")
        
        # Create feedback event
        feedback = SceneQualityFeedback(
            scene_id=scene_id,
            job_id=job_id,
            feedback_type=feedback_type,
            confidence=self._estimate_confidence(feedback_type),
            timestamp=datetime.now(timezone.utc),
            tenant_id=tenant_id,
            predicted_quality_before=self._get_model_prediction(scene_id),
            actual_quality_after=self._map_feedback_to_quality(feedback_type)
        )
        
        # Emit to audit chain
        self.audit_backend.write_event("scene_quality_feedback", {
            "scene_id": feedback.scene_id,
            "job_id": feedback.job_id,
            "feedback_type": feedback.feedback_type,
            "quality_signal": feedback.actual_quality_after,
            "tenant_id": feedback.tenant_id,
        })
        
        # Trigger optimizer asynchronously
        await self.trigger_optimizer(job_id, tenant_id)
    
    async def trigger_optimizer(self, job_id: str, tenant_id: str):
        """Aggregate feedback and trigger learning loop."""
        # Count feedback for this job
        feedback_list = self.get_job_feedback(job_id)
        if len(feedback_list) < 5:
            return  # Wait for more feedback before optimizing
        
        # Aggregate by scene type
        aggregated = self.aggregate_feedback_by_type(feedback_list)
        
        # Invoke optimizer (ADR-0314 integration)
        optimizer_result = await self.learning_optimizer.optimize(
            aggregations=aggregated,
            tenant_id=tenant_id,
            constraints=self.get_optimizer_constraints()
        )
        
        # Save new config for next job
        self.save_optimizer_config(optimizer_result, tenant_id)
        
        # Audit: config updated
        self.audit_backend.write_event("video_quality_config_updated", {
            "job_id": job_id,
            "feedback_count": len(feedback_list),
            "optimizer_delta": optimizer_result.to_dict(),
            "tenant_id": tenant_id,
        })
```

### Testing

- `test_feedback_submission_valid_scene` → feedback accepted
- `test_feedback_validation_rejects_old_job` → >24h old, rejected
- `test_feedback_aggregation_per_scene_type` → mean score computed
- `test_optimizer_tuning_increases_bitrate_on_blurry` → bitrate increased
- `test_console_feedback_ui_loads_scenes` → preview + buttons render

### LDD Metrics

| Metric | Target |
|---|---|
| Feedback submission latency | <100ms |
| Optimizer convergence time | <5 jobs |
| Mean quality score improvement | 0.80 → 0.88 (10% gain) |
| Feedback accuracy (user agrees with model) | >0.85 |

## Deployment

**Phase 2 (Weeks 3–4, after Phase 1 input validation):**
- Feedback collection UI
- Learning loop integration
- Optimizer tuning
- Console dashboard

**Phase 3 (Weeks 5–6):**
- Advanced analytics (convergence tracking, loss curves)
- Multi-tenant cross-learning (safe parameter sharing)

---

## Related

- ADR-0314 (Learning Infrastructure) — feedback events, optimizer
- ADR-0702 (Input Validation) — feedback on validation failures
- ADR-0703 (Adaptive Encoding) — bitrate tuning via feedback
- ADR-0701 (Color Processing) — grading strength tuning
