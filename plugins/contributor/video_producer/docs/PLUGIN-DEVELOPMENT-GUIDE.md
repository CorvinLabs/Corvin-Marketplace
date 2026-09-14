# Plugin Development Guide: Building on Video Producer

This guide demonstrates best practices for building a self-contained, production-quality plugin using **Video Producer Skill 2.0** as a template.

---

## How We Built Video Producer

### 1. Plugin Structure

```
plugins/contributor/video_producer/
├── src/
│   ├── maestro.py                    # Orchestrator
│   ├── phase5/
│   │   ├── renderers/
│   │   │   ├── tier1_quick.py        # Tier 1 renderer
│   │   │   ├── tier2_manim.py        # Tier 2 renderer
│   │   │   └── tier3_premium.py      # Tier 3 renderer
│   │   ├── fallback_router.py        # Fallback logic
│   │   ├── voice_sync_mapper.py      # Voice-sync timing
│   │   ├── asset_library.py          # Asset management
│   │   ├── storyboard/
│   │   │   ├── parser.py             # JSON parsing
│   │   │   └── validator.py          # Schema validation
│   │   └── compositor.py             # Video assembly
│   └── learning/
│       ├── didactic_optimizer.py     # Learning loop
│       └── tier_selector.py          # Tier selection
├── tests/
│   ├── test_tier1_renderer.py        # Unit tests
│   ├── test_maestro_workflow.py      # Integration tests
│   └── e2e/
│       └── test_full_pipeline.py     # E2E tests
├── panel/                             # Console UI
│   └── video-producer-stats.tsx
├── docs/                              # Documentation (YOU ARE HERE)
│   ├── ADR-0001-director-mode.md     # Design decisions
│   ├── ADR-0002-3tier-animation.md
│   ├── ADR-0003-didactic-storyboard.md
│   ├── CONCEPT-0001-orchestrated-skills.md
│   ├── ARCHITECTURE.md               # System overview
│   ├── IMPLEMENTATION-PLAN.md        # Phase breakdown
│   ├── ADR-GRAPH.md                  # Decision map
│   └── README.md                      # Entry point
├── plugin.json                        # Manifest
├── setup.py                           # Dependencies
├── README.md                          # User-facing docs
└── requirements.txt                   # Python deps
```

---

## How to Write Plugin ADRs

### Key Principle: Plugin ADRs Are Self-Contained

**Unlike central ADRs in Corvin-ADR, plugin ADRs:**
- Use **plugin-local numbering** (`video-producer:ADR-0001`, NOT `ADR-0740`)
- Live in `docs/`, not in a central repository
- Link to each other using plugin-local IDs
- Include `plugin_info` frontmatter block

### Frontmatter Template

```yaml
---
id: plugin-name:ADR-NNNN
status: proposed|accepted|deprecated
depends_on: [plugin-name:ADR-0001, plugin-name:CONCEPT-0001]
related: [plugin-name:ADR-0002]
paths:
  - "src/module/file.py"
  - "src/subdir/"
docs:
  - "docs/ARCHITECTURE.md"
  - "docs/ADR-GRAPH.md"
plugin_info:
  name: "plugin-name-skill-2.0"
  version: "2.0.0"
  marketplace_path: "plugins/category/plugin-name"
---
```

### Example: Video Producer ADR-0001

```markdown
---
id: video-producer:ADR-0001
status: accepted
depends_on: []
related: [video-producer:ADR-0002]
paths:
  - "src/"
  - "src/phase5/"
docs:
  - "docs/ARCHITECTURE.md"
  - "docs/IMPLEMENTATION-PLAN.md"
plugin_info:
  name: "video-producer-skill-2.0"
  version: "2.0.0"
  marketplace_path: "plugins/contributor/video_producer"
---

# ADR-NNNN: Title
...
```

### What Should Be an ADR?

✅ **Write an ADR when:**
- Major design choice (e.g., 3-tier vs. single-tier architecture)
- New protocol/interface/schema (TierRenderer contract)
- Irreversible decision (fallback order: Tier 3→2→1)
- Load-bearing constraint (voice-sync immutability)
- Cross-module coupling (learning loop integration)

❌ **Don't write an ADR when:**
- Bug fix with no behavior change
- Pure refactoring (same functionality, cleaner code)
- Config tuning (parameter adjustments)
- Test-only or docs-only changes

### Linking Plugin ADRs

```markdown
# ADR-0002: Foo

**Depends On:** [video-producer:ADR-0001]
**Related To:** [video-producer:ADR-0003]
**Paths:** src/foo.py, src/bar.py
**Docs:** docs/ARCHITECTURE.md

In the text:
- Reference related decisions: "See [video-producer:ADR-0001] for the design rationale."
- Use full IDs (video-producer:ADR-NNNN) for clarity
```

---

## How to Test

### Unit Tests (Component-Level)

Test individual classes/functions in isolation.

```python
# tests/test_tier1_renderer.py
import pytest
from src.phase5.renderers.tier1_quick import Tier1QuickRenderer

def test_tier1_quick_renderer_succeeds():
    """Tier 1 always succeeds; no dependencies."""
    renderer = Tier1QuickRenderer()
    assert renderer.dependencies_met()
    
    result = renderer.execute(AnimationRequest(...))
    assert result.success
```

### Integration Tests (Workflow-Level)

Test how components work together.

```python
# tests/test_maestro_workflow.py
def test_maestro_orchestrates_full_pipeline():
    """End-to-end: storyboard → frames → MP4."""
    maestro = Maestro(storyboard="learning-loop-v1.json")
    result = maestro.execute()
    
    assert result.success
    assert Path(result.output_path).exists()
    assert result.duration_seconds > 0
    assert len(result.audit_events) > 0
```

### E2E Tests (Real Execution)

Test the full plugin running end-to-end, like an operator would.

```python
# tests/e2e/test_full_pipeline.py
def test_e2e_generate_learning_loop_video():
    """Generate a real demo video; verify output is valid."""
    result = maestro.execute(storyboard_id="learning-loop")
    
    # Verify output MP4 is valid
    assert ffprobe(result.output_path).duration > 0
    
    # Verify hash reproducibility
    result2 = maestro.execute(storyboard_id="learning-loop")
    assert result.output_hash == result2.output_hash
    
    # Verify audit trail
    assert len(result.audit_events) == len(result2.audit_events)
```

### Test Running

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_tier1_renderer.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run E2E tests only (slower)
pytest tests/e2e/ -v
```

---

## How to Package & Distribute

### 1. Define Dependencies (setup.py)

```python
from setuptools import setup, find_packages

setup(
    name="video-producer-skill-2.0",
    version="2.0.0",
    packages=find_packages(),
    install_requires=[
        "anthropic>=0.7.0",
        "pydantic>=2.0",
        "pyyaml>=6.0",
        "manim>=0.18.0",  # Optional: Tier 2 only
        "ffmpeg-python>=0.2.3",
        "librosa>=0.10.0",
        "pillow>=10.0.0",
    ],
    extras_require={
        "manim": ["manim>=0.18.0", "ffmpeg-python>=0.2.3"],
        "dev": ["pytest>=7.0", "pytest-cov>=4.0"],
    },
)
```

### 2. Create Plugin Manifest (plugin.json)

```json
{
  "id": "video-producer-skill-2.0",
  "name": "Video Producer Skill 2.0",
  "version": "2.0.0",
  "category": "video",
  "description": "Generate educational/marketing videos from storyboards",
  "author": "Corvin Labs",
  "license": "Apache-2.0",
  
  "entry_point": "src.maestro:Maestro",
  
  "documentation": "docs/README.md",
  "adr_prefix": "video-producer",
  "docs_location": "docs/",
  "development_guide": "docs/PLUGIN-DEVELOPMENT-GUIDE.md",
  "adr_graph": "docs/ADR-GRAPH.md",
  
  "capabilities": [
    {
      "name": "video_generation",
      "version": "2.0.0",
      "parameters": {
        "storyboard_id": "string",
        "didactic_level": "enum[beginner,technical]",
        "tier_preference": "int[1,2,3]"
      }
    }
  ],
  
  "dependencies": {
    "internal": [],
    "external": ["manim", "ffmpeg"]
  },
  
  "console_panels": [
    {
      "id": "video-producer-stats",
      "title": "Video Producer Stats",
      "path": "panel/video-producer-stats.tsx"
    }
  ]
}
```

### 3. Package & Upload

```bash
# Create ZIP
zip -r video-producer-skill-2.0.zip \
  src/ tests/ docs/ panel/ \
  plugin.json setup.py README.md requirements.txt

# Upload to Marketplace
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -F "plugin=@video-producer-skill-2.0.zip" \
  https://marketplace.corvin-labs.com/api/plugins/upload

# Or use CLI
corvinctl marketplace upload video-producer-skill-2.0.zip
```

---

## Best Practices Applied in Video Producer

### 1. Design-First (ADRs Before Code)

✅ We wrote ADR-0001/0002/0003 BEFORE implementation  
✅ Each ADR documents a design choice + alternatives considered  
✅ ADRs are referenced in code via `paths:` field

### 2. Self-Contained Documentation

✅ All ADRs live in `docs/`, not in central repos  
✅ ARCHITECTURE.md explains the full system  
✅ IMPLEMENTATION-PLAN.md breaks down phases + gates  
✅ ADR-GRAPH.md shows decision dependencies

### 3. Test-Driven Development

✅ Tests written alongside features (TDD)  
✅ Unit + Integration + E2E coverage  
✅ Audit trail verified in tests

### 4. Learning Integration

✅ Every execution emits `SkillExecutedEvent`  
✅ Feedback loop integrated from day 1  
✅ Optimizer learns tier preferences

### 5. Audit-First Design

✅ Every decision logged + hash-chained  
✅ Reproducibility verified in tests  
✅ Operator can audit full history

### 6. Graceful Degradation

✅ Tier 3 fails → Tier 2 → Tier 1  
✅ Always produces something (or explicit error)  
✅ No silent partial failures

---

## How to Adapt This Pattern

### For a Different Plugin

1. **Copy the structure** (src/, tests/, docs/, panel/)
2. **Rename plugin-local IDs** (video-producer:ADR-NNNN → your-plugin:ADR-NNNN)
3. **Replace components** (TierRenderer → your abstraction)
4. **Update documentation** (ARCHITECTURE, IMPLEMENTATION-PLAN, ADR-GRAPH)
5. **Test thoroughly** (Unit + Integration + E2E)
6. **Deploy** (ZIP → Marketplace)

### Checklist for New Plugin

- [ ] Create `src/`, `tests/`, `docs/`, `panel/` directories
- [ ] Write 3+ ADRs documenting major design choices
- [ ] Create ARCHITECTURE.md (component overview + data flow)
- [ ] Create IMPLEMENTATION-PLAN.md (phases + deliverables)
- [ ] Create plugin.json manifest
- [ ] Write unit tests (target: 80%+ coverage)
- [ ] Write integration tests (workflows)
- [ ] Write E2E tests (real execution)
- [ ] Create console panel (optional, but recommended)
- [ ] Document learning integration (if applicable)
- [ ] Test reproducibility (same input → same output)
- [ ] Verify audit trail logging
- [ ] Package + upload to Marketplace

---

## Resources

- **[ARCHITECTURE.md](./ARCHITECTURE.md)** — System design + components
- **[ADR-0001](./ADR-0001-director-mode.md)** — High-level design
- **[ADR-0002](./ADR-0002-3tier-animation.md)** — Renderer architecture
- **[ADR-0003](./ADR-0003-didactic-storyboard.md)** — Data schema
- **[IMPLEMENTATION-PLAN.md](./IMPLEMENTATION-PLAN.md)** — Phase breakdown

---

**Next Steps:**
1. Read ARCHITECTURE.md for the full picture
2. Study ADR-0001/0002/0003 for design rationale
3. Explore tests/ to see TDD in action
4. Adapt this pattern for your own plugin

**Happy building!** 🚀
