"""Frames of a website tour: the frame model (pure) and the browser workers (Chromium).

``FrameModel`` turns the tour, the timeline and the outline into ONE function of the video time: where the camera is,
what is lit, which card shows, how far the zoom has gone. Frames therefore do not depend on each other, so any worker
may draw any frame, and two languages share every frame outside the intro and end card.

Python 3.9 compatible.
"""
from __future__ import annotations

import asyncio
import io
import math
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import camera as cam
from . import effects as fx
from . import page as pg

try:
    from .. import deadline as dl
except ImportError:  # standalone use
    import deadline as dl  # type: ignore[no-redef]

LAUNCH_TIMEOUT_S = 60.0
CHUNK = 60                 # contiguous frames per work item (fewer big jumps for one browser page)
TOPPAD_CSS = 64.0          # free space kept at the top of a "fit" view
ZONE_PAD_CSS = 24.0
TOP_OFF_CSS = 150.0        # a "top" view puts the heading this far below the top


class RenderError(RuntimeError):
    pass


def target_y(entry: Dict[str, Any], view: str, vh: float, max_y: float) -> float:
    top, bottom = float(entry["top"]), float(entry["bottom"])
    zone = vh - ZONE_PAD_CSS
    if view == "fit":
        y = top - (TOPPAD_CSS + max(0.0, (zone - TOPPAD_CSS - (bottom - top)) / 2))
    else:
        y = top - TOP_OFF_CSS
    return max(0.0, min(max_y, y))


class FrameModel:
    """Everything the picture depends on, as functions of the video time ``T`` (seconds)."""

    def __init__(self, tour: Dict[str, Any], tl: Dict[str, Any], outline: Dict[str, Any], effects: Dict[str, bool]):
        self.tour, self.tl, self.outline, self.effects = tour, tl, outline, effects
        self.fps = int(tl["fps"])
        self.total = float(tl["total_s"])
        self.by_key = {e["key"]: e for e in outline["entries"]}
        self.max_y = max(0.0, float(outline["page_height"]) - float(outline["vh"]))
        self.vh = float(outline["vh"])
        self.late = 0
        self.camera = self._camera()
        self.zoom = fx.zoom_curve([s["start"] for s in tl["scenes"]] + [self.total], effects["zoom"])
        self.spots = self._spot_windows()
        s0 = tl["scenes"][0]
        two = s0["sentences"][1]["at_avg"] - 0.3 if len(s0["sentences"]) > 1 else 1.6
        self.intro = {"end": s0["start"] + s0["dur"], "line2_at": max(1.0, two)}
        last = tl["scenes"][-1]["sentences"][-1]["at_avg"]
        self.outro = {"start": max(self.intro["end"], last - 0.4)}

    # -- camera --------------------------------------------------------------------------------
    def _camera(self) -> cam.Pchip:
        stops: List[cam.Stop] = []
        for sc, ts in zip(self.tour["scenes"], self.tl["scenes"]):
            e = self.by_key[sc["target"]]
            y0 = target_y(e, "top" if sc["view"] == "pan" else sc["view"], self.vh, self.max_y)
            stops.append((ts["start"], y0, None))
            if sc["view"] == "pan":
                y1 = max(y0, min(self.max_y, float(e["bottom"]) - (self.vh - ZONE_PAD_CSS)))
                if y1 > y0 + 40:
                    stops.append((ts["start"] + 0.12 * ts["dur"], y1, 0.7 * ts["dur"]))
            for k, s in enumerate(sc["sentences"]):
                if s.get("focus") and s["focus"] != sc["target"]:
                    stops.append((ts["sentences"][k]["at_avg"], target_y(self.by_key[s["focus"]], "fit", self.vh, self.max_y), None))
        knots, info = cam.build_knots(stops, self.total)
        self.late = info["late"]
        self.knots = knots
        return cam.Pchip([k[0] for k in knots], [k[1] for k in knots])

    def _spot_windows(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if not self.effects["spot"]:
            return out
        for sc, ts in zip(self.tour["scenes"], self.tl["scenes"]):
            n = len(sc["sentences"])
            for k, s in enumerate(sc["sentences"]):
                if not s.get("focus"):
                    continue
                a = ts["sentences"][k]["at_avg"]
                b = (ts["sentences"][k + 1]["at_avg"] - 0.1) if k + 1 < n else (ts["start"] + ts["dur"] - 0.5)
                out.append({"key": s["focus"], "a": a, "b": max(a + 0.8, b)})
        return out

    def selectors_for_spots(self, selectors: Dict[str, str]) -> Dict[str, str]:
        return {w["key"]: selectors[w["key"]] for w in self.spots}

    def groups(self, selectors: Dict[str, str]) -> List[Dict[str, Any]]:
        """Animation clocks: a scene's target starts its cycle with the scene; an anchor starts it with its sentence."""
        g: List[Dict[str, Any]] = []
        for sc, ts in zip(self.tour["scenes"], self.tl["scenes"]):
            g.append({"sel": selectors[sc["target"]], "Tg": ts["start"], "shift": 0})
        for sc, ts in zip(self.tour["scenes"], self.tl["scenes"]):
            for a in sc["anchors"]:
                g.append({"sel": selectors[a["key"]], "Tg": ts["sentences"][a["sentence"]]["at_avg"] + a["offset"], "shift": 0})
        return g

    # -- frames --------------------------------------------------------------------------------
    def frame_count(self) -> int:
        return int(self.tl["frames"])

    def is_language_frame(self, T: float) -> bool:
        return T < self.intro["end"] or T >= self.outro["start"]

    def state(self, f: int) -> Dict[str, Any]:
        T = f / self.fps
        y = self.camera(T)
        return {"T": T, "y": y, "spot": fx.spot_level(T, self.spots) if self.spots else {"key": None, "k": 0.0},
                "card": fx.card_state(T, self.intro, self.outro), "zoom": self.zoom(T) if self.zoom else 1.0}

    def report(self) -> Dict[str, Any]:
        m = cam.metrics(self.camera, self.fps, self.total)
        m.update({"knots": len(self.knots), "late_moves": self.late, "v_max_px_s": cam.V_MAX})
        return m


def crop_frame(data: bytes, rest_dev: float, zoom: float, out_path: str, size: Tuple[int, int] = (1920, 1080), quality: int = 92) -> None:
    """Sub-pixel position and zoom in ONE resampling: ``rest_dev`` (device px, 0 <= r < 1) is the part of the scroll the
    browser could not do; the crop box is a float box so the picture moves by the exact fraction."""
    from PIL import Image  # noqa: PLC0415

    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    im = Image.open(io.BytesIO(data))
    im.load()
    W, H = im.size
    he = H - 2.0
    bw, bh = W * (he / H) / zoom, he / zoom
    top = max(0.0, min(1.999, rest_dev))
    cx, cy = W / 2.0, top + he / 2.0
    box = (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)
    out = im.convert("RGB").resize(size, resample, box=box)
    out.save(out_path, "JPEG", quality=quality)


async def draw_frames(source: pg.Source, model: FrameModel, plan: Sequence[Dict[str, Any]], *, workers: int,
                      on_progress: Optional[Callable[[int, int], None]] = None, page_height: float = 0.0) -> Dict[str, Any]:
    """Draw every ``{"f": frame, "path": str, "texts": [4 card lines] | None}`` of ``plan``. A frame with ``texts`` is one of the
    language frames (intro or end card); the others are shared by all languages. Returns ``{"layout_drift_px", "workers"}``."""
    try:
        from playwright.async_api import async_playwright  # noqa: PLC0415
    except ImportError as e:
        raise RenderError("playwright is not installed (pip install playwright && playwright install chromium)") from e
    marker = f"--vp-browser={uuid.uuid4().hex}"
    state: Dict[str, Any] = {"pw": None, "browser": None}
    plan = list(plan)
    chunks = [plan[i:i + CHUNK] for i in range(0, len(plan), CHUNK)]
    workers = max(1, min(int(workers), 8, len(chunks) or 1))
    kw = source.launch_kwargs
    kw["args"] = [*kw["args"], marker]

    async def launch() -> None:
        state["pw"] = await async_playwright().start()
        state["browser"] = await state["pw"].chromium.launch(headless=True, **kw)

    try:
        await dl.await_with_deadline(launch(), LAUNCH_TIMEOUT_S, what="chromium launch", on_expire=lambda *_: dl.kill_marked(marker))
    except Exception as e:  # noqa: BLE001
        await _close(state, marker)
        raise RenderError(f"chromium could not be launched: {type(e).__name__}: {e}") from None

    done = 0
    drift = 0.0
    lock = asyncio.Lock()
    queue: "asyncio.Queue[List[Dict[str, Any]]]" = asyncio.Queue()
    for c in chunks:
        queue.put_nowait(c)
    errors: List[str] = []
    W, H = pg.VIEWPORT

    async def worker() -> None:
        nonlocal done, drift
        ctx = await state["browser"].new_context(viewport={"width": W, "height": H}, device_scale_factor=pg.DSF)
        page = await ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))
        await source.install(ctx, page)
        await pg.prepare_page(page, source.url)
        accent = await page.evaluate(fx.ACCENT_JS)
        await page.evaluate(fx.SETUP_JS, fx.setup_config(model.outline, model.effects, model.groups(model.outline["selectors"]),
                                                          model.selectors_for_spots(model.outline["selectors"]), accent))
        h_now = float(await page.evaluate("() => document.documentElement.scrollHeight"))
        local_drift = abs(h_now - page_height) if page_height else 0.0
        cur_texts: Optional[List[str]] = None
        pending: List["asyncio.Future[Any]"] = []
        try:
            while True:
                try:
                    chunk = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                for item in chunk:
                    st = model.state(item["f"])
                    tx = item.get("texts")
                    if tx is not None and tx != cur_texts:
                        await page.evaluate("(t) => window.__vt.setTexts(t)", tx)
                        cur_texts = tx
                    scroll_css, _rest0 = cam.snap(st["y"], pg.DSF)
                    real = await page.evaluate("(s) => window.__vt.frame(s)", {"scroll": scroll_css, "T": st["T"], "spot": st["spot"], "card": st["card"]})
                    rest = st["y"] * pg.DSF - round(float(real) * pg.DSF)
                    shot = await page.screenshot(type="jpeg", quality=95)
                    pending.append(asyncio.ensure_future(asyncio.to_thread(crop_frame, shot, rest, st["zoom"], str(item["path"]))))
                    if len(pending) >= 6:
                        await asyncio.gather(*pending)
                        pending = []
                    if errors:
                        raise RenderError(f"page error while drawing: {errors[0]}")
                    async with lock:
                        done += 1
                        if on_progress and (done % 48 == 0 or done == len(plan)):
                            on_progress(done, len(plan))
                if pending:
                    await asyncio.gather(*pending)
                    pending = []
        finally:
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            async with lock:
                drift = max(drift, local_drift)
            await ctx.close()

    tasks = [asyncio.ensure_future(worker()) for _ in range(workers)]
    try:
        await asyncio.gather(*tasks)
    except BaseException:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        await _close(state, marker)
    return {"layout_drift_px": round(drift, 1), "workers": workers}


async def _close(state: Dict[str, Any], marker: str) -> None:
    try:
        if state.get("browser") is not None:
            await state["browser"].close()
    except Exception:  # noqa: BLE001
        pass
    try:
        if state.get("pw") is not None:
            await state["pw"].stop()
    except Exception:  # noqa: BLE001
        pass
    dl.kill_marked(marker)
