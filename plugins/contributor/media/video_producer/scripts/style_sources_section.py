#!/usr/bin/env python3
"""Print the "Style" section of a Corvin-Videos sources.md from a video's style snapshot.

Usage: style_sources_section.py <videos/<job>/style>          -> markdown on stdout
       style_sources_section.py <videos/<job>/style> --copy-to <Corvin-Videos/<name>/source/style>

A video without a snapshot was made with the built-in CorvinOS look and gets a one-line section.
A snapshot that exists but cannot be read is an error (exit 1), never the built-in look.
"""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.style_pack import StyleError  # noqa: E402
from src.style_store import load_snapshot  # noqa: E402


def section(snapshot: Path) -> str:
    st = load_snapshot(snapshot)
    if st is None:
        return "## Style\n\nBuilt-in CorvinOS look (no custom style).\n"
    src = st.source or {}
    lines = [
        "## Style", "",
        f"- Style: {st.name} (`{st.id}`), source: {src.get('kind', 'tokens')}"
        + (f", deck aspect {src['deck_aspect']}" if src.get("deck_aspect") else ""),
        f"- Source deck sha256: `{src['sha256']}`" if src.get("sha256") else "- Source deck sha256: n/a",
        f"- Imported: {src.get('imported_at') or 'n/a'}",
        f"- Default theme: {st.default_theme}; decor: {st.decor}; wordmark: {st.wordmark or '(none)'}; "
        f"logo: {'yes' if st.mark_png else 'no'}",
        f"- Accent (dark / light): `{st.tokens['dark']['accent']}` / `{st.tokens['light']['accent']}`",
    ]
    if st.fonts:
        lines.append("- Font mapping: " + "; ".join(f"{m['from']} -> {m['to']} ({m['reason']})" for m in st.fonts))
    if st.warnings:
        lines += ["- Warnings:"] + [f"  - {w}" for w in st.warnings]
    lines += ["", "The look is derived from a third-party template; the template's rights stay with its owner. "
                  "The original deck is not stored (only this extracted style).", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot", type=Path)
    ap.add_argument("--copy-to", type=Path)
    a = ap.parse_args(argv)
    try:
        text = section(a.snapshot)
        has_style = load_snapshot(a.snapshot) is not None
    except StyleError as e:
        print(f"error: the style snapshot at {a.snapshot} is unreadable or invalid: {e}", file=sys.stderr)
        return 1
    print(text)
    if a.copy_to and has_style:
        a.copy_to.mkdir(parents=True, exist_ok=True)
        for name in ("style.json", "logo.png"):
            if (a.snapshot / name).is_file():
                shutil.copyfile(a.snapshot / name, a.copy_to / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
