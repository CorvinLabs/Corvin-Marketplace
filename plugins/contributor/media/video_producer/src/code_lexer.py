"""A pinned, fragment-tolerant lexer for the ``code`` template (ADR-2249 D2, spike S4).

Contract (``tests/test_code_lexer.py`` enforces it): for ANY input text the token texts joined equal
the input byte for byte - invalid code, an excerpt cut mid-string, binary-ish noise. Every scan step
advances by at least one character and every token is a slice of the input, so the contract holds by
construction; ``tokenize`` re-checks it anyway and falls back to one plain token rather than ever
dropping or inventing a character.

Why not ``tokenize`` or Pygments: the stdlib module differs per Python version (3.12 splits f-strings)
and raises on the partial snippets an excerpt usually is; Pygments is not a declared dependency and
differs per host. This module has no imports beyond ``re`` and its output is the same everywhere.

Linear time: strings are scanned by hand (no backtracking), the regexes below are anchored with no
nested overlapping quantifiers. A hostile input (100 000 quotes, a million backslashes) costs O(n).
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Tuple

Token = Tuple[str, str]  # (kind, text)

LANGS = ("python", "shell", "json", "yaml", "text")
KINDS = frozenset({
    "keyword", "builtin", "string", "comment", "number", "name", "key", "op", "ws",
    "decorator", "variable", "flag", "prompt", "text",
})

_ALIASES = {"py": "python", "python3": "python", "bash": "shell", "sh": "shell", "zsh": "shell",
            "console": "shell", "yml": "yaml", "jsonc": "json"}


def resolve_lang(name: str | None) -> str:
    """The lexer used for a declared language. Anything unknown is ``text`` - and the caller says so."""
    n = (name or "").strip().lower()
    n = _ALIASES.get(n, n)
    return n if n in LANGS else "text"


# A fixed list, not ``keyword.kwlist``: the output must not change with the Python version.
_PY_KEYWORDS = frozenset((
    "False None True and as assert async await break class continue def del elif else except finally for "
    "from global if import in is lambda nonlocal not or pass raise return try while with yield match case"
).split())
_PY_BUILTINS = frozenset((
    "abs all any bin bool bytes callable chr dict dir divmod enumerate filter float format frozenset getattr "
    "hasattr hash hex id input int isinstance issubclass iter len list map max min next object oct open ord "
    "pow print range repr reversed round set setattr slice sorted str sum super tuple type vars zip self cls "
    "Exception ValueError TypeError KeyError RuntimeError OSError"
).split())
_SH_KEYWORDS = frozenset("if then else elif fi for while until do done case esac in function select time".split())
_SH_BUILTINS = frozenset((
    "echo cd ls cat grep sed awk export source set unset exit return read printf test curl git python python3 "
    "pip npm docker systemctl journalctl sudo mkdir rm cp mv chmod find xargs kill"
).split())

_WS = re.compile(r"[ \t\r\f\v]+")
_PY_NUM = re.compile(
    r"0[xX][0-9a-fA-F_]+|0[oO][0-7_]+|0[bB][01_]+"
    r"|(?:\d[\d_]*(?:\.[\d_]*)?|\.\d[\d_]*)(?:[eE][+-]?\d+)?[jJ]?")
_NAME = re.compile(r"[^\W\d]\w*")
_STR_PREFIX = re.compile(r"(?:[rRbBuUfF]{1,2})?(?=[\"'])")
_SH_VAR = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|\$[@#?$!*0-9]")
_SH_FLAG = re.compile(r"--?[A-Za-z][\w-]*")
_SH_WORD = re.compile(r"[^\s\"'$#|&;<>()`\\]+")
_JSON_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")


def _scan_string(text: str, i: int, quote: str, *, multiline: bool, escapes: bool = True) -> int:
    """End index (exclusive) of the string whose opening quote ends at ``i``. Unterminated: a
    single-line string stops BEFORE the newline, a multi-line one runs to the end of the input."""
    n, q = len(text), len(quote)
    while i < n:
        c = text[i]
        if escapes and c == "\\":
            i += 2
            continue
        if c == quote[0] and text.startswith(quote, i):
            return i + q
        if c == "\n" and not multiline:
            return i
        i += 1
    return min(i, n)


# ── python ───────────────────────────────────────────────────────────────────────────────────────
def _python(text: str) -> List[Token]:
    out: List[Token] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            out.append(("ws", "\n")); i += 1; continue
        m = _WS.match(text, i)
        if m:
            out.append(("ws", m.group())); i = m.end(); continue
        if c == "#":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(("comment", text[i:j])); i = j; continue
        pm = _STR_PREFIX.match(text, i)
        if pm and (pm.end() > i or c in "\"'"):
            k = pm.end()
            quote = text[k]
            if text.startswith(quote * 3, k):
                j = _scan_string(text, k + 3, quote * 3, multiline=True)
            else:
                j = _scan_string(text, k + 1, quote, multiline=False)
            out.append(("string", text[i:j])); i = j; continue
        if c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            m = _PY_NUM.match(text, i)
            if m and m.end() > i:
                out.append(("number", m.group())); i = m.end(); continue
        if c == "@":
            m = _NAME.match(text, i + 1)
            if m:
                j = m.end()
                while j + 1 < n and text[j] == "." and _NAME.match(text, j + 1):
                    j = _NAME.match(text, j + 1).end()
                out.append(("decorator", text[i:j])); i = j; continue
        m = _NAME.match(text, i)
        if m:
            w = m.group()
            kind = "keyword" if w in _PY_KEYWORDS else "builtin" if w in _PY_BUILTINS else "name"
            out.append((kind, w)); i = m.end(); continue
        out.append(("op", c) if not c.isalnum() and c.isprintable() else ("text", c)); i += 1
    return out


# ── shell ────────────────────────────────────────────────────────────────────────────────────────
def _shell(text: str) -> List[Token]:
    out: List[Token] = []
    i, n = 0, len(text)
    cmd_next = True  # the next word is a command (line start, after | ; && ( $( )
    while i < n:
        c = text[i]
        prev = text[i - 1] if i else "\n"
        if c == "\n":
            out.append(("ws", "\n")); i += 1; cmd_next = True; continue
        m = _WS.match(text, i)
        if m:
            out.append(("ws", m.group())); i = m.end(); continue
        if c == "#" and prev in " \t\n;|&(":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(("comment", text[i:j])); i = j; continue
        if c == "$" and prev == "\n" and text.startswith("$ ", i):  # a pasted prompt
            out.append(("prompt", "$")); i += 1; continue
        if c in "\"'":
            j = _scan_string(text, i + 1, c, multiline=True, escapes=(c == '"'))
            out.append(("string", text[i:j])); i = j; cmd_next = False; continue
        m = _SH_VAR.match(text, i) if c == "$" else None
        if m:
            out.append(("variable", m.group())); i = m.end(); cmd_next = False; continue
        if c == "-" and prev in " \t":
            m = _SH_FLAG.match(text, i)
            if m:
                out.append(("flag", m.group())); i = m.end(); continue
        if c in "|&;(":
            j = i + 1
            while j < n and text[j] in "|&" and c in "|&":
                j += 1
            out.append(("op", text[i:j])); i = j; cmd_next = True; continue
        if c in "<>)`\\=":
            out.append(("op", c)); i += 1; continue
        m = _SH_WORD.match(text, i)
        if m:
            w = m.group()
            if w in _SH_KEYWORDS:
                kind = "keyword"; cmd_next = w in {"then", "else", "do", "elif"}
            elif cmd_next and w in _SH_BUILTINS:
                kind = "builtin"; cmd_next = False
            elif w[0].isdigit() and w.isdigit():
                kind = "number"; cmd_next = False
            else:
                kind = "name"; cmd_next = False
            out.append((kind, w)); i = m.end(); continue
        out.append(("text", c)); i += 1
    return out


# ── json ─────────────────────────────────────────────────────────────────────────────────────────
def _json(text: str) -> List[Token]:
    out: List[Token] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            out.append(("ws", "\n")); i += 1; continue
        m = _WS.match(text, i)
        if m:
            out.append(("ws", m.group())); i = m.end(); continue
        if c == '"':
            j = _scan_string(text, i + 1, '"', multiline=False)
            k = j
            while k < n and text[k] in " \t":
                k += 1
            out.append(("key" if k < n and text[k] == ":" else "string", text[i:j])); i = j; continue
        if c == "/" and text.startswith("//", i):  # jsonc
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(("comment", text[i:j])); i = j; continue
        if c.isdigit() or (c == "-" and i + 1 < n and text[i + 1].isdigit()):
            m = _JSON_NUM.match(text, i)
            if m:
                out.append(("number", m.group())); i = m.end(); continue
        m = _NAME.match(text, i)
        if m:
            w = m.group()
            out.append(("keyword" if w in ("true", "false", "null") else "name", w)); i = m.end(); continue
        out.append(("op", c) if c in "{}[],:" else ("text", c)); i += 1
    return out


# ── yaml ─────────────────────────────────────────────────────────────────────────────────────────
def _yaml_line(line: str) -> List[Token]:
    out: List[Token] = []
    n = len(line)
    i = 0
    m = _WS.match(line, 0)
    if m:
        out.append(("ws", m.group())); i = m.end()
    while line.startswith("- ", i) or line[i:] == "-":
        out.append(("op", "-")); i += 1
        m = _WS.match(line, i)
        if m:
            out.append(("ws", m.group())); i = m.end()
    # key: the first ': ' (or trailing ':') before any quote or comment opens
    j = i
    key_end = -1
    if j < n and line[j] not in "#\"'[{&*!|>%":
        while j < n:
            ch = line[j]
            if ch == "#" and line[j - 1] in " \t":
                break
            if ch == ":" and (j + 1 == n or line[j + 1] in " \t"):
                key_end = j
                break
            j += 1
    if key_end > i:
        out.append(("key", line[i:key_end])); out.append(("op", ":")); i = key_end + 1
    while i < n:
        c = line[i]
        m = _WS.match(line, i)
        if m:
            out.append(("ws", m.group())); i = m.end(); continue
        if c == "#" and (i == 0 or line[i - 1] in " \t"):
            out.append(("comment", line[i:])); i = n; continue
        if c in "\"'":
            j = _scan_string(line, i + 1, c, multiline=False, escapes=(c == '"'))
            out.append(("string", line[i:j])); i = j; continue
        if c in "&*!":
            m = re.compile(r"[&*!][\w./-]*").match(line, i)
            out.append(("variable", m.group())); i = m.end(); continue
        if c in "|>[]{},":
            out.append(("op", c)); i += 1; continue
        j = i
        while j < n and line[j] not in " \t#,]}" :
            j += 1
        j = max(j, i + 1)
        w = line[i:j]
        kind = ("keyword" if w in ("true", "false", "null", "~", "yes", "no", "True", "False")
                else "number" if re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", w) else "name")
        out.append((kind, w)); i = j
    return out


def _yaml(text: str) -> List[Token]:
    out: List[Token] = []
    parts = text.split("\n")
    for k, line in enumerate(parts):
        if k:
            out.append(("ws", "\n"))
        if line:
            out.extend(_yaml_line(line))
    return out


# ── text: comment and string heuristics only ─────────────────────────────────────────────────────
def _plain(text: str) -> List[Token]:
    out: List[Token] = []
    parts = text.split("\n")
    for k, line in enumerate(parts):
        if k:
            out.append(("ws", "\n"))
        if not line:
            continue
        body = line.lstrip(" \t")
        if len(body) < len(line):
            out.append(("ws", line[: len(line) - len(body)]))
        if not body:  # a whitespace-only line
            continue
        if body.startswith(("#", "//", "--", ";")):
            out.append(("comment", body))
        else:
            out.append(("name", body))
    return out


_LEXERS: Dict[str, Callable[[str], List[Token]]] = {
    "python": _python, "shell": _shell, "json": _json, "yaml": _yaml, "text": _plain,
}


def scan(text: str, lang: str) -> List[Token]:
    """The raw scan, without the safety net (the fidelity test targets this)."""
    return _LEXERS[resolve_lang(lang)](text)


def tokenize(text: str, lang: str | None = None) -> List[Token]:
    """Tokens for ``text``. Joined, they are always exactly ``text``; if a bug ever broke that, one plain
    token is returned instead - the slide shows uncoloured code, never altered code."""
    text = text or ""
    toks = scan(text, resolve_lang(lang))
    if "".join(t for _, t in toks) != text or any(not t or k not in KINDS for k, t in toks):
        return [("text", text)] if text else []
    return toks


def lines(tokens: List[Token]) -> List[List[Token]]:
    """Split tokens into display lines at "\\n". A token spanning lines (a triple-quoted string) is cut
    at the newline and keeps its kind on every piece. ``"\\n".join("".join(...) per line)`` equals the input."""
    rows: List[List[Token]] = [[]]
    for kind, txt in tokens:
        if "\n" not in txt:
            rows[-1].append((kind, txt)); continue
        pieces = txt.split("\n")
        for k, piece in enumerate(pieces):
            if k:
                rows.append([])
            if piece:
                rows[-1].append((kind, piece))
    return rows
