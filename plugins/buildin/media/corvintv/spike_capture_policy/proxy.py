"""Corvin-owned forward proxy for website capture (SPIKE, ADR-2249 D4 / T-0112).

One resolution per request, every resolved address validated (one bad record refuses the
whole name), connect to the PINNED validated IP. CONNECT (https, ws/wss) and absolute-form
HTTP are both handled here, so redirects and WebSockets cannot route around it.

Uniform failure: refusal, DNS failure, connect failure/timeout all answer the SAME bytes at
the SAME instant ``t0 + FLOOR_S``; resolve + connect are capped below the floor.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

import dnsstub
import policy

FLOOR_S = 2.0
RESOLVE_TIMEOUT_S = 0.4
CONNECT_TIMEOUT_S = 1.4
FAIL = (b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\nContent-Length: 32\r\n"
        b"Connection: close\r\n\r\nthis address cannot be captured\n")


class CaptureProxy:
    def __init__(self, mode: str = "strict", stub_port: int = 15353, console_names: Set[str] = frozenset()):
        self.mode = mode
        self.stub_port = stub_port
        self.console_names = set(console_names)
        self.own = policy.own_addresses()
        self.log: List[Dict] = []
        self.outbound: List[Tuple[str, int]] = []   # every TCP connect the proxy actually made
        self.port = 0
        self._lock = threading.Lock()

    # ---- decision -------------------------------------------------------------------------
    async def _resolve(self, host: str) -> List[ipaddress._BaseAddress]:
        loop = asyncio.get_running_loop()
        if host.endswith(".test"):
            got = []
            for qt in (1, 28):
                got += await loop.run_in_executor(None, dnsstub.query, host, qt, self.stub_port, RESOLVE_TIMEOUT_S / 2)
            return [ipaddress.ip_address(a) for a in got]
        infos = await asyncio.wait_for(loop.getaddrinfo(host, None, type=socket.SOCK_STREAM), RESOLVE_TIMEOUT_S)
        return [ipaddress.ip_address(i[4][0].split("%")[0]) for i in infos]

    async def decide(self, host: str, port: int) -> Tuple[Optional[ipaddress._BaseAddress], str]:
        if self.mode == "strict":
            r = policy.name_verdict(host, self.console_names)
            if r:
                return None, r
        try:
            lit = policy.parse_ip_literal(host)
        except ValueError as e:
            return None, "bad_host:" + str(e)
        try:
            addrs = [lit] if lit else await self._resolve(host.rstrip("."))
        except Exception as e:
            return None, "dns_fail:" + type(e).__name__
        if not addrs:
            return None, "dns_empty"
        for a in addrs:
            r = policy.address_verdict(a, self.own, self.mode)
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
        except Exception:
            pass
        finally:
            try:
                w.close()
            except Exception:
                pass

    async def _fail(self, w, t0):
        await asyncio.sleep(max(0.0, t0 + FLOOR_S - time.monotonic()))
        try:
            w.write(FAIL)
            await w.drain()
            w.close()
        except Exception:
            pass

    async def handle(self, cr, cw):
        t0 = time.monotonic()
        rec: Dict = {"t": time.time()}
        try:
            head = await asyncio.wait_for(cr.readuntil(b"\r\n\r\n"), 5)
        except Exception:
            cw.close()
            return
        line = head.split(b"\r\n", 1)[0].decode("latin-1")
        rec["line"] = line[:200]
        try:
            method, target, ver = line.split(" ")
            if method == "CONNECT":
                host, _, port = target.rpartition(":")
                port, rest = int(port), b""
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
        except Exception as e:
            rec.update(verdict="refused", reason="bad_request:" + str(e)[:60])
            self._record(rec)
            return await self._fail(cw, t0)
        ip, reason = await self.decide(host, port)
        rec.update(host=host, port=port, reason=reason)
        if ip is None:
            rec["verdict"] = "refused"
            self._record(rec)
            return await self._fail(cw, t0)
        try:
            with self._lock:
                self.outbound.append((str(ip), port))
            ur, uw = await asyncio.wait_for(asyncio.open_connection(str(ip), port), CONNECT_TIMEOUT_S)
        except Exception as e:
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
            srv = loop.run_until_complete(asyncio.start_server(self.handle, "127.0.0.1", 0))
            self.port = srv.sockets[0].getsockname()[1]
            self.loop = loop
            ready.set()
            loop.run_forever()

        threading.Thread(target=run, daemon=True).start()
        ready.wait(5)
        return self.port
