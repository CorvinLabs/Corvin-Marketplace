"""T-0112 measurement harness (SPIKE). Run: python3 -I run_spike.py  (from any cwd; adds own dir to path)

Measures, without touching any real website:
  1. hostile corpus (>= 80) via curl through the proxy (absolute-form HTTP + CONNECT)
     -> proxy.outbound must stay EMPTY and the canary listeners (every local address, port P)
        must record ZERO accepted connections;
  2. browser corpus (redirect, meta refresh, JS nav, iframe, img, fetch, WebSocket, service
     worker, rebinding) in headless Chrome pinned to the proxy, with Chrome's own resolver
     disabled (--host-resolver-rules MAP * ~NOTFOUND) so no name resolves outside the proxy;
  3. timing: refusal vs dns-empty vs connect-refused vs connect-timeout (same bytes, same instant);
  4. killpg: Chrome in its own session, killed at a deadline, no survivors, no zombies.
The ONLY non-policy connection is the fixture origin `origin.test`, pinned by the harness to a
loopback fixture server (it hosts the hostile pages); it is excluded from the hostile count.
"""
from __future__ import annotations

import http.server
import json
import os
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnsstub  # noqa: E402
import policy  # noqa: E402
import proxy as proxymod  # noqa: E402

CANARY_HITS: list = []


def canary(port: int):
    """Listen on every v4 + v6 address at `port`; record every accepted connection."""
    socks = []
    for fam, addr in ((socket.AF_INET, "0.0.0.0"), (socket.AF_INET6, "::")):
        s = socket.socket(fam, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if fam == socket.AF_INET6:
            s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        s.bind((addr, port))
        s.listen(64)
        socks.append(s)

        def loop(s=s):
            while True:
                c, peer = s.accept()
                CANARY_HITS.append(peer)
                c.close()
        threading.Thread(target=loop, daemon=True).start()
    return socks


def fixture_server(canary_port: int) -> int:
    P = canary_port
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
        "/hang": None,
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
            if p == "/hang":
                time.sleep(60)
                return
            body = (pages.get(p) or "ok").encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript" if p.endswith(".js") else "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1], list(pages)


class HarnessProxy(proxymod.CaptureProxy):
    """Strict proxy + ONE harness pin: origin.test -> loopback fixture (not counted as hostile)."""
    def __init__(self, fixture_port, **kw):
        super().__init__(**kw)
        self.fixture_port = fixture_port
        self.offline_dns_blocked: list = []   # real-DNS names the harness refused to resolve
        self.global_allowed: list = []        # policy said OK (global) -> harness withholds the connect

    async def _resolve(self, host):
        if not host.endswith(".test"):     # OFFLINE: no real DNS query ever leaves this host
            self.offline_dns_blocked.append(host)
            raise OSError("offline harness")
        return await super()._resolve(host)

    async def decide(self, host, port):
        if host.lower().rstrip(".") == "origin.test" and port == self.fixture_port:
            return policy.ipaddress.ip_address("127.0.0.1"), "harness_fixture"
        ip, why = await super().decide(host, port)
        if ip is not None:                  # OFFLINE: a policy-allowed global address is not dialled
            self.global_allowed.append((host, str(ip), port))
            return None, "offline_global_withheld"
        return ip, why


def corpus(P: int):
    own = sorted({str(a) for a in policy.own_addresses()})
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


def curl(proxy_port, url):
    t0 = time.monotonic()
    r = subprocess.run(["curl", "-s", "-k", "-g", "--max-time", "5", "-x", f"http://127.0.0.1:{proxy_port}",
                        "-o", "-", "-w", "\n%{http_code}|%{http_connect}", url], capture_output=True, text=True)
    return time.monotonic() - t0, r.stdout


def raw_req(proxy_port, line):
    """Raw request -> (elapsed, response bytes)."""
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


def chrome(proxy_port, url, udd, deadline, extra=()):
    cmd = ["google-chrome", "--headless=new", f"--user-data-dir={udd}", "--no-first-run",
           "--disable-background-networking", "--disable-component-update", "--disable-sync",
           "--disable-features=DnsOverHttps,NetworkPrediction,Translate,OptimizationHints,MediaRouter",
           "--no-default-browser-check", "--disable-domain-reliability", "--metrics-recording-only",
           f"--proxy-server=http://127.0.0.1:{proxy_port}", "--proxy-bypass-list=<-loopback>",
           "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1", "--disable-quic", "--ignore-certificate-errors",
           *extra, "--virtual-time-budget=4000", "--dump-dom", url]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    killed = False
    try:
        p.wait(timeout=deadline)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        killed = True
        p.wait()
    time.sleep(0.5)
    ps = subprocess.run(["ps", "-eo", "pid,pgid,stat,args"], capture_output=True, text=True).stdout
    survivors = [l for l in ps.splitlines() if udd in l]
    zombies = [l for l in ps.splitlines() if udd in l and " Z" in l]
    return {"killed_by_killpg": killed, "survivors": len(survivors), "zombies": len(zombies), "pgid": p.pid}


def main():
    P = 18000 + os.getpid() % 1000
    canary(P)
    stub = dnsstub.Stub(port=15353)
    fport, pages = fixture_server(P)
    px = HarnessProxy(fport, mode="strict", stub_port=15353)
    pport = px.start()
    res = {"canary_port": P, "proxy_port": pport}

    # 1. curl corpus
    urls = corpus(P)
    rows = []
    lock = threading.Lock()

    def one(u):
        dt, out = curl(pport, u)
        with lock:
            rows.append({"url": u, "t": round(dt, 4), "tail": out.strip().splitlines()[-1] if out.strip() else ""})
    ths = [threading.Thread(target=one, args=(u,)) for u in urls]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    res["curl_corpus_n"] = len(urls)

    # 2. browser corpus
    udd_root = tempfile.mkdtemp(prefix="t0112-")
    br = {}
    for page in [p for p in pages if p not in ("/sw.js", "/hang")]:
        udd = os.path.join(udd_root, page.strip("/"))
        extra = [f"--unsafely-treat-insecure-origin-as-secure=http://origin.test:{fport}"] if page == "/sw" else []
        br[page] = chrome(pport, f"http://origin.test:{fport}{page}", udd, 15, extra)
    res["browser_corpus_n"] = len(br)
    res["browser"] = br

    # 4. killpg on deadline (page that hangs)
    res["killpg"] = chrome(pport, f"http://origin.test:{fport}/hang", os.path.join(udd_root, "hang"), 3)

    hostile_out = [o for o in px.outbound if not (o == ("127.0.0.1", fport))]
    res["proxy_log_n"] = len(px.log)
    res["proxy_connected_hostile"] = [r for r in px.log if r.get("verdict") == "connected" and r.get("reason") != "harness_fixture"]
    res["proxy_outbound_hostile"] = hostile_out
    res["canary_hits"] = CANARY_HITS[:]
    res["global_allowed_withheld"] = px.global_allowed
    res["offline_dns_blocked"] = sorted(set(px.offline_dns_blocked))
    res["browser_hostile_lines"] = [ (r.get("line"), r.get("reason")) for r in px.log[len(urls)-1:] if r.get("reason") != "harness_fixture"]
    res["refusal_reasons"] = sorted({r.get("reason", "").split(":")[0] for r in px.log})
    res["dns_stub_queries"] = stub.queries
    res["curl_rows_not_502"] = [r for r in rows if not r["tail"].startswith("502") and "|502" not in r["tail"] and r["tail"] != "000|000"]
    res["curl_rejected_locally"] = [r["url"] for r in rows if r["tail"] == "000|000"]  # curl never sent it

    # 3. timing classes (sequential, 10 each)
    perm = proxymod.CaptureProxy(mode="permissive", stub_port=15353)
    perm_port = perm.start()
    closed = socket.socket(); closed.bind(("127.0.0.1", 0)); cport = closed.getsockname()[1]; closed.close()
    classes = {
        "refused_loopback": (pport, f"GET http://127.0.0.1:{P}/ HTTP/1.1"),
        "refused_connect_meta": (pport, f"CONNECT 169.254.169.254:{P} HTTP/1.1"),
        "dns_empty": (pport, f"GET http://nx.test:{P}/ HTTP/1.1"),
        "unreachable_conn_refused": (perm_port, f"GET http://127.0.0.1:{cport}/ HTTP/1.1"),
        "unreachable_conn_timeout": (perm_port, "GET http://10.255.255.1:9/ HTTP/1.1"),
    }
    timing, bodies = {}, {}
    for name, (port, line) in classes.items():
        ts = []
        for _ in range(10):
            dt, data = raw_req(port, line)
            ts.append(dt)
            bodies.setdefault(name, set()).add(data)
        timing[name] = {"median_ms": round(statistics.median(ts) * 1000, 2), "min_ms": round(min(ts) * 1000, 2),
                        "max_ms": round(max(ts) * 1000, 2)}
    res["timing"] = timing
    allb = set().union(*bodies.values())
    res["response_bytes_identical"] = len(allb) == 1
    meds = [v["median_ms"] for v in timing.values()]
    mins = [v["min_ms"] for v in timing.values()]
    maxs = [v["max_ms"] for v in timing.values()]
    res["timing_spread_ms"] = {"median_spread": round(max(meds) - min(meds), 2), "global_min": min(mins), "global_max": max(maxs)}
    res["perm_outbound"] = perm.outbound

    # verdict
    zero = not hostile_out and not res["proxy_connected_hostile"] and not CANARY_HITS and not res["curl_rows_not_502"]
    kp = res["killpg"]
    killok = kp["killed_by_killpg"] and kp["survivors"] == 0 and kp["zombies"] == 0 and all(b["survivors"] == 0 for b in br.values())
    timeok = res["response_bytes_identical"] and (max(maxs) - min(mins)) < 50
    res["checks"] = {"zero_reached": zero, "corpus_ge_80": len(urls) + len(br) >= 80, "killpg_ok": killok, "timing_ok": timeok}
    res["verdict"] = "GO" if all(res["checks"].values()) else "NO-GO"
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
