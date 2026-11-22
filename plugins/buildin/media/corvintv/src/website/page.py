"""The source of a tour: where the page comes from, how the browser may reach it, and the outline of the page.

Two sources (CONCEPT-0139 section 1):

* ``site``: a folder under ``<storage_base>/websites/<name>/``. The plugin process serves it itself on loopback
  (port 0, GET/HEAD only, files below the folder only, no listing, no symlink out of it) and the browser may reach
  NOTHING else: every other request is aborted and counted.
* ``url``: an http(s) address the HOST already let through (tenant switch, egress policy, L35 gate). The browser
  loads it ONLY through ``capture.CaptureProxy`` (name resolved once, every address checked, connect pinned), with the
  same hardening flags as a website capture. No loopback or private address, no second fetch path.

Python 3.9 compatible.
"""
from __future__ import annotations

import asyncio
import functools
import mimetypes
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

try:
    from .. import capture as cap
except ImportError:  # standalone use
    import capture as cap  # type: ignore[no-redef]

VIEWPORT = (1422, 800)
DSF = 1.35                      # 1422 x 800 css px at 1.35 = 1920 x 1080 device px
SITE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
MAX_SITE_BYTES = 200 * 1024 * 1024
MAX_SITE_FILES = 20000
MAX_OUTLINE = 40
MAX_OUTLINE_TEXT = 12000
NAV_TIMEOUT_MS = 45000

# Chrome's own background traffic off (the capture module's condition 1), same list as ``capture.chrome_command``.
HARDENING_ARGS = (
    "--disable-background-networking", "--disable-component-update", "--disable-sync", "--disable-domain-reliability",
    "--disable-client-side-phishing-detection", "--no-pings", "--disable-default-apps", "--disable-extensions",
    "--metrics-recording-only", "--mute-audio", "--hide-scrollbars",
    "--disable-features=DnsOverHttps,NetworkPrediction,Translate,OptimizationHints,MediaRouter,"
    "AutofillServerCommunication,CertificateTransparencyComponentUpdater,InterestFeedContentSuggestions",
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1", "--disable-quic",
)
# Deterministic frames: no threaded compositor animation, draw every stage before the screenshot.
DETERMINISM_ARGS = ("--disable-threaded-animation", "--run-all-compositor-stages-before-draw", "--disable-checker-imaging")

# The page's own timers are frozen (a slideshow or a counter must not run on the real clock); its CSS animations are
# seeked frame by frame. ``[data-reveal]``-style markers are shown by the effects layer, not by an observer.
FREEZE_JS = "window.setInterval = function () { return 0; };"
PREP_CSS = ("html{scroll-behavior:auto!important}"
            "[data-reveal],[data-aos],.reveal{transition:none!important}")


class SiteError(RuntimeError):
    """The source cannot be used; the message is safe to show to the operator."""


def site_dir(storage_base: str, name: str) -> Path:
    """``<storage_base>/websites/<name>`` after the checks that keep a tour inside the tenant's own folder."""
    if not isinstance(name, str) or not SITE_NAME_RE.match(name):
        raise SiteError("the site name may use letters, digits, dot, underscore and hyphen (at most 64)")
    root = Path(storage_base) / "websites"
    path = root / name
    if path.is_symlink() or not path.is_dir():
        raise SiteError(f"no site folder named {name!r} under the workspace's websites folder")
    real_root, real = root.resolve(), path.resolve()
    if os.path.commonpath([str(real_root), str(real)]) != str(real_root):
        raise SiteError("the site folder is not inside the workspace's websites folder")
    return real


def check_site_tree(root: Path) -> Dict[str, int]:
    """Refuse a folder with a symlink, a file outside it, too many files or too many bytes; it must hold index.html."""
    root = root.resolve()
    files = size = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for n in list(dirnames) + list(filenames):
            p = Path(dirpath) / n
            if p.is_symlink():
                raise SiteError("the site folder contains a symbolic link, which is not allowed")
        for n in filenames:
            files += 1
            size += (Path(dirpath) / n).stat().st_size
        if files > MAX_SITE_FILES or size > MAX_SITE_BYTES:
            raise SiteError("the site folder is too large (at most 20 000 files and 200 MB)")
    if not (root / "index.html").is_file():
        raise SiteError("the site folder has no index.html")
    return {"files": files, "bytes": size}


class _Handler(BaseHTTPRequestHandler):
    root: Path = Path(".")
    server_version = "CorvinTV-site"

    def log_message(self, *a: Any) -> None:  # silent
        return

    def _target(self) -> Optional[Path]:
        raw = unquote(urlsplit(self.path).path)
        if "\x00" in raw or "\\" in raw:
            return None
        rel = raw.lstrip("/") or "index.html"
        p = (self.root / rel).resolve()
        if os.path.commonpath([str(self.root), str(p)]) != str(self.root):
            return None
        if p.is_dir():
            p = p / "index.html"
        return p if p.is_file() and not p.is_symlink() else None

    def _range(self, size: int) -> Optional[Tuple[int, int]]:
        """A single ``bytes=a-b`` range, or None (the whole file). A bad range answers 416 in ``_send``."""
        h = self.headers.get("Range")
        if not h:
            return None
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", h.strip())
        if not m or (not m.group(1) and not m.group(2)):
            return (-1, -1)
        a, b = m.group(1), m.group(2)
        if not a:  # the last N bytes
            n = int(b)
            return (max(0, size - n), size - 1) if n > 0 else (-1, -1)
        start = int(a)
        end = min(int(b), size - 1) if b else size - 1
        return (start, end) if start <= end and start < size else (-1, -1)

    def _send(self, head_only: bool) -> None:
        p = self._target()
        if p is None:
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        size = p.stat().st_size
        rng = self._range(size)
        if rng == (-1, -1):
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        start, end = rng if rng else (0, size - 1)
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(end - start + 1 if size else 0))
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head_only and size:
            with open(p, "rb") as fh:
                fh.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = fh.read(min(65536, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)

    def do_GET(self) -> None:  # noqa: N802
        self._send(False)

    def do_HEAD(self) -> None:  # noqa: N802
        self._send(True)

    def do_POST(self) -> None:  # noqa: N802
        self.send_error(405)

    do_PUT = do_DELETE = do_PATCH = do_POST


class LocalSite:
    """Serves one folder on 127.0.0.1 (port 0) in a thread, for the length of a job."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.server: Optional[ThreadingHTTPServer] = None
        self.port = 0

    def start(self) -> str:
        handler = type("SiteHandler", (_Handler,), {"root": self.root})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True, name="vp-website-site").start()
        return f"http://127.0.0.1:{self.port}/index.html"

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


class Source:
    """Where the page comes from and what the browser is allowed to reach. Close it when the job ends."""

    def __init__(self, kind: str, url: str, origin: str, *, site: Optional[LocalSite] = None,
                 proxy: Optional["cap.CaptureProxy"] = None):
        self.kind, self.url, self.origin, self.site, self.proxy = kind, url, origin, site, proxy
        self.blocked = 0
        self.requests = 0
        self._lock = threading.Lock()

    @property
    def launch_kwargs(self) -> Dict[str, Any]:
        kw: Dict[str, Any] = {"args": [*DETERMINISM_ARGS, *HARDENING_ARGS]}
        if self.proxy is not None:
            kw["args"] += [*cap.WEBRTC_FLAGS, "--proxy-bypass-list=<-loopback>"]
            kw["proxy"] = {"server": f"http://127.0.0.1:{self.proxy.port}"}
        return kw

    async def install(self, context: Any, page: Any) -> None:
        """Gate every request of ``context``; a ``url`` source announces the page's own requests to the proxy."""
        async def gate(route: Any) -> None:
            u = route.request.url
            with self._lock:
                self.requests += 1
            if u.startswith(("data:", "blob:", "about:")):
                await route.continue_()
                return
            if self.kind == "site":
                if u.startswith(self.origin):
                    await route.continue_()
                else:
                    with self._lock:
                        self.blocked += 1
                    await route.abort()
                return
            parts = urlsplit(u)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                with self._lock:
                    self.blocked += 1
                await route.abort()
                return
            port = parts.port or (443 if parts.scheme == "https" else 80)
            self.proxy.announce(parts.hostname, port)  # type: ignore[union-attr]
            await route.continue_()

        await context.route("**/*", gate)

    def close(self) -> None:
        if self.site is not None:
            self.site.stop()
        if self.proxy is not None:
            self.proxy.stop()

    def summary(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"kind": self.kind, "requests": self.requests, "blocked_requests": self.blocked}
        if self.proxy is not None:
            out["proxy_hosts"] = self.proxy.hosts()
        return out


def open_source(config: Dict[str, Any], task_url: Optional[str]) -> Source:
    """``config["website_site"]`` (a folder name) wins over an address. Raises ``SiteError`` for anything unusable."""
    name = config.get("website_site")
    if name:
        root = site_dir(config["storage_base"], str(name))
        check_site_tree(root)
        site = LocalSite(root)
        url = site.start()
        return Source("site", url, url.rsplit("/", 1)[0] + "/", site=site)
    raw = config.get("website_url") or task_url
    if not raw:
        raise SiteError("the brief needs the address of the page (https://...) or the name of a site folder")
    try:
        target = cap.check_url(raw)
    except cap.CaptureRefused:
        raise SiteError("the address must be a plain http:// or https:// address") from None
    refusal = cap.precheck_host(target["host"], config.get("website_console_names") or ())
    if refusal:
        raise SiteError("this address cannot be used for a tour")
    proxy = cap.CaptureProxy([target["host"]], [target["port"]], config.get("website_console_names") or (),
                             egress=config.get("website_egress"))
    proxy.start()
    return Source("url", target["url"], f"{target['scheme']}://{target['host']}", proxy=proxy)


# ── the page ────────────────────────────────────────────────────────────────────────────────────

OUTLINE_JS = r"""
() => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.height > 40 && r.width > 100 && cs.display !== 'none' && cs.visibility !== 'hidden'; };
  const cssPath = (el) => {
    if (el.id && /^[A-Za-z][\w-]*$/.test(el.id) && document.querySelectorAll('#' + el.id).length === 1) return '#' + el.id;
    const parts = []; let n = el;
    while (n && n.nodeType === 1 && n !== document.body) {
      let i = 1, s = n; while ((s = s.previousElementSibling)) if (s.tagName === n.tagName) i++;
      parts.unshift(n.tagName.toLowerCase() + ':nth-of-type(' + i + ')'); n = n.parentElement;
    }
    return 'body > ' + parts.join(' > ');
  };
  const heading = (el) => { if (/^H[1-3]$/.test(el.tagName)) return el; if (el.tagName === 'FIGURE') return null; return el.querySelector('h1,h2,h3'); };
  const figLabel = (el) => (el.getAttribute('aria-label') || (el.querySelector('figcaption') || {}).innerText || '').replace(/\s+/g, ' ').trim();
  const cands = [...document.querySelectorAll('header, section, article, footer, figure, h1, h2, h3')].filter(vis);
  const secs = new Set(cands.filter(e => /^(HEADER|SECTION|ARTICLE|FOOTER)$/.test(e.tagName)));
  const out = []; const seen = new Set();
  for (const el of cands) {
    if (/^H3$/.test(el.tagName) && el.closest('section,article,header,footer')) continue;
    if (/^H[12]$/.test(el.tagName) && el.closest('section,article,header,footer') && secs.has(el.closest('section,article,header,footer'))
        && heading(el.closest('section,article,header,footer')) === el) continue;
    const h = heading(el); const r = el.getBoundingClientRect();
    const sel = cssPath(el); if (seen.has(sel)) continue; seen.add(sel);
    const fl = el.tagName === 'FIGURE' ? figLabel(el) : '';
    out.push({ selector: sel, tag: el.tagName.toLowerCase(), heading: (fl || ((h && h.innerText) || '')).replace(/\s+/g, ' ').trim().slice(0, 120),
      text: (fl + ' ' + (el.innerText || '')).replace(/\s+/g, ' ').trim().slice(0, 300),
      top: r.top + scrollY, bottom: r.bottom + scrollY,
      figures: el.querySelectorAll('figure,svg,canvas,video,picture').length,
      animated: (el.getAnimations ? el.getAnimations({ subtree: true }).length : 0) });
  }
  out.sort((a, b) => a.top - b.top);
  const cs = getComputedStyle(document.body);
  return { entries: out.slice(0, %(max)d), pageHeight: document.documentElement.scrollHeight, vh: innerHeight, dsf: devicePixelRatio,
           title: (document.title || '').slice(0, 160), lang: document.documentElement.lang || '',
           bg: cs.backgroundColor, fg: cs.color, font: cs.fontFamily };
}
""" % {"max": MAX_OUTLINE}

SCROLL_THROUGH_JS = """
async () => { for (let y = 0; y < document.documentElement.scrollHeight; y += 500) { window.scrollTo(0, y);
  await new Promise((r) => setTimeout(r, 70)); } window.scrollTo(0, 0); }
"""


async def prepare_page(page: Any, url: str) -> None:
    """Load the page the same way for the outline run and for every frame worker (so layout is identical)."""
    await page.add_init_script(FREEZE_JS)
    await page.goto(url, wait_until="load", timeout=NAV_TIMEOUT_MS)
    await page.wait_for_timeout(1500)
    await page.evaluate(SCROLL_THROUGH_JS)
    await page.wait_for_timeout(600)
    await page.add_style_tag(content=PREP_CSS)


async def read_outline(page: Any) -> Dict[str, Any]:
    """The outline with stable keys ``k1``.. in page order. ``selectors`` stays inside the plugin."""
    raw = await page.evaluate(OUTLINE_JS)
    entries: List[Dict[str, Any]] = []
    selectors: Dict[str, str] = {}
    budget = MAX_OUTLINE_TEXT
    for i, e in enumerate(raw["entries"], 1):
        key = f"k{i}"
        text = str(e.get("text", ""))[: max(0, min(300, budget))]
        budget -= len(text)
        selectors[key] = e["selector"]
        entries.append({"key": key, "tag": e["tag"], "heading": e.get("heading", ""), "text": text,
                        "top": float(e["top"]), "bottom": float(e["bottom"]),
                        "figures": int(e.get("figures", 0)), "animated": int(e.get("animated", 0))})
    if not entries:
        raise SiteError("the page has no sections or headings to tour")
    return {"entries": entries, "selectors": selectors, "page_height": float(raw["pageHeight"]), "vh": float(raw["vh"]),
            "dsf": float(raw["dsf"]), "title": raw.get("title", ""), "lang": raw.get("lang", ""),
            "bg": raw.get("bg", "rgb(11,14,19)"), "fg": raw.get("fg", "rgb(233,238,244)"), "font": raw.get("font", "")}


async def outline_for(source: Source, *, launch_timeout_s: float = 60.0) -> Dict[str, Any]:
    """Open the source once in its own browser and read the outline (the frame workers prepare the page the same way)."""
    try:
        from playwright.async_api import async_playwright  # noqa: PLC0415
    except ImportError as e:
        raise SiteError("playwright is not installed (pip install playwright && playwright install chromium)") from e
    try:
        from .. import deadline as dl  # noqa: PLC0415
    except ImportError:
        import deadline as dl  # type: ignore[no-redef]  # noqa: PLC0415
    import uuid  # noqa: PLC0415

    marker = f"--vp-browser={uuid.uuid4().hex}"
    kw = source.launch_kwargs
    kw["args"] = [*kw["args"], marker]
    pw = browser = None
    try:
        async def launch() -> None:
            nonlocal pw, browser
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(headless=True, **kw)
        await dl.await_with_deadline(launch(), launch_timeout_s, what="chromium launch", on_expire=lambda *_: dl.kill_marked(marker))
        ctx = await browser.new_context(viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]}, device_scale_factor=DSF)
        page = await ctx.new_page()
        await source.install(ctx, page)
        try:
            await prepare_page(page, source.url)
        except Exception as e:  # noqa: BLE001 - name the reason without the page's text
            raise SiteError(f"the page could not be loaded ({type(e).__name__})") from None
        return await read_outline(page)
    finally:
        try:
            if browser is not None:
                await browser.close()
        finally:
            if pw is not None:
                await pw.stop()
            dl.kill_marked(marker)
