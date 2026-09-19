# Video Producer Plugin 2.0 — Implementation Plan

## Overview

This plan outlines the implementation of the Video Producer Skill 2.0 3-Tier Animation System over **4 phases (8–10 weeks, ~4,500 LoC)**.

---

## Phase 1: Foundation (Weeks 1–3)

**Goal:** Tier 1 + Tier 2 renderers operational + fallback routing + basic voice-sync

### Deliverables

#### Week 1: ManimAnimatorWorker + Voice-Sync Mapper

**Code:**
- `src/phase5/renderers/tier2_manim.py` (400 LoC) — Manim renderer + subprocess timeout
- `src/phase5/voice_sync_mapper.py` (150 LoC) — Audio timing → frame mapping
- `src/phase5/asset_library.py` (100 LoC) — Manifest loader + SHA256 validation

**Tests:**
- `tests/test_manim_renderer.py` (300 LoC, 8 tests)
- `test_voice_sync_timing.py` (150 LoC, 4 tests)
- `test_asset_manifest.py` (100 LoC, 3 tests)

**Gate:** `pytest tests/phase1/` → all pass

#### Week 2: Tier 1 + Tier 3 Stubs + Fallback Router

**Code:**
- `src/phase5/renderers/tier1_quick.py` (100 LoC) — ASCII + simple SVG
- `src/phase5/renderers/tier3_premium.py` (100 LoC) — Asset loader stub
- `src/phase5/fallback_router.py` (200 LoC) — Fallback logic + caching

**Tests:**
- `test_tier1_quick_renderer.py` (100 LoC, 3 tests)
- `test_fallback_router.py` (200 LoC, 5 tests)
- `test_render_cache.py` (80 LoC, 2 tests)

**Gate:** `pytest tests/phase1/` → all pass + E2E: storyboard → MP4 works

#### Week 3: Didactic Storyboard Parser + Integration

**Code:**
- `src/phase5/storyboard/parser.py` (150 LoC) — JSON schema validation
- `src/phase5/storyboard/validator.py` (100 LoC) — Storyboard constraints
- `src/maestro.py` (300 LoC) — Orchestrator + workflow

**Tests:**
- `test_storyboard_parser.py` (150 LoC, 6 tests)
- `test_maestro_workflow.py` (300 LoC, 7 tests)

**Deliverable:** First demo video (Learning Loop, 30s, Manim-generated)

**Gate:** `pytest tests/phase1/` → 15 tests all pass

### Success Criteria (Phase 1)

- ✅ 15 E2E tests passing
- ✅ Demo video generated successfully (Learning Loop, 30s)
- ✅ Hash reproducible (same input → same output)
- ✅ Audit events logged + hash-chained
- ✅ Voice-sync timing aligns within ±100ms

---

## Phase 2: Learning Integration (Weeks 4–6)

**Goal:** Wire learning loop (ADR-0314) + collect feedback + optimize tier selection

### Deliverables

#### Week 4: Learning Event Emission

**Code:**
- Wire `SkillExecutedEvent` emission from Maestro
- Implement feedback collection API (`POST /v1/skills/video-producer/feedback`)
- Learning event store integration

**Tests:**
- `test_learning_event_emission.py` (150 LoC, 4 tests)
- `test_feedback_api.py` (200 LoC, 5 tests)

#### Week 5: Didactic Level Optimizer

**Code:**
- `src/learning/didactic_optimizer.py` (300 LoC) — Track which level performs best
- `src/learning/tier_selector.py` (200 LoC) — Auto-select tier per category

**Tests:**
- `test_didactic_optimizer.py` (250 LoC, 8 tests)
- `test_tier_selector.py` (150 LoC, 5 tests)

#### Week 6: Console Dashboard

**Code:**
- Console panel: Video Producer Stats (`src/panel/video-producer-stats.tsx`, 300 LoC)
  - Tier usage breakdown
  - Success rate by tier
  - Didactic level performance
  - Voice-sync accuracy metrics

**Tests:**
- `test_dashboard_widget.test.tsx` (200 LoC, 6 tests)

### Success Criteria (Phase 2)

- ✅ Learning events emitted + stored
- ✅ Feedback API operational
- ✅ Optimizer converges in <50 videos
- ✅ Console dashboard displays tier metrics
- ✅ 25 additional tests passing

---

## Phase 3: Premium Tier Support (Weeks 7–9)

**Goal:** Full Tier 3 (hand-crafted) workflow + upload API + quality metrics

### Deliverables

#### Week 7: Premium Asset Upload

**Code:**
- `src/phase5/premium_uploader.py` (250 LoC) — Upload + validate hand-crafted videos
- API endpoint: `POST /v1/marketplace/plugins/video-producer/assets`

**Tests:**
- `test_premium_upload.py` (200 LoC, 5 tests)

#### Week 8: Quality Metrics

**Code:**
- `src/quality/bitrate_analyzer.py` (100 LoC)
- `src/quality/color_grading.py` (150 LoC)
- Console panel: Quality Inspector (200 LoC)

**Tests:**
- `test_bitrate_analysis.py` (100 LoC, 3 tests)
- `test_quality_metrics.py` (150 LoC, 4 tests)

#### Week 9: Polish + Documentation

**Code:**
- Refactor + bug fixes (100 LoC)
- Usage guide + examples

**Tests:**
- Full integration test suite (400 LoC, 10 tests)

### Success Criteria (Phase 3)

- ✅ Premium asset upload workflow operational
- ✅ Quality metrics dashboard complete
- ✅ 20+ additional tests passing
- ✅ Documentation complete
- ✅ Code review + sign-off

---

## Phase 4: Production Hardening (Weeks 10–11)

**Goal:** Performance optimization, error handling, deployment readiness

### Deliverables

#### Week 10: Performance & Caching

**Code:**
- Advanced caching strategy (tier-aware, LRU eviction)
- Subprocess pooling for Tier 2 renders
- Memory profiling + optimization

**Tests:**
- Performance benchmarks (300 LoC, 5 tests)
- Memory leak tests

#### Week 11: Error Handling & Deployment

**Code:**
- Graceful error messages (user-facing)
- Retry logic for transient failures
- Plugin manifest + distribution

**Tests:**
- Error scenario tests (200 LoC, 8 tests)
- Deployment smoke tests

### Success Criteria (Phase 4)

- ✅ P95 latency < 120s (Tier 2 cold start)
- ✅ Cache hit rate > 60%
- ✅ 0 memory leaks
- ✅ All error scenarios handled
- ✅ Plugin ready for Marketplace distribution

---

## Testing Strategy

### Test Coverage

| Phase | Unit | Integration | E2E | Total |
|-------|------|-------------|-----|-------|
| **1** | 15 | 5 | 5 | **25** |
| **2** | 18 | 8 | 5 | **31** |
| **3** | 12 | 10 | 8 | **30** |
| **4** | 13 | 8 | 5 | **26** |
| **TOTAL** | **58** | **31** | **23** | **112** |

### Test Categories

**Unit Tests:**
- Component-level: renderers, voice-sync mapper, storyboard parser
- Data structure validation
- Fallback algorithm correctness

**Integration Tests:**
- Full pipeline: storyboard → frames → compositor → MP4
- Tier fallback scenarios (Tier 2 fails → Tier 1)
- Cache invalidation
- Learning event emission

**E2E Tests:**
- Real video generation (Learning Loop demo)
- Hash reproducibility verification
- Voice-sync accuracy (±100ms)
- Audit trail verification

---

## Blockers & Mitigations

| Blocker | Likelihood | Mitigation | Phase |
|---------|-----------|-----------|-------|
| Manim installation complexity | Medium | Pre-built Docker image + doc | 1 |
| FFmpeg compatibility | Low | Multi-platform testing | 1 |
| Voice-sync timing drift | Medium | Audio analysis validation | 1 |
| Learning optimizer convergence | Low | Manual tuning levers | 2 |
| Console integration delays | Low | Parallel UI development | 2 |
| Premium asset versioning | Medium | Immutable SHA256 naming | 3 |
| Performance at scale (1000 videos/day) | Medium | Caching + pooling strategy | 4 |

---

## Resource Requirements

**Team:**
- 1 senior skill engineer (8–10 weeks full-time)
- 1 QA engineer (3–4 weeks, Phase 1-2)
- 1 product lead (review gates, phase decisions)

**Infrastructure:**
- Render worker machine (Manim: 2GB RAM, GPU optional)
- Asset storage (S3 or equivalent, ~500 GB)
- Telemetry backend (OTEL-compatible)

**External Dependencies:**
- Manim + ffmpeg (open-source, packaged)
- Google Cloud Text-to-Speech API (narration, optional)
- Anthropic API (LLM-based narration variants, optional)

---

## Rollout Strategy

**Phase 1 → Internal Testing (1–2 weeks)**
- Core team generates sample videos
- Feedback on UX, quality, performance

**Phase 2 → Beta Users (2–3 weeks)**
- 5–10 marketplace contributors test
- Gather feedback on learning loop

**Phase 3 → GA Release (Weeks 9–10)**
- Marketplace plugin published
- Documentation complete

**Phase 4 → Production Optimization (Ongoing)**
- Monitor performance metrics
- Tune parameters based on real usage

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Video Generation Success Rate** | 98% | (successful videos / total attempts) |
| **Tier 2 Render Time (cold)** | < 60s/scene | ffprobe duration measurement |
| **Voice-Sync Accuracy** | ±100ms | Audio timing vs. frame index diff |
| **Cache Hit Rate** | > 60% | (cached renders / total renders) |
| **Learning Optimizer Convergence** | 50–100 videos | Tier selection stabilization |
| **P95 Latency** | < 120s | End-to-end time measurement |

---

## Timeline

```
Week 1  │ Manim + Voice-Sync
Week 2  │ Tier 1/3 + Fallback + Caching
Week 3  │ Storyboard Parser + Maestro [GATE 1: Demo Video]
────────├─────────────────────────────────────────────
Week 4  │ Learning Events + Feedback API
Week 5  │ Didactic Optimizer
Week 6  │ Console Dashboard [GATE 2: Learning Loop]
────────├─────────────────────────────────────────────
Week 7  │ Premium Upload API
Week 8  │ Quality Metrics
Week 9  │ Polish + Documentation [GATE 3: GA Ready]
────────├─────────────────────────────────────────────
Week 10 │ Performance Optimization
Week 11 │ Error Handling + Deployment [GATE 4: Production]
```

---

**Status: IMPLEMENTATION-READY — Ready for Phase 1 Kickoff**
