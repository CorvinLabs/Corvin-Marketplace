"""Sync design tokens from Figma Variables into design_tokens.json (ADR-2238, PLAN-0940 P5).

Figma is a token SOURCE, never a render dependency: this command writes the
JSON file, rendering only reads it. Run it, review the printed diff, commit.

    vault get figma_token | python -m src.figma_sync --file-key <KEY> --token-stdin [--dry-run]

Mapping (variable name = last path segment, lower-cased, '-'/' '/'.' -> '_'):
  COLOR  bg, bg_card, border, text, text_muted, text_faint, accent, accent_hi,
         glow, success  -> <theme>.<name>; the collection's mode names decide
         the theme ("...dark..." / "...light..."), a single-mode collection
         sets both themes
  STRING heading_family, body_family, mono_family -> typography.<name>
         (must be a bundled font, otherwise the sync is refused)
  FLOAT  rise_ms -> animation.rise_ms
Aliases are resolved. Anything else is listed as ignored. The merged result
must pass web_templates.validate_tokens, or nothing is written.

The token is read from stdin only (never argv, never the environment) and is
never printed. The Variables REST API is plan-gated by Figma: a 403 says so.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .web_templates import DEFAULT_TOKENS_PATH, THEME_KEYS, WebSceneError, validate_tokens
except ImportError:  # run as a plain script
    from web_templates import DEFAULT_TOKENS_PATH, THEME_KEYS, WebSceneError, validate_tokens

FIGMA_API = "https://api.figma.com"
_LOOPBACK = re.compile(r"^http://(127\.0\.0\.1|localhost)(:\d{1,5})?$")
_FILE_KEY = re.compile(r"^[A-Za-z0-9]{8,64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_\-]{8,200}$")
_MAX_BODY = 5_000_000
TYPO_KEYS = ("heading_family", "body_family", "mono_family")

EXIT_OK, EXIT_USAGE, EXIT_AUTH, EXIT_NOT_FOUND, EXIT_HTTP, EXIT_INVALID, EXIT_EMPTY = 0, 2, 3, 4, 5, 6, 7


class FigmaSyncError(Exception):
    def __init__(self, message: str, exit_code: int):
        super().__init__(message)
        self.exit_code = exit_code


def _printable(s: Any, limit: int = 160) -> str:
    return re.sub(r"[^\x20-\x7e]", "?", str(s))[:limit]


def fetch_variables(file_key: str, token: str, api_base: str = FIGMA_API, timeout: float = 20.0) -> Dict[str, Any]:
    if not _FILE_KEY.match(file_key or ""):
        raise FigmaSyncError("file key must be 8-64 letters/digits (the part after /file/ or /design/ in the URL)", EXIT_USAGE)
    if api_base != FIGMA_API and not _LOOPBACK.match(api_base):
        raise FigmaSyncError(f"api base must be {FIGMA_API} (or a loopback URL for tests)", EXIT_USAGE)
    req = urllib.request.Request(
        f"{api_base}/v1/files/{file_key}/variables/local",
        headers={"X-Figma-Token": token, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — scheme/host checked above
            body = resp.read(_MAX_BODY + 1)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = _printable(json.loads(e.read(4096) or b"{}").get("err") or "", 120)
        except Exception:  # noqa: BLE001
            pass
        if e.code in (401, 403):
            raise FigmaSyncError(
                f"Figma refused the request (HTTP {e.code}{': ' + detail if detail else ''}). The Variables REST API "
                "needs a token with file_variables:read and a Figma plan that exposes it.", EXIT_AUTH) from None
        if e.code == 404:
            raise FigmaSyncError("Figma file not found (HTTP 404) — check the file key", EXIT_NOT_FOUND) from None
        raise FigmaSyncError(f"Figma API error HTTP {e.code}{': ' + detail if detail else ''}", EXIT_HTTP) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise FigmaSyncError(f"Figma API unreachable: {_printable(getattr(e, 'reason', e), 120)}", EXIT_HTTP) from None
    if len(body) > _MAX_BODY:
        raise FigmaSyncError("Figma response larger than 5 MB — refusing", EXIT_HTTP)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise FigmaSyncError("Figma response is not JSON", EXIT_HTTP) from None
    if not isinstance(payload, dict) or not isinstance(payload.get("meta"), dict):
        raise FigmaSyncError("Figma response has no 'meta' object", EXIT_HTTP)
    return payload


def _norm(name: str) -> str:
    return re.sub(r"[\s\-.]+", "_", str(name).split("/")[-1].strip().lower())


def _color(v: Any) -> str:
    if not isinstance(v, dict) or not all(isinstance(v.get(k), (int, float)) for k in ("r", "g", "b")):
        raise ValueError("not a colour")
    r, g, b = (max(0, min(255, round(float(v[k]) * 255))) for k in ("r", "g", "b"))
    a = float(v.get("a", 1))
    if a >= 0.999:
        return f"#{r:02x}{g:02x}{b:02x}"
    a = max(0.0, min(1.0, round(a, 2)))
    return f"rgba({r}, {g}, {b}, {a:g})"


def _theme_of(mode_name: str) -> Optional[str]:
    n = mode_name.lower()
    if "dark" in n:
        return "dark"
    if "light" in n:
        return "light"
    return None


def map_variables(payload: Dict[str, Any], current: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Tuple[str, Any, Any]], List[str]]:
    """Return (merged tokens, changes [(path, old, new)], notes)."""
    meta = payload["meta"]
    variables: Dict[str, Any] = meta.get("variables") or {}
    collections: Dict[str, Any] = meta.get("variableCollections") or {}
    tokens = copy.deepcopy(current)
    changes: List[Tuple[str, Any, Any]] = []
    notes: List[str] = []
    mapped = 0

    def mode_names(coll_id: str) -> Dict[str, str]:
        coll = collections.get(coll_id) or {}
        return {m.get("modeId"): str(m.get("name", "")) for m in coll.get("modes") or [] if isinstance(m, dict)}

    def resolve(value: Any, mode_name: str, depth: int = 0) -> Any:
        if isinstance(value, dict) and value.get("type") == "VARIABLE_ALIAS":
            if depth > 8:
                raise ValueError("alias chain too deep (cycle?)")
            target = variables.get(value.get("id"))
            if not isinstance(target, dict):
                raise ValueError("alias points at an unknown variable")
            names = mode_names(target.get("variableCollectionId"))
            by_name = {n.lower(): mid for mid, n in names.items()}
            coll = collections.get(target.get("variableCollectionId")) or {}
            mid = by_name.get(mode_name.lower(), coll.get("defaultModeId"))
            vals = target.get("valuesByMode") or {}
            if mid not in vals:
                mid = next(iter(vals), None)
            return resolve(vals.get(mid), mode_name, depth + 1)
        return value

    def set_path(section: str, key: str, value: Any) -> None:
        old = tokens.get(section, {}).get(key)
        tokens.setdefault(section, {})[key] = value
        if old != value:
            changes.append((f"{section}.{key}", old, value))

    for var in variables.values():
        if not isinstance(var, dict) or var.get("remote"):
            continue
        name, rtype = _norm(var.get("name", "")), var.get("resolvedType")
        modes = mode_names(var.get("variableCollectionId"))
        values = var.get("valuesByMode") or {}
        try:
            if rtype == "COLOR" and name in THEME_KEYS:
                targets = []
                for mid, val in values.items():
                    theme = _theme_of(modes.get(mid, ""))
                    if theme:
                        targets.append((theme, val, modes.get(mid, "")))
                    elif len(values) > 1:
                        notes.append(f"ignored mode {_printable(modes.get(mid, mid), 40)!r} of {name} (not light/dark)")
                if not targets and len(values) == 1:
                    (mid, val), = values.items()
                    targets = [("dark", val, modes.get(mid, "")), ("light", val, modes.get(mid, ""))]
                for theme, val, mname in targets:
                    set_path(theme, name, _color(resolve(val, mname)))
                    mapped += 1
            elif rtype == "STRING" and name in TYPO_KEYS:
                (mid, val), = list(values.items())[:1]
                set_path("typography", name, resolve(val, modes.get(mid, "")))
                mapped += 1
            elif rtype == "FLOAT" and name == "rise_ms":
                (mid, val), = list(values.items())[:1]
                v = resolve(val, modes.get(mid, ""))
                set_path("animation", "rise_ms", int(round(v)) if isinstance(v, (int, float)) else v)
                mapped += 1
            else:
                notes.append(f"ignored {rtype} variable {_printable(var.get('name', ''), 60)!r}")
        except (ValueError, TypeError) as e:
            notes.append(f"skipped {_printable(var.get('name', ''), 60)!r}: {e}")
    if mapped == 0:
        raise FigmaSyncError("no Figma variable matched a design token name — nothing to sync", EXIT_EMPTY)
    return tokens, changes, notes


def write_tokens_atomic(path: Path, tokens: Dict[str, Any]) -> None:
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".design_tokens.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def sync(file_key: str, token: str, out: Path, api_base: str = FIGMA_API, dry_run: bool = False) -> Tuple[List, List[str]]:
    try:
        current = json.loads(Path(out).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise FigmaSyncError(f"cannot read current tokens at {out}: {e}", EXIT_USAGE) from None
    payload = fetch_variables(file_key, token, api_base=api_base)
    merged, changes, notes = map_variables(payload, current)
    merged["source"] = f"Figma variables (file ...{file_key[-4:]}), synced {date.today().isoformat()}"
    try:
        validate_tokens(merged)
    except WebSceneError as e:
        raise FigmaSyncError(f"refusing to write: {e}", EXIT_INVALID) from None
    if not dry_run:
        write_tokens_atomic(Path(out), merged)
    return changes, notes


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="figma_sync", description="Sync Figma Variables into design_tokens.json")
    ap.add_argument("--file-key", required=True)
    ap.add_argument("--token-stdin", action="store_true", required=True,
                    help="read the Figma personal access token from stdin (never pass it as an argument)")
    ap.add_argument("--out", type=Path, default=DEFAULT_TOKENS_PATH)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--api-base", default=FIGMA_API, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    token = sys.stdin.readline().strip()
    if not _TOKEN.match(token):
        print("error: no valid token on stdin", file=sys.stderr)
        return EXIT_USAGE
    try:
        changes, notes = sync(args.file_key, token, args.out, api_base=args.api_base, dry_run=args.dry_run)
    except FigmaSyncError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.exit_code
    for path, old, new in changes:
        print(f"  {path}: {old} -> {new}")
    for n in notes:
        print(f"  note: {n}")
    verb = "would change" if args.dry_run else "changed"
    print(f"{verb} {len(changes)} token(s) in {args.out}" + (" (dry run, nothing written)" if args.dry_run else ""))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
