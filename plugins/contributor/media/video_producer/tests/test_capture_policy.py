"""Website capture policy (ADR-2249 D4, T-0113 part 1): the spike S3 hostile corpus (T-0112,
``spike_capture_policy/``) as a regression test against the PRODUCTION module ``src/capture.py``.

What is measured, against real sockets, a real hostile DNS stub and a real headless Chrome:

* the 138-URL curl corpus through ``capture.CaptureProxy`` (absolute-form HTTP + CONNECT): zero
  connections made by the proxy to a hostile address, zero connections accepted by canary listeners on
  every local v4/v6 address, every answer the one uniform 502;
* every refusal class (refused name, refused address, empty DNS, a host that was not named, connect
  refused, connect timeout) answers the SAME bytes at the SAME instant (``FLOOR_S``);
* the 8 browser pages of the spike (redirect, meta refresh, JS navigation, iframe, img, fetch incl.
  rebinding, WebSocket, service worker) through ``capture.run_capture`` - the code the worker runs -,
  both with the production allowlist (only the named host) and with every host named (so the address
  policy alone decides): zero canary hits, nothing but the named fixture ever connected;
* the three conditions of the spike: Chrome's background traffic never leaves (only the named host is
  allowed), the resolver rules flag, and WebRTC/UDP disabled - with a positive control showing the UDP
  canary DOES see Chrome's STUN packets when the flag is left out;
* the worker's process group is killed at the deadline with nothing left running.

The run is OFFLINE except where noted: names outside ``.test`` are refused by the test resolver, and a
policy-allowed global address is recorded, never dialled. The only pinned connection is the harness
fixture ``origin.test`` (it hosts the hostile pages) and it is excluded from the hostile count.
"""
from __future__ import annotations

import asyncio
import http.server
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _capture_hostile_dns as dnsstub  # noqa: E402

from src import capture  # noqa: E402  - the module under test (RED until it exists)
from src import deadline as dl  # noqa: E402

pytestmark = [
    pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc (Linux)"),
    pytest.mark.skipif(shutil.which("curl") is None, reason="needs curl"),
]

CHROME = capture.find_browser() if hasattr(capture, "find_browser") else None
needs_chrome = pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium on this host")


# ── harness ─────────────────────────────────────────────────────────────────────────────────

class Canary:
    """TCP listeners on every v4 + v6 address at one port; every accepted connection is recorded."""

    def __init__(self):
        self.hits: list = []
        s4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s4.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s4.bind(("0.0.0.0", 0))
        self.port = s4.getsockname()[1]
        s6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s6.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        s6.bind(("::", self.port))
        for s in (s4, s6):
            s.listen(128)
            threading.Thread(target=self._loop, args=(s,), daemon=True).start()

    def _loop(self, s):
        while True:
            try:
                c, peer = s.accept()
            except OSError:
                return
            self.hits.append(peer)
            c.close()


class UdpCanary:
    def __init__(self):
        self.packets = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", 0))
        self.port = self.sock.getsockname()[1]
        # Chrome gathers no ICE candidate on loopback, so a STUN server on 127.0.0.1 is never asked:
        # the page points at one of this host's NON-loopback v4 addresses (measured: 1 packet without the flag)
        lan = sorted(str(a) for a in capture.own_addresses() if a.version == 4 and not a.is_loopback)
        self.addr = lan[0] if lan else "127.0.0.1"
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                self.sock.recvfrom(2048)
            except OSError:
                return
            self.packets += 1


def _stub_resolver(stub_port):
    """Offline resolver: .test names go to the hostile stub; any other name is refused - no real DNS."""
    seen: list = []

    def resolve(host: str):
        seen.append(host)
        if not host.endswith(".test"):
            raise OSError("offline test resolver")
        return dnsstub.query(host, 1, stub_port, 0.2) + dnsstub.query(host, 28, stub_port, 0.2)
    resolve.seen = seen
    return resolve


class OfflineProxy(capture.CaptureProxy):
    """The production proxy with two harness changes only: a policy-ALLOWED global address is recorded
    and withheld (never dialled), and ``origin.test:<fixture>`` is pinned to the loopback fixture."""

    def __init__(self, *a, fixture_port=None, all_named=False, **kw):
        super().__init__(*a, **kw)
        self.fixture_port = fixture_port
        self.all_named = all_named
        self.global_withheld: list = []
        self.extra_fixture_hosts: set = set()

    def _is_named(self, host, port):
        return True if self.all_named else super()._is_named(host, port)

    async def decide(self, host, port):
        if self.fixture_port and host.lower().rstrip(".") == "origin.test" and port == self.fixture_port:
            return ipaddress.ip_address("127.0.0.1"), "harness_fixture"
        if self.fixture_port and host.lower().rstrip(".") in self.extra_fixture_hosts and port == self.fixture_port:
            # the production host rule (page announcement + tenant rules), the fixture's port standing in for 80
            end = time.monotonic() + capture.ANNOUNCE_WAIT_S
            while not self._is_announced(host, port) and time.monotonic() < end:
                await asyncio.sleep(0.02)
            if not self._is_announced(host, port):
                return None, "not_from_page"
            allowed, why = capture.egress_allows(host, self.egress)
            return (ipaddress.ip_address("127.0.0.1"), "harness_fixture") if allowed else (None, why)
        ip, why = await super().decide(host, port)
        if ip is not None:
            self.global_withheld.append((host, str(ip), port))
            return None, "offline_global_withheld"
        return ip, why


def corpus(P: int):
    own = sorted({str(a) for a in capture.own_addresses()})
    hosts = [
        # IPv4 encodings of loopback / any
        "127.0.0.1", "127.1", "127.0.1", "0x7f000001", "2130706433", "017700000001", "0177.0.0.1",
        "0x7f.0.0.1", "0x7f.1", "127.000.000.001", "127.0.0.1.", "127.255.255.254", "0", "0.0.0.0",
        # names
        "localhost", "LOCALHOST.", "foo.localhost", "metadata.google.internal",
        # IPv6 loopback forms
        "[::1]", "[0:0:0:0:0:0:0:1]", "[::ffff:127.0.0.1]", "[::ffff:7f00:1]", "[::127.0.0.1]", "[::]",
        # private / link-local / CGNAT / metadata
        "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254", "100.64.0.1", "100.127.255.254",
        "192.0.0.1", "198.18.0.1", "240.0.0.1", "255.255.255.255",
        # NAT64 / 6to4 / Teredo / v4-compatible
        "[64:ff9b::7f00:1]", "[64:ff9b::a9fe:a9fe]", "[64:ff9b:1::7f00:1]", "[64:ff9b::808:808]",
        "[2002:7f00:1::]", "[2002:a9fe:a9fe::1]", "[2002:808:808::1]", "[2001:0:4136:e378:8000:63bf:80ff:fffe]",
        # multicast
        "224.0.0.1", "239.255.255.250", "[ff02::1]", "[ff05::1:3]",
        # zone ids
        "[fe80::1%25lo]", "[::1%25lo]", "[fe80::157f:af94:7756:94f6%25wlan0]",
        # hostile DNS stub
        "local.test", "v6local.test", "meta.test", "cgnat.test", "nat64.test", "mixed.test",
        "rebind.test", "rebind.test", "rebind.test", "rebind.test", "nx.test",
    ] + [f"[{a}]" if ":" in a else a for a in own]
    urls = []
    for h in hosts:
        urls.append(f"http://{h}:{P}/")
        urls.append(f"https://{h}:{P}/")
    urls += [  # userinfo tricks
        f"http://example.com@127.0.0.1:{P}/", f"http://user:pw@[::1]:{P}/",
        f"http://origin.test%40127.0.0.1:{P}/", f"http://127.0.0.1:{P}%2f@nx.test/",
    ]
    return urls


def _curl(proxy_port, url):
    r = dl.run_process(["curl", "-s", "-k", "-g", "--max-time", "5", "-x", f"http://127.0.0.1:{proxy_port}",
                        "-o", "-", "-w", "\n%{http_code}|%{http_connect}", url], deadline_s=10, text=True)
    out = r.stdout.strip()
    return out.splitlines()[-1] if out else ""


def _raw(proxy_port, line):
    t0 = time.monotonic()
    s = socket.create_connection(("127.0.0.1", proxy_port))
    s.sendall(line.encode() + b"\r\nHost: x\r\n\r\n")
    data = b""
    while True:
        b = s.recv(4096)
        if not b:
            break
        data += b
    s.close()
    return time.monotonic() - t0, data


@pytest.fixture(scope="module")
def stub():
    return dnsstub.Stub()


@pytest.fixture(scope="module")
def canary():
    return Canary()


# ── 1. the curl corpus ──────────────────────────────────────────────────────────────────────

def test_hostile_corpus_reaches_nothing(stub, canary):
    P = canary.port
    px = OfflineProxy(named_hosts=(), resolver=_stub_resolver(stub.port), all_named=True)
    port = px.start()
    try:
        urls = corpus(P)
        assert len(urls) >= 138
        with ThreadPoolExecutor(max_workers=48) as ex:
            tails = list(ex.map(lambda u: (u, _curl(port, u)), urls))
    finally:
        px.stop()
    assert px.outbound == [], f"the proxy dialled a hostile address: {px.outbound}"
    assert canary.hits == [], f"a canary listener accepted a connection: {canary.hits}"
    not_502 = [(u, t) for u, t in tails if not t.startswith("502") and "|502" not in t and t != "000|000"]
    assert not_502 == [], not_502
    rejected_by_curl = [u for u, t in tails if t == "000|000"]
    assert len(rejected_by_curl) <= 1, rejected_by_curl  # spike: one URL never left curl
    # rebinding: the public answer was validated + withheld (never dialled), the loopback ones refused
    assert all(ip == dnsstub.PUBLIC for _h, ip, _p in px.global_withheld), px.global_withheld
    assert {r["reason"].split(":")[0] for r in px.log} >= {"own_interface", "not_global", "refused_name"}


# ── 2. condition 1: only the named host leaves ──────────────────────────────────────────────

def test_only_the_named_host_and_its_ports_may_leave(stub):
    resolver = _stub_resolver(stub.port)
    px = capture.CaptureProxy(named_hosts=["example.org"], ports=[443], resolver=resolver)
    port = px.start()
    try:
        for line in ("CONNECT clients2.google.com:443 HTTP/1.1", "CONNECT accounts.google.com:443 HTTP/1.1",
                     "GET http://safebrowsing.googleapis.com/ HTTP/1.1", "CONNECT example.org:22 HTTP/1.1"):
            _dt, data = _raw(port, line)
            assert data == capture.FAIL
    finally:
        px.stop()
    assert [r["reason"] for r in px.log] == ["not_named"] * 4
    assert resolver.seen == [], "a host that was not named must be refused before any DNS query"
    assert px.outbound == []


# ── 3. uniform failure: same bytes, same instant ────────────────────────────────────────────

class _ConnectAnything(OfflineProxy):
    """Address policy switched OFF so the two unreachable classes can be produced at all."""

    def _address_ok(self, ip):
        return None


def test_every_refusal_and_every_unreachable_answers_identically(stub, canary):
    resolver = _stub_resolver(stub.port)
    strict = OfflineProxy(named_hosts=(), resolver=resolver, all_named=True)
    named = capture.CaptureProxy(named_hosts=["example.org"], resolver=resolver)
    anything = _ConnectAnything(named_hosts=(), resolver=resolver, all_named=True)
    ports = {k: p.start() for k, p in (("strict", strict), ("named", named), ("anything", anything))}
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    cport = closed.getsockname()[1]
    closed.close()
    classes = {
        "refused_loopback": ("strict", f"GET http://127.0.0.1:{canary.port}/ HTTP/1.1"),
        "refused_connect_metadata": ("strict", f"CONNECT 169.254.169.254:{canary.port} HTTP/1.1"),
        "refused_name": ("strict", f"GET http://localhost:{canary.port}/ HTTP/1.1"),
        "dns_empty": ("strict", f"GET http://nx.test:{canary.port}/ HTTP/1.1"),
        "not_named": ("named", "CONNECT clients2.google.com:443 HTTP/1.1"),
        "unreachable_connect_refused": ("anything", f"GET http://127.0.0.1:{cport}/ HTTP/1.1"),
        "unreachable_connect_timeout": ("anything", "GET http://10.255.255.1:9/ HTTP/1.1"),
    }
    times, bodies = {}, set()
    try:
        for name, (which, line) in classes.items():
            ts = []
            for _ in range(5):
                dt, data = _raw(ports[which], line)
                ts.append(dt)
                bodies.add(data)
            times[name] = ts
    finally:
        for p in (strict, named, anything):
            p.stop()
    assert bodies == {capture.FAIL}, bodies
    every = [t for ts in times.values() for t in ts]
    assert min(every) >= capture.FLOOR_S - 0.005, times
    assert max(every) - min(every) < 0.05, times  # spike: 2001.6-2005.8 ms
    assert canary.hits == []


# ── 4. the browser corpus through run_capture (what the worker runs) ────────────────────────

def _fixture_server(P: int, udp_port: int, udp_addr: str = "127.0.0.1"):
    pages = {
        "/redirect": None,
        "/meta": f'<meta http-equiv="refresh" content="0;url=http://127.0.0.1:{P}/meta">',
        "/jsnav": f'<script>location="http://[::1]:{P}/jsnav"</script>',
        "/iframe": f'<iframe src="http://169.254.169.254:{P}/"></iframe><iframe src="http://local.test:{P}/"></iframe>',
        "/img": f'<img src="http://0x7f000001:{P}/i.png"><img src="http://100.64.0.1:{P}/i.png">',
        "/fetch": f'<script>for(const u of ["http://127.1:{P}/f","http://[64:ff9b::7f00:1]:{P}/f","http://rebind.test:{P}/f","http://rebind.test:{P}/f","http://mixed.test:{P}/f"]) fetch(u,{{mode:"no-cors"}}).catch(()=>0)</script>',
        "/ws": f'<script>for(const u of ["ws://127.0.0.1:{P}/","ws://localhost:{P}/","wss://[::1]:{P}/","ws://local.test:{P}/"]) try{{new WebSocket(u)}}catch(e){{}}</script>',
        "/sw": '<script>navigator.serviceWorker.register("/sw.js").then(()=>navigator.serviceWorker.ready).then(()=>fetch("/x")).catch(()=>0)</script>',
        "/sw.js": f'self.addEventListener("install",e=>self.skipWaiting());self.addEventListener("activate",e=>e.waitUntil(clients.claim()));'
                  f'self.addEventListener("fetch",e=>e.respondWith(fetch("http://127.0.0.1:{P}/sw").catch(()=>new Response("x"))));',
        "/webrtc": '<script>const pc=new RTCPeerConnection({iceServers:[{urls:"stun:%s:%d"}]});'
                   'pc.createDataChannel("x");pc.createOffer().then(o=>pc.setLocalDescription(o));</script>'
                   '<p>webrtc</p>' % (udp_addr, udp_port),
        "/hang": None,
        "/plain": "<p>a page with nothing to load</p>",
        "/cdn": '<img src="http://cdn.test/pixel.png"><p>one image from another host</p>',
    }

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            p = self.path.split("?")[0]
            if p == "/redirect":
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{P}/redir")
                self.end_headers()
                return
            if p in ("/offsite", "/to_www"):
                self.send_response(302)
                host = "other.test" if p == "/offsite" else "www.origin.test"
                self.send_header("Location", f"http://{host}:{self.server.server_address[1]}/plain")
                self.end_headers()
                return
            if p == "/hang":
                time.sleep(30)
                return
            body = (pages.get(p) or "ok").encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript" if p.endswith(".js") else "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


BROWSER_PAGES = ["/redirect", "/meta", "/jsnav", "/iframe", "/img", "/fetch", "/ws", "/sw"]


def _survivors(marker: str):
    return dl.find_processes(marker)


# pages whose DOCUMENT moves to a refused address: no screenshot of an error page, ever (review
# 2026-10-13 finding 2); every other page keeps its document and only loses the refused sub-resources
NAVIGATES_AWAY = {"/redirect", "/meta", "/jsnav"}
ALLOW_ALL = {"forbidden": [], "allowed": [], "default": "allow"}


@needs_chrome
@pytest.mark.parametrize("all_named,egress", [(False, None), (True, None), (False, ALLOW_ALL)],
                         ids=["production_allowlist", "address_policy_only", "tenant_egress_allow_all"])
def test_browser_corpus_reaches_nothing(stub, canary, all_named, egress, tmp_path):
    udp = UdpCanary()
    srv, fport = _fixture_server(canary.port, udp.port)
    resolver = _stub_resolver(stub.port)
    px = OfflineProxy(named_hosts=["origin.test"], ports=[fport], resolver=resolver,
                      fixture_port=fport, all_named=all_named, egress=egress)
    px.start()
    results = {}
    try:
        for page in BROWSER_PAGES:
            work = tmp_path / page.strip("/")
            work.mkdir()
            results[page] = capture.run_capture(f"http://origin.test:{fport}{page}", viewport="desktop",
                                                work_dir=str(work), proxy=px, chrome=CHROME, deadline_s=20)
            assert _survivors(str(work)) == [], f"{page}: browser processes survived"
    finally:
        px.stop()
        srv.shutdown()
    assert canary.hits == [], canary.hits
    hostile = [o for o in px.outbound if o != ("127.0.0.1", fport)]
    assert hostile == [], hostile
    connected = {(r.get("host"), r.get("port")) for r in px.log if r.get("verdict") == "connected"}
    assert connected <= {("origin.test", fport)}, connected
    for page, r in results.items():
        if page in NAVIGATES_AWAY:
            assert r["ok"] is False and r["png_path"] is None, (page, r)
        else:
            assert r["ok"] is True and r["final_url"] == f"http://origin.test:{fport}{page}", (page, r)
    # Chrome's own background traffic (if any reached the proxy) was refused, never resolved for real
    assert not [h for h in resolver.seen if not h.endswith(".test")] or all_named


@needs_chrome
def test_chrome_flags_carry_the_three_spike_conditions(tmp_path):
    cmd = capture.chrome_command(CHROME, proxy_port=1234, profile_dir=str(tmp_path / "p"), viewport="desktop")
    assert "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1" in cmd
    assert "--proxy-server=http://127.0.0.1:1234" in cmd
    assert "--proxy-bypass-list=<-loopback>" in cmd
    assert "--disable-quic" in cmd
    assert "--disable-background-networking" in cmd
    assert "--remote-debugging-pipe" in cmd and not [a for a in cmd if a.startswith("--remote-debugging-port")]
    for flag in capture.WEBRTC_FLAGS:
        assert flag in cmd
    assert cmd[-1] == "about:blank"  # the URL is navigated over the protocol, never on the command line


@needs_chrome
def test_a_page_without_subresources_makes_exactly_one_request(stub, canary, tmp_path):
    """Condition 1 under tenant egress rules that allow EVERYTHING: Chrome's own background traffic
    (safe browsing, clients2/accounts.google.com, ... - measured 2026-10-13 despite the flags) never
    appears on a page session, so the proxy refuses it as not_from_page and nothing else is dialled."""
    srv, fport = _fixture_server(canary.port, 9)
    px = OfflineProxy(named_hosts=["origin.test"], ports=[fport], resolver=_stub_resolver(stub.port),
                      fixture_port=fport, egress=ALLOW_ALL)
    px.start()
    try:
        res = capture.run_capture(f"http://origin.test:{fport}/plain", viewport="desktop", work_dir=str(tmp_path),
                                  proxy=px, chrome=CHROME, deadline_s=15)
    finally:
        px.stop()
        srv.shutdown()
    assert res["ok"] is True, res
    assert px.global_withheld == [], px.global_withheld
    others = [r for r in px.log if r.get("host") != "origin.test"]
    assert all(r["reason"] == "not_from_page" for r in others), others
    assert {(r["host"], r["port"]) for r in px.log if r.get("verdict") == "connected"} == {("origin.test", fport)}


@needs_chrome
@pytest.mark.parametrize("egress,reason", [
    (ALLOW_ALL, "dns"), ({"forbidden": ["cdn.test"], "allowed": [], "default": "allow"}, "egress_forbidden"),
    ({"forbidden": [], "allowed": [], "default": "deny"}, "egress_default_deny"),
    ({"forbidden": [], "allowed": ["cdn.test"], "default": "deny"}, "dns"),
], ids=["allow_all", "forbidden", "default_deny", "allowed_explicit"])
def test_a_host_the_page_requests_is_decided_by_the_tenant_rules(stub, canary, egress, reason, tmp_path):
    """A sub-resource host the PAGE asked for reaches the tenant's egress rules (and then the address
    policy - here the stub resolver, so 'dns' = it got past the host rule); a forbidden or unmatched host
    under default deny is refused by the rules themselves."""
    srv, fport = _fixture_server(canary.port, 9)
    px = OfflineProxy(named_hosts=["origin.test"], ports=[fport], resolver=_stub_resolver(stub.port),
                      fixture_port=fport, egress=egress)
    px.start()
    try:
        res = capture.run_capture(f"http://origin.test:{fport}/cdn", viewport="desktop", work_dir=str(tmp_path),
                                  proxy=px, chrome=CHROME, deadline_s=15)
    finally:
        px.stop()
        srv.shutdown()
    assert res["ok"] is True, res
    cdn = [r for r in px.log if r.get("host") == "cdn.test"]
    assert cdn, px.log
    got = cdn[0]["reason"]
    assert got.startswith(reason) or (reason == "dns" and got.split(":")[0] in (
        "dns_fail", "dns_empty", "offline_global_withheld", "not_global", "own_interface")), cdn
    assert canary.hits == [], canary.hits


@needs_chrome
def test_webrtc_udp_never_leaves_the_browser_with_positive_control(stub, canary, tmp_path):
    udp = UdpCanary()
    assert udp.addr != "127.0.0.1", "needs a non-loopback v4 address for the STUN canary"
    srv, fport = _fixture_server(canary.port, udp.port, udp.addr)
    px = OfflineProxy(named_hosts=["origin.test"], ports=[fport], resolver=_stub_resolver(stub.port),
                      fixture_port=fport)
    pport = px.start()
    url = f"http://origin.test:{fport}/webrtc"
    try:
        # positive control: the SAME command without the WebRTC flags - the canary must see STUN packets
        ctl = tmp_path / "control"
        ctl.mkdir()
        # (without the WebRTC flags and without the DevTools pipe; --screenshot makes it exit by itself)
        cmd = [a for a in capture.chrome_command(CHROME, proxy_port=pport, profile_dir=str(ctl / "profile"),
                                                 viewport="desktop")
               if a not in capture.WEBRTC_FLAGS and a not in ("--remote-debugging-pipe", "about:blank")]
        cmd += ["--virtual-time-budget=5000", f"--screenshot={ctl / 'shot.png'}", url]
        dl.run_process(cmd, deadline_s=20, what="control chrome")
        control_packets = udp.packets
        assert control_packets > 0, "positive control failed: the UDP canary saw nothing even without the flag"
        work = tmp_path / "capture"
        work.mkdir()
        res = capture.run_capture(url, viewport="desktop", work_dir=str(work), proxy=px, chrome=CHROME, deadline_s=20)
        time.sleep(0.5)
    finally:
        px.stop()
        srv.shutdown()
    assert res["ok"], res
    assert udp.packets == control_packets, f"WebRTC sent {udp.packets - control_packets} UDP packet(s)"


# ── 5. deadline: the worker's process group is killed ───────────────────────────────────────

@needs_chrome
def test_run_capture_kills_a_hanging_page_at_its_deadline(stub, canary, tmp_path):
    srv, fport = _fixture_server(canary.port, 9)
    px = OfflineProxy(named_hosts=["origin.test"], ports=[fport], resolver=_stub_resolver(stub.port),
                      fixture_port=fport)
    px.start()
    t0 = time.monotonic()
    try:
        res = capture.run_capture(f"http://origin.test:{fport}/hang", viewport="desktop", work_dir=str(tmp_path),
                                  proxy=px, chrome=CHROME, deadline_s=3)
    finally:
        px.stop()
        srv.shutdown()
    assert time.monotonic() - t0 < 6
    assert res["ok"] is False and res["reason"] == "timeout" and res["png_path"] is None
    time.sleep(0.3)
    assert _survivors(str(tmp_path)) == []


@needs_chrome
def test_capture_url_worker_group_is_killed_at_the_host_deadline(tmp_path):
    """The host side: a worker subprocess (own session) running proxy + Chrome, killpg'd at the deadline.
    The URL is a name the real resolver answers NXDOMAIN for, so the proxy holds it for FLOOR_S - longer
    than the deadline - and nothing is fetched from anywhere."""
    t0 = time.monotonic()
    res = capture.capture_url("http://capture-deadline-probe.invalid/", viewport="desktop", deadline_s=1.0,
                              work_dir=str(tmp_path))
    assert time.monotonic() - t0 < 4
    assert res["ok"] is False and res["reason"] == "timeout" and res["png"] is None
    time.sleep(0.3)
    assert _survivors(str(tmp_path)) == [], "worker or browser survived the deadline"


# ── 6. the host-side URL check ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    "ftp://example.org/", "file:///etc/passwd", "javascript:alert(1)", "http://user:pw@example.org/",
    "http://example.org\\@127.0.0.1/", "http:///nohost", "http://exa mple.org/", "", "x" * 3000,
    "http://example.org:0/", "http://example.org:99999/",
])
def test_check_url_refuses_what_is_not_a_plain_http_address(bad):
    with pytest.raises(capture.CaptureRefused):
        capture.check_url(bad)


def test_check_url_normalises_and_names_the_host():
    got = capture.check_url("HTTPS://Example.ORG/pricing?plan=a#top")
    assert got == {"url": "https://example.org/pricing?plan=a", "scheme": "https", "host": "example.org", "port": 443}


@pytest.mark.parametrize("host", ["127.0.0.1", "0x7f000001", "localhost", "[::1]", "169.254.169.254", "10.1.2.3",
                                  "[64:ff9b::7f00:1]", "metadata.google.internal", "my.console.example"])
def test_precheck_refuses_literals_and_names_without_dns(host):
    assert capture.precheck_host(host.strip("[]"), console_names={"my.console.example"}) is not None


def test_precheck_lets_a_public_name_through_to_the_proxy():
    assert capture.precheck_host("example.org", console_names=set()) is None


# ── 7. host-side bounds: per-tenant slots, own addresses fail closed ─────────────────────────

def test_one_tenant_cannot_hold_every_slot():
    assert capture._take_slot("tenant_a")
    try:
        assert not capture._take_slot("tenant_a"), "a second concurrent capture of the same tenant"
        assert capture._take_slot("tenant_b"), "another tenant still gets the second host-wide slot"
        try:
            assert not capture._take_slot("tenant_c"), "the host-wide bound still holds"
        finally:
            capture._give_slot("tenant_b")
    finally:
        capture._give_slot("tenant_a")
    assert capture._TENANT_RUNNING == {}


def test_a_refused_literal_holds_the_slot_like_a_capture_that_ran():
    hold = time.monotonic() + 1.5
    box = {}
    th = threading.Thread(target=lambda: box.update(r=capture.capture_url("http://10.0.0.1/", tenant="lit_t",
                                                                           fail_hold_until=hold)))
    th.start()
    time.sleep(0.5)
    busy = not capture._take_slot("lit_t")
    if not busy:
        capture._give_slot("lit_t")
    th.join(10)
    assert box["r"]["reason"] in ("refused", "no_browser")
    if box["r"]["reason"] == "refused":
        assert busy, "a refused literal released its slot before the answer instant"


def test_own_addresses_fail_closed_when_no_source_answers(monkeypatch):
    monkeypatch.setattr(capture.shutil, "which", lambda name: None)
    monkeypatch.setattr(capture, "_udp_local", lambda probe, fam: None)
    with pytest.raises(capture.OwnAddressesUnknown):
        capture.own_addresses()
    assert capture.precheck_host("203.0.113.9") == "own_unknown"
    res = capture.capture_url("https://example.org/", chrome="/nonexistent")
    assert res["ok"] is False and res["reason"] == "unsupported"


def test_own_addresses_without_ip_still_finds_the_outbound_address(monkeypatch):
    """macOS/Windows have no ``ip``: the UDP-connect source address is found anyway (no packet sent)."""
    monkeypatch.setattr(capture.shutil, "which", lambda name: None)
    got = capture.own_addresses()
    real = capture._udp_local("192.0.2.1", socket.AF_INET)
    if real:
        assert ipaddress.ip_address(real) in got


# ── 8. review 2 (2026-10-13, reviewer A) ─────────────────────────────────────────────────────

@pytest.mark.parametrize("url", ["https://Example.COM./pricing?x=1", "https://example.com\u3002/pricing?x=1",
                                 "https://example.com\uff0e/pricing?x=1", "https://example.com\uff61/pricing?x=1"])
def test_a_trailing_dot_is_the_same_host_for_the_gate_and_the_proxy(url):
    t = capture.check_url(url)
    assert t["host"] == "example.com" and t["url"] == "https://example.com/pricing?x=1"


@pytest.mark.parametrize("bad", ["http://./", "https://com/", "http://intranet/", "https://example..com/"])
def test_single_label_and_empty_label_hosts_are_no_website(bad):
    with pytest.raises(capture.CaptureRefused):
        capture.check_url(bad)


def test_a_reported_host_prefix_never_narrows_the_neighbour_refusal(monkeypatch):
    class R:
        stdout = json.dumps([{"addr_info": [{"local": "2a01:4f8:1:2::5", "prefixlen": 128},
                                            {"local": "5.9.10.7", "prefixlen": 32}]}])
    monkeypatch.setattr(capture.shutil, "which", lambda name: "/sbin/ip" if name == "ip" else None)
    monkeypatch.setattr(capture._dl, "run_process", lambda *a, **k: R())
    monkeypatch.setattr(capture, "_udp_local", lambda probe, fam: None)
    scope = capture.own_scope()
    for addr in ("2a01:4f8:1:2::1", "2a01:4f8:1:2::6", "2a01:4f8:1:3::9", "5.9.10.1", "::ffff:5.9.10.8"):
        assert capture.address_verdict(ipaddress.ip_address(addr), scope), addr
    assert capture.address_verdict(ipaddress.ip_address("2a01:4f8:2::1"), scope) is None  # outside the /56


@pytest.mark.parametrize("addr,reason", [
    ("2a00:1450:4001:80b::99", "own_network"),     # a neighbour in the host's own /64
    ("::ffff:0:7f00:1", "embedded_v4"),            # SIIT form of 127.0.0.1
    ("fec0::1", "refused_range"),                  # deprecated site-local
    ("2001:20::1", "refused_range"),               # ORCHIDv2
    ("192.88.99.1", "refused_range"),              # 6to4 relay anycast
])
def test_on_link_neighbours_and_odd_ranges_are_refused(addr, reason):
    own = {ipaddress.ip_address("2a00:1450:4001:80b::1"), ipaddress.ip_network("2a00:1450:4001:80b::/64")}
    got = capture.address_verdict(ipaddress.ip_address(addr), own)
    assert got and got.startswith(reason), got
    assert capture.address_verdict(ipaddress.ip_address("2a00:1450:4001:80c::1"), own) is None


def test_own_global_addresses_carry_their_on_link_network():
    addrs, nets = capture.own_addresses(), capture.own_networks()
    assert all(isinstance(a, (ipaddress.IPv4Address, ipaddress.IPv6Address)) for a in addrs)
    for a in [x for x in addrs if x.is_global]:
        assert any(n.version == a.version and a in n for n in nets), a


@needs_chrome
def test_a_failed_capture_holds_its_slot_until_the_answer_instant(tmp_path):
    """Polling 'busy' must not reveal how long the worker ran: the slot is held until fail_hold_until."""
    hold = time.monotonic() + 6.0
    box = {}
    th = threading.Thread(target=lambda: box.update(r=capture.capture_url(
        "http://capture-hold-probe.invalid/", tenant="hold_t", fail_hold_until=hold, work_dir=str(tmp_path))))
    th.start()
    busy_seen_late = False
    while th.is_alive():
        if time.monotonic() > hold - 1.0:
            if not capture._take_slot("hold_t"):
                busy_seen_late = True
            else:
                capture._give_slot("hold_t")
            break
        time.sleep(0.1)
    th.join(30)
    assert box["r"]["ok"] is False
    assert time.monotonic() >= hold - 0.05
    assert busy_seen_late, "the slot was free before the answer instant"


def test_a_top_frame_navigation_between_the_checks_voids_the_capture():
    import queue
    class Q:
        events = queue.Queue()
    for ev in ({"sessionId": "s", "method": "Page.frameNavigated", "params": {"frame": {"id": "c", "parentId": "t"}}},
               {"sessionId": "x", "method": "Page.frameNavigated", "params": {"frame": {"id": "t"}}}):
        Q.events.put(ev)
    assert capture._top_frame_navigated(Q, "s") is False  # a child frame / another session
    Q.events.put({"sessionId": "s", "method": "Page.navigatedWithinDocument", "params": {"frameId": "t"}})
    assert capture._top_frame_navigated(Q, "s") is True


def test_same_site_is_the_host_or_a_dot_bounded_sub_or_parent_domain():
    assert capture.same_site("www.acme.com", "acme.com") and capture.same_site("acme.com", "www.acme.com")
    assert capture.same_site("ACME.com.", "acme.com")
    assert not capture.same_site("evilacme.com", "acme.com") and not capture.same_site("acme.com.evil.org", "acme.com")
    assert not capture.same_site("other.org", "acme.com")


@needs_chrome
@pytest.mark.parametrize("page,ok", [("/to_www", True), ("/offsite", False)])
def test_a_redirect_to_another_site_is_no_asset_even_when_the_rules_allow_it(stub, canary, page, ok, tmp_path):
    """Review 2 (B): the egress rules decide what may LOAD; what is CAPTURED must stay on the named site."""
    srv, fport = _fixture_server(canary.port, 9)
    px = OfflineProxy(named_hosts=["origin.test"], ports=[fport], resolver=_stub_resolver(stub.port),
                      fixture_port=fport, egress=ALLOW_ALL)
    px.extra_fixture_hosts = {"www.origin.test", "other.test"}
    px.start()
    try:
        res = capture.run_capture(f"http://origin.test:{fport}{page}", viewport="desktop", work_dir=str(tmp_path),
                                  proxy=px, chrome=CHROME, deadline_s=15)
    finally:
        px.stop()
        srv.shutdown()
    target = "www.origin.test" if page == "/to_www" else "other.test"
    assert px.connected(target, fport), px.log  # the redirect target really loaded through the proxy
    assert res["ok"] is ok, res
    if ok:
        assert res["final_url"] == f"http://www.origin.test:{fport}/plain"


def test_own_addresses_read_macos_ifconfig_with_prefixes(monkeypatch):
    """The macOS/BSD path: no ``ip``, ``ifconfig -a`` output with prefixlen / hex netmask."""
    out = """en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
	inet6 fe80::1c2b:3d4e:5f60:7182%en0 prefixlen 64 secured scopeid 0x4
	inet6 2a02:8070:1:2:a:b:c:d prefixlen 64 autoconf secured
	inet 203.0.113.7 netmask 0xffffff00 broadcast 203.0.113.255
lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
	inet 127.0.0.1 netmask 0xff000000
"""
    class R:
        stdout = out
    monkeypatch.setattr(capture.shutil, "which", lambda name: "/sbin/ifconfig" if name == "ifconfig" else None)
    monkeypatch.setattr(capture._dl, "run_process", lambda *a, **k: R())
    monkeypatch.setattr(capture, "_udp_local", lambda probe, fam: None)
    got = capture.own_scope()
    assert ipaddress.ip_address("2a02:8070:1:2:a:b:c:d") in capture.own_addresses()
    assert ipaddress.ip_network("2a02:8070:1::/56") in capture.own_networks()  # /64 reported, /56 refused
    assert ipaddress.ip_network("203.0.113.0/24") in got or ipaddress.ip_address("203.0.113.7") in got
    assert capture.address_verdict(ipaddress.ip_address("2a02:8070:1:2::1"), got) == "own_network"


def test_host_support_names_why_a_host_cannot_capture(monkeypatch):
    if CHROME and hasattr(os, "posix_spawn"):
        assert capture.host_support() is None
    monkeypatch.setattr(capture, "find_browser", lambda: None)
    assert capture.host_support() == "no_browser"
    monkeypatch.delattr(capture.os, "posix_spawn")
    assert capture.host_support() == "unsupported"
