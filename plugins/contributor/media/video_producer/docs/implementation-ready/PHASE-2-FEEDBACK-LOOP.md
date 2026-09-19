# Phase 2 Implementation — Learning Loop & Feedback
## Per-Scene Feedback UI + Optimizer Integration

**Status:** Implementation Ready  
**Duration:** Weeks 3–4  
**Effort:** ~800 LoC + 20 tests  
**Depends on:** Phase 1 complete

---

## Deliverable 1: Per-Scene Feedback UI

### File Structure
```
web-next/src/
├── components/VideoSceneFeedback.tsx (150 LoC)
│   ├─ Scene preview grid
│   ├─ Approve/Reject/Edit buttons per scene
│   ├─ Feedback reason selector
│   └─ Submit dialog
├── hooks/useSceneFeedback.ts (50 LoC)
├── tests/VideoSceneFeedback.test.tsx (50 LoC, 5 tests)
```

### UI Component
```tsx
<div className="scene-feedback-grid">
  {job.scenes.map(scene => (
    <SceneCard
      key={scene.id}
      thumbnail={scene.thumbnail}
      metadata={scene.metrics}
      onApprove={() => submitFeedback(scene.id, "approved")}
      onReject={() => openRejectDialog(scene.id)}
      onEdit={() => openEditDialog(scene.id)}
    />
  ))}
</div>

<RejectDialog>
  <p>Why does this scene need improvement?</p>
  <select name="reason">
    <option>Too Blurry</option>
    <option>Too Compressed</option>
    <option>Color Wrong</option>
    <option>Hallucination</option>
    <option>Other</option>
  </select>
  <Button onClick={submit}>Submit Feedback</Button>
</RejectDialog>
```

### API Endpoint
```
POST /v1/console/video/jobs/{job_id}/scenes/{scene_id}/feedback

Request:
{
  "feedback_type": "too_blurry" | "too_compressed" | "color_wrong" | "hallucination" | "approved" | "other",
  "confidence": 0.9
}

Response:
{
  "status": "success",
  "event_id": "feedback_evt_12345"
}
```

---

## Deliverable 2: Feedback Handler Skill

### File Structure
```
src/
├── feedback_handler.py (250 LoC)
│   ├─ FeedbackHandlerSkill class
│   ├─ SceneQualityFeedback dataclass
│   ├─ Feedback validation
│   ├─ Audit integration
│   └─ Optimizer trigger
├── tests/test_feedback_handler.py (100 LoC, 8 tests)
```

### Core Implementation
```python
@dataclass(frozen=True)
class SceneQualityFeedback:
    scene_id: str
    job_id: str
    feedback_type: Literal[
        "approved",
        "too_blurry",
        "too_compressed",
        "color_wrong",
        "hallucination"
    ]
    confidence: float  # 0–1
    timestamp: datetime
    tenant_id: str

class FeedbackHandlerSkill:
    async def submit_feedback(
        self,
        scene_id: str,
        job_id: str,
        feedback_type: str,
        tenant_id: str
    ) -> str:
        """
        Submit feedback on scene quality.
        
        Returns: feedback event ID
        Triggers: optimizer (if enough feedback collected)
        """
        # Validation
        if not self.validate_feedback(...):
            raise ValueError("Invalid feedback")
        
        # Create feedback event
        feedback = SceneQualityFeedback(...)
        
        # Audit log
        self.audit_backend.write_event("scene_quality_feedback", {...})
        
        # Trigger optimizer (after 5+ feedbacks per scene type)
        if self.should_trigger_optimizer(job_id):
            await self.trigger_optimizer(job_id, tenant_id)
        
        return feedback.id
```

---

## Deliverable 3: Learning Optimizer Integration

### File Structure
```
src/
├── optimizer.py (300 LoC)
│   ├─ VideoQualityOptimizer class
│   ├─ Learning loop (feedback → config tuning)
│   ├─ Parameter constraint validation
│   └─ ADR-0314 integration
├── tests/test_optimizer.py (100 LoC, 8 tests)
```

### Optimizer Logic
```python
class VideoQualityOptimizer:
    """Learns from feedback, tunes encoding/grading parameters."""
    
    async def optimize_from_feedback(
        self,
        feedback_list: List[SceneQualityFeedback],
        job_id: str,
        tenant_id: str
    ) -> OptimizerConfig:
        """
        Aggregate feedback, compute loss, adjust parameters.
        
        See ADR-0703 for detailed algorithm.
        """
        # 1. Aggregate feedback per scene type
        aggregated = self.aggregate_feedback(feedback_list)
        
        # 2. Compute loss signal (quality score per type)
        loss = self.compute_loss(aggregated)
        
        # 3. Gradient descent on parameters
        new_config = self.gradient_descent(
            current_config=self.load_current_config(tenant_id),
            loss=loss,
            learning_rate=0.01,
            constraints=self.optimizer_constraints
        )
        
        # 4. Save new config
        self.save_optimizer_config(new_config, tenant_id)
        
        # 5. Emit audit event
        self.audit_backend.write_event("optimizer_config_updated", {
            "job_id": job_id,
            "feedback_count": len(feedback_list),
            "loss_delta": loss.delta,
            "config_delta": new_config.delta,
        })
        
        return new_config
```

### Feedback-to-Action Mapping

| Feedback | Signal | Action | Parameter |
|----------|--------|--------|-----------|
| too_blurry | quality=0.3 | bitrate +20% | scene_type.bitrate_multiplier |
| too_compressed | quality=0.4 | switch to H.265 | scene_type.codec |
| color_wrong | quality=0.5 | grading +10% | grading.strength |
| hallucination | quality=0.2 | validation strictness +1 | validation.strictness |
| approved (5+) | quality=0.9 | bitrate -10% (cost savings) | scene_type.bitrate_multiplier |

---

## Deliverable 4: Quality Prediction LLM

### File Structure
```
src/
├── quality_predictor.py (150 LoC)
│   ├─ QualityPredictorSkill class
│   ├─ Confidence scoring (LLM)
│   └─ Prediction caching
├── tests/test_quality_prediction.py (50 LoC, 4 tests)
```

### Implementation
```python
class QualityPredictorSkill:
    """Predict scene quality before rendering (confidence scoring)."""
    
    async def predict_quality(
        self,
        scene: Scene,
        validation_result: AssetValidationResult,
        encoding: EncodingProfile
    ) -> float:
        """
        Predict output quality (0–1) based on inputs.
        
        Inputs:
          - Scene type, description
          - Validation result (confidence)
          - Encoding parameters (bitrate, resolution)
        
        Returns: confidence score (0–1)
        """
        prompt = f"""
Given this scene metadata:
- Type: {scene.type}
- Description: {scene.description}
- Asset validation confidence: {validation_result.overall_confidence}
- Encoding: {encoding.codec}/{encoding.resolution}/{encoding.bitrate}

Predict the output video quality (0–1). Be conservative.
"""
        # Use Haiku (lightweight model)
        response = await self.llm_client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse confidence score
        score = self.extract_score(response.content[0].text)
        return max(0, min(1, score))
```

---

## Deliverable 5: Console Dashboard Updates

### File Structure
```
web-next/src/
├── components/VideoLearningStatus.tsx (100 LoC)
│   ├─ Feedback count per scene type
│   ├─ Convergence status
│   ├─ Optimizer tuning history
│   └─ Next steps
├── tests/VideoLearningStatus.test.tsx (30 LoC)
```

### Dashboard Update
```
┌─ Video Quality & Learning ──────────────┐
│                                         │
│ Recent Job: job_abc123                  │
│                                         │
│ FEEDBACK SUMMARY:                       │
│ Scene Type  │ Feedback │ Quality │ Trend
│ ────────────┼──────────┼─────────┼──────
│ Title       │ 3 ✓      │ 0.92    │ ↑
│ Narration   │ 5 ✗      │ 0.78    │ ↓
│ Screenshot  │ 4 ✓      │ 0.85    │ →
│ Animation   │ 2 ✓      │ 0.88    │ ↑
│                                         │
│ LEARNING STATUS:                        │
│ Converged: NO (improving)               │
│ Mean Quality: 0.86 (up from 0.82)      │
│ Iterations: 2 of 5                      │
│                                         │
│ NEXT TUNING:                            │
│ • Narration bitrate: 8 → 8.5 Mbps      │
│ • Screenshot codec: H.264 → H.265      │
│                                         │
└─────────────────────────────────────────┘
```

---

## Integration Checklist

- [ ] FeedbackHandlerSkill wired into console API
- [ ] Per-scene feedback UI renders scenes + buttons
- [ ] Feedback submission calls API endpoint
- [ ] Audit events logged for each feedback
- [ ] Optimizer triggered after 5+ feedbacks per type
- [ ] Learning dashboard shows feedback count + trend
- [ ] Quality prediction LLM integrated (pre-flight confidence)
- [ ] Config file updated with optimizer results
- [ ] E2E test: submit feedback → optimizer tunes → next job uses config

---

## Test Plan (20 tests, ~30 min)

**Unit Tests:**
- test_feedback_validation_valid → pass
- test_feedback_validation_old_job → reject
- test_feedback_aggregation_per_type → correct mean
- test_optimizer_bitrate_increase_on_blurry → +20%
- test_optimizer_codec_change_on_compressed → H.265
- test_quality_prediction_high_confidence → 0.9+
- test_quality_prediction_low_confidence → 0.3-
- test_config_saved_and_loaded → persisted

**E2E Tests:**
- test_submit_feedback_flow → feedback accepted
- test_optimizer_triggered_on_threshold → config updated
- test_next_job_uses_tuned_config → parameters applied
- test_learning_dashboard_shows_convergence → status updated

---

## Success Criteria

- ✅ All 20 tests green
- ✅ Per-scene feedback UI working (manual test)
- ✅ Optimizer converges within 5 iterations
- ✅ Learning dashboard displays correctly
- ✅ Next job uses tuned parameters (audit verified)

---

**Next Phase:** ADR-0702 (GPU Acceleration, Weeks 5–6)
