---
id: ADR-0701
status: proposed
supersedes: []
depends_on: [ADR-0702, ADR-0703]
related: [CONCEPT-0041, ADR-0702, ADR-0703]
commits: []
paths:
  - "core/skills/video_producer_skill/color_processor.py"
  - "core/skills/video_producer_skill/tests/test_color_processing.py"
docs:
  - "docs/video-producer/color-processing.md"
---

# ADR-0701 — Video Producer Color Processing Pipeline

**Status:** Proposed  
**Date:** 2026-09-13  
**Deciders:** Claude Haiku 4.5

## Summary

Standardizes color space handling across all video scenes through a fail-closed pipeline:
1. **Input Detection** — infer colorspace from EXIF/content
2. **Normalization** — equalize brightness/contrast across scenes
3. **Optional Grading** — apply user-selected color preset (warm/cool/vintage)
4. **Output Conversion** — convert to target broadcast colorspace (BT.709)

**Key Invariants:**
- Fail-closed on colorspace conversion failure
- Histogram-matching for frame-to-frame consistency
- User-selectable grading presets
- Audit trail for every color decision

## Decision

Implement **ColorProcessorSkill** with 4-stage pipeline:

### Pipeline

1. **Input Colorspace Detection**
   - Check EXIF metadata (ColorSpace, ColorSpaceData tags)
   - Infer from histogram analysis if metadata absent
   - Supported spaces: sRGB, Adobe RGB, BT.709, DCI-P3, BT.2020
   - Fallback: assume sRGB if detection fails

2. **Conversion to Working Space**
   - Convert all inputs to sRGB (default) or BT.709 (video)
   - Use libvips/ImageMagick for color-accurate conversion
   - Fail-closed: if conversion fails, reject scene

3. **Normalization (Histogram Matching)**
   - Analyze histogram of current + previous scene
   - Adjust brightness/contrast to match previous scene's luminance
   - Avoid jarring transitions between scenes
   - Optional: linear interpolation fade if mismatch >10%

4. **Optional Grading (LUT Application)**
   - Load user-selected LUT file (if provided)
   - Apply color grading (warm, cool, vintage, cinematic)
   - Default: no grading (neutral pass-through)

5. **Output Conversion**
   - Convert from working space to output colorspace
   - Target: BT.709 (standard video color space)
   - Fallback to sRGB if BT.709 not supported

### Configuration

```yaml
color:
  input_detection: auto       # "auto", "sRGB", "p3", "bt709", "bt2020"
  working_space: sRGB         # "sRGB", "BT.709"
  normalization:
    enabled: true
    method: histogram_matching  # "histogram_matching", "curve_fitting"
    target_luminance: 50      # 0–100, target average brightness
    tolerance: 0.1            # 10%, allow deviation before adjustment
  grading:
    preset: none              # "none", "warm", "cool", "vintage", "cinematic"
    strength: 1.0             # 0–1, intensity of grading
    custom_lut: null          # path to custom LUT file (3D color cube)
  output_colorspace: BT.709
  output_profile: baseline
```

### Data Model

```python
@dataclass(frozen=True)
class ColorProcessingResult:
    scene_id: str
    input_colorspace: str
    normalized_luminance: float  # 0–100
    grading_applied: str  # "none", "warm", "cool", etc.
    output_colorspace: str
    status: Literal["success", "warn", "fail"]
    warnings: List[str]  # e.g., ["histogram_clipping_detected"]
    timestamp: datetime
```

### Implementation Outline

```python
class ColorProcessorSkill:
    async def process_scene_colors(
        self,
        scene_image: Path,
        scene_metadata: dict,
        previous_scene_luminance: float = None,
        config: ColorConfig = None
    ) -> ColorProcessingResult:
        """Process scene through color pipeline."""
        
        # 1. Detect input colorspace
        detected_space = await self._detect_colorspace(scene_image)
        
        # 2. Convert to working space
        working_image = await self._convert_to_working_space(
            scene_image,
            detected_space,
            config.working_space
        )
        
        # 3. Normalize (histogram match)
        if config.normalization.enabled and previous_scene_luminance:
            normalized_image, new_luminance = await self._normalize_histogram(
                working_image,
                target_luminance=previous_scene_luminance,
                tolerance=config.normalization.tolerance
            )
        
        # 4. Apply grading (optional LUT)
        if config.grading.preset != "none":
            graded_image = await self._apply_grading(
                normalized_image,
                config.grading.preset,
                config.grading.strength
            )
        
        # 5. Convert to output colorspace
        final_image = await self._convert_to_output(
            graded_image or normalized_image,
            config.output_colorspace
        )
        
        # Save and return result
        await self._save_processed_image(final_image, scene_image)
        
        return ColorProcessingResult(...)
```

### Testing

- `test_srgb_to_bt709_conversion` → successful conversion
- `test_histogram_matching_consistency` → frame-to-frame luma difference <5%
- `test_grading_lut_application` → colors shifted as expected
- `test_colorspace_conversion_failure` → fail-closed (reject scene)

### LDD Metrics

| Metric | Target |
|---|---|
| Color consistency (frame-to-frame) | <10% chrominance variance |
| Grading quality (subjective) | >0.8 (user satisfaction) |
| Processing latency | <2s per scene |

## Consequences

- ✅ Consistent color across scenes
- ✅ User-controllable grading
- ✅ FAIL-CLOSED design (invalid colors rejected)
- ❌ +2s latency per scene (colorspace conversion + histogram analysis)

## Related

- ADR-0703 (Adaptive Encoding) — color profile impacts codec selection
- ADR-0703 (Feedback Loop) — user adjusts grading presets
