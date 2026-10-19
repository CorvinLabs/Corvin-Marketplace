"""Build the bundled console-screenshot catalogue for the `console_still` template (PLAN-0942 D10).

Reads screenshots from a Corvin-Website checkout, re-encodes them as JPEG (<= 250 kB) into
src/web/assets/console/ and writes catalog.json (key -> file, caption, source, date).
Rendering never reads the website: only the committed files here are used.

    python scripts/build_console_assets.py ../../../../../Corvin-Website
"""

import datetime
import io
import json
import sys
from pathlib import Path

from PIL import Image

MAX_BYTES = 250 * 1024
OUT = Path(__file__).resolve().parents[1] / "src" / "web" / "assets" / "console"

# The storyboard model never sees these images, so callouts and zoom may only target
# named hotspots measured here by hand (fractions of the image: x, y, description).
SPOTS = {
    "audit_compliance": {
        "guarantees": (0.58, 0.23, "the structural guarantees card"),
        "hash_chain_card": (0.40, 0.47, "the hash chain card: present, size, last event, last timestamp"),
        "event_list": (0.31, 0.68, "the audit chain event list header with category filters"),
    },
    "audit_events": {
        "event_type": (0.35, 0.18, "an event type name in a row"),
        "category_badge": (0.29, 0.18, "the category badge of a row (Other, Console, OS Turn)"),
        "short_hash": (0.84, 0.18, "the short record hash at the right of a row"),
    },
}

# key, source file (relative to the website root), caption shown to the storyboard model
SHOTS = [
    ("audit_compliance", "header/41-audit-compliance.png",
     "Audit & Compliance page: structural guarantees, the hash chain card (present, size, last event), the event list"),
    ("audit_events", "header/42-audit-events.png", "Audit chain event list: one row per record with type, short hash and time"),
    ("knowledge_hub", "header/40-knowledge-hub.png", "Knowledge hub page"),
    ("knowledge_query", "header/39-knowledge-query.png", "Knowledge query page"),
    ("compute_overview", "header/50-agentic-compute-overview.png", "Agentic Compute overview"),
    ("compute_run_graph", "header/46-agentic-compute-run-graph.png", "Agentic Compute run graph of one compute run"),
    ("workflow_branching", "header/51-workflow-incident-response-branching.png", "Workflow editor: a branching incident-response workflow"),
    ("chat", "handbook/screenshots/02-chat.png", "Console chat"),
    ("engines", "handbook/screenshots/06-engines.png", "AI engine settings"),
    ("personas", "handbook/screenshots/07-personas.png", "Personas page"),
    ("skills", "handbook/screenshots/12-skills.png", "Skills page"),
    ("auto_routing", "handbook/screenshots/23-auto-routing.png", "Auto-routing settings"),
]


def encode(src: Path) -> bytes:
    img = Image.open(src).convert("RGB")
    if img.width > 1600:
        img = img.resize((1600, round(img.height * 1600 / img.width)), Image.LANCZOS)
    for quality in (86, 80, 74, 68, 60):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        if buf.tell() <= MAX_BYTES:
            return buf.getvalue()
    raise SystemExit(f"{src.name}: cannot get under {MAX_BYTES} bytes")


def main(website: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = {}
    for key, rel, caption in SHOTS:
        src = website / rel
        data = encode(src)
        (OUT / f"{key}.jpg").write_bytes(data)
        w, h = Image.open(io.BytesIO(data)).size
        catalog[key] = {"file": f"{key}.jpg", "caption": caption, "source": f"Corvin-Website/{rel}",
                        "date": datetime.date.fromtimestamp(src.stat().st_mtime).isoformat(), "width": w, "height": h,
                        "spots": {name: {"x": x, "y": y, "description": desc}
                                  for name, (x, y, desc) in SPOTS.get(key, {}).items()}}
        print(f"{key:20s} {len(data) // 1024:4d} kB  {w}x{h}")
    (OUT / "catalog.json").write_text(json.dumps(catalog, indent=1) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
