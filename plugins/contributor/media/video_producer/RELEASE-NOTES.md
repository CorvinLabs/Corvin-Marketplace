# Video Producer Plugin — Release Notes

## Version 1.2.0 (2026-10-09)

### What's new
- **One look across every slide.** The footer carries the real CorvinOS mark (chevron, underscore bar, gold dot). A slide the model describes badly is now rebuilt as a web quote slide from its own narration — the plain "EXAMPLE" placeholder slide no longer appears in LLM-written videos.
- **Overlap detection.** Every web slide is measured in the browser once its animation has settled (`src/web_layout.py`): text over text, text across a box edge, boxes overlapping, clipped text and text off the stage are reported. A colliding slide is swapped for a clean quote slide and listed in the job metadata (`layout_collisions`). Templates were fixed where the check found real defects (chart labels wrap, dense diagrams use compact cards, long words break instead of leaving their card).
- **Grounded explainers (ADR-2240, host-gated).** For Corvin topics the console can hand the storyboard a fact pack from the knowledge base and the code (`src/grounding.py`, `src/grounded_storyboard.py`); claims in the storyboard are checked against it. New `console_still` template (bundled console screenshots with hotspots) and a "you are here" layer strip. This only runs where the host builds a pack; elsewhere the plugin behaves as before.
- **Softer background glow** on every slide.

### Known limits
- A diagram with six or more nodes shrinks its labels to fit; they stay readable but small.
- If every field of a slide is at its maximum length the slide can still collide; it is then replaced by a quote slide (see above).
- The storyboard model's duration guesses and the real narration length can differ by more than 10 %; the video follows the narration.

### Verified by
`tests/test_layout_check.py` (collision kinds with positive controls, all templates, a pipeline E2E with a real collision), the plugin suite, and the console's fresh-install lifecycle spec: install from this repository on GitHub, panel in the sidebar, a video produced through the panel and checked (h264 1920x1080, audio, no subtitles, every scene a web slide, the gold dot of the mark present, motion over time), uninstall.

## Version 1.1.0 — Production Ready (2026-10-09)

**This is the first production-ready release.** The plugin has been stabilized, documented, and tested end-to-end.

### 🎉 What's New

#### Web-Slide Rendering (ADR-2238)
- **14 built-in slide templates** with smooth animations (line charts, donuts, flow graphs, timelines, cycles, 3D layers, stats, diagrams, comparisons, quotes, code blocks)
- **Deterministic rendering:** Headless Chromium with timeline seeking produces bit-identical frames every run
- **Ambient motion loops:** Infinite CSS animations (pulses, orbits, shine effects) seamlessly repeat without jumps
- **D3-equivalent geometry in Python:** Nice axis ticks, monotone cubic curves, DAG graph layout — all computed deterministically without JavaScript
- **Fallback to Pillow:** If Chromium is unavailable, videos still render with classic static slides

#### OpenAI TTS Default (ADR-2211)
- **Natural narration:** OpenAI TTS (`tts-1-hd`, voice `onyx`) is now the default
- **Fallback chain:** If OpenAI key is absent or API fails, automatically falls back to edge-tts → Piper → silent mock
- **Quality metadata:** Every job records which TTS engine actually ran (`tts_provider_used`)

#### Claude Storyboard (new default)
- **Repair pass:** invalid web-slide specs go back to the model once with the exact errors
- **Faster & better:** Claude Sonnet generates storyboards in ~14s with 8/8 valid templates (vs. qwen3's ~65s with some failures)
- **Gated by L35/L34:** Only runs if egress policy allows `api.anthropic.com` and data classification permits `claude_code` engine
- **Fallback to Ollama:** If API is forbidden, storyboards run locally
- **Model choice:** Automatically uses newest Claude Sonnet version via `model_selector.tier_model("sonnet")`

#### Documentation Overhaul
- **USER-GUIDE.md** — Step-by-step for Marketplace users (examples, troubleshooting, tips)
- **README.md updated** — Reflects the live implementation (storyboard → TTS → web slides → MP4)
- **WEB-SLIDES.md** — Comprehensive template reference with data contracts and animation specs

### ✅ What Works Now

- ✅ Post a task description, get a narrated video in 2–3 minutes
- ✅ 14 slide templates with smooth animations
- ✅ Professional design in corvin-labs.com brand language (Newsreader font, Amber accent, dark/light themes)
- ✅ Natural human-sounding narration (OpenAI TTS by default)
- ✅ 1920×1080 MP4 output at 30fps
- ✅ Job metadata tracks which AI models and TTS engines ran
- ✅ E2E tests verify the full pipeline

### ⚠️ What's Not Done

- **Figma integration:** Token sync is implemented but never verified live (no Figma token on dev host)
- **Subtitles:** Deliberately not included (ADR-2211 design decision — optimized for narration-only)
- **Custom templates:** Slide templates are fixed (but AI picks the best one per scene)

### 🔄 Breaking Changes

None. Version 1.1.0 is fully backward-compatible with 1.0.0.

### 📦 Dependencies

- Python 3.11+
- `playwright` (for Chromium headless rendering) — optional but recommended
- `openai` (for TTS) — required if using `tts_engine: "openai"` (default)
- `ffmpeg` (for video assembly)

### 🧪 Testing

91 tests passed on the development host (2026-10-09): `tests/test_skill.py`, `test_models.py`, `test_storage.py`, `test_web_charts.py`, `test_web_slides_e2e.py` (see README, Testing). Pre-existing red tests: four in `test_api_routes.py` and one icon call-site test.

### 📝 Migration from 1.0.0

No action needed. The plugin is 100% backward-compatible. Existing job configs still work; new jobs will use the improved features automatically.

### 🔗 Related ADRs

- **[ADR-2238](../../Corvin-Knowledge/decisions/ADR-2238-video-producer-deterministic-web-slide-renderer-html-css.md)** — Web-slide renderer design
- **[ADR-2211](../../Corvin-Knowledge/decisions/ADR-2211-video-producer-openai-tts-default-and-layout-collision-resolution.md)** — OpenAI TTS + quality improvements

---

## Version 1.0.0 — Initial Release (2026-10-03)

- Basic storyboard → TTS → Pillow slides → MP4 pipeline
- Placeholder documentation (refers to never-activated 3-tier architecture)
- No web-slide rendering
- No quality improvements

---


**Questions?** See [USER-GUIDE.md](USER-GUIDE.md) or contact the plugin maintainers.

