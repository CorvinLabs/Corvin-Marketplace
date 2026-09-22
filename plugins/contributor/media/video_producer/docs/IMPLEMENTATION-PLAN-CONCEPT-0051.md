# Implementation Plan: CONCEPT-0051 Content-First Video Verification

**Concept:** CONCEPT-0051 — Content-First Video Verification  
**ADRs:** ADR-0951, ADR-0952  
**Timeline:** 2 weeks (Phases 1–2)  
**Owner:** Video Producer Plugin Team

---

## Phase 1: Tier 1 Content Existence Checks (5 days)

### Deliverables
- `src/verification/audio_inspector_tier1.py` — Audio existence checks
- `src/verification/video_inspector_tier1.py` — Video existence checks
- `src/verification/thresholds.py` — All threshold constants
- `tests/test_content_verification_tier1.py` — 30+ test cases

### Specific Changes

**File: `src/verification/audio_inspector_tier1.py` (NEW)**
```python
class AudioContentInspectorTier1:
    """Detect pure sine tones vs. real audio (500ms, ~95% accuracy)"""
    
    def inspect(self, audio_path: Path) -> AudioVerificationResult:
        """
        Returns:
            - passed: bool
            - reason: str (if failed)
            - frequencies_detected: int
            - mfcc_variance: float
            - amplitude_range: float
            - diagnostic: dict (detailed metrics for debugging)
        """
        # Extract 1-second sample
        audio_sample = librosa.load(audio_path, sr=48000, duration=1.0)
        
        # Check 1: Frequency peak count
        fft = np.abs(np.fft.fft(audio_sample))
        peaks = find_peaks(fft, height=threshold)[0]
        if len(peaks) < 2:  # Threshold from ADR-0952
            return AudioVerificationResult(
                passed=False,
                reason="audio_single_frequency_detected",
                diagnostic={
                    "expected_minimum_peaks": 2,
                    "actual_peaks": len(peaks),
                    "hint": "If this is real content, try: --run-tier-2 or --skip-verification"
                }
            )
        
        # Check 2: MFCC variance with hysteresis
        mfcc = librosa.feature.mfcc(y=audio_sample, sr=48000)
        mfcc_var = np.var(mfcc)
        if mfcc_var < 0.14:  # FAIL threshold
            return AudioVerificationResult(
                passed=False,
                reason="audio_mfcc_variance_too_low",
                diagnostic={
                    "expected_minimum": 0.16,  # Pass threshold
                    "actual_value": float(mfcc_var),
                    "manual_review_range": [0.14, 0.16],
                    "hint": "If this is real content, try: --run-tier-2"
                }
            )
        elif 0.14 <= mfcc_var <= 0.16:
            # Manual review zone
            return AudioVerificationResult(
                passed=False,
                reason="audio_mfcc_variance_in_manual_review_range",
                diagnostic={
                    "actual_value": float(mfcc_var),
                    "manual_review_range": [0.14, 0.16],
                    "hint": "Value is borderline. Try --run-tier-2 for thorough analysis"
                }
            )
        
        # Check 3: Amplitude range with hysteresis
        amp_range = np.max(np.abs(audio_sample)) - np.min(np.abs(audio_sample))
        if amp_range < 0.25:  # FAIL threshold
            return AudioVerificationResult(
                passed=False,
                reason="audio_amplitude_range_too_narrow",
                diagnostic={
                    "expected_minimum": 0.3,
                    "actual_value": float(amp_range),
                    "hint": "Audio appears silent or is test tone"
                }
            )
        
        return AudioVerificationResult(
            passed=True,
            frequencies_detected=len(peaks),
            mfcc_variance=float(mfcc_var),
            amplitude_range=float(amp_range)
        )
```

**File: `src/verification/video_inspector_tier1.py` (NEW)**
```python
class VideoContentInspectorTier1:
    """Detect solid backgrounds vs. real content (300ms, ~95% accuracy)"""
    
    def inspect(self, video_path: Path) -> VideoVerificationResult:
        """
        Returns:
            - passed: bool
            - reason: str (if failed)
            - color_variance: float
            - unique_colors: int
            - temporal_variance: float
        """
        # Extract 3 frames (start, middle, end)
        frames = [
            extract_frame(video_path, 0),
            extract_frame(video_path, total_frames // 2),
            extract_frame(video_path, total_frames - 1)
        ]
        
        # Check 1: Color variance across frames
        color_variance = np.var([frame.mean() for frame in frames])
        if color_variance < 0.15:  # Threshold from ADR-0952
            return VideoVerificationResult(
                passed=False,
                reason="Video color variance too low — appears to be solid background"
            )
        
        # Check 2: Unique colors in first frame
        unique_colors = len(np.unique(frames[0].reshape(-1, 3)))
        if unique_colors < 20:
            return VideoVerificationResult(
                passed=False,
                reason="Video has too few unique colors — appears to be solid background"
            )
        
        # Check 3: Temporal variance between frames
        temporal_diff = np.mean(np.abs(frames[0].astype(float) - frames[1].astype(float)))
        if temporal_diff < 0.05:  # Threshold from ADR-0952
            return VideoVerificationResult(
                passed=False,
                reason="Video frames are nearly identical — no animation or scene change"
            )
        
        return VideoVerificationResult(
            passed=True,
            color_variance=float(color_variance),
            unique_colors=int(unique_colors),
            temporal_variance=float(temporal_diff)
        )
```

**File: `src/verification/thresholds.py` (NEW)**
```python
# Audio thresholds (Tier 1)
AUDIO_TIER1_MIN_FREQUENCIES = 2
AUDIO_TIER1_MIN_MFCC_VARIANCE = 0.15
AUDIO_TIER1_MIN_AMPLITUDE_RANGE = 0.3

# Video thresholds (Tier 1)
VIDEO_TIER1_MIN_COLOR_VARIANCE = 0.15
VIDEO_TIER1_MIN_UNIQUE_COLORS = 20
VIDEO_TIER1_MIN_TEMPORAL_VARIANCE = 0.05

# Audit trail severity levels
VERIFICATION_FAIL_SEVERITY = "ERROR"
VERIFICATION_PASS_SEVERITY = "INFO"
```

### Tests
**`tests/test_content_verification_tier1.py`:**
```python
def test_audio_pure_sine_rejected():
    """Pure 440Hz sine wave should fail Tier 1"""
    audio_path = create_sine_tone(freq=440, duration=1.0)
    result = AudioContentInspectorTier1().inspect(audio_path)
    assert not result.passed
    assert "single_frequency" in result.reason

def test_audio_speech_passed():
    """Real speech should pass Tier 1"""
    # Use espeak or TTS to generate real audio
    audio_path = generate_speech("Hello world")
    result = AudioContentInspectorTier1().inspect(audio_path)
    assert result.passed

def test_video_solid_blue_rejected():
    """Solid blue background should fail Tier 1"""
    video_path = create_solid_color_video(color=(0, 0, 27), duration=1.0)
    result = VideoContentInspectorTier1().inspect(video_path)
    assert not result.passed
    assert "solid background" in result.reason

def test_video_with_text_passed():
    """Video with text overlay should pass Tier 1"""
    video_path = create_video_with_text("Hello World")
    result = VideoContentInspectorTier1().inspect(video_path)
    assert result.passed
    # Additional tests: 20+ total
```

**Real File E2E Test (uses actual broken videos from incident):**
```python
# In: tests/e2e/test_empty_videos_rejected.py

def test_real_sine_tone_from_incident_rejected():
    """
    Use actual broken video from 2026-09-22 incident
    
    This test verifies that the exact sine-tone audio that broke production
    is now REJECTED by Tier 1 verification.
    """
    # Path to real broken file from incident
    real_sine_path = Path(__file__).parent.parent.parent / \
        "Corvin-Videos/blender_20260922_001652/steps/narration.wav"
    
    if real_sine_path.exists():
        result = AudioContentInspectorTier1().inspect(real_sine_path)
        
        # MUST FAIL
        assert not result.passed, \
            f"Incident audio should fail but passed: {result.diagnostic}"
        
        # MUST show why
        assert "single_frequency" in result.reason or \
               "mfcc_variance_too_low" in result.reason, \
               f"Rejection reason not clear: {result.reason}"
        
        # MUST have diagnostic info
        assert result.diagnostic is not None
        assert "expected" in result.diagnostic or "actual" in result.diagnostic
    else:
        pytest.skip("Incident video files not available in test environment")


def test_real_solid_blue_from_incident_rejected():
    """
    Use actual broken video from 2026-09-22 incident
    
    This test verifies that the exact solid-blue video that broke production
    is now REJECTED by Tier 1 verification.
    """
    # Path to real broken file from incident
    real_video_path = Path(__file__).parent.parent.parent / \
        "Corvin-Videos/blender_20260922_001652/steps/layers.mp4"
    
    if real_video_path.exists():
        result = VideoContentInspectorTier1().inspect(real_video_path)
        
        # MUST FAIL
        assert not result.passed, \
            f"Incident video should fail but passed: {result.diagnostic}"
        
        # MUST show why
        assert "solid background" in result.reason or \
               "color_variance_too_low" in result.reason or \
               "unique_colors_too_few" in result.reason, \
               f"Rejection reason not clear: {result.reason}"
        
        # MUST have diagnostic info
        assert result.diagnostic is not None
    else:
        pytest.skip("Incident video files not available in test environment")
```

### Deliverable Proof
- [ ] All tests passing: `pytest tests/test_content_verification_tier1.py -v`
- [ ] Code coverage > 90%
- [ ] Audit integration wired (verify audit events logged)

---

## Phase 2: Tier 2 + Integration (7 days)

### Deliverables
- `src/verification/audio_inspector_tier2.py` — Spectral analysis
- `src/verification/video_inspector_tier2.py` — Feature detection
- `src/verification/orchestrator.py` — Tier routing logic
- `src/verification/audit_integration.py` — Log to audit trail
- `tests/test_content_verification_tier2.py` — 30+ test cases

### Integration Points

**ADR-0232 (Audit Trail):**
```python
# In orchestrator.py
def verify_with_audit(video_path: Path, tier: int = 1) -> bool:
    result = run_verification_tier(video_path, tier)
    
    emit_audit_event({
        "event_type": "video_content_verification",
        "tier": tier,
        "passed": result.passed,
        "reason": result.reason,
        "metrics": result.metrics
    })
    
    return result.passed
```

**ADR-0314 (Learning Loop):**
```python
# In orchestrator.py
def handle_verification_failure(result: VerificationResult):
    if not result.passed:
        emit_learning_event({
            "event_type": "content_verification_failed",
            "failure_type": result.reason,
            "recommendation": "regenerate_with_real_content"
        })
```

### Deliverable Proof
- [ ] Tier 1 + Tier 2 chaining works
- [ ] Audit events logged for every verification
- [ ] Learning events emitted on failure
- [ ] All tests passing

---

## Phase 3: Tier 3 + Documentation (Optional, 5 days)

### Deliverables
- `src/verification/audio_inspector_tier3.py` — Speech detection (Whisper)
- `src/verification/video_inspector_tier3.py` — Object detection (YOLO)
- `docs/VERIFICATION-GUIDE.md` — Operator documentation
- `docs/TROUBLESHOOTING.md` — Common failures

---

## Testing Strategy

### Unit Tests (Phase 1–2)
```
tests/
├── test_content_verification_tier1.py    (30+ tests)
├── test_content_verification_tier2.py    (30+ tests)
├── test_audio_inspector_tier1.py
├── test_video_inspector_tier1.py
└── test_audit_integration.py
```

### E2E Tests
```
tests/e2e/
├── test_empty_videos_rejected.py         # Sine tones + solid color
├── test_real_content_accepted.py         # Speech + graphics
└── test_audit_trail_logging.py
```

### Adversarial Tests
```
tests/adversarial/
├── test_almost_empty_audio.py            # Very quiet speech
├── test_almost_empty_video.py            # Minimal color variance
└── test_edge_cases.py                    # Silence, black frames, etc.
```

---

## Success Criteria

✅ **Phase 1 Complete:**
- Tier 1 audio/video inspectors written and tested
- 60+ unit tests, all passing
- Catches pure sine tones and solid colors
- 500ms performance budget met

✅ **Phase 2 Complete:**
- Tier 2 implemented and integrated
- Audit trail logs every verification
- Learning loop receives failure signals
- 90%+ test coverage

✅ **Phase 3 (Optional):**
- Tier 3 definitive proof working
- Operator documentation complete
- Troubleshooting guide available

---

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| False positives (reject valid videos) | Tier 1 thresholds calibrated on real data; operator `--allow-empty` override |
| Performance impact | Tier 1 only by default (500ms); Tier 2/3 optional |
| Dependency issues (Librosa, OpenCV) | Already required by Maestro orchestrator |
| Audit bloat (too many events) | Log only failures in Tier 1; use sampling in Tier 3 |

---

## Rollout Plan

**Week 1:** Phase 1 complete, Tier 1 deployed  
**Week 2:** Phase 2 complete, Tier 1+2 deployed  
**Optional:** Phase 3 (Tier 3 on-demand)

**Monitoring:**
- Track Tier 1 rejection rate (expect <5% of real videos)
- Monitor audit event volume
- Survey operator feedback

