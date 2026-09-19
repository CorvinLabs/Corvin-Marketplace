# Phase 1 Implementation — Video Quality Enhancement
## Deliverables, Test Plan, Integration Checklist

**Status:** Implementation Ready  
**Duration:** Weeks 1–2  
**Effort:** ~1200 LoC + 35 tests  
**Owner:** Video Producer Plugin Team

---

## Deliverable 1: InputValidatorSkill

### File Structure
```
src/
├── input_validator.py (400 LoC)
│   ├─ InputValidatorSkill class
│   ├─ AssetValidationResult dataclass
│   ├─ 8 validation check methods
│   └─ audit_backend integration
├── tests/
│   └─ test_input_validation.py (200 LoC, 15 tests)
│       ├─ test_file_integrity_missing → FAIL
│       ├─ test_resolution_too_low → FAIL
│       ├─ test_contradiction_major → FAIL
│       ├─ test_valid_screenshot_passes → PASS
│       └─ ... (12 more)
└── fixtures/
    └─ test_assets/ (sample images for testing)
```

### Core Implementation
```python
class InputValidatorSkill:
    """8-point validation pipeline for screenshot assets."""
    
    async def validate_asset(
        self,
        asset_path: str,
        scene_metadata: dict,
        job_context: dict
    ) -> AssetValidationResult:
        """
        Validates screenshot before rendering.
        
        Returns: AssetValidationResult (pass/warn/fail status)
        """
        # See ADR-0699 for full implementation details
        ...
```

### Integration Points
1. **Called by:** VideoProducerSkill (Maestro) after LLM screenshot generation
2. **Input:** Asset path + scene metadata
3. **Output:** AssetValidationResult (audit event + confidence score)
4. **Audit:** Every validation logged (ADR-0314 event stream)

### Test Checklist
- [ ] File integrity checks (missing, corrupted, oversized)
- [ ] Resolution validation (720p–4K range)
- [ ] Colorspace detection (sRGB, BT.709, P3)
- [ ] Contradiction detection (Vision API calls)
- [ ] Artifact detection (compression, aliasing)
- [ ] Layout validation (UI elements, text readability)
- [ ] Scene-specific checks (title, narration, screenshot, animation)
- [ ] Consistency check (vs. previous scene)
- [ ] E2E: full pipeline passes valid screenshot
- [ ] E2E: full pipeline rejects invalid screenshot

---

## Deliverable 2: Baseline Adaptive Encoding

### File Structure
```
src/
├── encoder.py (400 LoC)
│   ├─ AdaptiveEncoderSkill class
│   ├─ EncodingProfile dataclass
│   ├─ Codec/resolution/bitrate selection logic
│   └─ Fallback mechanism (adaptive retry)
├── encoding_profiles.yaml (150 LoC)
│   ├─ youtube preset
│   ├─ linkedin preset
│   ├─ archive preset
│   ├─ presentation preset
│   └─ custom template
├── tests/
│   └─ test_adaptive_encoding.py (150 LoC, 12 tests)
│       ├─ test_h264_chosen_for_linkedin
│       ├─ test_h265_chosen_for_archive
│       ├─ test_bitrate_adjusted_for_complexity
│       ├─ test_fallback_codec_on_encode_failure
│       └─ ... (8 more)
└── fixtures/
    └─ sample_scenes/ (test video segments)
```

### Core Implementation
```python
class AdaptiveEncoderSkill:
    """Scene-adaptive codec & bitrate selection."""
    
    def choose_encoding(
        self,
        scene: Scene,
        job_context: dict,
        validation_result: AssetValidationResult,
        quality_preset: str = "youtube"
    ) -> EncodingProfile:
        """
        Determines encoding params per scene.
        
        See ADR-0700 for decision matrix.
        """
        ...
```

### YAML Config (encoding_profiles.yaml)
```yaml
encoding_profiles:
  youtube:
    codec_priority: [h264, h265]
    resolution:
      default: 1080p
      range: [1080p, 1440p]
    bitrate:
      target: 8-12 Mbps
      min: 4 Mbps
      max: 12 Mbps
    scene_overrides:
      title: { bitrate: "4-6 Mbps", codec: h264 }
      narration: { bitrate: "5-8 Mbps", codec: h264 }
      screenshot: { bitrate: "8-12 Mbps", codec: h264 }
      animation: { bitrate: "6-10 Mbps", codec: h265 }
  # ... (linkedin, archive, presentation presets)
```

### Integration Points
1. **Called by:** VideoProducerSkill after InputValidator passes
2. **Config loaded from:** `encoding_profiles.yaml` (user-selectable preset)
3. **Outputs:** EncodingProfile (codec, resolution, bitrate, FFmpeg args)
4. **FFmpeg integration:** Generate native FFmpeg command

### Test Checklist
- [ ] Codec selection (H.264 default, H.265 for archive)
- [ ] Resolution selection (per preset range)
- [ ] Bitrate selection (scene-adaptive)
- [ ] FFmpeg preset (fast/medium/slow)
- [ ] Fallback sequence (bitrate ↓ → codec change → resolution ↓)
- [ ] YAML preset loading (youtube, linkedin, archive, presentation)
- [ ] Scene-specific overrides (title/narration/screenshot/animation)
- [ ] E2E: encoding completes, output valid
- [ ] E2E: fallback works on encode failure
- [ ] Audit trail: encoding decision logged

---

## Deliverable 3: Color Space Detection

### File Structure
```
src/
├── color_processor.py (250 LoC)
│   ├─ ColorProcessorSkill class
│   ├─ ColorProcessingResult dataclass
│   ├─ Colorspace detection methods
│   └─ Conversion logic (EXIF, histogram)
├── tests/
│   └─ test_color_processing.py (100 LoC, 8 tests)
│       ├─ test_srgb_detection_from_exif
│       ├─ test_bt709_histogram_inference
│       ├─ test_conversion_to_working_space
│       ├─ test_fail_closed_on_conversion_error
│       └─ ... (4 more)
└── fixtures/
    └─ color_test_images/ (sRGB, BT.709, P3 samples)
```

### Core Implementation
```python
class ColorProcessorSkill:
    """Detect and normalize colorspace."""
    
    async def detect_colorspace(self, image_path: str) -> str:
        """Detect from EXIF or infer from histogram."""
        # Returns: "sRGB", "BT.709", "P3", "BT.2020", or fallback "sRGB"
        ...
    
    async def convert_to_working_space(
        self,
        image_path: str,
        source_space: str,
        target_space: str
    ) -> Path:
        """Convert image to working colorspace."""
        # Fail-closed: if conversion fails, raise exception
        ...
```

### Phase 1 Scope
- Colorspace **detection** (EXIF, histogram)
- **Conversion to working space** (sRGB)
- **Fail-closed design** (invalid → reject)

### Phase 2+ Scope (not yet)
- Histogram matching (normalization)
- Color grading (LUT application)
- Output colorspace conversion (BT.709)

### Test Checklist
- [ ] EXIF colorspace detection
- [ ] Histogram-based inference (fallback)
- [ ] Conversion to sRGB
- [ ] Conversion to BT.709
- [ ] Fail-closed on conversion error
- [ ] Unsupported colorspace handling
- [ ] E2E: detect + convert pipeline

---

## Deliverable 4: Console Quality Metrics Panel

### File Structure
```
web-next/src/
├── components/VideoQualityMetrics.tsx (150 LoC)
│   ├─ Job quality summary card
│   ├─ Per-scene metrics grid
│   ├─ Validation status display
│   └─ Encoding decision breakdown
├── hooks/useVideoQualityMetrics.ts (50 LoC)
│   └─ Query hook for job metrics endpoint
└── tests/
    └─ VideoQualityMetrics.test.tsx (50 LoC, 5 tests)
        ├─ test_panel_renders_job_metrics
        ├─ test_validation_status_shown
        ├─ test_encoding_params_displayed
        └─ ...
```

### UI Layout
```
┌─ Video Quality Metrics ─────────────┐
│                                     │
│ Job: job_abc123                     │
│ Status: ✓ Complete (4m 32s)         │
│                                     │
│ Input Validation:   8/8 ✓ (100%)   │
│ Encoding:          H.264/1080p     │
│ Bitrate:           7.2 Mbps        │
│ File Size:         27 MB           │
│ Color Space:       BT.709          │
│ Prediction Conf:   0.87            │
│                                     │
│ Per-Scene Status:                   │
│ ┌─────────┬─────────┬─────────┐   │
│ │ Scene 1 │ Scene 2 │ Scene 3 │   │
│ │ ✓ Pass  │ ✓ Pass  │ ⚠ Warn  │   │
│ └─────────┴─────────┴─────────┘   │
│                                     │
└─────────────────────────────────────┘
```

### API Endpoint
```
GET /v1/console/video/jobs/{job_id}/quality-metrics

Response:
{
  "job_id": "job_abc123",
  "status": "complete",
  "validation": {
    "passed": 8,
    "warned": 0,
    "failed": 0
  },
  "encoding": {
    "codec": "h264",
    "resolution": "1080p",
    "bitrate": "7200k"
  },
  "color": {
    "input_space": "sRGB",
    "output_space": "BT.709"
  },
  "per_scene": [
    {
      "scene_id": "s1",
      "validation_status": "pass",
      "validation_confidence": 0.95,
      "encoding_codec": "h264",
      "encoding_bitrate": "6000k"
    },
    ...
  ]
}
```

### Integration Points
1. **Called from:** VideoProducerPage (existing component)
2. **Backend:** `/v1/console/video/jobs/{job_id}/quality-metrics` endpoint
3. **Data source:** Job metadata + validation/encoding audit events

---

## Integration Checklist

### Backend Integration
- [ ] Import InputValidatorSkill into VideoProducerSkill (Maestro)
- [ ] Call validator after LLM screenshot generation
- [ ] Handle validation result (pass/warn/fail)
- [ ] Emit audit event for each validation
- [ ] Wire encoder selection into scene rendering
- [ ] Load encoding_profiles.yaml from plugin config
- [ ] Build FFmpeg commands from EncodingProfile
- [ ] Emit audit event for each encoding decision

### Console Integration
- [ ] Add VideoQualityMetrics component to job detail page
- [ ] Implement `/quality-metrics` API endpoint
- [ ] Wire job metadata to metrics panel
- [ ] Display validation status per scene
- [ ] Display encoding parameters per scene

### Testing Integration
- [ ] Run all unit tests (`pytest tests/`)
- [ ] Run E2E tests (VideoProducerSkill with InputValidator)
- [ ] Manual testing: create job, validate metrics panel displays correctly
- [ ] Audit trail verification: all events present

---

## Test Execution Plan

### Phase 1 Test Suite (35 tests, ~45 min runtime)

**Unit Tests (20 tests):**
```bash
pytest src/tests/test_input_validation.py -v       # 8 tests, 2 min
pytest src/tests/test_adaptive_encoding.py -v      # 10 tests, 3 min
pytest src/tests/test_color_processing.py -v       # 8 tests, 2 min
```

**E2E Tests (15 tests):**
```bash
pytest tests/e2e/test_quality_pipeline.py -v       # 15 tests, 30 min
  └─ test_input_validation_end_to_end
  └─ test_encoding_selection_end_to_end
  └─ test_color_detection_end_to_end
  └─ test_console_metrics_panel_loads
  └─ ... (11 more)
```

**Coverage Target:** >85% (critical paths 100%)

---

## Rollout Plan

### Week 1
- **Day 1–2:** InputValidatorSkill implementation + tests
- **Day 3–4:** AdaptiveEncoderSkill + encoding_profiles.yaml
- **Day 5:** Color detection + console panel + integration

### Week 2
- **Day 1–2:** E2E testing + bug fixes
- **Day 3:** Code review + documentation
- **Day 4:** Manual testing (production-like environment)
- **Day 5:** Merge to main, prepare Phase 2

### Success Criteria
- ✅ All 35 tests green
- ✅ Code review approved
- ✅ Manual testing passed (quality metrics visible in console)
- ✅ Audit trail verified (all events logged)
- ✅ Documentation complete

---

## Known Dependencies & Constraints

### External Dependencies
- **Vision API** (Claude's vision for contradiction detection) — requires API key
- **FFmpeg** (video encoding) — must be installed on host
- **libvips/ImageMagick** (colorspace conversion) — optional but recommended

### Performance Constraints
- Validation latency: <5s per asset (timeout at 10s)
- Colorspace detection: <2s per asset
- Encoding selection: <1s per scene

### Configuration
- Encoding presets loaded from `encoding_profiles.yaml`
- Audit backend must be initialized before validation runs (fail-closed)

---

## Review Checklist for Implementer

Before merging Phase 1:
- [ ] All tests green (35/35)
- [ ] Code coverage >85%
- [ ] Audit events verified (sample job logged correctly)
- [ ] Console panel displays metrics (manual test)
- [ ] No breaking changes to existing VideoProducerSkill API
- [ ] Documentation complete (ADRs + this file)
- [ ] Commit message includes ADR references

---

**Next Phase:** ADR-0703 (Per-Scene Feedback & Learning Loop, Weeks 3–4)
