"""P0 spike report: run the PowerPoint style importer over a local corpus (never committed).

Usage: CORVIN_STYLE_CORPUS=dir[:dir...] python scripts/style_corpus_report.py [dir ...]
Prints only structural facts per deck (short hash label); never slide text, notes or authors.
"""
import hashlib
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import style_import_pptx as imp  # noqa: E402
from src.style_pack import contrast  # noqa: E402

EXTS = (".pptx", ".potx")


def collect(dirs):
    seen, files = {}, 0
    for d in dirs:
        for p in sorted(Path(d).rglob("*")):
            if p.is_file() and p.suffix.lower() in EXTS:
                files += 1
                data = p.read_bytes()
                seen.setdefault(hashlib.sha256(data).hexdigest(), data)
    return files, seen


def main(argv):
    dirs = argv[1:] or [d for d in os.environ.get("CORVIN_STYLE_CORPUS", "").split(os.pathsep) if d]
    if not dirs:
        print("set CORVIN_STYLE_CORPUS or pass directories")
        return 2
    files, decks = collect(dirs)
    print(f"{files} files, {len(decks)} distinct (sha256)")
    print(f"{'deck':8} {'aspect':6} {'default':8} {'accent':8} {'ctr':5} {'fonts':34} {'logo':10} {'warn':4} {'ms':>5}")
    ok = defaults = sampled = a169 = a43 = 0
    for sha, data in sorted(decks.items()):
        t0 = time.perf_counter()
        try:
            res = imp.import_pptx(data, "")
        except imp.PptxImportError as e:
            print(f"{sha[:8]:8} ERROR {str(e)[:60]}")
            continue
        ms = (time.perf_counter() - t0) * 1000
        st = res.style
        ok += 1
        own = st.tokens[st.default_theme]
        is_default = any("default Office colours" in w for w in st.warnings)
        neutral = any("neutral accent" in w for w in st.warnings)
        defaults += is_default
        sampled += is_default and not neutral
        asp = st.source["deck_aspect"]
        a169 += asp == "16:9"
        a43 += asp == "4:3"
        fonts = ",".join(f"{m['from']}>{m['to']}" for m in st.fonts)[:34]
        logo = "none"
        if st.mark_png:
            from PIL import Image
            import io
            logo = "x".join(map(str, Image.open(io.BytesIO(st.mark_png)).size))
        print(f"{sha[:8]:8} {asp:6} {str(is_default):8} {own['accent']:8} {contrast(own['bg'], own['accent']):5.1f} "
              f"{fonts:34} {logo:10} {len(st.warnings):4} {ms:5.0f}")
    print(f"\nimported without error: {ok}/{len(decks)}; default-palette decks: {defaults}; "
          f"of those with a sampled non-default accent: {sampled}; neutral-flagged: {defaults - sampled}; "
          f"16:9: {a169}, 4:3: {a43}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
