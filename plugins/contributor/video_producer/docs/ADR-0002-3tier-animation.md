---
id: video-producer:ADR-0002
status: accepted
depends_on: [video-producer:ADR-0001]
related: [video-producer:ADR-0003]
paths:
  - "src/phase5/"
docs:
  - "docs/ARCHITECTURE.md"
plugin_info:
  name: "video-producer-skill-2.0"
  version: "2.0.0"
---

# ADR-0002: 3-Tier Animation Architecture

**Status:** ACCEPTED  
**Decision:** Implement tiered renderer interface with fallback algorithm  
**Depends On:** [video-producer:ADR-0001]  
**Related To:** [video-producer:CONCEPT-0001, video-producer:ADR-0003]

**Paths:**
- `src/phase5/`
- `src/phase5/renderers/tier1_quick.py`
- `src/phase5/renderers/tier2_manim.py`
- `src/phase5/renderers/tier3_premium.py`

**Docs:**
- `docs/ARCHITECTURE.md`

---

## Executive Summary

Define a unified `TierRenderer` interface so that Tier 1 (ASCII), Tier 2 (Manim), and Tier 3 (Premium) can be swapped transparently. The `FallbackRouter` attempts each tier in sequence until one succeeds.

**Key Contract:**
```python
class TierRenderer(ABC):
  @abstractmethod
  def execute(self, request: AnimationRequest) -> AnimationResult:
    """Execute animation rendering. Return success flag + output path or error."""
    pass
  
  def tier_level(self) -> int:
    return self._tier  # 1, 2, or 3
  
  def dependencies_met(self) -> bool:
    """Check if this tier's dependencies are available."""
    pass
```

---

## Tier 1: Quick Renderer (ASCII + Simple SVG)

### Specification
```python
class Tier1QuickRenderer(TierRenderer):
  """Minimal animation renderer for rapid prototyping"""
  
  def execute(self, request: AnimationRequest) -> AnimationResult:
    # No external dependencies beyond PIL
    # Generate simple SVG or ASCII art
    # Composite into 30 FPS video
    # Duration: ~10s per scene
    # Fallback for: Tier 2/3 unavailable
  
  def dependencies_met(self) -> bool:
    # PIL always available; return True
    return True
```

### Output Characteristics
- **Fidelity:** Low (ASCII/simple SVG)
- **Duration:** 10s per scene
- **File size:** ~1 MB per 60s video
- **Dependencies:** Python standard library + PIL
- **Failure modes:** None (always succeeds)

### Use Cases
- Drafts / prototypes
- Testing storyboard structure
- Fallback when Manim unavailable
- Quick preview for operator approval

---

## Tier 2: Rich Renderer (Manim)

### Specification
```python
class ManimAnimatorWorker(TierRenderer):
  """Manim (Mathematical Animation Engine) renderer for professional animations"""
  
  def execute(self, request: AnimationRequest) -> AnimationResult:
    # Load scene spec from asset library
    # Generate Manim scene script (Python code)
    # Render via manim subprocess
    # Verify output (duration, hash, validity)
    # Duration: ~60s per scene
    # Fallback for: Tier 3 unavailable
  
  def dependencies_met(self) -> bool:
    # Check if 'manim' command is available
    try:
      subprocess.run(['manim', '--version'], capture_output=True, timeout=5)
      return True
    except:
      return False
```

### Output Characteristics
- **Fidelity:** Medium (professional-grade animations)
- **Duration:** 60s per scene (first render) or cached
- **File size:** ~5-10 MB per 60s video
- **Dependencies:** manim, ffmpeg, latex
- **Failure modes:** Timeout, missing dependencies, rendering error

### Use Cases
- Educational videos
- Marketing videos
- Technical documentation
- Learning content with animations

### Implementation Details
- **Scene Specs:** Loaded from `assets/manifest.json`
- **Subprocess Timeout:** 60s hard limit (kill process)
- **Caching:** Store rendered MP4s by animation_id + hash
- **Fallback:** If manim unavailable, try Tier 1

---

## Tier 3: Premium Renderer (Hand-Crafted)

### Specification
```python
class Tier3PremiumRenderer(TierRenderer):
  """Premium hand-crafted video loader"""
  
  def execute(self, request: AnimationRequest) -> AnimationResult:
    # Load pre-rendered MP4 from asset library
    # Validate checksum
    # Return file path
    # Duration: N/A (human-created)
    # No fallback (highest quality)
  
  def dependencies_met(self) -> bool:
    # Check if premium asset exists
    return self.asset_library.has_asset(request.animation_id)
```

### Output Characteristics
- **Fidelity:** High (bespoke, hand-crafted)
- **Duration:** N/A (pre-created)
- **File size:** Variable (bespoke)
- **Dependencies:** Asset library access
- **Failure modes:** Asset not found

### Use Cases
- Launch announcements
- Keynote videos
- High-profile marketing
- Any video where custom cinematography is justified

---

## Fallback Router Algorithm

### Pseudocode
```python
class FallbackRouter:
  def __init__(self):
    self.tier_renderers = {
      3: Tier3PremiumRenderer(),
      2: ManimAnimatorWorker(),
      1: Tier1QuickRenderer(),
    }
  
  def execute(self, request: AnimationRequest) -> AnimationResult:
    audit_event = {
      "event_type": "animation_fallback_attempt",
      "animation_id": request.animation_id,
      "tiers_attempted": []
    }
    
    for tier_num in [3, 2, 1]:
      renderer = self.tier_renderers[tier_num]
      
      # Skip if dependencies not met
      if not renderer.dependencies_met():
        audit_event["tiers_attempted"].append({
          "tier": tier_num,
          "status": "skipped",
          "reason": "dependencies_not_met"
        })
        continue
      
      try:
        result = renderer.execute(request)
        
        if result.success:
          audit_event["tiers_attempted"].append({
            "tier": tier_num,
            "status": "success",
            "output_path": str(result.output_path),
            "output_hash": result.output_hash,
            "render_time_ms": result.render_time_ms
          })
          audit_log(audit_event)
          return result
        else:
          audit_event["tiers_attempted"].append({
            "tier": tier_num,
            "status": "failed",
            "error": result.error
          })
      
      except Exception as e:
        audit_event["tiers_attempted"].append({
          "tier": tier_num,
          "status": "exception",
          "error": str(e)
        })
        continue
    
    # All tiers exhausted
    audit_event["final_status"] = "all_tiers_failed"
    audit_log(audit_event)
    return AnimationResult(
      animation_id=request.animation_id,
      success=False,
      error="All tiers exhausted; no animation rendered"
    )
```

### Execution Order
1. **Tier 3 (Premium):** Try first if hand-crafted asset exists
2. **Tier 2 (Manim):** Try if Tier 3 fails or unavailable
3. **Tier 1 (Quick):** Final fallback (always succeeds)

### Caching
```python
class RenderCache:
  def __init__(self, cache_dir: Path):
    self.cache_dir = cache_dir  # e.g., /tmp/render_cache/
  
  def get(self, animation_id: str, output_hash: str) -> Optional[Path]:
    # Return cached output if exists and hash matches
    cache_file = self.cache_dir / f"{animation_id}_{output_hash}.mp4"
    if cache_file.exists():
      return cache_file
    return None
  
  def set(self, animation_id: str, output_hash: str, output_path: Path):
    # Cache the output for future use
    cache_file = self.cache_dir / f"{animation_id}_{output_hash}.mp4"
    shutil.copy(output_path, cache_file)
```

---

## Data Structures

### AnimationRequest
```python
@dataclass
class AnimationRequest:
  animation_id: str              # "learning-loop"
  concept_id: str                # "learning-loop"
  didactic_level: str            # "beginner" | "technical"
  duration_seconds: int          # requested duration
  assets: List[str]              # asset dependencies
  output_format: str             # "mp4" | "webm"
  tier: Optional[int] = None     # preferred tier (None = auto-select)
  preferred_tier: int = 2        # default to Manim if available
```

### AnimationResult
```python
@dataclass
class AnimationResult:
  animation_id: str
  success: bool
  output_path: Optional[Path] = None    # path to MP4
  output_hash: Optional[str] = None     # SHA256
  duration_seconds: float = 0           # actual duration
  render_time_ms: int = 0               # time to render
  tier_used: int = 0                    # which tier succeeded
  error: Optional[str] = None
```

---

## Audit Trail Integration

### Required Events
```json
{
  "event_type": "animation_tier_attempt",
  "animation_id": "learning-loop",
  "tier": 2,
  "status": "success|failed|skipped",
  "error": "...",
  "timestamp": "2026-09-14T13:00:00Z",
  "tenant_id": "_default"
}
```

All tier attempts logged, enabling:
- Debugging (which tiers are failing?)
- Metrics (Tier 2 success rate vs. Tier 1 fallback rate)
- Audit trail (which video used which tier?)

---

## Error Handling

### Tier-Level Errors
```
Tier 3 (Premium):
  ├─ Asset not found → skip, try Tier 2
  ├─ Checksum mismatch → skip, try Tier 2
  └─ File corrupted → skip, try Tier 2

Tier 2 (Manim):
  ├─ Scene script generation fails → try Tier 1
  ├─ Manim not installed → skip, try Tier 1
  ├─ Subprocess timeout (60s) → try Tier 1
  ├─ Output verification fails → try Tier 1
  └─ Memory error → try Tier 1

Tier 1 (Quick):
  ├─ PIL import fails → CRITICAL ERROR (should never happen)
  └─ (otherwise always succeeds)
```

---

## Testing Strategy

### Tier 1 Tests
- `test_tier1_always_succeeds`
- `test_tier1_no_dependencies`
- `test_tier1_output_valid`

### Tier 2 Tests
- `test_tier2_manim_renders`
- `test_tier2_timeout_enforced`
- `test_tier2_hash_reproducible`
- `test_tier2_missing_dependencies_skipped`

### Tier 3 Tests
- `test_tier3_loads_premium_asset`
- `test_tier3_validates_checksum`
- `test_tier3_asset_not_found_skipped`

### Fallback Router Tests
- `test_fallback_tier3_fails_tier2_succeeds`
- `test_fallback_tier2_fails_tier1_succeeds`
- `test_fallback_all_tiers_fail_returns_error`
- `test_fallback_audit_logged`
- `test_cache_prevents_rerender`

---

## Performance Characteristics

| Tier | Cold Start | Cached | Memory | CPU | Disk |
|------|-----------|--------|--------|-----|------|
| **1** | 10s | 5s | 500 MB | Low | 1 MB |
| **2** | 60s | 5s | 2 GB | High | 5-10 MB |
| **3** | <1s | <1s | 500 MB | None | 10+ MB |

**Implication:** Cache aggressively; prefer cached Tier 2 over cold Tier 1.

---

## Load-Bearing Constraints

### 1. Fallback is Deterministic
Same `AnimationRequest` always tries tiers in same order (3→2→1). Never randomize.

### 2. Tier Availability is Immutable During Execution
Don't check `dependencies_met()` mid-render. Check once at start; if a renderer starts, it must finish (or timeout).

### 3. Error Messages Must Indicate Tier
Every error must include which tier failed: `"Tier 2 (Manim) timeout: ..."`

### 4. Caching Uses Output Hash
Cache key = `animation_id + output_hash`. Same scene + different hash = regenerate (not reuse).

---

## Related ADRs & Concepts

- **video-producer:CONCEPT-0001:** 3-Tier Animation & Didactic Storyboards
- **video-producer:ADR-0001:** Director Mode Advanced (high-level design)
- **video-producer:ADR-0003:** Didactic Storyboard System (schema + voice-sync)

---

**Status: ACCEPTED — Deployed and in production**
