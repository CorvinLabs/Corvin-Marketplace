---
id: video-producer:ADR-0003
status: accepted
depends_on: [video-producer:ADR-0001, video-producer:ADR-0002]
related: [video-producer:CONCEPT-0001]
paths:
  - "src/phase5/storyboard/"
docs:
  - "docs/ARCHITECTURE.md"
plugin_info:
  name: "video-producer-skill-2.0"
  version: "2.0.0"
---

# ADR-0003: Didactic Storyboard System — Schema, Voice-Sync, Asset Versioning

**Status:** ACCEPTED  
**Decision:** Define storyboard schema with voice-sync timing + asset versioning  
**Depends On:** [video-producer:ADR-0001, video-producer:ADR-0002]  
**Related To:** [video-producer:CONCEPT-0001]

**Paths:**
- `src/phase5/storyboard/`
- `storyboards/`

**Docs:**
- `docs/ARCHITECTURE.md`

---

## Executive Summary

A **Didactic Storyboard** is a JSON file that defines:
1. **Scene Sequence** — list of scenes in order
2. **Didactic Level** — "beginner" or "technical" (affects narration, animation complexity)
3. **Voice-Sync Timing** — narration script + keyframe anchors (frames aligned to speech)
4. **Asset Versioning** — SHA256 hashes ensure reproducible renders
5. **Tier Preferences** — which tier (1/2/3) to use for each scene

**Example:**
```json
{
  "id": "learning-loop-explainer",
  "title": "The Learning Loop",
  "didactic_level": "beginner",
  "duration_seconds": 120,
  "scenes": [
    {
      "id": "intro",
      "title": "Introduction",
      "duration_seconds": 30,
      "animation": {
        "animation_id": "learning-loop-intro",
        "preferred_tier": 2,
        "fallback_to": [1]
      },
      "narration": {
        "script": "Today we'll explore how systems learn from feedback.",
        "voice_id": "en-US-Neural2-A",
        "timing_sec": 0.0,
        "voice_sync": {
          "keyframes": [
            {"frame": 0, "event": "speech_start"},
            {"frame": 60, "event": "diagram_appears"},
            {"frame": 120, "event": "animation_completes"}
          ]
        }
      }
    }
  ]
}
```

---

## Storyboard Schema (YAML / JSON)

### Top-Level Structure
```yaml
storyboard:
  id: string                          # Unique identifier
  title: string                        # Human-readable title
  description: string                  # Long description
  didactic_level: "beginner" | "technical"
  target_audience: string              # e.g., "educators", "engineers"
  duration_seconds: number             # Total video length
  language: string                     # "en", "de", etc.
  created_at: ISO8601                  # When created
  created_by: string                   # Author
  version: string                      # "1.0", "1.1", etc.
  revision_notes: string               # What changed in this version
  
  scenes: [Scene]                      # Ordered list of scenes
  metadata: Metadata                   # Optional metadata
```

### Scene Structure
```yaml
scene:
  id: string                           # "intro", "learning-loop-explanation"
  title: string                         # Scene title
  duration_seconds: number              # How long this scene plays
  
  # Animation specification
  animation:
    animation_id: string                # "learning-loop"
    tier_preference: number             # Preferred tier (1, 2, or 3)
    fallback_to: [number]               # Fallback tiers if preferred fails
    duration_override: number           # Override asset duration (optional)
  
  # Narration and voice-sync
  narration:
    script: string                      # Full narration text for this scene
    voice_id: string                    # "en-US-Neural2-A" (voice provider ID)
    language: string                    # "en-US"
    timing_start_sec: number            # When narration starts (0 if first scene)
    
    voice_sync:
      keyframes: [Keyframe]             # Animation-narration sync points
      silence_ranges: [Range]           # Pauses in narration (optional)
  
  # Visual elements (overlays, text, etc.)
  visual_elements: [VisualElement]      # Optional
  
  # Metadata specific to this scene
  metadata:
    difficulty_level: string            # "easy" | "medium" | "hard"
    learning_objectives: [string]       # What learner should know after
    estimated_completion_time_sec: number
```

### Keyframe Structure (Voice-Sync)
```yaml
keyframe:
  frame: number                          # Frame index (frame = time_sec * 30 FPS)
  event: string                          # "speech_start", "diagram_appears", etc.
  narrator_text: string                  # Text spoken at this frame
  animation_action: string               # "zoom_in", "highlight", "fade_in" (optional)
  timestamp_sec: number                  # Absolute time in audio (for verification)
```

### Asset Reference (Versioned)
```yaml
asset_ref:
  id: string                             # "learning-loop"
  version: string                        # "1.0"
  checksum_sha256: string                # Asset hash (ensures reproducibility)
  # OR use short form:
  asset_id: "learning-loop#v1.0#abc123def456..."  # Fully qualified
```

---

## Voice-Sync Timing Algorithm

### Input
```python
@dataclass
class NarrationAudio:
  audio_path: Path              # "narration.mp3"
  duration_sec: float           # Duration of audio file
  frame_rate: int = 30          # FPS (standard video)
```

### Processing Steps
```
1. Load audio → extract timing metadata
2. For each keyframe in narration.voice_sync.keyframes:
   a. timestamp_sec = keyframe.timestamp_sec
   b. frame_index = timestamp_sec * frame_rate
   c. validate: 0 <= frame_index < total_frames
   d. mark as anchor point in timeline
3. For each silence_range:
   a. start_frame = silence_start_sec * frame_rate
   b. end_frame = silence_end_sec * frame_rate
   c. no animation/narration between these frames
4. Output: VoiceSyncMapping (used by compositor)
```

### Verification
```python
def validate_voice_sync(storyboard: Storyboard, audio: NarrationAudio):
  total_frames = int(audio.duration_sec * 30)
  
  for scene in storyboard.scenes:
    for keyframe in scene.narration.voice_sync.keyframes:
      if keyframe.frame >= total_frames:
        raise ValueError(
          f"Scene {scene.id}: keyframe {keyframe.frame} "
          f"exceeds audio duration ({total_frames} frames)"
        )
  
  # Check for overlapping silence ranges
  for scene in storyboard.scenes:
    ranges = scene.narration.voice_sync.silence_ranges or []
    for i, r1 in enumerate(ranges):
      for r2 in ranges[i+1:]:
        if ranges_overlap(r1, r2):
          raise ValueError(f"Overlapping silence ranges in scene {scene.id}")
```

---

## Asset Versioning & Reproducibility

### Reproducibility Guarantee
```
Same storyboard + same assets → same video output (bit-for-bit)

Proof:
1. Asset: animation_id + version + checksum_sha256 uniquely identifies content
2. Narration: script text + voice_id + timing_sec uniquely identify audio
3. Compositor: same inputs + same parameters → deterministic output
4. FFmpeg: same frames + same audio + same codec → bit-identical video
```

---

## Validation Rules

### Storyboard-Level Validations
```python
def validate_storyboard(storyboard: dict) -> List[ValidationError]:
  errors = []
  
  # Required fields
  required = ["id", "title", "didactic_level", "scenes"]
  for field in required:
    if field not in storyboard:
      errors.append(ValidationError(f"Missing required field: {field}"))
  
  # Didactic level must be valid
  if storyboard.get("didactic_level") not in ["beginner", "technical"]:
    errors.append(ValidationError("Invalid didactic_level"))
  
  # Scene IDs must be unique
  scene_ids = [s["id"] for s in storyboard.get("scenes", [])]
  if len(scene_ids) != len(set(scene_ids)):
    errors.append(ValidationError("Duplicate scene IDs"))
  
  # Total duration must match sum of scene durations
  total = sum(s.get("duration_seconds", 0) for s in storyboard.get("scenes", []))
  if total != storyboard.get("duration_seconds", 0):
    errors.append(ValidationError("Duration mismatch"))
  
  return errors
```

### Scene-Level Validations
```
- narration.voice_sync.keyframes must be sorted by frame
- keyframes must not exceed audio duration
- animation.tier_preference must be in [1, 2, 3]
- animation.fallback_to must contain tiers < tier_preference
- duration_seconds > 0
```

---

## Implementation Workflow

### Creating a Storyboard (Operator)
```
1. Define scenes + narration script
2. Record/generate narration audio
3. Manually annotate keyframe timing (or auto-extract)
4. Validate storyboard (check_storyboard_valid())
5. Save to storyboards/<id>.json
6. Commit + push
```

### Rendering a Storyboard (Video Producer Skill)
```
1. Load storyboard.json
2. Validate (check_storyboard_valid())
3. For each scene:
   a. Load animation via FallbackRouter (tier 3→2→1)
   b. Load narration audio
   c. Validate voice-sync timing
   d. Composite animation + narration + overlays
   e. Output frames
4. Assemble all frames → final MP4
```

---

## Testing Strategy

### Unit Tests
- `test_storyboard_schema_valid`
- `test_storyboard_schema_invalid` (missing required fields)
- `test_voice_sync_keyframes_sorted`
- `test_voice_sync_exceeds_audio_duration` (error case)
- `test_asset_versioning_reproducible`
- `test_didactic_level_learning` (feedback integration)
- `test_silence_ranges_valid`

### Integration Tests
- `test_storyboard_load_and_validate`
- `test_storyboard_render_full_pipeline`
- `test_storyboard_voice_sync_alignment`
- `test_storyboard_asset_caching`
- `test_storyboard_fallback_tiers`

---

## Audit Trail Events

```json
{
  "event_type": "storyboard_loaded",
  "storyboard_id": "learning-loop-explainer-v1",
  "didactic_level": "beginner",
  "scene_count": 2,
  "timestamp": "2026-09-14T13:00:00Z"
}

{
  "event_type": "storyboard_rendered",
  "storyboard_id": "learning-loop-explainer-v1",
  "output_path": "/tmp/video.mp4",
  "output_hash": "...",
  "duration_seconds": 120,
  "tiers_used": [2, 1],
  "timestamp": "2026-09-14T13:01:00Z"
}
```

---

## Load-Bearing Constraints

### 1. Storyboard is Immutable Once Published
Once a storyboard is used to generate a video, its ID + version cannot change. Always create a new version (e.g., v1.1) if modifications are needed.

### 2. Voice-Sync Keyframes are Anchors, Not Prescriptions
Keyframes define *when* animation events occur relative to narration, not *what* happens. The animation system interprets keyframe events.

### 3. Asset Hash is Canonical
If an asset's checksum_sha256 changes, it's a different asset (even if animation_id is same). Update version + hash.

### 4. Didactic Level is Observable
Every rendered video must include metadata indicating which didactic level was used, enabling learning loop feedback.

---

## Future Enhancements

1. **LLM Narration Generation** — Auto-generate beginner/technical narration variants
2. **Didactic Level Optimization** — Learning loop recommends best level per concept
3. **Interactive Storyboards** — Pause/replay sections, quiz integration
4. **Multi-Language Support** — Translate storyboard + regenerate narration
5. **Accessibility Features** — Captions, audio descriptions, high-contrast assets

---

**Status: ACCEPTED — Deployed and in production**
