"""Grounding pack: knowledge-base decisions + code excerpts for a Corvin explainer video.

CONCEPT-0100 / PLAN-0942. The host builds the pack with :func:`build_pack`, gates it
(L44/L34/L35, audited) and hands the accepted pack to ``orchestrate_video`` as
``grounding_pack``. This module never decides policy and never executes code from the
knowledge base: it reads the projector's graph files, decision markdown under
``<kb>/decisions/`` and git-tracked source files, each with containment and size limits.
The guarantee about what leaves the host is the host's gate on the returned text — an
in-process plugin could read more (the plugin perimeter is attribution, not security).
"""

from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import math
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

PACK_VERSION = 1
MAX_FILE_BYTES = 256 * 1024          # decision markdown
MAX_CODE_BYTES = 1024 * 1024         # one source file (security_events.py is ~370 kB)
DEFAULT_BUDGET_CHARS = 6000
MAX_DECISIONS = 4
MAX_EXCERPT_LINES = 12
MAX_MODULE_DOC_CHARS = 900

_STATUS_TIER = {"accepted": 0, "proposed": 1}
_EXCLUDED_DIR_PARTS = {".corvin", "node_modules", "tests", "test", "__pycache__", ".git"}
# Directories renamed after many decisions were written; a stale anchor is retried
# under its current name instead of reading as "not built".
PATH_RENAMES: Tuple[Tuple[str, str], ...] = (("operator/", "corvin_operator/"),)

KB_ID_RE = re.compile(r"\bADR-(\d{3,4})\b", re.IGNORECASE)
TRIGGER_RE = re.compile(r"\bcorvin(?:os)?\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-zäöüß0-9]+", re.IGNORECASE)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{2,}$")
_BACKTICK_RE = re.compile(r"`([^`\n]{2,80})`")
_SOURCE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".mjs", ".sh", ".go", ".rs")

_STOPWORDS = {
    # German
    "und", "oder", "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer",
    "ist", "sind", "wie", "was", "wer", "wo", "warum", "mit", "für", "von", "zu", "zum", "zur", "im", "in",
    "auf", "aus", "bei", "über", "unter", "nach", "vor", "auch", "nicht", "mir", "mich", "uns", "euch",
    "mal", "bitte", "kurz", "genau", "wirklich", "erkläre", "erklär", "erklären", "erklaere", "beschreibe",
    "zeige", "zeig", "mache", "mach", "funktioniert", "funktionieren", "video", "videos", "erklärvideo",
    "minuten", "minute", "sekunden", "worte", "wörter", "drei", "zwei", "vier", "fünf", "etwa", "ca",
    "prägnant", "einfach", "dabei", "dann", "damit", "diese", "dieser", "dieses", "hier",
    # English
    "the", "and", "or", "of", "to", "in", "on", "for", "with", "how", "what", "why", "does", "do", "is",
    "are", "a", "an", "explain", "describe", "show", "make", "works", "work", "minutes", "minute", "words",
    "about", "video", "short", "please",
    # the trigger itself carries no topic
    "corvin", "corvinos",
}


class GroundingError(Exception):
    """Raised for unusable inputs (bad roots); never for 'no topic found'."""


@dataclass(frozen=True)
class CodeRoot:
    """A source tree whose git-tracked files may be excerpted.

    ``kb_prefix`` is how decisions name this tree in their ``paths:`` (``""`` for
    CorvinOS, ``"Corvin-Marketplace/"`` for the marketplace). ``include`` limits the
    tracked files to these prefixes (e.g. only ``plugins/buildin/`` of the marketplace:
    contributor code is third-party text and stays out of a pack)."""

    path: Path
    kb_prefix: str = ""
    include: Tuple[str, ...] = ()


@dataclass
class Section:
    id: str
    title: str
    status: str
    date: str
    truth: str
    evidence: str
    text: str

    def to_dict(self) -> Dict[str, str]:
        return {k: getattr(self, k) for k in ("id", "title", "status", "date", "truth", "evidence", "text")}


@dataclass
class _Decision:
    id: str
    title: str
    status: str
    path: Path
    date: str
    body: str = ""
    paths: List[str] = field(default_factory=list)
    score: float = 0.0
    backlinks: int = 0
    depends_on: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------- scrubbing

_SCRUB_PATTERNS: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "<redacted key>"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{6,}"), "<redacted>"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "<redacted>"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "<redacted>"),
    (re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"), "<redacted>"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "<redacted>"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer <redacted>"),
    (re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*\S+"), r"\1=<redacted>"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "<email>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<ip>"),
    (re.compile(r"/home/[^/\s]+"), "~"),
    (re.compile(r"(?i)\bC:\\Users\\[^\\\s]+"), "~"),
)


def scrub(text: str) -> str:
    """Redact secret shapes, emails, IPv4 addresses and home paths. Never truncates."""
    for pattern, repl in _SCRUB_PATTERNS:
        text = pattern.sub(repl, text)
    return text


# --------------------------------------------------------------------------- safe file access

def _contained(path: Path, root: Path) -> Optional[Path]:
    try:
        real = Path(os.path.realpath(path))
        root_real = Path(os.path.realpath(root))
    except OSError:
        return None
    if real != root_real and root_real not in real.parents:
        return None
    return real


def _read_text(path: Path, root: Path, max_bytes: int = MAX_FILE_BYTES) -> Optional[str]:
    """Read a file only if it lies inside ``root``, is no symlink, and is small."""
    real = _contained(path, root)
    if real is None:
        return None
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if st.st_size > max_bytes:
            return None
        with os.fdopen(fd, "rb") as fh:
            fd = -1
            return fh.read(max_bytes + 1).decode("utf-8", errors="replace")
    except OSError:
        return None
    finally:
        if fd >= 0:
            os.close(fd)


def _excluded(rel: str) -> bool:
    parts = rel.split("/")
    return any(p in _EXCLUDED_DIR_PARTS or p.startswith(".venv") for p in parts[:-1])


class _Tracked:
    """Git-tracked files of one code root (never a walk of the disk: untracked trees
    such as ``.corvin/`` hold tenant data)."""

    def __init__(self, root: CodeRoot, timeout: float = 10.0):
        self.root = root
        out = subprocess.run(
            ["git", "-C", str(root.path), "ls-files", "-z"],
            capture_output=True, timeout=timeout, check=False,
        )
        if out.returncode != 0:
            raise GroundingError(f"not a git checkout: {root.path.name}")
        files = [f for f in out.stdout.decode("utf-8", "replace").split("\0") if f and not _excluded(f)]
        # every tracked file counts for "does it exist"; only the included ones may be read
        self.all_files: Set[str] = set(files)
        if root.include:
            files = [f for f in files if f.startswith(root.include)]
        self.files: Set[str] = set(files)

    def exists(self, pattern: str) -> bool:
        pattern = pattern.strip().strip("/")
        if not pattern:
            return False
        if not any(c in pattern for c in "*?["):
            return pattern in self.all_files or any(f.startswith(pattern + "/") for f in self.all_files)
        if pattern.endswith("/**"):
            return any(f.startswith(pattern[:-3] + "/") for f in self.all_files)
        return any(fnmatch.fnmatchcase(f, pattern) for f in self.all_files)

    def match(self, pattern: str) -> List[str]:
        pattern = pattern.strip().strip("/")
        if not pattern:
            return []
        if not any(c in pattern for c in "*?["):
            if pattern in self.files:
                return [pattern]
            prefix = pattern + "/"
            return sorted(f for f in self.files if f.startswith(prefix))[:200]
        if pattern.endswith("/**"):
            prefix = pattern[:-3] + "/"
            return sorted(f for f in self.files if f.startswith(prefix))[:200]
        return sorted(f for f in self.files if fnmatch.fnmatchcase(f, pattern))[:200]

    def read(self, rel: str) -> Optional[str]:
        if rel not in self.files:
            return None
        return _read_text(self.root.path / rel, self.root.path, MAX_CODE_BYTES)


# --------------------------------------------------------------------------- KB reading

def _load_jsonl(path: Path, root: Path) -> Iterable[Dict[str, Any]]:
    text = _read_text(path, root) if path.stat().st_size <= MAX_FILE_BYTES else _read_large(path, root)
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _read_large(path: Path, root: Path) -> Optional[str]:
    """The graph files exceed the per-file cap; they are generated, not authored, and
    still read with containment and no-follow (bounded at 64 MB)."""
    if _contained(path, root) is None:
        return None
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    with os.fdopen(fd, "rb") as fh:
        return fh.read(64 * 1024 * 1024).decode("utf-8", errors="replace")


def _frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    raw, body = text[3:end], text[end + 4:]
    meta: Dict[str, Any] = {}
    key = None
    for line in raw.splitlines():
        if re.match(r"^[A-Za-z_]+:", line):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip("'\"")
            meta[key] = val if val else []
        elif key and line.strip().startswith("- ") and isinstance(meta.get(key), list):
            meta[key].append(line.strip()[2:].strip().strip("'\""))
    return meta, body


def _terms(text: str) -> List[str]:
    words = [w.lower() for w in _WORD_RE.findall(text)]
    return [w for w in words if len(w) >= 3 and w not in _STOPWORDS]


def _phrases(text: str) -> List[str]:
    """Adjacent topic-word pairs of the task as written ("Audit Chain" -> "auditchain"),
    plus single compound words long enough to be one ("Auditchain")."""
    words = [w.lower() for w in _WORD_RE.findall(text)]
    out = [a + b for a, b in zip(words, words[1:])
           if len(a) >= 3 and len(b) >= 3 and a not in _STOPWORDS and b not in _STOPWORDS]
    out += [w for w in words if len(w) >= 9 and w not in _STOPWORDS]
    return out


def _title_vocab(title: str) -> Set[str]:
    words = [w.lower() for w in _WORD_RE.findall(title)]
    vocab = set(words)
    vocab.update(a + b for a, b in zip(words, words[1:]))  # "audit chain" also matches "auditchain"
    return vocab


def _in_title(term: str, vocab: Set[str]) -> bool:
    """A task word matches a title word, an adjacent title-word pair ("audit chain" for
    "auditchain"), or splits into two title words ("auditchain" for "Audit-Detail ...
    Chain Writer")."""
    if term in vocab:
        return True
    return any(term[:i] in vocab and term[i:] in vocab for i in range(4, len(term) - 3))


def _score(terms: Sequence[str], title: str, body: str) -> Tuple[float, float]:
    if not terms:
        return 0.0, 0.0
    vocab = _title_vocab(title)
    title_cov = sum(1 for t in terms if _in_title(t, vocab)) / len(terms)
    body_l = body.lower()
    compact = re.sub(r"[\s_-]+", "", body_l)
    body_cov = sum(1 for t in terms if t in body_l or t in compact) / len(terms)
    return title_cov, body_cov


# --------------------------------------------------------------------------- code evidence

def _anchor_exists(pattern: str, roots: Sequence[_Tracked]) -> bool:
    """The anchor exists in a tracked tree, even where its text may not be excerpted."""
    for tracked in roots:
        prefix = tracked.root.kb_prefix
        if prefix and not pattern.startswith(prefix):
            continue
        if not prefix and any(pattern.startswith(t.root.kb_prefix) for t in roots if t.root.kb_prefix):
            continue
        rel = pattern[len(prefix):]
        if any(tracked.exists(c) for c in [rel] + [new + rel[len(old):] for old, new in PATH_RENAMES
                                                   if rel.startswith(old)]):
            return True
    return False


def _resolve_anchor(pattern: str, roots: Sequence[_Tracked]) -> List[Tuple[_Tracked, str]]:
    for tracked in roots:
        prefix = tracked.root.kb_prefix
        if prefix and not pattern.startswith(prefix):
            continue
        if not prefix and any(pattern.startswith(t.root.kb_prefix) for t in roots if t.root.kb_prefix):
            continue
        rel = pattern[len(prefix):]
        candidates = [rel] + [new + rel[len(old):] for old, new in PATH_RENAMES if rel.startswith(old)]
        for cand in candidates:
            hits = tracked.match(cand)
            if hits:
                return [(tracked, h) for h in hits]
    return []


def _definitions(source: str) -> Dict[str, Tuple[int, str, str]]:
    """name -> (line, signature, first docstring paragraph) for top-level and class-level defs."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return {}
    out: Dict[str, Tuple[int, str, str]] = {}
    lines = source.splitlines()

    def visit(nodes, depth=0):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                sig_end = node.body[0].lineno - 1 if node.body else node.lineno
                sig = " ".join(l.strip() for l in lines[node.lineno - 1:max(sig_end, node.lineno)])[:220]
                doc = (ast.get_docstring(node) or "").split("\n\n")[0]
                out.setdefault(node.name, (node.lineno, sig, " ".join(doc.split())[:300]))
                if isinstance(node, ast.ClassDef) and depth == 0:
                    visit(node.body, depth + 1)

    visit(tree.body)
    return out


def _module_doc(source: str) -> str:
    try:
        doc = ast.get_docstring(ast.parse(source)) or ""
    except (SyntaxError, ValueError):
        return ""
    lines = [" ".join(l.split()) for l in doc.splitlines()]
    doc = "\n".join(l for l in lines if l)
    return doc[:MAX_MODULE_DOC_CHARS]


def _call_site(tracked: _Tracked, name: str, def_file: str, timeout: float) -> Optional[str]:
    """A tracked, non-test file other than the definition that names ``name``."""
    try:
        out = subprocess.run(
            ["git", "-C", str(tracked.root.path), "grep", "-l", "-w", "-F", "--", name],
            capture_output=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    for f in out.stdout.decode("utf-8", "replace").splitlines():
        name_l = Path(f).name.lower()
        # a package __init__ that re-exports a name does not call it
        if f != def_file and f in tracked.files and f.endswith(_SOURCE_SUFFIXES) \
                and "test" not in name_l and name_l != "__init__.py":
            return f
    return None


def _code_citations(tracked: _Tracked, timeout: float) -> Dict[str, int]:
    """decision id -> number of tracked non-Markdown files that name it. CorvinOS marks
    load-bearing code with the decision it implements, so this measures how much code a
    decision actually governs (``git grep``, no file is opened here)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(tracked.root.path), "grep", "-o", "-I", "-E", r"ADR-[0-9]{4}",
             "--", ".", ":(exclude)*.md"],
            capture_output=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return {}
    pairs = set()
    for line in out.stdout.decode("utf-8", "replace").splitlines():
        f, _, did = line.rpartition(":")
        if f in tracked.files:
            pairs.add((f, did))
    counts: Dict[str, int] = {}
    for _f, did in pairs:
        counts[did] = counts.get(did, 0) + 1
    return counts


def _cited_identifiers(body: str) -> List[str]:
    names: List[str] = []
    for raw in _BACKTICK_RE.findall(body):
        token = raw.strip().rstrip("()")
        token = token.split(".")[-1] if "." in token and "/" not in token else token
        token = token.split("::")[-1]
        if _IDENT_RE.match(token) and _specific(token) and token not in names:
            names.append(token)
    return names


_GENERIC_NAMES = {"get", "set", "run", "main", "load", "save", "create", "update", "delete", "init",
                  "start", "stop", "close", "open", "read", "write", "send", "call", "apply", "check",
                  "validate", "build", "render", "process", "handle", "execute", "chat_key", "tenant_id",
                  "config", "settings", "status", "result", "data", "path", "name", "value"}


def _specific(name: str) -> bool:
    """Only names specific enough that a call site is evidence: a generic ``get`` or
    ``create`` matches thousands of unrelated lines."""
    if name.lower() in _GENERIC_NAMES:
        return False
    camel = sum(1 for c in name[1:] if c.isupper()) >= 1 and name[0].isupper()
    return len(name) >= 8 and ("_" in name.strip("_") or camel)


# --------------------------------------------------------------------------- section text

_LEVEL_RE = re.compile(r"(?i)\b(conceptual|structural|implementation)(?: level)?\b\s*[:*_.)—-]+\s*")


def _levels(body: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for para in re.split(r"\n\s*\n", body):
        flat = " ".join(para.split())
        for m in _LEVEL_RE.finditer(flat):
            key = m.group(1).lower()
            if key in out:
                continue
            rest = flat[m.end():]
            nxt = _LEVEL_RE.search(rest)
            chunk = rest[: nxt.start()] if nxt else rest
            chunk = chunk.strip(" *_")
            if len(chunk) >= 40:
                out[key] = chunk[:420]
    return out


def _section_text(body: str, heading_re: str, limit: int) -> str:
    m = re.search(rf"(?im)^#{{2,3}}\s*{heading_re}.*$", body)
    if not m:
        return ""
    rest = body[m.end():]
    nxt = re.search(r"(?m)^#{1,3}\s", rest)
    chunk = rest[: nxt.start()] if nxt else rest
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", chunk) if p.strip()]
    return (paras[0] if paras else "")[:limit]


def _alternatives(body: str) -> List[str]:
    m = re.search(r"(?im)^#{2,3}\s*alternatives?.*$", body)
    if not m:
        return []
    rest = body[m.end():]
    nxt = re.search(r"(?m)^#{1,2}\s", rest)
    chunk = rest[: nxt.start()] if nxt else rest
    heads = re.findall(r"(?m)^#{3,4}\s*(.+)$", chunk) or re.findall(r"(?m)^[-*]\s+\*{0,2}([^*\n:]{6,90})", chunk)
    return [" ".join(h.split())[:90] for h in heads[:4]]


def _number_sentences(body: str, limit: int = 3) -> List[str]:
    out: List[str] = []
    flat = " ".join(body.split())
    for sent in re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])", flat):
        if re.search(r"\b\d+(?:[.,]\d+)?\s?(?:ms|s|%|MB|kB|GB|x|records?|events?|files?|tests?|hex)\b", sent) \
                and 30 <= len(sent) <= 260 and "|" not in sent:
            out.append(sent)
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- public API

def is_candidate_task(task: str) -> bool:
    """Grounding is considered only for tasks about Corvin or naming a decision."""
    return bool(KB_ID_RE.search(task) or TRIGGER_RE.search(task))


def build_pack(
    task: str,
    kb_root: Path,
    code_roots: Sequence[CodeRoot],
    *,
    budget_chars: int = DEFAULT_BUDGET_CHARS,
    deadline_s: float = 8.0,
) -> Optional[Dict[str, Any]]:
    """Return a grounding pack for ``task`` or ``None`` when the task is not about a
    documented Corvin decision. The pack is plain data (JSON-safe)."""
    started = time.monotonic()

    def left() -> float:
        return deadline_s - (time.monotonic() - started)

    if not is_candidate_task(task):
        return None
    kb_root = Path(kb_root)
    graph = kb_root / "kb" / "graph" / "entities.jsonl"
    decisions_dir = kb_root / "decisions"
    if not graph.is_file() or not decisions_dir.is_dir():
        return None

    tracked = [_Tracked(r, timeout=max(1.0, left())) for r in code_roots]

    entities = list(_load_jsonl(graph, kb_root))
    decision_uids = {e.get("uid") for e in entities if e.get("type") == "decision" and e.get("uid")}
    # Centrality: how many OTHER DECISIONS link to this one. Links from tasks, notes and
    # ideas do not count — they are agent-authorable and say nothing about structure.
    backlinks: Dict[str, int] = {}
    rel_path = kb_root / "kb" / "graph" / "relations.jsonl"
    if rel_path.is_file():
        for rel in _load_jsonl(rel_path, kb_root):
            dst, src = rel.get("dst"), rel.get("src")
            if isinstance(dst, str) and src in decision_uids and src != dst:
                backlinks[dst] = backlinks.get(dst, 0) + 1

    for tr in tracked:
        for did, n in _code_citations(tr, timeout=max(1.0, min(5.0, left()))).items():
            backlinks[did] = backlinks.get(did, 0) + n

    explicit = {f"ADR-{int(n):04d}" for n in KB_ID_RE.findall(task)}
    terms = _terms(task)
    phrases = _phrases(task)
    candidates: List[_Decision] = []
    for ent in entities:
        if ent.get("type") != "decision":
            continue
        status = str(ent.get("status") or "").lower()
        eid = str(ent.get("id") or "")
        if status not in _STATUS_TIER and eid not in explicit:
            continue
        path = Path(str(ent.get("path") or ""))
        if _contained(path, decisions_dir) is None:
            continue
        title = str(ent.get("title") or "")
        if eid not in explicit:
            title_cov, _ = _score(terms, title, "")
            if title_cov == 0:
                continue
        candidates.append(_Decision(id=eid, title=title, status=status, path=path, date="",
                                    backlinks=2 * backlinks.get(str(ent.get("uid") or ""), 0)
                                    + backlinks.get(eid, 0)))
        if left() <= 0:
            return None

    picked: List[_Decision] = []
    for dec in candidates:
        text = _read_text(dec.path, decisions_dir)
        if not text:
            continue
        meta, body = _frontmatter(text)
        dec.body = body
        dec.date = str(meta.get("created") or meta.get("date") or "")[:10]
        dec.paths = [p for p in meta.get("paths", []) if isinstance(p, str)] if isinstance(meta.get("paths"), list) else []
        dec.depends_on = [d for d in meta.get("depends_on", []) if isinstance(d, str)] \
            if isinstance(meta.get("depends_on"), list) else []
        title_cov, body_cov = _score(terms, dec.title, body)
        # the topic phrase in the title as a phrase ("audit chain") outweighs scattered terms
        vocab = _title_vocab(dec.title)
        phrase_hits = sum(1 for ph in set(phrases) if ph in vocab)
        dec.score = 100.0 if dec.id in explicit else 10 * title_cov + 2 * body_cov + 6 * phrase_hits
        picked.append(dec)
    if not picked:
        return None

    full = [d for d in picked if d.id in explicit or d.score >= 10 * 0.99]
    if full:
        pool = full
    else:  # partial title matches: keep only those close to the best one
        best = max(d.score for d in picked)
        pool = [d for d in picked if d.score >= 0.6 * best]
    anchored = {d.id: bool(d.paths) and any(_resolve_anchor(p, tracked) for p in d.paths[:12]) for d in pool}
    pool.sort(key=lambda d: (
        0 if d.id in explicit else 1,
        _STATUS_TIER.get(d.status, 2),
        -round(d.score, 1),
        -d.backlinks,
        0 if anchored.get(d.id) else 1,
        "".join(chr(255 - ord(c)) for c in d.date),  # newer first
        d.id,
    ))
    chosen = pool[:MAX_DECISIONS]
    # the topic as the picks define it: words shared by at least two chosen titles
    title_words = [set(_terms(d.title)) for d in chosen]
    topic = [w for w in set().union(*title_words) if len(w) >= 4 and sum(w in t for t in title_words) >= 2]
    foundation = _foundation([dep for d in chosen for dep in d.depends_on], entities, backlinks,
                             {d.id for d in chosen}, decisions_dir, topic or terms)
    if foundation is not None:
        chosen.append(foundation)

    titles = {str(e.get("id")): str(e.get("title") or "") for e in entities if e.get("type") == "decision"}
    # The most central decision carries the explanation; it gets the larger share.
    n = len(chosen)
    shares = [0.34] + [0.66 / (n - 1)] * (n - 1) if n > 1 else [1.0]
    sections: List[Section] = []
    for dec, share in zip(chosen, shares):
        if left() <= 0:
            break
        sections.append(_build_section(dec, tracked, max(600, int(budget_chars * share)),
                                       timeout=max(1.0, min(4.0, left())), titles=titles))
    if not sections:
        return None
    return {"version": PACK_VERSION, "sections": [s.to_dict() for s in sections],
            "budget_chars": budget_chars}


def _foundation(depends_on: List[str], entities: List[Dict[str, Any]], backlinks: Dict[str, int],
                taken: Set[str], decisions_dir: Path, topic: Sequence[str]) -> Optional["_Decision"]:
    """The accepted decision the picks build on that is most about the topic.

    Titles miss foundations: the audit-chain decisions build on ADR-0232 (boot
    tripwire), whose title never says "audit chain" while 200+ files cite it. Code
    citations alone favour generic foundations (the multi-tenant ADR is cited even
    more), so the score is topic density (hits per 1000 words) x log(citations)."""
    by_id = {str(e.get("id")): e for e in entities if e.get("type") == "decision"}
    best: Optional[Tuple[float, "_Decision"]] = None
    for did in dict.fromkeys(depends_on):
        ent = by_id.get(did)
        if not ent or did in taken or str(ent.get("status") or "").lower() != "accepted":
            continue
        cites = backlinks.get(did, 0)
        if cites < 10:
            continue
        path = Path(str(ent.get("path") or ""))
        text = _read_text(path, decisions_dir) if _contained(path, decisions_dir) else None
        if not text:
            continue
        meta, body = _frontmatter(text)
        low = body.lower()
        hits = sum(len(re.findall(r"\b" + re.escape(t), low)) for t in set(topic))
        words = max(200, len(body.split()))
        score = (1000 * hits / words) * math.log(cites)
        if hits and (best is None or score > best[0]):
            dec = _Decision(id=did, title=str(ent.get("title") or ""), status="accepted", path=path,
                            date=str(meta.get("created") or "")[:10], body=body)
            dec.paths = [p for p in meta.get("paths", []) if isinstance(p, str)] \
                if isinstance(meta.get("paths"), list) else []
            best = (score, dec)
    return best[1] if best else None


def _build_section(dec: _Decision, tracked: Sequence[_Tracked], limit: int, timeout: float,
                   titles: Optional[Dict[str, str]] = None) -> Section:
    resolved: List[Tuple[_Tracked, str]] = []
    for pattern in dec.paths[:16]:
        resolved.extend(_resolve_anchor(pattern, tracked)[:20])
    py_files = [(t, f) for t, f in resolved if f.endswith(".py")][:8]
    sources = {f: t.read(f) for t, f in py_files}
    sources = {f: s for f, s in sources.items() if s}

    cited = _cited_identifiers(dec.body)
    defs: List[Tuple[str, str, int, str, str]] = []  # name, file, line, sig, doc
    parsed = {f: _definitions(src) for f, src in sources.items()}
    for name in cited:
        for f in sources:
            d = parsed[f].get(name)
            if d:
                defs.append((name, f, *d))
                break
        if len(defs) >= 4:
            break

    evidence = ""
    if not dec.paths:
        truth = "unknown"
    elif not resolved:
        # declared anchors that exist outside the readable scope are "unknown", not "planned"
        truth = "unknown" if any(_anchor_exists(p, tracked) for p in dec.paths[:16]) else "planned"
    else:
        truth = "unknown"
        owner = {f: t for t, f in py_files}
        for name, f, line, _sig, _doc in defs:
            site = _call_site(owner[f], name, f, timeout)
            if site:
                truth, evidence = "live", f"{name} ({f}:{line}) is called from {site}"
                break

    # Pieces in priority order: when the budget runs out, the tail goes first.
    header = (f"[{dec.id}] {dec.title} — decision {dec.status}" + (f", {dec.date}" if dec.date else "")
              + f"; implementation: {truth}" + (f" ({evidence})" if evidence else ""))
    pieces: List[str] = []
    levels = _levels(dec.body)
    what = levels.get("structural") or _section_text(dec.body, r"decision", 360)
    why = levels.get("conceptual") or _section_text(dec.body, r"context", 360)
    how = levels.get("implementation")
    if what:
        pieces.append(("Structural: " if "structural" in levels else "Decision: ") + what[:360])
    module_docs = [(f, _module_doc(src)) for f, src in list(sources.items())[:3]]
    module_docs = [(f, d) for f, d in module_docs if d]
    if module_docs:
        f, doc = module_docs[0]
        pieces.append(f"Code {f}:1 (module docstring):\n{doc}")
    if why:
        pieces.append(("Conceptual: " if "conceptual" in levels else "Context: ") + why[:360])
    if how:
        pieces.append(f"Implementation: {how[:300]}")
    for name, f, line, sig, doc in defs:
        pieces.append(f"Code {f}:{line}: {sig}" + (f"\n  {doc[:200]}" if doc else ""))
    for f, doc in module_docs[1:]:
        pieces.append(f"Code {f}:1 (module docstring):\n{doc}")
    if titles and dec.depends_on:
        deps = [f"{d} ({titles[d][:70]})" for d in dec.depends_on[:4] if d in titles]
        if deps:
            pieces.append("Builds on: " + "; ".join(deps))
    alts = _alternatives(dec.body)
    if alts:
        pieces.append("Alternatives considered: " + "; ".join(alts))
    for sent in _number_sentences(dec.body, limit=2):
        pieces.append(f"Figure: {sent}")

    out = [scrub(header)]
    used = len(out[0])
    for piece in pieces:
        piece = scrub(piece)
        if used + 1 + len(piece) > limit:
            room = limit - used - 1
            if room >= 160 and not piece.startswith("Code "):
                out.append(piece[: room - 1].rsplit(" ", 1)[0] + "…")
            continue
        out.append(piece)
        used += 1 + len(piece)
    return Section(id=dec.id, title=scrub(dec.title), status=dec.status, date=dec.date,
                   truth=truth, evidence=scrub(evidence), text="\n".join(out))


def render_pack(pack: Dict[str, Any]) -> str:
    """The SOURCES text of a pack (what the storyboard model and the gates see)."""
    return "\n\n".join(str(s.get("text", "")) for s in pack.get("sections", []) if isinstance(s, dict))


def pack_digest(pack: Dict[str, Any]) -> str:
    return hashlib.sha256(render_pack(pack).encode("utf-8")).hexdigest()


def with_sections(pack: Dict[str, Any], keep_ids: Iterable[str]) -> Optional[Dict[str, Any]]:
    keep = set(keep_ids)
    sections = [s for s in pack.get("sections", []) if isinstance(s, dict) and s.get("id") in keep]
    if not sections:
        return None
    return {**pack, "sections": sections}


def validate_pack(pack: Any) -> Optional[Dict[str, Any]]:
    """Shape check for a pack handed over by the host; anything malformed is dropped."""
    if not isinstance(pack, dict) or pack.get("version") != PACK_VERSION:
        return None
    sections = pack.get("sections")
    if not isinstance(sections, list) or not sections or len(sections) > MAX_DECISIONS + 1:
        return None
    clean = []
    for s in sections:
        if not isinstance(s, dict):
            return None
        if not all(isinstance(s.get(k), str) for k in ("id", "title", "status", "truth", "text")):
            return None
        if not re.fullmatch(r"ADR-\d{3,4}", s["id"]) or s["truth"] not in ("live", "planned", "unknown"):
            return None
        clean.append({k: str(s.get(k, "")) for k in ("id", "title", "status", "date", "truth", "evidence", "text")})
    total = sum(len(s["text"]) for s in clean)
    if total > 2 * DEFAULT_BUDGET_CHARS:
        return None
    return {"version": PACK_VERSION, "sections": clean}
