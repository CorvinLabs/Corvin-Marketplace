"""Penpot SVG board -> closed shape model as JSON on stdout (ADR-2257 strand A, T-0187).

Usage: python scripts/penpot_to_json.py BOARD.svg > board.json

Reads the file through the same hardened reader the console upload uses. Exit 0 with the JSON
model; exit 2 with the refusal on stderr when the reader refuses the file (DOCTYPE, size, unknown
Penpot structure, ...). Only typed fields are printed, never the upload's own markup.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from penpot_import import PenpotImportError, svg_to_json  # noqa: E402


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 1
    try:
        data = Path(argv[1]).read_bytes()
    except OSError as e:
        print(f"cannot read the file: {type(e).__name__}", file=sys.stderr)
        return 2
    try:
        model = svg_to_json(data)
    except PenpotImportError as e:
        print(str(e), file=sys.stderr)
        return 2
    json.dump(model, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
