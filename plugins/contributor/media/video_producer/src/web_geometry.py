"""Pure geometry for the web-slide charts (ADR-2238).

The maths D3 would do in a browser — "nice" axis ticks, monotone cubic
interpolation, layered graph layout — computed in Python, so a slide stays a
static document: no script runs at render time, and the frames stay
deterministic under timeline seeking.
"""

from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple


def nice_ticks(lo: float, hi: float, count: int = 5) -> List[float]:
    """Round tick values covering [lo, hi], step 1/2/5 x 10^k (d3.ticks + nice)."""
    if hi < lo:
        lo, hi = hi, lo
    if hi == lo:
        hi = lo + (abs(lo) or 1.0)
    raw = (hi - lo) / max(count, 1)
    mag = 10 ** math.floor(math.log10(raw))
    err = raw / mag
    step = (10 if err >= math.sqrt(50) else 5 if err >= math.sqrt(10) else 2 if err >= math.sqrt(2) else 1) * mag
    start = math.floor(lo / step + 1e-9) * step
    stop = math.ceil(hi / step - 1e-9) * step
    n = int(round((stop - start) / step))
    return [round(start + i * step, 10) + 0.0 for i in range(n + 1)]


def _sign(x: float) -> int:
    return -1 if x < 0 else 1


def monotone_path(points: Sequence[Tuple[float, float]]) -> str:
    """SVG path through ``points`` (x strictly increasing) using monotone cubic
    interpolation — d3.curveMonotoneX: no overshoot between data points."""
    n = len(points)
    if n < 2:
        raise ValueError("a curve needs at least two points")
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    if n == 2:
        return f"M{xs[0]:.1f},{ys[0]:.1f}L{xs[1]:.1f},{ys[1]:.1f}"
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    s = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    for i in range(1, n - 1):
        p = (s[i - 1] * h[i] + s[i] * h[i - 1]) / (h[i - 1] + h[i])
        m[i] = (_sign(s[i - 1]) + _sign(s[i])) * min(abs(s[i - 1]), abs(s[i]), 0.5 * abs(p)) or 0.0
    m[0] = (3 * s[0] - m[1]) / 2
    m[-1] = (3 * s[-1] - m[-2]) / 2
    out = [f"M{xs[0]:.1f},{ys[0]:.1f}"]
    for i in range(n - 1):
        dx = h[i] / 3
        out.append(
            f"C{xs[i] + dx:.1f},{ys[i] + dx * m[i]:.1f} "
            f"{xs[i + 1] - dx:.1f},{ys[i + 1] - dx * m[i + 1]:.1f} "
            f"{xs[i + 1]:.1f},{ys[i + 1]:.1f}"
        )
    return "".join(out)


def layer_dag(ids: Sequence[str], edges: Sequence[Tuple[str, str]]) -> Dict[str, int]:
    """Longest-path layering of a DAG: every edge points to a strictly higher layer.
    Raises ValueError on a cycle."""
    preds: Dict[str, List[str]] = {i: [] for i in ids}
    succs: Dict[str, List[str]] = {i: [] for i in ids}
    for a, b in edges:
        preds[b].append(a)
        succs[a].append(b)
    indeg = {i: len(preds[i]) for i in ids}
    queue = [i for i in ids if indeg[i] == 0]
    layer = {i: 0 for i in ids}
    seen = 0
    while queue:
        node = queue.pop(0)
        seen += 1
        for nxt in succs[node]:
            layer[nxt] = max(layer[nxt], layer[node] + 1)
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if seen != len(ids):
        raise ValueError("the graph has a cycle (use the 'cycle' template for loops)")
    return layer


def order_layers(ids: Sequence[str], edges: Sequence[Tuple[str, str]], layer: Dict[str, int]) -> List[List[str]]:
    """Nodes grouped by layer; each layer after the first sorted by the mean
    position of its predecessors (one barycentre sweep — fewer crossings)."""
    n_layers = max(layer.values()) + 1
    groups: List[List[str]] = [[i for i in ids if layer[i] == k] for k in range(n_layers)]
    preds: Dict[str, List[str]] = {i: [] for i in ids}
    for a, b in edges:
        preds[b].append(a)
    for k in range(1, n_layers):
        pos = {node: j / max(len(g) - 1, 1) for g in groups[:k] for j, node in enumerate(g)}
        original = {node: j for j, node in enumerate(groups[k])}

        def key(node: str) -> Tuple[float, int]:
            ps = [pos[p] for p in preds[node] if p in pos]
            return (sum(ps) / len(ps) if ps else 0.5, original[node])

        groups[k].sort(key=key)
    return groups


def polar(cx: float, cy: float, r: float, angle: float) -> Tuple[float, float]:
    return cx + r * math.cos(angle), cy + r * math.sin(angle)
