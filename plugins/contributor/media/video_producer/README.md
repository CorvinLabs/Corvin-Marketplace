# Video Producer Skill

**What ships live today: a task description → a short narrated MP4.**

> **2026-10-03 — this file was rewritten to describe what actually runs.**
> The previous version documented a 4-tier renderer / CLI / `VideoProducerOrchestrator`
> architecture that a full reachability audit found has **zero production callers** —
> see [ADR-0953](docs/ADR-0953-consolidation-dead-code-removal.md) for the audit and the
> consolidation plan. `DEPLOYMENT_STATUS.md`, `ARCHITECTURE.md`, `PHASE-1-STATUS.md`,
> `PHASE1_IMPLEMENTATION_REPORT.md`, `PRODUCTION_VERIFICATION_REPORT.md` and
> `WAVE6_COMPLETE.md` all describe that same never-activated design — read them as
> historical design intent, not as the current system.

## What it actually does (the live path)

The host (CorvinOS console, `core/console/corvin_console/routes/video_producer_api.py`)
loads this plugin's `src/` package and calls exactly five modules:
`models.py`, `storage.py`, `skill.py`, `async_runner.py`, `__init__.py` (~850 LoC total).
Nothing else under `src/` is reachable from there.

1. **Storyboard:** the task text is sent to an LLM (Anthropic, if the host's egress
   policy admits it for this job; otherwise a local Ollama instance) and turned into a
   JSON storyboard (scenes, narration text, durations), enforcing a scene-count and
   total-duration ceiling.
2. **Narration:** each scene's text is synthesized with **gTTS** (Google's public
   Translate TTS endpoint — not a paid API, no SLA).
3. **Slide image:** a simple text slide is rendered per scene (PIL, not a renderer tier).
4. **Assembly:** `ffmpeg` encodes each scene's audio+image into a clip, then concatenates
   all clips into `output.mp4` + an `.srt` caption file.
5. **Storage:** jobs and outputs are persisted per-tenant (`storage.py`, atomic writes).

**Not live, despite being described in older docs:** PPT/screenshot asset analysis,
live-console screenshot capture, Blender/Three.js/Manim rendering tiers, YouTube upload,
the plugin's own learning-loop modules (`learning_event_store.py`,
`tier_learning_optimizer.py`) — the console uses its own, separate learning path instead.

## Entry point

There is no CLI and no importable orchestrator class in current use. The only live entry
point is the host's HTTP API:

```
POST /v1/console/video/jobs           {"task": "..."}   → {"job_id": "..."}
GET  /v1/console/video/jobs/{job_id}                      → status
GET  /v1/console/video/videos/{job_id}/download           → the MP4
```

(`python3 -m video_producer`, `from video_producer import VideoProducerOrchestrator`,
and the `tests/test_orchestrator_e2e.py` CLI test below all exercise the **dead**
`src/video_producer/` sub-package — kept for now pending the ADR-0953 Phase B
extraction review, not an alternative way to run this plugin.)

## Configuration

- `ANTHROPIC_API_KEY` — optional; storyboard backend falls back to local Ollama without it
- No OpenAI key is used on the live path (narration is gTTS, not OpenAI TTS)

## Testing

```bash
# The tests that exercise the live path:
python3 -m pytest tests/test_models.py tests/test_storage.py tests/test_skill.py \
  tests/test_api_routes.py tests/test_review_2026_10_03.py -v
```
Most other files under `tests/` exercise the dead clusters listed in ADR-0953 and will
be removed or rewritten in Phase C of the consolidation.

## Documentation

- [ADR-0953](docs/ADR-0953-consolidation-dead-code-removal.md) — **start here**: the
  reachability audit and the consolidation decision
- `docs/ADR-0001` / `ADR-0002` / `ADR-0003` / `ADR-0951` / `ADR-0952` — describe the
  never-activated 3-tier/director-mode architecture (historical design intent only)

## License

Apache License 2.0
