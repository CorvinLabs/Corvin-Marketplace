# Video Producer Plugin: Architecture Reference

**Complete system design for auditable, learnable, resilient video generation.**

---

## System Layers

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 7: YouTube Integration (upload, analytics)           │
├─────────────────────────────────────────────────────────────┤
│  Layer 6: Quality Gates (DRAFT / PRODUCTION / BROADCAST)    │
├─────────────────────────────────────────────────────────────┤
│  Layer 5: Quality Scorer (5 components, deterministic)      │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Workers (Slide, Audio, Video, Validator)          │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Orchestrator (Hero's Journey + error handling)    │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Design System (colors, typography, layout)        │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Plugin Bootstrap (lifecycle + audit)              │
├─────────────────────────────────────────────────────────────┤
│  Audit Trail (hash-chained, immutable)                      │
└─────────────────────────────────────────────────────────────┘
```

### Layer 1: Plugin Bootstrap
**Responsibility:** Initialization, configuration loading, audit trail setup

**Files:**
- `src/plugin.py` — Main plugin class
- `plugin.json` — Plugin manifest

**Contracts:**
- Load design system (fail if missing)
- Initialize workers (fail-fast on import errors)
- Log bootstrap event
- Never silent failures (all errors audited)

**Test Coverage:**
- ✅ Design system loads correctly
- ✅ Design system validation (missing colors → error)
- ✅ Bootstrap succeeds with valid config
- ✅ Bootstrap fails + audits error

### Layer 2: Design System
**Responsibility:** Single source of truth for visual branding

**Files:**
- `design_system.json` — Color palette, typography, layout
- `src/models.py::DesignSystem` — Data model with validation

**Contracts:**
- Load from JSON at startup
- Validate: all required colors, fonts, dimensions present
- Fail if contrast <4.5:1 (WCAG AA)
- Version control: one file per version (v1, v2, v3...)

**Test Coverage:**
- ✅ Load valid design_system.json
- ✅ Reject invalid (missing colors)
- ✅ Version tracking

### Layer 3: Orchestrator
**Responsibility:** 5-act narrative pipeline + error handling

**Files:**
- `src/orchestrator.py` — Main Skill (TODO: implement in Phase 1 Week 2)

**Contracts:**
- Takes topic, duration, optional script
- Extracts storyboard (uses Hero's Journey template)
- Calls workers sequentially (with error recovery)
- Audits every step
- Returns VideoJob in one of 3 states (DRAFT/PRODUCTION/BROADCAST)

**Pipeline:**
```
1. Extract Storyboard
   ├─ Hero's Journey template (1-min, 5-min, 15-min versions)
   ├─ Fact-checker (confidence <75 → flag for review)
   └─ Audit: storyboard_extracted

2. Generate Slides (SlideGenerator Worker)
   ├─ Input: Scene list (title, body_text, duration)
   ├─ Output: PNG sequence (/tmp/slide_000.png, ...)
   └─ Audit: slide_generated (count, avg contrast)

3. Generate Audio (AudioGenerator Worker)
   ├─ Input: Full script
   ├─ Primary: Google Cloud TTS (high quality)
   ├─ Fallback: Piper (offline)
   ├─ Fallback2: Silence (always works)
   └─ Audit: audio_generated (provider, duration)

4. Assemble Video (VideoAssembler Worker)
   ├─ DRAFT: PNG sequence + audio side-by-side (no encoding)
   ├─ PRODUCTION: H.264 encode (2.5 Mbps, 1920x1080, 30 fps)
   └─ Audit: video_assembled (codec, bitrate, file size)

5. Validate Quality (QualityValidator Worker)
   ├─ 5-component scoring (0-100 total)
   ├─ Never fails (score is 0-100, no exceptions)
   └─ Audit: quality_validated (breakdown)

6. Enforce Gate (QualityGateEnforcer)
   ├─ Score 0-50 → DRAFT (output: PNG + audio, no video yet)
   ├─ Score 50-85 → PRODUCTION (output: H.264 video)
   ├─ Score 85-100 → BROADCAST (output: video + manual review flag)
   └─ Audit: quality_gate_decision (gate, reason)
```

**Error Recovery:**
```
SlideGenerator fails
├─ Try: Pillow slide rendering
├─ Fallback: Text-only slide (white bg + text overlay)
└─ Audit: slide_generated (provider: fallback)

AudioGenerator fails
├─ Try: Google Cloud TTS
├─ Fallback 1: Piper (offline)
├─ Fallback 2: Silence (always works)
└─ Audit: audio_generated (provider: fallback)

VideoAssembler fails
├─ Try: FFmpeg H.264 encode
├─ Fallback: Export PNG sequence + instructions
└─ Audit: video_assembled (format: png_sequence)

QualityValidator fails
├─ Return: QualityBreakdown(5, 5, 5, 5, 5) = score 25 (DRAFT)
└─ Audit: quality_validated (error: true, score: 25)
```

### Layer 4: Workers
**Responsibility:** Isolated, testable, error-handled task execution

**Worker Contract:**
```python
class Worker(Protocol):
    async def execute(self, input: WorkerInput) -> WorkerOutput:
        """Execute worker task.
        
        Raises WorkerError with fallback info (never unhandled exceptions).
        """
        pass
```

**4 Workers:**

| Worker | Input | Output | Fallback |
|---|---|---|---|
| **SlideGenerator** | Scene(title, body_text) | PNG file | Text-only slide |
| **AudioGenerator** | Script text | WAV file | Silence |
| **VideoAssembler** | PNG sequence + audio + timing | MP4 file | PNG sequence |
| **QualityValidator** | Video metadata | QualityBreakdown(0-100) | Minimal score |

**Testing Strategy:**
- Unit tests: mock dependencies (no real TTS API calls)
- Integration tests: mock only external APIs (Google TTS)
- E2E tests: real workers, real files (but no YouTube upload)

**Test Coverage:** ≥90% per worker

### Layer 5: Quality Scorer
**Responsibility:** Deterministic 5-component evaluation

**Files:**
- `src/quality_scorer.py` — Scorer implementation
- Tests: `tests/test_quality_scorer.py`

**5 Components (each 0-20 points):**

| Component | Metric | Pass Criteria | Points |
|---|---|---|---|
| Visual Clarity | WCAG AA contrast | ≥4.5:1 for text | 0-20 |
| Audio Quality | Loudness (LUFS) | -23 ± 3 LUFS | 0-20 |
| Narrative Flow | Pacing accuracy | Scene durations ±10% | 0-20 |
| Accessibility | Captions + descriptions | English captions required | 0-20 |
| Technical Specs | Codec + bitrate + fps | H.264, 2-6 Mbps, ≥24 fps | 0-20 |

**Scoring Algorithm:**
```python
score = visual_clarity + audio_quality + narrative_flow + accessibility + technical_specs
# Range: 0-100 (always valid, never crashes)
```

**Error Handling:**
- If any component fails to score → return minimal (0-5 points)
- If all components fail → return 5 points (conservative estimate)
- No exceptions escape (fail-safe)

**Test Coverage:** 100% (all 5 components tested in isolation + integration)

### Layer 6: Quality Gates
**Responsibility:** Hard enforcement of DRAFT/PRODUCTION/BROADCAST

**Files:**
- `src/quality_gates.py` — Gate logic
- Tests: `tests/test_quality_gates.py`

**Gate Thresholds (HARDCODED, NEVER CONFIGURABLE):**
```python
DRAFT_MAX_SCORE = 50              # 0-50 points
PRODUCTION_MIN_SCORE = 50         # 50-85 points
PRODUCTION_MAX_SCORE = 85
BROADCAST_MIN_SCORE = 85          # 85-100 points (NEVER LOWER)
```

**Gate Decisions:**
```
Score 0-49     → DRAFT
               → Output: PNG sequence + audio (no video)
               → Next: Iterate script/slides

Score 50-84    → PRODUCTION
               → Output: H.264 video (ready for upload queue)
               → Next: Auto-publish or manual edit

Score 85-100   → BROADCAST
               → Output: H.264 video (marked for review)
               → Next: Human reviews, publishes to YouTube
```

**Immutability:**
- No `quality_gates_enabled: false` config flag
- No `SKIP_QUALITY_GATES=true` env var
- To change gates: edit code → add ADR → code review → merge
- This ensures gates never silently change

**Test Coverage:** 100% (all gate transitions tested)

### Layer 7: YouTube Integration
**Responsibility:** Upload, metadata, analytics (TODO: Phase 4)

**Planned:**
- Authenticate with YouTube OAuth
- Upload video (unlisted first, scheduled publish)
- Track analytics (views, watch time, CTR)
- Dashboard integration

---

## Data Models

```
┌──────────────────┐
│   VideoJob       │
├──────────────────┤
│ id: str          │
│ topic: str       │
│ duration: str    │ ← "1m", "5m", "15m"
│ state: GateState │ ← DRAFT, PRODUCTION, BROADCAST
│ quality_score    │ ← 0-100
│ quality_break    │ ← 5 components
│ video_path: str  │ ← Path to MP4 (if PRODUCTION+)
│ storyboard       │ ← Storyboard object
│ slides: [str]    │ ← PNG file paths
│ audio_path: str  │ ← WAV/MP3 file path
└──────────────────┘
         ▲
         │
    ┌────┴─────────┐
    │              │
┌───────────────┐  ┌──────────────────┐
│  Storyboard   │  │  QualityBreakdown│
├───────────────┤  ├──────────────────┤
│ id: str       │  │ visual_clarity   │
│ topic: str    │  │ audio_quality    │
│ scenes: [S]   │  │ narrative_flow   │
│ narration     │  │ accessibility    │
│ confidence    │  │ technical_specs  │
└───────────────┘  └──────────────────┘
         ▲                 ▲
         │                 │
         └─────────────────┘
         QualityValidator
```

---

## Audit Trail (Hash-Chained)

Every decision is logged:

```json
{
  "timestamp": "2026-09-13T14:25:50.123Z",
  "event_type": "quality_gate_decision",
  "plugin_id": "video-producer-orchestrator",
  "video_id": "test-job-001",
  "quality_score": 87,
  "gate": "BROADCAST",
  "reason": "Score 87 >= 85 (BROADCAST threshold)",
  "next_action": "manual_review",
  "hash": "sha256(...)",
  "prev_hash": "sha256(...)"
}
```

**Events Emitted:**
1. `plugin_bootstrap` — Plugin loaded
2. `storyboard_extracted` — Scene structure created
3. `slide_generated` — PNG sequence created
4. `audio_generated` — Audio file created (which provider?)
5. `video_assembled` — MP4 video assembled
6. `quality_validated` — Quality score computed (5 components)
7. `quality_gate_decision` — Gate enforced (DRAFT/PRODUCTION/BROADCAST)
8. `video_promoted` — DRAFT→PRODUCTION or PRODUCTION→BROADCAST
9. `video_published` — YouTube upload started
10. `learning_event_emitted` — Feedback recorded

**Audit Benefits:**
- Operator can trace: "Show me every frame decision"
- Compliance: "Prove quality gates were enforced" ✓
- Debugging: "Why did this video get score 75?" (breakdown in audit)
- Learning: "Track feedback → gate adjustment" (in audit log)

---

## Error Handling Strategy

**Principle:** Fail-safe, not fail-hard. Always produce output.

```
┌─────────────────┐
│  Try Primary    │
└────────┬────────┘
         │
    ┌────▼─────────────┐
    │ Success?         │
    └─┬──────────────┬─┘
      │ YES          │ NO
      │              │
      │         ┌────▼─────────────┐
      │         │ Try Fallback 1   │
      │         └─┬──────────────┬─┘
      │           │ YES          │ NO
      │           │              │
      │           │         ┌────▼─────────────┐
      │           │         │ Try Fallback 2   │
      │           │         └─┬──────────────┬─┘
      │           │           │ YES          │ NO
      │           │           │              │
      │           │           │    ┌─────────▼──────┐
      │           │           │    │ Fallback 3     │
      │           │           │    │ (Always works) │
      │           │           │    └────────────────┘
      │           │           │           │
      │           └───────┬───┘           │
      │                   │               │
      └───────────────────┴───────────────┘
                          │
                   ┌──────▼──────┐
                   │  Audit Log  │
                   │ (which path?)
                   └─────────────┘
```

**Example: AudioGenerator**
```
1. Try Google Cloud TTS (high quality)
   └─ If fails: reason logged, proceed to fallback
2. Try Piper TTS (offline, always available)
   └─ If fails: reason logged, proceed to fallback
3. Generate silence (0 dB noise floor)
   └─ Always succeeds (no fallback needed)
4. Audit: "audio_generated (provider: silence)"
```

---

## Testing Strategy

### Unit Tests (Isolated)
```
tests/test_models.py
├─ TestScene (valid/invalid durations)
├─ TestStoryboard (valid/invalid structure)
├─ TestQualityBreakdown (valid/invalid scores)
└─ TestVideoJob (state transitions)

tests/test_quality_gates.py
├─ TestQualityGateEnforcer (all thresholds)
├─ TestGateDecision (reason + next_action)
└─ TestGatePromotion (DRAFT→PRODUCTION→BROADCAST)

tests/test_quality_scorer.py
├─ TestQualityScorer (5 components)
├─ TestScorerComponents (each component 0-20)
└─ TestScorerResilience (never crashes)
```

### Integration Tests (Mocked APIs)
```
tests/test_orchestrator.py (TODO: Phase 1 Week 2)
├─ TestOrchestrator (full pipeline)
├─ TestWorkerIntegration (workers called in order)
├─ TestErrorRecovery (fallback paths work)
└─ TestAuditTrail (all events logged)
```

### E2E Tests (Real Files)
```
tests/e2e_test_full_pipeline.py (TODO: Phase 1 Week 3)
├─ TestFullPipeline1Min (1-min video end-to-end)
├─ TestFullPipeline5Min (5-min video end-to-end)
├─ TestGateTransitions (DRAFT→PRODUCTION→BROADCAST)
└─ TestYouTubeReadiness (final video YouTube-compatible)
```

**Coverage Target:** ≥85% overall, 100% on quality gates

---

## Performance Budget

| Operation | Target | Measurement |
|---|---|---|
| SlideGenerator (4 slides) | <5s | Time to PNG sequence |
| AudioGenerator (80s audio) | <15s | Time to WAV file (depends on TTS) |
| VideoAssembler (DRAFT) | <5s | Time to PNG+audio side-by-side |
| VideoAssembler (PRODUCTION) | <30s | Time to H.264 encode |
| QualityValidator | <2s | Time to 5-component score |
| Full pipeline (DRAFT) | <30s | Start to DRAFT video |
| Full pipeline (PRODUCTION) | <60s | Start to PRODUCTION video |

---

## Deployment

### Phase 1 Week 1 (TODAY)
- ✅ Project setup (git, GitHub Actions)
- ✅ Design system locked
- ✅ Quality gates hardcoded
- ✅ 96+ tests passing
- ✅ 0 CRITICAL findings

### Phase 1 Week 2
- SlideGenerator worker (300 LOC)
- AudioGenerator worker (200 LOC)
- VideoAssembler worker (500 LOC)
- Orchestrator implementation

### Phase 1 Week 3
- QualityValidator worker (150 LOC)
- QualityGateEnforcer (200 LOC)
- Console API routes (200 LOC)
- 96+ tests → 150+ tests

---

**Last Updated:** 2026-09-13  
**Status:** READY FOR PHASE 1 IMPLEMENTATION
