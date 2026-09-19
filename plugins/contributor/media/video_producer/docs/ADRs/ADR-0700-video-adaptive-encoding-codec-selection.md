---
id: ADR-0703
status: proposed
supersedes: []
depends_on: [ADR-0692, ADR-0314]
related: [CONCEPT-0041, ADR-0702, ADR-0701, ADR-0702, ADR-0703]
commits: []
paths:
  - "core/skills/video_producer_skill/encoder.py"
  - "core/skills/video_producer_skill/encoding_profiles.yaml"
  - "core/skills/video_producer_skill/tests/test_adaptive_encoding.py"
docs:
  - "docs/video-producer/adaptive-encoding.md"
---

# ADR-0703 — Adaptive Encoding & Codec Selection

**Status:** Proposed  
**Date:** 2026-09-13  
**Deciders:** Claude Haiku 4.5, Shumway

## Context

The current Video Producer Skill uses hardcoded FFmpeg defaults for all scenes:
```bash
ffmpeg -c:v libx264 -crf 23 -preset medium ...
```

This results in:
- **Suboptimal quality/file-size trade-offs** (CRF 23 is too aggressive for some scenes, too conservative for others)
- **Platform incompatibility** (H.265 not supported on older browsers)
- **No bitrate targets** (file size varies wildly; YouTube recommendations ignored)
- **Wasted encoding time** (H.264 libx264 is CPU-intensive, no GPU acceleration considered)

Different scene types need different encoding strategies:
- **Title scene:** high visual quality, static image → H.265 is efficient
- **Narration scene:** balanced quality, low motion → H.264 baseline (compatibility)
- **Screenshot scene:** high detail, may need upscaling → higher bitrate
- **Animation scene:** synthetic content, compresses well → H.265 or low bitrate H.264

### Current State
- Single FFmpeg command for all scenes (H.264, CRF 23, 1280×720)
- No quality presets (YouTube vs. LinkedIn vs. Archive)
- No codec choice logic (always H.264)
- No bitrate targets

## Decision

Implement **Scene-Adaptive Encoding** with three load-bearing principles:

1. **Immutable Baseline Constraints** (never weaken)
   - Min bitrate: 2 Mbps (YouTube recommendation)
   - Max bitrate: 25 Mbps (archive quality)
   - Min resolution: 720p (quality floor)
   - Max resolution: 4K (platform compatibility)

2. **Learnable Encoding Parameters** (tuned via ADR-0314 feedback loop)
   - Per-scene-type bitrate multiplier (title/narration/screenshot/animation)
   - Codec preference (H.264 for broad compatibility, H.265 for quality)
   - FFmpeg preset (fast/medium/slow tradeoff)

3. **Quality Presets** (operator-selectable)
   - YouTube (8–12 Mbps, 1080p–1440p, broad compatibility)
   - LinkedIn (8 Mbps max, 1080p, strict H.264)
   - Archive (15–25 Mbps, 2160p, H.265 preferred)
   - Presentation (4–8 Mbps, 1080p, smallest size)
   - Custom (user-defined profile)

### Encoding Decision Matrix

**Per Scene Type:**

| Scene Type | Preset | Codec | Resolution | Target Bitrate | CRF (H.264) / QP (H.265) | Preset | Why |
|---|---|---|---|---|---|---|---|
| **Title** | YouTube | H.264 | 1080p | 4–6 Mbps | 23–25 | medium | High visual quality, static → H.264 acceptable, medium preset balanced |
| | Archive | H.265 | 2160p | 12–16 Mbps | 20–22 | slow | Best compression, 4K sharp |
| **Narration** | YouTube | H.264 | 1080p–1440p | 5–8 Mbps | 22–24 | medium | Most common scene, balanced quality |
| | Archive | H.265 | 1440p–2160p | 10–15 Mbps | 20–23 | medium | Better compression than H.264 |
| **Screenshot** | YouTube | H.264 | 1440p | 8–12 Mbps | 20–22 | medium | High detail needed, higher bitrate |
| | Archive | H.265 | 2160p | 15–20 Mbps | 18–21 | slow | Max quality for detailed content |
| **Animation** | YouTube | H.265 | 1080p–1440p | 6–10 Mbps | 21–23 | fast | Synthetic content, H.265 efficient, can use fast preset |
| | Archive | H.265 | 2160p | 12–18 Mbps | 19–22 | medium | Synthetic → good compression |
| **Composite** | YouTube | H.264 | 1080p–1440p | 6–10 Mbps | 22–24 | medium | Mixed content, H.264 safest |
| | Archive | H.264 | 1440p–2160p | 12–18 Mbps | 20–23 | slow | Stick with H.264 for safety |

### Quality Presets (YAML Config)

```yaml
# File: core/skills/video_producer_skill/encoding_profiles.yaml

encoding_profiles:
  youtube:
    description: "Optimized for YouTube (8–12 Mbps, 1080p–1440p)"
    target_platform: "youtube"
    codec_priority: [h264, h265]  # try H.264 first (compatibility), fallback H.265
    resolution:
      default: 1080p
      range: [1080p, 1440p]
      upscale_threshold: 1.3x  # upscale if source <720p
    bitrate:
      target: 8-12 Mbps
      min: 4 Mbps
      max: 12 Mbps
    ffmpeg_preset: medium
    scene_overrides:
      title: { bitrate: "4-6 Mbps", codec: h264, preset: medium }
      narration: { bitrate: "5-8 Mbps", codec: h264, preset: medium }
      screenshot: { bitrate: "8-12 Mbps", codec: h264, preset: medium }
      animation: { bitrate: "6-10 Mbps", codec: h265, preset: fast }
    container: "mp4"
    audio: { codec: aac, bitrate: 128k, sample_rate: 48000 }
    color_profile: BT.709
    profile: baseline  # wide compatibility
    level: 4.2

  linkedin:
    description: "LinkedIn standard (8 Mbps, 1080p, strict H.264)"
    target_platform: "linkedin"
    codec_priority: [h264]  # LinkedIn prefers H.264
    resolution:
      default: 1080p
      range: [720p, 1080p]
    bitrate:
      target: 8 Mbps
      min: 2 Mbps
      max: 8 Mbps  # LinkedIn limit
    ffmpeg_preset: medium
    scene_overrides:
      all: { codec: h264, preset: medium, crf: 23 }
    container: "mp4"
    audio: { codec: aac, bitrate: 128k }
    color_profile: BT.709
    profile: baseline
    level: 4.1

  archive:
    description: "High quality archive (15–25 Mbps, 2160p, H.265 preferred)"
    target_platform: "archive"
    codec_priority: [h265, h264]
    resolution:
      default: 1440p
      range: [1440p, 2160p]
      upscale_threshold: 1.5x
    bitrate:
      target: 15-25 Mbps
      min: 8 Mbps
      max: 25 Mbps
    ffmpeg_preset: slow  # slower = better compression
    scene_overrides:
      title: { bitrate: "12-16 Mbps", codec: h265, preset: slow }
      narration: { bitrate: "10-15 Mbps", codec: h265, preset: medium }
      screenshot: { bitrate: "15-20 Mbps", codec: h265, preset: slow }
      animation: { bitrate: "12-18 Mbps", codec: h265, preset: medium }
    container: "mp4"
    audio: { codec: aac, bitrate: 192k, sample_rate: 48000 }
    color_profile: BT.2020  # wider gamut
    profile: main  # H.265 profile
    level: 5.1

  presentation:
    description: "Minimal size (4–8 Mbps, 1080p, balanced)"
    target_platform: "presentation"
    codec_priority: [h264, h265]
    resolution:
      default: 1080p
      range: [720p, 1080p]
    bitrate:
      target: 4-8 Mbps
      min: 2 Mbps
      max: 8 Mbps
    ffmpeg_preset: medium
    scene_overrides:
      all: { codec: h264, preset: medium, crf: 25 }
    container: "mp4"
    audio: { codec: aac, bitrate: 96k }
    color_profile: sRGB
    profile: baseline
    level: 4.0
```

### Runtime Encoding Decision Logic

```python
class AdaptiveEncoderSkill:
    """Selects codec, resolution, bitrate per scene."""
    
    def choose_encoding(
        self,
        scene: Scene,
        job_context: dict,
        validation_result: AssetValidationResult,
        quality_preset: str = "youtube"
    ) -> EncodingProfile:
        """
        Determine encoding parameters for a scene.
        
        Inputs:
          - scene: Scene metadata (type, description)
          - job_context: Job config (quality_preset, target_duration)
          - validation_result: Asset validation (resolution, artifacts, confidence)
          - quality_preset: "youtube" | "linkedin" | "archive" | "presentation" | custom
        
        Returns: EncodingProfile (codec, bitrate, resolution, ffmpeg_args)
        """
        # Load preset config
        preset_config = self.load_preset(quality_preset)
        
        # 1. Determine codec
        codec = self._choose_codec(
            preset_config,
            scene.type,
            validation_result.overall_confidence
        )
        
        # 2. Determine resolution
        resolution = self._choose_resolution(
            preset_config,
            scene.type,
            validation_result.metadata.get("actual_resolution"),
            upscale=preset_config.resolution.upscale_threshold
        )
        
        # 3. Determine bitrate
        bitrate = self._choose_bitrate(
            preset_config,
            scene.type,
            resolution,
            scene_complexity=self._analyze_complexity(scene),
            artifact_warning=validation_result.has_warning("artifacts")
        )
        
        # 4. Determine FFmpeg preset (speed vs quality)
        preset = self._choose_ffmpeg_preset(
            preset_config,
            codec,
            scene.type,
            job_context.get("prefer_speed", False)
        )
        
        # 5. Build FFmpeg command
        ffmpeg_args = self._build_ffmpeg_args(
            codec=codec,
            resolution=resolution,
            bitrate=bitrate,
            preset=preset,
            color_profile=preset_config.color_profile,
            input_file=scene.asset_path,
            output_file=scene.output_path,
            audio_config=preset_config.audio
        )
        
        # 6. Log decision (audit trail)
        self.audit_backend.write_event("encoding_decision", {
            "scene_id": scene.id,
            "job_id": job_context["job_id"],
            "preset": quality_preset,
            "scene_type": scene.type,
            "codec": codec,
            "resolution": resolution,
            "bitrate": bitrate,
            "ffmpeg_preset": preset,
            "validation_confidence": validation_result.overall_confidence,
            "tenant_id": job_context["tenant_id"],
        })
        
        return EncodingProfile(
            codec=codec,
            resolution=resolution,
            bitrate=bitrate,
            ffmpeg_preset=preset,
            ffmpeg_args=ffmpeg_args,
            color_profile=preset_config.color_profile,
            audio_codec=preset_config.audio.codec
        )
    
    def _choose_codec(
        self,
        preset_config: PresetConfig,
        scene_type: str,
        confidence: float
    ) -> str:
        """
        Choose codec from priority list, considering platform compatibility.
        
        - H.264: broader compatibility (all browsers, all platforms)
        - H.265: better compression (20–50% smaller for same quality)
        
        Fallback to H.264 if H.265 unavailable on platform.
        """
        scene_overrides = preset_config.scene_overrides.get(scene_type, {})
        codec_from_scene = scene_overrides.get("codec")
        if codec_from_scene:
            return codec_from_scene
        
        # Use preset priority list
        for codec in preset_config.codec_priority:
            if self._is_codec_available(codec):
                # High-confidence scenes can use H.265
                # Low-confidence scenes (validation warnings) → H.264 (safer)
                if codec == "h265" and confidence < 0.7:
                    continue  # skip H.265 if confidence low, use H.264
                return codec
        
        # Fallback
        return "h264"
    
    def _choose_resolution(
        self,
        preset_config: PresetConfig,
        scene_type: str,
        actual_resolution: tuple,
        upscale: float = 1.3
    ) -> str:
        """
        Choose output resolution.
        
        Rules:
        - Never upscale more than `upscale` threshold (blurry)
        - Never downscale if source matches target (waste)
        - Honor preset min/max range
        """
        default_res = preset_config.resolution.get("default", "1080p")
        min_res = self._parse_resolution(preset_config.resolution["range"][0])
        max_res = self._parse_resolution(preset_config.resolution["range"][1])
        
        if actual_resolution:
            src_w, src_h = actual_resolution
            src_res = (src_w * src_h) ** 0.5  # diagonal
            
            # Check upscaling limit
            default_diagonal = (1920 * 1080) ** 0.5 if "1080p" in default_res else 2560
            if src_res / default_diagonal < (1 / upscale):
                # Source too small, use min resolution instead
                return preset_config.resolution["range"][0]
            
            # Source is adequate, use default
            return default_res
        
        # No actual resolution info, use default
        return default_res
    
    def _choose_bitrate(
        self,
        preset_config: PresetConfig,
        scene_type: str,
        resolution: str,
        scene_complexity: float,
        artifact_warning: bool
    ) -> str:
        """
        Choose bitrate based on scene type, complexity, and validation result.
        
        - Simple scenes (title, static): lower bitrate
        - Complex scenes (screenshot, animation): higher bitrate
        - Artifact warnings: increase bitrate to preserve quality
        """
        scene_overrides = preset_config.scene_overrides.get(scene_type, {})
        if "bitrate" in scene_overrides:
            return scene_overrides["bitrate"]
        
        # Parse preset bitrate range
        target_range = preset_config.bitrate["target"]
        min_br = self._parse_bitrate(preset_config.bitrate["min"])
        max_br = self._parse_bitrate(preset_config.bitrate["max"])
        
        # Adjust based on complexity
        if scene_complexity > 0.7:
            # Complex scene, use higher end of range
            br = max_br * 0.8
        elif scene_complexity < 0.3:
            # Simple scene, use lower end
            br = min_br * 1.5
        else:
            # Medium complexity, use middle
            br = (min_br + max_br) / 2
        
        # Artifact warning: bump bitrate 20% to preserve detail
        if artifact_warning:
            br *= 1.2
        
        # Clamp to min/max
        br = max(min_br, min(br, max_br))
        
        return f"{int(br)}k"
```

### Codec Availability Detection

```python
def _is_codec_available(self, codec: str) -> bool:
    """Check if codec is available (GPU or CPU)."""
    available_codecs = self._probe_ffmpeg()
    
    codec_names = {
        "h264": ["libx264", "h264_nvenc", "h264_qsv", "h264_videotoolbox"],
        "h265": ["libx265", "hevc_nvenc", "hevc_qsv", "hevc_videotoolbox"],
    }
    
    for name in codec_names.get(codec, []):
        if name in available_codecs:
            return True
    
    return False
```

### Fallback Mechanism (Adaptive Retry)

```python
async def encode_scene_with_fallback(
    self,
    scene: Scene,
    primary_encoding: EncodingProfile
) -> EncodingResult:
    """Encode scene, fall back to lower bitrate/codec if failure."""
    
    try:
        # Try primary encoding
        result = await self._run_ffmpeg(primary_encoding)
        if result.success and self._verify_output(result):
            self.audit_backend.write_event("encoding_succeeded", {
                "scene_id": scene.id,
                "encoding": primary_encoding.to_dict(),
            })
            return result
    except Exception as e:
        logger.warning(f"Encoding failed: {e}")
    
    # Fallback 1: reduce bitrate by 20%
    fallback_1 = primary_encoding.with_bitrate_reduced(0.2)
    try:
        result = await self._run_ffmpeg(fallback_1)
        if result.success:
            self.audit_backend.write_event("encoding_fallback_bitrate", {
                "scene_id": scene.id,
                "original": primary_encoding.to_dict(),
                "fallback": fallback_1.to_dict(),
            })
            return result
    except Exception:
        pass
    
    # Fallback 2: switch to H.264 (if was H.265)
    if primary_encoding.codec == "h265":
        fallback_2 = primary_encoding.with_codec("h264")
        try:
            result = await self._run_ffmpeg(fallback_2)
            if result.success:
                self.audit_backend.write_event("encoding_fallback_codec", {...})
                return result
        except Exception:
            pass
    
    # Fallback 3: reduce resolution + bitrate
    fallback_3 = primary_encoding.with_resolution_reduced()
    result = await self._run_ffmpeg(fallback_3)  # no exception handling, let it fail
    self.audit_backend.write_event("encoding_fallback_resolution", {
        "original": primary_encoding.to_dict(),
        "fallback": fallback_3.to_dict(),
        "final": result.to_dict(),
    })
    return result
```

### Data Model

```python
@dataclass(frozen=True)
class EncodingProfile:
    codec: str  # "h264" or "h265"
    resolution: str  # "1080p", "1440p", "2160p"
    bitrate: str  # "8000k", "12000k"
    ffmpeg_preset: str  # "fast", "medium", "slow"
    color_profile: str  # "BT.709", "sRGB", "BT.2020"
    audio_codec: str  # "aac"
    ffmpeg_args: List[str]  # raw FFmpeg arguments
    
    def with_bitrate_reduced(self, factor: float) -> "EncodingProfile":
        """Return new profile with bitrate reduced by factor (0.2 = 20% reduction)."""
        current = int(self.bitrate.rstrip('k'))
        new_bitrate = f"{int(current * (1 - factor))}k"
        return replace(self, bitrate=new_bitrate)
    
    def with_codec(self, new_codec: str) -> "EncodingProfile":
        """Return new profile with different codec."""
        return replace(self, codec=new_codec)
    
    def with_resolution_reduced(self) -> "EncodingProfile":
        """Return new profile with resolution one step down."""
        downscale_map = {"2160p": "1440p", "1440p": "1080p", "1080p": "720p"}
        new_res = downscale_map.get(self.resolution, self.resolution)
        return replace(self, resolution=new_res)
```

### LDD Metrics

| Metric | Target | Why |
|---|---|---|
| File size per minute | 20–40 MB/min (YouTube) | Balance quality and platform limits |
| Encoding speed | <30s per minute of video (with GPU) | User experience (not too slow) |
| Quality satisfaction | >0.8 (avg user feedback) | Perceptual quality acceptance |
| Platform compatibility | 95%+ (codec/profile support) | Broad accessibility |

### Testing

**Unit Tests:**
- `test_h264_chosen_for_linkedin_preset` → codec=="h264"
- `test_h265_chosen_for_archive_preset` → codec=="h265"
- `test_bitrate_adjusted_for_high_complexity_scene` → bitrate_increased
- `test_fallback_codec_when_h265_unavailable` → fallback to H.264
- `test_fallback_bitrate_on_encode_failure` → reduce bitrate, retry

**E2E Tests:**
- `test_full_scene_encoding_workflow` → encode scene, verify output
- `test_adaptive_fallback_sequence` → primary fails, fallback succeeds

### Deployment

**Phase 1 (Weeks 1–2):**
- Implement EncodingProfile selection logic
- Load YAML presets
- Integrate into VideoProducerSkill
- Tests + docs

**Phase 2 (Weeks 3–4):**
- GPU acceleration integration (ADR-0702)
- Learning loop tuning (ADR-0703)
- Console preset selector UI

---

## Consequences

### Benefits
- ✅ Scene-adaptive encoding → optimal quality/size trade-off
- ✅ Preset selection → user control (YouTube/Archive/Presentation)
- ✅ Learning loop integration → self-optimizing bitrates
- ✅ Fallback mechanism → resilience on encoding failure

### Costs
- ❌ YAML config complexity (multiple presets to maintain)
- ❌ Encoding time increases slightly (more codec choices tried)

### Mitigation
- Preset defaults tuned by experts (YouTube, LinkedIn, etc.)
- Auto-selection based on job metadata (minimize operator choice)
