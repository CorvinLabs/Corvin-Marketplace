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
* **The worker** (``python -I capture.py --worker``) starts a ``CaptureProxy`` and drives Chrome over
  the DevTools protocol on a pipe (``--remote-debugging-pipe``: no listening port). It navigates, waits
  for the page to settle and takes the screenshot only when the frame that is SHOWN is an http(s)
  document the proxy actually connected to - a redirect, meta refresh or script navigation to an
  address that was refused, and every Chrome error page, is a failed capture, never an asset. Chrome
  stays in the worker's process group (``deadline.mark_job_process``), so the host's group kill reaches
  the browser too.
* **What may load.** The host the user named passed the tenant's real L35 gate before the worker
  started. Any OTHER host (a redirect target, a CDN, a font host) is allowed only when the tenant's
  egress rules - passed to the worker as data (``egress``: forbidden / allowed / default, exact host
  match, the same rules ``EgressGate.validate`` applies) - allow it, only on ports 80/443, and only
  when every resolved address passes the address policy below. Without ``egress`` only the named host
  may load (the strict mode the spike measured).
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
NAVIGATION_DEADLINE_S = 9.0   # the browser inside the worker: navigate + settle + screenshot
CAPTURE_DEADLINE_S = 12.0     # the whole worker (proxy start + browser + screenshot); a caller pads
                              # every failure to this bound so a hang answers like a refusal
SETTLE_MIN_S = 1.0            # after the load event: let a meta refresh / script navigation happen
SETTLE_MAX_S = 3.0            # ... and wait for network idle at most this long
MAX_CONCURRENT = 2            # host-wide
MAX_PER_TENANT = 1            # per tenant, inside the host-wide bound
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


class OwnAddressesUnknown(RuntimeError):
    """This host's own addresses could not be enumerated; a capture must not run (fail closed)."""


def _udp_local(probe: str, family: int) -> Optional[str]:
    """The source address the kernel would use towards ``probe`` - a UDP connect sends no packet."""
    try:
        with socket.socket(family, socket.SOCK_DGRAM) as s:
            s.connect((probe, 53))
            return s.getsockname()[0]
    except OSError:
        return None


def own_addresses() -> Set[Any]:
    """Every address of this host - so the host can never be its own target. Sources, any of which
    counts: ``ip -j addr`` (Linux), ``ifconfig -a`` (macOS/BSD), and on every platform the source
    address the kernel picks towards a public v4/v6 address (a UDP connect, no packet sent), plus
    what this host's names resolve to and the loopback addresses. Raises ``OwnAddressesUnknown`` when
    no interface source answered at all, instead of silently checking against loopback only."""
    out: Set[Any] = {ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1")}
    known = False

    def add(text: str) -> None:
        try:
            out.add(ipaddress.ip_address(text.split("%")[0]))
        except ValueError:
            pass

    if shutil.which("ip"):
        try:
            r = _dl.run_process(["ip", "-j", "addr"], deadline_s=5, text=True, what="ip addr")
            for itf in json.loads(r.stdout or "[]"):
                for a in itf.get("addr_info", []):
                    add(a["local"])
            known = True
        except Exception:  # noqa: BLE001 - the next source decides; known stays False if none answers
            pass
    if not known and shutil.which("ifconfig"):
        try:
            r = _dl.run_process(["ifconfig", "-a"], deadline_s=5, text=True, what="ifconfig")
            for line in (r.stdout or "").splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] in ("inet", "inet6"):
                    add(parts[1])
                    known = True
        except Exception:  # noqa: BLE001
            pass
    for probe, fam in (("192.0.2.1", socket.AF_INET), ("2001:db8::1", socket.AF_INET6)):
        local = _udp_local(probe, fam)
        if local:
            add(local)
            known = True
    for name in {socket.gethostname(), socket.getfqdn()}:
        try:
            for info in socket.getaddrinfo(name, None):
                add(info[4][0])
        except (OSError, ValueError):
            pass
    if not known:
        raise OwnAddressesUnknown("no interface source answered")
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
        try:
            return address_verdict(lit, own_addresses())
        except OwnAddressesUnknown:
            return "own_unknown"
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


OTHER_HOST_PORTS = frozenset({80, 443})
ANNOUNCE_WAIT_S = 1.2  # < FLOOR_S: waiting for a page's announcement never changes a refusal's timing


def egress_allows(host: str, egress: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    """The tenant's egress rules for a host that was NOT named: forbidden wins, then allowed, then the
    default - exact host match, as ``EgressGate.validate`` decides. No rules -> not allowed."""
    if not egress:
        return False, "not_named"
    h = _canonical_host(host)
    if h in {_canonical_host(x) for x in egress.get("forbidden") or ()}:
        return False, "egress_forbidden"
    if h in {_canonical_host(x) for x in egress.get("allowed") or ()}:
        return True, "egress_allowed"
    if egress.get("default") == "allow":
        return True, "egress_default_allow"
    return False, "egress_default_deny"


class CaptureProxy:
    """Forward proxy for ONE capture. ``named_hosts``/``ports``: the destinations the user named (they
    passed the real egress gate on the host); ``egress``: the tenant's rules for every OTHER host
    (``egress_allows``), None = only the named hosts; ``resolver``: name -> list of address strings
    (default: the system resolver). The address policy applies to every host alike."""

    def __init__(self, named_hosts: Iterable[str], ports: Iterable[int] = (80, 443),
                 console_names: Iterable[str] = (), resolver: Optional[Resolver] = None,
                 egress: Optional[Dict[str, Any]] = None):
        self.named = {_canonical_host(h) for h in named_hosts}
        self.ports = {int(p) for p in ports}
        self.console_names = set(console_names)
        self.resolver = resolver
        self.egress = egress
        self.announced: Set[Tuple[str, int]] = set()   # (host, port) a PAGE session asked for
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

    def announce(self, host: str, port: int) -> None:
        """A page (not the browser) is about to request host:port - seen on a page-scoped DevTools
        session. Only an announced host can be allowed besides the named one, so Chrome's own
        background traffic (never on a page session) is refused whatever the egress rules say."""
        with self._lock:
            self.announced.add((_canonical_host(host), int(port)))

    def _is_announced(self, host: str, port: int) -> bool:
        with self._lock:
            return (_canonical_host(host), port) in self.announced

    def _host_allowed(self, host: str, port: int) -> Tuple[bool, str]:
        if self._is_named(host, port):
            return True, "named"
        if not self.egress or port not in OTHER_HOST_PORTS:
            return False, "not_named"
        if not self._is_announced(host, port):
            return False, "not_from_page"
        return egress_allows(host, self.egress)

    async def decide(self, host: str, port: int) -> Tuple[Optional[Any], str]:
        if self.egress and not self._is_named(host, port) and port in OTHER_HOST_PORTS:
            # the page's announcement may arrive just after the CONNECT; refusals answer at FLOOR_S anyway
            end = time.monotonic() + ANNOUNCE_WAIT_S
            while not self._is_announced(host, port) and time.monotonic() < end:
                await asyncio.sleep(0.02)
        allowed, why = self._host_allowed(host, port)
        if not allowed:
            return None, why
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
        """The verdict of the FIRST request for host:port (None = never asked)."""
        h = _canonical_host(host)
        with self._lock:
            for r in self.log:
                if r.get("host") == h and r.get("port") == port:
                    return r.get("verdict")
        return None

    def connected(self, host: str, port: int) -> bool:
        """Did the proxy open a connection to host:port at least once during this capture?"""
        h = _canonical_host(host)
        with self._lock:
            return any(r.get("host") == h and r.get("port") == port and r.get("verdict") == "connected"
                       for r in self.log)

    def hosts(self) -> Dict[str, int]:
        """verdict -> number of distinct hosts (for the audit record: counts, never names)."""
        seen: Dict[str, Set[str]] = {}
        with self._lock:
            for r in self.log:
                if r.get("host"):
                    seen.setdefault(r.get("verdict") or "?", set()).add(r["host"])
        return {k: len(v) for k, v in seen.items()}


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


def chrome_command(chrome: str, *, proxy_port: int, profile_dir: str, viewport: str) -> List[str]:
    """Chrome for one capture, driven over ``--remote-debugging-pipe`` (fds 3/4). It starts on
    about:blank; the URL is navigated over the protocol so the result of the navigation is known."""
    w, h, dsf = VIEWPORTS[viewport]
    return [
        chrome, "--headless=new", f"--user-data-dir={profile_dir}", "--no-first-run",
        "--no-default-browser-check", "--incognito", "--remote-debugging-pipe",
        # condition 1: Chrome's own background traffic off
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
        "about:blank",
    ]


class _Cdp:
    """DevTools protocol over the pipe Chrome opens with ``--remote-debugging-pipe``: NUL-terminated
    JSON both ways. A reader thread dispatches answers to callers and, for every page-scoped session,
    announces the hosts the page requests to the proxy the moment the event arrives. Sessions of
    iframes and workers are auto-attached, their Network domain enabled before they run."""

    def __init__(self, wfd: int, rfd: int, end: float, proxy: Optional["CaptureProxy"] = None):
        import queue  # noqa: PLC0415
        self.w, self.r, self.end, self.proxy = wfd, rfd, end, proxy
        self.next_id = 0
        self._wlock = threading.Lock()
        self._cond = threading.Condition()
        self._answers: Dict[int, Dict[str, Any]] = {}
        self._closed = False
        self.events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.page_sessions: Set[str] = set()
        self._thread = threading.Thread(target=self._reader, daemon=True, name="vp-capture-cdp")
        self._thread.start()

    def join(self, timeout: float) -> None:
        self._thread.join(timeout)

    def left(self) -> float:
        return self.end - time.monotonic()

    def _send(self, method: str, params: Optional[Dict[str, Any]] = None, session: Optional[str] = None) -> int:
        with self._wlock:
            self.next_id += 1
            mid = self.next_id
            msg: Dict[str, Any] = {"id": mid, "method": method, "params": params or {}}
            if session:
                msg["sessionId"] = session
            data = memoryview(json.dumps(msg).encode() + b"\0")
            while data:
                data = data[os.write(self.w, data):]
        return mid

    def _reader(self) -> None:
        buf = bytearray()
        try:
            while True:
                chunk = os.read(self.r, 1 << 20)
                if not chunk:
                    break
                buf += chunk
                while True:
                    i = buf.find(b"\0")
                    if i < 0:
                        break
                    raw = bytes(buf[:i])
                    del buf[:i + 1]
                    try:
                        self._dispatch(json.loads(raw))
                    except Exception:  # noqa: BLE001 - one bad message never stops the reader
                        pass
        except OSError:
            pass
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def _dispatch(self, m: Dict[str, Any]) -> None:
        if "id" in m:
            with self._cond:
                self._answers[m["id"]] = m
                self._cond.notify_all()
            return
        method, sid, prm = m.get("method"), m.get("sessionId"), m.get("params") or {}
        if method == "Target.attachedToTarget":
            child = prm.get("sessionId")
            if child and (prm.get("targetInfo") or {}).get("type") in (
                    "page", "iframe", "worker", "shared_worker", "service_worker"):
                self.watch(child, resume=bool(prm.get("waitingForDebugger")))
        elif method == "Network.requestWillBeSent" and sid in self.page_sessions and self.proxy:
            parts = urlsplit(str((prm.get("request") or {}).get("url") or ""))
            default = {"http": 80, "ws": 80, "https": 443, "wss": 443}.get(parts.scheme)
            if default and parts.hostname:
                try:
                    self.proxy.announce(parts.hostname, parts.port or default)
                except ValueError:
                    pass
        self.events.put(m)

    def watch(self, sid: str, resume: bool = False) -> None:
        """Announce this session's requests; follow its children; let it run if it waits."""
        self.page_sessions.add(sid)
        self._send("Network.enable", session=sid)
        self._send("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": True,
                                            "flatten": True}, session=sid)
        if resume:
            self._send("Runtime.runIfWaitingForDebugger", session=sid)

    def call(self, method: str, params: Optional[Dict[str, Any]] = None, session: Optional[str] = None,
             timeout: float = 5.0) -> Dict[str, Any]:
        mid = self._send(method, params, session)
        until = min(time.monotonic() + timeout, self.end)
        with self._cond:
            while mid not in self._answers:
                if self._closed:
                    raise EOFError("devtools pipe closed")
                wait = until - time.monotonic()
                if wait <= 0:
                    raise TimeoutError("devtools")
                self._cond.wait(wait)
            m = self._answers.pop(mid)
        if "error" in m:
            raise RuntimeError(f"devtools {method}: {str(m['error'])[:120]}")
        return m.get("result") or {}

    def next_event(self, until: float) -> Optional[Dict[str, Any]]:
        """The next event, None when ``until`` passes first; TimeoutError past the capture deadline."""
        import queue  # noqa: PLC0415
        wait = min(until, self.end) - time.monotonic()
        try:
            return self.events.get(timeout=max(0.0, wait))
        except queue.Empty:
            if time.monotonic() >= self.end:
                raise TimeoutError("devtools") from None
            return None

    def drain(self) -> None:
        import queue  # noqa: PLC0415
        try:
            while True:
                self.events.get_nowait()
        except queue.Empty:
            pass


def _shown_frame(cdp: _Cdp, sid: str, proxy: CaptureProxy) -> Tuple[Optional[str], str]:
    """The URL of the frame that is shown, when it is an http(s) document the proxy connected to;
    else (None, reason). An error page (``unreachableUrl``, ``chrome-error:``) is never shown."""
    frame = (cdp.call("Page.getFrameTree", session=sid, timeout=max(0.1, cdp.left()))
             .get("frameTree") or {}).get("frame") or {}
    if frame.get("unreachableUrl"):
        return None, "unreachable"
    parts = urlsplit(str(frame.get("url") or ""))
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None, "unreachable"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if not proxy.connected(parts.hostname, port):
        return None, "refused"
    return f"{parts.scheme}://{parts.netloc}{parts.path or '/'}", "ok"


def _drive(cdp: _Cdp, url: str, viewport: str, out_png: str, proxy: CaptureProxy) -> Dict[str, Any]:
    target = cdp.call("Target.createTarget", {"url": "about:blank"})["targetId"]
    sid = cdp.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
    cdp.watch(sid)
    cdp.call("Page.enable", session=sid)
    cdp.call("Page.setLifecycleEventsEnabled", {"enabled": True}, session=sid)
    w, h, dsf = VIEWPORTS[viewport]
    cdp.call("Emulation.setDeviceMetricsOverride",
             {"width": w, "height": h, "deviceScaleFactor": dsf, "mobile": viewport == "mobile"}, session=sid)
    cdp.drain()
    nav = cdp.call("Page.navigate", {"url": url}, session=sid, timeout=max(0.1, cdp.left()))
    if nav.get("errorText"):
        return {"ok": False, "reason": "unreachable"}
    loader = nav.get("loaderId")
    loaded = False
    while not loaded:  # the load event of THIS navigation (raises TimeoutError at the deadline)
        ev = cdp.next_event(cdp.end)
        loaded = bool(ev) and ev.get("sessionId") == sid and ev.get("method") == "Page.loadEventFired"
    t_load = time.monotonic()
    idle = False
    while True:  # settle: a meta refresh or script navigation happens here, then network idle
        now = time.monotonic()
        if now - t_load >= SETTLE_MAX_S or (idle and now - t_load >= SETTLE_MIN_S):
            break
        ev = cdp.next_event(min(t_load + SETTLE_MAX_S, now + 0.2))
        if ev and ev.get("sessionId") == sid and ev.get("method") == "Page.lifecycleEvent":
            prm = ev.get("params") or {}
            if prm.get("name") == "networkIdle" and prm.get("loaderId") == loader:
                idle = True
            elif prm.get("name") == "init":
                loader, idle = prm.get("loaderId"), False  # a new document started loading
    shown, why = _shown_frame(cdp, sid, proxy)
    if not shown:
        return {"ok": False, "reason": why}
    shot = cdp.call("Page.captureScreenshot", {"format": "png"}, session=sid, timeout=max(0.1, cdp.left()))
    again, why = _shown_frame(cdp, sid, proxy)
    if again != shown:  # navigated away while the screenshot was taken
        return {"ok": False, "reason": why if not again else "unreachable"}
    import base64  # noqa: PLC0415
    png = base64.b64decode(shot.get("data") or "")
    if not png:
        return {"ok": False, "reason": "browser_failed"}
    with open(out_png, "wb") as f:
        f.write(png)
    return {"ok": True, "reason": "ok", "final_url": shown}


def _high_fd(fd: int) -> int:
    """Move ``fd`` above the stdio range so the spawn's dup2 onto 3/4 never targets itself (a
    dup2(fd, fd) would leave close-on-exec set and Chrome would start without its pipe)."""
    import fcntl  # noqa: PLC0415
    hi = fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 10)
    os.close(fd)
    return hi


def run_capture(url: str, *, viewport: str, work_dir: str, proxy: CaptureProxy, chrome: str,
                deadline_s: float = NAVIGATION_DEADLINE_S) -> Dict[str, Any]:
    """Run the browser once through an already started ``proxy``; the code the worker runs.
    -> ``{ok, reason, png_path, final_url}``. ``ok`` only when the frame that is shown at the end is an
    http(s) document the proxy connected to - so a redirect to a refused address, a dead link or an
    error page never yields a screenshot. Every Chrome process is gone when this returns."""
    if not hasattr(os, "posix_spawn"):
        return {"ok": False, "reason": "unsupported", "png_path": None}
    end = time.monotonic() + deadline_s
    out_png = os.path.join(work_dir, "shot.png")
    profile = os.path.join(work_dir, "profile")
    os.makedirs(profile, mode=0o700, exist_ok=True)
    cmd = chrome_command(chrome, proxy_port=proxy.port, profile_dir=profile, viewport=viewport)
    r_cmd, w_cmd = (_high_fd(x) for x in os.pipe())
    r_res, w_res = (_high_fd(x) for x in os.pipe())
    devnull = os.devnull
    actions = [(os.POSIX_SPAWN_DUP2, r_cmd, 3), (os.POSIX_SPAWN_DUP2, w_res, 4),
               (os.POSIX_SPAWN_OPEN, 0, devnull, os.O_RDONLY, 0),
               (os.POSIX_SPAWN_OPEN, 1, devnull, os.O_WRONLY, 0),
               (os.POSIX_SPAWN_OPEN, 2, devnull, os.O_WRONLY, 0)]
    pid = None
    cdp: Optional[_Cdp] = None
    try:
        pid = os.posix_spawn(chrome, cmd, dict(os.environ), file_actions=actions)
        os.close(r_cmd)
        os.close(w_res)
        r_cmd = w_res = -1
        cdp = _Cdp(w_cmd, r_res, end, proxy)
        try:
            res = _drive(cdp, url, viewport, out_png, proxy)
        except TimeoutError:
            res = {"ok": False, "reason": "timeout"}
        except (EOFError, RuntimeError, OSError, ValueError, KeyError):
            res = {"ok": False, "reason": "browser_failed"}
        try:
            cdp.end = time.monotonic() + 1.0
            cdp.call("Browser.close", timeout=1.0)
        except Exception:  # noqa: BLE001 - killed below anyway
            pass
    except OSError:
        res = {"ok": False, "reason": "browser_failed"}
    finally:
        if pid:  # Chrome first: its exit gives the reader thread EOF before any fd number is freed
            _reap(pid, profile)
        if cdp is not None:
            cdp.join(1.0)
        for fd in (r_cmd, w_cmd, r_res, w_res):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
    res.setdefault("png_path", out_png if res.get("ok") else None)
    return res


def _reap(pid: int, marker: str) -> None:
    """Chrome and every process it started are gone when this returns: the tree under ``pid`` while it
    still has its parent links, then anything left that carries the profile directory ``marker``."""
    try:
        _dl.kill_process_tree([pid], grace_s=0.5)
    except Exception:  # noqa: BLE001
        pass
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    try:
        left = [x for x in _dl.find_processes(marker) if x != os.getpid()]
        if left:
            _dl.kill_process_tree(left, grace_s=0.5)
    except Exception:  # noqa: BLE001
        pass


# ── host side ───────────────────────────────────────────────────────────────────────────────

_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT)
_TENANT_LOCK = threading.Lock()
_TENANT_RUNNING: Dict[str, int] = {}


def _take_slot(tenant: str) -> bool:
    """One of the host-wide slots AND a free per-tenant slot, or nothing (never blocks)."""
    with _TENANT_LOCK:
        if _TENANT_RUNNING.get(tenant, 0) >= MAX_PER_TENANT:
            return False
        if not _SLOTS.acquire(blocking=False):
            return False
        _TENANT_RUNNING[tenant] = _TENANT_RUNNING.get(tenant, 0) + 1
        return True


def _give_slot(tenant: str) -> None:
    with _TENANT_LOCK:
        n = _TENANT_RUNNING.get(tenant, 0) - 1
        if n > 0:
            _TENANT_RUNNING[tenant] = n
        else:
            _TENANT_RUNNING.pop(tenant, None)
        _SLOTS.release()


def capture_url(url: str, *, viewport: str = "desktop", deadline_s: float = CAPTURE_DEADLINE_S,
                console_names: Iterable[str] = (), chrome: Optional[str] = None,
                work_dir: Optional[str] = None, egress: Optional[Dict[str, Any]] = None,
                tenant: str = "_default") -> Dict[str, Any]:
    """Capture ``url`` in a worker process -> ``{ok, reason, png, final_url, hosts, elapsed}``; ``png``
    only when ``ok``. ``egress``: the tenant's rules for hosts other than the named one
    (``egress_allows``); ``tenant`` keys the per-tenant concurrency bound.

    ``reason`` is a closed token: ok | invalid_url | refused | unreachable | timeout | browser_failed |
    no_browser | unsupported | busy. It is for the audit record; a caller must answer refused /
    unreachable / timeout / browser_failed identically, by content and by time (ADR-2249 D4)."""
    t0 = time.monotonic()

    def done(ok: bool, reason: str, png: Optional[bytes] = None, **extra: Any) -> Dict[str, Any]:
        return {"ok": ok, "reason": reason, "png": png, "final_url": extra.get("final_url"),
                "hosts": extra.get("hosts") or {}, "elapsed": time.monotonic() - t0}

    if viewport not in VIEWPORTS:
        return done(False, "invalid_url")
    try:
        target = check_url(url)
    except CaptureRefused as e:
        return done(False, e.code)
    if not hasattr(os, "posix_spawn"):
        return done(False, "unsupported")
    try:
        own_addresses()
    except OwnAddressesUnknown:
        return done(False, "unsupported")
    if precheck_host(target["host"], console_names):
        return done(False, "refused")
    chrome = chrome or find_browser()
    if not chrome:
        return done(False, "no_browser")
    if not _take_slot(tenant):
        return done(False, "busy")
    own_dir = work_dir is None
    work = None
    try:
        work = work_dir or tempfile.mkdtemp(prefix="vp-capture-")
        os.chmod(work, 0o700)
        request = {"url": target["url"], "host": target["host"], "port": target["port"], "viewport": viewport,
                   "work_dir": work, "chrome": chrome, "console_names": sorted(set(console_names)),
                   "egress": egress,
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
        hosts = res.get("hosts") if isinstance(res.get("hosts"), dict) else {}
        if not res.get("ok"):
            reason = res.get("reason")
            if reason not in ("refused", "unreachable", "timeout", "unsupported"):
                reason = "browser_failed"
            return done(False, reason, hosts=hosts)
        png_path = os.path.join(work, "shot.png")
        try:
            fd = os.open(png_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as f:
                png = f.read(MAX_PNG_BYTES + 1)
        except OSError:
            return done(False, "browser_failed", hosts=hosts)
        if not png or len(png) > MAX_PNG_BYTES:
            return done(False, "browser_failed", hosts=hosts)
        final = res.get("final_url") if isinstance(res.get("final_url"), str) else None
        return done(True, "ok", png, final_url=final, hosts=hosts)
    except OSError:  # no temp dir, no process: a failure like any other, never an exception
        return done(False, "browser_failed")
    finally:
        _give_slot(tenant)
        if work:
            if own_dir:
                shutil.rmtree(work, ignore_errors=True)
            else:
                shutil.rmtree(os.path.join(work, "profile"), ignore_errors=True)


def _worker_main() -> int:
    """``python -I capture.py --worker``: one request as JSON on stdin, one JSON line on stdout."""
    _dl.mark_job_process()  # Chrome stays in THIS process group: the host's killpg reaches it
    req = json.loads(sys.stdin.read())
    try:
        proxy = CaptureProxy(named_hosts=[req["host"]], ports={80, 443, int(req["port"])},
                             console_names=req.get("console_names") or (), egress=req.get("egress"))
    except OwnAddressesUnknown:
        print(json.dumps({"ok": False, "reason": "unsupported"}), flush=True)
        return 0
    proxy.start()
    try:
        res = run_capture(req["url"], viewport=req["viewport"], work_dir=req["work_dir"], proxy=proxy,
                          chrome=req["chrome"], deadline_s=float(req["navigation_deadline_s"]))
    finally:
        proxy.stop()
    print(json.dumps({"ok": res["ok"], "reason": res["reason"], "final_url": res.get("final_url"),
                      "hosts": proxy.hosts()}), flush=True)
    return 0


if __name__ == "__main__" and "--worker" in sys.argv[1:]:
    sys.exit(_worker_main())
