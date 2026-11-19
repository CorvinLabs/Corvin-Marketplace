# Video templates

A **video template** is a whole-video recipe: how long the video is, who it is for, what tone it has, which scenes it
has in which order, and which checks the finished storyboard must pass. It is not a *slide* template (hero, content,
stat, ... in `WEB-SLIDES.md`): a slide template is one picture a scene can use; a video template decides what the
storyboard writer is asked to produce. Choosing one changes the storyboard prompt and the checks. It never changes the
renderer, the voice chain or the job lifecycle.

## Shipped templates

| id | For | Target length | Scenes | Opens with a question |
|---|---|---|---|---|
| `standard` | the previous behaviour, no extra rules | by the task | 3-8 | no |
| `short` | phone format, one idea | 35 s (25-59 s) | 4-7 | **yes** (at most 12 words) |
| `marketing` | product video: problem, benefit, proof, next step | 75 s | 5-8 | no |
| `code_debugging` | symptom, reproduction, cause, fix, verification | 3.5 min | 6-10 | no |
| `research` | question, method, findings, limits, conclusion | 5 min | 6-10 | no |
| `didactic` | make a concept understood | 4 min | 5-8 | no |
| `tutorial` | step-by-step how-to | 3 min | 5-10 | no |
| `release_notes` | what is new, breaking changes first | 1.5 min | 4-8 | no |
| `executive_brief` | decision brief: situation, options, recommendation, ask | 2 min | 4-7 | no |
| `postmortem` | blameless look back at an incident | 4 min | 6-10 | no |
| `faq` | several questions, each with a short evidenced answer | 2.5 min | 4-9 | no |

**`short` is listed but cannot be produced yet.** It is a 9:16 (1080x1920) format and the web-slide renderer is fixed at
1920x1080. The template says so (`format.available: false` plus the reason), the panel shows it disabled with that reason, and the
console refuses it with 409. It becomes selectable when the vertical renderer exists; no other file changes then.

## Where it lives

- Files: `src/video_templates/<id>.json`, one per template, validated strictly on load by `src/video_templates.py`
  (unknown key, wrong type, unknown check name, unknown slide template, file name different from `id`: all errors).
- The file name is the id. `standard.json` must exist.
- Checks are code (`video_templates.CHECKS`) and are referenced by name from the template. A new check is a code change
  with a test; a template can only use names that exist.

## Schema (version 1)

| Field | Meaning |
|---|---|
| `schema` | always `1` |
| `id` | `^[a-z][a-z0-9_]{1,31}$`, equals the file name |
| `name`, `summary` | `{"en": ..., "de": ...}`, both languages required; shown verbatim in the panel (no internal ids) |
| `category` | `explain` / `persuade` / `engineer` / `research` / `format` (groups the picker) |
| `sort` | order in the picker (default 100) |
| `audience`, `tone` | prose given to the storyboard writer |
| `format` | `{"aspect": "16:9"|"9:16", "available": bool, "unavailable_reason": "..."}` (a reason is required when not available) |
| `duration` | `{"target_s", "min_s", "max_s"}`; above `max_s * 1.10` is an error, below `min_s * 0.70` a warning |
| `scenes` | `{"min", "max"}`; above `max` is an error, below `min` a warning |
| `scene_ms` | `{"min", "max"}` allowed length of one scene (replaces the generic 8-20 s rule) |
| `didactic_strategy` | `minimal_visual`, `rich_visual` or `null` (auto-detect) |
| `structure` | ordered steps `{"kind", "purpose", "required"?}`; `kind` is a scene kind (title, opening, problem, solution, example, summary, anchor) |
| `preferred_slides` | slide templates that fit; each must exist in `web_templates.TEMPLATES` |
| `rules`, `avoid` | bullet lists added to the prompt |
| `hook` | `{"kind": "question", "max_words": N}` or absent; needs the `opens_with_question` check |
| `evidence` | `none` / `sources` / `cited_numbers` (how strictly claims must come from the task) |
| `checks` | names from `CHECKS`: `opens_with_question`, `ends_with_takeaway`, `has_data_scene`, `has_code_scene`, `no_pressure_language`, `has_opening_context` |
| `recommended_model` | `haiku` / `sonnet` / `opus` (a hint shown to the operator; the host's model routing decides) |

## What a job does with a template

1. The console resolves the template: an explicit `video_template` in the request, else the tenant's remembered choice
   (new videos only), else `standard`. A film and a revision never use one. An unknown id is 422, an unavailable one is 409.
2. `generate_storyboard_with_llm(..., video_template=id)` adds the template block to the prompt, lowers the length ceiling
   to the template's, and replaces the scene-length rule. For `standard` the prompt is byte-identical to before.
3. The reply is checked. A template **error** (too long, too many scenes, a Short that does not open with a question)
   triggers exactly **one** repair call naming those problems; a reply that is still wrong fails the job with the reason.
   **Warnings** (missing takeaway, no data scene, pressure wording, ...) never block; they are recorded in the storyboard report.

## Honest limits

- The template steers and checks the storyboard; it cannot make a video true. `evidence: sources` and `cited_numbers`
  ask the writer to use only what the task contains and the checks look for a data scene, but a claim is not verified
  against a source automatically.
- The pressure-wording check is a short word list: a smell test that only warns.
- `recommended_model` is informational. The model that writes the storyboard is chosen by the host's routing.
- Two plugin versions are involved: a console without this module answers `501` on `/video/templates` and the panel shows
  "Templates unavailable"; videos are produced as before.
