"""Code scenes WITHOUT the v2 opt-in (ADR-2249 D2, invariant 1): every one of these must render
byte-identically to 1.4.x. ``golden_code_v1.json`` holds their sha256, computed on Marketplace
``31e760a`` (before Code v2 existed) by ``python -m tests.code_v1_cases --write``."""

import hashlib
import json
import sys
from pathlib import Path

from src.web_templates import build_document, scene_item_subs, scene_items, validate_scene_data
from src.web_timeline import AudioPauses, build_timeline

GOLDEN_PATH = Path(__file__).parent / "golden_code_v1.json"

DATA = {
    "shell": {"title": "Install", "language": "sh", "lines": ["$ pip install corvinos", "# then", "$ corvinos-serve --port 8765"]},
    "python": {"eyebrow": "Python", "title": "A function", "language": "python",
               "lines": ["def add(a, b):", "    # sum", "    return a + b", "", "print(add(1, 2))"]},
    "nolang": {"title": "Twelve lines", "lines": [f"line {k} = {k * k}  // c" for k in range(12)]},
    "escape": {"title": "<b>x</b> & y", "language": "<js>", "lines": ["if (a < b && c > d) { x = \"q\"; }", "  $ not a prompt", "\tindented"]},
}
NARRATION = "Zuerst installieren wir das Paket. Dann starten wir den Server auf Port 8765. Fertig."
PAUSES = AudioPauses(duration=9.0, pause_ends=[3.0, 6.0], speech_start=0.0, speech_end=9.0, silent_ratio=0.1)


def cases():
    for name, data in DATA.items():
        for theme in ("dark", "light"):
            yield f"{name}|{theme}|plain", dict(template="code", data=data, duration_s=7, theme=theme)
            yield f"{name}|{theme}|idx", dict(template="code", data=data, duration_s=7, theme=theme,
                                              scene_index=2, total_scenes=5, compact=True)
            d = validate_scene_data("code", data)
            tl = build_timeline("code", scene_items("code", d), NARRATION, PAUSES, beats=[0, 1, None][:3],
                                subs=scene_item_subs("code", d))
            yield f"{name}|{theme}|timeline", dict(template="code", data=data, duration_s=9, theme=theme, timeline=tl)


def digest(kw) -> str:
    kw = dict(kw)
    return hashlib.sha256(build_document(kw.pop("template"), kw.pop("data"), **kw).encode()).hexdigest()


if __name__ == "__main__" and "--write" in sys.argv:
    GOLDEN_PATH.write_text(json.dumps({k: digest(kw) for k, kw in cases()}, indent=1, sort_keys=True) + "\n")
    print("wrote", GOLDEN_PATH)
