"""Code v2 for the ``code`` template (ADR-2249 D2, PLAN-0947 P1).

Opt-in: a ``code`` scene is v2 only with ``"highlight": true``. Without it nothing here runs and the
scene renders byte-identically to 1.4.x (``tests/golden_code_v1.json``).

What v2 adds, all of it data -> server-built HTML:
- tokens from the pinned lexer ``code_lexer`` (never ``tokenize``, never Pygments);
- line groups: one narrated sentence reveals and focuses lines a..b together (a beat per group);
- diff mode: every line starts with ``+``, ``-`` or a space; added/removed lines are tinted;
- annotations: a short note anchored to ``line`` (and optionally a ``cols`` range), a beat each;
- an output block: text the AUTHOR wrote, labelled "as written, not executed". Code is never run;
- up to 24 lines, with a font size computed to fit (validation refuses what cannot fit at 16 px).

Colours are style roles, DERIVED: each token class takes a role of the active palette and is mixed
toward ``text`` until it reaches 4.5:1 against every surface it can sit on (the card, the diff tints,
the annotation tint). Nothing from the model is a colour; ``validate_style`` is unchanged.

``code_fidelity`` (ADR-2249 D5): the rendered code text, tags stripped and unescaped, equals the
validated source line for line, and the lexer's raw token join equals the source byte for byte.
"""

from __future__ import annotations

import html
import math
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from . import code_lexer
except ImportError:  # standalone script use
    import code_lexer

V2_FIELDS = ("highlight", "groups", "diff", "annotations", "output")
MAX_LINES = 24
MAX_LINE_CHARS = 150  # Accommodate long hostile/test payloads; actual fit is computed per-scene
MAX_GROUPS = 8
MAX_ANNOTATIONS = 4
MAX_OUTPUT_LINES = 6
MIN_FONT_PX = 16
MAX_FONT_PX = 30
MIN_CONTRAST = 4.5
DANGER_BASE = "#e5534b"  # the fixed hue a removed line is derived from (there is no danger role)
TINT_ADD, TINT_DEL, TINT_MARK = 0.14, 0.14, 0.20

# geometry (px) the fit check and the CSS share: change one, change both
FRAME_TOP, FRAME_BOTTOM = 72, 120
RAIL_W, RAIL_GAP = 420, 32
BAR_H, PRE_PAD_Y, PRE_PAD_X = 64, 24, 36
OUT_HEAD_H, OUT_PAD_Y = 46, 14
LH, OUT_SCALE, OUT_LH = 1.45, 0.9, 1.4
CH = 0.602  # advance of one JetBrains Mono glyph per px of font size
TITLE_PX, EYEBROW_H, HEADER_GAP = 56, 52, 28
NOTE_H, NOTE_GAP = 64, 12

# token kind -> palette role (None = the line's own text colour)
ROLE_OF: Dict[str, Optional[str]] = {
    "keyword": "accent", "key": "accent", "prompt": "accent",
    "string": "success",
    "number": "accent_hi", "builtin": "accent_hi", "decorator": "accent_hi", "variable": "accent_hi",
    "comment": "text_muted", "flag": "text_muted",
    "name": None, "op": None, "ws": None, "text": None,
}
CLS = {"keyword": "kw", "key": "ky", "prompt": "pr", "string": "st", "number": "nu", "builtin": "bi",
       "decorator": "de", "variable": "va", "comment": "cm", "flag": "fl"}

OUTPUT_LABEL = {"en": "Output", "de": "Ausgabe"}
NOT_EXECUTED = {"en": "as written · not executed", "de": "wie angegeben · nicht ausgeführt"}
PLAIN_NOTE = {"en": "not highlighted", "de": "ohne Hervorhebung"}


class _Err(ValueError):
    pass


# ── validation ──────────────────────────────────────────────────────────────

def is_v2(data: Any) -> bool:
    return isinstance(data, dict) and data.get("highlight") is True


def validate(data: Dict[str, Any], *, text: Callable, code_line: Callable, lst: Callable, unknown: Callable,
             err: type) -> Dict[str, Any]:
    """The v2 contract. ``text``/``code_line``/``lst``/``unknown`` are web_templates' own helpers, so
    every free string passes the same control/bidi stripping and length caps as every other field."""
    unknown(data, ("eyebrow", "title", "language", "lines") + V2_FIELDS)
    lines = [code_line(ln, MAX_LINE_CHARS) for ln in lst(data, "lines", 1, MAX_LINES)]
    n = len(lines)
    diff = data.get("diff", False)
    if not isinstance(diff, bool):
        raise err("field 'diff' must be true or false")
    if diff:
        for k, ln in enumerate(lines, start=1):
            if ln and ln[0] not in "+- ":
                raise err(f"diff line {k} must start with '+', '-' or a space")

    groups = []
    if data.get("groups") is not None:
        last = 0
        for g in lst(data, "groups", 1, MAX_GROUPS):
            if not isinstance(g, dict):
                raise err("groups entries must be objects")
            unknown(g, ("lines", "label"))
            span = g.get("lines")
            if (not isinstance(span, list) or len(span) != 2
                    or any(isinstance(v, bool) or not isinstance(v, int) for v in span)):
                raise err("a group's 'lines' must be [first, last] (1-based line numbers)")
            a, b = span
            if not 1 <= a <= b <= n:
                raise err(f"group lines [{a}, {b}] outside 1..{n}")
            if a <= last:
                raise err("groups must be in order and must not overlap")
            last = b
            groups.append({"lines": [a, b], "label": text(g, "label", 40, False)})

    annotations = []
    if data.get("annotations") is not None:
        for an in lst(data, "annotations", 1, MAX_ANNOTATIONS):
            if not isinstance(an, dict):
                raise err("annotations entries must be objects")
            unknown(an, ("line", "cols", "label"))
            ln = an.get("line")
            if isinstance(ln, bool) or not isinstance(ln, int) or not 1 <= ln <= n:
                raise err(f"annotation 'line' must be a line number in 1..{n}")
            cols = an.get("cols")
            if cols is not None:
                body = _split_marker(lines[ln - 1], diff)[1]
                if (not isinstance(cols, list) or len(cols) != 2
                        or any(isinstance(v, bool) or not isinstance(v, int) for v in cols)):
                    raise err("annotation 'cols' must be [first, last] (1-based columns of the code)")
                if not 1 <= cols[0] <= cols[1] <= len(body):
                    raise err(f"annotation cols {cols} outside line {ln} (1..{len(body)})")
                cols = [cols[0], cols[1]]
            annotations.append({"line": ln, "cols": cols, "label": text(an, "label", 36)})

    output = None
    if data.get("output") is not None:
        o = data["output"]
        if not isinstance(o, dict):
            raise err("field 'output' must be an object {\"lines\": [...], \"label\"?}")
        unknown(o, ("lines", "label"))
        output = {"lines": [code_line(ln, MAX_LINE_CHARS) for ln in lst(o, "lines", 1, MAX_OUTPUT_LINES)],
                  "label": text(o, "label", 24, False)}

    out = {"title": text(data, "title", 80), "language": text(data, "language", 24, False),
           "highlight": True, "lines": lines, "diff": diff, "output": output}
    if groups:  # only include groups if non-empty
        out["groups"] = groups
    if annotations:  # only include annotations if non-empty
        out["annotations"] = annotations
    fs = font_px({"eyebrow": text(data, "eyebrow", 40, False), **out})
    if fs < MIN_FONT_PX:
        raise err(f"too much code for one slide ({n} lines, longest {max(len(x) for x in lines)} chars"
                  f"{', with output' if output else ''}{', with annotations' if annotations else ''}): "
                  f"it would need {fs}px text, minimum {MIN_FONT_PX}px — split the scene or shorten lines")
    return out


def strip_v2(data: Any) -> Optional[Dict[str, Any]]:
    """The same scene as a 1.4 code scene (the first rung of the degrade ladder), or None when the
    data has nothing a v1 scene could show. Diff markers stay in the text; groups/notes/output go."""
    if not isinstance(data, dict):
        return None
    return {k: v for k, v in data.items() if k not in V2_FIELDS}


# ── layout ──────────────────────────────────────────────────────────────────

def _title_lines(title: str) -> int:
    return max(1, math.ceil(len(title or "") * 0.47 * TITLE_PX / 1580))


def font_px(d: Dict[str, Any]) -> int:
    """The code font size (px) that fits the slide: width by the longest line, height by the line
    count plus header and output block. Below MIN_FONT_PX the scene is refused at validation."""
    n = len(d["lines"])
    gutter = len(str(n)) + 1 + (2 if d.get("diff") else 0)
    longest = max([len(x) for x in d["lines"]] + [len(x) + 0 for x in ((d.get("output") or {}).get("lines") or [])])
    width = 1580 - (RAIL_W + RAIL_GAP if d.get("annotations") else 0) - 2 * PRE_PAD_X - 2
    fs_w = width / (CH * (longest + gutter + 1))
    header = (EYEBROW_H if d.get("eyebrow") else 0) + _title_lines(d.get("title")) * TITLE_PX * 1.1 + HEADER_GAP
    avail = 1080 - FRAME_TOP - FRAME_BOTTOM - header - BAR_H - 2 * PRE_PAD_Y - 2
    rows = LH * n
    if d.get("output"):
        avail -= OUT_HEAD_H + 2 * OUT_PAD_Y + 1
        rows += OUT_LH * OUT_SCALE * len(d["output"]["lines"])
    fs_h = avail / rows
    return int(min(MAX_FONT_PX, fs_w, fs_h))


def _split_marker(line: str, diff: bool) -> Tuple[str, str]:
    if diff and line and line[0] in "+- ":
        return line[0], line[1:]
    return "", line


def units(d: Dict[str, Any]) -> List[Tuple[int, int]]:
    """The revealable line units, 0-based inclusive: the groups, or one unit per line without groups."""
    if d.get("groups"):
        return [(g["lines"][0] - 1, g["lines"][1] - 1) for g in d["groups"]]
    return [(k, k) for k in range(len(d["lines"]))]


def steps(d: Dict[str, Any]) -> Dict[str, Any]:
    """Reveal steps (ADR-2245): 2.. for line units, then one per annotation, then the output."""
    u = units(d)
    a0 = 2 + len(u)
    return {"units": [2 + k for k in range(len(u))],
            "annotations": [a0 + k for k in range(len(d.get("annotations") or []))],
            "output": a0 + len(d.get("annotations") or []) if d.get("output") else None}


def reveal_steps(d: Dict[str, Any]) -> int:
    return len(units(d)) + len(d.get("annotations") or []) + (1 if d.get("output") else 0)


def scene_items(d: Dict[str, Any]) -> List[Tuple[str, int]]:
    st = steps(d)
    items: List[Tuple[str, int]] = []
    groups = d.get("groups") or []
    for k, (a, b) in enumerate(units(d)):
        label = (groups[k].get("label") if groups else None) or " ".join(
            x.strip() for x in d["lines"][a:b + 1] if x.strip())
        items.append((label[:120], st["units"][k]))
    for an, s in zip(d.get("annotations") or [], st["annotations"]):
        items.append((an["label"], s))
    if d.get("output"):
        items.append((d["output"].get("label") or "Output", st["output"]))
    return items


def scene_item_subs(d: Dict[str, Any]) -> List[str]:
    subs = [""] * len(units(d)) + [""] * len(d.get("annotations") or [])
    if d.get("output"):
        subs.append("Output Ausgabe Ergebnis result prints")
    return subs


# ── colour derivation ───────────────────────────────────────────────────────

_HEX6 = re.compile(r"#[0-9a-fA-F]{6}")
_RGBA = re.compile(r"rgba\((\d{1,3}), ?(\d{1,3}), ?(\d{1,3}), ?[\d.]+\)")


def _hex(value: Any) -> Optional[str]:
    if isinstance(value, str) and _HEX6.fullmatch(value):
        return value.lower()
    m = _RGBA.fullmatch(value) if isinstance(value, str) else None
    if m:
        return "#%02x%02x%02x" % tuple(min(255, int(m.group(i))) for i in (1, 2, 3))
    return None


def _sp():
    """style_pack's colour maths, imported lazily: style_pack imports web_templates."""
    try:
        from . import style_pack
    except ImportError:  # standalone script use
        import style_pack
    return style_pack


def surfaces(palette: Dict[str, Any]) -> List[str]:
    mix = _sp().mix
    card = _hex(palette.get("bg_card")) or "#000000"
    succ = _hex(palette.get("success")) or card
    acc = _hex(palette.get("accent")) or card
    danger = derive_danger(palette)
    return [card, mix(card, succ, TINT_ADD), mix(card, danger, TINT_DEL), mix(card, acc, TINT_MARK)]


def _derive(role: str, text: str, surf: List[str]) -> str:
    contrast, mix = _sp().contrast, _sp().mix
    for k in range(0, 21):
        c = mix(role, text, k / 20)
        if min(contrast(c, s) for s in surf) >= MIN_CONTRAST:
            return c
    return text


def derive_danger(palette: Dict[str, Any]) -> str:
    contrast, mix = _sp().contrast, _sp().mix
    card = _hex(palette.get("bg_card")) or "#000000"
    text = _hex(palette.get("text")) or "#ffffff"
    for k in range(0, 21):
        c = mix(DANGER_BASE, text, k / 20)
        if contrast(c, card) >= MIN_CONTRAST:
            return c
    return text


def token_colours(palette: Dict[str, Any]) -> Dict[str, str]:
    """kind -> derived #rrggbb for every token class that has a role. Same palette, same colours."""
    text = _hex(palette.get("text")) or "#ffffff"
    surf = surfaces(palette)
    out: Dict[str, str] = {}
    for kind, role in ROLE_OF.items():
        if role is None:
            continue
        base = _hex(palette.get(role)) or text
        out[kind] = _derive(base, text, surf)
    out["danger"] = _derive(derive_danger(palette), text, surf)
    out["success_marker"] = _derive(_hex(palette.get("success")) or text, text, surf)
    return out


def css(palette: Dict[str, Any]) -> str:
    """Per-document CSS for a v2 scene: derived colours as custom properties plus the layout rules.
    Only a v2 document carries it, so no other document's bytes change."""
    mix = _sp().mix
    col = token_colours(palette)
    card = _hex(palette.get("bg_card")) or "#000000"
    v = "".join(f"--tk-{CLS[k]}:{col[k]};" for k in CLS)
    v += (f"--tk-add:{col['success_marker']};--tk-del:{col['danger']};"
          f"--tint-add:{mix(card, _hex(palette.get('success')) or card, TINT_ADD)};"
          f"--tint-del:{mix(card, derive_danger(palette), TINT_DEL)};"
          f"--tint-mark:{mix(card, _hex(palette.get('accent')) or card, TINT_MARK)};")
    rules = "".join(f".cv2 .t-{c}{{color:var(--tk-{c})}}" for c in CLS.values())
    return (
        f".cv2{{{v}}}"
        f".frame.cv2{{padding:{FRAME_TOP}px 170px {FRAME_BOTTOM}px}}"
        f".cv2 .title{{font-size:{TITLE_PX}px;line-height:1.1}}"
        f".cv2 .eyebrow{{margin-bottom:20px}}"
        f".cv2 .row{{display:flex;gap:{RAIL_GAP}px;margin-top:{HEADER_GAP}px;align-items:flex-start}}"
        f".cv2 .term{{margin-top:0;flex:1 1 auto;min-width:0}}"
        f".cv2 .term .bar-top{{height:{BAR_H}px;padding:0 28px}}"
        f".cv2 pre{{padding:{PRE_PAD_Y}px {PRE_PAD_X}px;font-family:var(--font-mono);font-size:var(--cfs);"
        f"line-height:{LH};color:var(--text);white-space:pre}}"
        ".cv2 .ln2{display:block;height:var(--clh);clip-path:inset(0 100% 0 0);"
        "animation:type 600ms steps(24,end) both;animation-delay:calc(var(--at) + var(--k,0) * 110ms)}"
        ".cv2 .ln2 .no{color:var(--text-muted);opacity:.7;user-select:none}"
        ".cv2 .ln2.add{background:var(--tint-add)}.cv2 .ln2.del{background:var(--tint-del)}"
        ".cv2 .ln2 .mk{font-weight:700}.cv2 .ln2.add .mk{color:var(--tk-add)}.cv2 .ln2.del .mk{color:var(--tk-del)}"
        ".cv2 .mark{border-radius:4px;box-shadow:inset 0 -3px 0 transparent;"
        "animation:mark-in 500ms ease-out both;animation-delay:var(--at)}"
        "@keyframes mark-in{from{background:transparent;box-shadow:inset 0 -3px 0 transparent}"
        "to{background:var(--tint-mark);box-shadow:inset 0 -3px 0 var(--accent)}}"
        f".cv2 .out{{border-top:1px dashed var(--border);padding:{OUT_PAD_Y}px {PRE_PAD_X}px}}"
        f".cv2 .out .oh{{height:{OUT_HEAD_H - 10}px;display:flex;gap:18px;align-items:baseline;"
        "font-family:var(--font-mono);font-size:20px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-muted)}"
        ".cv2 .out .oh b{font-weight:600;color:var(--accent)}.cv2 .out .oh span{letter-spacing:.04em;text-transform:none}"
        f".cv2 .out pre{{padding:0;font-size:calc(var(--cfs) * {OUT_SCALE});line-height:{OUT_LH};color:var(--text)}}"
        f".cv2 .rail{{position:relative;flex:0 0 {RAIL_W}px;width:{RAIL_W}px;align-self:stretch}}"
        f".cv2 .anno{{position:absolute;left:36px;right:0;min-height:{NOTE_H - 8}px;padding:10px 18px;"
        "border-left:4px solid var(--accent);border-radius:10px;background:var(--bg-card);"
        "font-family:var(--font-body);font-size:24px;line-height:1.25;color:var(--text);display:flex;align-items:center}"
        ".cv2 .rail svg{position:absolute;left:0;top:0;overflow:visible}"
        ".cv2 .rail path{fill:none;stroke:var(--accent);stroke-width:2;opacity:0;"
        "animation:fade 300ms ease-out both;animation-delay:var(--at)}"
        + rules
    )


# ── rendering ───────────────────────────────────────────────────────────────

def _e(s: str) -> str:
    return html.escape(s, quote=True)


def line_tokens(d: Dict[str, Any]) -> Tuple[List[List[code_lexer.Token]], bool]:
    """Tokens per display line (diff markers excluded) and whether the lexer was exact."""
    bodies = [_split_marker(ln, d.get("diff"))[1] for ln in d["lines"]]
    source = "\n".join(bodies)
    lang = code_lexer.resolve_lang(d.get("language"))
    raw = code_lexer.scan(source, lang)
    exact = "".join(t for _, t in raw) == source
    rows = code_lexer.lines(code_lexer.tokenize(source, lang))
    rows += [[] for _ in range(len(bodies) - len(rows))]
    return rows[: len(bodies)], exact


def _line_html(tokens: List[code_lexer.Token], marks: List[Tuple[int, int, int]]) -> str:
    """Token spans; a mark (0-based column range + its step) wraps the columns it covers."""
    out: List[str] = []
    col = 0
    for kind, txt in tokens:
        pieces: List[Tuple[str, Optional[int]]] = []
        start = col
        cuts = sorted({start, start + len(txt)} | {c for a, b, _ in marks for c in (a, b + 1) if start < c < start + len(txt)})
        for x, y in zip(cuts, cuts[1:]):
            step = next((s for a, b, s in marks if a <= x and y - 1 <= b), None)
            pieces.append((txt[x - start:y - start], step))
        col += len(txt)
        cls = CLS.get(kind)
        for piece, step in pieces:
            inner = _e(piece)
            if cls:
                inner = f'<span class="t-{cls}">{inner}</span>'
            out.append(inner if step is None else f'<span class="mark" style="--i:{step};--nofocus:1">{inner}</span>')
    # adjacent pieces of one mark render as separate spans; that is fine visually (no gaps: no padding)
    return "".join(out) or "&#8203;"


def _fvar(step: int, default: int) -> str:
    return f"var(--f{step},{default})"


def body(d: Dict[str, Any], lang: str = "en") -> str:
    """The slide body for a validated v2 scene (same frame/header shape as every template)."""
    try:
        from .web_templates import _header
    except ImportError:
        from web_templates import _header
    lang = lang if lang in OUTPUT_LABEL else "en"
    fs = font_px(d)
    lh = round(fs * LH, 2)
    st = steps(d)
    u = units(d)
    rows, _ = line_tokens(d)
    n = len(d["lines"])
    width_no = len(str(n))
    annos = d.get("annotations") or []
    marks_by_line: Dict[int, List[Tuple[int, int, int]]] = {}
    anno_by_line: Dict[int, List[int]] = {}
    for an, s in zip(annos, st["annotations"]):
        if an.get("cols"):
            marks_by_line.setdefault(an["line"] - 1, []).append((an["cols"][0] - 1, an["cols"][1] - 1, s))
        anno_by_line.setdefault(an["line"] - 1, []).append(s)

    unit_of = {}
    for k, (a, b) in enumerate(u):
        for i in range(a, b + 1):
            unit_of[i] = k

    def line(i: int, k_in_unit: int) -> str:
        mk, _ = _split_marker(d["lines"][i], d.get("diff"))
        cls = " add" if mk == "+" else " del" if mk == "-" else ""
        gutter = f'<span class="no">{str(i + 1).rjust(width_no)} </span>'
        if d.get("diff"):
            gutter += f'<span class="mk">{_e(mk or " ")}</span> '
        code = _line_html(rows[i], marks_by_line.get(i, []))
        return f'<span class="ln2{cls}" style="--k:{k_in_unit}">{gutter}<span class="cd">{code}</span></span>'

    unit_steps = st["units"]
    parts: List[str] = []
    i = 0
    while i < n:
        k = unit_of.get(i)
        if k is None:  # context lines outside every group: shown with the frame, dimmed while a group is in focus
            j = i
            while j < n and j not in unit_of:
                j += 1
            dim = "min(" + ",".join(_fvar(s, 1) for s in unit_steps) + ")" if unit_steps else "1"
            parts.append(f'<div class="grp ctx" style="--i:1;--nofocus:1;filter:opacity({dim})">'
                         + "".join(line(x, x - i) for x in range(i, j)) + "</div>")
            i = j
            continue
        a, b = u[k]
        s = unit_steps[k]
        own = sorted({x for ln in range(a, b + 1) for x in anno_by_line.get(ln, [])})
        lit = "max(" + ",".join([_fvar(s, 1)] + [_fvar(x, 0) for x in own]) + ")" if own else _fvar(s, 1)
        glow = (f" drop-shadow(0 0 calc(var(--g{s},0) * 10px) "
                f"rgb(from var(--accent) r g b / calc(var(--g{s},0) * .55)))")
        parts.append(f'<div class="grp" style="--i:{s};--nofocus:1;filter:opacity({lit}){glow}">'
                     + "".join(line(x, x - a) for x in range(a, b + 1)) + "</div>")
        i = b + 1

    resolved = code_lexer.resolve_lang(d.get("language"))
    label = ""
    if d.get("language"):
        plain = resolved == "text" and d["language"].strip().lower() not in ("text", "txt", "plain")
        label = f"<span>{_e(d['language'])}{' · ' + PLAIN_NOTE[lang] if plain else ''}{' · diff' if d.get('diff') else ''}</span>"
    elif d.get("diff"):
        label = "<span>diff</span>"

    out_html = ""
    if d.get("output"):
        o = d["output"]
        head = (f'<div class="oh"><b>{_e(o.get("label") or OUTPUT_LABEL[lang])}</b>'
                f'<span>{NOT_EXECUTED[lang]}</span></div>')
        text = "".join(f'<span class="oln">{_e(x) or "&#8203;"}</span>\n' for x in o["lines"]).rstrip("\n")
        out_html = f'<div class="out r" style="--i:{st["output"]}">{head}<pre>{text}</pre></div>'

    term = (f'<div class="term r" style="--i:1;--cfs:{fs}px;--clh:{lh}px">'
            f'<div class="bar-top"><i></i><i></i><i></i>{label}</div>'
            f'<pre>{"".join(parts)}</pre>{out_html}</div>')

    rail = ""
    if annos:
        rail = _rail(d, annos, st["annotations"], fs, lh)
    return f'<div class="frame cv2">{_header(d)}<div class="row">{term}{rail}</div></div>'


def _rail(d: Dict[str, Any], annos: List[Dict[str, Any]], anno_steps: List[int], fs: int, lh: float) -> str:
    """Notes beside the code, each at the height of its line (pushed apart so none overlap), a thin
    connector from the code's edge to the note."""
    ys = [BAR_H + 1 + PRE_PAD_Y + (an["line"] - 1) * lh + lh / 2 for an in annos]
    order = sorted(range(len(annos)), key=lambda k: (ys[k], k))
    tops: Dict[int, float] = {}
    floor = 0.0
    for k in order:
        top = max(ys[k] - NOTE_H / 2, floor)
        tops[k] = top
        floor = top + NOTE_H + NOTE_GAP
    notes, paths = [], []
    for k, (an, s) in enumerate(zip(annos, anno_steps)):
        cy = tops[k] + NOTE_H / 2
        paths.append(f'<path style="--i:{s};--nofocus:1" d="M-{RAIL_GAP - 4} {ys[k]:.1f} '
                     f'C 10 {ys[k]:.1f}, 10 {cy:.1f}, 36 {cy:.1f}"/>')
        notes.append(f'<div class="anno r" style="--i:{s};top:{tops[k]:.1f}px">{_e(an["label"])}</div>')
    height = max(floor, 10)
    return (f'<div class="rail"><svg width="{RAIL_W}" height="{height:.0f}">{"".join(paths)}</svg>'
            f'{"".join(notes)}</div>')


# ── code_fidelity (ADR-2249 D5) ─────────────────────────────────────────────

_TAG = re.compile(r"<[^>]*>")
_CD = re.compile(r'<span class="cd">(.*?)</span></span>(?=<span class="ln2|</div>)', re.S)


def fidelity(d: Dict[str, Any], lang: str = "en") -> Dict[str, Any]:
    """Measure one validated v2 scene: (1) the lexer's raw tokens joined equal the source byte for
    byte, (2) the code text in the rendered body, tags stripped and unescaped, equals the source
    line for line. Both must hold for ``identical``."""
    _, exact = line_tokens(d)
    doc = body(d, lang)
    shown = [html.unescape(_TAG.sub("", m)).replace("​", "") for m in _CD.findall(doc)]
    want = [_split_marker(ln, d.get("diff"))[1] for ln in d["lines"]]
    rendered = shown == want
    return {"lines": len(want), "lexer_exact": exact, "rendered_exact": rendered, "identical": exact and rendered}


def summarize(results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The job-level signal: share of v2 code scenes whose shown code is the source, byte for byte.
    None when the video has no v2 code scene (no data is not a pass)."""
    if not results:
        return None
    ok = sum(1 for r in results if r.get("identical"))
    return {"scenes": len(results), "identical": ok, "value": round(ok / len(results), 4),
            "pass": ok == len(results)}
