# Phase 3 Implementation — GPU Acceleration & Performance
## Hardware Encoding, Parallelization, Caching, Dashboard

**Status:** Implementation Ready  
**Duration:** Weeks 5–6  
**Effort:** ~600 LoC + 15 tests  
**Depends on:** Phase 1–2 complete

---

## Deliverable 1: GPU Accelerator Skill

### File Structure
```
src/
├── gpu_accelerator.py (250 LoC)
│   ├─ GPUAcceleratorSkill class
│   ├─ Hardware encoder detection
│   ├─ NVENC/QSV/Videotoolbox selection
│   └─ Fallback to CPU
├── tests/test_gpu_acceleration.py (80 LoC, 6 tests)
```

### Core Implementation
```python
class GPUAcceleratorSkill:
    """Detect available GPU encoders, use priority."""
    
    def get_available_encoders(self) -> List[str]:
        """Probe FFmpeg for hardware encoders."""
        # Returns: ["h264_nvenc", "hevc_nvenc", "h264_qsv", ...]
        ...
    
    async def encode_scene_with_gpu(
        self,
        scene: Scene,
        encoding: EncodingProfile
    ) -> EncodedScene:
        """
        Encode using GPU (NVIDIA NVENC preferred).
        
        Priority:
        1. NVIDIA NVENC (H.264 nvenc / H.265 nvenc)
        2. Intel QSV (h264_qsv / hevc_qsv)
        3. Apple Videotoolbox (h264_videotoolbox / hevc_videotoolbox)
        4. CPU fallback (libx264 / libx265)
        """
        if "h264_nvenc" in self.available_encoders:
            return await self._encode_with_nvenc(scene, encoding)
        elif "h264_qsv" in self.available_encoders:
            return await self._encode_with_qsv(scene, encoding)
        else:
            return await self._encode_with_cpu(scene, encoding)
```

### Performance Target
- **With GPU:** <30s per minute of video
- **With CPU:** <3 min per minute of video

---

## Deliverable 2: Scene Parallelization

### File Structure
```
src/
├── parallel_renderer.py (200 LoC)
│   ├─ ParallelSceneRendererSkill class
│   ├─ ThreadPoolExecutor management
│   ├─ TTS audio generation (4 workers)
│   ├─ Screenshot rendering (3 workers)
│   ├─ Encoding (2 workers)
│   └─ Multiplexing (1 worker, sequential)
├── tests/test_parallelization.py (60 LoC, 5 tests)
```

### Implementation
```python
class ParallelSceneRendererSkill:
    """Parallelize TTS, screenshots, encoding."""
    
    def __init__(self):
        self.tts_pool = ThreadPoolExecutor(max_workers=4)
        self.screenshot_pool = ThreadPoolExecutor(max_workers=3)
        self.encode_pool = ThreadPoolExecutor(max_workers=2)
    
    async def render_all_scenes_parallel(
        self,
        scenes: List[Scene]
    ) -> List[EncodedScene]:
        """
        Render scenes in parallel (TTS + screenshots + encoding).
        Multiplex final output sequentially.
        """
        # 1. TTS audio generation (parallel, 4 workers)
        audio_futures = [
            asyncio.create_task(self._generate_tts_parallel(scene))
            for scene in scenes
        ]
        audio_results = await asyncio.gather(*audio_futures)
        
        # 2. Screenshot rendering (parallel, 3 workers)
        screenshot_futures = [
            asyncio.create_task(self._render_screenshot_parallel(scene))
            for scene in scenes
        ]
        screenshot_results = await asyncio.gather(*screenshot_futures)
        
        # 3. Encoding (parallel, 2 workers)
        encode_futures = [
            asyncio.create_task(self._encode_scene_parallel(scene))
            for scene in scenes
        ]
        encoded_results = await asyncio.gather(*encode_futures)
        
        # 4. Multiplex (sequential, final video)
        final_video = await self._multiplex_scenes(encoded_results)
        
        return final_video
```

### Performance Gain
- TTS: 4 parallel calls = ~4x faster
- Screenshots: 3 parallel browsers = ~3x faster
- Encoding: 2 parallel FFmpeg = ~2x faster (if GPU available)
- **Total speedup:** ~4x for 5-min video (TTS bottleneck)

---

## Deliverable 3: Caching System

### File Structure
```
src/
├── cache_manager.py (150 LoC)
│   ├─ CacheManager class
│   ├─ Screenshot cache (hash-based)
│   ├─ Encoded segment cache
│   ├─ LUT cache (color grading)
│   └─ TTL management (7 days default)
├── tests/test_caching.py (50 LoC, 4 tests)
```

### Cache Strategy
```python
class CacheManager:
    """Manage cached artifacts (screenshots, segments, LUTs)."""
    
    def cache_key(self, asset_hash: str, job_config: dict) -> str:
        """Generate deterministic cache key."""
        return hashlib.sha256(
            f"{asset_hash}:{json.dumps(job_config)}".encode()
        ).hexdigest()
    
    async def get_cached_screenshot(
        self,
        scene_description: str,
        config: dict
    ) -> Optional[Path]:
        """
        Check if screenshot already cached.
        Returns: Path if cached and fresh, None otherwise.
        """
        key = self.cache_key(scene_description, config)
        cache_path = self.cache_dir / f"screenshot_{key}.png"
        
        if cache_path.exists():
            age = datetime.now() - cache_path.stat().st_mtime
            if age < timedelta(days=7):  # TTL
                return cache_path
        
        return None
    
    async def cache_encoded_segment(
        self,
        scene_id: str,
        segment_path: Path
    ) -> str:
        """Cache encoded video segment for reuse."""
        key = f"segment_{scene_id}_{self.config_hash()}"
        cache_path = self.cache_dir / f"{key}.mp4"
        shutil.copy(segment_path, cache_path)
        return str(cache_path)
```

### Cache Directories
```
~/.corvin/video-producer/cache/

├── screenshots/ (PNG, hash-named)
├── segments/ (MP4, hash-named)
├── luts/ (3D color cubes)
└── metadata.json (cache manifest, TTL tracking)
```

### Cache Hit Benefit
- Screenshot cache: skip LLM + rendering (~5s saved)
- Segment cache: skip encoding (~30s saved for 1-min segment)

---

## Deliverable 4: Advanced Dashboard

### File Structure
```
web-next/src/
├── components/VideoPerformanceDashboard.tsx (120 LoC)
│   ├─ Performance metrics display
│   ├─ GPU utilization graph
│   ├─ Encoding latency timeline
│   ├─ Cache hit rate
│   └─ Convergence curve
├── hooks/usePerformanceMetrics.ts (40 LoC)
├── tests/VideoPerformanceDashboard.test.tsx (30 LoC)
```

### Dashboard Sections
```
┌─ Video Producer Performance Dashboard ──┐
│                                         │
│ Real-Time Metrics (Last 5 Jobs):        │
│                                         │
│ Encoding Latency:                       │
│ ├─ Avg: 42 sec/min (with GPU)          │
│ ├─ Min: 28 sec/min (GPU hit)           │
│ ├─ Max: 85 sec/min (CPU fallback)      │
│ └─ Trend: ↓ improving                   │
│                                         │
│ GPU Utilization:                        │
│ ├─ NVIDIA RTX4090: 75% (active)        │
│ ├─ Encoding threads: 2/2 in use        │
│ └─ Fallback rate: 0.2% (very rare)     │
│                                         │
│ Cache Performance:                      │
│ ├─ Screenshot hits: 45% (18/40)        │
│ ├─ Segment hits: 12% (5/40)            │
│ └─ Storage used: 2.3 GB / 10 GB        │
│                                         │
│ Quality Convergence:                    │
│ ├─ Mean score: 0.87 (stable)           │
│ ├─ Σ feedback: 47 scenes reviewed      │
│ └─ Learning rate: 0.01 (conservative)  │
│                                         │
└─────────────────────────────────────────┘
```

### API Endpoints
```
GET /v1/console/video/performance/metrics
  → Last 5 jobs' latency, GPU usage, cache stats

GET /v1/console/video/performance/convergence
  → Quality score trend over jobs (loss curve)

GET /v1/console/video/cache/stats
  → Cache hit rates, storage usage, TTL expiry
```

---

## Integration Checklist

### GPU Integration
- [ ] Probe FFmpeg for available encoders
- [ ] Detect NVIDIA NVENC (preferred)
- [ ] Fallback to CPU if no GPU
- [ ] Log encoder choice (audit)
- [ ] Monitor GPU memory usage (fail-closed if >95%)

### Parallelization
- [ ] TTS generator uses ThreadPoolExecutor (4 workers)
- [ ] Screenshot renderer uses ThreadPoolExecutor (3 workers)
- [ ] Encoding pool uses ThreadPoolExecutor (2 workers)
- [ ] Multiplex final output (sequential)
- [ ] Measure parallelization speedup (target: 4x TTS)

### Caching
- [ ] Screenshot cache with 7-day TTL
- [ ] Segment cache (optional for iterative workflows)
- [ ] LUT cache for color grading presets
- [ ] Cache manifest (metadata.json)
- [ ] Measure cache hit rate (target: >40% screenshots)

### Dashboard
- [ ] Performance metrics API endpoint
- [ ] Real-time GPU/latency graph
- [ ] Convergence curve display
- [ ] Cache statistics panel
- [ ] Integration with existing console

---

## Test Plan (15 tests, ~20 min)

**Unit Tests:**
- test_gpu_encoder_detection → returns available codecs
- test_nvenc_priority_selection → prefers NVENC
- test_cpu_fallback_on_gpu_unavailable → switches to CPU
- test_parallel_tts_speedup → 4x faster
- test_screenshot_cache_hit → reuses cached image
- test_cache_ttl_expiry → evicts old cache

**E2E Tests:**
- test_gpu_encoding_end_to_end → encodes with NVENC
- test_parallelization_complete_workflow → all workers run
- test_cache_hit_reuses_segment → no re-encoding
- test_performance_dashboard_displays → metrics shown

---

## Performance Targets

| Metric | Target | How |
|--------|--------|-----|
| Encoding latency | <30s/min (GPU) | Real benchmark |
| TTS parallelization | 4x speedup | Measure wall-clock time |
| Cache hit rate | >40% (screenshots) | Track cache queries |
| GPU utilization | 70%+ | nvidia-smi samples |
| Memory usage | <2GB for 5-min video | Monitor peak RSS |

---

## Success Criteria

- ✅ All 15 tests green
- ✅ GPU encoding verified (NVIDIA NVENC detected)
- ✅ Parallelization speedup measured (4x TTS)
- ✅ Cache hit rate >40%
- ✅ Performance dashboard renders
- ✅ Mean encoding latency <40s/min

---

**End of Implementation Roadmap** — Phases 1–3 Complete
