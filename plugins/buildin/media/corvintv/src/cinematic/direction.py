"""The screenplay of a cinematic video: prompt for the director, extraction and validation of its answer.

Pure functions, no I/O besides reading the bundled prompt and manual. The validator returns ALL findings at once so
one repair round can fix them; nothing from the model reaches the page except as JSON data (see ``stage``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence

HERE = Path(__file__).resolve().parent
LANGS_OK = ("de", "en", "es", "fr", "it", "pt", "nl", "pl", "sv", "da", "tr", "ja", "zh", "ko", "ru", "uk", "cs")
WORDS_PER_MINUTE = 130
MIN_MINUTES, MAX_MINUTES = 1, 30
MAX_ACTS = 40
MAX_ACTORS_PER_ACT = 60
MAX_TWEENS_PER_ACT = 400
MAX_BEAT_CHARS = 600
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,39}")

COMMON = {"id", "type", "x", "y", "s", "r", "o", "flip", "par", "z"}
PROPS: Dict[str, set] = {
    "sky": {"tone", "stars", "moon", "mx", "my", "ms", "phase"}, "sea": {"hy", "amp", "speed", "tone", "refl", "rx", "rcol"},
    "mist": {"a", "n", "speed", "color", "w"}, "particles": {"n", "w", "h", "color", "speed", "dir", "size", "a", "seed"},
    "grade": {"v", "tint", "ta"}, "lighthouse": {"power", "beam", "focus", "aim", "sweep", "sweepSpeed", "tint", "bcol", "dark"},
    "oracle": {"color", "glow", "calm", "speak"}, "figure": {"pose", "color"}, "ship": {"lit", "seed"},
    "rings": {"n", "color", "R", "speed", "a", "r0", "squash", "w", "phase"},
    "ribbon": {"x0", "y0", "x1", "y1", "p", "q", "color", "w", "seed", "wave", "a"},
    "flow": {"x0", "y0", "x1", "y1", "n", "color", "speed", "bend", "p"},
    "constellation": {"nodes", "links", "p", "lp", "hl", "dim", "size", "color"},
    "pages": {"n", "m", "targets"}, "arch": {"lit", "key", "R", "th"}, "gate": {"open", "kind", "color", "glow"},
    "token": {"shape", "hue", "glow", "seed"}, "lamps": {"states", "gap"}, "coin": {"spin", "shine"},
    "blueprint": {"kind", "p", "color"}, "compass": {"ang", "wobble", "glow"}, "pedestal": {"fill", "kind", "color"},
    "bubble": {"pop", "hue", "seed"}, "crystal": {"grow", "hue", "seed"},
    "gear": {"teeth", "R", "speed", "phase", "color", "warm"}, "terrain": {"p", "seed", "fog", "rot", "hiker"},
    "curve": {"w", "h", "p", "color"}, "cycle": {"R", "n", "lit", "color", "cols", "speed"},
    "pixelpic": {"w", "h", "lvl", "noise", "scan", "glow", "frame", "glowc"}, "tower": {"lit", "gap"},
    "tree": {"grow", "seed", "color"}, "fan": {"fold", "n"},
    "caption": {"text", "size", "color", "align", "p", "italic", "bold", "font", "lh"},
    "symbol": {"size", "p"}, "art": {"src", "w", "h", "p", "radius", "glow", "glowc"},
}
CAM = {"cx", "cy", "zoom", "rot"}
EASES = {"linear", "in", "out", "soft", "inOut", "smooth", "back", "drop", "step"}
AT = re.compile(r"^(b\d+|end)\s*([+-]\s*[\d.]+)?$")


class DirectionError(ValueError):
    """The screenplay is unusable; ``findings`` lists every problem found."""

    def __init__(self, findings: Sequence[str]):
        self.findings = list(findings)
        more = f" (+{len(self.findings) - 6} more)" if len(self.findings) > 6 else ""
        super().__init__("; ".join(self.findings[:6]) + more)


def library_text() -> str:
    return (HERE / "engine" / "LIBRARY.md").read_text(encoding="utf-8")


def clamp_minutes(minutes: Any) -> int:
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        m = 5
    return max(MIN_MINUTES, min(MAX_MINUTES, m))


def clean_langs(langs: Any) -> List[str]:
    out: List[str] = []
    for lang in (langs if isinstance(langs, (list, tuple)) else [langs]):
        code = str(lang or "").strip().lower()[:2]
        if code in LANGS_OK and code not in out:
            out.append(code)
    return out[:2] or ["en"]


def build_prompt(task: str, minutes: int, langs: Sequence[str], art_names: Sequence[str]) -> str:
    """The director prompt. The brief is inserted last and only once, so its text can never be re-expanded as a token."""
    minutes = clamp_minutes(minutes)
    langs = clean_langs(list(langs))
    acts = f"{max(3, round(minutes * 1.6))} to {max(5, round(minutes * 2.2))}"
    lang_ex = "{" + ", ".join(f'"{lg}": "..."' for lg in langs) + "}"
    text = (HERE / "prompt.md").read_text(encoding="utf-8")
    for key, val in (("{LANGS}", ", ".join(langs)), ("{WORDS}", str(minutes * WORDS_PER_MINUTE)),
                     ("{MINUTES}", str(minutes)), ("{ACTS}", acts), ("{LANG_EXAMPLE}", lang_ex),
                     ("{BEAT_EXAMPLE}", lang_ex),
                     ("{ART_NAMES}", ", ".join(art_names) if art_names else "none are supplied, so use no `art` figure"),
                     ("{LIBRARY}", library_text())):
        text = text.replace(key, val)
    return text.replace("{TASK}", task.strip()[:6000], 1)


def extract(raw: str) -> Dict[str, Any]:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0] if "\n" in s else s.strip("`")
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        raise DirectionError(["the answer contains no JSON object"])
    try:
        doc = json.loads(s[a:b + 1])
    except ValueError as e:
        raise DirectionError([f"the JSON does not parse: {e}"]) from None
    if not isinstance(doc, dict):
        raise DirectionError(["the JSON is not an object"])
    return doc


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check(doc: Dict[str, Any], minutes: int, langs: Sequence[str], art_names: Sequence[str]) -> List[str]:
    """All findings (empty list = valid). The word count is a soft band around the target length."""
    err: List[str] = []
    langs = clean_langs(list(langs))
    art = set(art_names)
    acts = doc.get("acts")
    if not isinstance(acts, list) or not acts:
        return ["`acts` must be a non-empty list"]
    if len(acts) > MAX_ACTS:
        err.append(f"{len(acts)} acts, at most {MAX_ACTS}")
    words = 0
    seen_act_ids = set()
    for a in acts[:MAX_ACTS]:
        if not isinstance(a, dict):
            err.append("an act is not an object")
            continue
        aid = str(a.get("id", "?"))
        if aid in seen_act_ids:
            err.append(f"duplicate act id {aid!r}")
        seen_act_ids.add(aid)
        beats = a.get("beats")
        if not isinstance(beats, list) or not 1 <= len(beats) <= 12:
            err.append(f"{aid}: needs 1..12 beats")
            beats = [] if not isinstance(beats, list) else beats[:12]
        for k, b in enumerate(beats):
            for lang in langs:
                t = b.get(lang) if isinstance(b, dict) else None
                if not isinstance(t, str) or not t.strip():
                    err.append(f"{aid}: beat {k} lacks {lang}")
                elif len(t) > MAX_BEAT_CHARS:
                    err.append(f"{aid}: beat {k} ({lang}) is longer than {MAX_BEAT_CHARS} characters")
            if isinstance(b, dict) and isinstance(b.get(langs[0]), str):
                words += len(b[langs[0]].split())
        actors = a.get("actors")
        if not isinstance(actors, list) or len(actors) > MAX_ACTORS_PER_ACT:
            err.append(f"{aid}: `actors` must be a list of at most {MAX_ACTORS_PER_ACT}")
            continue
        ids: Dict[Any, str] = {}
        for ac in actors:
            if not isinstance(ac, dict):
                err.append(f"{aid}: an actor is not an object")
                continue
            t, i = ac.get("type"), ac.get("id")
            if not isinstance(i, str) or not i:
                err.append(f"{aid}: an actor lacks an id")
                continue
            if t == "cam":
                ids[i] = t
                continue
            if t not in PROPS:
                err.append(f"{aid}: unknown actor type {t!r}")
                continue
            if i in ids:
                err.append(f"{aid}: duplicate actor id {i!r}")
            ids[i] = t
            for k in ac:
                if k not in COMMON and k not in PROPS[t]:
                    err.append(f"{aid}: actor {i} ({t}) has unknown property {k!r}")
            if t == "caption":
                tx = ac.get("text")
                if not (isinstance(tx, dict) and all(isinstance(tx.get(lg), str) and tx.get(lg) for lg in langs)):
                    err.append(f"{aid}: caption {i} needs text in {', '.join(langs)}")
            if t == "art" and ac.get("src") not in art:
                err.append(f"{aid}: art {i} uses an unknown design {ac.get('src')!r}")
        tweens = a.get("tweens", [])
        if not isinstance(tweens, list) or len(tweens) > MAX_TWEENS_PER_ACT:
            err.append(f"{aid}: `tweens` must be a list of at most {MAX_TWEENS_PER_ACT}")
            continue
        for tw in tweens:
            if not isinstance(tw, dict):
                err.append(f"{aid}: a tween is not an object")
                continue
            who, p = tw.get("a"), tw.get("p")
            if who != "cam" and who not in ids:
                err.append(f"{aid}: tween on unknown actor {who!r}")
                continue
            allowed = CAM if who == "cam" else (COMMON | PROPS.get(ids.get(who, ""), set()))
            if p not in allowed:
                err.append(f"{aid}: tween property {p!r} not valid for {who!r}")
            if "to" not in tw:
                err.append(f"{aid}: tween without 'to'")
            at = tw.get("at")
            if not _num(at) and not AT.match(str(at)):
                err.append(f"{aid}: bad 'at' {at!r}")
            m = re.match(r"^b(\d+)", str(at))
            if m and int(m.group(1)) >= max(len(beats), 1):
                err.append(f"{aid}: tween refers to beat {m.group(1)} but the act has {len(beats)}")
            if tw.get("e") and tw["e"] not in EASES:
                err.append(f"{aid}: unknown easing {tw['e']!r}")
            if "d" in tw and (not _num(tw["d"]) or tw["d"] <= 0 or tw["d"] > 120):
                err.append(f"{aid}: bad duration")
    target = clamp_minutes(minutes) * WORDS_PER_MINUTE
    if words and not target * 0.4 <= words <= target * 1.8:
        err.append(f"the narration has {words} words in {langs[0]}, expected about {target} "
                   f"(band {int(target * .4)}..{int(target * 1.8)})")
    return err


def validate(raw_or_doc: Any, minutes: int, langs: Sequence[str], art_names: Sequence[str]) -> Dict[str, Any]:
    doc = extract(raw_or_doc) if isinstance(raw_or_doc, str) else raw_or_doc
    if not isinstance(doc, dict):
        raise DirectionError(["the screenplay is not an object"])
    err = check(doc, minutes, langs, art_names)
    if err:
        raise DirectionError(err)
    return doc


def repair_prompt(original: str, previous: str, findings: Sequence[str]) -> str:
    return (original + "\n\n## Your previous answer was rejected\nFix exactly these findings and reply with the "
            "complete corrected JSON object only:\n" + "\n".join(f"- {f}" for f in list(findings)[:40])
            + "\n\nPrevious answer:\n" + previous[:60000])
