# Penpot designs in the Video Producer (ADR-2257)

The Video Producer reads designs made in [Penpot](https://penpot.app) (open source, MPL-2.0). It does **not** contain an
editor and needs no Penpot installation: you export a board as SVG and import the file. Everything below works on Linux,
macOS and Windows with only what the producer already needs (Python standard library, Pillow; Chromium only for the
image path).

## Two ways to use a board

| You want | Do this | Result |
|---|---|---|
| Your videos in the design's colours and fonts | **Style chip > Import from PowerPoint or Penpot...**, or attach the `.svg` and choose **Use as style** | A style draft (palette, fonts) with previews; save it like any style |
| The board itself shown in a video | Panel details, **Assets** tab > **Import Penpot board (SVG)** | A 1920x1080-at-most PNG image asset for a `still` scene, plus the stored design |
| The board revealed step by step while the narration speaks | After the import, **Board steps** on the image: click shapes into ordered steps, save | A `board` scene the storyboard can place (ADR-2260) |

Both use the same reader (`src/penpot_import.py`): the SVG is reduced to a closed model of rectangles, ellipses, paths and
text with validated numbers and `#rrggbb` colours. The style path derives the palette with the same rules as the
PowerPoint import (the accent is the most prominent chromatic fill; text and background contrast rules are enforced).
The image path renders **only that model** with the producer's headless Chromium (JavaScript off, every network request
aborted); no byte of the upload reaches the browser.

## Boards: a design revealed step by step (ADR-2260)

On import the validated model is stored beside the picture as `design.json` (typed fields only - size, origin,
background, shapes - never the upload, never steps). It is immutable like the picture, counts toward the same quota,
is deleted with the image, and is **validated again on every load**: a hand-edited or tampered file is refused, never
repaired.

A design becomes a **board** once its reveal steps are assigned: an ordered list of 1 to 12 steps, every shape in
exactly one, each with an optional plain-text label (at most 40 characters). The steps are saved through the same
update as captions and hotspots (`PATCH /v1/console/video/assets/{id}` with `steps`; `null` removes them) and are
checked against the stored design by the server. A design without steps is **unassigned**: it is still a picture for
`still` scenes and still a style source, but it is refused as a board with "assign steps first".

**Steps are assigned by hand.** An automatic grouping rule is not shipped: the measurement that would decide on one
(S1, at least five real exports and two independent boards whose intended steps their owner writes down) has not been
run yet. The **One step per group** button only proposes a starting point from the export's top-level groups; nothing is
saved until you press **Save steps**. (A real Penpot export can put every shape into one top-level group - the fixture
does - so that proposal is often a single step.)

In the video each step is one item for the narration timeline. A step is revealed when the narration names its label,
or - without a label - its first text; a step with neither appears through the storyboard's `beats`, else on an even
rhythm, and is then **not** tied to a word. Motion is one of four: text rises, rectangles and fill-only paths fade,
ellipses scale, and a path with a stroke draws its stroke on (its fill fades in behind). The drawing order is always
the design's own shape order. Text is drawn in the producer's bundled fonts, stretched to the design's text width
(`textLength`), so letter shapes and spacing can differ from Penpot's.

**Board limits** (checked when a design is used as a board, not at import; a larger design still imports as a picture
and is refused as a board with the count): 240 shapes, 60 000 characters of path data, 4 000 characters of text,
strokes up to 16, shape transforms scaled at most 2x, text up to 320 px, 16 gradients, 120 see-through shapes, 60
stretched texts. They were measured so that a design meeting every limit at once renders at no more than twice the
median frame time of the other templates at 1920x1080 (`tests/test_board.py`).

**When a board cannot be shown** - the stored model no longer validates, the render fails, or the slide collides - the
same image is shown as a `still` scene instead and the job records `board_to_still` with a progress message; it is
never the classic slide and never a quote replacement. If the storyboard names a design that is not board-ready, the
scene becomes a `still` of the same image. The storyboard model is offered only board-ready designs (id, caption, step
labels); it can place a board, never invent one or its shapes.

## What is not imported

An SVG export does not carry Penpot components, constraints, auto-layout or animations, so they are not imported.
**Kept:** linear and radial gradients on fills (2 to 8 stops, at most 64 per design); a shape that uses one also carries
its first stop colour as the flat fallback the palette ranking reads. A gradient that breaks a bound (more than 8 stops,
decreasing or out-of-range offsets, an unknown unit, a transform other than `matrix()`, a reference to another
gradient) is dropped, counted, and the shape takes the colour of its first valid stop.

Dropped and counted (the dialog and the asset response say how many): gradient strokes, patterns, a gradient or colour
that cannot be read, style sheets that set `fill`/`stroke` (and the shapes they style; the `@font-face` sheet and the
structural classes of a real Penpot export cost nothing), colours set on a `<tspan>`, images, filters
(shadows, blurs), `foreignObject`, `use`, scripts, lines/polylines/polygons, unsupported transforms, shapes with
malformed numbers. External `@font-face` URLs in the export are never followed. Text keeps its position and box width
(`textLength`); the typeface falls back to the host's sans-serif when the Penpot font is not available, so
glyph shapes can differ from Penpot's.

Limits: 8 MB per file, 16 to 20 000 px per side, 2 000 shapes, 600 characters per text (30 000 in total),
5 s parse budget, 64 levels of nesting. A DOCTYPE or ENTITY declaration refuses the file.

**Only Penpot exports are read.** Penpot names every shape `shape-<uuid>`; a file with no such element (a Figma,
Inkscape or hand-written SVG) is refused with `Unknown Penpot structure: ...` and nothing is imported. This is checked
on the 2.18.x export format only; a future Penpot version that renames the shape ids is refused the same way, and its
fixture test is the place to add the new structure.

Without the console: `python scripts/penpot_to_json.py BOARD.svg > board.json` prints the same closed model as JSON
(exit 0), or the refusal on stderr with exit 2. The JSON carries only typed fields, never the upload's markup.

## Measured

On a real export from Penpot 2.18.3 (`tests/fixtures/penpot_board.svg`): 8 shapes read, and the rendering in Chromium is
pixel-identical to the original SVG everywhere except inside the two text boxes (different fallback typeface:
`tests/test_penpot_import.py::test_render_matches_the_penpot_svg_in_chromium`).

## API and audit

- `POST /v1/console/video/styles/import` accepts `.pptx`/`.potx` or an SVG (sniffed by content, never by extension).
- `POST /v1/console/video/assets/import-penpot` (SVG, optional `caption`) stores the rendered image like any asset,
  and the design beside it; the response's `asset.board` says whether it can be a board and why not.
- `GET /v1/console/video/assets/{id}/design` returns the stored model, its steps and labels (Board steps dialog).
- `PATCH /v1/console/video/assets/{id}` with `steps` assigns or (`null`) removes the reveal steps.
- Audit (tenant chain, written before anything becomes visible): `video_producer.style_imported` and
  `video_producer.asset_uploaded`, both with `format: pptx | penpot_svg`; only byte counts and a sha256 prefix are
  recorded, never the design's text. Assigning steps writes `video_producer.asset_updated` with `step_count`; opening
  the design writes `video_producer.asset_accessed` with `purpose: design`. No shape, text or label reaches the chain.
- Figma: a Figma SVG export goes through the same importer but is **unverified** - no real Figma export is in the test
  suite yet.

## Running Penpot yourself (optional)

Designing needs a Penpot, either the public one or your own. The producer works without it. For a local instance see the
optional stack in `scripts/penpot_stack/` and its runbook, `docs/PENPOT-STACK-RUNBOOK.md` (needs Docker or Podman and about
3 GB RAM).
