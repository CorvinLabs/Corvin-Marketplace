"""Video templates: a named recipe that tells the storyboard writer WHAT KIND of video to make.

A video template is not a slide template. A slide template (``web_templates.TEMPLATES``: hero, content,
stat, ...) is one visual a single scene can use. A video template is the whole-video recipe: length, audience,
tone, the order of scenes and what each one is for, which slide templates fit, which checks the finished
storyboard must pass. Choosing "Marketing" or "Code debugging" changes the storyboard prompt and the checks;
it never changes the renderer, the voice chain or the job lifecycle.

Templates are data (``src/video_templates/*.json``), validated strictly on load: an unknown key, a wrong type
or an unknown check name is an error, so a typo in a template can never silently weaken a rule. The checks
are code (``CHECKS`` below) and are referenced BY NAME from the template file.

Severity: a check returns ``error`` (the storyboard is repaired once, then the job fails) or ``warning``
(recorded, never blocks). Only rules the template's purpose depends on are errors (a Short opens with a
question; no video exceeds its template's maximum length).

Python 3.9 compatible (the plugin's declared floor): no ``X | Y`` annotations evaluated at runtime.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1
DEFAULT_TEMPLATE_ID = "standard"
TEMPLATE_DIR = Path(__file__).resolve().parent / "video_templates"

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_ASPECTS = ("16:9", "9:16")
_CATEGORIES = ("explain", "persuade", "engineer", "research", "format")
_KINDS = ("title", "opening", "problem", "solution", "example", "summary", "anchor")
_EVIDENCE = ("none", "sources", "cited_numbers")
_MODEL_TIERS = ("haiku", "sonnet", "opus")
_LANGS = ("en", "de")

# Slide templates that carry a measurable claim (a number, a quote, a piece of code).
_DATA_SLIDES = frozenset({"stat", "chart", "line", "donut", "bento", "quote", "code"})

# Pressure / fear language a template may forbid (CONCEPT-0137 section 6). A word list is a SMELL test:
# it only ever produces a warning for the operator to read, never an automatic rewrite.
_PRESSURE_PHRASES = (
    "nur noch heute", "letzte chance", "verpass", "bevor es zu spät", "du wirst bereuen", "sonst bist du",
    "only today", "last chance", "don't miss out", "before it's too late", "you will regret", "or else you",
    "act now", "jetzt oder nie",
)


class TemplateError(ValueError):
    """A template file that does not meet the schema, or a request that names no usable template."""


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" | "warning"
    code: str
    message: str

    def to_dict(self) -> Dict[str, str]:
        return {"severity": self.severity, "code": self.code, "message": self.message}


@dataclass(frozen=True)
class Step:
    kind: str
    purpose: str
    required: bool = True


@dataclass(frozen=True)
class VideoTemplate:
    id: str
    name: Dict[str, str]
    summary: Dict[str, str]
    category: str
    audience: str
    tone: str
    aspect: str
    available: bool
    unavailable_reason: str
    target_s: int
    min_s: int
    max_s: int
    scene_min: int
    scene_max: int
    scene_ms_min: int
    scene_ms_max: int
    didactic_strategy: Optional[str]
    structure: Tuple[Step, ...]
    preferred_slides: Tuple[str, ...]
    rules: Tuple[str, ...]
    avoid: Tuple[str, ...]
    hook_max_words: int          # 0 = no question hook required
    evidence: str
    checks: Tuple[str, ...]
    recommended_model: str
    sort: int = 100
    mode: str = "slides"
    input_kind: str = ""         # what the brief must contain beyond text: "" | "url"

    def public(self) -> Dict[str, Any]:
        """What the panel needs to draw the picker. The prompt rules stay server-side."""
        return {
            "id": self.id, "name": dict(self.name), "summary": dict(self.summary), "category": self.category,
            "audience": self.audience, "tone": self.tone, "aspect": self.aspect,
            "available": self.available, "unavailable_reason": self.unavailable_reason,
            "duration": {"target_s": self.target_s, "min_s": self.min_s, "max_s": self.max_s},
            "scenes": {"min": self.scene_min, "max": self.scene_max},
            "structure": [{"kind": s.kind, "purpose": s.purpose, "required": s.required} for s in self.structure],
            "hook": {"kind": "question", "max_words": self.hook_max_words} if self.hook_max_words else None,
            "evidence": self.evidence, "recommended_model": self.recommended_model,
            "mode": self.mode, "input": {"kind": self.input_kind} if self.input_kind else None,
        }


# ── Loading and strict validation ────────────────────────────────────────────

def _req(d: Dict[str, Any], key: str, typ: Any, where: str) -> Any:
    if key not in d:
        raise TemplateError("%s: missing '%s'" % (where, key))
    v = d[key]
    if typ is int and isinstance(v, bool):
        raise TemplateError("%s: '%s' must be an integer" % (where, key))
    if not isinstance(v, typ):
        raise TemplateError("%s: '%s' has the wrong type" % (where, key))
    return v


def _only(d: Dict[str, Any], allowed: Tuple[str, ...], where: str) -> None:
    extra = sorted(set(d) - set(allowed))
    if extra:
        raise TemplateError("%s: unknown key(s) %s" % (where, ", ".join(extra)))


def _text_map(v: Any, where: str) -> Dict[str, str]:
    if not isinstance(v, dict) or set(v) != set(_LANGS):
        raise TemplateError("%s: needs exactly the languages %s" % (where, "/".join(_LANGS)))
    for lang, s in v.items():
        if not isinstance(s, str) or not s.strip() or len(s) > 400:
            raise TemplateError("%s.%s: a non-empty text of at most 400 characters" % (where, lang))
    return dict(v)


def _strings(v: Any, where: str, *, max_items: int, max_len: int = 400) -> Tuple[str, ...]:
    if not isinstance(v, list) or len(v) > max_items:
        raise TemplateError("%s: a list of at most %d strings" % (where, max_items))
    out = []
    for s in v:
        if not isinstance(s, str) or not s.strip() or len(s) > max_len:
            raise TemplateError("%s: every entry is a non-empty string of at most %d characters" % (where, max_len))
        out.append(s.strip())
    return tuple(out)


_TOP_KEYS = (
    "schema", "id", "name", "summary", "category", "sort", "audience", "tone", "format", "duration", "scenes",
    "scene_ms", "didactic_strategy", "structure", "preferred_slides", "rules", "avoid", "hook", "evidence",
    "checks", "recommended_model", "mode", "input",
)
# ADR-2336: a template normally shapes the storyboard of a SLIDE video ("slides"). A template with another mode picks
# another job pipeline (``website``: a narrated tour of a web page) and says what its brief must contain.
_MODES = ("slides", "website")
_INPUT_KINDS = ("url",)


def parse_template(raw: Dict[str, Any], source: str = "template") -> VideoTemplate:
    """Validate one template dict. Raises TemplateError naming the first problem."""
    if not isinstance(raw, dict):
        raise TemplateError("%s: not an object" % source)
    _only(raw, _TOP_KEYS, source)
    if _req(raw, "schema", int, source) != SCHEMA_VERSION:
        raise TemplateError("%s: schema must be %d" % (source, SCHEMA_VERSION))
    tid = _req(raw, "id", str, source)
    if not _ID_RE.match(tid):
        raise TemplateError("%s: id must match %s" % (source, _ID_RE.pattern))
    where = tid
    category = _req(raw, "category", str, where)
    if category not in _CATEGORIES:
        raise TemplateError("%s: category must be one of %s" % (where, ", ".join(_CATEGORIES)))
    fmt = _req(raw, "format", dict, where)
    _only(fmt, ("aspect", "available", "unavailable_reason"), where + ".format")
    aspect = _req(fmt, "aspect", str, where + ".format")
    if aspect not in _ASPECTS:
        raise TemplateError("%s.format: aspect must be one of %s" % (where, ", ".join(_ASPECTS)))
    available = _req(fmt, "available", bool, where + ".format")
    reason = fmt.get("unavailable_reason", "")
    if not available and not (isinstance(reason, str) and reason.strip()):
        raise TemplateError("%s.format: an unavailable template must say why" % where)
    dur = _req(raw, "duration", dict, where)
    _only(dur, ("target_s", "min_s", "max_s"), where + ".duration")
    t, lo, hi = (_req(dur, k, int, where + ".duration") for k in ("target_s", "min_s", "max_s"))
    if not (5 <= lo <= t <= hi <= 3600):
        raise TemplateError("%s.duration: need 5 <= min_s <= target_s <= max_s <= 3600" % where)
    sc = _req(raw, "scenes", dict, where)
    _only(sc, ("min", "max"), where + ".scenes")
    smin, smax = _req(sc, "min", int, where + ".scenes"), _req(sc, "max", int, where + ".scenes")
    if not (1 <= smin <= smax <= 30):
        raise TemplateError("%s.scenes: need 1 <= min <= max <= 30" % where)
    ms = _req(raw, "scene_ms", dict, where)
    _only(ms, ("min", "max"), where + ".scene_ms")
    mmin, mmax = _req(ms, "min", int, where + ".scene_ms"), _req(ms, "max", int, where + ".scene_ms")
    if not (1000 <= mmin <= mmax <= 30000):
        raise TemplateError("%s.scene_ms: need 1000 <= min <= max <= 30000" % where)
    strat = raw.get("didactic_strategy")
    if strat not in (None, "minimal_visual", "rich_visual"):
        raise TemplateError("%s: didactic_strategy must be minimal_visual, rich_visual or null" % where)
    steps = []
    for i, st in enumerate(_req(raw, "structure", list, where)):
        if not isinstance(st, dict):
            raise TemplateError("%s.structure[%d]: not an object" % (where, i))
        _only(st, ("kind", "purpose", "required"), "%s.structure[%d]" % (where, i))
        kind = _req(st, "kind", str, "%s.structure[%d]" % (where, i))
        if kind not in _KINDS:
            raise TemplateError("%s.structure[%d]: kind must be one of %s" % (where, i, ", ".join(_KINDS)))
        purpose = _req(st, "purpose", str, "%s.structure[%d]" % (where, i)).strip()
        if not purpose or len(purpose) > 300:
            raise TemplateError("%s.structure[%d]: purpose of 1-300 characters" % (where, i))
        req = st.get("required", True)
        if not isinstance(req, bool):
            raise TemplateError("%s.structure[%d]: required must be a boolean" % (where, i))
        steps.append(Step(kind, purpose, req))
    if not 2 <= len(steps) <= 12:
        raise TemplateError("%s.structure: 2-12 steps" % where)
    if sum(1 for s in steps if s.required) > smax:
        raise TemplateError("%s: more required steps than scenes.max" % where)
    # Imported lazily: web_templates pulls in the renderer's data tables.
    try:
        from .web_templates import TEMPLATES as _slides  # noqa: PLC0415
    except ImportError:  # standalone use
        from web_templates import TEMPLATES as _slides  # noqa: PLC0415
    pref = _strings(_req(raw, "preferred_slides", list, where), where + ".preferred_slides", max_items=12, max_len=24)
    unknown = [p for p in pref if p not in _slides]
    if unknown:
        raise TemplateError("%s.preferred_slides: no such slide template: %s" % (where, ", ".join(unknown)))
    hook = raw.get("hook")
    hook_words = 0
    if hook is not None:
        if not isinstance(hook, dict):
            raise TemplateError("%s.hook: not an object" % where)
        _only(hook, ("kind", "max_words"), where + ".hook")
        if hook.get("kind") != "question":
            raise TemplateError("%s.hook: kind must be 'question'" % where)
        hook_words = _req(hook, "max_words", int, where + ".hook")
        if not 3 <= hook_words <= 30:
            raise TemplateError("%s.hook: max_words 3-30" % where)
    evidence = _req(raw, "evidence", str, where)
    if evidence not in _EVIDENCE:
        raise TemplateError("%s: evidence must be one of %s" % (where, ", ".join(_EVIDENCE)))
    checks = _strings(_req(raw, "checks", list, where), where + ".checks", max_items=12, max_len=40)
    bad = [c for c in checks if c not in CHECKS]
    if bad:
        raise TemplateError("%s.checks: unknown check %s (known: %s)" % (where, ", ".join(bad), ", ".join(sorted(CHECKS))))
    if hook_words and "opens_with_question" not in checks:
        raise TemplateError("%s: a hook needs the opens_with_question check" % where)
    model = _req(raw, "recommended_model", str, where)
    if model not in _MODEL_TIERS:
        raise TemplateError("%s: recommended_model must be one of %s" % (where, ", ".join(_MODEL_TIERS)))
    sort = raw.get("sort", 100)
    if not isinstance(sort, int) or isinstance(sort, bool):
        raise TemplateError("%s: sort must be an integer" % where)
    mode = raw.get("mode", "slides")
    if mode not in _MODES:
        raise TemplateError("%s: mode must be one of %s" % (where, ", ".join(_MODES)))
    input_kind = ""
    if "input" in raw:
        inp = _req(raw, "input", dict, where)
        _only(inp, ("kind",), where + ".input")
        input_kind = _req(inp, "kind", str, where + ".input")
        if input_kind not in _INPUT_KINDS:
            raise TemplateError("%s.input: kind must be one of %s" % (where, ", ".join(_INPUT_KINDS)))
        if mode == "slides":
            raise TemplateError("%s: an input applies to a template with another mode than slides" % where)
    if mode == "website" and input_kind != "url":
        raise TemplateError("%s: the website mode needs input.kind 'url'" % where)
    return VideoTemplate(
        id=tid, name=_text_map(raw.get("name"), where + ".name"), summary=_text_map(raw.get("summary"), where + ".summary"),
        category=category, audience=_req(raw, "audience", str, where).strip(), tone=_req(raw, "tone", str, where).strip(),
        aspect=aspect, available=available, unavailable_reason=str(reason or "").strip(),
        target_s=t, min_s=lo, max_s=hi, scene_min=smin, scene_max=smax, scene_ms_min=mmin, scene_ms_max=mmax,
        didactic_strategy=strat, structure=tuple(steps), preferred_slides=pref,
        rules=_strings(_req(raw, "rules", list, where), where + ".rules", max_items=14),
        avoid=_strings(_req(raw, "avoid", list, where), where + ".avoid", max_items=10),
        hook_max_words=hook_words, evidence=evidence, checks=checks, recommended_model=model, sort=sort,
        mode=mode, input_kind=input_kind,
    )


_CACHE: Dict[str, Dict[str, VideoTemplate]] = {}


def load_all(directory: Optional[Path] = None) -> Dict[str, VideoTemplate]:
    """Every template of the directory, keyed by id, ordered by (sort, id). A broken file raises: the set of
    shipped templates is part of the build, so a failure belongs in the test run, not in a half-empty picker."""
    base = Path(directory) if directory is not None else TEMPLATE_DIR
    key = str(base)
    if key in _CACHE:
        return _CACHE[key]
    found: Dict[str, VideoTemplate] = {}
    for path in sorted(base.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise TemplateError("%s: unreadable (%s)" % (path.name, type(e).__name__)) from None
        t = parse_template(raw, path.name)
        if t.id != path.stem:
            raise TemplateError("%s: id '%s' must equal the file name" % (path.name, t.id))
        if t.id in found:
            raise TemplateError("%s: duplicate id" % path.name)
        found[t.id] = t
    if DEFAULT_TEMPLATE_ID not in found:
        raise TemplateError("the default template '%s' is missing" % DEFAULT_TEMPLATE_ID)
    ordered = dict(sorted(found.items(), key=lambda kv: (kv[1].sort, kv[0])))
    _CACHE[key] = ordered
    return ordered


def get(template_id: Optional[str]) -> VideoTemplate:
    """The named template; None/"" = the default. An unknown id raises (never a silent fallback)."""
    tid = (template_id or DEFAULT_TEMPLATE_ID).strip()
    all_ = load_all()
    if tid not in all_:
        raise TemplateError("unknown video template '%s'" % tid[:40])
    return all_[tid]


def usable(template_id: Optional[str]) -> VideoTemplate:
    """get() plus the availability rule: a template whose renderer is not built is refused, never rendered wrong."""
    t = get(template_id)
    if not t.available:
        raise TemplateError("the '%s' template is not available: %s" % (t.id, t.unavailable_reason))
    return t


def effective_max_minutes(t: VideoTemplate, tenant_max_minutes: int) -> int:
    """The validator and the budget count whole minutes: the template can only lower the tenant's ceiling."""
    return max(1, min(int(tenant_max_minutes), -(-t.max_s // 60)))


# ── Prompt block ─────────────────────────────────────────────────────────────

def prompt_block(t: VideoTemplate) -> str:
    """The text inserted into the storyboard prompt. It states the recipe and says it wins over the generic
    DESIGN RULES where they differ. Empty for the default template (the prompt stays byte-identical)."""
    if t.id == DEFAULT_TEMPLATE_ID:
        return ""
    lines = [
        "VIDEO TEMPLATE: %s (%s)" % (t.name["en"], t.id),
        "This template overrides the generic DESIGN RULES above wherever they differ.",
        "Audience: %s" % t.audience,
        "Tone: %s" % t.tone,
        "Length: about %d s in total (never more than %d s, never less than %d s); %d-%d scenes; each scene %d-%d ms."
        % (t.target_s, t.max_s, t.min_s, t.scene_min, t.scene_max, t.scene_ms_min, t.scene_ms_max),
        "Scene plan, in this order (\"required\" steps must appear):",
    ]
    for i, s in enumerate(t.structure, 1):
        lines.append("  %d. kind \"%s\"%s: %s" % (i, s.kind, "" if s.required else " (optional)", s.purpose))
    if t.hook_max_words:
        lines.append("HOOK: the very first sentence of scene 1's narration_text is ONE open question of at most %d words "
                     "that the video answers. It is spoken first and shown as the headline of scene 1." % t.hook_max_words)
    if t.preferred_slides:
        lines.append("Prefer these slide templates: %s." % ", ".join(t.preferred_slides))
    if t.evidence == "sources":
        lines.append("EVIDENCE: every factual claim comes from the task or its attached sources; name the source in the "
                     "narration. State an uncertainty instead of guessing.")
    elif t.evidence == "cited_numbers":
        lines.append("EVIDENCE: every number, date and name comes from the task or its sources, verbatim. Never invent one.")
    lines += ["RULES:"] + ["- " + r for r in t.rules]
    if t.avoid:
        lines += ["AVOID:"] + ["- " + r for r in t.avoid]
    lines.append("Never use pressure, fear, shame or false urgency to persuade; the video must be true and checkable.")
    return "\n".join(lines) + "\n\n"


# ── Checks on the finished storyboard ────────────────────────────────────────

def _scenes(sb: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [s for s in (sb.get("scenes") or []) if isinstance(s, dict)]


def _first_sentence(text: str) -> str:
    m = re.match(r"\s*(.+?[.!?…])(\s|$)", text or "", re.S)
    return (m.group(1) if m else (text or "").strip()).strip()


def _check_opens_with_question(t: VideoTemplate, sb: Dict[str, Any]) -> List[Issue]:
    sc = _scenes(sb)
    if not sc:
        return []
    first = _first_sentence(str(sc[0].get("narration_text") or ""))
    words = len(first.split())
    if not first.endswith("?"):
        return [Issue("error", "hook_not_question", "The first sentence of scene 1 must be a question (it ends with '?').")]
    if t.hook_max_words and words > t.hook_max_words:
        return [Issue("error", "hook_too_long", "The opening question has %d words; the limit is %d." % (words, t.hook_max_words))]
    return []


def _check_ends_with_takeaway(t: VideoTemplate, sb: Dict[str, Any]) -> List[Issue]:
    sc = _scenes(sb)
    if sc and sc[-1].get("kind") not in ("summary", "anchor"):
        return [Issue("warning", "no_takeaway", "The last scene is not a summary/anchor with a one-sentence takeaway.")]
    return []


def _check_has_data_scene(t: VideoTemplate, sb: Dict[str, Any]) -> List[Issue]:
    if any(s.get("template") in _DATA_SLIDES for s in _scenes(sb)):
        return []
    return [Issue("warning", "no_data_scene", "No scene shows a number, a quote or code (stat, chart, line, donut, bento, quote, code).")]


def _check_has_code_scene(t: VideoTemplate, sb: Dict[str, Any]) -> List[Issue]:
    if any(s.get("template") == "code" for s in _scenes(sb)):
        return []
    return [Issue("warning", "no_code_scene", "No scene shows code; a debugging video needs the faulty and the fixed code on screen.")]


def _check_no_pressure_language(t: VideoTemplate, sb: Dict[str, Any]) -> List[Issue]:
    hits = []
    for s in _scenes(sb):
        low = str(s.get("narration_text") or "").lower()
        hits += [p for p in _PRESSURE_PHRASES if p in low]
    if hits:
        return [Issue("warning", "pressure_language", "Pressure or fear wording found (%s); rewrite it factually." % ", ".join(sorted(set(hits))[:4]))]
    return []


def _check_has_opening_context(t: VideoTemplate, sb: Dict[str, Any]) -> List[Issue]:
    kinds = [s.get("kind") for s in _scenes(sb)]
    if kinds and not any(k in ("opening", "problem") for k in kinds[:3]):
        return [Issue("warning", "no_context", "No opening/problem scene in the first three scenes.")]
    return []


CHECKS: Dict[str, Callable[[VideoTemplate, Dict[str, Any]], List[Issue]]] = {
    "opens_with_question": _check_opens_with_question,
    "ends_with_takeaway": _check_ends_with_takeaway,
    "has_data_scene": _check_has_data_scene,
    "has_code_scene": _check_has_code_scene,
    "no_pressure_language": _check_no_pressure_language,
    "has_opening_context": _check_has_opening_context,
}


def check_storyboard(t: VideoTemplate, storyboard: Dict[str, Any]) -> List[Issue]:
    """Template rules for a parsed storyboard dict: length and scene count (always), then the named checks."""
    if t.id == DEFAULT_TEMPLATE_ID:
        return []
    out: List[Issue] = []
    sc = _scenes(storyboard)
    total_s = sum(int(s.get("duration_ms") or 0) for s in sc) / 1000.0
    if total_s > t.max_s * 1.10:
        out.append(Issue("error", "too_long", "The storyboard is %.0f s; this template allows at most %d s." % (total_s, t.max_s)))
    elif total_s < t.min_s * 0.70:
        out.append(Issue("warning", "too_short", "The storyboard is %.0f s; this template aims for %d-%d s." % (total_s, t.min_s, t.max_s)))
    if len(sc) > t.scene_max:
        out.append(Issue("error", "too_many_scenes", "%d scenes; this template allows at most %d." % (len(sc), t.scene_max)))
    elif len(sc) < t.scene_min:
        out.append(Issue("warning", "too_few_scenes", "%d scenes; this template aims for at least %d." % (len(sc), t.scene_min)))
    kinds = [s.get("kind") for s in sc]
    for st in t.structure:
        if st.required and st.kind not in kinds:
            out.append(Issue("warning", "missing_step", "No scene of kind '%s' (%s)." % (st.kind, st.purpose[:60])))
    for name in t.checks:
        out += CHECKS[name](t, storyboard)
    return out


def errors(issues: List[Issue]) -> List[Issue]:
    return [i for i in issues if i.severity == "error"]


def repair_instruction(issues: List[Issue]) -> str:
    return ("The storyboard you returned breaks the video template. Fix exactly these problems and return the complete "
            "corrected JSON object only:\n" + "\n".join("- " + i.message for i in errors(issues)))
