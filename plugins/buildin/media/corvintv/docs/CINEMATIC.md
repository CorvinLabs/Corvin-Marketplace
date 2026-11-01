# Cinematic films (CorvinTV 1.8.0)

A **cinematic film** is the second way CorvinTV makes a video. A slide video is a sequence of animated slides; a film is
a few long continuous *acts*, each one shot built from moving figures (a coast, a lighthouse, a knowledge map, a ribbon
of light, your own Penpot designs), told by a narrator, with the camera drifting through it. The seven-part series
*From Spark to Foundation* (1080p, 24 fps, about 20 minutes per episode) was made this way; this mode makes the same
look available to every user, from a single sentence.

## How to make one

**Console.** Video panel → switch **Cinematic film** on, pick the length (2 to 10 minutes), write what the film is about,
optionally attach Penpot SVG exports (they become *designs* the film shows) → start. One MP4 per language comes out:
the language of your text, or both when you write the brief for two (`cinematic_langs`, at most two).

**API.** `POST /v1/console/video/jobs`

```json
{ "task": "Show how our onboarding works, calm and curious.",
  "mode": "cinematic", "cinematic_minutes": 4, "cinematic_langs": ["en", "de"],
  "designs": [ { "name": "home", "svg": "<svg …>" }, { "name": "settings", "svg": "<svg …>" } ] }
```

`designs` are Penpot "Export as SVG" files (name: letters, digits, `.`, `_`, `-`, at most 40 characters; at most 12
designs, 8 MB each). A film is a new video: it cannot be revised in place; describe the change in a new brief.

## What makes these films beautiful (and what the mode does for you)

These are the measured properties of the example series and the rule that produces each one. The director prompt
(`src/cinematic/prompt.md`) and the figure library (`src/cinematic/engine/LIBRARY.md`) carry them, so the model does not
have to rediscover them.

| Property of the examples | How the mode guarantees it |
|---|---|
| One continuous shot per act, 4 to 9 narrated *beats* per act, 12 actors and about 31 tweens per act | The screenplay is acts of beats, every figure has start values and tweens (`direction.py` validates counts, ids and property names) |
| Every visual event happens **on the word**: a beat starts, something changes | A tween's `at` is `"b3"`, `"b3+1.2"` or `"end-2"`, resolved against the real spoken timeline, never a guess |
| The camera moves all the time (slow push-ins, parallax: sky 0.1, sea 0.4) | `cam` tweens (`cx`, `cy`, `zoom`, `rot`) and a `par` factor per figure; the prompt asks for camera moves |
| Metaphor first, almost no text, **no subtitles, no pointing dot** | Visible text only through `caption`; the prompt forbids the dot and subtitles; there is no subtitle track |
| One consistent look: night palette, amber accent, soft glow, vignette | Fixed palette and `grade`; fonts (Newsreader, Instrument Sans) are embedded in the page, so the film looks the same on every machine |
| Calm, even narration: tts-1-hd voice, -16 LUFS | The plugin's TTS chain (OpenAI, edge-tts, gTTS) and `loudnorm=I=-16` in the encode |
| German and English identical in picture and length | One shared timeline: a beat's slot is the longer of its spoken lengths; only acts with a `caption` are drawn once per language, the rest once |
| Frames identical on every run | The engine uses no clock and no random: a frame is a pure function of (act, time, language) |

Practical advice for a brief: say **who it is for and what they should feel or do afterwards**, name the two or three
ideas that must be understood, and give an **example as an example**. The film invents no numbers or commands.

## Penpot designs in a film

Design a screen, a card or a diagram in Penpot, use *Export as SVG*, attach it. The screenplay may show it with the
`art` figure:

```json
{ "id": "home", "type": "art", "src": "home", "x": 960, "y": 520, "w": 1100, "h": 619, "p": 0, "radius": 18, "glow": 0.4 }
```

with tweens on `p` (a left-to-right wipe), `o`, `s`, `x`, `y`, and the camera moving onto it on the beat that talks
about it. The director may only use the design names you supplied; the validator rejects any other `src` and the one
repair round tells the model which name is wrong. A design is reduced by the same closed importer as a Penpot style
(rectangles, ellipses, paths, text, gradients; images, filters, scripts and external fonts are dropped) and reaches the
browser only as a `data:` image, so an upload cannot run code or fetch anything. What an SVG export cannot carry
(components, auto-layout, prototype animation) is not imported; the film animates the picture, the camera and the
reveal, not the Penpot prototype. See [PENPOT-IMPORT.md](PENPOT-IMPORT.md).

## What happens in a job

1. **Screenplay.** The director (Claude: the host's Claude Code login or an API key, like the slide storyboard) writes
   acts and beats in every requested language. The result is validated; **all** findings go back in **one** repair
   round; if it is still wrong the job ends with the findings as its error.
2. **Speech.** One clip per beat and language (cached by text), converted to 24 kHz mono.
3. **Timeline.** Beat times and act lengths on the 24 fps grid; `max_duration_minutes` is enforced on the real length.
4. **Frames.** One page with the engine, fonts, acts and designs; headless Chromium draws every frame (network blocked,
   only `data:` images). Progress is reported per 48 frames and can be cancelled.
5. **Encode.** H.264 CRF 19, AAC 192k, loudness-normalised, one file per language: `output.mp4` (first language),
   `output.<lang>.mp4`. Temporary frames are deleted; `cinematic/direction.json`, `cinematic/timeline.json` and the
   production report stay with the video.

Job metadata (`mode`, `languages`, `language_files`, `language_sync_diff_ms`, `designs`, `screenplay_repaired`) is on
the video output; the report is `report.json`. The audit trail records `video_producer.job_started` with `mode`.

## Limits and honest notes

- Needs the same things as a slide video (ffmpeg, Chromium via Playwright, a narration voice) **and** Claude for the
  screenplay. Offline, the job ends with a clear message.
- The figure library is a coastal night world plus abstract figures (constellations, ribbons, gates, gears, terrain, …).
  It is strong for explaining ideas and weak for literal product walkthroughs: for those, attach designs and let the
  camera and reveals do the work.
- A 4-minute two-language film is about 6 000 captures; on a laptop expect minutes, not seconds.
- Quality signals of the slide pipeline (layout collisions, cue timing) do not apply to films; the report states the
  facts that were measured (duration, sync between languages, repairs).
- No "production ready" claim beyond what the tests measure: `tests/test_cinematic.py` (24 unit tests) and
  `tests/test_cinematic_job_e2e.py` (real job process, Chromium, ffmpeg, Penpot design, repair round, failure case).

## Files

| Path | Role |
|---|---|
| `src/cinematic/prompt.md` | director prompt |
| `src/cinematic/engine/*.js`, `LIBRARY.md` | deterministic canvas engine and its manual (the model's only vocabulary) |
| `src/cinematic/direction.py` | prompt builder, extraction, validator, repair prompt |
| `src/cinematic/stage.py` | page builder (script-safe JSON, embedded fonts), Penpot designs, frame capture |
| `src/cinematic/produce.py` | the job: speech, timeline, audio, frames, encode, job record; dispatched from `skill._orchestrate_from_config` when `mode == "cinematic"` |
