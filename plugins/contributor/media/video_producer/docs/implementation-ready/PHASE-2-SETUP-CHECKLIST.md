# Phase 2 Development Setup — Checklist

**Status:** 🟢 **Ready to Begin**  
**Date:** 2026-09-24  
**Developer:** [Your Name]  
**Task ID:** #1 (Video Producer Plugin: Phase 2 Blender Rendering Extension)

---

## ✅ Pre-Development Checklist

### 1. Repository Setup

- [ ] Clone the Marketplace repository
  ```bash
  cd /home/shumway/projects/Corvin-Marketplace
  git status
  git pull origin main
  ```

- [ ] Navigate to plugin directory
  ```bash
  cd plugins/contributor/media/video_producer
  pwd
  ```

- [ ] Verify Phase 1 files exist
  ```bash
  ls -la src/blender_async_executor.py
  ls -la src/blender_renderer.py
  ```

### 2. Python Environment

- [ ] Check Python version (≥3.9)
  ```bash
  python3 --version
  ```

- [ ] Create virtual environment (optional)
  ```bash
  python3 -m venv venv
  source venv/bin/activate  # Linux/macOS
  # or: venv\Scripts\activate  # Windows
  ```

- [ ] Install dependencies
  ```bash
  pip install -r requirements.txt
  ```

- [ ] Verify Blender installation
  ```bash
  blender --version
  ```

### 3. Test Environment

- [ ] Run existing Phase 1 tests
  ```bash
  pytest tests/ -v --tb=short
  ```

- [ ] Run Blender-specific tests
  ```bash
  pytest tests/test_phase3_renderers.py -v -k blender
  ```

- [ ] Expected output: All tests passing ✅

### 4. Git Setup

- [ ] Create a feature branch for Phase 2
  ```bash
  git checkout -b phase2/blender-3d-pipeline
  ```

- [ ] Verify branch is active
  ```bash
  git branch
  git status
  ```

---

## 📚 Documentation Review

Read these in order to understand the codebase:

- [ ] **PHASE1_IMPLEMENTATION_REPORT.md**
  - Understand Phase 1 deliverables
  - Review Maestro orchestrator architecture

- [ ] **DEPLOYMENT_STATUS.md**
  - Review production constraints
  - Understand tier system (1, 1.5, 2, 3)

- [ ] **PHASE-2-BLENDER-RENDERING-HANDOFF.md**
  - This is your **primary handoff document**
  - Reviews what's done, what's next

- [ ] **BLENDER-SCENE-SCHEMA.md**
  - This is your **specification**
  - JSON schema for 3D scenes
  - Reference while implementing Scene Builder

### Recommended Reading Order

1. PHASE-2-BLENDER-RENDERING-HANDOFF.md (10 min)
2. BLENDER-SCENE-SCHEMA.md (15 min)
3. src/blender_async_executor.py (10 min)
4. src/blender_renderer.py (15 min)
5. src/learning_event_store.py (10 min)
6. tests/test_phase3_renderers.py (15 min)

**Total:** ~75 minutes of reading

---

## 🛠️ Development Setup

### 1. Create Phase 2 Directories

```bash
mkdir -p src/tests
```

### 2. Create Stub Files (Start Here)

Create empty Python files for each Phase 2 component:

```bash
touch src/scene_builder.py
touch src/material_library.py
touch src/animation_controller.py
touch src/blender_quality_metrics.py
touch tests/test_phase2_blender_pipeline.py
```

### 3. Verify File Structure

```bash
tree -L 2 src/
# Expected:
# src/
# ├── scene_builder.py                    (NEW - empty)
# ├── material_library.py                 (NEW - empty)
# ├── animation_controller.py             (NEW - empty)
# ├── blender_quality_metrics.py          (NEW - empty)
# ├── blender_async_executor.py           (EXISTS - Phase 1)
# ├── blender_renderer.py                 (EXISTS - Phase 1)
# ├── maestro.py                          (EXISTS - Phase 1)
# ├── voice_synthesizer.py                (EXISTS - Phase 1)
# └── ... (other Phase 1 files)
```

---

## 📋 Implementation Sequence

### Week 1: Scene Builder + Material Library

**Day 1–2: Scene Builder (400–500 LoC)**
- [ ] Study BLENDER-SCENE-SCHEMA.md
- [ ] Study Blender Python API basics
- [ ] Implement `scene_builder.py`
  - [ ] Parse JSON schema
  - [ ] Create Blender objects from specs
  - [ ] Wire animations to keyframes
  - [ ] Export .blend file
- [ ] Write 5 unit tests

**Day 3–4: Material Library (200–300 LoC)**
- [ ] Implement `material_library.py`
  - [ ] PBR material definitions
  - [ ] Texture loading
  - [ ] Shader graph generation
- [ ] Write 3 unit tests

**Day 5: Integration + Polish**
- [ ] Wire Scene Builder → Material Library
- [ ] Run all tests
- [ ] Commit: `feat(phase2): implement scene builder + material library`

### Week 2: Animation Controller + Quality Metrics

**Day 1–2: Animation Controller (300–400 LoC)**
- [ ] Implement `animation_controller.py`
  - [ ] Keyframe generation from timing
  - [ ] Camera path animation
  - [ ] Motion curves
- [ ] Write 4 unit tests

**Day 3: Quality Metrics (150–200 LoC)**
- [ ] Implement `blender_quality_metrics.py`
  - [ ] Render time prediction
  - [ ] Quality scoring
- [ ] Write 3 unit tests

**Day 4–5: Learning Loop Integration + E2E Tests**
- [ ] Wire ADR-0314 learning integration
- [ ] Create E2E test: JSON → .blend → render → video
- [ ] Commit: `feat(phase2): implement animation + metrics + learning loop`

### Week 3: Testing + Deployment

- [ ] Run full test suite: `pytest tests/ -v`
- [ ] Fix any failures
- [ ] Update DEPLOYMENT_STATUS.md with Phase 2 results
- [ ] Create ADR-0704 architectural decision record
- [ ] Final commit + PR review

---

## 🧪 Testing Strategy

### Unit Tests (Per Component)

Each component should have dedicated unit tests:

```bash
# Scene Builder tests
pytest tests/test_phase2_blender_pipeline.py::test_scene_builder_* -v

# Material Library tests
pytest tests/test_phase2_blender_pipeline.py::test_material_library_* -v

# Animation Controller tests
pytest tests/test_phase2_blender_pipeline.py::test_animation_controller_* -v

# Quality Metrics tests
pytest tests/test_phase2_blender_pipeline.py::test_quality_metrics_* -v
```

### Integration Tests

Test the full pipeline:

```bash
# Full pipeline: JSON → .blend → render
pytest tests/test_phase2_blender_pipeline.py::test_e2e_blender_pipeline -v
```

### Test Coverage

- [ ] All components have >80% code coverage
- [ ] Run coverage report:
  ```bash
  pytest tests/test_phase2_blender_pipeline.py --cov=src --cov-report=html
  ```

---

## 🔧 Useful Commands

### Development

```bash
# Run tests while developing
pytest tests/test_phase2_blender_pipeline.py -v --tb=short

# Run with verbose output + print statements
pytest tests/test_phase2_blender_pipeline.py -v -s

# Run specific test
pytest tests/test_phase2_blender_pipeline.py::test_scene_builder_parse_json -v

# Watch for changes (install pytest-watch first)
ptw tests/test_phase2_blender_pipeline.py -- -v
```

### Git

```bash
# Check current branch
git branch

# Stage files
git add src/scene_builder.py src/material_library.py

# Commit
git commit -m "feat(phase2): implement scene builder + material library

- Parse JSON scene schema
- Generate .blend files via Blender Python API
- Material assignment + property mapping
- 8 unit tests passing

Tests: 8/8 passing
Coverage: 95%"

# Push to feature branch
git push origin phase2/blender-3d-pipeline
```

### Debugging

```bash
# Print debug info
python3 -c "from src.scene_builder import SceneBuilder; print(SceneBuilder)"

# Test imports
python3 -c "import src.blender_async_executor; print('OK')"

# Inspect Blender API
blender --background --python-expr "import bpy; print(bpy.__version__)"
```

---

## 📞 Getting Help

### If You Get Stuck

| Issue | Solution |
|-------|----------|
| Import error | Verify Python path: `export PYTHONPATH=/path/to/plugin:$PYTHONPATH` |
| Blender not found | Install: `sudo apt install blender` (Linux) or `brew install blender` (macOS) |
| Schema validation error | Check JSON against BLENDER-SCENE-SCHEMA.md |
| Test failures | Run with `-vv` flag for detailed output |
| Performance issues | Profile with `python3 -m cProfile -s cumtime script.py` |

### Code References

- **Blender Python API:** https://docs.blender.org/api/current/
- **Cycles Rendering:** https://docs.blender.org/manual/en/latest/render/cycles/
- **EEVEE Rendering:** https://docs.blender.org/manual/en/latest/render/eevee/
- **Phase 1 Code:** `src/blender_async_executor.py`, `src/blender_renderer.py`

---

## 🎯 Daily Standup Template

Use this template to track progress:

```markdown
## Day N (2026-09-XX)

### Completed
- [ ] Task description

### In Progress
- [ ] Task description

### Blocked
- [ ] Issue + solution plan

### Next
- [ ] Tomorrow's tasks

### Test Status
- Passing: N/N
- Coverage: XX%
```

---

## ✨ Success Criteria (Final Checklist)

### Code Quality
- [ ] All components implemented (4 modules)
- [ ] All tests passing (15+ tests)
- [ ] Code coverage >80%
- [ ] No syntax errors or warnings
- [ ] No linter errors (`pylint`, `flake8`)

### Functionality
- [ ] Scene Builder generates valid .blend files
- [ ] Material Library creates PBR materials
- [ ] Animation Controller generates keyframes
- [ ] Quality Metrics estimates render time
- [ ] Learning Loop integration working

### Documentation
- [ ] Code has docstrings
- [ ] Tests have clear descriptions
- [ ] ADR-0704 created + added to Corvin-ADR
- [ ] DEPLOYMENT_STATUS.md updated

### Git & Deployment
- [ ] Feature branch clean and ready
- [ ] Commit message clear + follows convention
- [ ] PR description complete
- [ ] Tests passing in CI/CD

---

## 📅 Timeline Summary

| Week | Task | Status |
|------|------|--------|
| **Week 1** | Scene Builder + Material Library | 🟡 IN PROGRESS |
| **Week 2** | Animation Controller + Quality Metrics | 🔲 NOT STARTED |
| **Week 3** | Testing + Deployment | 🔲 NOT STARTED |

**Est. Total:** 3 weeks, ~1500–1800 LoC

---

## 🚀 Ready to Start?

1. Complete the **Pre-Development Checklist** above ✅
2. Read the **Documentation Review** section
3. Create the stub files in **Development Setup**
4. Begin implementation from **Implementation Sequence**

**Start with:** `src/scene_builder.py`

Good luck! 🎬

---

**Checklist Version:** 1.0  
**Last Updated:** 2026-09-24  
**Status:** READY FOR DEVELOPMENT

