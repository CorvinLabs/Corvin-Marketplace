# CorvinTV cinematic scene library

Every picture is built from **actors** that move over time. An **act** is one continuous shot of 50 to 110 seconds
with a narration made of **beats** (one or two spoken sentences each, in every requested language). Stage coordinates: 1920 x 1080 pixels,
origin top left, x to the right, y downwards. The picture has a dark night palette; the colours below are the series palette.

Palette (hex): night `#05070e`, ink `#ece9e2`, amber `#e8a83a`, ice `#bfe9ff`, teal `#2ec4b6`, violet `#8b7bd8`, red `#d95d5d`, green `#56c596`, blue `#5b8def`, pink `#ff9ad0`.
Colour meaning (keep it consistent through a video): amber/gold = the main idea and its light, ice/white = the thing that answers, teal = knowledge and memory, violet = the examiner or the risk, red = a found flaw, green = a passed check.

## Act JSON

```json
{ "id": "1.03",
  "beats": [ {"de": "Erster Satz.", "en": "First sentence."}, {"de": "...", "en": "..."} ],
  "actors": [ {"id": "sky", "type": "sky", "par": 0.1, "moon": 1}, {"id": "lh", "type": "lighthouse", "x": 520, "y": 760} ],
  "tweens": [ {"a": "lh", "p": "power", "to": 1, "at": "b1", "d": 2.5, "e": "inOut"} ] }
```
* `actors` are drawn in list order (later = in front); `z` overrides (grade uses `z: 100`).
* `tweens` change any numeric property over time: `a` actor id, `p` property, `to` value, `at` start, `d` duration in seconds, `e` easing.
  The value before the first tween is the one written in the actor. Several tweens on one property chain in time order.
* `at`: `"b3"` = the moment beat 3 starts to be spoken (beats count from 0), `"b3+1.5"` = 1.5 s after that, `"b3-0.5"` = shortly before, `"end-2"` = two seconds before the act ends, or a plain number of seconds from the act start.
  **Tie every visual event to the beat where the narrator says it.**
* Easings: `inOut` (default), `out`, `in`, `soft`, `smooth`, `linear`, `back` (overshoot), `drop` (falls and settles), `step`.
* Lists of numbers (for example `states` of `lamps`) fade element by element; any other non-number (`hl`, a text) switches at the end of the tween.
* Camera: an actor named `cam` may be tweened (`cx`, `cy` centre, default 960/540, `zoom` default 1, `rot` degrees).
  Actors with `par` (parallax, default 1) follow the camera; `par: 0` is fixed to the screen. Use `par` 0.1 for the sky, 0.4 for the sea. **Camera moves (slow push-ins, pans) make a shot feel filmed; use them.**

Common properties of every actor: `x`, `y` (anchor), `s` (scale, 1), `r` (rotation in degrees), `o` (opacity 0..1), `flip` (mirror), `par`, `z`.

## Actors

**Backdrop**
* `sky`: `tone` 0 night .. 1 dusk/dawn, `stars` density (1), `moon` 0/1, `mx`,`my`, `ms` moon scale, `phase` 0..1 (crescent). Fills the screen. Use `par` 0.1.
* `sea`: `hy` horizon y (720), `amp` wave height (9), `speed`, `tone` (match the sky), `refl` 0..1 shimmering light path at `rx`, `rcol`. Fills the screen below `hy`. `par` 0.4.
* `mist`: drifting fog bands: `y` (centre height), `a` opacity (0.16), `n`, `speed`, `color`, `w`.
* `particles`: floating motes in an area of `w` x `h` **centred** on `x`,`y`: `n`, `color`, `speed`, `dir` (degrees, -90 = up), `size`, `a`, `seed`.
* `grade`: vignette on top of everything: `v` 0.6. Put one last in every act with `z: 100`.

**The world** (a coastal night scene; `lighthouse`, `oracle`, `figure`, `ship` are a ready-made cast: use them when a story of light, guidance and a questioner fits the topic, otherwise stay with the abstract actors below)
* `lighthouse` (the hero of the series; the *idea*): `x`,`y` = base at the rock, `s`; the tower is about 410 px high, the lamp room sits 331*s above the base.
  `power` lamp 0..1, `beam` 0..1 (default = power), `focus` 0 = wide diffuse glow .. 1 = razor beam, `aim` degrees (0 = right, negative = upward; if absent the beam sweeps gently), `sweep` sweep amplitude in degrees, `tint` hex colour makes it a silhouette in that colour (use `#8b7bd8` for the **Shadow**), `bcol` beam colour.
  A lit lighthouse whose `focus` rises from 0.1 to 0.9 over a video is the visual form of "the idea gets sharper".
* `oracle` (the model; a faceless being of light): `x`,`y` = feet, `s` (about 470 px tall), `color`, `glow` 0..1, `calm` 0..1 (turbulent .. serene), `speak` 0..1 (rings leave the head while it answers).
* `figure` (the person who asks, listens, walks): `pose` `stand`|`ask`|`look`|`walk`, `color`. About 170 px tall.
* `ship`: sailboat with lantern: `lit`, `seed`. `rings`: expanding ripples: `n`,`color`,`R`,`speed`,`a`,`r0`,`squash`,`w`.
* `ribbon`: a flowing ribbon of light (an answer, a thought) from `x0`,`y0` to `x1`,`y1` (use actor `x`/`y` 0 so these are stage coordinates): `p` head 0..1, `q` tail (default p-0.3), `color`, `w`, `seed` (changes its curve), `wave`, `a`.
  Tween `p` from 0 to 1 to let it fly; tween `q` from 0 to 1 afterwards to let it dissolve.
* `flow`: a stream of chevrons along a gentle curve `x0,y0 -> x1,y1`: `n`,`color`,`speed`,`bend`,`p`.

**Knowledge and structure**
* `constellation` (the knowledge graph, a star map): `nodes` `[[x,y,color?,size?], ...]` in stage coordinates (actor at 0,0), `links` `[[i,j],...]`, `p` how many stars are shown (float, 0..n), `lp` links drawn 0..1, `hl` list of highlighted indices, `dim` 0..1 (dims the others), `size`, `color`.
* `pages` (documents): `x`,`y`,`s`, `n`, `m` 0..1 (the pages lift and dissolve into particles that fly to `targets` `[[x,y],...]` in stage coordinates; pair with a constellation whose `p` rises afterwards).
* `arch` (progress of the series: **seven stones**): `x`,`y` = ground centre, `s`, `lit` 0..7 (stones glow in order), `key` 0..1 (the keystone, stone 4, falls from above and lands with a shock ring; 0 = not yet there), `R` 330, `th` 96.
* `gate` (a check): `x`,`y` = ground centre, `s`, `open` 0..1 (the doors slide apart and light pours out), `kind` `keyhole`|`seal`|`compass`, `color`, `glow`. About 360 px high at s=1.
* `token` (an idea candidate): `shape` `seed`|`leaf`|`diamond`|`triangle`|`bulb`, `hue`, `glow`, `seed`. Tween `x`,`y` to let it travel to a gate, through it, or back.
* `lamps` (tests / results): `states` `[0..1,...]` (0 red, 1 green), `gap`; hang from above. `coin`: `spin` (radians), `shine`.
* `blueprint`: `kind` `bridge`|`tower`|`plan` (plan = rows ticked off one by one), `p` 0..1 drawing progress, `color`.
* `compass`: `ang` needle degrees, `wobble` (settling shake, tween 1 -> 0), `glow`.
* `pedestal`: `fill` 0..1, `kind` `orb` (memory)|`eye` (review)|`needle` (feedback)|`book`, `color`. Empty = dashed ghost circle above the pedestal.
* `bubble` (a fragile idea with a tiny lighthouse inside): `pop` 0..1 (bursts), `hue`, `seed`. `crystal` (the model as raw material): `grow`, `hue`, `seed`. `gear`: `teeth`,`R`,`speed` (negative turns the other way),`phase`,`color`,`warm` 0..1 (forge glow); two gears side by side mesh visually.

**Learning and resolution**
* `terrain` (the loss landscape, a wireframe valley with a rolling light that descends it): `p` 0..1 progress of the descent, `seed` (2 default), `fog`, `rot`, `hiker` 0/1. About 1000 px wide.
* `curve`: a falling line of progress: `w`,`h`,`p`,`color`. `cycle`: a ring of flowing chevrons (a loop): `R`,`n` segments,`lit` 0..n,`cols`,`color`,`speed`.
* `pixelpic`: a picture (a lighthouse at dawn) whose **resolution** you control: `lvl` 0..11 (0 = 2x2 blocks, 5 = 12x12, 8 = 32x32, 11 = fine), `noise` 0..1 (forgery speckle that flickers), `scan` 0/1 (an examining scan line), `w`,`h`,`frame`.
* `tower` (layers of rising resolution under a seed of light, `lit` 0..5): `x`,`y` = top centre, `gap`. Plate 1 is blocky, plate 5 is nearly sharp.
* `tree`: grows from a seed: `grow` 0..1, `seed`, `color`. `fan`: a folded screen that unfolds into a flat plan: `fold` 0 folded .. 1 flat, `n`.

**Rare text, brand and your own designs**
* `caption`: `text` an object with one entry per requested language, e.g. `{"de": "...", "en": "..."}` (**every requested language**), `size`, `color`, `align`, `p` 0..1 typewriter, `italic`, `bold`, `font`. Use very sparingly: only the title card, the opening/closing question, and the closing sentence.
* `symbol`: the CorvinOS mark, `size`, `p` 0..1 (drawn in). Use once, at the start of the video, only for CorvinOS topics.
* `art`: the user's own design (for example a Penpot board or screen), drawn centred at `x`,`y`. `src` is the **name of one of the supplied designs** (only the names listed under "Supplied designs" exist), `w`,`h` size in stage pixels (keep the design's aspect), `p` 0..1 wipes it in from left to right, `radius` rounds the corners, `glow` 0..1 puts a soft light behind it (`glowc` colour). Tween `p`, `o`, `s`, `x`, `y` to reveal it on the beat that talks about it, and move the camera onto it. Never invent a `src` name.

## Composition advice
* One shot, one picture that tells the beat: few strong actors, clear screen space, a focal subject on the thirds. Let things move into place on the beat; do not set everything at once.
* Always start from a believable base layer: `sky` + `sea` (or `sky` only for the abstract shots) + `mist`/`particles` + `grade`.
* Reuse the world between acts so the series feels like one place: the coast with the lighthouse at left (x 300-560), the sea horizon at 720, the oracle to the right (x 1250-1450), the asking figure at x 700-1000.
* Metaphor first: show the idea happening (a ribbon dissolves into mist = the model forgets) instead of writing it.
* Avoid anything that reads as a lone glowing yellow dot used to point at things. Never put a single amber dot, cursor or marker on screen to direct attention; direct attention with composition, light and camera.
