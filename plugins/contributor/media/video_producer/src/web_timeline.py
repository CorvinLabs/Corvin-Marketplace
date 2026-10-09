"""Narration-synced cue timeline for web slides (ADR-2245).

Speech is the clock: a scene's narration is split into sentences, each sentence
start is located in the real narration audio (character share, snapped to a
detected pause), and the slide's items are revealed and focused when the
narration names them. Pure Python plus one ``ffmpeg silencedetect`` call; no
extra TTS request and no model in the loop.

The output is a ``Timeline`` that ``web_templates.build_document`` turns into
per-element animation delays and one focus "clock" animation.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HEADER_TIMES = {0: 0.35, 1: 0.65}   # eyebrow, title
FIRST_CONTENT_S = 1.0               # no item before the title has landed
REVEAL_LEAD_S = 0.25                # an item starts rising just before its name is said
FOCUS_MIN_GAP_S = 2.5               # focus never jumps faster than this
MIN_VISIBLE_S = 2.5                 # an item named in the last words still gets this long on screen
SNAP_WINDOW_S = 1.2
MIN_SENTENCE_S = 0.5
MAX_CHIPS = 4
CHIP_MAX_CHARS = 28
SPARSE_TEMPLATES = ("hero", "quote", "stat")

_ABBREV = (
    "z. B.", "z.B.", "u. a.", "u.a.", "d. h.", "d.h.", "bzw.", "ca.", "Nr.", "vgl.", "inkl.", "etc.",
    "Dr.", "Prof.", "evtl.", "ggf.", "usw.", "e.g.", "i.e.", "vs.", "approx.", "Mr.", "Ms.", "No.",
)
_STOP = {
    "der", "die", "das", "und", "oder", "aber", "eine", "einen", "einem", "einer", "eines", "nicht",
    "sich", "auch", "wird", "werden", "wurde", "sind", "ist", "mit", "für", "von", "auf", "aus", "bei",
    "dass", "diese", "dieser", "dieses", "denn", "wenn", "dann", "noch", "schon", "immer", "jeder", "jede",
    "jedes", "alle", "allen", "kein", "keine", "genau", "dabei", "damit", "dafür", "darum", "hier", "dort",
    "the", "and", "that", "this", "with", "from", "into", "every", "each", "when", "then", "they", "their",
    "there", "which", "would", "could", "should", "about", "because", "while", "where",
}


# ── text ───────────────────────────────────────────────────────────────────

def split_sentences(text: str) -> List[Tuple[int, int]]:
    """Sentence spans (start, end) over ``text``; abbreviations and decimals
    (``z. B.``, ``ca. 30``, ``3.5``) do not end a sentence."""
    protected = text
    for ab in _ABBREV:
        protected = protected.replace(ab, ab.replace(".", "\x00"))
    protected = re.sub(r"(?<=\d)\.(?=\d)", "\x00", protected)
    spans, start = [], 0
    for m in re.finditer(r"[.!?…]+[\"'“”»)]*\s+", protected):
        end = m.end()
        if protected[start:end].strip():
            spans.append((start, end))
        start = end
    if protected[start:].strip():
        spans.append((start, len(protected)))
    return spans or ([(0, len(text))] if text.strip() else [])


def _collapse(text: str) -> Tuple[str, List[int]]:
    """Lower-cased alphanumerics only, with the original index of each kept char."""
    chars, idx = [], []
    for i, ch in enumerate(text):
        if ch.isalnum():
            chars.append(ch.lower())
            idx.append(i)
    return "".join(chars), idx


def _tokens(label: str) -> List[str]:
    """Significant lower-case tokens of a label: its words, and the parts of
    CamelCase / hyphenated / '+'-joined compounds ('EventEmitter' -> eventemitter,
    event, emitter)."""
    out: List[str] = []
    for w in re.findall(r"[\w][\w\-./+]*", label or "", flags=re.UNICODE):
        parts = [w] + re.split(r"[\-./+_]|(?<=[a-zäöüß])(?=[A-ZÄÖÜ])", w)
        for part in parts:
            c = re.sub(r"[^\w]", "", part).lower().replace("_", "")
            if len(c) >= 4 and c not in _STOP and not c.isdigit() and c not in out:
                out.append(c)
    return out


def find_mentions(narration: str, labels: Sequence[str], subs: Optional[Sequence[str]] = None) -> List[List[int]]:
    """For each label, the character positions in ``narration`` where it is named.

    Tried in order, first hit wins: the whole label (spacing, hyphens, case
    ignored); its most specific token no other item shares (compound parts
    count: 'EventEmitter' matches 'Emitter'); then the same for the item's
    sub-line ('Feedback, Outcome' matches 'Nutzerfeedback')."""
    flat, idx = _collapse(narration)
    subs = list(subs) if subs is not None else [""] * len(labels)
    toks = [_tokens(lb) for lb in labels]
    stoks = [_tokens(sb) for sb in subs]
    counts: Dict[str, int] = {}
    for ts in toks + stoks:
        for t in set(ts):
            counts[t] = counts.get(t, 0) + 1

    def unique(ts: List[str]) -> List[str]:
        return sorted((t for t in ts if counts[t] == 1 and len(t) >= 5), key=len, reverse=True)

    out: List[List[int]] = []
    for lb, ts, ss in zip(labels, toks, stoks):
        whole = _collapse(lb)[0]
        needles = ([whole] if len(whole) >= 4 else []) + unique(ts) + unique(ss)
        pos: List[int] = []
        for nd in needles:
            start = 0
            while (k := flat.find(nd, start)) >= 0:
                pos.append(idx[k])
                start = k + len(nd)
            if pos:
                break
        out.append(sorted(set(pos)))
    return out


def fallback_chip(sentence: str, lang: str) -> Optional[str]:
    """One keyword from a sentence: the longest capitalised word inside it
    (German nouns), else the longest long word. None when nothing qualifies."""
    words = re.findall(r"[\wÄÖÜäöüß][\w\-ÄÖÜäöüß]*", sentence)
    if len(words) < 3:
        return None
    body = words[1:]  # the first word is capitalised by grammar, not by meaning
    cands = [w for w in body if w[0].isupper() and len(w) >= 6] if lang == "de" else []
    if not cands:
        cands = [w for w in body if len(w) >= (8 if lang != "de" else 9)]
    cands = [w for w in cands if w.lower() not in _STOP and not w.isdigit() and len(w) <= CHIP_MAX_CHARS]
    return max(cands, key=len) if cands else None


# ── audio ──────────────────────────────────────────────────────────────────

@dataclass
class AudioPauses:
    duration: float
    pause_ends: List[float] = field(default_factory=list)   # speech resumes here
    speech_start: float = 0.0
    speech_end: float = 0.0
    silent_ratio: float = 0.0


def detect_pauses(audio: Path, duration: float, noise_db: int = -35, min_pause: float = 0.25) -> AudioPauses:
    """Pause ends from ``ffmpeg silencedetect``. Any failure = no pauses (estimate only)."""
    res = AudioPauses(duration=duration, speech_end=duration)
    try:
        err = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(audio), "-af",
             f"silencedetect=n={noise_db}dB:d={min_pause}", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        ).stderr
    except (OSError, subprocess.SubprocessError):
        return res
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    silent = sum(float(x) for x in re.findall(r"silence_duration: ([\d.]+)", err))
    if len(starts) > len(ends):  # silence runs to the end
        silent += max(0.0, duration - starts[-1])
        res.speech_end = max(0.0, starts[-1])
    res.silent_ratio = silent / duration if duration > 0 else 1.0
    if starts and starts[0] <= 0.05 and ends:
        res.speech_start = ends[0]
        ends = ends[1:]
    res.pause_ends = [e for e in ends if e < res.speech_end]
    if res.silent_ratio >= 0.5 or res.speech_end - res.speech_start < 0.3 * duration:
        # mostly silent (the offline mock voice) or implausible: no usable speech
        # boundaries — the whole clip is the speech region and nothing is snapped
        return AudioPauses(duration=duration, speech_end=duration, silent_ratio=max(res.silent_ratio, 0.5))
    return res


def sentence_starts(spans: List[Tuple[int, int]], pauses: AudioPauses) -> List[float]:
    """Start time of every sentence: character share of the speech region, each
    snapped to the nearest unused pause end within ±SNAP_WINDOW_S, order kept."""
    if not spans:
        return []
    s0, s1 = pauses.speech_start, max(pauses.speech_end, pauses.speech_start + 0.1)
    total = spans[-1][1] - spans[0][0] or 1
    est = [s0 + (a - spans[0][0]) / total * (s1 - s0) for a, _ in spans]
    out = [est[0]]
    snap = pauses.silent_ratio < 0.5
    used: set = set()
    for k in range(1, len(est)):
        lo = out[-1] + MIN_SENTENCE_S
        t = max(est[k], lo)
        if snap:
            best = None
            for j, p in enumerate(pauses.pause_ends):
                if j in used or p < lo or abs(p - est[k]) > SNAP_WINDOW_S:
                    continue
                if best is None or abs(p - est[k]) < abs(pauses.pause_ends[best] - est[k]):
                    best = j
            if best is not None:
                used.add(best)
                t = pauses.pause_ends[best]
        out.append(min(t, max(lo, pauses.duration - 0.2)))
    return out


# ── cues ───────────────────────────────────────────────────────────────────

@dataclass
class Timeline:
    duration: float
    sentences: List[str]
    starts: List[float]
    step_times: Dict[int, float]                  # content step -> reveal time
    item_steps: List[int]                         # steps that take part in focus
    focus: List[Tuple[float, Optional[int]]]      # (time, focused step or None)
    chips: List[Tuple[float, str]]
    source: str                                   # "llm" | "fallback"
    notes: List[str] = field(default_factory=list)

    def time_of(self, step: int) -> float:
        if step in HEADER_TIMES:
            return HEADER_TIMES[step]
        if step in self.step_times:
            return self.step_times[step]
        lower = [s for s in list(self.step_times) + list(HEADER_TIMES) if s < step]
        base = max(lower) if lower else 1
        bt = self.step_times.get(base, HEADER_TIMES.get(base, FIRST_CONTENT_S))
        return bt + 0.35 * (step - base)

    @property
    def first_content(self) -> float:
        return min(self.step_times.values(), default=FIRST_CONTENT_S)

    @property
    def last_reveal(self) -> float:
        return max(list(self.step_times.values()) + [t for t, _ in self.chips], default=FIRST_CONTENT_S)

    def event_times(self) -> List[float]:
        return sorted(set(list(self.step_times.values()) + [t for t, _ in self.focus] + [t for t, _ in self.chips]))


def _time_at(pos: int, spans: List[Tuple[int, int]], starts: List[float], end: float) -> float:
    for k, (a, b) in enumerate(spans):
        if a <= pos < b or k == len(spans) - 1:
            nxt = starts[k + 1] if k + 1 < len(starts) else end
            frac = min(max((pos - a) / max(b - a, 1), 0.0), 1.0)
            return starts[k] + frac * (nxt - starts[k])
    return end


def _sentence_of(pos: int, spans: List[Tuple[int, int]]) -> int:
    for k, (a, b) in enumerate(spans):
        if a <= pos < b:
            return k
    return len(spans) - 1


def validate_beats(beats: Any, n_sentences: int, n_items: int, sentences: List[str],
                   chips_ok: bool) -> Tuple[Optional[List[Any]], str]:
    """LLM beats: one entry per sentence — an item index, a chip (verbatim 1–3 words of
    that sentence) or null. Anything else = (None, reason) and the fallback runs."""
    if beats is None:
        return None, "no beats"
    if not isinstance(beats, list) or len(beats) != n_sentences:
        return None, f"beats length {len(beats) if isinstance(beats, list) else '?'} != {n_sentences} sentences"
    out: List[Any] = []
    for k, b in enumerate(beats):
        if b is None:
            out.append(None)
        elif isinstance(b, bool):
            return None, f"beat {k}: boolean"
        elif isinstance(b, int):
            if not 0 <= b < n_items:
                return None, f"beat {k}: item {b} out of range (0..{n_items - 1})"
            out.append(b)
        elif isinstance(b, str):
            t = " ".join(b.split())
            if not chips_ok:
                out.append(None)
                continue
            if not t or len(t) > CHIP_MAX_CHARS or len(t.split()) > 3 or t.lower() not in sentences[k].lower():
                return None, f"beat {k}: chip {t[:30]!r} is not 1-3 words of its sentence"
            out.append(t)
        else:
            return None, f"beat {k}: unsupported type"
    return out, "ok"


def build_timeline(
    template: str,
    items: List[Tuple[str, int]],
    narration: str,
    pauses: AudioPauses,
    *,
    beats: Any = None,
    lang: str = "en",
    chips_allowed: bool = True,
    subs: Optional[List[str]] = None,
) -> Timeline:
    """Cues for one scene. ``items`` = (label, step) per data item, in data order;
    ``subs`` = each item's sub-line, a second place the narration may name it."""
    duration = pauses.duration
    text = " ".join((narration or "").split())
    spans = split_sentences(text)
    sentences = [text[a:b].strip() for a, b in spans]
    starts = sentence_starts(spans, pauses) if spans else []
    end = max(pauses.speech_end, starts[-1] + 0.5 if starts else 0.0)
    chips_ok = chips_allowed and template in SPARSE_TEMPLATES
    checked, reason = validate_beats(beats, len(sentences), len(items), sentences, chips_ok)
    source = "llm" if checked is not None else "fallback"
    notes = [] if checked is not None or beats is None else [f"beats ignored: {reason}"]

    item_time: Dict[int, float] = {}
    focus_raw: List[Tuple[float, Optional[int]]] = []   # data-item index or None
    chips: List[Tuple[float, str]] = []

    if checked is not None:
        for k, b in enumerate(checked):
            t = starts[k]
            if isinstance(b, int):
                item_time.setdefault(b, max(FIRST_CONTENT_S, t - REVEAL_LEAD_S))
                focus_raw.append((t, b))
            elif isinstance(b, str):
                p = sentences[k].lower().find(b.lower())
                chips.append((_time_at(spans[k][0] + max(p, 0), spans, starts, end), b))
            else:
                focus_raw.append((t, None))
    # label mentions fill whatever the beats left open (and are the whole fallback)
    mentions = find_mentions(text, [lb for lb, _ in items], subs) if items else []
    mentioned_sentences = set()
    for j, plist in enumerate(mentions):
        for p in plist:
            mentioned_sentences.add(_sentence_of(p, spans))
            t = _time_at(p, spans, starts, end)
            if j not in item_time:
                item_time[j] = max(FIRST_CONTENT_S, t - REVEAL_LEAD_S)
            if checked is None:
                focus_raw.append((t, j))
    if checked is None:
        for k in range(len(sentences)):
            if k not in mentioned_sentences and k > 0:
                focus_raw.append((starts[k], None))
        if chips_ok:
            for k, s in enumerate(sentences):
                c = fallback_chip(s, lang)
                if c:
                    p = s.find(c)
                    chips.append((_time_at(spans[k][0] + max(p, 0), spans, starts, end), c))

    # items nobody named: placed between their named neighbours, in data order
    n = len(items)
    if n:
        known = sorted(item_time)
        tail_end = max(FIRST_CONTENT_S + 0.4 * n, min(end - 1.0, (item_time[known[-1]] if known else FIRST_CONTENT_S) + 1.2 * n))
        for j in range(n):
            if j in item_time:
                continue
            prev = max((k for k in known if k < j), default=None)
            nxt = min((k for k in known if k > j), default=None)
            t_prev = item_time[prev] if prev is not None else FIRST_CONTENT_S
            if nxt is not None:
                t_next, span = item_time[nxt], nxt - (prev if prev is not None else -1)
            else:
                t_next, span = tail_end, n - (prev if prev is not None else -1)
            off = j - (prev if prev is not None else -1)
            item_time[j] = t_prev + (t_next - t_prev) * off / span
        if not known:
            # nothing named at all: pace the items over the first 70 % of the speech
            window = max(1.0, 0.7 * end - FIRST_CONTENT_S)
            for j in range(n):
                item_time[j] = FIRST_CONTENT_S + window * j / max(n, 1)

    # every item stays on screen long enough to be read (named in the last words = shown just before)
    latest = max(FIRST_CONTENT_S, duration - MIN_VISIBLE_S)
    for j in sorted(item_time, key=lambda k: item_time[k], reverse=True):
        if item_time[j] > latest:
            item_time[j] = latest
        latest = max(FIRST_CONTENT_S, item_time[j] - 0.3)

    step_times: Dict[int, float] = {}
    for j, (_, step) in enumerate(items):
        t = round(item_time[j], 3)
        step_times[step] = min(step_times.get(step, t), t)
    item_steps = sorted(set(step_times))

    # focus: only once two items are visible, never faster than FOCUS_MIN_GAP_S,
    # on the item's step (a flow column focuses as one)
    focus: List[Tuple[float, Optional[int]]] = []
    current: Optional[int] = None
    for t, j in sorted(focus_raw, key=lambda x: x[0]):
        target = items[j][1] if j is not None else None
        visible = sum(1 for s, ts in step_times.items() if ts <= t + 0.05)
        if target is not None and visible < 2:
            continue
        if target == current or (focus and t - focus[-1][0] < FOCUS_MIN_GAP_S):
            continue
        if t >= duration - 0.6:
            break
        focus.append((round(max(t, step_times.get(target, 0.0)), 3), target))
        current = target
    if len(item_steps) < 2:
        focus = []

    # chips: spaced, capped, in time order
    kept: List[Tuple[float, str]] = []
    seen = set()
    for t, c in sorted(chips):
        if c.lower() in seen or (kept and t - kept[-1][0] < FOCUS_MIN_GAP_S) or t > duration - 0.8:
            continue
        kept.append((round(max(t - REVEAL_LEAD_S, FIRST_CONTENT_S), 3), c))
        seen.add(c.lower())
        if len(kept) == MAX_CHIPS:
            break

    return Timeline(duration=duration, sentences=sentences, starts=[round(s, 3) for s in starts],
                    step_times=step_times, item_steps=item_steps, focus=focus, chips=kept,
                    source=source, notes=notes)
