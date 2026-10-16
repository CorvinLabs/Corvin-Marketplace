"""KB entity model — one implementation of types, discovery, links and rollups.

Every knowledge artefact is a Markdown file with YAML frontmatter. Its TYPE comes
from the directory it lives in (never from a field a writer could get wrong), its
IDENTITY is an immutable `uid` (ULID), its `id` is the human handle and may be
renumbered. Relations are typed `links:`; a target is either another entity
(id or uid) or an external URI — that is what lets any source be referenced.

Sources are declared in kb/_meta/sources.yaml. A source is a root plus a
directory→type map; a non-writable source (the legacy Corvin-ADR repo until the
cutover) is read and linked, never modified, and its findings never block.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import kb_lib as L

REPO = Path(__file__).resolve().parent.parent
KB_NAME = "Corvin-Knowledge"   # repo:Corvin-Knowledge/... resolves against this repo, wherever it is checked out

# --- schema -----------------------------------------------------------------------

DECISION_STATUS = ("proposed", "accepted", "superseded", "frozen", "rejected")
TASK_STATUS = ("open", "in_progress", "blocked", "done", "cancelled")

TYPES: dict[str, dict] = {
    "decision":   dict(prefix="ADR",     width=4, status=DECISION_STATUS),
    "concept":    dict(prefix="CONCEPT", width=4, status=DECISION_STATUS),
    "idea":       dict(prefix="IDEA",    width=4, status=DECISION_STATUS),
    "plan":       dict(prefix="PLAN",    width=4, status=DECISION_STATUS),
    "review":     dict(prefix="REVIEW",  width=4, status=("open", "addressed", "dismissed")),
    "note":       dict(prefix="NOTE",    width=4, status=None),       # a record, no lifecycle
    "initiative": dict(prefix="I",       width=2, status=None),       # status is DERIVED
    "epic":       dict(prefix="E",       width=3, status=None),       # status is DERIVED
    "task":       dict(prefix="T",       width=4, status=TASK_STATUS),
}
CONTAINERS = {"initiative", "epic"}
PARENT = {"task": ("epic", "epic"), "epic": ("initiative", "initiative")}

# Closed relation vocabulary. ADR-0264 list fields (depends_on, related, supersedes)
# stay valid on decisions and are read as links of the same rel.
RELS = {
    "implements", "depends_on", "related", "supersedes", "inspired_by", "formalized_as",
    "reviews", "derived_from", "evidence", "source", "discussed_in", "regresses",
    "search",  # G0 gate (T-0036): idea/concept deduplication via search evidence
}
LEGACY_LIST_RELS = ("depends_on", "related", "supersedes")
# Fields that are derived and must never be stored (heal removes them).
DERIVED_FIELDS = {"superseded_by", "realization", "rollup", "children", "implementation_ready"}

URI_SCHEMES = {"https", "http", "repo", "file", "commit", "session", "memory", "mailto"}
URI_RE = re.compile(r"^([a-z][a-z0-9+.-]*):(.+)$")
ID_ANY = re.compile(r"^(ADR|CONCEPT|IDEA|PLAN|REVIEW|NOTE|I|E|T)-(\d+)$")

# --- sources ----------------------------------------------------------------------


@dataclass
class Source:
    root: Path
    writable: bool
    dirs: dict[str, str]
    name: str


def _pinned_root(repo: Path, name: str, git_root: Path, ref: str, refresh: bool) -> Path:
    """A detached worktree of *git_root* at *ref*, private to the KB.

    A source must not depend on which branch somebody else has checked out in that
    repo (found 2026-10-03: a parallel session switched Corvin-ADR to a pre-migration
    branch and the KB suddenly saw 110 duplicate ids)."""
    wt = repo / ".kb-cache" / name
    if refresh:
        L.git(git_root, "fetch", "-q", "origin", check=False)
    sha = L.git(git_root, "rev-parse", ref).strip()
    if not (wt / ".git").exists():
        wt.parent.mkdir(parents=True, exist_ok=True)
        L.git(git_root, "worktree", "add", "-q", "--detach", str(wt), sha)
    elif L.git(wt, "rev-parse", "HEAD").strip() != sha:
        L.git(wt, "checkout", "-q", "--detach", sha)
    return wt


def load_sources(repo: Path = REPO, *, refresh: bool = False) -> list[Source]:
    cfg = yaml.safe_load((repo / "kb/_meta/sources.yaml").read_text())
    out = []
    for s in cfg["sources"]:
        root = (repo / s["root"]).resolve()
        if s.get("ref"):
            if not root.exists():
                continue
            root = _pinned_root(repo, s.get("name", "src"), root, s["ref"], refresh)
        out.append(Source(root, bool(s.get("writable", False)), dict(s["dirs"]), s.get("name", s["root"])))
    return out


# --- entities ---------------------------------------------------------------------


@dataclass
class Link:
    rel: str
    to: str
    external: bool


@dataclass(eq=False)   # identity: two files are never "the same entity" because their fields match
class Entity:
    path: Path
    type: str
    source: Source
    doc: L.Doc
    id: str | None = None
    uid: str | None = None
    links: list[Link] = field(default_factory=list)
    link_errors: list[str] = field(default_factory=list)

    @property
    def fm(self) -> dict:
        return self.doc.fm or {}

    @property
    def writable(self) -> bool:
        return self.source.writable

    @property
    def title(self) -> str:
        t = self.fm.get("title")
        if t:
            return str(t)
        for line in self.doc.lines[self.doc.fm_end + 1 if self.doc.fm else 0:]:
            if line.startswith("# "):
                return re.sub(r"^#\s+(?:[A-Z]+-\d+\s*[—:-]\s*)?", "", line).strip()
        return self.path.stem

    @property
    def status(self) -> str | None:
        s = self.fm.get("status")
        return None if s is None else str(s)

    @property
    def parent_id(self) -> str | None:
        p = PARENT.get(self.type)
        return str(self.fm[p[0]]) if p and self.fm.get(p[0]) else None


def id_from_name(name: str, type_: str) -> str | None:
    pre = TYPES[type_]["prefix"]
    m = re.match(rf"^{pre}-(\d+)", name)
    if not m and type_ == "decision":
        # legacy Corvin-ADR names carry the number without the prefix (`0466-…`,
        # `adr_0801_…`); without this the real ADR-0466 had no id and `kb show ADR-0466`
        # resolved to three files that merely list it in renumbered_from (review drift #7)
        m = re.match(r"^(?:adr_)?(\d{3,4})[-_]", name)
    return f"{pre}-{int(m.group(1)):0{TYPES[type_]['width']}d}" if m else None


def _links(fm: dict, type_: str) -> tuple[list[Link], list[str]]:
    out, errs = [], []
    raw = fm.get("links") or []
    if not isinstance(raw, list):
        return out, ["links is not a list"]
    for item in raw:
        if isinstance(item, dict) and "rel" in item and "to" in item:
            rel, to = str(item["rel"]), str(item["to"])
        elif isinstance(item, str) and item.split(":", 1)[0].strip() in RELS:
            rel, to = (x.strip() for x in item.split(":", 1))
        else:
            errs.append(f"link not {{rel, to}}: {item!r}")
            continue
        out.append(Link(rel, to, bool(URI_RE.match(to)) and not ID_ANY.match(to)))
    for rel in (*LEGACY_LIST_RELS, "implements"):
        out += [Link(rel, x, False) for x in L.as_list(fm.get(rel))]
    if type_ in ("task", "epic") and fm.get("depends_on") and not isinstance(fm.get("depends_on"), list):
        errs.append("depends_on is not a list")
    return out, errs


def discover(sources: list[Source] | None = None) -> list[Entity]:
    sources = sources if sources is not None else load_sources()
    ents = []
    for src in sources:
        for d, type_ in src.dirs.items():
            base = src.root / d
            if not base.is_dir():
                continue
            root = src.root.resolve()
            for p in sorted(base.glob("*.md")):
                if p.name.lower() in ("readme.md", "index.md", "_template.md"):
                    continue
                # a symlink, or a file reached through a symlinked directory, is not
                # KB content: following it let `kb heal` (run by the console) write
                # outside the repository (review S-#2)
                if p.is_symlink() or not p.resolve().is_relative_to(root):
                    continue
                doc = L.parse(p)
                fm = doc.fm or {}
                e = Entity(p, type_, src, doc)
                e.id = str(fm["id"]) if fm.get("id") else id_from_name(p.name, type_)
                e.uid = str(fm["uid"]) if fm.get("uid") else None
                e.links, e.link_errors = _links(fm, type_)
                ents.append(e)
    return ents


class Index:
    """Resolution of ids, uids and former ids. Ambiguity is reported, never resolved."""

    def __init__(self, ents: list[Entity]):
        self.ents = ents
        self.by_uid: dict[str, list[Entity]] = {}
        self.by_id: dict[str, list[Entity]] = {}
        self.alias: dict[str, set[str]] = {}
        for e in ents:
            if e.uid:
                self.by_uid.setdefault(e.uid, []).append(e)
            if e.id:
                self.by_id.setdefault(e.id, []).append(e)
            for old in L.as_list(e.fm.get("renumbered_from")):
                self.alias.setdefault(old, set()).add(e.uid or str(e.path))

    def resolve(self, ref: str) -> list[Entity]:
        ref = ref.strip()
        if ref in self.by_uid:
            return self.by_uid[ref]
        key = L.norm_id(ref) if re.fullmatch(r"ADR-\d{1,4}", ref, re.I) else ref
        hits = self.by_id.get(key or ref)
        if hits:
            live = [h for h in hits if h.status != "superseded"]
            return live or hits
        if ref in self.alias:
            return [x for u in self.alias[ref] for x in self.by_uid.get(u, [])]
        return []

    def one(self, ref: str) -> Entity | None:
        hits = self.resolve(ref)
        return hits[0] if len(hits) == 1 else None

    def children(self, parent: Entity) -> list[Entity]:
        out = []
        for e in self.ents:
            pid = e.parent_id
            if pid and parent in self.resolve(pid):
                out.append(e)
        return out


# --- rollup (CONCEPT §6.3) — a total function, never stored -------------------------

def rollup(states: list[str]) -> str:
    if not states:
        return "open"
    s = set(states)
    if s <= {"done", "cancelled"}:
        return "done" if "done" in s else "cancelled"
    if "in_progress" in s:
        return "in_progress"
    if "blocked" in s:
        return "blocked"
    if "done" in s and "open" in s:
        return "in_progress"
    return "open"


def effective_status(e: Entity, idx: Index, _seen: frozenset = frozenset(), *, regressions: bool = True) -> str:
    """The status the board shows. With regressions=False: the RECORDED state, as it was
    when the work was closed — what E20 judges a done task against (a later regression of
    a dependency does not make an earlier `done` wrong; it is the new task's business)."""
    if e.type == "task":
        if not regressions:
            return e.status or "open"
        regressed = any(
            l.rel == "regresses" and x is e
            for o in idx.ents if o.type == "task" and o.status not in ("done", "cancelled")
            for l in o.links for x in idx.resolve(l.to)
        )
        return "open" if regressed and e.status == "done" else (e.status or "open")
    if e.type in CONTAINERS:
        if e in _seen:
            return "open"
        # a SUGGESTED task (an epic's follow-up template, MESH-010) is a proposal, not part of the plan:
        # it never changes what its container reads until a human starts it
        return rollup([effective_status(c, idx, _seen | {e}, regressions=regressions) for c in idx.children(e)
                       if c.type in ("task", "epic") and not c.fm.get("suggested")])
    return e.status or "open"


REVIEW_TERMINATIONS = ("three-consecutive-zero", "max-rounds-reached", "non-convergence")


def review_rounds(review: Entity) -> list[dict]:
    """The review's rounds as written by `kb review round|calibrate` (CONCEPT-0090 §3.3).
    A malformed entry is skipped, never repaired — it simply does not count."""
    raw = review.fm.get("rounds")
    return [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []


def counted_rounds(review: Entity) -> list[dict]:
    """Rounds that count toward 3x0: calibrated ones whose seed was found. A plain round
    (calibration `none`) still records findings, and a missed seed voids its round — it
    neither counts nor resets the streak (§3.3 'Calibration, the positive control')."""
    return [r for r in review_rounds(review) if r.get("calibration") == "passed"]


def fix_defect_streak(review: Entity) -> int:
    """How many of the most recent COUNTED rounds in a row found defects in an earlier
    round's fixes (`fix_defects` > 0). Two in a row is the second non-convergence clause."""
    streak = 0
    for r in reversed(counted_rounds(review)):
        if int(r.get("fix_defects") or 0) > 0:
            streak += 1
        else:
            break
    return streak


def three_consecutive_zero(review: Entity) -> bool:
    """The last three COUNTED rounds found nothing, each under a different lead question."""
    last = counted_rounds(review)[-3:]
    return (len(last) == 3 and all(r.get("findings") == 0 for r in last)
            and len({str(r.get("lead_question", "")).strip().lower() for r in last}) == 3
            and all(str(r.get("lead_question", "")).strip() for r in last))


def reviews_of(decision: Entity, idx: Index) -> list[Entity]:
    """Review entities that `reviews` the decision. The edge goes review -> decision, the
    direction `kb review open --reviews ADR-…` writes; a decision never has to be edited
    to receive a review."""
    return [e for e in idx.ents if e.type == "review"
            and any(ln.rel == "reviews" and not ln.external and decision in idx.resolve(ln.to)
                    for ln in e.links)]


_AUDIT_CACHE: dict[str, tuple[tuple[int, int], dict]] = {}


def kb_root(path: Path) -> Path:
    """The KB repository containing `path`: the nearest ancestor with kb/_meta/sources.yaml.
    A source's root is not it when the writable source is a subdirectory (`root: kb`) or a
    pinned legacy worktree under .kb-cache/."""
    p = Path(path).resolve()
    for cand in (p, *p.parents):
        if (cand / "kb" / "_meta" / "sources.yaml").is_file():
            return cand
    return p


def audit_facts(root: Path) -> dict:
    """What kb/audit.jsonl records, cached per file state: the creating actor of each uid
    (`op: new`) and the reviews closed three-consecutive-zero by `kb review close`. Like any
    local file it can be edited — G4 also asks for kb's closing commit (closed_by_kb)."""
    p = kb_root(root) / "kb" / "audit.jsonl"
    try:
        st = p.stat()
    except OSError:
        return {"creator": {}, "closed": set()}
    key = (st.st_mtime_ns, st.st_size)
    hit = _AUDIT_CACHE.get(str(p))
    if hit and hit[0] == key:
        return hit[1]
    creator, closed = {}, set()
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        if not isinstance(r, dict):
            continue
        if r.get("op") == "new" and r.get("uid"):
            creator.setdefault(r["uid"], str(r.get("actor", "")))
        elif r.get("op") == "review_close" and r.get("terminated_reason") == "three-consecutive-zero" and r.get("uid"):
            closed.add(r["uid"])
    facts = {"creator": creator, "closed": closed}
    _AUDIT_CACHE[str(p)] = (key, facts)
    return facts


def authors_of(decision: Entity) -> set[str]:
    """The decision's authors, lower-case: the audited `kb new` actor and the `author:` field.
    Both count — a hand-set field must not replace the audited creator (review R2-A5)."""
    out = {str(decision.fm.get("author") or "").strip().lower(),
           audit_facts(decision.source.root)["creator"].get(decision.uid or "", "").strip().lower()}
    out.discard("")
    return out


_CLOSE_COMMITS: dict[tuple[str, str], bool] = {}


def closed_by_kb(review: Entity) -> bool:
    """The review's history holds the commit `kb review close` makes: subject
    `kb: <id> closed — three-consecutive-zero`, touching BOTH the review file and kb/audit.jsonl.
    A hand-appended audit line plus a hand-set verdict is caught by this; a deliberate
    imitation of kb's commit is not — everything in a local repo can be forged by its owner,
    the same attribution boundary as actor identity (ADR-2208 amendment 4)."""
    import subprocess
    root = kb_root(review.source.root)
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    key = (str(review.path), head)
    if key in _CLOSE_COMMITS:
        return _CLOSE_COMMITS[key]
    # kb's close commit: subject `kb: <id> closed — three-consecutive-zero` (the id at that time —
    # an E06 renumber or a rename later must not undo G4, hence --follow and any id) and the same
    # commit adds the review_close audit line carrying THIS review's uid
    out = subprocess.run(["git", "-C", str(root), "log", "--follow", "--format=%H%x00%s", "--",
                          str(review.path.relative_to(root))], capture_output=True, text=True)
    ok = False
    for line in out.stdout.splitlines():
        sha, _, subj = line.partition("\x00")
        if re.fullmatch(r"kb: \S+ closed — three-consecutive-zero", subj):
            diff = subprocess.run(["git", "-C", str(root), "show", "--format=", sha, "--", "kb/audit.jsonl"],
                                  capture_output=True, text=True).stdout
            ok = any(ln.startswith("+") and '"review_close"' in ln and str(review.uid) in ln for ln in diff.splitlines())
            if ok:
                break
    _CLOSE_COMMITS[key] = ok
    return ok


def review_passes_g4(review: Entity, decision: Entity) -> bool:
    """G4 as CONCEPT-0090 §3.1 states it, recomputed: the review is addressed and closed
    three-consecutive-zero AND `kb review close` recorded that closing in the audit log, the
    rounds hold the streak, and no counted reviewer is the decision's author. A hand-set
    `status`/`terminated_reason` alone never passes."""
    fm = review.fm
    if fm.get("status") != "addressed" or fm.get("terminated_reason") != "three-consecutive-zero":
        return False
    if not three_consecutive_zero(review):
        return False
    if review.uid not in audit_facts(review.source.root)["closed"] or not closed_by_kb(review):
        return False
    authors = authors_of(decision)
    return all(str(r.get("reviewer", "")).strip().lower() not in authors for r in counted_rounds(review)[-3:])


def implemented_decisions(task: Entity, idx: Index) -> list[Entity]:
    """Decisions a task implements — directly (`implements` on the task) or through its epic."""
    out = [x for ln in task.links if ln.rel == "implements" and not ln.external
           for x in idx.resolve(ln.to) if x.type == "decision"]
    for ep in [h for h in idx.resolve(task.parent_id or "") if h.type == "epic"]:
        out += [x for ln in ep.links if ln.rel == "implements" and not ln.external
                for x in idx.resolve(ln.to) if x.type == "decision"]
    seen, uniq = set(), []
    for x in out:
        if id(x) not in seen:
            seen.add(id(x))
            uniq.append(x)
    return uniq


def is_code_task(task: Entity, idx: Index) -> bool:
    """A task that implements a decision (itself or through its epic): its `done` needs G5
    evidence. The same edges `realization` counts — a task-level `implements` used to make
    the decision `built` while skipping G5."""
    return task.type == "task" and bool(implemented_decisions(task, idx))


def gate_status(decision: Entity, idx: Index) -> dict:
    """G1-G4 as booleans — the single implementation shared by `kb check` (which reports a
    failing predicate as a WARNING: these measure readiness, not consistency) and the
    derived `implementation_ready` (CONCEPT-0090 §3.1)."""
    concept_links = [ln for ln in decision.links if ln.rel in ("formalized_as", "inspired_by") and not ln.external]
    resolved = []
    for ln in concept_links:
        hits = [h for h in idx.resolve(ln.to) if h.type == "concept"]
        if len(hits) == 1:
            resolved.append(hits[0])
    g1 = bool(resolved)
    g2 = g1 and any(
        h is decision
        for c in resolved for ln in c.links if not ln.external
        for h in idx.resolve(ln.to)
    )
    # identity, never `uid == uid`: two uid-less legacy decisions compared equal (review R3-A7)
    epics = list({id(h): h for h in idx.ents if h.type == "epic"
                  for ln in h.links if ln.rel == "implements" and not ln.external
                  for hit in idx.resolve(ln.to) if hit is decision}.values())
    dec_paths = set(L.as_list(decision.fm.get("paths")))
    overlapping = [ep for ep in epics if dec_paths and set(L.as_list(ep.fm.get("paths"))) & dec_paths]
    ok_epic = overlapping[0] if overlapping else None
    g3_plan = bool(epics)
    # EVERY implementing epic must be planned (paths overlap, tasks with acceptance criteria):
    # one good epic used to wave through a second one an agent could then build (review R3-A2)
    g3_overlap = bool(epics) and len(overlapping) == len(epics)
    # every overlapping epic has at least one task, and every task has acceptance criteria —
    # an epic without tasks used to pass vacuously
    g3_tasks_ok = g3_overlap and all(
        [t for t in idx.children(ep) if t.type == "task"]
        and not [t for t in idx.children(ep) if t.type == "task" and not t.fm.get("definition_of_done")]
        for ep in overlapping)
    g3 = g3_plan and g3_overlap and g3_tasks_ok
    revs = reviews_of(decision, idx)
    # §3.1: a review `reviews` the decision AND the plan — every implementing epic
    g4 = any(review_passes_g4(r, decision) and all(
        any(ln.rel == "reviews" and not ln.external and ep in idx.resolve(ln.to) for ln in r.links) for ep in epics)
        for r in revs)
    return dict(g1=g1, g2=g2, g3=g3, g4=g4, ready=g1 and g2 and g3 and g4,
                g3_plan=g3_plan, g3_overlap=g3_overlap, g3_tasks_ok=g3_tasks_ok,
                resolved_concepts=resolved, implementing_epic=ok_epic, reviews=revs)


def implementation_ready(decision: Entity, idx: Index) -> bool:
    """Derived: true iff G1-G4 hold. Never stored (DERIVED_FIELDS) — a stored status would be
    one more writer, which is the failure mode ADR-2205 removed (CONCEPT-0090 §3.1)."""
    return gate_status(decision, idx)["ready"]


def realization(decision: Entity, idx: Index) -> str:
    """Derived: is an ADR built? From the tasks/epics that implement it, never from its own status."""
    impl = [e for e in idx.ents if e.type in ("task", "epic")
            and any(l.rel == "implements" and decision in idx.resolve(l.to) for l in e.links)]
    if not impl:
        return "unplanned" if decision.status == "accepted" else "n/a"
    r = rollup([effective_status(e, idx) for e in impl])
    return "built" if r == "done" else r


def audit_append(repo: Path, data: bytes) -> None:
    """Append pre-serialised audit lines (O_NOFOLLOW, like audit()) — the transaction records
    their hash before writing them, so recovery can cut exactly this segment."""
    import os
    if (repo / "kb").is_symlink():
        raise SystemExit("refused: kb/ is a symlink")
    fd = os.open(repo / "kb/audit.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def audit(repo: Path, rec: dict) -> None:
    """Append one record to kb/audit.jsonl — never through a symlink (O_NOFOLLOW): a
    link planted in a pulled KB redirected these appends outside the repo (review S-#3)."""
    import datetime as dt
    import os
    rec = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **rec}
    if (repo / "kb").is_symlink():
        raise SystemExit("refused: kb/ is a symlink")
    fd = os.open(repo / "kb/audit.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
