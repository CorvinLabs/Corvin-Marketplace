"""The stage of a cinematic video: the canvas page and the frame capture.

The page is one self-contained HTML file: the engine scripts, the fonts (bundled, so a video looks the same on every
machine), the acts and the user's designs as data. Everything the model or the user supplied is JSON data inside a
``<script>`` block with ``<``, ``>``, ``&`` and the line separators escaped, so no byte of it can close the block or
become markup. Designs (Penpot exports) pass the plugin's own SVG sanitiser first and arrive as ``data:`` images.
The capture browser may load nothing but the page itself and ``data:`` URLs.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

try:
    from .. import deadline as dl
    from .. import penpot_import
except ImportError:  # standalone script use
    import deadline as dl
    import penpot_import

HERE = Path(__file__).resolve().parent
ENGINE = HERE / "engine"
FONTS = HERE.parent / "web" / "fonts"
FILES = ("core.js", "actors_world.js", "actors_concept_a.js", "actors_concept_b.js")
FONT_FACES = (  # family, file, style
    ("Newsreader", "Newsreader.woff2", "normal"),
    ("Newsreader", "Newsreader-Italic.woff2", "italic"),
    ("Instrument Sans", "InstrumentSans.woff2", "normal"),
)
FPS = 24
LAUNCH_TIMEOUT_S = 60.0
FRAME_TIMEOUT_S = 30.0
MAX_ART = 12
MAX_ART_BYTES = 8 * 1024 * 1024
_CHROMIUM_ARGS = ("--force-color-profile=srgb", "--font-render-hinting=none", "--disable-gpu-compositing")

BOOT = """
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
window.show = function (i, t, lang) { window.__lang = lang || 'de'; renderAct(ctx, ACTS[i], t); };
window.preload = async function () {
  for (const f of ['400 64px "Newsreader"', 'italic 400 64px "Newsreader"', '700 64px "Newsreader"', '400 64px "Instrument Sans"', '700 64px "Instrument Sans"']) await document.fonts.load(f);
  for (const [k, src] of Object.entries(ASSETS)) { const im = new Image(); im.src = src; await im.decode(); IMAGES[k] = im; }
};
"""


class CinematicError(RuntimeError):
    """A cinematic render step failed; the message says which and why."""


def _json_for_script(obj: Any) -> str:
    """JSON that is safe inside <script>: nothing in it can end the block or start a comment."""
    s = json.dumps(obj, ensure_ascii=False)
    return (s.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
             .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _font_css() -> str:
    rules = []
    for family, fname, style in FONT_FACES:
        p = FONTS / fname
        if not p.is_file():
            continue
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        rules.append(f"@font-face{{font-family:'{family}';font-style:{style};font-weight:200 900;"
                     f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "".join(rules)


def prepare_art(designs: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """``{name: Penpot SVG export (bytes or text)}`` -> ``{name: data: URL of the sanitised SVG}``.

    The upload is untrusted: ``penpot_import`` reduces it to its closed shape model and writes the SVG from typed
    fields only. A design it refuses is reported by name, never silently dropped."""
    out: Dict[str, str] = {}
    if not designs:
        return out
    if not isinstance(designs, dict) or len(designs) > MAX_ART:
        raise CinematicError(f"designs must be an object with at most {MAX_ART} entries")
    from .direction import NAME_RE  # noqa: PLC0415
    for name, raw in designs.items():
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            raise CinematicError(f"design name {str(name)[:40]!r} must be 1-40 letters, digits, '.', '_' or '-'")
        data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
        if not data or len(data) > MAX_ART_BYTES:
            raise CinematicError(f"design {name!r} is empty or larger than {MAX_ART_BYTES // 1048576} MiB")
        try:
            design = penpot_import.parse_design(data)
            svg = penpot_import.to_svg(design)
        except Exception as e:  # noqa: BLE001 — the closed importer's own errors carry the reason
            raise CinematicError(f"design {name!r} could not be imported: {e}") from None
        out[name] = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return out


def build_page(acts: List[Dict[str, Any]], assets: Optional[Dict[str, str]] = None) -> str:
    """Engine + fonts + acts + designs as one HTML string. Pure string work."""
    js = "\n".join((ENGINE / f).read_text(encoding="utf-8") for f in FILES)
    head = ("<!doctype html><html><head><meta charset=\"utf-8\"><style>" + _font_css()
            + "html,body{margin:0;background:#05070e}canvas{display:block}</style></head>"
            "<body><canvas id=\"cv\" width=\"1920\" height=\"1080\"></canvas><script>")
    data = ("const ACTS = " + _json_for_script(acts) + ";\nconst ASSETS = " + _json_for_script(assets or {}) + ";\n")
    return head + js + "\n" + data + BOOT + "</script></body></html>"


async def capture_frames(page_path: Path, plan: Sequence[Dict[str, Any]], *, workers: int = 4,
                         fmt: str = "jpg", on_progress: Optional[Callable[[int, int], None]] = None) -> None:
    """Render every ``{"s": act, "t": seconds, "l": lang, "f": path}`` of ``plan`` to its file.

    Frames are a pure function of (act, time, language), so any worker may take any entry. The browser is started with
    a unique marker so a hung one can be found and ended with its driver; ``on_progress`` may raise (cancel/budget)."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise CinematicError("playwright is not installed (pip install playwright && playwright install chromium)") from e
    marker = f"--vp-browser={uuid.uuid4().hex}"
    state: Dict[str, Any] = {"pw": None, "browser": None}
    plan = list(plan)
    workers = max(1, min(int(workers), 8, len(plan) or 1))

    def hard_kill(_why: str = "hung") -> None:
        dl.kill_marked(marker)

    async def launch() -> None:
        state["pw"] = await async_playwright().start()
        state["browser"] = await state["pw"].chromium.launch(headless=True, args=[*_CHROMIUM_ARGS, marker])

    try:
        await dl.await_with_deadline(launch(), LAUNCH_TIMEOUT_S, what="chromium launch", on_expire=hard_kill)
    except Exception as e:  # noqa: BLE001
        await _close(state, marker)
        raise CinematicError(f"chromium could not be launched: {type(e).__name__}: {e}") from None

    done = 0
    lock = asyncio.Lock()
    errors: List[str] = []

    async def worker(k: int) -> None:
        nonlocal done
        ctx = await state["browser"].new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1,
                                                 java_script_enabled=True)

        async def gate(route):  # the page needs nothing from the network: allow only itself and data: URLs
            u = route.request.url
            await (route.continue_() if u.startswith(("file:", "data:", "about:", "blob:")) else route.abort())

        await ctx.route("**/*", gate)
        page = await ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)[:300]))
        await page.goto(page_path.resolve().as_uri())
        await page.evaluate("window.preload()")
        for e in plan[k::workers]:
            await page.evaluate("([s, t, l]) => window.show(s, t, l)", [e["s"], e["t"], e.get("l", "en")])
            f = str(e["f"])
            if f.endswith(".png"):
                await page.locator("#cv").screenshot(path=f, type="png")
            else:
                await page.locator("#cv").screenshot(path=f, type="jpeg", quality=92)
            if errors:
                raise CinematicError(f"page error while drawing: {errors[0]}")
            async with lock:
                done += 1
                if on_progress and (done % 48 == 0 or done == len(plan)):
                    on_progress(done, len(plan))
        await ctx.close()

    try:
        budget = dl.current_budget()
        total_s = (budget.remaining() if budget else 3600.0)
        await dl.await_with_deadline(asyncio.gather(*(worker(k) for k in range(workers))), max(10.0, total_s),
                                     what="frame capture", on_expire=hard_kill)
    finally:
        await _close(state, marker)
    if errors:
        raise CinematicError(f"page error while drawing: {errors[0]}")
    missing = [e["f"] for e in plan if not Path(e["f"]).is_file()]
    if missing:
        raise CinematicError(f"{len(missing)} of {len(plan)} frames were not written")


async def _close(state: Dict[str, Any], marker: str) -> None:
    try:
        if state.get("browser"):
            await asyncio.wait_for(state["browser"].close(), 10)
        if state.get("pw"):
            await asyncio.wait_for(state["pw"].stop(), 10)
    except Exception:  # noqa: BLE001 — a browser that will not close is ended by its marker below
        pass
    if dl.find_processes(marker):
        dl.kill_marked(marker)
