---
id: video-producer:ADR-0001
status: accepted
depends_on: []
related: [video-producer:ADR-0002]
paths:
  - "src/"
  - "src/phase5/"
docs:
  - "docs/ARCHITECTURE.md"
  - "docs/IMPLEMENTATION-PLAN.md"
plugin_info:
  name: "video-producer-skill-2.0"
  version: "2.0.0"
  marketplace_path: "plugins/contributor/video_producer"
---

# ADR-0001: Director Mode Advanced — Video Producer Phase 5.1 (Weeks 1–3)

**Status:** ACCEPTED  
**Decision:** Implement 3-Tier Animation System for Video Producer Skill 2.0  
**Depends On:** []  
**Related To:** [video-producer:CONCEPT-0001, video-producer:ADR-0002, video-producer:ADR-0003]

**Paths:**
- `src/phase5/`
- `src/maestro.py`

**Docs:**
- `docs/ARCHITECTURE.md`
- `docs/IMPLEMENTATION-PLAN.md`
- `docs/CONCEPT-0001-orchestrated-skills.md`

---

## Executive Summary

Video Producer Skill 2.0 needs to support multiple animation quality tiers to handle diverse use cases: quick prototypes (Tier 1), professional marketing videos (Tier 2), and hand-crafted cinema (Tier 3). Phase 5.1 delivers the foundation:

1. **ManimAnimatorWorker** — Render Manim scenes to MP4 (Tier 2)
2. **AssetLibrary Versioning** — SHA256-hashed, reproducible assets
3. **Voice-Sync Mapper** — Align narration with animation timing
4. **Fallback Router** — Degrade gracefully if rendering fails
5. **E2E Test Suite** — 15+ tests covering all tiers

**Success Metric:** 98% video generation success rate (vs. 85% baseline).

---

## Problem Statement

### Current State (Phase 5, End-State)
- Phase 5.1–5.4 deliver: Playwright (screenshots), SVG (diagrams), Compositing (mixed assets), FFmpeg (video assembly)
- All videos render at **single quality level**
- No narration generation; script is provided
- No voice-sync; animation pacing is independent of narration
- No asset versioning; same asset name can have different content across videos
- Rendering failures are hard (FFmpeg fails → entire video fails)

### Pain Points
1. **Beginners confused:** Dense technical diagrams (e.g., audit loop) are optimized for experts
2. **Experts bored:** Oversimplified explanations lack depth
3. **Narration misaligned:** Animation speed doesn't match speech pace
4. **Reproducibility nightmare:** A2A task regenerates "learning-loop.svg" — is it the same version as in Video #47?
5. **Production risk:** Single failed render path (e.g., Playwright not installed) blocks all videos

### Why Phase 5.1 Solves It
- **Tier 1 (Quick):** No dependencies, ASCII + simple SVG, fast (10s/scene)
- **Tier 2 (Rich):** Manim animations, professional rendering (60s/scene)
- **Tier 3 (Premium):** Hand-crafted, unlimited time
- **Fallback chain:** Tier 3 fails → Tier 2 → Tier 1 (always produces something)
- **Voice-sync:** Narration timing drives animation keyframes
- **Asset versioning:** SHA256 hash + immutable URLs

---

## Decision: 3-Tier Renderer Architecture

### Three Phases

#### Phase 5.1.1 (Weeks 1–2): ManimAnimatorWorker + Voice-Sync
- **ManimAnimatorWorker.execute(AnimationRequest)** → MP4
  - Scene spec loading (from asset library manifest)
  - Manim scene script generation
  - Subprocess rendering with timeout
  - Output verification (duration + hash)
- **VoiceSyncMapper** — map narration timing to frame indices
  - Input: narration audio + keyframe script
  - Output: list of `(frame_index, narrator_event)`
- **AssetLibraryManifest** — versioned asset registry
  - Each asset: id, type, checksum_sha256, version, dependencies

**E2E Tests (8):**
- Learning loop animation renders in < 60s
- Animation output hash is reproducible
- Voice-sync timing aligns narration to keyframes
- Asset manifest loads and validates
- Fallback from Tier 2 → Tier 1 when Manim unavailable
- Timeout enforcement (hard kill at 60s)

#### Phase 5.1.2 (Weeks 2–3): Fallback Router + Integration
- **FallbackRouter** — if Tier N fails, try Tier N-1
  - TierRenderer interface (execute → Result with success flag)
  - Try sequence: `Tier3 → Tier2 → Tier1`
  - Cache results to avoid re-rendering
- **Didactic Storyboard Parser** — load storyboard schema
- **Full Pipeline Integration** — storyboard → frame sequence → MP4
  - Reuse Phase 5 compositing + FFmpeg assembly
  - Add voice-sync timing to compositor

**E2E Tests (7):**
- Full pipeline: storyboard → MP4 (Tier 2)
- Full pipeline: storyboard → MP4 (Tier 2 fails → Tier 1)
- Storyboard validates didactic level
- Mixed-tier scene (Tier 2 + Tier 1 + Tier 3 hand-crafted)
- Cache prevents duplicate renders
- Frame indices align with voice-sync timing

---

## Tier Specifications

### Tier 1 (Quick)
**Renderer:** ASCII + Simple SVG  
**Speed:** 10s per scene  
**Fidelity:** Low (suitable for drafts)

```python
class Tier1QuickRenderer:
  def execute(self, request: AnimationRequest) -> Result:
    # Render ASCII art or simple SVG
    # No external dependencies beyond PIL
    # Always succeeds (or returns error placeholder)
```

### Tier 2 (Rich)
**Renderer:** Manim (Mathematical Animation Engine)  
**Speed:** 60s per scene (with Manim cached)  
**Fidelity:** Medium (professional)

```python
class ManimAnimatorWorker:
  def execute(self, request: AnimationRequest) -> AnimationResult:
    # Load scene spec from asset library
    # Generate Manim scene script
    # Render via manim subprocess
    # Verify output (duration + hash)
    # Return AnimationResult
```

### Tier 3 (Premium)
**Renderer:** Hand-Crafted Video  
**Speed:** ∞ (human-created)  
**Fidelity:** High (bespoke)

```python
class Tier3PremiumRenderer:
  def execute(self, request: AnimationRequest) -> Result:
    # Load pre-rendered MP4 from asset library
    # Validate checksum
    # Return file path
```

---

## Voice-Sync Specification

### Input
```python
@dataclass
class NarrationScript:
  audio_path: Path              # "narration.mp3"
  script_events: List[str]      # ["Feedback received", "System optimizes", ...]
  timing_sec: List[float]       # [0.0, 15.5, 30.2, ...]  (when each event occurs)
  narration_rate: float         # words per second (extracted from audio)
```

### Output
```python
@dataclass
class VoiceSyncMapping:
  frame_to_event: Dict[int, str]  # {0: "Start", 120: "Feedback", ...}
  narrator_silence_ranges: List[(start_frame, end_frame)]  # for pauses
  keyframe_indices: List[int]     # which frames are "anchor points"
```

### Algorithm
```
1. Load audio → extract timing (via librosa or ffprobe)
2. Parse narration script → extract event keywords
3. For each event:
   - Find timing in audio
   - Map to frame index (frame = timing_sec * frame_rate)
   - Mark as keyframe anchor
4. Output: VoiceSyncMapping (used by compositor to sync animation)
```

---

## Asset Library Manifest

**File:** `assets/manifest.json`

```json
{
  "version": "1.0",
  "description": "Asset Library for Video Producer Phase 5.1",
  "generated_at": "2026-09-14T13:00:00Z",
  "assets": [
    {
      "id": "learning-loop",
      "type": "manim-scene",
      "name": "Learning Loop Diagram",
      "description": "5-step feedback loop animation",
      "version": "1.0",
      "checksum_sha256": "abc123def456...",
      "didactic_level": ["beginner", "technical"],
      "duration_seconds": 30,
      "file_path": "scenes/learning_loop_scene.py",
      "license": "MIT",
      "created_at": "2026-09-14",
      "renderer_tier": 2
    }
  ]
}
```

---

## Fallback Algorithm

```
render_with_fallback(request: AnimationRequest) -> Result:
  for tier in [3, 2, 1]:
    try:
      result = tier_renderer[tier].execute(request)
      if result.success:
        audit_log(event="animation_rendered", tier=tier, result=result)
        return result
    except Exception as e:
      audit_log(event="animation_tier_failed", tier=tier, error=str(e))
      continue
  
  # If all tiers fail, return error result (never render partial/corrupted)
  return Result(success=False, error="All tiers failed")
```

---

## Load-Bearing Constraints

### 1. Voice-Sync is Immutable
Once narration audio is locked, frame timing is immutable. Changing animation speed requires regenerating audio. Prevents out-of-sync disasters.

### 2. Asset Hashing for Reproducibility
Every asset (SVG, Manim scene, screenshot) is SHA256-hashed. Same input → same output hash forever.

### 3. Fallback is Ordered (Tier 3 → 2 → 1)
If Tier 3 fails, automatically try Tier 2. If Tier 2 fails, use Tier 1. Never render something partially.

### 4. Timeout Hard Limit (60s per scene)
Manim renderer kills process at 60s. Prevents runaway renders blocking system.

### 5. Audit-First Design
Every rendering decision (which tier, why it failed, fallback triggered) is logged to audit trail. Immutable, hash-chained.

---

## Testing Strategy

### Unit Tests (8 tests)
- `test_manim_worker_renders_animation`
- `test_animation_output_hash_reproducible`
- `test_voice_sync_mapper_aligns_timing`
- `test_asset_manifest_loads`
- `test_fallback_from_tier2_to_tier1`
- `test_timeout_hard_limit`
- `test_tier3_premium_loads`
- `test_didactic_storyboard_parses`

### Integration Tests (7 tests)
- Full pipeline: storyboard → MP4 (Tier 2)
- Full pipeline: storyboard → MP4 (Tier 2 fails → Tier 1)
- Mixed-tier scene (Tier 2 + Tier 1 + Tier 3)
- Cache prevents duplicate renders
- Frame indices align with voice-sync timing
- Audit trail logs all rendering decisions
- E2E: demo video (Learning Loop) generated successfully

### Success Criteria
- ✅ All 15 tests PASS
- ✅ First demo video renders in < 60s
- ✅ Output MP4 is valid (ffprobe confirms)
- ✅ Hash reproducible (same input → same output)
- ✅ Audit events logged + hash-chained

---

## Implementation Plan (Weeks 1–3)

### Week 1: ManimAnimatorWorker + Voice-Sync
**Deliverables:**
- `ManimAnimatorWorker` class (400 LoC)
- `VoiceSyncMapper` class (150 LoC)
- `AssetLibraryManifest` loader (100 LoC)
- Unit tests (400 LoC)

**Blockers:** None

### Week 2: Fallback Router + Integration
**Deliverables:**
- `FallbackRouter` class (200 LoC)
- `Tier1QuickRenderer` stub (100 LoC)
- `Tier3PremiumRenderer` stub (100 LoC)
- Pipeline integration (200 LoC)
- Integration tests (400 LoC)

**Blockers:** None (Tier 1 and 3 can be stubs initially)

### Week 3: Polish + Demo
**Deliverables:**
- Bug fixes + refinement
- First demo video (Learning Loop, 30s, Manim-generated)
- Documentation + usage guide
- Code review + sign-off

**Blockers:** None

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Manim installation failures | Medium | Fallback to Tier 1; document install procedure |
| Voice-sync timing drift | High | Use audio timestamp extraction (ffprobe); validate timing before rendering |
| Asset versioning conflicts | Medium | Immutable SHA256 hashing; never overwrite assets |
| Rendering timeout cascades | Low | Hard 60s kill limit; fail gracefully to next tier |

---

## Compliance & Audit

### Audit Events
```
{
  "event_type": "animation_rendered",
  "tier": 2,
  "animation_id": "learning-loop",
  "output_hash": "abc123...",
  "duration_seconds": 30,
  "render_time_ms": 45123,
  "timestamp": "2026-09-14T13:00:00Z"
}
```

All rendering decisions logged + hash-chained.

---

## Metrics & Success

**Primary Metric:** Video generation success rate  
- **Baseline (Phase 5):** 85% (single path; no fallback)
- **Target (Phase 5.1):** 98% (3-tier fallback)

**Secondary Metrics:**
- Tier 2 rendering time (target: < 60s/scene)
- Asset library size (target: < 100 MB)
- Voice-sync accuracy (target: ±100ms drift)

---

**Status: ACCEPTED — Phase 5.1 complete and deployed**
