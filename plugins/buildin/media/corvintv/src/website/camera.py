"""One global camera path for a website tour.

The hand-made tours eased every station on its own, so the camera stood still at each station (stop and go) and
``scrollTo`` snapped to device pixels (uneven 0/1-pixel steps on a slow move). Here the whole tour has ONE curve:
a monotone cubic Hermite interpolation (PCHIP, Fritsch-Butland slopes) through knots ``(t, y)``. It is C1 (no
jump in speed), never overshoots a knot, and stands still only where two knots share the same ``y`` (a wanted
hold). A move is capped at ``V_MAX`` px/s: a long way simply starts earlier. The sub-pixel part of a position is
handed to the cropper (``snap``) so a slow move is smooth too.

Pure functions, no browser: the properties are tested directly (``tests/test_website_camera.py``).
Python 3.9 compatible.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

V_MAX = 900.0          # css px per second, the fastest the camera may move
RUN_UP_S = 0.8         # a move across a scene boundary starts this long BEFORE the first sentence
ARRIVE_MAX_S = 2.8     # ... and ends at the latest this long after it
ARRIVE_FRAC = 0.35     # ... or after this share of the time to the next stop, whichever is shorter
MIN_SEG_S = 0.3        # two moves never overlap closer than this
PEAK_FACTOR = 1.5      # a Hermite move with zero end speed peaks at 1.5 x distance / time


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


class Pchip:
    """Monotone piecewise cubic Hermite through ``(xs, ys)``; ``xs`` strictly increasing, at least two knots."""

    def __init__(self, xs: Sequence[float], ys: Sequence[float]):
        if len(xs) != len(ys) or len(xs) < 2:
            raise ValueError("a camera path needs at least two knots")
        if any(b <= a for a, b in zip(xs, xs[1:])):
            raise ValueError("knot times must be strictly increasing")
        self.x = [float(v) for v in xs]
        self.y = [float(v) for v in ys]
        h = [b - a for a, b in zip(self.x, self.x[1:])]
        d = [(self.y[i + 1] - self.y[i]) / h[i] for i in range(len(h))]
        n = len(self.x)
        m = [0.0] * n
        if n == 2:
            m[0] = m[1] = d[0]
        else:
            for i in range(1, n - 1):
                if d[i - 1] * d[i] <= 0:
                    m[i] = 0.0
                else:
                    w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
                    m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
            m[0] = self._end(h[0], h[1], d[0], d[1])
            m[-1] = self._end(h[-1], h[-2], d[-1], d[-2])
        self.m = m
        self._h = h

    @staticmethod
    def _end(h0: float, h1: float, d0: float, d1: float) -> float:
        s = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
        if _sign(s) != _sign(d0):
            return 0.0
        if _sign(d0) != _sign(d1) and abs(s) > 3 * abs(d0):
            return 3 * d0
        return s

    def _seg(self, t: float) -> int:
        lo, hi = 0, len(self.x) - 2
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.x[mid] <= t:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def __call__(self, t: float) -> float:
        if t <= self.x[0]:
            return self.y[0]
        if t >= self.x[-1]:
            return self.y[-1]
        i = self._seg(t)
        h = self._h[i]
        u = (t - self.x[i]) / h
        u2, u3 = u * u, u * u * u
        return ((2 * u3 - 3 * u2 + 1) * self.y[i] + (u3 - 2 * u2 + u) * h * self.m[i]
                + (-2 * u3 + 3 * u2) * self.y[i + 1] + (u3 - u2) * h * self.m[i + 1])

    def speed(self, t: float) -> float:
        """dy/dt in px per second."""
        if t <= self.x[0] or t >= self.x[-1]:
            return 0.0
        i = self._seg(t)
        h = self._h[i]
        u = (t - self.x[i]) / h
        u2 = u * u
        return (((6 * u2 - 6 * u) / h) * self.y[i] + (3 * u2 - 4 * u + 1) * self.m[i]
                + ((-6 * u2 + 6 * u) / h) * self.y[i + 1] + (3 * u2 - 2 * u) * self.m[i + 1])


Stop = Tuple[float, float, Optional[float]]  # (time the camera should start arriving, y, arrival time or None = automatic)


def build_knots(stops: Sequence[Stop], total_s: float, *, v_max: float = V_MAX) -> Tuple[List[Tuple[float, float]], Dict[str, Any]]:
    """Knots for ``Pchip`` from the tour's stops (sorted by time). Returns ``(knots, info)``; ``info["late"]`` counts moves
    that could not stay under ``v_max`` because the previous move left no room (reported, never hidden)."""
    stops = sorted(((float(t), float(y), a) for t, y, a in stops), key=lambda s: s[0])
    if not stops:
        raise ValueError("a camera path needs a stop")
    knots: List[Tuple[float, float]] = [(0.0, stops[0][1])]
    last_t, last_y = 0.0, stops[0][1]
    late = 0
    for i in range(1, len(stops)):
        t, y, arrive = stops[i]
        if abs(y - last_y) < 0.5:
            continue  # same place: the camera holds
        nxt = stops[i + 1][0] if i + 1 < len(stops) else total_s
        arrive_t = t + (arrive if arrive is not None else min(ARRIVE_MAX_S, ARRIVE_FRAC * max(0.0, nxt - t)))
        need = PEAK_FACTOR * abs(y - last_y) / v_max
        depart = min(t - RUN_UP_S, arrive_t - need)
        depart = max(depart, last_t + MIN_SEG_S)
        if arrive_t - depart < need:
            arrive_t = depart + need
            late += 1
        if depart > last_t:
            knots.append((depart, last_y))
        knots.append((arrive_t, y))
        last_t, last_y = arrive_t, y
    if total_s > last_t:
        knots.append((total_s, last_y))
    else:
        knots.append((last_t + 0.5, last_y))
    # strictly increasing, collapse equal times
    out: List[Tuple[float, float]] = []
    for t, y in knots:
        if out and t <= out[-1][0] + 1e-6:
            continue
        out.append((t, y))
    return out, {"late": late, "knots": len(out)}


def metrics(cam: Pchip, fps: int, total_s: float) -> Dict[str, float]:
    """Measured smoothness of the sampled path (what the video really shows): the largest jump between two frames
    (``max_step_px``, css px), the largest change of that jump from one frame to the next (``max_accel_px``) and
    the peak speed."""
    n = max(2, int(total_s * fps))
    ys = [cam(i / fps) for i in range(n + 1)]
    steps = [b - a for a, b in zip(ys, ys[1:])]
    accel = [abs(b - a) for a, b in zip(steps, steps[1:])]
    return {"max_step_px": round(max((abs(s) for s in steps), default=0.0), 3),
            "max_accel_px": round(max(accel, default=0.0), 3),
            "peak_speed_px_s": round(max((abs(s) for s in steps), default=0.0) * fps, 1),
            "distance_px": round(sum(abs(s) for s in steps), 1)}


def snap(y_css: float, dsf: float) -> Tuple[float, float]:
    """``(scroll position to ask the browser for, rest in DEVICE pixels)``: the browser scrolls whole device pixels,
    the rest (0 <= r < 1) is applied when cropping so the picture still moves by the exact fraction."""
    dev = y_css * dsf
    whole = math.floor(dev + 1e-9)
    return whole / dsf, dev - whole
