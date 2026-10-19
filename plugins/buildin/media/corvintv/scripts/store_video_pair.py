#!/usr/bin/env python3
"""The storage step of the Corvin-Videos convention, with its ``language_parity`` gate (ADR-2247, T-0094).

Every video is stored in two language versions (``<name>.de.mp4`` + ``<name>.en.mp4`` + ``sources.md``).
This step reads both jobs' storyboards, computes ``language_parity`` (src/signals.py: scene count +-1,
>= 80 % identical template positions, the same numeric facts in both narrations up to locale
formatting) and writes the result as the "Language parity" block of ``<dest>/sources.md`` (replacing an
earlier block, keeping everything else). Only a pair that PASSES is stored: the two MP4s are copied to
``<dest>/<name>.<lang>.mp4``. A failing pair is not stored (exit 1); its block says why.

Usage: store_video_pair.py <videos_dir> --de <job_id> --en <job_id> --dest <Corvin-Videos/<name>>
       [--check] (compute and print the block only; write nothing)
       (<videos_dir> = <tenant>/video_producer/videos; the job records are read from ../jobs/)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import signals as sg  # noqa: E402

BEGIN = "<!-- language_parity:begin (written by video_producer scripts/store_video_pair.py; do not edit) -->"
END = "<!-- language_parity:end -->"
_JOB = re.compile(r"^job_[0-9a-f]{8}$")


def storyboard_of(videos_dir: Path, job_id: str) -> List[Dict[str, Any]]:
    if not _JOB.match(job_id):
        raise ValueError(f"not a job id: {job_id!r}")
    rec = json.loads((videos_dir.parent / "jobs" / f"{job_id}.json").read_text(encoding="utf-8"))
    scenes = sg.storyboard_scene_dicts(rec.get("storyboard"))
    if not scenes:
        raise ValueError(f"{job_id} has no storyboard")
    return scenes


def _codes(xs) -> str:
    return ", ".join(f"`{x}`" for x in xs) or "none"


def block(p: Dict[str, Any], jobs: Dict[str, str], today: str) -> str:
    t, f = p["templates"], p["numeric_facts"]
    verdict = p["verdict"] + (" - " + "; ".join(p["reasons"]) if p["reasons"] else "")
    return "\n".join([
        BEGIN,
        "## Language parity",
        "",
        f"- Verdict: **{verdict}** ({'stored' if p['verdict'] == 'pass' else 'not stored by the storage step'})",
        f"- Scenes: de {p['scenes']['de']}, en {p['scenes']['en']} (a difference of one is allowed)",
        f"- Templates: {t['identical_positions']} of {t['of']} positions identical "
        f"({round((t['share'] or 0) * 100)} %, at least {round(t['threshold'] * 100)} % required)",
        f"  - de: {' · '.join(t['de'])}",
        f"  - en: {' · '.join(t['en'])}",
        f"- Numeric facts (every number and percentage of the narration, locale-normalised): "
        f"de {_codes(f['de'])}; en {_codes(f['en'])}",
        f"- Only in de: {_codes(f['only_de'])}; only in en: {_codes(f['only_en'])}",
        f"- Jobs: de `{jobs['de']}`, en `{jobs['en']}`; checked {today}",
        END,
    ]) + "\n"


def write_block(sources: Path, text: str) -> None:
    old = sources.read_text(encoding="utf-8") if sources.is_file() else ""
    if BEGIN in old and END in old:
        a, rest = old.split(BEGIN, 1)
        new = a + text.rstrip("\n") + rest.split(END, 1)[1]
    else:
        new = old.rstrip("\n") + ("\n\n" if old.strip() else "") + text
    tmp = sources.with_suffix(".md.tmp")
    tmp.write_text(new, encoding="utf-8")
    tmp.replace(sources)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("videos_dir", type=Path)
    ap.add_argument("--de", required=True)
    ap.add_argument("--en", required=True)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    jobs = {"de": a.de, "en": a.en}
    try:
        p = sg.language_parity(storyboard_of(a.videos_dir, a.de), storyboard_of(a.videos_dir, a.en),
                               langs=("de", "en"))
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    text = block(p, jobs, date.today().isoformat())
    print(text)
    if a.check:
        return 0 if p["verdict"] == "pass" else 1
    a.dest.mkdir(parents=True, exist_ok=True)
    write_block(a.dest / "sources.md", text)
    if p["verdict"] != "pass":
        print(f"not stored: language_parity failed ({'; '.join(p['reasons'])})", file=sys.stderr)
        return 1
    for lang, job in jobs.items():
        src = a.videos_dir / job / "output.mp4"
        if not src.is_file():
            print(f"error: {src} missing", file=sys.stderr)
            return 2
        shutil.copy2(src, a.dest / f"{a.dest.name}.{lang}.mp4")
    print(f"stored {a.dest.name}.de.mp4 + {a.dest.name}.en.mp4 in {a.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
