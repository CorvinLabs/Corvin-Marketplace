# Website tour (CorvinTV 1.9.0)

A website tour turns a web page into a narrated video **and** a page you can send or put online. The real page is filmed
while a voice walks the viewer down it: the camera scrolls in one smooth curve, the page's own CSS animations run in time
with the spoken sentences, and a few restrained effects lift the focus. The deliverable is a bundle: one MP4 per language, a
self-contained player page with chapters and a transcript, and a zip of that folder.

Design: CONCEPT-0139 and ADR-2336 (Corvin-Knowledge). Tests: `tests/test_website_tour.py` (fast) and
`tests/test_website_tour_e2e.py` (the real job process, a real browser, ffmpeg).

## How to start one

**In the console.** Pick the template **Website tour** in the composer, write the page address and what the tour should say
("https://example.com Explain the plans and what each one costs"), choose the voice language and the length, produce. A tour of
an address needs the workspace's **website capture** switch to be on and an enabled egress policy that allows the host
(the same rules as "Add website screenshot"). When it is done, the stage shows the video; the globe button next to Download
gives the **website bundle** (zip).

**From the command line** (no console, no switch; you are the operator):

```
python scripts/website_tour.py --site ./my-site --tour tour.json --langs de en --out ./tour-out
python scripts/website_tour.py --url https://example.com --task "Explain the pricing page" --langs en --out ./tour-out
```

`--site` copies a folder with an `index.html` into `<out>/websites/<name>`; it is served on loopback by the job itself and the
browser may reach nothing else. `--url` loads the page through the capture proxy (only the named host). Result:
`<out>/videos/<job>/`.

## What comes out

```
output.mp4, output.<lang>.mp4      1920x1080 H.264 + AAC, loudness -16 LUFS, no burned-in subtitles
site/index.html                    player, chapters, language switch, transcript; no request to any other site
site/video.<lang>.mp4, poster.jpg
site/chapters.<lang>.vtt, captions.<lang>.vtt   (the caption track is off until the viewer turns it on)
site/README.txt                    how to put it online: upload the folder to any static host
website-bundle.zip                 the folder as one file to send
report.json                        production report incl. camera smoothness and blocked requests
```

`index.html` is one file with a strict content-security policy (the hash of its one inline script, `default-src 'none'`).
Every text that came from the page or the model is escaped. For social previews add an absolute `og:image` once you know the URL.

## The tour

A tour is a JSON document: an intro (two lines per language), scenes, an outro. A scene names ONE target of the page's
**outline** (`k1`, `k2`, ... in page order), a view (`top`, `fit` a whole figure, `pan` down a tall section) and one to six
sentences. A sentence may add a `focus` (another outline key to highlight). `anchors` start a looping figure's animation at a
sentence. Without `--tour` the native Claude Code engine writes the tour from the outline and your brief; the answer may
name outline keys only (never selectors, addresses or code), every number must appear on the page, and one repair round fixes
what the validator finds.

## Camera and effects

* **Camera.** One global curve (monotone cubic Hermite) through the tour's stops: continuous speed, no stop at every
  scene, no overshoot, capped at 900 css px per second (a long way starts earlier). The sub-pixel part of every position is
  applied when cropping, so a slow move is smooth. The report holds `max_step_px` and `max_accel_px`.
* **Animations.** Every CSS animation of the page is set to the video time, frame by frame. The page's own timers
  (`setInterval`) are frozen.
* **Effects** (`website_effects`, all on by default): `spot` dims the page outside the focused element, `reveal` lets the
  page's reveal markers (`[data-reveal]`, `[data-aos]`, `.reveal`) rise as the camera brings them in, `zoom` is a slow push-in
  that continues from scene to scene, `vignette` softens the edges.
* **Cards.** Intro and end card in the page's own colours. The end card says that the voice is AI-generated.

## Voice

Every sentence is spoken by `skill._synthesize_narration_chain`: the CorvinOS chain, OpenAI first, then edge-tts, then Piper.
There is no second voice path.

## Limits

JavaScript timers of the page are frozen (a demo that only moves through `setInterval` stands still); videos and canvases show
their state at load; content that only appears after a click is not shown; pages behind a login cannot be toured. Narration is
English or German. A tour of an address is unavailable until the workspace has turned on website capture and has an egress
policy.

## Example: a real tour of a live site

`docs/examples/corvinos-amplifier-tour.json` is the tour (German + English, 11 scenes, 26 sentences) behind the first video made with this
feature: CorvinOS as an amplifier for Claude Code, filmed from https://corvin-labs.com/ . Print the keys of a page first, then write the tour:

```
python scripts/website_tour.py --url https://corvin-labs.com/ --allow-host fonts.googleapis.com --allow-host fonts.gstatic.com \
    --allow-host unpkg.com --print-outline --langs de --out ./tour-out
python scripts/website_tour.py --url https://corvin-labs.com/ --tour docs/examples/corvinos-amplifier-tour.json --langs de en \
    --allow-host fonts.googleapis.com --allow-host fonts.gstatic.com --allow-host unpkg.com --out ./tour-out
```

Measured on that run: 3:12 minutes, camera peak 900 px/s (the cap) and at most 0.8 px change of the step from one frame to the next,
narration onsets within 0.02 s of the plan, 0 blocked requests. A page that builds itself with a script CDN (this one loads React from
`unpkg.com`) needs that host in `--allow-host`; without it the page stays empty and the outline step says so ("no sections or headings").
