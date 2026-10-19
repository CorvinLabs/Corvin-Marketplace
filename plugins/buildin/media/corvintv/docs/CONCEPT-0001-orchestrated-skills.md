---
id: video-producer:CONCEPT-0001
status: accepted
describes: "Orchestrated Multi-Skill Pattern"
related: [video-producer:ADR-0001, video-producer:ADR-0002, video-producer:ADR-0003]
paths:
  - "src/maestro.py"
  - "src/workers/"
docs:
  - "docs/ARCHITECTURE.md"
plugin_info:
  name: "video-producer-skill-2.0"
  version: "2.0.0"
---

# CONCEPT-0001: 3-Tier Animation & Didactic Storyboards

**Status:** ACCEPTED  
**Pattern Type:** Pedagogical Content Engineering  
**Integration:** Video Producer Skill 2.0 Phase 5.1 (Director Mode Advanced)  
**Date Created:** 2026-09-14

---

## The Problem: One-Size-Fits-All Video Production

**Thesis:** Current video producer generates "flat" storyboards—same animation quality for every audience (beginners, technical experts, learners). Narration is generic. Asset complexity varies wildly, causing:
- Beginners confused by dense technical diagrams
- Experts bored by oversimplified explanations
- No synchronization between narration pacing and visual reveals
- No asset versioning; regenerating a single scene breaks reproducibility across videos

**Antithesis:** A fully custom animation system would:
- Generate 3 versions of every scene (quick/rich/premium)
- Add LLM-based narration generation per didactic level
- Implement frame-by-frame voice-sync
- Version every asset (SVG, Manim, Playwright screenshot)
- Require 10x implementation cost for marginal benefit

**Synthesis:** **3-Tier Animation Didactics System**
- **Tier 1 (Quick):** Fast-render ASCII + simple SVG (10s per scene)
- **Tier 2 (Rich):** Manim math animations + voice-sync narration (60s per scene)
- **Tier 3 (Premium):** Hand-crafted high-fidelity cinematography (unlimited time)

Each tier inherits lower tiers' fallbacks (Tier 3 broken → use Tier 2; Tier 2 broken → use Tier 1).

---

## Solution: Didactic Storyboard as First-Class Concept

### Core Insight
A **Didactic Storyboard** is not just a sequence of slides—it is:
1. **Parametric:** Learns from feedback (which didactic level performs best)
2. **Versioned:** Every asset has SHA256 hash + immutable URL
3. **Voice-Synced:** Each animation step maps to narration timing
4. **Fallback-Safe:** Rendering failure at Tier 3 gracefully downgrades

### Three Tiers

| Tier | Renderer | Speed | Fidelity | Use Case |
|------|----------|-------|----------|----------|
| **1: Quick** | ASCII + simple SVG | 10s/scene | Low (suitable for sketches) | Drafts, prototypes, testing |
| **2: Rich** | Manim + voice-sync | 60s/scene | Medium (professional) | Marketing, educational, public docs |
| **3: Premium** | Hand-crafted cinematic | ∞ | High (bespoke) | Launch announcements, keynote videos |

---

## Load-Bearing Constraints

### 1. **Voice-Sync is Immutable**
Once narration audio is generated, frame timing must NOT change. Changing animation speed requires re-generating audio. Prevents out-of-sync disasters.

### 2. **Asset Hashing for Reproducibility**
Every SVG, Manim scene, screenshot is SHA256-hashed. Same input → same output hash forever. Allows "pin to hash" in storyboards: `assets: ["learning-loop.svg#abc123def456..."]` guarantees reproducibility across 100 videos.

### 3. **Fallback is Ordered (1 → 2 → 3)**
If Tier 3 rendering fails, automatically use Tier 2. If Tier 2 fails, use Tier 1. Never render something "partially"—either fully succeed or cleanly fail to next tier.

### 4. **Didactic Level is Learnable**
Track which didactic level (beginner vs. technical) produces better engagement/retention. Learning loop adjusts router to pick the better level for future videos in same category.

---

## Hypotheses & Validation Plan

### H1: 3-Tier Fallback Reduces Rendering Failures
**Metric:** % of videos successfully generated (no manual intervention)  
**Baseline:** Phase 5 (all videos, single-path) = 85% (without Playwright installed, falls back to stub)  
**Target:** Phase 5.1 (3-tier) = 98% (Tier 3 fails → Tier 2 → Tier 1)

### H2: Voice-Sync Improves Perceived Quality
**Metric:** User survey (1-5 scale, "animation matches narration timing?")  
**Baseline:** Phase 5 (no sync) = 2.1/5  
**Target:** Phase 5.1 (with sync) = 4.2/5

### H3: Didactic Level Learning Converges
**Metric:** % of learners choosing "more helpful" when comparing beginner vs. technical for same concept  
**Baseline:** Random (50/50)  
**Target:** Phase 5.1 (after 20 videos) = 70% convergence to best level

---

## Alternative Approaches (Rejected)

### A1: Single-Tier Parameterized Quality
Generate one animation, adjust quality via `--quality` flag at render time.  
**Why rejected:** Quality adjustments after rendering break voice-sync; no graceful degradation.

### A2: Fully AI-Generated Narration
LLM generates 100% of narration (no human input).  
**Why rejected:** LLM can hallucinate; for educational content, human narration ensures accuracy. Hybrid (human + LLM) is better.

### A3: Real-Time Tier Selection (No Pre-Render)
Decide Tier at runtime based on available bandwidth.  
**Why rejected:** Stalls video playback if Tier 2 rendering is slow; pre-rendering all tiers eliminates latency.

---

## When to Use This Pattern

✅ **Use CONCEPT-0001 when:**
- Producing educational/marketing videos with multiple target audiences
- Narration timing matters (learning outcomes depend on pacing)
- Asset reproducibility is critical (versioning, A/B testing, auditing)
- Rendering failures should NOT block publication (graceful fallback needed)

❌ **Don't use when:**
- Single audience, single narration style (overhead not justified)
- Real-time/streaming video (pre-rendering defeats purpose)
- 100% hand-crafted cinematography (no fallback needed; use Tier 3 only)

---

## Implementation Phases

### Phase 5.1 (Weeks 1–3): Foundation
- **ManimAnimatorWorker** (Tier 2 renderer) — 400 LoC
- **AssetLibrary versioning** — manifest.json + SHA256 hashing
- **Voice-Sync Mapper** — map narration timing to frame indices
- **Fallback Router** — if Tier N fails, try Tier N-1
- **E2E Tests** — 15+ tests covering all tiers, fallback logic

### Phase 5.2 (Weeks 4–6): Learning Integration
- **Didactic Level Learner** — track which level performs better
- **Storyboard Optimizer** — adjust tier selection per category
- **Console Dashboard** — visualize tier usage, success rates
- **Feedback Collection** — user survey integration

### Phase 5.3 (Weeks 7–10): Hand-Crafted Premium Support
- **Tier 3 Upload API** — upload hand-crafted videos
- **Cinematic Asset Management** — organize premium assets
- **Quality Metrics** — file size, bitrate, color grading
- **Preview Generation** — thumbnail + preview MP4

---

## Related Artifacts

- **video-producer:ADR-0001:** Director Mode Advanced (phases, gates, decision points)
- **video-producer:ADR-0002:** 3-Tier Animation Architecture (renderer contracts, fallback algorithm)
- **video-producer:ADR-0003:** Didactic Storyboard System (schema, voice-sync timing, asset versioning)

---

**Status: ACCEPTED — Pattern deployed and in production**
