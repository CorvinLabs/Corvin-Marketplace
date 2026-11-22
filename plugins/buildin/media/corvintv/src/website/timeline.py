"""Spoken lengths -> scene times (one timeline for every language: ADR-2311's rule).

A scene lasts as long as the SLOWEST language needs; the other language keeps its natural rhythm and the slack goes
mostly between its sentences (70 %), a smaller part to lead-in and tail (15 % each), so no boundary has dead air.
The picture is language independent; the sound is per language. ``at_avg`` (mean over the languages) is what the
picture follows (focus, effects), so both languages see the same video.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

LEAD_S, GAP_S, TAIL_S = 0.6, 0.7, 1.0


def build(scenes: Sequence[Dict[str, Any]], durs: Dict[Tuple[int, int, str], float], langs: Sequence[str],
          fps: int) -> Dict[str, Any]:
    """``scenes[i]["sentences"]`` = list of sentence dicts; ``durs[(i, k, lang)]`` = seconds. Returns
    ``{"total_s", "fps", "scenes": [{"id","start","dur","sentences":[{"k","at":{lang},"dur":{lang},"at_avg"}]}]}``."""
    t0 = 0.0
    out: List[Dict[str, Any]] = []
    for i, sc in enumerate(scenes):
        n = len(sc["sentences"])
        need = {lg: LEAD_S + sum(durs[(i, k, lg)] + GAP_S for k in range(n)) + TAIL_S for lg in langs}
        dur = round(max(need.values()), 2)
        entry: Dict[str, Any] = {"id": str(sc["id"]), "start": round(t0, 2), "dur": dur, "sentences": []}
        per_lang: Dict[str, List[float]] = {}
        for lg in langs:
            slack = dur - need[lg]
            inner = (slack * 0.7 / (n - 1)) if n > 1 else 0.0
            t = LEAD_S + slack * 0.15
            ats = []
            for k in range(n):
                ats.append(round(entry["start"] + t, 3))
                t += durs[(i, k, lg)] + GAP_S + inner
            per_lang[lg] = ats
        for k in range(n):
            entry["sentences"].append({
                "k": k, "at": {lg: per_lang[lg][k] for lg in langs}, "dur": {lg: round(durs[(i, k, lg)], 3) for lg in langs},
                "at_avg": round(sum(per_lang[lg][k] for lg in langs) / len(langs), 3)})
        out.append(entry)
        t0 += dur
    total = round(t0, 2)
    return {"total_s": total, "fps": int(fps), "frames": max(1, round(total * fps)), "scenes": out}
