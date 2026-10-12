"""Canvas template (ADR-2249 D1, PLAN-0947 P2, T-0110): a sketch board for explanations.

Data in, SVG/HTML out. Built from the measured S1/S2 spike prototype; registered for real in
``web_templates`` (TEMPLATES, validate_scene_data, reveal_steps, scene_items, builder, css).

  * closed vocabulary of element types, closed numeric ranges, text through the plugin's own
    ``_text`` cleaning (control/bidi stripping, length caps) and HTML escaping. Nothing from the
    model is a colour: ``tone`` is one of five style roles, resolved to the active palette's CSS
    variables; ``validate_style`` is untouched. Text is never executed, never interpreted;
  * placement is semantic: a 12x6 grid (``at: {col,row,w,h}``) or relative
    (``right_of|left_of|below|above|inside`` + ``gap``), resolved here, never pixels;
  * the validator PROVES what is decidable on the data (bounds, attached arrows, grid-cell overlaps
    between shapes, text that cannot fit its box at the legibility floor, counts) and returns ALL
    errors at once (one repair round);
  * strokes draw on with stroke-dashoffset (CSS animation, seekable through
    document.getAnimations()), duration proportional to path length clamped to 0.4-2.5 s, starting
    at the element's cue; an optional pen sprite (``fill: none``, CSS offset-path) follows the
    stroke - the renderer only ever moves a page's time forward, so it survives the capture;
    ``sketch: true`` is a seeded wobble computed here (no render-time randomness);
  * the render gate: ``PROBE_JS`` measures the settled page (text vs shape, text overflowing its
    shape, text vs text, strokes through text/shapes, detached arrows, out of the canvas) and
    ``web_renderer`` reports each finding as a layout issue (type prefix ``cv-``).
"""

from __future__ import annotations

import copy
import html
import math
import random
import re
import zlib
from typing import Any, Dict, List, Optional, Tuple

# web_templates imports this module lazily (inside its functions), so importing it back here at
# call time never forms an import cycle; same dual-mode import as code_v2.

def _wt():
    try:
        from . import web_templates  # noqa: PLC0415
    except ImportError:  # standalone script use
        import web_templates  # noqa: PLC0415
    return web_templates


# ── vocabulary and limits ───────────────────────────────────────────────────
SHAPES = ("box", "round", "circle", "diamond", "cylinder", "cloud", "person")
CONNECTORS = ("arrow", "line")
MARKS = ("brace", "bracket", "underline", "circle-highlight")
OTHERS = ("freehand", "label", "group")
TYPES = SHAPES + CONNECTORS + MARKS + OTHERS
TONES = ("accent", "accent_hi", "text", "muted", "success")
ANCHORS = ("n", "e", "s", "w", "c")
ROUTES = ("straight", "elbow", "curved")
SIDES = ("n", "e", "s", "w")
GAPS = {"s": 0, "m": 1, "l": 2}
REL = ("right_of", "left_of", "below", "above", "inside")
COLS, ROWS = 12, 6
MAX_ELEMENTS = 40
MAX_TEXT_TOTAL = 400
MAX_POINTS = 40
MAX_STEP = 12
VIZ_W, VIZ_H = 1580, 620
CW, RH = VIZ_W / COLS, VIZ_H / ROWS
PAD = 10            # a shape is drawn inside its cells, inset by this
MIN_FONT = 20       # legibility floor (px at 1080p)
PEN_PX_PER_S = 900.0
PEN_MIN_S, PEN_MAX_S = 0.4, 2.5
_ID = re.compile(r"[a-z0-9_]{1,16}")

TEXT_LIMIT = {"label": 60, "group": 30, "arrow": 24, "line": 24, "brace": 30, "bracket": 30,
              "underline": 30, "circle-highlight": 30}


class CanvasError(ValueError):
    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


# text cleaning shared with the plugin (imported lazily so this file stays importable alone)
def _clean(value: Any, limit: int, where: str, errs: List[str]) -> Optional[str]:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        errs.append(f"{where}: text must be a string")
        return None
    _CTRL, _WS = _wt()._CTRL, _wt()._WS
    v = _WS.sub(" ", _CTRL.sub("", value)).strip()
    if len(v) > limit:
        errs.append(f"{where}: text is {len(v)} chars, limit {limit}")
        return v[:limit]
    return v or None


def _int_in(v: Any, lo: int, hi: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _num_in(v: Any, lo: float, hi: float) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi


# ── text fitting (estimate; the rendered check measures the real thing) ───
_FONT_STEPS = (34, 32, 30, 28, 26, 24, 22, 20)
LABEL_SIZE = {"s": 24, "m": 30, "l": 40}


def _text_box(kind: str, w: float, h: float) -> Tuple[float, float]:
    """Usable text area (px) inside a shape's drawn box."""
    if kind in ("circle", "cloud"):
        return w * 0.72 - 16, h * 0.70 - 8
    if kind == "diamond":
        return w * 0.55 - 8, h * 0.55 - 4
    if kind == "cylinder":
        return w - 28, h * 0.62 - 8
    if kind == "person":
        return w - 8, h * 0.40
    return w - 28, h - 16


def _lines_needed(text: str, fs: float, avail_w: float) -> int:
    # word wrap at ~0.53 em per character (Instrument Sans/Newsreader average incl. space)
    cpl = max(1, int(avail_w / (fs * 0.53)))
    lines, cur = 1, 0
    for word in text.split():
        n = len(word)
        if n > cpl:
            return 99
        if cur == 0:
            cur = n
        elif cur + 1 + n <= cpl:
            cur += 1 + n
        else:
            lines += 1
            cur = n
    return lines


def fit_font(text: str, avail_w: float, avail_h: float, steps=_FONT_STEPS) -> Optional[int]:
    for fs in steps:
        if _lines_needed(text, fs, avail_w) * fs * 1.18 <= avail_h:
            return fs
    return None


# ── validation + layout ─────────────────────────────────────────────────────
_NORM_KEYS = frozenset({"eyebrow", "title", "sketch", "pen", "continue_from", "elements", "steps", "source", "base"})
_BASE_KEYS = frozenset({"_seed0", "_sid", "_sketch"})  # carried-over elements only (``carry_over``)


def validate_canvas(data: Any, base: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Normalised canvas data (with resolved cell boxes) or CanvasError(all errors).

    The result keeps the spec it came from (``source``) and the carried-over board (``base``), and
    validating a result again validates that spec again - every caller in the render path
    (timeline, document, ladder) re-validates, so the normalised form must be accepted, and nothing
    derived (boxes, font sizes, steps) is ever trusted from the input.

    ``base``: the settled board of the scene this one continues from (``carry_over``), drawn already
    at the first frame; its elements are on the same board as the scene's own (ids, placement,
    overlap, the 40-element and 400-character limits count both) but take no step."""
    if isinstance(data, dict) and isinstance(data.get("source"), dict) and set(data) <= _NORM_KEYS:
        return validate_canvas(data["source"], base=data.get("base") if base is None else base)
    errs: List[str] = []
    if not isinstance(data, dict):
        raise CanvasError(["canvas data must be a JSON object"])
    if base is not None and (not isinstance(base, list) or not all(isinstance(b, dict) for b in base)):
        raise CanvasError(["the carried-over board must be a list of elements"])
    nb = len(base or [])
    allowed = {"eyebrow", "title", "sketch", "pen", "elements", "continue_from"}
    extra = sorted(set(data) - allowed)
    if extra:
        errs.append(f"unknown scene field(s) {extra} (allowed: {sorted(allowed)})")
    out: Dict[str, Any] = {
        "eyebrow": _clean(data.get("eyebrow"), 40, "eyebrow", errs),
        "title": _clean(data.get("title"), 80, "title", errs),
        "sketch": bool(data.get("sketch", False)),
        "pen": bool(data.get("pen", True)),
    }
    if not out["title"]:
        errs.append("title is required")
    for flag in ("sketch", "pen"):
        if flag in data and not isinstance(data[flag], bool):
            errs.append(f"{flag} must be true or false")
    # continue_from: optional scene id for revisions (previous canvas becomes base)
    cf = data.get("continue_from")
    if cf is not None:
        if not isinstance(cf, str) or not re.match(r"^[a-z][a-z0-9_]*$", cf):
            errs.append(f"continue_from must be a valid scene id (got {cf!r})")
            cf = None
        out["continue_from"] = cf
    else:
        out["continue_from"] = None
    els = data.get("elements")
    if not isinstance(els, list) or not els:
        errs.append("elements must be a non-empty list")
        raise CanvasError(errs)
    if len(els) + nb > MAX_ELEMENTS:
        errs.append(f"{len(els)} elements, limit {MAX_ELEMENTS} (split the explanation into two scenes)" if not nb else
                    f"{len(els)} elements plus {nb} carried over by continue_from, limit {MAX_ELEMENTS} on one board "
                    f"(erase elements in the earlier scene or start a new canvas)")
        els = els[:max(MAX_ELEMENTS - nb, 0)]
    els = list(base or []) + list(els)

    norm: List[Dict[str, Any]] = []
    ids: Dict[str, int] = {}
    text_total = 0
    prev_step = 1
    for k, el in enumerate(els):
        is_base = k < nb
        where = f"continue_from[{k}]" if is_base else f"elements[{k - nb}]"
        if not isinstance(el, dict):
            errs.append(f"{where}: must be an object")
            continue
        t = el.get("type")
        if t not in TYPES:
            errs.append(f"{where}: unknown type {t!r} (allowed: {', '.join(TYPES)})")
            continue
        eid = el.get("id")
        where = f"{where} ({t}{' ' + eid if isinstance(eid, str) else ''})"
        common = {"type", "id", "step", "erase_at", "tone", "text", "emphasis"}
        per = {
            **{s: {"at", "size", "gap", *REL} for s in SHAPES},
            "label": {"at", "size", "gap", "font", "style", *REL},
            "group": {"members", "at"},
            "arrow": {"from", "to", "from_anchor", "to_anchor", "route"},
            "line": {"from", "to", "from_anchor", "to_anchor", "route"},
            "freehand": {"points", "closed"},
            "brace": {"target", "targets", "side"},
            "bracket": {"target", "targets", "side"},
            "underline": {"target"},
            "circle-highlight": {"target", "side"},
        }[t]
        bad = sorted(set(el) - common - per - (_BASE_KEYS if is_base else frozenset()))
        if bad:
            errs.append(f"{where}: unknown field(s) {bad} for type {t} (allowed: {sorted(common | per)})")
        n: Dict[str, Any] = {"type": t, "k": k}
        if eid is not None:
            if not isinstance(eid, str) or not _ID.fullmatch(eid):
                errs.append(f"{where}: id must match [a-z0-9_]{{1,16}}")
            elif eid in ids:
                errs.append(f"{where}: duplicate id {eid!r}")
            else:
                ids[eid] = len(norm)
                n["id"] = eid
        elif t in SHAPES or t in ("label", "group"):
            n["id"] = f"_e{k}"
            ids[n["id"]] = len(norm)
        if is_base:
            # already on the board when the scene starts: no step, no beat, never erased here
            n["step"], n["base"] = 0, True
            if el.get("step") is not None or el.get("erase_at") is not None:
                errs.append(f"{where}: a carried-over element has no step")
            n["_seed0"] = el.get("_seed0") if _int_in(el.get("_seed0"), 0, 0xFFFFFFFF) else 0
            n["_sid"] = str(el.get("_sid", ""))[:20]
            n["_sketch"] = el.get("_sketch") is True
        else:
            step = el.get("step", prev_step)
            if not _int_in(step, 1, MAX_STEP):
                errs.append(f"{where}: step must be an integer 1-{MAX_STEP}")
                step = prev_step
            n["step"] = step
            prev_step = step
        if not is_base and el.get("erase_at") is not None:
            ea = el["erase_at"]
            if not _int_in(ea, 2, MAX_STEP) or ea <= step:
                errs.append(f"{where}: erase_at must be a step after the element's own step (<= {MAX_STEP})")
            else:
                n["erase_at"] = ea
        tone = el.get("tone", "accent" if t in CONNECTORS + MARKS + ("freehand",) else "text")
        if tone not in TONES:
            errs.append(f"{where}: tone must be one of {TONES}")
            tone = "text"
        n["tone"] = tone
        if "emphasis" in el and not isinstance(el["emphasis"], bool):
            errs.append(f"{where}: emphasis must be true or false")
        n["emphasis"] = el.get("emphasis") is True
        txt = _clean(el.get("text"), TEXT_LIMIT.get(t, 40), where, errs)
        if t == "label" and not txt:
            errs.append(f"{where}: a label needs text")
        n["text"] = txt
        text_total += len(txt or "")
        if t in ("label",):
            st = el.get("style", "body")
            if st not in ("title", "body", "note"):
                errs.append(f"{where}: style must be title|body|note")
                st = "body"
            n["style"] = st
            fz = el.get("font", "m")
            if fz not in LABEL_SIZE:
                errs.append(f"{where}: font must be s|m|l")
                fz = "m"
            n["font"] = fz
        if t in CONNECTORS:
            for key in ("from", "to"):
                if not isinstance(el.get(key), str):
                    errs.append(f"{where}: '{key}' must be an element id")
                n[key] = el.get(key)
            for key in ("from_anchor", "to_anchor"):
                a = el.get(key)
                if a is not None and a not in ANCHORS:
                    errs.append(f"{where}: {key} must be one of {ANCHORS}")
                    a = None
                n[key] = a
            r = el.get("route", "straight")
            if r not in ROUTES:
                errs.append(f"{where}: route must be one of {ROUTES}")
                r = "straight"
            n["route"] = r
        if t == "freehand":
            pts = el.get("points")
            ok = isinstance(pts, list) and 2 <= len(pts) <= MAX_POINTS and all(
                isinstance(p, list) and len(p) == 2 and _num_in(p[0], 0, COLS) and _num_in(p[1], 0, ROWS) for p in pts)
            if not ok:
                errs.append(f"{where}: points must be 2-{MAX_POINTS} [x, y] pairs in grid units, x 0-{COLS}, y 0-{ROWS}")
                pts = [[0, 0], [1, 1]]
            n["points"] = [[float(x), float(y)] for x, y in pts]
            n["closed"] = el.get("closed") is True
        if t in ("brace", "bracket", "underline", "circle-highlight"):
            tg = el.get("targets") if t in ("brace", "bracket") and el.get("targets") is not None else [el.get("target")]
            if not isinstance(tg, list) or not tg or not all(isinstance(x, str) for x in tg) or len(tg) > 8:
                errs.append(f"{where}: needs 'target' (an element id){' or targets (1-8 ids)' if t in ('brace', 'bracket') else ''}")
                tg = []
            n["targets"] = tg
            side = el.get("side", "e" if t in ("brace", "bracket") else "s")
            if t == "underline" and "side" in el:
                errs.append(f"{where}: underline has no side (its text goes below)")
            if side not in SIDES:
                errs.append(f"{where}: side must be one of {SIDES}")
                side = "e"
            n["side"] = side
        if t == "group":
            mem = el.get("members")
            if mem is not None and (not isinstance(mem, list) or not all(isinstance(x, str) for x in mem) or not mem):
                errs.append(f"{where}: members must be a list of element ids")
                mem = None
            n["members"] = mem
            if mem is None and el.get("at") is None:
                errs.append(f"{where}: a group needs members or at")
        if t in SHAPES or t in ("label", "group"):
            n["raw"] = {key: el.get(key) for key in ("at", "size", "gap", *REL) if el.get(key) is not None}
        norm.append(n)

    if text_total > MAX_TEXT_TOTAL:
        errs.append(f"total text is {text_total} chars, limit {MAX_TEXT_TOTAL}")
    if errs:
        raise CanvasError(errs)

    _resolve_boxes(norm, ids, errs)
    if not errs:
        _check_refs(norm, ids, errs)
    if not errs:
        _check_cells_and_text(norm, errs)
    if errs:
        raise CanvasError(errs)
    out["elements"] = norm
    out["steps"] = sorted({e["step"] for e in norm if not e.get("base")} | {e["erase_at"] for e in norm if e.get("erase_at")})
    out["source"] = copy.deepcopy(data)
    out["base"] = copy.deepcopy(base) if base else None
    return out


def _resolve_boxes(els: List[Dict[str, Any]], ids: Dict[str, int], errs: List[str]) -> None:
    """Every shape/label/group gets an integer cell box {col,row,w,h}; relative placement
    is resolved in dependency order (a cycle is an error)."""
    state: Dict[int, int] = {}

    def size_of(e: Dict[str, Any], where: str) -> Tuple[int, int]:
        s = e["raw"].get("size")
        if s is None:
            return (2, 1) if e["type"] != "label" else (3, 1)
        if not isinstance(s, dict) or set(s) - {"w", "h"} or not _int_in(s.get("w", 2), 1, COLS) or not _int_in(s.get("h", 1), 1, ROWS):
            errs.append(f"{where}: size must be {{w: 1-{COLS}, h: 1-{ROWS}}}")
            return 2, 1
        return int(s.get("w", 2)), int(s.get("h", 1))

    def resolve(i: int) -> Optional[Dict[str, int]]:
        e = els[i]
        where = f"elements[{e['k']}] ({e['type']} {e['id']})"
        if "box" in e:
            return e["box"]
        if state.get(i) == 1:
            errs.append(f"{where}: relative placement forms a cycle")
            return None
        state[i] = 1
        raw = e["raw"]
        box = None
        if e["type"] == "group" and e.get("members"):
            boxes = []
            for m in e["members"]:
                if m not in ids:
                    errs.append(f"{where}: member {m!r} is not an element id")
                    continue
                if els[ids[m]]["type"] not in SHAPES + ("label", "group"):
                    errs.append(f"{where}: member {m!r} is not a shape or label")
                    continue
                b = resolve(ids[m])
                if b:
                    boxes.append(b)
            if boxes:
                c0 = min(b["col"] for b in boxes); r0 = min(b["row"] for b in boxes)
                c1 = max(b["col"] + b["w"] for b in boxes); r1 = max(b["row"] + b["h"] for b in boxes)
                box = {"col": c0, "row": r0, "w": c1 - c0, "h": r1 - r0, "group_pad": True}
        elif raw.get("at") is not None:
            at = raw["at"]
            if not isinstance(at, dict) or set(at) - {"col", "row", "w", "h"} or not all(
                    _int_in(at.get(k2, 1 if k2 in "wh" else -1), 0 if k2 in ("col", "row") else 1, COLS) for k2 in ("col", "row", "w", "h")):
                errs.append(f"{where}: at must be {{col: 0-11, row: 0-5, w: 1-12, h: 1-6}} (integers)")
            else:
                w, h = size_of(e, where)
                box = {"col": at["col"], "row": at["row"], "w": at.get("w", w), "h": at.get("h", h)}
        else:
            rels = [r for r in REL if raw.get(r) is not None]
            if len(rels) != 1:
                errs.append(f"{where}: needs exactly one placement: 'at' or one of {REL}")
            else:
                r = rels[0]
                ref = raw[r]
                if not isinstance(ref, str) or ref not in ids:
                    errs.append(f"{where}: {r} must name an existing element id (got {ref!r})")
                elif els[ids[ref]]["type"] not in SHAPES + ("label", "group"):
                    errs.append(f"{where}: {r} must name a shape, label or group")
                else:
                    rb = resolve(ids[ref])
                    gap = raw.get("gap", "m")
                    if gap not in GAPS:
                        errs.append(f"{where}: gap must be s|m|l")
                        gap = "m"
                    g = GAPS[gap]
                    if rb:
                        w, h = size_of(e, where)
                        if r == "inside":
                            w = min(w, rb["w"]) if raw.get("size") else rb["w"]
                            h = min(h, rb["h"]) if raw.get("size") else rb["h"]
                            box = {"col": rb["col"] + (rb["w"] - w) // 2, "row": rb["row"] + (rb["h"] - h) // 2, "w": w, "h": h,
                                   "inside": ref}
                        elif r == "right_of":
                            box = {"col": rb["col"] + rb["w"] + g, "row": rb["row"] + (rb["h"] - h) // 2, "w": w, "h": h}
                        elif r == "left_of":
                            box = {"col": rb["col"] - g - w, "row": rb["row"] + (rb["h"] - h) // 2, "w": w, "h": h}
                        elif r == "below":
                            box = {"col": rb["col"] + (rb["w"] - w) // 2, "row": rb["row"] + rb["h"] + g, "w": w, "h": h}
                        else:
                            box = {"col": rb["col"] + (rb["w"] - w) // 2, "row": rb["row"] - g - h, "w": w, "h": h}
        state[i] = 2
        if box is not None:
            if box["col"] < 0 or box["row"] < 0 or box["col"] + box["w"] > COLS or box["row"] + box["h"] > ROWS:
                errs.append(f"{where}: resolves to col {box['col']}..{box['col'] + box['w']}, row {box['row']}..{box['row'] + box['h']} "
                            f"— outside the {COLS}x{ROWS} grid")
            e["box"] = box
        return box

    for i, e in enumerate(els):
        if e["type"] in SHAPES + ("label", "group"):
            resolve(i)


def _check_refs(els: List[Dict[str, Any]], ids: Dict[str, int], errs: List[str]) -> None:
    for e in els:
        where = f"elements[{e['k']}] ({e['type']})"
        refs = [e["from"], e["to"]] if e["type"] in CONNECTORS else e.get("targets", [])
        for r in refs:
            if r not in ids:
                errs.append(f"{where}: {r!r} is not an element id (arrows/marks must attach to existing elements)")
            elif "box" not in els[ids[r]]:
                errs.append(f"{where}: {r!r} is not a placed shape/label/group")
        if e["type"] in CONNECTORS and e["from"] == e["to"]:
            errs.append(f"{where}: from and to are the same element")
        if e["type"] in CONNECTORS and not errs:
            a, b = els[ids[e["from"]]], els[ids[e["to"]]]
            if e.get("step", 1) < max(a["step"], b["step"]):
                e["step"] = max(a["step"], b["step"])  # an arrow cannot appear before what it connects


def _cells(b: Dict[str, int]) -> set:
    return {(c, r) for c in range(b["col"], b["col"] + b["w"]) for r in range(b["row"], b["row"] + b["h"])}


def _check_cells_and_text(els: List[Dict[str, Any]], errs: List[str]) -> None:
    placed = [e for e in els if "box" in e and e["type"] != "group" and not e["box"].get("inside")]
    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            a, b = placed[i], placed[j]
            # an element erased before the other appears may share cells with it
            if a.get("erase_at") and a["erase_at"] <= b["step"] or b.get("erase_at") and b["erase_at"] <= a["step"]:
                continue
            ov = _cells(a["box"]) & _cells(b["box"])
            if ov:
                errs.append(f"{a['type']} {a['id']} and {b['type']} {b['id']} occupy the same grid cells {sorted(ov)[:3]}"
                            f" — move one (cells are col 0-11, row 0-5)")
    for e in els:
        if "box" not in e or not e.get("text"):
            continue
        x, y, w, h = px_box(e["box"])
        if e["type"] == "label":
            fs = LABEL_SIZE[e["font"]]
            if _lines_needed(e["text"], fs, w - 8) * fs * 1.18 > h - 4:
                errs.append(f"label {e['id']}: text {e['text'][:24]!r} does not fit a {e['box']['w']}x{e['box']['h']} cell box at font {e['font']} — enlarge it or shorten the text")
            e["fs"] = fs
        elif e["type"] == "group":
            e["fs"] = 22
        else:
            aw, ah = _text_box(e["type"], w - 2 * PAD, h - 2 * PAD)
            fs = fit_font(e["text"], aw, ah)
            if fs is None:
                errs.append(f"{e['type']} {e['id']}: text {e['text'][:24]!r} does not fit a {e['box']['w']}x{e['box']['h']} cell "
                            f"{e['type']} at >= {MIN_FONT}px — enlarge it (size/at) or shorten the text")
            e["fs"] = fs or MIN_FONT


def px_box(b: Dict[str, int]) -> Tuple[float, float, float, float]:
    return b["col"] * CW, b["row"] * RH, b["w"] * CW, b["h"] * RH


# ── geometry → strokes ───────────────────────────────────────────────────────
Pt = Tuple[float, float]


def _fmt(p: Pt) -> str:
    return f"{p[0]:.1f} {p[1]:.1f}"


def _poly_len(pts: List[Pt]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def _bez(p0, p1, p2, p3, n=16) -> List[Pt]:
    out = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        out.append((mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0],
                    mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1]))
    return out


def _ellipse_pts(cx, cy, rx, ry, a0=0.0, a1=2 * math.pi, n=48) -> List[Pt]:
    return [(cx + rx * math.cos(a0 + (a1 - a0) * i / n), cy + ry * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def _catmull(pts: List[Pt], closed=False) -> List[Pt]:
    """Centripetal-ish Catmull-Rom through the points, sampled as a polyline."""
    if len(pts) < 3:
        return pts
    P = ([pts[-1]] + pts + [pts[0], pts[1]]) if closed else ([pts[0]] + pts + [pts[-1]])
    out: List[Pt] = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        seg = _bez(p1, c1, c2, p2, 10)
        out.extend(seg if not out else seg[1:])
    return out


def _resample(pts: List[Pt], step=14.0) -> List[Pt]:
    L = _poly_len(pts)
    if L == 0:
        return pts
    n = max(2, int(L / step))
    out, acc, j = [pts[0]], 0.0, 0
    seglens = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
    for i in range(1, n):
        target = L * i / n
        while j < len(seglens) - 1 and acc + seglens[j] < target:
            acc += seglens[j]
            j += 1
        f = (target - acc) / seglens[j] if seglens[j] else 0
        a, b = pts[j], pts[j + 1]
        out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    out.append(pts[-1])
    return out


def _wobble(pts: List[Pt], seed: int, amp=2.2) -> List[Pt]:
    """Deterministic hand-drawn wobble: smooth seeded noise along the normal (no render-time randomness)."""
    rng = random.Random(seed)
    pts = _resample(pts)
    k = len(pts)
    knots = [rng.uniform(-1, 1) for _ in range(k // 6 + 3)]
    out = []
    for i, (x, y) in enumerate(pts):
        u = i / 6
        a = knots[int(u)]
        b = knots[int(u) + 1]
        f = u - int(u)
        f = f * f * (3 - 2 * f)
        off = (a + (b - a) * f) * amp
        px, py = pts[max(i - 1, 0)]
        nx, ny = pts[min(i + 1, k - 1)]
        dx, dy = nx - px, ny - py
        L = math.hypot(dx, dy) or 1
        out.append((x - dy / L * off, y + dx / L * off))
    return out


def _path(pts: List[Pt], closed=False) -> str:
    d = "M" + _fmt(pts[0]) + "".join("L" + _fmt(p) for p in pts[1:])
    return d + ("Z" if closed else "")


def _rect_pts(x, y, w, h, r=0.0) -> List[Pt]:
    if r <= 0:
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
    pts: List[Pt] = []
    for cx, cy, a0 in ((x + w - r, y + r, -math.pi / 2), (x + w - r, y + h - r, 0), (x + r, y + h - r, math.pi / 2), (x + r, y + r, math.pi)):
        pts.extend(_ellipse_pts(cx, cy, r, r, a0, a0 + math.pi / 2, 8))
    pts.append(pts[0])
    return pts


def _cloud_pts(x, y, w, h) -> List[Pt]:
    cx, cy = x + w / 2, y + h / 2
    rx, ry = w / 2 * 0.92, h / 2 * 0.86
    pts: List[Pt] = []
    bumps = 9
    for i in range(bumps):
        a0 = 2 * math.pi * i / bumps
        a1 = 2 * math.pi * (i + 1) / bumps
        p0 = (cx + rx * math.cos(a0), cy + ry * math.sin(a0))
        p1 = (cx + rx * math.cos(a1), cy + ry * math.sin(a1))
        mid = (a0 + a1) / 2
        bulge = (cx + rx * 1.18 * math.cos(mid), cy + ry * 1.18 * math.sin(mid))
        seg = _bez(p0, ((p0[0] + bulge[0]) / 2 + (bulge[0] - cx) * .12, (p0[1] + bulge[1]) / 2 + (bulge[1] - cy) * .12),
                   ((p1[0] + bulge[0]) / 2 + (bulge[0] - cx) * .12, (p1[1] + bulge[1]) / 2 + (bulge[1] - cy) * .12), p1, 8)
        pts.extend(seg if not pts else seg[1:])
    return pts


def shape_strokes(e: Dict[str, Any]) -> Tuple[List[List[Pt]], Optional[List[Pt]], Tuple[float, float, float, float]]:
    """(strokes, fill outline or None, drawn box) for a placed shape."""
    x, y, w, h = px_box(e["box"])
    x, y, w, h = x + PAD, y + PAD, w - 2 * PAD, h - 2 * PAD
    t = e["type"]
    if t == "box":
        p = _rect_pts(x, y, w, h, 4)
        return [p], p, (x, y, w, h)
    if t == "round":
        p = _rect_pts(x, y, w, h, min(28, h / 2, w / 2))
        return [p], p, (x, y, w, h)
    if t == "circle":
        p = _ellipse_pts(x + w / 2, y + h / 2, w / 2, h / 2, -math.pi / 2, 1.5 * math.pi)
        return [p], p, (x, y, w, h)
    if t == "diamond":
        p = [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2), (x + w / 2, y)]
        return [p], p, (x, y, w, h)
    if t == "cylinder":
        ry = min(18, h * 0.14)
        top = _ellipse_pts(x + w / 2, y + ry, w / 2, ry, math.pi, 3 * math.pi)
        bottom = _ellipse_pts(x + w / 2, y + h - ry, w / 2, ry, math.pi, 0, 24)  # through +pi/2 = the lower arc
        body = [(x, y + ry), (x, y + h - ry)] + bottom + [(x + w, y + ry)]
        fill = body + _ellipse_pts(x + w / 2, y + ry, w / 2, ry, 0, -math.pi, 24)
        return [top, body], fill, (x, y, w, h)
    if t == "cloud":
        p = _cloud_pts(x, y, w, h)
        return [p], p, (x, y, w, h)
    if t == "person":
        s = min(w, h * 0.6)
        cx = x + w / 2
        hr = s * 0.17
        head = _ellipse_pts(cx, y + hr + 2, hr, hr, -math.pi / 2, 1.5 * math.pi, 32)
        by = y + 2 * hr + 8
        body = _bez((cx - s * .32, by + s * .55), (cx - s * .32, by), (cx + s * .32, by), (cx + s * .32, by + s * .55), 20)
        return [head, body], None, (x, y, w, h)
    raise ValueError(t)


def _anchor(e: Dict[str, Any], side: str) -> Tuple[Pt, Pt]:
    """Point on the drawn outline + outward normal."""
    x, y, w, h = drawn_box(e)
    cx, cy = x + w / 2, y + h / 2
    if side == "c":
        return (cx, cy), (0, 0)
    d = {"n": ((cx, y), (0, -1)), "s": ((cx, y + h), (0, 1)), "e": ((x + w, cy), (1, 0)), "w": ((x, cy), (-1, 0))}[side]
    if e["type"] == "person" and side in ("e", "w"):
        s = min(w, h * 0.6) * 0.42
        return ((cx + s, y + h * 0.32), (1, 0)) if side == "e" else ((cx - s, y + h * 0.32), (-1, 0))
    return d


def drawn_box(e: Dict[str, Any]) -> Tuple[float, float, float, float]:
    x, y, w, h = px_box(e["box"])
    if e["type"] == "group":
        return x + 2, y - 12 if y >= 12 else y, w - 4, h + (12 if y >= 12 else 0) + 10
    if e["type"] == "label":
        return x + 4, y + 4, w - 8, h - 8
    return x + PAD, y + PAD, w - 2 * PAD, h - 2 * PAD


def _auto_sides(a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[str, str]:
    ax, ay, aw, ah = drawn_box(a)
    bx, by, bw, bh = drawn_box(b)
    dx = (bx + bw / 2) - (ax + aw / 2)
    dy = (by + bh / 2) - (ay + ah / 2)
    # prefer horizontal unless clearly stacked
    if bx >= ax + aw or bx + bw <= ax:
        if not (by >= ay + ah or by + bh <= ay) or abs(dx) >= abs(dy) * 1.2:
            return ("e", "w") if dx > 0 else ("w", "e")
    return ("s", "n") if dy > 0 else ("n", "s")


def connector_path(e: Dict[str, Any], a: Dict[str, Any], b: Dict[str, Any]) -> List[Pt]:
    sa, sb = _auto_sides(a, b)
    sa = e.get("from_anchor") or sa
    sb = e.get("to_anchor") or sb
    (p1, n1), (p2, n2) = _anchor(a, sa), _anchor(b, sb)
    gap = 8
    p1 = (p1[0] + n1[0] * gap, p1[1] + n1[1] * gap)
    tip = 14 if e["type"] == "arrow" else 0
    p2 = (p2[0] + n2[0] * (gap + tip), p2[1] + n2[1] * (gap + tip))
    if e["route"] == "straight":
        return [p1, p2]
    if e["route"] == "elbow":
        if sa in ("e", "w"):
            if sb in ("e", "w"):
                mx = (p1[0] + p2[0]) / 2
                return [p1, (mx, p1[1]), (mx, p2[1]), p2]
            return [p1, (p2[0], p1[1]), p2]
        if sb in ("n", "s"):
            my = (p1[1] + p2[1]) / 2
            return [p1, (p1[0], my), (p2[0], my), p2]
        return [p1, (p1[0], p2[1]), p2]
    dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    k = dist * 0.4
    c1 = (p1[0] + n1[0] * k, p1[1] + n1[1] * k) if n1 != (0, 0) else p1
    c2 = (p2[0] + n2[0] * k, p2[1] + n2[1] * k) if n2 != (0, 0) else p2
    if c1 == p1 and c2 == p2:
        return [p1, p2]
    return _bez(p1, c1, c2, p2, 24)


def mark_path(e: Dict[str, Any], targets: List[Dict[str, Any]]) -> Tuple[List[Pt], Optional[Tuple[float, float, str]]]:
    """Stroke for brace/bracket/underline/circle-highlight around the union of targets + where its text goes."""
    xs = [drawn_box(t) for t in targets]
    x0 = min(b[0] for b in xs); y0 = min(b[1] for b in xs)
    x1 = max(b[0] + b[2] for b in xs); y1 = max(b[1] + b[3] for b in xs)
    t = e["type"]
    if t == "circle-highlight":
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2 + 22, (y1 - y0) / 2 + 18
        pts = _ellipse_pts(cx, cy, rx, ry, -2.2, -2.2 + 2 * math.pi + 0.35, 56)
        sd = e["side"]
        return pts, {"s": (cx, cy + ry + 8, "s"), "n": (cx, cy - ry - 8, "n"), "e": (cx + rx + 12, cy, "e"),
                     "w": (cx - rx - 12, cy, "w")}[sd]
    if t == "underline":
        y = y1 + 8
        return [(x0, y), (x1, y)], (x0 + (x1 - x0) / 2, y + 8, "s")
    side = e["side"]
    off, depth = 10, 18
    if side in ("e", "w"):
        x = x1 + off if side == "e" else x0 - off
        sg = 1 if side == "e" else -1
        if t == "bracket":
            pts = [(x, y0), (x + sg * depth, y0), (x + sg * depth, y1), (x, y1)]
        else:
            ym = (y0 + y1) / 2
            pts = (_bez((x, y0), (x + sg * depth, y0), (x, ym - 6), (x + sg * depth, ym), 10)[:-1]
                   + _bez((x + sg * depth, ym), (x, ym + 6), (x + sg * depth, y1), (x, y1), 10))
            pts = (_bez((x, y0), (x + sg * depth * .6, y0), (x + sg * depth * .6, y0 + 8), (x + sg * depth * .6, ym - 14), 8)
                   + _bez((x + sg * depth * .6, ym - 14), (x + sg * depth * .6, ym - 2), (x + sg * depth, ym), (x + sg * depth * 1.1, ym), 6)[1:]
                   + _bez((x + sg * depth * 1.1, ym), (x + sg * depth, ym), (x + sg * depth * .6, ym + 2), (x + sg * depth * .6, ym + 14), 6)[1:]
                   + _bez((x + sg * depth * .6, ym + 14), (x + sg * depth * .6, y1 - 8), (x + sg * depth * .6, y1), (x, y1), 8)[1:])
        return pts, (x + sg * (depth + 14), (y0 + y1) / 2, side)
    y = y1 + off if side == "s" else y0 - off
    sg = 1 if side == "s" else -1
    if t == "bracket":
        pts = [(x0, y), (x0, y + sg * depth), (x1, y + sg * depth), (x1, y)]
    else:
        xm = (x0 + x1) / 2
        pts = (_bez((x0, y), (x0, y + sg * depth * .6), (x0 + 8, y + sg * depth * .6), (xm - 14, y + sg * depth * .6), 8)
               + _bez((xm - 14, y + sg * depth * .6), (xm - 2, y + sg * depth * .6), (xm, y + sg * depth), (xm, y + sg * depth * 1.1), 6)[1:]
               + _bez((xm, y + sg * depth * 1.1), (xm, y + sg * depth), (xm + 2, y + sg * depth * .6), (xm + 14, y + sg * depth * .6), 6)[1:]
               + _bez((xm + 14, y + sg * depth * .6), (x1 - 8, y + sg * depth * .6), (x1, y + sg * depth * .6), (x1, y), 8)[1:])
    return pts, ((x0 + x1) / 2, y + sg * (depth + 14), side)


# ── HTML builder ────────────────────────────────────────────────────────────
CANVAS_CSS = """
.cv { position: relative; margin-top: 40px; width: 1580px; height: 620px; }
.cv svg.cv-svg { position: absolute; left: 0; top: 0; overflow: visible; }
.cv .st { fill: none; stroke-width: 3.5; stroke-linecap: round; stroke-linejoin: round;
          stroke-dasharray: 1; stroke-dashoffset: 1; animation: draw var(--pd) linear both; animation-delay: var(--pt); }
.cv .st.em { stroke-width: 5; }
.cv .fl { opacity: 0; animation: fade 400ms ease-out both; animation-delay: var(--ft); }
.cv .hd { opacity: 0; animation: fade 120ms linear both; animation-delay: var(--ft); }
.cv .t { position: absolute; display: flex; align-items: center; justify-content: center; text-align: center;
         line-height: 1.18; opacity: 0; animation: fade 350ms ease-out both; animation-delay: var(--ft); color: var(--text);
         overflow-wrap: anywhere; }
.cv .t.title { font-family: var(--font-heading); }
.cv .t.note { color: var(--text-muted); font-style: italic; }
.cv .t.l-left { justify-content: flex-start; text-align: left; }
.cv .t.l-right { justify-content: flex-end; text-align: right; }
.cv .t.grp { align-items: flex-start; justify-content: flex-start; font-family: var(--font-mono); color: var(--text-muted); letter-spacing: .04em; }
.cv .t.pill span { background: var(--bg); padding: 2px 10px; border-radius: 8px; }
.cv .pen { position: absolute; left: 0; top: 0; width: 14px; height: 14px; margin: 0; border-radius: 50%;
           background: var(--accent-hi); box-shadow: 0 0 14px var(--accent); offset-rotate: 0deg; offset-anchor: center;
           opacity: 0; animation: pen var(--pd) linear none; animation-delay: var(--pt); }
@keyframes pen { from { offset-distance: 0%; opacity: 1; } to { offset-distance: 100%; opacity: 1; } }
.cv .er { animation: erase 400ms ease-in both; animation-delay: var(--at); }
@keyframes erase { from { opacity: 1; } to { opacity: 0; } }
"""

_TONE_VAR = {"accent": "var(--accent)", "accent_hi": "var(--accent-hi)", "text": "var(--text)",
             "muted": "var(--text-muted)", "success": "var(--success)"}


def _e(s: Optional[str]) -> str:
    return html.escape(s or "", quote=True)


def pen_duration(length_px: float) -> float:
    return min(PEN_MAX_S, max(PEN_MIN_S, length_px / PEN_PX_PER_S))


def build_canvas(d: Dict[str, Any]) -> str:
    els = d["elements"]
    by_id = {e["id"]: e for e in els if "id" in e}
    step_index = {s: k for k, s in enumerate(d["steps"])}
    svg: List[str] = []
    divs: List[str] = []
    pens: List[str] = []
    seed0 = zlib.crc32((d.get("title") or "").encode("utf-8"))

    def stroke_set(e, strokes: List[List[Pt]], stroke_col: str, wrap_i: int, extra_cls="", fill_pts=None,
                   head: Optional[List[Pt]] = None) -> Tuple[str, float]:
        """One <g> per element; strokes share the element's pen window, split by length. A carried-over
        element (continue_from) keeps the wobble it had in its own scene and is drawn already."""
        if e.get("base"):
            if e["_sketch"]:
                strokes = [_wobble(s, e["_seed0"] ^ zlib.crc32(f"{e['_sid']}/{j}".encode())) for j, s in enumerate(strokes)]
        elif d["sketch"]:
            strokes = [_wobble(s, seed0 ^ zlib.crc32(f"{e.get('id', e['k'])}/{j}".encode())) for j, s in enumerate(strokes)]
        lens = [_poly_len(s) for s in strokes]
        total = pen_duration(sum(lens))
        offs, acc = [], 0.0
        parts = []
        if fill_pts is not None:
            parts.append(f'<path class="fl" style="--ft:calc(var(--at) + {total * 0.55:.3f}s)" fill="var(--bg-card)" '
                         f'd="{_path(fill_pts, True)}"/>')
        for s, L in zip(strokes, lens):
            dur = total * (L / sum(lens)) if sum(lens) else total
            pd = f"--pt:calc(var(--at) + {acc:.3f}s);--pd:{dur:.3f}s"
            dpath = _path(s)
            parts.append(f'<path class="st{extra_cls}" pathLength="1" stroke="{stroke_col}" style="{pd}" d="{dpath}"/>')
            if d["pen"] and not e.get("base"):
                pens.append(f'<i class="pen" style="--i:{wrap_i};--nofocus:1;{pd};'
                            f'offset-path:path(\'{dpath}\')"></i>')
            acc += dur
        if head:
            parts.append(f'<path class="hd" fill="{stroke_col}" style="--ft:calc(var(--at) + {total:.3f}s)" d="{_path(head, True)}"/>')
        er = ""
        kind = "shape" if e["type"] in SHAPES else e["type"]
        cue = ' class="base"' if e.get("base") else f' style="--i:{wrap_i}"'
        g = (f'<g data-cv="{kind}" data-type="{e["type"]}" data-k="{e["k"]}" data-id="{_e(e.get("id", ""))}"{cue}{er}>'
             f'{"".join(parts)}</g>')
        return g, total

    def text_div(e, x, y, w, h, fs, wrap_i, delay, cls="", owner=None):
        card = ' data-incard="1"' if e["type"] in SHAPES and e["type"] != "person" and owner is None else ""
        cue = "" if e.get("base") else f"--i:{wrap_i};--ft:calc(var(--at) + {delay:.3f}s);"
        if e.get("base"):
            cls = (cls + " base").strip()
        return (f'<div class="t {cls}"{card} data-owner="{_e(owner or e.get("id", ""))}" style="{cue}'
                f'left:{x:.1f}px;top:{y:.1f}px;width:{w:.1f}px;height:{h:.1f}px;'
                f'font-size:{fs}px">{"<span>" + _e(e["text"]) + "</span>" if "pill" in cls else _e(e["text"])}</div>')

    for e in els:
        n_svg, n_div = len(svg), len(divs)
        wi = 0 if e.get("base") else 2 + step_index[e["step"]]
        col = _TONE_VAR[e["tone"]] if e["type"] not in SHAPES else ("var(--accent)" if e["emphasis"] else
                                                                    (_TONE_VAR[e["tone"]] if e["tone"] != "text" else "var(--text-muted)"))
        em = " em" if e["emphasis"] else ""
        t = e["type"]
        if t in SHAPES:
            strokes, fill, (x, y, w, h) = shape_strokes(e)
            g, total = stroke_set(e, strokes, col, wi, em, fill)
            svg.append(g)
            if e.get("text"):
                aw, ah = _text_box(t, w, h)
                if t == "person":
                    tx, ty, tw, th = x - 4, y + h * 0.6, w + 8, h * 0.4
                elif t == "cylinder":
                    tx, ty, tw, th = x + (w - aw) / 2, y + h * 0.2 + (h * 0.75 - ah) / 2, aw, ah
                else:
                    tx, ty, tw, th = x + (w - aw) / 2, y + (h - ah) / 2, aw, ah
                divs.append(text_div(e, tx, ty, tw, th, e["fs"], wi, total * 0.6, "title" if e["emphasis"] else ""))
        elif t == "label":
            x, y, w, h = drawn_box(e)
            cls = {"title": "title", "body": "", "note": "note"}[e["style"]]
            divs.append(text_div(e, x, y, w, h, e["fs"], wi, 0.0, cls))
            if e["tone"] != "text":
                divs[-1] = divs[-1].replace('class="t ', f'class="t ').replace("font-size:", f"color:{_TONE_VAR[e['tone']]};font-size:")
        elif t == "group":
            x, y, w, h = drawn_box(e)
            pts = _rect_pts(x, y, w, h, 18)
            g, total = stroke_set(e, [pts], "var(--border)" if e["tone"] == "text" else col, wi, "")
            svg.append(g)
            if e.get("text"):
                divs.append(text_div(e, x + 16, y + 6, w - 32, 30, 20, wi, 0.1, "grp"))
        elif t in CONNECTORS:
            a, b = by_id[e["from"]], by_id[e["to"]]
            pts = connector_path(e, a, b)
            head = None
            if t == "arrow":
                (qx, qy), (px_, py_) = pts[-1], pts[-2]
                L = math.hypot(qx - px_, qy - py_) or 1
                ux, uy = (qx - px_) / L, (qy - py_) / L
                tipx, tipy = qx + ux * 14, qy + uy * 14
                head = [(tipx, tipy), (qx - uy * 9, qy + ux * 9), (qx + uy * 9, qy - ux * 9)]
            g, total = stroke_set(e, [pts], col, wi, em, None, head)
            svg.append(g.replace('data-cv="arrow"', f'data-cv="arrow" data-from="{_e(e["from"])}" data-to="{_e(e["to"])}"')
                       .replace('data-cv="line"', f'data-cv="line" data-from="{_e(e["from"])}" data-to="{_e(e["to"])}"'))
            if e.get("text"):
                samp = _resample(pts, 4.0)
                mid = samp[len(samp) // 2]
                a0, a1 = samp[max(len(samp) // 2 - 3, 0)], samp[min(len(samp) // 2 + 3, len(samp) - 1)]
                if abs(a1[0] - a0[0]) >= abs(a1[1] - a0[1]):
                    divs.append(text_div(e, mid[0] - 110, mid[1] - 36, 220, 30, 20, wi, total * 0.8, "pill", owner=f"_a{e['k']}"))
                else:
                    divs.append(text_div(e, mid[0] + 10, mid[1] - 15, 230, 30, 20, wi, total * 0.8, "pill l-left", owner=f"_a{e['k']}"))
        elif t == "freehand":
            pts = [(x * CW, y * RH) for x, y in e["points"]]
            sm = _catmull(pts + ([pts[0]] if e["closed"] else []), False) if len(pts) >= 3 else pts
            g, total = stroke_set(e, [sm], col, wi, em)
            svg.append(g)
        else:  # marks
            tg = [by_id[x] for x in e["targets"]]
            pts, tpos = mark_path(e, tg)
            g, total = stroke_set(e, [pts], col, wi, em)
            svg.append(g)
            if e.get("text") and tpos:
                tx, ty, side = tpos
                fs = 22
                if side == "e":
                    divs.append(text_div(e, tx, ty - 30, 260, 60, fs, wi, total, "l-left note", owner=f"_m{e['k']}"))
                elif side == "w":
                    divs.append(text_div(e, tx - 260, ty - 30, 260, 60, fs, wi, total, "l-right note", owner=f"_m{e['k']}"))
                elif side == "s":
                    divs.append(text_div(e, tx - 150, ty, 300, 34, fs, wi, total, "note", owner=f"_m{e['k']}"))
                else:
                    divs.append(text_div(e, tx - 150, ty - 34, 300, 34, fs, wi, total, "note", owner=f"_m{e['k']}"))
        if e.get("erase_at"):
            # erase = an outer wrapper whose own cue is the erase step's (fades the whole element out)
            ei = 2 + step_index[e["erase_at"]]
            svg[n_svg:] = [f'<g class="er" style="--i:{ei};--nofocus:1">{"".join(svg[n_svg:])}</g>']
            if len(divs) > n_div:
                divs[n_div:] = [f'<div class="er" style="--i:{ei};--nofocus:1">{"".join(divs[n_div:])}</div>']

    body = (f'<div class="frame">{_header(d)}<div class="cv">'
            f'<svg class="cv-svg" width="{VIZ_W}" height="{VIZ_H}" viewBox="0 0 {VIZ_W} {VIZ_H}">{"".join(svg)}</svg>'
            f'{"".join(divs)}{"".join(pens)}</div></div>')
    return body


def _header(d):
    return _wt()._header(d)


# ── hooks called by web_templates ───────────────────────────────────────────
def validate(data: Any, err=ValueError) -> Dict[str, Any]:
    """``validate_canvas`` with the caller's error type (WebSceneError)."""
    try:
        return validate_canvas(data)
    except CanvasError as e:
        raise err("; ".join(e.errors)) from None


def reveal_steps(d: Dict[str, Any]) -> int:
    return len(d["steps"])


def css(d: Optional[Dict[str, Any]] = None) -> str:
    """The canvas rules; a board with carried-over elements adds the rules that show them at once
    (only then, so every other canvas document keeps its bytes)."""
    if d and any(e.get("base") for e in d.get("elements") or []):
        return CANVAS_CSS + BASE_CSS
    return CANVAS_CSS


BASE_CSS = """
.cv .base .st { animation: none; stroke-dashoffset: 0; }
.cv .base .fl, .cv .base .hd, .cv .t.base { animation: none; opacity: 1; }
"""


def body(d: Dict[str, Any]) -> str:
    return build_canvas(d)


def scene_item_subs(d: Dict[str, Any]) -> List[str]:
    return [""] * len(d["steps"])


def scene_items(d: Dict[str, Any]) -> List[Tuple[str, int]]:
    """(label, reveal step) per canvas step — what the narration can name (ADR-2245)."""
    out = []
    for k, s in enumerate(d["steps"]):
        texts = [e["text"] for e in d["elements"] if e["step"] == s and e.get("text")]
        out.append((texts[0] if texts else f"step {s}", 2 + k))
    return out


# ── render gate ─────────────────────────────────────────────────────────────
# Measured in the settled page (the S1 probe). The generic LAYOUT_JS found 2 of the 46 canvas
# defects of the study, this one 14. Every finding is an error of the scene.
PROBE_JS = r"""() => {
  const cv = document.querySelector('.cv'); if (!cv) return null;
  const C = cv.getBoundingClientRect();
  const hidden = el => { for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return true; }
    return false; };
  const R = r => ({x: r.left, y: r.top, w: r.width, h: r.height});
  const inter = (a, b, tol) => { const x = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
    const y = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y); return x > tol && y > tol; };
  const inside = (a, b, tol) => a.x >= b.x - tol && a.y >= b.y - tol && a.x + a.w <= b.x + b.w + tol && a.y + a.h <= b.y + b.h + tol;
  const ptIn = (p, r, s) => p.x > r.x + s && p.x < r.x + r.w - s && p.y > r.y + s && p.y < r.y + r.h - s;
  const gs = [...cv.querySelectorAll('g[data-cv]')].filter(g => !hidden(g));
  const shapes = gs.filter(g => g.dataset.cv === 'shape').map(g => {
    const p = g.querySelector('path.fl') || g.querySelector('path.st'); return {id: g.dataset.id, type: g.dataset.type, r: R(g.getBoundingClientRect())}; });
  const byId = {}; for (const s of shapes) byId[s.id] = s;
  const texts = [];
  for (const d of cv.querySelectorAll('.t')) {
    if (hidden(d)) continue;
    const rg = document.createRange(); rg.selectNodeContents(d);
    for (const line of rg.getClientRects()) if (line.width >= 1 && line.height >= 1)
      texts.push({owner: d.dataset.owner, r: R(line), txt: d.textContent.trim().slice(0, 24)});
  }
  const strokes = [];
  for (const g of gs) {
    if (g.dataset.cv === 'shape' || g.dataset.cv === 'group') continue;
    const pts = [];
    for (const p of g.querySelectorAll('path.st')) {
      const L = p.getTotalLength(), m = p.getScreenCTM();
      for (let i = 0; i <= 60; i++) { const q = p.getPointAtLength(L * i / 60);
        const s = new DOMPoint(q.x, q.y).matrixTransform(m); pts.push({x: s.x, y: s.y, f: i / 60}); }
    }
    strokes.push({kind: g.dataset.cv, k: g.dataset.k, from: g.dataset.from, to: g.dataset.to, pts});
  }
  const issues = [];
  const add = (type, a, b) => issues.push({type, a: String(a || ''), b: String(b || '')});
  // out of the canvas area (marks may hug the border: 30 px grace) or off the stage
  for (const s of shapes) if (!inside(s.r, R(C), 30) || s.r.x < 0 || s.r.y < 0 || s.r.x + s.r.w > 1920 || s.r.y + s.r.h > 1080) add('oob', s.id);
  for (const t of texts) if (!inside(t.r, R(C), 30) || t.r.x < 0 || t.r.x + t.r.w > 1920 || t.r.y + t.r.h > 1080) add('oob', t.txt);
  for (const s of strokes) if (s.pts.some(p => p.x < C.left - 30 || p.x > C.right + 30 || p.y < C.top - 30 || p.y > C.bottom + 30)) add('oob', s.kind + s.k);
  for (let i = 0; i < texts.length; i++) for (let j = i + 1; j < texts.length; j++)
    if (texts[i].owner !== texts[j].owner && inter(texts[i].r, texts[j].r, 2)) add('text-text', texts[i].txt, texts[j].txt);
  for (const t of texts) {
    const own = byId[t.owner];
    if (own && own.type !== 'person' && !inside(t.r, own.r, 4)) add('text-overflow', t.txt, t.owner);
    for (const s of shapes) if (s.id !== t.owner && inter(t.r, s.r, 2) && !inside(s.r, t.r, 0)) {
      // a label placed INSIDE a shape on purpose sits within it entirely
      if (inside(t.r, s.r, 2) && !byId[t.owner]) continue;
      add('text-shape', t.txt, s.id);
    }
  }
  for (const s of strokes) {
    const mine = '_' + (s.kind === 'arrow' || s.kind === 'line' ? 'a' : 'm') + s.k;
    const hitT = new Set(), hitS = new Set();
    for (const p of s.pts) {
      for (const t of texts) if (t.owner !== mine && t.owner !== s.from && t.owner !== s.to && ptIn(p, t.r, 2)) hitT.add(t.txt);
      if (s.kind === 'arrow' || s.kind === 'line')
        for (const sh of shapes) if (sh.id !== s.from && sh.id !== s.to && ptIn(p, sh.r, 6)) hitS.add(sh.id);
    }
    for (const t of hitT) add('stroke-text', s.kind + s.k, t);
    for (const h of hitS) add('stroke-shape', s.kind + s.k, h);
    if ((s.kind === 'arrow' || s.kind === 'line') && s.pts.length) {
      const d = (p, r) => Math.hypot(Math.max(r.x - p.x, 0, p.x - r.x - r.w), Math.max(r.y - p.y, 0, p.y - r.y - r.h));
      const a = byId[s.from] || null, b = byId[s.to] || null;
      if (a && d(s.pts[0], a.r) > 24) add('detached', s.kind + s.k, s.from);
      if (b && d(s.pts[s.pts.length - 1], b.r) > 40) add('detached', s.kind + s.k, s.to);
    }
  }
  for (let i = 0; i < shapes.length; i++) for (let j = i + 1; j < shapes.length; j++) {
    const a = shapes[i].r, b = shapes[j].r;
    if (inter(a, b, 2) && !inside(a, b, 2) && !inside(b, a, 2)) add('shape-shape', shapes[i].id, shapes[j].id);
  }
  return {issues, n_shapes: shapes.length, n_texts: texts.length, n_strokes: strokes.length};
}"""

ISSUE_TYPES = ("oob", "text-text", "text-overflow", "text-shape", "stroke-text", "stroke-shape", "detached", "shape-shape")


def probe_issues(result: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """PROBE_JS result -> layout issues in web_layout's shape ({type, a, b}); types are prefixed
    ``cv-`` so a report says which probe found them. ``None`` (no canvas in the page) -> []."""
    if not result:
        return []
    seen, out = set(), []
    for i in result.get("issues", []):
        key = (i["type"], i.get("a", ""), i.get("b", ""))
        if key not in seen:  # one finding per (kind, pair): a wrapped text run is several client rects
            seen.add(key)
            out.append({"type": "cv-" + key[0], "a": key[1], "b": key[2]})
    return out


# ── continue_from: the previous canvas is the base (ADR-2249 D1) ─────────────
def carry_over(d: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The settled board of a validated canvas as the base of a scene that continues from it.

    What is on screen at the END of that scene is carried: erased elements are not, and neither is
    anything that pointed at one (a connector, a mark, an element placed inside it). Every element
    keeps its resolved cell box (``at``) and the wobble of its own scene (``_seed0``/``_sid``/
    ``_sketch``), so the first frame of the continuation is the last frame of the scene before it.
    Auto ids are renamed ``_b<n>`` so they cannot clash with the new scene's own auto ids."""
    seed0 = zlib.crc32((d.get("title") or "").encode("utf-8"))
    els = [e for e in d["elements"] if not e.get("erase_at")]
    ids = {e["id"] for e in els if "id" in e}
    changed = True
    while changed:
        changed, keep = False, []
        for e in els:
            refs = [e["from"], e["to"]] if e["type"] in CONNECTORS else list(e.get("targets") or [])
            inside = (e.get("box") or {}).get("inside")
            if any(r not in ids for r in refs) or (inside and inside not in ids):
                ids.discard(e.get("id"))
                changed = True
                continue
            keep.append(e)
        els = keep
    rename = {e["id"]: f"_b{j}" for j, e in enumerate(els) if str(e.get("id", "")).startswith("_")}
    rid = lambda x: rename.get(x, x)  # noqa: E731
    out: List[Dict[str, Any]] = []
    for e in els:
        t = e["type"]
        r: Dict[str, Any] = {"type": t, "tone": e["tone"]}
        if "id" in e:
            r["id"] = rid(e["id"])
        if e.get("text"):
            r["text"] = e["text"]
        if e.get("emphasis"):
            r["emphasis"] = True
        if t == "label":
            r["style"], r["font"] = e["style"], e["font"]
        if t in CONNECTORS:
            r.update({"from": rid(e["from"]), "to": rid(e["to"]), "route": e["route"]})
            for key in ("from_anchor", "to_anchor"):
                if e.get(key):
                    r[key] = e[key]
        if t == "freehand":
            r["points"] = [list(p) for p in e["points"]]
            if e.get("closed"):
                r["closed"] = True
        if t in MARKS:
            if t in ("brace", "bracket"):
                r["targets"] = [rid(x) for x in e["targets"]]
            else:
                r["target"] = rid(e["targets"][0])
            if t != "underline":
                r["side"] = e["side"]
        if "box" in e:
            b = e["box"]
            if b.get("inside"):
                r["inside"] = rid(b["inside"])
                r["size"] = {"w": b["w"], "h": b["h"]}
            else:
                r["at"] = {"col": b["col"], "row": b["row"], "w": b["w"], "h": b["h"]}
        if e.get("base"):
            r.update({"_seed0": e["_seed0"], "_sid": e["_sid"], "_sketch": e["_sketch"]})
        else:
            r.update({"_seed0": seed0, "_sid": str(e.get("id", e["k"])), "_sketch": bool(d["sketch"])})
        out.append(r)
    return out


def spec_of(data: Any) -> Any:
    """The authored spec behind canvas data (normalised or not)."""
    if isinstance(data, dict) and isinstance(data.get("source"), dict) and set(data) <= _NORM_KEYS:
        return data["source"]
    return data


def attach_base(data: Any, earlier: Dict[str, Dict[str, Any]], err=ValueError) -> Any:
    """Resolve ``continue_from`` against the canvas scenes before this one (``earlier``: scene id ->
    validated data) and return the data to validate. A base handed in with the data is never
    trusted: it is always recomputed from the scene it names."""
    src = spec_of(data)
    if not isinstance(src, dict):
        return data
    cf = src.get("continue_from")
    if cf is None:
        return {"source": src}
    if not isinstance(cf, str) or cf not in earlier:
        raise err(f"continue_from {cf!r} is not an earlier canvas scene of this storyboard")
    return {"source": src, "base": carry_over(earlier[cf])}


# ── the degrade ladder's canvas rungs (ADR-2249 D1: repair -> compact -> content slide) ──
_STROKE_ISSUES = ("cv-stroke-shape", "cv-stroke-text", "cv-detached", "cv-oob")
_TEXT_ISSUES = ("cv-text-shape", "cv-text-text", "cv-text-overflow", "cv-oob")
_OPPOSITE = {"n": "s", "s": "n", "e": "w", "w": "e"}
# measure-then-reroute: what an implicated connector is tried with, in order (route, from, to anchor)
_REROUTES = (("straight", None, None), ("elbow", None, None), ("curved", "n", "n"), ("curved", "s", "s"))


def _raw_slots(d: Dict[str, Any]):
    """(source copy, base copy, per merged element index: ("base"|"own", position))."""
    src = copy.deepcopy(d["source"])
    base = copy.deepcopy(d.get("base") or [])
    slots = [("base", j) for j in range(len(base))] + [("own", j) for j in range(len(src["elements"]))]
    return src, base, slots


def _implicated(d: Dict[str, Any], issues: List[Dict[str, Any]]) -> Tuple[set, set]:
    """Merged indices of the connectors and marks a probe finding names (by stroke name or by text)."""
    by_name = {f"{e['type']}{e['k']}": e for e in d["elements"] if e["type"] in CONNECTORS + MARKS}
    by_text = {(e.get("text") or "")[:24]: e for e in d["elements"]
               if e["type"] in CONNECTORS + MARKS and e.get("text")}
    conn, marks = set(), set()
    for i in issues:
        hits = []
        if i.get("type") in _STROKE_ISSUES:
            hits.append(by_name.get(i.get("a", "")))
        if i.get("type") in _TEXT_ISSUES or i.get("type") == "cv-stroke-text":
            hits += [by_text.get(i.get("a", "")), by_text.get(i.get("b", ""))]
        for e in hits:
            if e is None:
                continue
            (conn if e["type"] in CONNECTORS else marks).add(e["k"])
    return conn, marks


def repair_variants(d: Dict[str, Any], issues: List[Dict[str, Any]]) -> List[Tuple[str, Dict[str, Any]]]:
    """Rung 1 (repair): data-only fixes of what the probe measured, nothing removed - the connectors
    it names are rerouted (``_REROUTES``), the marks it names move to the opposite side. Returns
    candidates ``(label, data)`` to MEASURE in order; [] when no finding names a connector or mark
    (a shape or freehand collision has no data-only repair)."""
    conn, marks = _implicated(d, issues)
    if not conn and not marks:
        return []
    out: List[Tuple[str, Dict[str, Any]]] = []
    seen = set()
    for n, (route, fa, ta) in enumerate(_REROUTES):
        src, base, slots = _raw_slots(d)
        changed = False
        for k in sorted(conn | marks):
            where, j = slots[k]
            el = (base if where == "base" else src["elements"])[j]
            if k in conn:
                before = (el.get("route", "straight"), el.get("from_anchor"), el.get("to_anchor"))
                el["route"] = route
                for key, val in (("from_anchor", fa), ("to_anchor", ta)):
                    if val is None:
                        el.pop(key, None)
                    else:
                        el[key] = val
                changed |= before != (route, fa, ta)
            elif n % 2 == 0 and el["type"] != "underline":
                el["side"] = _OPPOSITE[el.get("side", "e" if el["type"] in ("brace", "bracket") else "s")]
                changed = True
        key = repr((src, base))
        if changed and key not in seen:
            seen.add(key)
            label = f"reroute_{route}{'_' + fa if fa else ''}" if conn else "move_marks"
            out.append((label, {"source": src, "base": base or None}))
    return out


def compact_variant(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Rung 2 (compact): the floating labels of connectors and marks go (the shapes keep their own
    text), and the hand-drawn wobble is switched off. None when that changes nothing."""
    src, base, _ = _raw_slots(d)
    changed = bool(src.get("sketch"))
    src["sketch"] = False
    for el in list(base) + list(src["elements"]):
        if el.get("type") in CONNECTORS + MARKS and el.get("text"):
            el.pop("text")
            changed = True
    return {"source": src, "base": base or None} if changed else None


def step_bullets(d: Dict[str, Any]) -> List[str]:
    """Rung 3 (content slide): one bullet per step, every text of that step, in drawing order."""
    out = []
    for s in d["steps"]:
        texts = [e["text"] for e in d["elements"] if e["step"] == s and not e.get("base") and e.get("text")]
        if texts:
            line = " — ".join(texts)
            out.append(line if len(line) <= 110 else line[:107].rstrip() + "...")
    return out
