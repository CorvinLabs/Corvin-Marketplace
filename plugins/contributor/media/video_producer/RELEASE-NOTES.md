# Video Producer Plugin — Release Notes

## Version 1.4.0 (2026-10-10)

### What's new
- **Your own look.** Import a PowerPoint (`.pptx`/`.potx`) as a *style*: palette, fonts (mapped to the three bundled
  families), logo, wordmark and decoration. Pick it in the composer's **Style** chip; set one as the workspace
  default; a revision keeps the original video's style. Without a style nothing changes — the CorvinOS look is
  pinned byte-for-byte by 90 golden hashes. A custom-styled video never shows the CorvinOS mark unless you switch on
  the "made with CorvinOS" credit.
- **Safe by construction.** The deck is read in memory with a hardened, dependency-free reader (zip and XML limits,
  no DTD/entities, no network, macros refused, logos re-encoded as PNG — SVG is dropped), never stored, and slide
  text/notes/author names are never read. Palettes must meet contrast rules before they can be saved; a palette that
  does not is repaired at import or refused.
- **Honest about default colours.** 18 of 29 real decks measured here carry PowerPoint's default palette. Those
  imports get a flagged neutral accent and ask you to choose one instead of silently producing "default blue".
- **Reproducible.** The style is copied next to each video (`videos/<job>/style/`);
  `scripts/style_sources_section.py` prints the Style section for a `sources.md` in Corvin-Videos.
- **Audited and erasable.** Style import/save/delete/use are audit events; the workspace's Video Producer store is
  covered by the GDPR Art. 17 erasure layer (see Known limits).

### Known limits
- Background artwork of slide masters is not reproduced: a spike over 29 decks found layouts to be plain fills plus an
  occasional small logo, so only colours and the logo are taken. (A background-plate mode was evaluated and not built.)
- One look per video: a styled video uses the style's default theme for every scene.
- Fonts map to Newsreader / Instrument Sans / JetBrains Mono only; font files cannot be uploaded (licensing).
- Erasure: jobs and styles carry no per-user owner, so the erasure layer removes the whole workspace store only when the
  subject is the workspace itself.
- Videos grounded on the CorvinOS knowledge base can still use the CorvinOS console screenshot and layer-strip templates.
- Two hosts cap request bodies for the import routes (25 MB deck, 8 MB for save/preview); the gateway host got a cap
  for these paths in this release.

### Verified by
`tests/test_style_pack.py`, `test_style_store.py`, `test_style_import.py` (hostile corpus: zip/XML bombs, traversal,
macros, SVG, image bombs), `test_style_review_fixes.py` (defects found by two independent adversarial reviews),
`test_style_sources_section.py`, `test_style_e2e.py` (real Chromium + ffmpeg: the style's accent reaches the frames,
the Corvin gold does not); console `test_video_producer_styles_e2e.py` (two workspaces, audit chain, erasure).

## Version 1.3.1 (2026-10-10)

### What's new
- **The CorvinOS mark opens every video.** The first slide of every video now carries the mark large
  (150 px on the title slide, above the badge; 120 px as a corner mark when the first slide is not a hero
  slide), fading in at the start. The small mark in the footer stays on every slide. The storyboard prompt now
  requires scene 1 to be the `hero` scene, so the large mark normally sits on the title slide.
- No setting is needed: it is part of the renderer (`INTRO_MARK_PX`, `INTRO_MARK_CORNER_PX` in
  `src/web_templates.py`), so every video produced by this version has it.

### Known limits
- Only the web renderer draws it; the Pillow fallback (used when a slide cannot be rendered as a web slide)
  has no large mark.

### Verified by
`tests/test_web_templates.py` (large mark on the first scene only, on every template; none on later scenes),
`tests/test_layout_check.py` (the longest title slide and four other first slides stay free of overlaps).

## Version 1.3.0 (2026-10-09)

### What's new
- **The slide follows the voice (ADR-2245).** Before, every slide revealed all of its content within the
  first half of its narration and then stood still while the voice kept explaining. Now each item — a bullet,
  a node, a bar, a step, a layer — appears when the narration names it, and the eye is led to it: the named
  item glows in the accent colour, the others step back. Sentence starts are located in the real narration
  audio (pauses found with ffmpeg, no extra TTS call), so the timing follows what is actually spoken.
- **Beats in the storyboard.** The storyboard model may add `beats` per scene — one entry per sentence: the
  item the sentence is about, a 1-3 word keyword chip (title, quote and number slides), or nothing. Beats are
  checked against the final narration when the slide is rendered; where they do not fit, the plugin finds the
  items in the narration itself (labels, compound parts, sub-lines). The job metadata says which way each
  scene went (`cues[].beats_source`, `beats_fallback_rate`).
- **Collisions keep the content.** A slide whose text collides is retried without chips, then as a compact
  variant, then as bullets that keep every item — before it falls back to a one-line quote.
- **Measured.** `scripts/measure_engagement.py` reports how long a video stands still (still stretches of
  the content, with ambient dots filtered out), the gaps between cues and, with `--whisper`, how close each
  cue is to the spoken word.

### Results
The seven tasks of the 1.2.0 baseline, produced again through the live console (`measure_engagement.py`):

| | 1.2.0 | 1.3.0 |
|---|---|---|
| Dead share (time in still stretches of 5 s or more) | 57 % | 19 % |
| Longest still stretch per scene, median | 8.5 s | 4.0 s |
| Longest still stretch, maximum | 23 s | 18.75 s |
| Scenes with a still stretch of 5 s or more | 52 of 61 | 21 of 59 |

Not yet reached: cue-to-word alignment, measured with `--whisper` on two of the seven jobs (36 items), is
0.87 s at the median but 4.5 s at p90 (goal: 1.5 s). Part of it is the fallback placing an item the
narration names late, part is the measurement matching the first mention of a word part. The remaining
still stretches sit inside long sentences (one cue per sentence) and on screenshot slides without items.

### Known limits
- Slides with ambient motion (flow, diagram, cycle, timeline, layers, line) are captured frame by frame for
  the whole narration; rendering takes longer than before on those.
- When the narration never names a slide's items, the fallback can only place them between the ones it
  finds; the storyboard model's beats are what makes such scenes precise.
- The focus glow is kept tight on purpose: a wide soft glow bands into dark contour rings once encoded as
  8-bit H.264.

### Verified by
`tests/test_web_timeline.py` (sentence splitting, pause snapping on generated audio, beats validation, a 45 s
scene whose last cue must reach the encoded clip, focus dimming in Chromium), an E2E through
`start_video_production` with beats, the plugin suite, a re-run of the seven baseline tasks through the live
console, and the console's fresh-install lifecycle spec against this repository on GitHub.

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

