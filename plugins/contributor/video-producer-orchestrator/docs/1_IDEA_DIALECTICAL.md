# Video Producer Plugin: Master Plan (Dialectical Synthesis)

**Date:** 2026-09-13  
**Status:** COMPLETE — Ready for Phase 1 Implementation

---

## THESIS: The Problem We Solve

### Challenge
CorvinOS is powerful but hard to explain in <2 minutes. Current marketing approach:
- Blog posts (too long, people don't read)
- Static images (don't show motion/interaction)
- Community tutorials (inconsistent quality, scattered)

**Goal:** Credible, auditable demo videos (1-min, 5-min, 15-min) that teach CorvinOS without requiring manual PowerPoint editing each time.

### Today's Workflow (Manual, Error-Prone)
```
1. Writer drafts narrative (Google Docs) → 3 days, back-and-forth
2. Designer creates slides (Figma) → 2 days, revisions
3. Voice actor records audio (Audacity) → 1 day, retakes
4. Video editor assembles (Adobe Premiere) → 2 days, color grading
5. YouTube upload (manual metadata) → 0.5 day

Total: 8.5 days, 4 people, $2,000+ cost, no reproducibility
```

### Desired Future
```
corvin video generate --topic="CorvinOS Intro" --duration=1m

Output: high-quality MP4 (1920×1080, H.264, 2.5 Mbps)
        + storyboard JSON (facts verified against ADRs)
        + audit trail (every decision logged)
        + quality score (85/100 = ready for YouTube)

Time: 5 minutes (local), $0 cost (Google Cloud free tier)
```

---

## ANTITHESIS: Why This Is Hard

### Five Hidden Assumptions to Defeat

**1. Assumption: "LLM can write good scripts"**
- **Reality:** LLMs hallucinate. "CorvinOS uses Kubernetes" → false. "Audit chain is bidirectional" → false.
- **Solution:** Fact-checker against ADRs/docs. No claim passes without source.

**2. Assumption: "One video pipeline fits all"**
- **Reality:** 1-min video needs different pacing than 15-min. Narrative structure must adapt.
- **Solution:** 3 templates (1-min / 5-min / 15-min), each with 5-act structure.

**3. Assumption: "Visual quality is subjective"**
- **Reality:** YouTube algorithm favors >60% watch time. Users abandon blurry slides.
- **Solution:** Deterministic quality scorer (5 components, WCAG AA contrast checks).

**4. Assumption: "TTS sounds robotic"**
- **Reality:** Google Cloud TTS sounds professional. Piper (offline) is backup if API fails.
- **Solution:** Primary: Google TTS (16 kHz, natural voice). Fallback: Piper.

**5. Assumption: "Nobody cares about reproducibility"**
- **Reality:** Compliance requires it. "Show me every frame decision for audit." → Impossible without audit trail.
- **Solution:** Hash-chain audit (every slide, every frame, every parameter) → ADR-0314.

### Hard Technical Constraints

| Constraint | Why | Solution |
|---|---|---|
| **Codec Compatibility** | YouTube rejects some H.265 variants | Use H.264, verified bitrate 2–6 Mbps |
| **Audio Sync** | A/V drift accumulates over time | Verify frame/audio sample alignment, re-encode if drift >50ms |
| **Offline TTS Fallback** | Google TTS API can fail | Piper (local) runs on any machine, free |
| **Design System Drift** | Designers change colors mid-project | Lock design_system.json at release, version bumps only |
| **Fact-Checking Latency** | Checking every claim against docs is slow | Index docs at startup (LSH + embeddings), <100ms lookup |

---

## SYNTHESIS: The Solution (Orchestrated Skill + Workers)

### Architecture: Hero's Journey Orchestrator

**Core Insight:** Video generation is a **deterministic state machine**, not an LLM task.

```
                ┌─────────────────────────┐
                │   User Request          │
                │ (topic, duration,       │
                │  custom scripts)        │
                └────────┬────────────────┘
                         │
                ┌────────▼────────────────┐
                │  StoryboardExtractor    │
                │  (Narrative Template)   │
                │  (Fact Checker)         │
                └────────┬────────────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
    ┌─────────┐   ┌──────────┐   ┌───────────┐
    │ Slide   │   │ Audio    │   │ Video     │
    │ Gen     │   │ Gen      │   │ Assembler │
    └────┬────┘   └────┬─────┘   └─────┬─────┘
         │             │               │
         └─────────────┼───────────────┘
                       │
                ┌──────▼──────────┐
                │  QualityValidator│
                │  (5 components)  │
                └────┬────────────┘
                     │
          ┌──────────▼──────────┐
          │ Quality Gates       │
          │ DRAFT / PRODUCTION  │
          │ / BROADCAST         │
          └───────────────────┘
```

### Four Specialized Workers

| Worker | Responsibility | Input | Output | Fallback |
|---|---|---|---|---|
| **SlideGenerator** | Pillow-based slides (text overlay, design system colors) | JSON scene spec | PNG sequence | Plain white + text |
| **AudioGenerator** | TTS synthesis (Google Cloud or Piper) | Script text, speaker voice | MP3/WAV (16 kHz) | Silence (0 dB) |
| **VideoAssembler** | FFmpeg orchestration (concat PNG + audio, encode to H.264) | PNG sequence, audio, timing | MP4 (1920×1080, 2.5 Mbps) | PNG sequence + instructions |
| **QualityValidator** | Deterministic scorer (5 components: visual, audio, narrative, accessibility, specs) | Video metadata | Quality score (0-100) + breakdown | Always returns score (never fails) |

### Three-Tier Quality Gates (HARD ENFORCEMENT)

```
Score 0-50   → DRAFT (must iterate)
Score 50-85  → PRODUCTION (auto-queue for upload)
Score 85-100 → BROADCAST (requires human approval)

No env var override. No skip flag.
```

### Learning Loop (ADR-0314 Integration)

```
Video Generated
    ↓
User Rates (⭐☆ to ⭐⭐⭐⭐⭐)
    ↓
Feedback Event (video_id, rating, timestamp)
    ↓
Learning Daemon (daily)
    ↓
Optimizer: "Users who rate 4+ stars have quality_score ≥ X"
    ↓
Next Video Uses Tuned Gate Threshold
    ↓
Audit Log: "quality_gate_threshold: 50 → 55 (confidence 0.87)"
```

---

## Implementation Roadmap (12 Weeks)

### PHASE 1: Foundation + Security (Weeks 1-3)

**Week 1: Infrastructure**
- ✅ GitHub project setup (Actions, secrets, branch protection)
- ✅ Design system in code (colors.json, typography.json)
- ✅ Plugin.json + setup.py
- ✅ Test infrastructure (pytest, coverage, mocking)
- **Target:** 0 CRITICAL findings, plugin boots

**Week 2: Core Workers**
- ✅ SlideGenerator (Pillow, 300 LOC, 10+ tests)
- ✅ AudioGenerator (Google TTS fallback Piper, 200 LOC, 10+ tests)
- ✅ VideoAssembler (FFmpeg, 500 LOC, 15+ tests)
- **Target:** 96+ tests, 100% worker coverage

**Week 3: Quality Framework**
- ✅ QualityValidator (5-component scorer, 150 LOC, 10+ tests)
- ✅ QualityGates (DRAFT/PRODUCTION/BROADCAST, 200 LOC, 20+ tests)
- ✅ Console integration (review queue UI)
- **Target:** Quality gates live, 0 test failures

### PHASE 2: Visual Excellence (Weeks 4-6)

**Week 4: Design System**
- ✅ Export Figma → SVG/CSS
- ✅ Implement color palette + typography
- ✅ Update all components (Hero's Journey templates)
- **Target:** Visual style complete, reproducible

**Week 5: Animations**
- ✅ Manim integration (3D diagrams)
- ✅ SVG morphing (Skills tree)
- ✅ Motion graphics library
- **Target:** 1 professional reference video (⭐⭐⭐⭐)

**Week 6: Advanced Graphics**
- ✅ Isometric 3D Skills diagram
- ✅ Learning loop animation
- ✅ Audit chain visualization
- **Target:** All graphics ready, reusable

### PHASE 3: Didactic Mastery (Weeks 7-9)

**Week 7: Narrative Framework**
- ✅ Hero's Journey implementation
- ✅ ADR extraction pipeline
- ✅ Fact-checking automation
- **Target:** 3 storyboards complete, all facts verified

**Week 8: Video Generation + User Testing**
- ✅ Generate 3 production videos
- ✅ User testing (10 non-technical users per video)
- ✅ A/B testing + iteration
- **Target:** User comprehension ≥75%, 3 videos at ≥85% quality

**Week 9: Multi-Version Optimization**
- ✅ Fine-tune pacing (1-min / 5-min / 15-min)
- ✅ Cross-device testing (mobile, desktop, TV)
- ✅ Accessibility validation (captions, audio descriptions)
- **Target:** 6 videos ready (3 scripts × 2 quality levels)

### PHASE 4: Scale & Deploy (Weeks 10-12)

**Week 10: CI/CD + Monitoring**
- ✅ GitHub Actions (auto-test, auto-build)
- ✅ Quality dashboard (metrics tracking)
- ✅ YouTube upload automation
- **Target:** CI/CD green, every commit tested

**Week 11: Plugin Documentation**
- ✅ Complete BUILDING_PLUGINS.md
- ✅ Embed all 9 ADRs in docs/
- ✅ Create examples/ with generated videos
- **Target:** Plugin is self-contained tutorial

**Week 12: Production Launch**
- ✅ Publish 3 videos to YouTube
- ✅ Analytics setup + dashboards
- ✅ Plugin registered in Corvin-Marketplace
- **Target:** Plugin live, 50k+ views (2 weeks post-launch)

---

## Success Metrics

### Engineering Metrics
- ✅ Test coverage ≥85%
- ✅ Video generation <5 minutes (local)
- ✅ Quality score reproducible (same input → same output)
- ✅ Audit trail 100% (every decision logged)

### User Metrics
- ✅ User comprehension ≥75% (post-watch survey)
- ✅ YouTube watch time ≥60% (AVD)
- ✅ YouTube CTR ≥2% (click-through rate)
- ✅ Community feedback ≥4/5 stars

### Business Metrics
- ✅ 50k+ views (2 weeks post-launch)
- ✅ GitHub stars +500 (from video visibility)
- ✅ Plugin downloads ≥1,000/month

---

## Risk Management

### CRITICAL Risks (Require Mitigation)

| Risk | Impact | Mitigation |
|---|---|---|
| **TTS API failures** | Videos fail mid-generation | Piper fallback (local, offline) |
| **Hallucinated facts** | Videos spread misinformation | Fact-checker mandatory, <75 confidence = flag for review |
| **FFmpeg codec issues** | Videos unplayable on YouTube | Test on 3 test devices, codec lock in config |
| **Design system drift** | Inconsistent branding | JSON version control, one-way changes (3-tier review) |
| **Timeline slippage** | Phase 3 not ready by Week 9 | Parallel work on Phase 4 starting Week 7 |

### MEDIUM Risks (Monitor)

| Risk | Impact | Mitigation |
|---|---|---|
| **Audio sync drift** | A/V out of sync after 5+ minutes | Verify alignment every frame, re-encode if drift >50ms |
| **Learning loop overfitting** | Gates tuned too loose (worse quality) | Minimum threshold floor (BROADCAST ≥75, never lower) |
| **User testing attrition** | Can't recruit 10 users per video | Offer $25 Visa gift card, stagger recruiting |

### LOW Risks (Document)

| Risk | Mitigation |
|---|---|
| **Figma export issues** | Have manual SVG fallback |
| **Slow CI/CD** | Parallelize tests, cache dependencies |

---

## Team & Autonomy Model

### Roles
- **Orchestrator (You):** Day-to-day execution, blocker resolution, phase gates
- **Workers:** Isolated Python modules (error-handled, testable)
- **Operators:** Marketplace maintainers (plugin registration, analytics)

### Autonomy
- **Phases 1-3:** Autonomous execution (standing status reports weekly)
- **Phase 4:** Human review (YouTube metadata, final QA)

### Escalation
- If any phase >3 days behind schedule → immediate remediation (parallel workstreams)
- If any quality gate fails → root cause analysis + ADR amendment

---

## Load-Bearing Decisions (Never Override)

1. **Fact-checking is mandatory** — no claims without sources
2. **Quality gates are hard** — DRAFT/PRODUCTION/BROADCAST (no env var bypass)
3. **Design system is code** — colors.json is source of truth
4. **Audit trail is complete** — every frame, every parameter logged
5. **Workers are isolated** — one failure doesn't kill the pipeline
6. **Tests are required** — every commit must pass 96+ tests
7. **Learning loop respects minimums** — BROADCAST gate ≥75, never lower

---

## Next Steps

1. **Week 1 Kickoff:** Infrastructure setup (GitHub Actions, design_system.json, plugin.json)
2. **Week 1 Deliverable:** Plugin boots, 0 CRITICAL findings, tests run
3. **Week 2 Kickoff:** Implement SlideGenerator worker
4. **Week 2 Deliverable:** SlideGenerator tested, integrated, produces PNG sequence

**Confidence:** 8.3/10 (tight timeline, achievable with discipline and parallel work on Phases 3-4)

---

**Status: READY FOR PHASE 1 IMPLEMENTATION**
