"""Address policy for the capture proxy (SPIKE, ADR-2249 D4 / T-0112).

Allow-by-global: an address is connectable only if it is globally routable AFTER every
transition form is unwrapped, is not multicast, and is not one of this host's own interface
addresses. ``ipaddress.is_global`` alone is NOT that (measured on Python 3.11.15): it returns
True for 224.0.0.1, 239.255.255.250, ff05::1:3, 64:ff9b::7f00:1 (NAT64 of loopback),
::127.0.0.1 (v4-compatible loopback) and the host's own global IPv6 address.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import subprocess
from typing import Iterable, Optional, Set

NAT64 = [ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48")]
SIX_TO_FOUR = ipaddress.ip_network("2002::/16")
TEREDO = ipaddress.ip_network("2001::/32")
V4_COMPAT = ipaddress.ip_network("::/96")
REFUSED_NAMES = {"localhost", "metadata.google.internal", "metadata", "instance-data"}


def own_addresses() -> Set[ipaddress._BaseAddress]:
    """Every address bound to an interface of this host (spike: Linux `ip -j addr`)."""
    out: Set[ipaddress._BaseAddress] = set()
    try:
        data = json.loads(subprocess.run(["ip", "-j", "addr"], capture_output=True, text=True, timeout=5).stdout)
        for itf in data:
            for a in itf.get("addr_info", []):
                out.add(ipaddress.ip_address(a["local"].split("%")[0]))
    except Exception:
        pass
    return out


def parse_ip_literal(host: str) -> Optional[ipaddress._BaseAddress]:
    """IP literal in any textual encoding (127.1, hex, octal, decimal, bracketed v6), else None."""
    h = host.strip().rstrip(".")
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    if "%" in h:
        raise ValueError("zone id")
    try:
        return ipaddress.ip_address(h)
    except ValueError:
        pass
    try:  # inet_aton accepts every legacy IPv4 form the URL parser might pass through
        if all(c in "0123456789abcdefxABCDEFX." for c in h) and h:
            return ipaddress.ip_address(socket.inet_aton(h))
    except OSError:
        pass
    return None


def _embedded_v4(ip: ipaddress.IPv6Address) -> Iterable[ipaddress.IPv4Address]:
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


def address_verdict(ip, own: Set, mode: str = "strict") -> Optional[str]:
    """None = allowed, else the refusal reason. mode: strict | naive (is_global only) | permissive."""
    if mode == "permissive":
        return None
    if mode == "naive":
        return None if ip.is_global else "not_global"
    if ip in own:
        return "own_interface"
    if ip.version == 6:
        for v4 in _embedded_v4(ip):
            r = address_verdict(v4, own, mode)
            if r:
                return "embedded_v4:" + r
        if any(ip in n for n in NAT64) or ip in SIX_TO_FOUR or ip in TEREDO or ip in V4_COMPAT:
            return "transition_form"  # v1: no transition-mechanism destinations at all
    if ip.is_multicast:
        return "multicast"
    if not ip.is_global:
        return "not_global"
    return None


def name_verdict(host: str, console_names: Set[str]) -> Optional[str]:
    h = host.lower().rstrip(".")
    if h in REFUSED_NAMES or h.endswith(".localhost") or h in console_names:
        return "refused_name"
    return None
