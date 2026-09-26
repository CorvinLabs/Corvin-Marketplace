# Phase 2: Blender Rendering Extension — Handoff & Next Steps

**Status:** 🟡 **READY FOR PHASE 2 DEVELOPMENT**  
**Date:** 2026-09-24  
**Handoff From:** Phase 1 Complete (Tier 1, 1.5, 2 renderers)  
**Handoff To:** Phase 2 Blender 3D Enhancement  

---

## 📦 What Was Completed (Phase 1)

### Production-Ready Components

✅ **Tier 1 (Quick Renderer)** — Always available fallback
- SVG diagram generation
- PNG/MP4 conversion via ffmpeg
- Render time: <10 seconds

✅ **Tier 1.5 (Three.js)** — GPU-accelerated 3D
- Puppeteer-driven headless Chrome
- 3 pre-built scenes (maestro-3d, learning-loop-3d, audit-chain-3d)
- Render time: ~20 seconds

✅ **Tier 2 (Manim)** — Rich math animation
- Python scene generation
- Manim framework rendering
- Render time: ~45 seconds

✅ **Tier 3 (Blender)** — Premium 3D INFRASTRUCTURE (stubbed)
- `blender_async_executor.py` ✅ Implemented (async job submission)
- `blender_renderer.py` ✅ Implemented (3D rendering core)
- Job polling, failure tracking, auto-downgrade logic
- **Actual 3D asset pipeline: NOT YET BUILT**

---

## 🎯 Phase 2 Scope — Blender 3D Asset Pipeline

### What Needs to Happen

The Blender infrastructure is **ready** but the **asset pipeline is incomplete**. Phase 2 builds:

1. **Scene Builder** (NEW)
   - Generate .blend files from narration + storyboard
   - 3D object/lighting/camera setup
   - Material assignment, animation keyframes
   - Estimated: 400–500 LoC

2. **Material Library** (NEW)
   - PBR material definitions (metallic, roughness, etc.)
   - Texture asset management
   - Blender shader graph templates
   - Estimated: 200–300 LoC

3. **Animation Controller** (NEW)
   - Keyframe generation from timing data
   - Camera path generation
   - Object motion curves
   - Estimated: 300–400 LoC

4. **Quality Metrics** (ENHANCE)
   - Render preview metrics (frame count, resolution, duration)
   - Estimated render time prediction
   - Quality confidence scoring
   - Estimated: 150–200 LoC

5. **Learning Integration** (WIRE)
   - Hook Phase 2 Learning Loop (ADR-0314) into Blender tier
   - Feedback → quality prediction refinement
   - Optimizer learns Blender strengths/weaknesses
   - Estimated: 100–150 LoC

### Success Criteria (Phase 2)

| Criterion | Details |
|-----------|---------|
| **E2E Blender Render** | Narration + storyboard → .blend file → MP4 video |
| **15+ Tests** | Scene builder, materials, animation, metrics |
| **Render Quality** | 1920×1080 @ 30fps, CRF 18 preset |
| **Latency** | Submission <100ms, render ~90 sec |
| **Learning Integration** | Feedback affects next Tier 3 job |
| **Fallback Chain** | Tier 3 → 2 → 1.5 → 1 (all paths working) |

---

## 📂 File Structure — Phase 2 (NEW FILES)

```
src/
├── scene_builder.py          ← NEW (generates .blend files from data)
├── material_library.py        ← NEW (PBR materials + textures)
├── animation_controller.py    ← NEW (keyframe + camera animation)
├── blender_quality_metrics.py ← NEW (render prediction + scoring)
└── tests/
    └── test_phase2_blender_pipeline.py ← NEW (15+ E2E tests)

docs/
├── implementation-ready/
│   ├── PHASE-2-BLENDER-RENDERING-HANDOFF.md ← THIS FILE
│   └── BLENDER-SCENE-SCHEMA.md              ← NEW (spec)
└── ADRs/
    └── ADR-0704-blender-3d-pipeline.md       ← NEW (architectural decision)
```

---

## 🔄 Handoff Checklist

### For You (Getting Started)

- [ ] Read this entire handoff document
- [ ] Review `src/blender_async_executor.py` (async job submission API)
- [ ] Review `src/blender_renderer.py` (3D rendering core)
- [ ] Run existing tests: `pytest tests/test_phase3_renderers.py -v -k blender`
- [ ] Verify Blender CLI availability: `blender --version`
- [ ] Check Phase 1 tests all pass: `pytest tests/ -v`

### For the Next Developer (Future Handoff)

- [ ] Implement Scene Builder
- [ ] Implement Material Library
- [ ] Implement Animation Controller  
- [ ] Add 15+ tests covering all new components
- [ ] Wire into Learning Loop (ADR-0314)
- [ ] Update deployment scripts
- [ ] Run full E2E test suite
- [ ] Document in ADR-0704

---

## 🛠️ Getting Started — Development Guide

### 1. Review Current Blender Integration

```bash
cd /home/shumway/projects/Corvin-Marketplace/plugins/contributor/media/video_producer

# Inspect async executor (non-blocking job submission)
cat src/blender_async_executor.py | grep -A 20 "class BlenderAsyncExecutor"

# Inspect renderer (core 3D rendering logic)
cat src/blender_renderer.py | grep -A 20 "class BlenderRenderer"

# Run current tests
pytest tests/test_phase3_renderers.py::test_blender_health_check -v
pytest tests/test_phase3_renderers.py -v -k blender
```

### 2. Understand the Scene Format

Blender scenes will be specified as JSON:

```json
{
  "scene_id": "learning_loop_3d_v1",
  "duration": 30.0,
  "resolution": { "width": 1920, "height": 1080 },
  "framerate": 30,
  "objects": [
    {
      "name": "maestro_cube",
      "type": "mesh",
      "mesh": "cube",
      "location": [0, 0, 0],
      "scale": [1, 1, 1],
      "material": "metallic_blue",
      "animation": {
        "keyframes": [
          { "frame": 0, "rotation": [0, 0, 0] },
          { "frame": 120, "rotation": [0, 360, 0] }
        ]
      }
    }
  ],
  "camera": {
    "location": [5, 5, 5],
    "look_at": [0, 0, 0],
    "path": [
      { "frame": 0, "pos": [5, 5, 5] },
      { "frame": 120, "pos": [8, 8, 8] }
    ]
  },
  "lights": [
    {
      "name": "key_light",
      "type": "sun",
      "location": [5, 10, 5],
      "energy": 2.0,
      "angle": 0.5
    }
  ]
}
```

### 3. Development Workflow

```bash
# 1. Start with scene_builder.py
# Takes narration + storyboard → generates scene JSON + .blend file

# 2. Implement material_library.py
# PBR material definitions, texture loading, shader graphs

# 3. Implement animation_controller.py
# Keyframe generation from narration timing, camera paths

# 4. Add blender_quality_metrics.py
# Predict render time, quality scoring, learning integration

# 5. Wire tests
pytest tests/test_phase2_blender_pipeline.py -v

# 6. Test full pipeline
python3 scripts/test_blender_e2e.py
```

---

## ⚙️ API Reference — What Already Works

### `BlenderAsyncExecutor` (use this for job submission)

```python
from src.blender_async_executor import BlenderAsyncExecutor

executor = BlenderAsyncExecutor(
    output_dir="./outputs/blender"
)

# Submit a render job (non-blocking, <100ms)
job_id = executor.submit_job(
    blend_file="path/to/scene.blend",
    start_frame=1,
    end_frame=150
)

# Poll for completion
status = executor.poll_job(job_id)
# Returns: { "status": "running|complete|failed", "progress": 0.45, ... }

# Check for auto-downgrade (Tier 3 → Tier 2)
should_downgrade = executor.check_auto_downgrade()
```

### `BlenderRenderer` (use this for 3D rendering)

```python
from src.blender_renderer import BlenderRenderer, BlenderScene, BlenderConfig

config = BlenderConfig(
    framerate=30,
    resolution_x=1920,
    resolution_y=1080,
    samples=100,          # quality: higher = better but slower
    engine="CYCLES",      # CYCLES (realistic) or EEVEE (fast)
    use_gpu=True          # GPU acceleration if available
)

renderer = BlenderRenderer(output_dir="./outputs", config=config)

scene = BlenderScene(
    blend_file="path/to/scene.blend",
    start_frame=1,
    end_frame=150,
    output_dir="./outputs/render"
)

# Render synchronously (returns list of PNG frame paths)
frames = renderer.render_scene(scene)
print(f"Rendered {len(frames)} frames")
```

---

## 📊 Learning Integration (Phase 2 Task)

Wire Blender feedback into the learning loop:

```python
# After render completes, record execution
from src.learning_event_store import LearningEventStore

event_store = LearningEventStore()

event_store.record_execution_event(
    tier=3,
    concept_id="learning_loop_3d",
    duration_ms=render_duration,
    quality_score=predicted_quality,
    success=True
)

# Collect user feedback
event_store.record_feedback_event(
    tier=3,
    feedback_type="outcome_feedback",
    signal="satisfied",  # or "dissatisfied"
    confidence=0.95
)

# Optimizer automatically adjusts Tier 3 weights
optimizer = TierLearningOptimizer()
optimizer.optimize_from_feedback()
```

---

## 🎬 Phase 2 Deliverables Checklist

### Code Implementation
- [ ] `src/scene_builder.py` (400–500 LoC)
  - [ ] Parse narration + storyboard JSON
  - [ ] Generate 3D object specs
  - [ ] Create .blend file via Blender Python API
  - [ ] Export to filesystem

- [ ] `src/material_library.py` (200–300 LoC)
  - [ ] PBR material definitions (metallic, roughness, etc.)
  - [ ] Texture asset loading
  - [ ] Blender shader graph generation
  - [ ] Material assignment logic

- [ ] `src/animation_controller.py` (300–400 LoC)
  - [ ] Parse animation timing from storyboard
  - [ ] Generate keyframes for objects/camera
  - [ ] Motion curve generation
  - [ ] Camera path animation

- [ ] `src/blender_quality_metrics.py` (150–200 LoC)
  - [ ] Render time prediction (frames × complexity)
  - [ ] Quality confidence scoring
  - [ ] Learning loop integration

### Testing (15+ new tests)
- [ ] `tests/test_phase2_blender_pipeline.py`
  - [ ] Scene builder tests (5 tests)
  - [ ] Material library tests (3 tests)
  - [ ] Animation controller tests (4 tests)
  - [ ] Quality metrics tests (3 tests)

### Documentation
- [ ] `docs/BLENDER-SCENE-SCHEMA.md` (JSON schema spec)
- [ ] `docs/ADRs/ADR-0704-blender-3d-pipeline.md` (architecture)
- [ ] Update `DEPLOYMENT_STATUS.md` with Phase 2 status

### Deployment
- [ ] Update installation script to handle Blender dependencies
- [ ] Add Blender configuration to config.yaml
- [ ] Document Blender setup guide

---

## 🚨 Known Limitations & Gotchas

### Blender CLI Quirks

1. **Blender must be installed:** `blender --version` should work
2. **GPU acceleration optional:** Falls back to CPU (slower but always works)
3. **Temp files:** Blender may leave temp files; clean up after render
4. **File locking:** `.blend` file may be locked during render; poll with backoff
5. **Python API:** Blender's Python API is version-specific; test with your version

### Phase 2 Risks

| Risk | Mitigation |
|------|-----------|
| Blender not installed | Fallback to Tier 2 (Manim) via fallback chain |
| .blend file corruption | Validate file before rendering, re-generate if needed |
| Keyframe conflicts | Validator checks for overlapping keyframes |
| Material undefined | Fallback to default material |
| GPU out of memory | Downgrade samples, reduce resolution, retry on CPU |

---

## 📞 Communication Handoff

### Questions? Check These First

1. **How does async job submission work?**
   → Read `src/blender_async_executor.py::submit_job()`

2. **What's the .blend file format?**
   → See BLENDER-SCENE-SCHEMA.md (create this in Phase 2)

3. **How do I generate keyframes?**
   → See `src/animation_controller.py` (implement in Phase 2)

4. **How does learning loop wire in?**
   → See `src/learning_event_store.py` and `src/tier_learning_optimizer.py`

5. **When do I run tests?**
   → After each component: `pytest tests/test_phase2_blender_pipeline.py -v`

---

## 🔗 Related Documentation

- **Phase 1 Report:** `PHASE1_IMPLEMENTATION_REPORT.md` ✅ Complete
- **Phase 3 Deployment:** `DEPLOYMENT_STATUS.md` ✅ Production Ready
- **Learning Loop:** `docs/ADRs/ADR-0703-video-feedback-learning-integration.md`
- **Tier System:** `docs/ADRs/ADR-0002-3tier-animation.md`

---

## ✅ Sign-Off

**Phase 1 Status:** ✅ COMPLETE (All Tier 1–2 renderers working)  
**Phase 2 Status:** 🟡 READY FOR DEVELOPMENT (Infrastructure ready, asset pipeline pending)  
**Phase 3 Status:** 🟢 PRODUCTION READY (Deployed to marketplace)

**Handoff Date:** 2026-09-24  
**Handoff From:** Phase 1 Team  
**Handoff To:** Phase 2 Developer (You!)  

**Next: Start with `scene_builder.py` and read the schema spec.**

---

**Ready to begin Phase 2?** ✨

The foundation is solid. Build on it!

