"""Hostile local DNS resolver stub for the capture corpus (ported from spike_capture_policy/dnsstub.py,
T-0112). Stdlib only. Binds an ephemeral UDP port on 127.0.0.1; every answer has TTL 0.

  local.test A 127.0.0.1 | v6local.test AAAA ::1 | meta.test A 169.254.169.254
  cgnat.test A 100.64.0.1 | nat64.test AAAA 64:ff9b::7f00:1
  mixed.test A <public> + A 127.0.0.1  (one bad record among good ones)
  rebind.test A alternates <public> / 127.0.0.1 on every query (classic rebinding)
"""
from __future__ import annotations

import ipaddress
import socket
import struct
import threading
from typing import List

PUBLIC = "93.184.215.14"


class Stub:
    def __init__(self):
        self.queries = 0
        self._rebind = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def records(self, name: str, qtype: int) -> List[str]:
        n = name.lower().rstrip(".")
        a = {"local.test": ["127.0.0.1"], "meta.test": ["169.254.169.254"], "cgnat.test": ["100.64.0.1"],
             "mixed.test": [PUBLIC, "127.0.0.1"]}
        aaaa = {"v6local.test": ["::1"], "nat64.test": ["64:ff9b::7f00:1"]}
        if n == "rebind.test" and qtype == 1:
            self._rebind += 1
            return [PUBLIC if self._rebind % 2 else "127.0.0.1"]
        return (a if qtype == 1 else aaaa if qtype == 28 else {}).get(n, [])

    def _serve(self):
        while True:
            try:
                data, peer = self.sock.recvfrom(512)
            except OSError:
                return
            self.queries += 1
            try:
                qid = data[:2]
                i, labels = 12, []
                while data[i]:
                    labels.append(data[i + 1:i + 1 + data[i]].decode())
                    i += 1 + data[i]
                qtype = struct.unpack(">H", data[i + 1:i + 3])[0]
                question = data[12:i + 5]
                ans = b""
                recs = self.records(".".join(labels), qtype)
                for r in recs:
                    rd = ipaddress.ip_address(r).packed
                    ans += b"\xc0\x0c" + struct.pack(">HHIH", qtype, 1, 0, len(rd)) + rd
                hdr = qid + struct.pack(">HHHHH", 0x8180, 1, len(recs), 0, 0)
                self.sock.sendto(hdr + question + ans, peer)
            except Exception:  # noqa: BLE001
                pass


def query(name: str, qtype: int, port: int, timeout: float = 0.3) -> List[str]:
    q = struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
    for lab in name.rstrip(".").split("."):
        q += bytes([len(lab)]) + lab.encode()
    q += b"\x00" + struct.pack(">HH", qtype, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(q, ("127.0.0.1", port))
        data = s.recv(512)
    finally:
        s.close()
    an = struct.unpack(">H", data[6:8])[0]
    i = len(q)
    out = []
    for _ in range(an):
        i += 2
        _t, _c, _ttl, ln = struct.unpack(">HHIH", data[i:i + 10])
        i += 10
        out.append(str(ipaddress.ip_address(data[i:i + ln])))
        i += ln
    return out
