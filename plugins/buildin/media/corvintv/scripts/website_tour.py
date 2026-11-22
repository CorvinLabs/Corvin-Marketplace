"""Make a narrated tour of a web page from the command line (CONCEPT-0139 section 10, ADR-2336).

    python scripts/website_tour.py --site ./my-site --tour tour.json --langs de en --out ./tour-out
    python scripts/website_tour.py --url https://example.com --task "Explain the pricing page" --langs en --out ./tour-out

It starts the SAME job entry the console uses (``start_video_production`` with ``mode: "website"``), with its own storage
folder, so a tour can be made without the console. ``--site`` copies the folder to ``<out>/websites/<name>`` (the only place a
site is served from). ``--url`` fetches through the capture proxy with the operator's own responsibility: no tenant egress rules,
only the named host loads. Narration uses the CorvinOS chain (openai -> edge -> piper). Result: ``<out>/videos/<job>/``
(``output*.mp4``, ``site/``, ``website-bundle.zip``).
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.util
import json
import shutil
import sys
import uuid
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
PKG = "corvin_video_producer_plugin"


def load():
    spec = importlib.util.spec_from_file_location(PKG, SRC / "__init__.py", submodule_search_locations=[str(SRC)])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = pkg
    spec.loader.exec_module(pkg)
    return importlib.import_module(PKG + ".skill"), importlib.import_module(PKG + ".models"), importlib.import_module(PKG + ".storage")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--site", help="folder with index.html (copied into <out>/websites/)")
    src.add_argument("--url", help="http(s) address of the page")
    ap.add_argument("--tour", help="tour.json (scenes and narration); without it the Claude Code engine writes the tour")
    ap.add_argument("--task", default="", help="what the tour should convey (used when no --tour is given)")
    ap.add_argument("--langs", nargs="+", default=["en"], choices=["en", "de"])
    ap.add_argument("--minutes", type=int, default=4)
    ap.add_argument("--fps", type=int, default=30, choices=[24, 30, 60])
    ap.add_argument("--no-effects", nargs="*", default=[], choices=["spot", "reveal", "zoom", "vignette"], help="switch effects off")
    ap.add_argument("--allow-host", action="append", default=[], metavar="HOST",
                    help="another host a --url page may load from (fonts, a CDN); repeat it; every other host stays blocked")
    ap.add_argument("--print-outline", action="store_true",
                    help="print the page's outline (the keys k1.. a tour may name) as JSON and exit; nothing is produced")
    ap.add_argument("--out", required=True, help="storage folder for the job")
    a = ap.parse_args(argv)

    skill, models, storage_mod = load()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    config = {"storage_base": str(out), "mode": "website", "website_langs": a.langs, "website_minutes": a.minutes, "website_fps": a.fps,
              "website_effects": {k: False for k in a.no_effects}, "max_duration_minutes": max(a.minutes, 5)}
    if a.site:
        site = Path(a.site).resolve()
        name = "".join(c if c.isalnum() or c in "._-" else "-" for c in site.name)[:60] or "site"
        dest = out / "websites" / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(site, dest, symlinks=False)
        config["website_site"] = name
        task = a.task or f"Tour of the site {name}"
    else:
        config["website_url"] = a.url
        task = (a.task or "Explain this page") + " " + a.url
    if a.allow_host:
        config["website_egress"] = {"forbidden": [], "allowed": sorted(set(a.allow_host)), "default": "deny"}
    if a.print_outline:
        page = importlib.import_module(PKG + ".website.page")
        source = page.open_source(config, None)
        try:
            outline = asyncio.run(page.outline_for(source))
        finally:
            source.close()
        print(json.dumps({"title": outline["title"], "page_height": outline["page_height"], "entries": [
            {k: e[k] for k in ("key", "tag", "heading", "top", "bottom", "figures", "animated")} | {"text": e["text"][:90]}
            for e in outline["entries"]]}, ensure_ascii=False, indent=1))
        return 0
    if a.tour:
        config["tour"] = json.loads(Path(a.tour).read_text(encoding="utf-8"))
    store = storage_mod.get_storage(str(out))
    job_id = "job_" + uuid.uuid4().hex[:8]
    store.save_job(models.VideoJob(id=job_id, task=task, status="pending"))
    result = asyncio.run(skill.start_video_production(job_id, task, config))
    print(json.dumps({"job_id": job_id, "dir": str(out / "videos" / job_id), "duration_seconds": result.get("duration_seconds")}))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
