---
id: ADR-0702
status: proposed
supersedes: []
depends_on: [ADR-0703, ADR-0701]
related: [CONCEPT-0041, ADR-0703]
commits: []
paths:
  - "core/skills/video_producer_skill/gpu_accelerator.py"
  - "core/skills/video_producer_skill/tests/test_gpu_acceleration.py"
docs:
  - "docs/video-producer/performance-gpu.md"
---

# ADR-0702 — Performance & GPU Acceleration

**Status:** Proposed  
**Date:** 2026-09-13  

## Summary

Optimize video rendering through:
1. **GPU Hardware Encoding** (H.264/H.265 NVENC, Intel QSV)
2. **Scene-Level Parallelization** (TTS audio, screenshots, encoding workers)
3. **Caching** (rendered scenes, intermediate segments, LUTs)
4. **Memory Management** (streaming, intermediate cleanup)

**Target:** <30s per minute of video (with GPU); <3min for 5-min video.

## Decision

### 1. GPU Hardware Encoding

Detect available hardware encoders and use priority:
```
NVIDIA NVENC (H.264/H.265) > Intel QSV (H.264/H.265) > CPU libx264/libx265
```

**Benefits:** 2–3x faster than CPU encoding, lower power usage.

**Config:**
```yaml
performance:
  gpu_enabled: true
  gpu_device: "cuda"  # "cuda", "qsv", "videotoolbox"
  hardware_encoding:
    h264: true
    h265: true
```

### 2. Parallelization

- **TTS Audio:** 4 concurrent Playwright browsers → 4 TTS calls in parallel
- **Screenshots:** 3 concurrent browser instances
- **Encoding:** 2 concurrent FFmpeg workers (OS-dependent)
- **Multiplexing:** single-threaded, sequential (final merge)

**Implementation:** ThreadPoolExecutor + asyncio.gather()

### 3. Caching Strategy

- **Screenshot Cache:** reuse rendered images (same storyboard)
- **Encoded Segments:** cache scene video (if unchanged between runs)
- **Color LUTs:** pre-compute once, reuse

**Cache TTL:** 7 days (operator-tunable)

### 4. Memory Management

- Streaming encode: process in chunks (not all in RAM)
- Intermediate cleanup: delete temp files after each scene
- Monitor RAM usage (fail-closed if >80% utilization)

## Implementation Outline

```python
class GPUAcceleratorSkill:
    async def encode_scene_parallel(self, scenes: List[Scene]) -> List[EncodedScene]:
        """Encode multiple scenes in parallel."""
        futures = [
            asyncio.create_task(self._encode_single(scene))
            for scene in scenes
        ]
        return await asyncio.gather(*futures)
    
    async def _encode_single(self, scene: Scene) -> EncodedScene:
        """Encode single scene with GPU fallback to CPU."""
        try:
            if self.gpu_available:
                return await self._encode_with_gpu(scene)
        except Exception:
            logger.warning(f"GPU encoding failed for {scene.id}, falling back to CPU")
        
        return await self._encode_with_cpu(scene)
```

## LDD Metrics

| Metric | Target | How |
|---|---|---|
| Encoding latency | <30s/min (GPU) | Time per minute of video |
| CPU usage | <50% during encode | Monitor via psutil |
| Memory usage | <2GB for 5-min video | Track peak RAM |
| GPU utilization | >70% (when active) | nvidia-smi |

## Testing

- `test_gpu_available_hardware_encoder_used`
- `test_fallback_to_cpu_on_gpu_failure`
- `test_parallel_scene_encoding_speedup` → 2–3x faster
- `test_cache_hit_reuses_segment` → no re-encoding

## Deployment

Phase 3 (Weeks 5–6, after Phase 1/2 stable).

---

## Related

- ADR-0703 (Adaptive Encoding) — encoder selection
- ADR-0703 (Feedback Loop) — performance metrics for tuning
