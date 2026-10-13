# Penpot designs in the Video Producer (ADR-2257)

The Video Producer reads designs made in [Penpot](https://penpot.app) (open source, MPL-2.0). It does **not** contain an
editor and needs no Penpot installation: you export a board as SVG and import the file. Everything below works on Linux,
macOS and Windows with only what the producer already needs (Python standard library, Pillow; Chromium only for the
image path).

## Two ways to use a board

| You want | Do this | Result |
|---|---|---|
| Your videos in the design's colours and fonts | **Style chip > Import from PowerPoint or Penpot...**, or attach the `.svg` and choose **Use as style** | A style draft (palette, fonts) with previews; save it like any style |
| The board itself shown in a video | Panel details, **Assets** tab > **Import Penpot board (SVG)** | A 1920x1080-at-most PNG image asset for a `still` scene |

Both use the same reader (`src/penpot_import.py`): the SVG is reduced to a closed model of rectangles, ellipses, paths and
text with validated numbers and `#rrggbb` colours. The style path derives the palette with the same rules as the
PowerPoint import (the accent is the most prominent chromatic fill; text and background contrast rules are enforced).
The image path renders **only that model** with the producer's headless Chromium (JavaScript off, every network request
aborted); no byte of the upload reaches the browser.

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

## Measured

On a real export from Penpot 2.18.3 (`tests/fixtures/penpot_board.svg`): 8 shapes read, and the rendering in Chromium is
pixel-identical to the original SVG everywhere except inside the two text boxes (different fallback typeface:
`tests/test_penpot_import.py::test_render_matches_the_penpot_svg_in_chromium`).

## API and audit

- `POST /v1/console/video/styles/import` accepts `.pptx`/`.potx` or an SVG (sniffed by content, never by extension).
- `POST /v1/console/video/assets/import-penpot` (SVG, optional `caption`) stores the rendered image like any asset.
- Audit (tenant chain, written before anything becomes visible): `video_producer.style_imported` and
  `video_producer.asset_uploaded`, both with `format: pptx | penpot_svg`; only byte counts and a sha256 prefix are
  recorded, never the design's text.

## Running Penpot yourself (optional)

Designing needs a Penpot, either the public one or your own. The producer works without it. For a local instance see the
optional stack in `scripts/penpot_stack/` and its runbook, `docs/PENPOT-STACK-RUNBOOK.md` (needs Docker or Podman and about
3 GB RAM).
