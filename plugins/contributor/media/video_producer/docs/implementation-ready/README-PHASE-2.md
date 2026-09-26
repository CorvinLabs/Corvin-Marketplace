# Phase 2 Blender Rendering — Developer Guide

**Status:** 🟡 **Ready for Development**  
**Timeline:** 3 weeks (Weeks of 2026-09-24)  
**Effort:** ~1500–1800 LoC + 15+ tests  
**Task ID:** #1

---

## 🚀 Quick Start (5 minutes)

1. **Read the Handoff:**
   ```bash
   cat PHASE-2-BLENDER-RENDERING-HANDOFF.md
   ```

2. **Review the Schema:**
   ```bash
   cat BLENDER-SCENE-SCHEMA.md
   ```

3. **Do the Setup:**
   ```bash
   cat PHASE-2-SETUP-CHECKLIST.md | grep "^### 2" -A 20
   ```

4. **Start Coding:**
   ```bash
   touch src/scene_builder.py
   # Begin implementation
   ```

---

## 📚 Documentation Index

### For Handoff & Context
- **[PHASE-2-BLENDER-RENDERING-HANDOFF.md](PHASE-2-BLENDER-RENDERING-HANDOFF.md)** ← START HERE
  - What was completed (Phase 1)
  - What needs to happen (Phase 2 scope)
  - API reference for existing components
  - Limitations & gotchas

### For Specification
- **[BLENDER-SCENE-SCHEMA.md](BLENDER-SCENE-SCHEMA.md)** ← YOUR SPEC
  - JSON schema for 3D scenes
  - Object, material, light, camera definitions
  - Complete example scene
  - Implementation notes

### For Development Setup
- **[PHASE-2-SETUP-CHECKLIST.md](PHASE-2-SETUP-CHECKLIST.md)** ← YOUR CHECKLIST
  - Pre-development checklist
  - Python environment setup
  - Implementation sequence (week by week)
  - Testing strategy
  - Success criteria

### Reference Documentation
- **[../ADRs/ADR-0703-video-feedback-learning-integration.md](../ADRs/ADR-0703-video-feedback-learning-integration.md)**
  - Learning loop architecture (ADR-0314)
  - Feedback integration

- **[../ADRs/ADR-0002-3tier-animation.md](../ADRs/ADR-0002-3tier-animation.md)**
  - Tier system overview
  - Fallback chain design

- **[../DEPLOYMENT_STATUS.md](../DEPLOYMENT_STATUS.md)**
  - Production readiness criteria
  - Phase 1–3 status

- **[../PHASE1_IMPLEMENTATION_REPORT.md](../PHASE1_IMPLEMENTATION_REPORT.md)**
  - Phase 1 completed components
  - Testing coverage summary

---

## 🎯 Phase 2 Deliverables

| Component | LoC | Tests | Status |
|-----------|-----|-------|--------|
| **Scene Builder** | 400–500 | 5 | 🔲 NOT STARTED |
| **Material Library** | 200–300 | 3 | 🔲 NOT STARTED |
| **Animation Controller** | 300–400 | 4 | 🔲 NOT STARTED |
| **Quality Metrics** | 150–200 | 3 | 🔲 NOT STARTED |
| **Total** | 1050–1400 | 15+ | 🔲 IN PROGRESS |

---

## 🛠️ What You're Building

### **Scene Builder** (First priority)
Converts JSON scene specification → .blend file

```python
from src.scene_builder import SceneBuilder

builder = SceneBuilder()
scene_json = { ... }  # From BLENDER-SCENE-SCHEMA.md
builder.build_scene(scene_json, output_path="scene.blend")
# → scene.blend (ready for Blender rendering)
```

### **Material Library** (Second priority)
Manages PBR materials and textures

```python
from src.material_library import MaterialLibrary

library = MaterialLibrary()
material_def = { ... }  # From schema
library.create_material(material_def)
# → Blender material object
```

### **Animation Controller** (Third priority)
Generates keyframes from scene data

```python
from src.animation_controller import AnimationController

controller = AnimationController()
controller.apply_keyframes(blender_object, keyframes)
# → Object animated over timeline
```

### **Quality Metrics** (Fourth priority)
Estimates render time + quality scoring

```python
from src.blender_quality_metrics import QualityMetrics

metrics = QualityMetrics()
est_time = metrics.estimate_render_time(scene_json)
# → Predicted render duration (seconds)
```

---

## 📖 Reading Order

### Minimum (Start here)
1. This README (5 min)
2. PHASE-2-BLENDER-RENDERING-HANDOFF.md (15 min)
3. BLENDER-SCENE-SCHEMA.md (20 min)

**Total: 40 minutes** — Enough to start coding

### Full (Recommended)
1. This README (5 min)
2. PHASE-2-BLENDER-RENDERING-HANDOFF.md (15 min)
3. BLENDER-SCENE-SCHEMA.md (20 min)
4. PHASE-2-SETUP-CHECKLIST.md (10 min)
5. `src/blender_async_executor.py` (10 min)
6. `src/blender_renderer.py` (15 min)
7. `src/learning_event_store.py` (10 min)
8. `tests/test_phase3_renderers.py` (20 min)

**Total: 105 minutes** — Complete understanding

---

## 🚀 Getting Started

### Step 1: Setup (30 minutes)
```bash
cd /home/shumway/projects/Corvin-Marketplace/plugins/contributor/media/video_producer

# Follow PHASE-2-SETUP-CHECKLIST.md
# - Verify Python environment
# - Verify Blender installation
# - Create feature branch
# - Create stub files
```

### Step 2: Read Documentation (40 minutes)
```bash
# Read minimum docs
cat PHASE-2-BLENDER-RENDERING-HANDOFF.md
cat BLENDER-SCENE-SCHEMA.md
```

### Step 3: Review Phase 1 Code (30 minutes)
```bash
# Understand existing Blender integration
cat src/blender_async_executor.py | head -100
cat src/blender_renderer.py | head -100

# Run existing tests
pytest tests/test_phase3_renderers.py -v -k blender
```

### Step 4: Start Implementation (Weeks 1–3)
```bash
# Week 1: Scene Builder + Material Library
# Week 2: Animation Controller + Quality Metrics
# Week 3: Testing + Integration

# See PHASE-2-SETUP-CHECKLIST.md for detailed sequence
```

---

## 🧪 Testing Your Work

### Run All Phase 2 Tests
```bash
pytest tests/test_phase2_blender_pipeline.py -v
```

### Run Specific Component Test
```bash
# Scene Builder tests
pytest tests/test_phase2_blender_pipeline.py::test_scene_builder_* -v

# Material Library tests
pytest tests/test_phase2_blender_pipeline.py::test_material_library_* -v
```

### Check Coverage
```bash
pytest tests/test_phase2_blender_pipeline.py --cov=src --cov-report=html
# Open: htmlcov/index.html
```

---

## 📋 Success Criteria

When Phase 2 is complete:

- [ ] Scene Builder generates .blend files from JSON schema
- [ ] Material Library creates PBR materials + assigns to objects
- [ ] Animation Controller wires keyframes to Blender timeline
- [ ] Quality Metrics predicts render time + scores quality
- [ ] Learning Loop integration working (ADR-0314 feedback)
- [ ] 15+ tests passing (>80% coverage)
- [ ] No linter errors or warnings
- [ ] ADR-0704 written + committed to Corvin-ADR
- [ ] DEPLOYMENT_STATUS.md updated with Phase 2 results

---

## 💡 Key Concepts

### Blender Python API
- Scenes: `bpy.data.scenes.new()`
- Objects: `bpy.data.objects.new()`, `scene.collection.objects.link()`
- Materials: `bpy.data.materials.new()`
- Keyframes: `obj.keyframe_insert()` on properties

### JSON Scene Schema
- Objects, cameras, lights, materials defined as JSON
- Keyframes relative to scene start (frame 0)
- All animations via keyframe lists (no curves yet)

### Learning Loop (ADR-0314)
- Record execution events (tier, duration, quality)
- Collect feedback (user satisfaction, quality assessment)
- Optimizer learns tier preferences over time

### Tier System
- Tier 1 (Quick): Always available
- Tier 1.5 (Three.js): GPU 3D
- Tier 2 (Manim): Math animation
- Tier 3 (Blender): Premium 3D ← **You are here**

---

## 🔗 External Resources

### Blender Python API
- https://docs.blender.org/api/current/
- https://docs.blender.org/manual/en/latest/scripting/

### Cycles Rendering
- https://docs.blender.org/manual/en/latest/render/cycles/

### PBR Materials
- https://docs.blender.org/manual/en/latest/shader_nodes/introduction.html
- https://learnopengl.com/PBR/Theory

---

## 📞 Support

### If You Need Help

**Understanding the schema?**
→ Read BLENDER-SCENE-SCHEMA.md complete example

**How to use async executor?**
→ See PHASE-2-BLENDER-RENDERING-HANDOFF.md § API Reference

**How to wire learning loop?**
→ See PHASE-2-BLENDER-RENDERING-HANDOFF.md § Learning Integration

**Blender API question?**
→ https://docs.blender.org/api/current/

---

## 📅 Timeline

```
Week 1 (2026-09-24 — 2026-09-30)
├── Day 1–2: Scene Builder
├── Day 3–4: Material Library
└── Day 5: Integration + commit

Week 2 (2026-10-01 — 2026-10-07)
├── Day 1–2: Animation Controller
├── Day 3: Quality Metrics
└── Day 4–5: Learning Loop + E2E tests + commit

Week 3 (2026-10-08 — 2026-10-14)
├── Full test suite
├── Fix any issues
├── ADR-0704 + DEPLOYMENT_STATUS.md update
└── Final review + merge
```

---

## ✨ Next Phase Preview

After Phase 2 completes:

**Phase 3:** Production hardening + marketplace release
- Bundle all components into installable package
- Run integration tests
- Deploy to marketplace v2.0.0
- Monitor learning loop convergence

---

## 🎬 Ready?

1. ✅ You've read this README
2. ✅ Follow [PHASE-2-SETUP-CHECKLIST.md](PHASE-2-SETUP-CHECKLIST.md)
3. ✅ Read [PHASE-2-BLENDER-RENDERING-HANDOFF.md](PHASE-2-BLENDER-RENDERING-HANDOFF.md)
4. ✅ Study [BLENDER-SCENE-SCHEMA.md](BLENDER-SCENE-SCHEMA.md)
5. ✅ Start with `src/scene_builder.py`

**Good luck! 🚀**

---

**Document Version:** 1.0  
**Last Updated:** 2026-09-24  
**Status:** READY FOR DEVELOPMENT

