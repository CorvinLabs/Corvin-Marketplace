# Video Producer Plugin 2.0 — Architecture Overview

## System Overview

The Video Producer Skill 2.0 is an **orchestrated multi-worker skill** that generates educational and marketing videos from storyboard specifications. The plugin implements a **3-Tier Animation Architecture** to handle diverse quality and complexity requirements.

```
┌─────────────────────────────────────────────────────────────┐
│                    Maestro Skill                            │
│           (Orchestration + Workflow Management)             │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
    ┌────▼────┐   ┌────▼────┐  ┌────▼────┐
    │ Tier 1  │   │ Tier 2  │  │ Tier 3  │
    │ Quick   │   │  Rich   │  │Premium  │
    │Renderer │   │Renderer │  │Renderer │
    └────┬────┘   └────┬────┘  └────┬────┘
         │             │             │
    ASCII + SVG    Manim Math    Hand-Crafted
    10s/scene      60s/scene      ∞/scene
         │             │             │
         └─────────────┼─────────────┘
                       │
              ┌────────▼────────┐
              │ FallbackRouter  │
              │ (Tier 3→2→1)    │
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │  Compositor     │
              │ (Voice-Sync +   │
              │  FFmpeg)        │
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │   Output MP4    │
              └─────────────────┘
```

---

## Core Components

### 1. Maestro Skill (Orchestrator)

**File:** `src/maestro.py`  
**Purpose:** High-level workflow orchestration + phase gating

**Responsibilities:**
- Load storyboard specification (JSON)
- Validate storyboard schema (ADR-0003)
- Emit learning events to track execution
- Coordinate workers (Tier renderers, compositors)
- Handle task state + progress tracking
- Log all decisions to audit trail

**Input:** `MaestroRequest` (storyboard_id, didactic_level, tier_preference)  
**Output:** `MaestroResult` (video_path, duration, tiers_used, audit_events)

### 2. Three Tier Renderers

#### Tier 1: Quick Renderer
**File:** `src/phase5/renderers/tier1_quick.py`  
**Dependencies:** PIL, standard library  
**Output:** ASCII art + simple SVG animations  
**Speed:** 10s per scene  
**Fallback:** Always succeeds (no dependencies)

#### Tier 2: Manim Animator Worker
**File:** `src/phase5/renderers/tier2_manim.py`  
**Dependencies:** manim, ffmpeg, latex  
**Output:** Professional mathematical animations  
**Speed:** 60s per scene (cached)  
**Fallback:** Uses Tier 1 if manim unavailable

#### Tier 3: Premium Renderer
**File:** `src/phase5/renderers/tier3_premium.py`  
**Dependencies:** Asset library access  
**Output:** Pre-rendered hand-crafted videos  
**Speed:** <1s (just copy)  
**Fallback:** Uses Tier 2 if asset unavailable

### 3. Fallback Router

**File:** `src/phase5/fallback_router.py`  
**Purpose:** Transparent tier selection + graceful degradation

**Algorithm:**
```
For each animation request:
  Try Tier 3:
    ├─ Check if asset exists + valid
    ├─ Verify checksum SHA256
    └─ If success, return (emit audit event)
  
  Try Tier 2:
    ├─ Check if Manim available
    ├─ Generate scene spec
    ├─ Render subprocess (60s timeout)
    ├─ Verify output
    └─ If success, return (emit audit event)
  
  Try Tier 1:
    ├─ Always available
    ├─ Render ASCII/SVG
    └─ Return (emit audit event)
  
  If all fail:
    └─ Return error (emit audit event)
```

### 4. Voice-Sync Mapper

**File:** `src/phase5/voice_sync_mapper.py`  
**Purpose:** Align narration timing to animation keyframes

**Algorithm:**
1. Load narration audio (MP3/WAV)
2. Extract timing metadata (ffprobe or librosa)
3. For each keyframe in storyboard:
   - Map narrator event to frame index
   - Mark as anchor point
4. Output `VoiceSyncMapping` for compositor

**Critical Constraint:** Immutable once narration is locked (ADR-0001, Constraint #1)

### 5. Asset Library Manager

**File:** `src/phase5/asset_library.py`  
**Purpose:** Version + hash all assets (SVG, Manim scenes, screenshots)

**Features:**
- SHA256 hashing for reproducibility
- Manifest versioning (manifest.json)
- Immutable asset URLs (`asset_id#version#hash`)
- Fallback chain management

**Manifest Format:**
```json
{
  "assets": [
    {
      "id": "learning-loop",
      "version": "1.0",
      "checksum_sha256": "abc123...",
      "type": "manim-scene",
      "renderer_tier": 2
    }
  ]
}
```

### 6. Compositor

**File:** `src/phase5/compositor.py`  
**Purpose:** Assemble frames + narration + overlays → MP4

**Pipeline:**
1. Load animation frames (from Tier renderer)
2. Load narration audio
3. Apply voice-sync timing (keyframe anchors)
4. Add visual overlays (text, annotations)
5. Composite to final frames
6. Assemble with FFmpeg → MP4

---

## Data Flow

```
┌────────────────────────────────────────────┐
│        Storyboard (JSON Input)             │
│  - Scenes: [intro, explanation, conclusion]
│  - Didactic Level: "beginner"|"technical" │
│  - Voice-sync: keyframes + timing          │
└────────────────────┬─────────────────────┘
                     │
              ┌──────▼──────┐
              │   Maestro   │
              │  (Validate) │
              └──────┬──────┘
                     │
          ┌──────────┼──────────┐
          │                     │
     ┌────▼────┐         ┌─────▼──────┐
     │ For Each│         │  Load      │
     │ Scene   │         │ Narration  │
     └────┬────┘         │ Audio      │
          │              └─────┬──────┘
          │                    │
     ┌────▼──────────────────┬─▼─────────┐
     │   FallbackRouter      │ VoiceSyncMapper
     │   (Try Tier 3→2→1)    │ (Map timing)
     └────┬──────────────────┬─────────┘
          │                  │
     ┌────▼────┐             │
     │ Rendered│             │
     │Frames   │             │
     └────┬────────────────┬─┘
          │                │
          └────────┬───────┘
                   │
              ┌────▼─────────┐
              │ Compositor   │
              │ (Assembly)   │
              └────┬─────────┘
                   │
              ┌────▼─────────┐
              │ Output MP4   │
              └──────────────┘
```

---

## Learning Integration (ADR-0314)

Every Skill execution emits learning events:

```python
{
  "event_type": "skill_executed",
  "skill_id": "video-producer-skill-2.0",
  "input": {"storyboard_id": "learning-loop", "didactic_level": "beginner"},
  "output": {"video_path": "/tmp/video.mp4", "tiers_used": [2, 1]},
  "latency_ms": 125000,
  "lom": "maestro.execute:L237",  # Line of Moral Responsibility
  "timestamp": "2026-09-14T13:00:00Z"
}
```

**Feedback Loop:**
1. Video is published
2. User watches + provides feedback (quality rating, engagement)
3. Feedback event emitted
4. Learning optimizer reads feedback + skill events
5. Adjusts tier selection for future videos in same category

---

## Audit Trail Integration (ADR-0232/0233)

All rendering decisions are immutable, hash-chained:

```json
{
  "event_type": "animation_tier_attempt",
  "animation_id": "learning-loop",
  "tier": 2,
  "status": "success|failed|skipped",
  "output_hash": "def456...",
  "timestamp": "2026-09-14T13:00:00Z",
  "tenant_id": "_default"
}
```

**Verification:**
- Hash-chain verified at boot (ADR-0232 tripwire)
- Operator can audit full video generation history
- Reproducible: same storyboard + assets → same output hash

---

## Compliance & Constraints

### Load-Bearing Rules (ADR-0001, ADR-0002, ADR-0003)

1. **Voice-Sync Immutable:** Frame timing locked once narration is generated
2. **Asset Hashing:** SHA256 for all assets (reproducibility guarantee)
3. **Fallback Ordered:** Always try Tier 3 → Tier 2 → Tier 1 (never randomize)
4. **Timeout Hard Limit:** 60s max per Tier 2 render (hard kill)
5. **Audit-First Design:** Every decision logged + hash-chained

### Tenant Isolation (GDPR Art. 5, 6, 32)

All events scoped to `tenant_id`. Cross-tenant queries blocked.

---

## Related Documentation

- **[ADR-0001: Director Mode Advanced](./ADR-0001-director-mode.md)** — High-level design + phase gates
- **[ADR-0002: 3-Tier Animation Architecture](./ADR-0002-3tier-animation.md)** — Renderer contracts + fallback algorithm
- **[ADR-0003: Didactic Storyboard System](./ADR-0003-didactic-storyboard.md)** — Schema + voice-sync timing
- **[CONCEPT-0001: Orchestrated Skills](./CONCEPT-0001-orchestrated-skills.md)** — Design pattern + alternatives
- **[Implementation Plan](./IMPLEMENTATION-PLAN.md)** — Phases, deliverables, timeline
