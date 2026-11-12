#!/usr/bin/env python3
"""CorvinTV host doctor: is this machine able to render web-quality video, and if not, repair it (user space).

Usage: corvintv_doctor.py [--no-repair] [--json]
Run it with the Python that runs the console (the one that has playwright), e.g. the uv tool's python.
Exit code 0 = web quality available, 1 = not (the reason and the fix are printed).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import environment as env  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--no-repair", action="store_true", help="only check, download nothing")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    res = env.ensure(repair=not args.no_repair)
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        c, f = res["chromium"], res["ffmpeg"]
        print(f"python   : {res['python']}")
        print(f"chromium : {'OK ' + c.get('version', '') if c['ok'] else 'MISSING - ' + str(c.get('reason'))}"
              f"{' (repaired automatically)' if c.get('repaired') and c['ok'] else ''}")
        print(f"ffmpeg   : {'OK ' + str(f['path']) + ' (' + str(f['source']) + ')' if f['ok'] else 'MISSING - ' + str(f.get('reason'))}")
        for name, part in (("chromium", c), ("ffmpeg", f)):
            if not part["ok"] and part.get("fix"):
                print(f"fix {name}: {part['fix']}")
        print("web-quality video:", "yes" if res["web_quality"] and f["ok"] else "NO")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
