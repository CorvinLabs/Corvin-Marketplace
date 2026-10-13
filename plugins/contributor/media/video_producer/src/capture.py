"""Website capture as an asset (ADR-2249 D4, T-0113): policy, Corvin-owned forward proxy, worker.

Moved from the S3 spike (``spike_capture_policy/``, T-0112, measured GO 2026-10-13: 146 hostile cases,
0 reached destinations, byte- and time-identical refusals, killpg at the deadline). The spike folder
stays as the measurement record; THIS module is the product code and the hostile corpus runs against it
(``tests/test_capture_policy.py``).

Shape:

* **The host** (the console route) calls ``capture_url``. It checks the URL (``check_url``) and refuses
  IP literals / refused names without any DNS query (``precheck_host``), then runs ONE worker process
  through ``deadline.run_process``: own session, the whole process group SIGTERM/SIGKILLed at the
  deadline. At most ``MAX_CONCURRENT`` captures run host-wide.
* **The worker** (``python -I capture.py --worker``) starts a ``CaptureProxy`` that allows ONLY the
  host the user named (and only its ports), then runs Chrome with every request pinned to that proxy.
  Chrome stays in the worker's process group (``deadline.mark_job_process``), so the host's group kill
  reaches the browser too.
* **The proxy** resolves a name once, validates EVERY resolved address (one bad record refuses the
  name), and connects to the pinned validated address - no rebinding window. Allow-by-global: the
  address must be globally routable after every transition form (IPv4-mapped, v4-compatible, NAT64,
  6to4, Teredo) is unwrapped, must not be multicast and must not be one of this host's own addresses.
  Every failure - refused name, refused address, a host that was not named, empty DNS, connect refused,
  connect timeout - answers the same bytes at the same instant ``t0 + FLOOR_S``.

The three conditions of the spike, all enforced here:
  1. Chrome's background traffic (google.com, safe browsing, ...) never leaves: the proxy allows only
     the named host; the background flags are set as well.
  2. ``--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1``: Chrome cannot resolve any name
     itself; only the proxy resolves.
  3. Every browser request goes through the one proxy (``--proxy-bypass-list=<-loopback>``, QUIC off)
     and WebRTC may not use UDP that is not proxied (``WEBRTC_FLAGS``; the proxy carries no UDP).

Captured pixels are untrusted content: this module returns PNG bytes and nothing read from the page.
Stdlib only (the worker runs isolated with ``-I``).
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlsplit

if __name__ == "__main__" and __package__ in (None, ""):  # the worker: python -I capture.py --worker
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from . import deadline as _dl
except ImportError:  # worker script mode (no package context)
    import deadline as _dl  # type: ignore[no-redef]

# ── budgets ──────────────────────────────────────────────────────────────────────────────────
FLOOR_S = 2.0                 # every proxy failure answers at t0 + FLOOR_S
RESOLVE_TIMEOUT_S = 0.4
CONNECT_TIMEOUT_S = 1.4
NAVIGATION_DEADLINE_S = 15.0  # the browser inside the worker
CAPTURE_DEADLINE_S = 25.0     # the whole worker (proxy start + browser + screenshot)
MAX_CONCURRENT = 2            # host-wide
MAX_PNG_BYTES = 16 * 1024 * 1024
MAX_URL_CHARS = 2048
VIEWPORTS: Dict[str, Tuple[int, int, int]] = {  # name -> (width, height, device scale factor)
    "desktop": (1920, 1080, 1),
    "mobile": (412, 915, 2),
}

FAIL = (b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\nContent-Length: 32\r\n"
        b"Connection: close\r\n\r\nthis address cannot be captured\n")

# ── policy (from spike_capture_policy/policy.py) ────────────────────────────────────────────
NAT64 = [ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48")]
SIX_TO_FOUR = ipaddress.ip_network("2002::/16")
TEREDO = ipaddress.ip_network("2001::/32")
V4_COMPAT = ipaddress.ip_network("::/96")
REFUSED_NAMES = {"localhost", "metadata.google.internal", "metadata", "instance-data"}


class CaptureRefused(ValueError):
    """The URL is not a plain http(s) address; ``code`` is a closed token safe to audit."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def own_addresses() -> Set[Any]:
    """Every address bound to an interface of this host (Linux ``ip -j addr``), plus what this host's
    own names resolve to and the loopback addresses - so the host can never be its own target."""
    out: Set[Any] = {ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1")}
    if shutil.which("ip"):
        try:
            r = _dl.run_process(["ip", "-j", "addr"], deadline_s=5, text=True, what="ip addr")
            for itf in json.loads(r.stdout or "[]"):
                for a in itf.get("addr_info", []):
                    out.add(ipaddress.ip_address(a["local"].split("%")[0]))
        except Exception:  # noqa: BLE001 - best effort; the global check still applies
            pass
    for name in {socket.gethostname(), socket.getfqdn()}:
        try:
            for info in socket.getaddrinfo(name, None):
                out.add(ipaddress.ip_address(info[4][0].split("%")[0]))
        except (OSError, ValueError):
            pass
    return out


def parse_ip_literal(host: str) -> Optional[Any]:
    """IP literal in any textual encoding (127.1, hex, octal, decimal, bracketed v6), else None.
    Raises ``ValueError`` for a zone id."""
    h = host.strip().rstrip(".")
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    if "%" in h:
        raise ValueError("zone id")
    try:
        return ipaddress.ip_address(h)
    except ValueError:
        pass
    try:  # inet_aton accepts every legacy IPv4 form a URL parser might pass through
        if h and all(c in "0123456789abcdefxABCDEFX." for c in h):
            return ipaddress.ip_address(socket.inet_aton(h))
    except OSError:
        pass
    return None


def _embedded_v4(ip) -> Iterable[Any]:
    if ip.ipv4_mapped:
        yield ip.ipv4_mapped
    if ip in V4_COMPAT:
        yield ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    if any(ip in n for n in NAT64):
        yield ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    if ip.sixtofour:
        yield ip.sixtofour
    if ip.teredo:
        yield ip.teredo[1]


def address_verdict(ip, own: Set[Any]) -> Optional[str]:
    """None = connectable, else the refusal reason. ``is_global`` alone is NOT enough (measured on
    Python 3.11: True for 224.0.0.1, ff05::1:3, 64:ff9b::7f00:1, ::127.0.0.1 and own global v6)."""
    if ip in own:
        return "own_interface"
    if ip.version == 6:
        for v4 in _embedded_v4(ip):
            r = address_verdict(v4, own)
            if r:
                return "embedded_v4:" + r
        if any(ip in n for n in NAT64) or ip in SIX_TO_FOUR or ip in TEREDO or ip in V4_COMPAT:
            return "transition_form"  # v1: no transition-mechanism destinations at all
    if ip.is_multicast:
        return "multicast"
    if not ip.is_global:
        return "not_global"
    return None


def name_verdict(host: str, console_names: Iterable[str]) -> Optional[str]:
    h = host.lower().rstrip(".")
    if h in REFUSED_NAMES or h.endswith(".localhost") or h in {n.lower().rstrip(".") for n in console_names}:
        return "refused_name"
    return None


def precheck_host(host: str, console_names: Iterable[str] = ()) -> Optional[str]:
    """The host-side check before any worker or DNS query: a refused name, a zone id, or an IP literal
    the address policy refuses. None = hand it to the proxy (which decides at connect time)."""
    r = name_verdict(host, console_names)
    if r:
        return r
    try:
        lit = parse_ip_literal(host)
    except ValueError:
        return "bad_host"
    if lit is not None:
        return address_verdict(lit, own_addresses())
    return None


def _canonical_host(host: str) -> str:
    return host.strip().strip("[]").lower().rstrip(".")


def check_url(url: Any) -> Dict[str, Any]:
    """A plain http(s) address the user typed -> ``{url, scheme, host, port}`` (normalised, no
    fragment). Raises ``CaptureRefused`` for anything else: another scheme, userinfo, a backslash,
    whitespace or control characters, no host, a bad port, a host that is not valid IDNA."""
    if not isinstance(url, str) or not url or len(url) > MAX_URL_CHARS:
        raise CaptureRefused("invalid_url")
    if any(c.isspace() or ord(c) < 0x20 or c == "\\" for c in url):
        raise CaptureRefused("invalid_url")
    try:
        parts = urlsplit(url)
        port = parts.port
        host = parts.hostname
    except ValueError:
        raise CaptureRefused("invalid_url") from None
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not host or "@" in parts.netloc:
        raise CaptureRefused("invalid_url")
    if port is not None and not 1 <= port <= 65535:
        raise CaptureRefused("invalid_url")
    if ":" in host:  # IPv6 literal
        shown = f"[{host}]"
    else:
        try:
            host = host.encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise CaptureRefused("invalid_url") from None
        shown = host
    default = 443 if scheme == "https" else 80
    port = port or default
    netloc = shown if port == default else f"{shown}:{port}"
    path = parts.path or "/"
    norm = f"{scheme}://{netloc}{path}" + (f"?{parts.query}" if parts.query else "")
    return {"url": norm, "scheme": scheme, "host": host, "port": port}


# ── proxy (from spike_capture_policy/proxy.py) ──────────────────────────────────────────────

Resolver = Callable[[str], List[str]]


class CaptureProxy:
    """Forward proxy for ONE capture. ``named_hosts``/``ports``: the only destinations allowed at all
    (condition 1); ``resolver``: name -> list of address strings (default: the system resolver)."""

    def __init__(self, named_hosts: Iterable[str], ports: Iterable[int] = (80, 443),
                 console_names: Iterable[str] = (), resolver: Optional[Resolver] = None):
        self.named = {_canonical_host(h) for h in named_hosts}
        self.ports = {int(p) for p in ports}
        self.console_names = set(console_names)
        self.resolver = resolver
        self.own = own_addresses()
        self.log: List[Dict[str, Any]] = []
        self.outbound: List[Tuple[str, int]] = []   # every TCP connect the proxy actually made
        self.port = 0
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server = None

    # ---- decision -------------------------------------------------------------------------
    def _is_named(self, host: str, port: int) -> bool:
        return _canonical_host(host) in self.named and port in self.ports

    def _address_ok(self, ip) -> Optional[str]:
        return address_verdict(ip, self.own)

    async def _resolve(self, host: str) -> List[Any]:
        loop = asyncio.get_running_loop()
        if self.resolver is not None:
            got = await asyncio.wait_for(loop.run_in_executor(None, self.resolver, host), RESOLVE_TIMEOUT_S)
            return [ipaddress.ip_address(a.split("%")[0]) for a in got]
        infos = await asyncio.wait_for(loop.getaddrinfo(host, None, type=socket.SOCK_STREAM), RESOLVE_TIMEOUT_S)
        return [ipaddress.ip_address(i[4][0].split("%")[0]) for i in infos]

    async def decide(self, host: str, port: int) -> Tuple[Optional[Any], str]:
        if not self._is_named(host, port):
            return None, "not_named"
        r = name_verdict(host, self.console_names)
        if r:
            return None, r
        try:
            lit = parse_ip_literal(host)
        except ValueError as e:
            return None, "bad_host:" + str(e)
        try:
            addrs = [lit] if lit else await self._resolve(host.rstrip("."))
        except Exception as e:  # noqa: BLE001
            return None, "dns_fail:" + type(e).__name__
        if not addrs:
            return None, "dns_empty"
        for a in addrs:
            r = self._address_ok(a)
            if r:
                return None, f"{r}:{a}"
        return addrs[0], "ok"  # pinned: the first validated address, never re-resolved

    # ---- wire -----------------------------------------------------------------------------
    async def _pipe(self, r, w):
        try:
            while True:
                b = await r.read(65536)
                if not b:
                    break
                w.write(b)
                await w.drain()
        except Exception:  # noqa: BLE001
            pass
        finally:
            try:
                w.close()
            except Exception:  # noqa: BLE001
                pass

    async def _fail(self, w, t0):
        await asyncio.sleep(max(0.0, t0 + FLOOR_S - time.monotonic()))
        try:
            w.write(FAIL)
            await w.drain()
            w.close()
        except Exception:  # noqa: BLE001
            pass

    async def handle(self, cr, cw):
        t0 = time.monotonic()
        rec: Dict[str, Any] = {"t": time.time()}
        try:
            head = await asyncio.wait_for(cr.readuntil(b"\r\n\r\n"), 5)
        except Exception:  # noqa: BLE001
            cw.close()
            return
        line = head.split(b"\r\n", 1)[0].decode("latin-1")
        try:
            method, target, ver = line.split(" ")
            if method == "CONNECT":
                host, _, port_s = target.rpartition(":")
                port, rest = int(port_s), b""
            else:
                if not target.startswith("http://"):
                    raise ValueError("not absolute-form http")
                hostport, _, path = target[7:].partition("/")
                hostport = hostport.rpartition("@")[2]
                if hostport.startswith("["):
                    host, _, p = hostport[1:].partition("]")
                    port = int(p[1:]) if p.startswith(":") else 80
                else:
                    host, _, p = hostport.partition(":")
                    port = int(p) if p else 80
                rest = f"{method} /{path} {ver}".encode()
            host = host.strip("[]")
        except Exception as e:  # noqa: BLE001
            rec.update(verdict="refused", reason="bad_request:" + str(e)[:60])
            self._record(rec)
            return await self._fail(cw, t0)
        ip, reason = await self.decide(host, port)
        rec.update(host=_canonical_host(host), port=port, reason=reason)
        if ip is None:
            rec["verdict"] = "refused"
            self._record(rec)
            return await self._fail(cw, t0)
        try:
            with self._lock:
                self.outbound.append((str(ip), port))
            ur, uw = await asyncio.wait_for(asyncio.open_connection(str(ip), port), CONNECT_TIMEOUT_S)
        except Exception as e:  # noqa: BLE001
            rec.update(verdict="unreachable", pinned=str(ip), reason="connect:" + type(e).__name__)
            self._record(rec)
            return await self._fail(cw, t0)
        rec.update(verdict="connected", pinned=str(ip))
        self._record(rec)
        if method == "CONNECT":
            cw.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        else:
            hdrs = head.split(b"\r\n", 1)[1]
            uw.write(rest + b"\r\n" + hdrs)
        await asyncio.gather(self._pipe(cr, uw), self._pipe(ur, cw))

    def _record(self, rec):
        with self._lock:
            self.log.append(rec)

    def start(self) -> int:
        ready = threading.Event()

        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._server = loop.run_until_complete(asyncio.start_server(self.handle, "127.0.0.1", 0))
            self.port = self._server.sockets[0].getsockname()[1]
            self._loop = loop
            ready.set()
            loop.run_forever()

        threading.Thread(target=run, daemon=True, name="vp-capture-proxy").start()
        if not ready.wait(5):
            raise RuntimeError("capture proxy did not start")
        return self.port

    def stop(self) -> None:
        loop, srv = self._loop, self._server
        if loop is None:
            return

        def _close():
            if srv is not None:
                srv.close()
            for t in asyncio.all_tasks(loop):
                t.cancel()
            loop.call_soon(loop.stop)
        try:
            loop.call_soon_threadsafe(_close)
        except RuntimeError:
            pass

    def main_verdict(self, host: str, port: int) -> Optional[str]:
        """The verdict of the FIRST request for the named document's host:port (None = never asked)."""
        h = _canonical_host(host)
        with self._lock:
            for r in self.log:
                if r.get("host") == h and r.get("port") == port:
                    return r.get("verdict")
        return None


# ── browser ─────────────────────────────────────────────────────────────────────────────────

# condition 3: no UDP that does not go through the proxy - and an HTTP proxy carries no UDP at all
WEBRTC_FLAGS = (
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
)


def find_browser() -> Optional[str]:
    """The Chrome/Chromium binary to capture with: ``CORVIN_CAPTURE_BROWSER`` if it is an executable,
    else the first of google-chrome / chromium on PATH."""
    env = os.environ.get("CORVIN_CAPTURE_BROWSER", "").strip()
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        return env
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    return None


def chrome_command(chrome: str, *, proxy_port: int, profile_dir: str, out_png: str, url: str,
                   viewport: str) -> List[str]:
    w, h, dsf = VIEWPORTS[viewport]
    return [
        chrome, "--headless=new", f"--user-data-dir={profile_dir}", "--no-first-run",
        "--no-default-browser-check", "--incognito",
        # condition 1: Chrome's own background traffic off (the proxy refuses it anyway)
        "--disable-background-networking", "--disable-component-update", "--disable-sync",
        "--disable-domain-reliability", "--disable-client-side-phishing-detection", "--no-pings",
        "--disable-default-apps", "--disable-extensions", "--metrics-recording-only",
        "--disable-features=DnsOverHttps,NetworkPrediction,Translate,OptimizationHints,MediaRouter,"
        "AutofillServerCommunication,CertificateTransparencyComponentUpdater,InterestFeedContentSuggestions",
        # every request through the one proxy; loopback too (Chrome bypasses it for loopback by default)
        f"--proxy-server=http://127.0.0.1:{proxy_port}", "--proxy-bypass-list=<-loopback>",
        # condition 2: Chrome resolves nothing itself - only the proxy does
        "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
        "--disable-quic",
        *WEBRTC_FLAGS,
        "--deny-permission-prompts", "--disable-notifications", "--mute-audio", "--hide-scrollbars",
        f"--window-size={w},{h}", f"--force-device-scale-factor={dsf}",
        "--virtual-time-budget=5000", f"--screenshot={out_png}",
        url,
    ]


def run_capture(url: str, *, viewport: str, work_dir: str, proxy: CaptureProxy, chrome: str,
                deadline_s: float = NAVIGATION_DEADLINE_S) -> Dict[str, Any]:
    """Run the browser once through an already started ``proxy``; the code the worker runs.
    -> ``{ok, reason, png_path}``. ``ok`` only when the named document itself was fetched through the
    proxy (a refused/unreachable document never yields a screenshot of an error page)."""
    out_png = os.path.join(work_dir, "shot.png")
    profile = os.path.join(work_dir, "profile")
    os.makedirs(profile, mode=0o700, exist_ok=True)
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    cmd = chrome_command(chrome, proxy_port=proxy.port, profile_dir=profile, out_png=out_png, url=url,
                         viewport=viewport)
    try:
        r = _dl.run_process(cmd, deadline_s=deadline_s, what="capture browser", max_output=64 * 1024)
    except _dl.DeadlineExceeded:
        return {"ok": False, "reason": "timeout", "png_path": None}
    verdict = proxy.main_verdict(parts.hostname or "", port)
    if verdict != "connected":
        return {"ok": False, "reason": "refused" if verdict == "refused" else "unreachable", "png_path": None}
    if r.returncode != 0 or not os.path.isfile(out_png) or os.path.getsize(out_png) == 0:
        return {"ok": False, "reason": "browser_failed", "png_path": None}
    return {"ok": True, "reason": "ok", "png_path": out_png}


# ── host side ───────────────────────────────────────────────────────────────────────────────

_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT)


def capture_url(url: str, *, viewport: str = "desktop", deadline_s: float = CAPTURE_DEADLINE_S,
                console_names: Iterable[str] = (), chrome: Optional[str] = None,
                work_dir: Optional[str] = None) -> Dict[str, Any]:
    """Capture ``url`` in a worker process -> ``{ok, reason, png, elapsed}``; ``png`` only when ``ok``.

    ``reason`` is a closed token: ok | invalid_url | refused | unreachable | timeout | browser_failed |
    no_browser | busy. It is for the audit record; a caller must answer refused / unreachable / timeout
    identically (ADR-2249 D4 "uniform failures")."""
    t0 = time.monotonic()

    def done(ok: bool, reason: str, png: Optional[bytes] = None) -> Dict[str, Any]:
        return {"ok": ok, "reason": reason, "png": png, "elapsed": time.monotonic() - t0}

    if viewport not in VIEWPORTS:
        return done(False, "invalid_url")
    try:
        target = check_url(url)
    except CaptureRefused as e:
        return done(False, e.code)
    if precheck_host(target["host"], console_names):
        return done(False, "refused")
    chrome = chrome or find_browser()
    if not chrome:
        return done(False, "no_browser")
    if not _SLOTS.acquire(blocking=False):
        return done(False, "busy")
    own_dir = work_dir is None
    work = work_dir or tempfile.mkdtemp(prefix="vp-capture-")
    try:
        os.chmod(work, 0o700)
        request = {"url": target["url"], "host": target["host"], "port": target["port"], "viewport": viewport,
                   "work_dir": work, "chrome": chrome, "console_names": sorted(set(console_names)),
                   "navigation_deadline_s": max(1.0, min(NAVIGATION_DEADLINE_S, deadline_s - 2.0))}
        try:
            r = _dl.run_process([sys.executable, "-I", os.path.abspath(__file__), "--worker"],
                                input=json.dumps(request), deadline_s=deadline_s, text=True,
                                what="website capture", max_output=64 * 1024)
        except _dl.DeadlineExceeded:
            return done(False, "timeout")
        try:
            res = json.loads((r.stdout or "").strip().splitlines()[-1])
        except (ValueError, IndexError):
            return done(False, "browser_failed")
        if not res.get("ok"):
            reason = res.get("reason")
            return done(False, reason if reason in ("refused", "unreachable", "timeout") else "browser_failed")
        png_path = os.path.join(work, "shot.png")
        try:
            fd = os.open(png_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as f:
                png = f.read(MAX_PNG_BYTES + 1)
        except OSError:
            return done(False, "browser_failed")
        if not png or len(png) > MAX_PNG_BYTES:
            return done(False, "browser_failed")
        return done(True, "ok", png)
    finally:
        _SLOTS.release()
        if own_dir:
            shutil.rmtree(work, ignore_errors=True)
        else:
            shutil.rmtree(os.path.join(work, "profile"), ignore_errors=True)


def _worker_main() -> int:
    """``python -I capture.py --worker``: one request as JSON on stdin, one JSON line on stdout."""
    _dl.mark_job_process()  # Chrome stays in THIS process group: the host's killpg reaches it
    req = json.loads(sys.stdin.read())
    proxy = CaptureProxy(named_hosts=[req["host"]], ports={80, 443, int(req["port"])},
                         console_names=req.get("console_names") or ())
    proxy.start()
    try:
        res = run_capture(req["url"], viewport=req["viewport"], work_dir=req["work_dir"], proxy=proxy,
                          chrome=req["chrome"], deadline_s=float(req["navigation_deadline_s"]))
    finally:
        proxy.stop()
    print(json.dumps({"ok": res["ok"], "reason": res["reason"]}), flush=True)
    return 0


if __name__ == "__main__" and "--worker" in sys.argv[1:]:
    sys.exit(_worker_main())
