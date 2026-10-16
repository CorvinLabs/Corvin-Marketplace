#!/usr/bin/env python3
"""kb — the single entry point for the Corvin-Knowledge base.

  kb check   [--json PATH] [--strict]      rule catalogue over every source (errors block; G1-G6 warn)
  kb heal    [--dry-run] [--no-commit]      fix what is DERIVABLE, nothing else
  kb new     TYPE --title T [--epic E-001] [--initiative I-01] [--link rel=target]... [--actor A]
  kb task    ID TO [--reason R] [--dod TEXT] [--evidence k=v]...   the ONLY task status writer
  kb review  open|round|calibrate|fix|close|status   the review loop (G4); the file is the state
  kb orchestrate REF [--reviewer R --reviewer-cmd CMD] [--drafter-cmd CMD]   one resumable step: a review round, or the
                                            next stage of an idea/concept/decision's pipeline
  kb sweep   [--create-tasks]               G6 drift sweep: vanished paths/commits/evidence -> regresses task
  kb breaker status | reset KEY --reason R  circuit breakers (reset is a human action)
  kb learn   [--days N]                     classified refusals/findings by class
  kb guidance run | pending | ack | retire  learning loop -> advisory guidance -> SkillForge skill
  kb export                                 projection payload for the task manager (JSON)
  kb queue                                  the human queue: what waits for a human, and whether A2 is paused
  kb verify  --items FILE                   compare a task-manager snapshot with the export
  kb index                                  kb/graph/{entities,relations}.jsonl (generated)
  kb find    TERM... [--type T] [--status S]   search titles, ids and text across everything
  kb show    REF                            one entity: path, status, links, backlinks, children
  kb baseline [--init | --init-rule RULE | --accept RULE FILE DETAIL --reason R]   shrink-only

Autonomy (ADR-2208, CONCEPT-0090 §3): actors matching kb/_meta/autonomy.yaml agent_actors are
held to levels A1 (drafts) / A2 (build ready, non-human-required decisions) / A3 (human only)
and to circuit breakers; humans are never gated. Identity is attribution, not authentication.

Two kinds of deviation, two answers (docs/CONCEPT.md §14):
  * derivable  -> healed immediately and audited (uid, status spelling, derived fields
                  stored by hand, a container carrying a status, a later-born duplicate id)
  * semantic   -> refused at write time (task state machine, link resolution, cycles)
                  and reported; never guessed, because a guessed status IS the
                  inconsistency this KB exists to prevent.
Findings on a non-writable (legacy) source are reported, never block.
"""
from __future__ import annotations

import argparse
import hashlib
import contextlib
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

try:
    import fcntl
except ModuleNotFoundError:     # Windows: no fcntl; the lock below falls back to msvcrt
    fcntl = None
    import msvcrt

# O_NOFOLLOW does not exist on Windows; the explicit is_symlink() refusal before every open is
# then the only guard (Windows creates symlinks only with a privilege an attacker rarely has)
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True   # never leave scripts/__pycache__ in the KB working tree
import kb_lib as L  # noqa: E402
import kb_model as M  # noqa: E402

# No git hook ever runs for a kb git command (status, update-index, reset, commit-tree, update-ref
# ...): a hook inherits whatever kb holds, and a daemonizing one kept the KB locked after a
# kill (review R7-B3); kb commits are plumbing, like `git commit --no-verify`. GIT_CONFIG_PARAMETERS
# is how git passes `-c` to its own children, so it reaches every git child of this process.
os.environ["GIT_CONFIG_PARAMETERS"] = (os.environ.get("GIT_CONFIG_PARAMETERS", "") +
                                       f" 'core.hooksPath={os.devnull}'").strip()

TASK_FSM = {
    "open":        {"in_progress", "cancelled"},
    "in_progress": {"blocked", "done", "open", "cancelled"},
    "blocked":     {"in_progress", "open", "cancelled"},
    "done":        set(),      # terminal — a regression is a NEW task with `regresses:`
    "cancelled":   set(),
}
# rule -> (severity, healable)
RULES = {
    "E01_uid_missing":          ("error", True),
    "E02_uid_invalid":          ("error", False),
    "E03_uid_duplicate":        ("error", False),
    "E04_id_missing":           ("error", True),
    "E05_id_bad_format":        ("error", False),
    "E06_id_duplicate":         ("error", True),
    "E07_status_invalid":       ("error", True),
    "E08_container_has_status": ("error", True),
    "E09_derived_field_stored": ("error", True),
    "E10_parent_missing":       ("error", False),
    "E11_parent_unresolved":    ("error", False),
    "E12_link_malformed":       ("error", False),
    "E13_link_rel_unknown":     ("error", False),
    "E14_link_dangling":        ("error", False),
    "E15_link_ambiguous":       ("warning", False),
    "E16_external_link_bad":    ("error", False),
    "E17_depends_cycle":        ("error", False),
    "E18_reason_missing":       ("error", False),
    "E19_done_incomplete":      ("error", False),
    "E20_done_with_open_deps":  ("error", False),
    "E21_frontmatter_broken":   ("error", True),    # only "no_frontmatter" is healed (identity, never status)
    "E22_field_not_list":       ("error", True),
    "E23_transition_refused":   ("error", False),   # refusal: a move the task state machine forbids
    "E24_breaker_state_diverged": ("error", False), # breakers.json lost a trip the audit log records
    "W01_empty_container":      ("warning", False),
    "W02_frozen_source_written": ("warning", False),
    "G0_no_search_evidence":    ("error", False),   # refusal: a near-duplicate idea/concept without --link search=<hit>
    "G0_near_duplicate":        ("warning", False),  # check: a near-duplicate idea/concept that neither cites the
                                                     # older one (search/related/derived_from) nor says distinct_because
    # G1-G4 measure READINESS (they feed the derived implementation_ready), not consistency.
    # As errors they froze the board whenever any session wrote a proposed ADR the old way
    # (no concept, no plan yet) — an incomplete pipeline is not an inconsistent KB. They bite
    # where autonomy acts: an agent's A1 draft and an agent's A2 start are refused (see _autonomy).
    "G1_no_concept":            ("warning", False),
    "G2_no_backedge":           ("warning", False),
    "G3_no_plan":               ("warning", False),
    "G3_no_path_overlap":       ("warning", False),
    "G3_task_no_acceptance":    ("warning", False),
    "G4_no_review":             ("warning", False),  # no review entity `reviews` the decision
    "G4_not_closed":            ("warning", False),  # a review exists but did not close three-consecutive-zero
    "G5_no_evidence":           ("warning", False),  # done code task without done_evidence (pre-G5 tasks)
    "G5_evidence_invalid":      ("error", False),    # refusal: evidence missing/unprovable at `done`
    "G5_commit_not_on_main":    ("error", False),    # refusal: evidence commit not reachable from origin/main
    "G6_drift":                 ("warning", False),  # `kb sweep`: a built decision's paths/commits/evidence vanished
    "A1_wip_limit":             ("error", False),    # refusal: agent drafts over autonomy.yaml wip_limit
    "A1_incomplete_draft":      ("error", False),    # refusal: agent decision without a concept link
    "A2_not_ready":             ("error", False),    # refusal: agent starts a task of a decision not implementation_ready
    "A2_human_required":        ("error", False),    # refusal: decision is human-required (risk) and not accepted
    "A3_human_only":            ("error", False),    # refusal: an agent attempted a human-only action
    "B_breaker_open":           ("error", False),    # refusal: a tripped circuit breaker covers this action
    "R_review_refused":         ("error", False),    # refusal: kb review open/round/close rule violated
}

# Rules a developer introduced AFTER the baseline existed and may absorb ONCE with
# `kb baseline --init-rule` (in the same commit that adds the rule). Empty: every current
# error rule predates the baseline, so its findings are admitted one by one (--accept).
FRESH_RULES: frozenset[str] = frozenset()

# The closed finding_class taxonomy for `kb learn` (T-0048): every RULES code, plus a
# review round that recorded >0 findings. Unknown classes are refused at write time.
FINDING_CLASSES = frozenset(RULES) | {"REVIEW_FINDING_CONFIRMED"}


def log_finding(repo: Path, finding_class: str, *, entity_id: str | None = None,
                entity_uid: str | None = None, detail: str = "", actor: str = "kb",
                do_commit: bool = True, refusal: bool = False) -> None:
    """Classify one refusal or confirmed finding (T-0048) into kb/audit.jsonl — ids plus a
    hash of the detail, never its text (review S-#5). Committed on its own: an uncommitted
    append left the tree dirty and the record was swept into the NEXT, unrelated commit.
    Callers hold kb_lock (flock is per open file — taking it again here would deadlock)."""
    if finding_class not in FINDING_CLASSES:
        raise SystemExit(f"refused: unknown finding_class {finding_class!r} "
                         f"(not in the closed taxonomy of {len(FINDING_CLASSES)} classes)")
    rec = dict(op="finding_classified", finding_class=finding_class, actor=actor)
    if entity_id:
        rec["id"] = entity_id
    if entity_uid:
        rec["uid"] = entity_uid
    if detail:
        rec["detail_sha256"] = hashlib.sha256(detail.encode()).hexdigest()
        rec["detail_len"] = len(detail)
    transaction(repo, {}, [rec], f"kb: audit {finding_class}" + (f" ({entity_id})" if entity_id else ""),
                do_commit=do_commit)
    if refusal and is_agent(repo, actor):
        _park_on_repeat(repo, rec, actor, do_commit=do_commit)


def refuse(repo: Path, finding_class: str, msg: str, **kw) -> "NoReturn":
    """Log the refusal under its class, then refuse — with the rule's own message even when
    the audit commit itself fails (another session holding .git/index.lock): the caller must
    learn which rule it broke, not a git error."""
    try:
        log_finding(repo, finding_class, refusal=True, **kw)
    except SystemExit as exc:
        raise SystemExit(f"refused: {msg} (the refusal could not be logged: {exc.code})") from exc
    raise SystemExit(f"refused: {msg}")


# --- check ------------------------------------------------------------------------

def _f(out, rule, e, detail):
    out[rule].append(dict(file=str(e.path), id=e.id, uid=e.uid, source=e.source.name,
                          writable=e.writable, detail=detail))


def check(ents: list[M.Entity], repo: Path = M.REPO) -> dict:
    idx = M.Index(ents)
    out: dict[str, list] = defaultdict(list)
    for e in ents:
        spec = M.TYPES[e.type]
        if e.doc.fm is None:
            if e.writable:
                _f(out, "E21_frontmatter_broken", e, e.doc.fm_err)
            continue
        fm = e.fm
        if not e.uid:
            _f(out, "E01_uid_missing", e, "")
        elif not L.ULID_RE.match(e.uid):
            _f(out, "E02_uid_invalid", e, e.uid)
        if not e.id:
            _f(out, "E04_id_missing", e, "")
        elif not re.fullmatch(rf"{spec['prefix']}-\d{{{spec['width']},}}", e.id):
            _f(out, "E05_id_bad_format", e, f"{e.id} is not {spec['prefix']}-{'N' * spec['width']}")
        st = e.status
        if e.type in M.CONTAINERS:
            if "status" in fm:
                _f(out, "E08_container_has_status", e, f"status: {st} (derived, never stored)")
        elif spec["status"] is not None and (st is None or st not in spec["status"]):
            _f(out, "E07_status_invalid", e, f"{st!r} not in {spec['status']}")
        for k in M.DERIVED_FIELDS & set(fm):
            _f(out, "E09_derived_field_stored", e, k)
        if e.type in M.PARENT:
            key, ptype = M.PARENT[e.type]
            if not fm.get(key):
                _f(out, "E10_parent_missing", e, f"{e.type} needs {key}:")
            else:
                hits = [h for h in idx.resolve(str(fm[key])) if h.type == ptype]
                if len(hits) != 1:
                    _f(out, "E11_parent_unresolved", e, f"{key}: {fm[key]} -> {len(hits)} {ptype}(s)")
        for msg in e.link_errors:
            _f(out, "E12_link_malformed", e, msg)
        for ln in e.links:
            if ln.rel not in M.RELS:
                _f(out, "E13_link_rel_unknown", e, ln.rel)
            if ln.external:
                bad = external_link_error(repo, ln.to)
                if bad:
                    _f(out, "E16_external_link_bad", e, bad)
            else:
                hits = idx.resolve(ln.to)
                if not hits:
                    # legacy ADR-0264 lists cite many never-existing ids; only native ones block
                    _f(out, "E14_link_dangling", e, f"{ln.rel} -> {ln.to}")
                elif len(hits) > 1:
                    _f(out, "E15_link_ambiguous", e, f"{ln.rel} -> {ln.to} ({len(hits)} entities)")
        if st == "blocked" and not fm.get("blocked_reason"):
            _f(out, "E18_reason_missing", e, "blocked without blocked_reason")
        if st == "cancelled" and e.type == "task" and not fm.get("cancelled_reason"):
            _f(out, "E18_reason_missing", e, "cancelled without cancelled_reason")
        if e.type == "task" and st == "done":
            miss = [k for k in ("definition_of_done", "completed_at") if not fm.get(k)]
            if miss:
                _f(out, "E19_done_incomplete", e, f"missing {miss}")
            for d in open_dependencies(e, idx, recorded=True):
                _f(out, "E20_done_with_open_deps", e, f"{d.id} is {M.effective_status(d, idx, regressions=False)}")
        for k in LIST_FIELDS & set(fm):
            if fm[k] is not None and not isinstance(fm[k], list):
                _f(out, "E22_field_not_list", e, k)
        if e.type in M.CONTAINERS and not idx.children(e):
            _f(out, "W01_empty_container", e, "no children")
    # uid / id uniqueness
    for uid, hs in idx.by_uid.items():
        if len(hs) > 1:
            for h in hs:
                _f(out, "E03_uid_duplicate", h, f"{uid} in {len(hs)} files")
    for i, hs in idx.by_id.items():
        live = [h for h in hs if h.status != "superseded"]
        if len(hs) > 1 and len({h.uid for h in hs}) > 1 and len(live) > 1:
            # only the LIVE carriers are findings: a superseded sibling legitimately keeps the
            # number, and renumbering it repointed every `supersedes:` that names it (review #4)
            for h in live:
                _f(out, "E06_id_duplicate", h, f"{i} carried by {len(live)} files")
    # depends_on cycles among tasks/epics (decision cycles are adr_lint's G2)
    graph = {e.uid: [d.uid for ln in e.links if ln.rel == "depends_on" for d in idx.resolve(ln.to)
                     if d.uid and d.type in ("task", "epic")]
             for e in ents if e.uid and e.type in ("task", "epic")}
    seen, stack = set(), set()

    def dfs(u, path):
        if u in stack:
            cyc = path[path.index(u):]
            for x in cyc:
                for h in idx.by_uid.get(x, []):
                    _f(out, "E17_depends_cycle", h, " -> ".join(idx.by_uid[y][0].id or y for y in cyc))
            return
        if u in seen:
            return
        seen.add(u)
        stack.add(u)
        for v in graph.get(u, []):
            dfs(v, path + [v])
        stack.discard(u)
    for u in graph:
        dfs(u, [u])

    # G0 (T-0036): a near-duplicate idea/concept must cite the older one or say why it differs
    cands = [e for e in ents if e.type in ("idea", "concept") and e.writable and e.uid and e.fm]
    words = {e.uid: L.slug_words(e.title) for e in cands}
    born = {e.uid: str(e.fm.get("created") or "") for e in cands}
    for i, a in enumerate(cands):
        for b in cands[i + 1:]:
            if L.jaccard(words[a.uid], words[b.uid]) < G0_THRESHOLD:
                continue
            new, old = (a, b) if born[a.uid] >= born[b.uid] else (b, a)
            cites = any(ln.rel in ("search", "related", "derived_from", "supersedes") and old in idx.resolve(ln.to)
                        for ln in new.links) or any(ln.rel in ("search", "related", "derived_from", "supersedes")
                                                    and new in idx.resolve(ln.to) for ln in old.links)
            if not cites and not new.fm.get("distinct_because"):
                _f(out, "G0_near_duplicate", new, f"near {old.id} — cite it or set distinct_because")
    # G1-G4 (T-0037/T-0038/T-0042): one predicate in M.gate_status(), also behind the
    # derived implementation_ready, so the report and the badge never diverge.
    for e in ents:
        if e.type == "task" and e.status == "done" and not isinstance(e.fm.get("done_evidence"), dict) \
                and M.is_code_task(e, idx):
            _f(out, "G5_no_evidence", e, "done code task without done_evidence (a mapping; completed before G5?)")
        if e.type != "decision":
            continue
        gs = M.gate_status(e, idx)
        if not gs["g1"]:
            _f(out, "G1_no_concept", e, "no formalized_as/inspired_by link resolves to exactly one concept")
        elif not gs["g2"]:
            _f(out, "G2_no_backedge", e, f"none of {[c.id for c in gs['resolved_concepts']]} links back to {e.id}")
        if not gs["g3_plan"]:
            _f(out, "G3_no_plan", e, "no epic implements this decision")
            continue
        if not gs["g3_overlap"]:
            dec_paths = set(L.as_list(e.fm.get("paths")))
            off = sorted(ep.id for ep in idx.ents if ep.type == "epic" and any(
                ln.rel == "implements" and e in idx.resolve(ln.to) for ln in ep.links)
                and not (dec_paths & set(L.as_list(ep.fm.get("paths")))))
            _f(out, "G3_no_path_overlap", e, f"implementing epics without paths: overlapping {sorted(dec_paths)}: {off}")
            continue
        if not gs["g3_tasks_ok"]:
            kids = [t for t in idx.children(gs["implementing_epic"]) if t.type == "task"]
            no_dod = [t.id for t in kids if not t.fm.get("definition_of_done")]
            _f(out, "G3_task_no_acceptance", e,
               f"{gs['implementing_epic'].id} has no tasks" if not kids else
               f"an implementing epic has tasks without acceptance criteria: {no_dod}")
            continue
        if not gs["reviews"]:
            _f(out, "G4_no_review", e, f"{gs['implementing_epic'].id} implements this, but no review `reviews` it")
        elif not gs["g4"]:
            _f(out, "G4_not_closed", e,
               f"{[r.id for r in gs['reviews']]} did not close three-consecutive-zero (calibrated, reviewer != author)")

    _breaker_scan(repo, out, ents)
    frozen_scan(repo, out)
    base = load_baseline(repo)
    for k, v in out.items():
        for x in v:
            x["baselined"] = (k, os.path.relpath(x["file"], repo), x["detail"]) in base
    blocking = sum(1 for k, v in out.items() for x in v
                   if RULES[k][0] == "error" and x["writable"] and not x["baselined"])
    legacy = sum(1 for v in out.values() for x in v if not x["writable"])
    return dict(entities=len(ents), blocking=blocking, legacy_findings=legacy,
                baselined=sum(1 for v in out.values() for x in v if x["baselined"]),
                counts={k: len(v) for k, v in sorted(out.items())},
                native_counts={k: n for k, n in ((k, sum(1 for x in v if x["writable"])) for k, v in sorted(out.items())) if n},
                issues=out)


def _breaker_scan(repo: Path, out: dict, ents: list) -> None:
    """E24: every breaker the audit log says is tripped (trip without a later reset) must be in
    kb/_meta/breakers.json — clearing the file by a plain commit used to resume autonomy
    without the human reset the rule requires (review R2-B6)."""
    open_ = {}
    for r in _audit_records(repo):
        if r.get("op") in ("breaker_tripped", "breaker_reset"):
            key = f"{r.get('breaker_class')}:{r.get('scope')}" if r.get("scope") else str(r.get("breaker_class"))
            if r["op"] == "breaker_tripped":
                open_[key] = True
            else:
                open_.pop(key, None)
    missing = sorted(k for k in open_ if k not in breakers(repo))
    if missing:
        anchor = next((e for e in ents if e.writable), None)
        if anchor is not None:
            out["E24_breaker_state_diverged"].append(dict(
                file=str(repo / BREAKERS), id=None, uid=None, source=anchor.source.name, writable=True,
                detail=f"audited trips missing from breakers.json: {missing}"))


def projects_root(repo: Path) -> Path:
    """The directory holding the sibling repos — via git's common dir, so a linked
    worktree (e.g. under /tmp) still resolves repo:CorvinOS/... against the real tree."""
    common = L.git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir", check=False).strip()
    return Path(common).parent.parent if common else repo.parent


BASELINE = "kb/_meta/baseline.json"


def load_baseline(repo: Path) -> set[tuple[str, str, str]]:
    """Accepted pre-existing findings (pending hand work), keyed (rule, file, detail) so a
    NEW finding in an already-listed file is never hidden. Never grows: `kb baseline`
    only keeps entries that still occur — CONCEPT.md §3.7."""
    p = repo / BASELINE
    if not p.is_file():
        return set()
    return {(r, f, d) for r, rows in json.loads(p.read_text())["accepted"].items() for f, d in rows}


def write_baseline(repo: Path, *, init: bool = False, accept: tuple[str, str, str] | None = None,
                   reason: str = "", actor: str = "kb", do_commit: bool = True,
                   init_rule: str | None = None) -> dict:
    """Shrink the baseline to what still occurs; `--init` creates the first one (refused once
    one exists — re-initialising silently absorbed every new finding, review KB-core #10);
    `--accept RULE FILE DETAIL --reason` admits ONE named, currently-occurring finding,
    audited and committed, so growth is a visible decision instead of a side effect;
    `--init-rule RULE` admits EVERY currently-occurring finding of one freshly introduced rule
    (e.g. a new gate rolled out against ~1000 pre-existing decisions) — scoped to that rule only,
    so it cannot silently absorb a finding of any OTHER rule the way a second --init would."""
    with kb_lock(repo):
        res = check(M.discover(M.load_sources(repo)), repo)
        current = {(k, os.path.relpath(x["file"], repo), x["detail"]) for k, v in res["issues"].items() for x in v
                   if RULES[k][0] == "error" and x["writable"]}
        exists = (repo / BASELINE).is_file()
        old = load_baseline(repo)
        if init and exists:
            raise SystemExit("refused: a baseline exists — it only shrinks; admit one finding with --accept")
        if not init and not exists and not init_rule:
            raise SystemExit("refused: no baseline yet — `kb baseline --init` creates the first one")
        if init_rule and init_rule not in RULES:
            raise SystemExit(f"refused: {init_rule!r} is not a known rule")
        if is_agent(repo, actor):
            raise SystemExit("refused: the baseline is human-only (A3) — an agent never widens it")
        prev_doc = json.loads((repo / BASELINE).read_text()) if exists else {}
        done_rules = set(prev_doc.get("init_rules") or [])
        if init_rule:
            # once per rule, and only for a rule that is new to the baseline: re-running it was a
            # second --init — it absorbed NEW findings of new ADRs (ADR-2209/2210, 2026-10-04)
            if init_rule in done_rules:
                raise SystemExit(f"refused: --init-rule {init_rule} already ran; admit one finding with --accept")
            if init_rule not in FRESH_RULES:
                raise SystemExit(f"refused: {init_rule} is not a freshly introduced rule (FRESH_RULES in kb.py) — "
                                 "admit one finding with --accept")
            if any(k == init_rule for k, _f, _d in old):
                raise SystemExit(f"refused: {init_rule} already has baseline entries — it is not a freshly "
                                 "introduced rule; admit one finding with --accept")
            if RULES[init_rule][0] != "error":
                raise SystemExit(f"refused: {init_rule} is a warning — warnings never block, nothing to baseline")
        keep = current if init else (current & old)
        audits = []
        if init_rule:
            done_rules.add(init_rule)
            new_for_rule = {(k, f, d) for k, f, d in current if k == init_rule}
            keep = keep | new_for_rule
            audits.append(dict(op="baseline_init_rule", actor=actor, rule=init_rule, entries=len(new_for_rule)))
        if accept:
            if not reason:
                raise SystemExit("refused: --accept needs --reason")
            if accept not in current:
                raise SystemExit(f"refused: {list(accept)} is not a current blocking finding")
            keep = keep | {accept}
            audits.append(dict(op="baseline_accept", actor=actor, rule=accept[0], file=accept[1],
                               detail=accept[2], reason_sha256=hashlib.sha256(reason.encode()).hexdigest()))
        if init:
            audits.append(dict(op="baseline_init", actor=actor, entries=len(keep)))
        acc: dict[str, list[list[str]]] = {}
        for r, f, d in sorted(keep):
            acc.setdefault(r, []).append([f, d])
        prev = prev_doc
        reasons = {k: v for k, v in (prev.get("reasons") or {}).items()
                   if tuple(k.split("|", 2)) in keep}          # a dropped entry takes its reason along
        if accept:
            reasons["|".join(accept)] = reason
        text = json.dumps({"version": 1, "note": "accepted pre-existing findings; shrinks only (kb baseline)",
                           "accepted": acc, **({"reasons": reasons} if reasons else {}),
                           **({"init_rules": sorted(done_rules)} if done_rules else {})},
                          indent=1, ensure_ascii=False) + "\n"
        p = repo / BASELINE
        changed = not exists or p.read_text() != text
        sha = transaction(repo, {p: (text, None)}, audits,
                          "kb: baseline " + ("init" if init else f"init-rule {init_rule}" if init_rule
                                             else f"accept {accept[0]} {accept[1]}" if accept
                                             else f"shrink by {len(old - keep)}"),
                          do_commit=do_commit) if changed else None
        return dict(entries=len(keep), dropped=len(old - keep), added=len(keep - old), commit=sha)


def frozen_scan(repo: Path, out: dict) -> None:
    """A repo that used to hold knowledge must not grow again (W02)."""
    try:
        cfg = yaml.safe_load((repo / "kb/_meta/sources.yaml").read_text())
    except OSError:
        return
    for fz in cfg.get("frozen") or []:
        root = (repo / fz["root"]).resolve()
        at = fz.get("at")
        if not at or not (root / ".git").exists():
            continue
        refs = L.git(root, "for-each-ref", "--format=%(refname:short) %(*objectname)%(objectname)",
                     "refs/heads", "refs/remotes", "refs/tags", check=False).split("\n")
        head = L.git(root, "rev-parse", "HEAD", check=False).strip()
        if head:   # a detached HEAD carries commits no ref names
            refs.append(f"HEAD {head}")
        ported = [str(x) for x in fz.get("ported") or []]
        seen: set[str] = set()
        for line in filter(None, refs):
            name, _, sha = line.rpartition(" ")
            sha = sha[:40]   # an annotated tag: the peeled commit comes first, then the tag object
            if not name or name.endswith("/HEAD") or sha in seen:   # one finding per commit, not per ref
                continue
            seen.add(sha)
            if any(sha.startswith(x) for x in ported):
                continue
            behind = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", sha, at],
                                    capture_output=True).returncode == 0
            if behind:            # at or before the freeze (e.g. an old, already-merged branch)
                continue
            out["W02_frozen_source_written"].append(dict(
                file=str(root), id=None, uid=None, source=fz["name"], writable=False,
                detail=f"{fz['name']} {name} @ {sha[:10]} is beyond the freeze {at[:10]} — "
                       "knowledge written there is invisible to the KB; move it here"))


LIST_FIELDS = {"labels", "renumbered_from", "depends_on", "related", "supersedes", "implements",
               "paths", "docs", "commits"}


def external_link_error(repo: Path, to: str) -> str | None:
    """Why an external link target is invalid, or None. Shared by `check` and `new`, so a
    link `new` accepts can never be one `check` then blocks on (review KB-core #7)."""
    m = M.URI_RE.match(to)
    if not m or m.group(1) not in M.URI_SCHEMES:
        return f"unknown scheme: {to}"
    if m.group(1) == "repo":
        r, _, rest = m.group(2).partition("/")
        base = repo if r in (M.KB_NAME, repo.name) else projects_root(repo) / r
        if not rest or Path(rest).is_absolute() or ".." in Path(rest).parts or not (base / rest).exists():
            return f"{to} does not exist"
    return None


def open_dependencies(e: M.Entity, idx: M.Index, *, recorded: bool = False) -> list[M.Entity]:
    """Work items `e` depends on that are not done — tasks by status, epics/initiatives by
    their rollup (a task depending on an open epic is not done either, review #8). At a
    transition the board's view counts (a regressed dependency blocks a NEW done); for an
    existing `done` (E20 in check) the recorded state does — otherwise one regression task
    turned every already-closed dependent red and froze the projection (review R1-C3)."""
    return [d for ln in e.links if ln.rel == "depends_on" for d in idx.resolve(ln.to)
            if d.type in ("task", "epic", "initiative")
            and M.effective_status(d, idx, regressions=not recorded) != "done"]


# --- locking + commit ---------------------------------------------------------------

def _flock(fd: int, lock: bool) -> None:
    """Non-blocking exclusive lock / unlock of the whole kb/.lock file — flock on POSIX, a
    one-byte msvcrt region lock on Windows (same exclusion between kb processes)."""
    if fcntl is not None:
        fcntl.flock(fd, (fcntl.LOCK_EX | fcntl.LOCK_NB) if lock else fcntl.LOCK_UN)
        return
    os.lseek(fd, 0, os.SEEK_SET)
    msvcrt.locking(fd, msvcrt.LK_NBLCK if lock else msvcrt.LK_UNLCK, 1)


@contextlib.contextmanager
def kb_lock(repo: Path):
    """Exclusive KB lock. Opened O_NOFOLLOW and never truncated: `open(..., "w")` on a
    planted `kb/.lock -> <audit chain>` symlink emptied the target (review S-#1)."""
    kb = repo / "kb"
    if kb.is_symlink():
        raise SystemExit("refused: kb/ is a symlink")
    kb.mkdir(exist_ok=True)
    if (kb / ".lock").is_symlink():
        raise SystemExit("refused: kb/.lock is a symlink")
    fd = os.open(kb / ".lock", os.O_RDWR | os.O_CREAT | O_NOFOLLOW, 0o644)
    try:
        deadline = time.time() + float(os.environ.get("KB_LOCK_TIMEOUT", "120"))
        while True:
            try:
                _flock(fd, True)
                break
            except (BlockingIOError, PermissionError):   # msvcrt reports a held lock as EACCES
                if time.time() > deadline:
                    raise SystemExit("refused: the KB is locked by another kb process (or a git child it left "
                                     "running) — nothing was written; retry")
                time.sleep(0.1)
        _FLOCK_FDS.append(fd)
        # a dead writer that never wrote leaves only its lock + journal: drop them BEFORE the
        # mid-operation refusal, or a rebase started meanwhile and that lock block each other
        # forever (review R6-B3)
        _drop_unwritten_dead_lock(repo)
        _refuse_mid_operation(repo)
        _recover(repo)
        yield
    finally:
        if fd in _FLOCK_FDS:
            _FLOCK_FDS.remove(fd)
        _flock(fd, False)
        os.close(fd)


def uncommitted(repo: Path, path: Path) -> bool:
    """True when `path` differs from HEAD (staged, unstaged or untracked). A writer that
    rewrote such a file would commit the operator's unrelated, half-written edit along
    with its own change (review KB-core #6)."""
    return bool(L.git(repo, "status", "--porcelain", "--", str(path.relative_to(repo)), check=False).strip())


def _guard(repo: Path, p: Path, text: str, like: "L.Doc | None", keys: set[str] | None) -> None:
    """Refuse a write that would land outside the repository (a symlinked directory on
    the way: review-2 #4) or that changed more frontmatter than the writer meant to — the
    one check that covers every `_key_span` blind spot (review-2 #3)."""
    root = repo.resolve()
    if not p.parent.resolve().is_relative_to(root) or p.parent.resolve() != (root / p.parent.relative_to(repo)):
        raise SystemExit(f"refused: {p.relative_to(repo)} resolves outside the repository (symlinked directory)")
    if keys is None or like is None or like.fm is None:
        return
    new = L.fm_of(text)
    if new is None:
        raise SystemExit(f"refused: the edit of {p.relative_to(repo)} would break its frontmatter")
    stray = sorted(k for k in set(like.fm) | set(new) if k not in keys and like.fm.get(k) != new.get(k))
    if stray:
        raise SystemExit(f"refused: the edit of {p.relative_to(repo)} would also change {stray} — fix the file by hand")


def _refuse_mid_operation(repo: Path) -> None:
    """No KB write while a human's rebase/merge/cherry-pick is in progress, on a detached HEAD
    or with unmerged paths: a write there committed the conflict markers of kb/audit.jsonl and
    tripped stop-all against an agent (stress review R3-B4)."""
    for marker in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
        gp = _git_run(repo, "rev-parse", "--git-path", marker).stdout.strip()
        if gp and (Path(gp) if os.path.isabs(gp) else repo / gp).exists():
            raise SystemExit(f"refused: a git {marker.split('_')[0].split('-')[0].lower()} is in progress in "
                             f"{repo.name} — finish it first")
    if _git_run(repo, "symbolic-ref", "-q", "HEAD").returncode != 0 and \
            _git_run(repo, "rev-parse", "-q", "--verify", "HEAD").returncode == 0:
        raise SystemExit(f"refused: {repo.name} is on a detached HEAD — check out a branch first")
    if _git_run(repo, "ls-files", "-u").stdout.strip():
        raise SystemExit(f"refused: {repo.name} has unmerged paths — resolve them first")


def _gitpath(repo: Path, name: str) -> Path:
    """A path inside the repository's git dir — never in the worktree, so no `git add -A` can
    ever carry it into a commit (the journal used to live at kb/.txn and a human's add -A
    committed it, stress review R3-B)."""
    gp = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-path", name],
                        capture_output=True, text=True).stdout.strip()
    return Path(gp) if os.path.isabs(gp) else repo / gp


def _journal(repo: Path) -> Path:
    return _gitpath(repo, "kb-txn.json")      # present only between a transaction's first write and its commit


def _recover(repo: Path) -> None:
    """Finish what a killed writer left half-done (taken under kb_lock, before any work).
    The journal records the files' bytes and the audit size BEFORE the transaction and, once
    the writes are complete, the hashes the commit must contain. HEAD holds exactly those ->
    the commit landed, only the journal is stale. Otherwise nothing of it was committed:
    restore the files, cut the audit log back, unstage.
    Without this a kill between the audit append and the commit left a dirty task file that
    refused every later move and an audit line the next unrelated commit swept in."""
    import base64
    # (an index-sync backlog file of the previous commit primitive is obsolete)
    _gitpath(repo, "kb-idxsync.json").unlink(missing_ok=True)
    # private index files of a killed writer (under the lock none is live) — R4-B5
    gdir = _gitpath(repo, "kb-index-x").parent
    for leftover in [*gdir.glob("kb-index-*"), *gdir.glob("kb-shared-*"), *gdir.glob("kb-swap-*"),
                     *gdir.glob("kb-lockseed-*")]:
        if leftover.is_file() and not leftover.is_symlink():
            leftover.unlink(missing_ok=True)
    # a writer killed inside write_doc leaves its mkstemp file; under the lock none is live
    for src in M.load_sources(repo):
        if src.writable:
            for d in src.dirs:
                base = src.root / d
                for tmpf in base.glob(".kbw-*") if base.is_dir() else []:
                    if tmpf.is_file() and not tmpf.is_symlink():
                        tmpf.unlink(missing_ok=True)
    for tmpf in (repo / "kb").glob("**/.kbw-*"):
        if tmpf.is_file() and not tmpf.is_symlink() and ".kb-cache" not in tmpf.parts:
            tmpf.unlink(missing_ok=True)
    jp = _journal(repo)
    if not jp.is_file() or jp.is_symlink():
        return
    try:
        j = json.loads(jp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        jp.unlink(missing_ok=True)
        return
    # a writer killed while holding index.lock leaves it behind: remove it only when the journal
    # names the dead process that took it (a live git process's lock is never touched)
    lk = _gitpath(repo, "index.lock")
    lock = _IndexLock(repo)
    pid, nonce = j.get("pid"), j.get("lock_nonce")
    if lk.exists() and not lk.is_symlink() and isinstance(pid, int) and pid != os.getpid() \
            and isinstance(nonce, str) and len(nonce) >= 32:
        if not _writer_alive(pid, j.get("pid_start")):
            try:
                # the dead writer's own lock: it was BORN holding this nonce (a hard link, so never an
                # empty or half-written lock) and kb never writes into it — a git process's lock
                # holds index bytes ("DIRC…"), never the nonce (review R5-A1: an inode+ctime id was
                # invalidated by kb's own write into the lock and wedged every later write)
                if _is_our_lock(lk.read_bytes(), nonce):
                    # TAKE IT OVER, never unlink first: between an unlink and the index repair a
                    # human's commit would land on the stale index and revert kb's (review R5-B5)
                    lock.nonce, lock.held = nonce, True
            except FileNotFoundError:
                pass

    def committed() -> bool:
        """HEAD holds exactly what this transaction wrote — then its commit landed. HEAD merely
        moving proves nothing: another session commits into the same checkout."""
        cand = j.get("cand")
        if isinstance(cand, str) and re.fullmatch(r"[0-9a-f]{40}", cand) and \
                _git_ok(repo, "merge-base", "--is-ancestor", cand, "HEAD"):
            return True                                    # landed — even if HEAD moved on since (a pull)
        after = j.get("after")
        if not after:
            return False                                   # killed before the writes were complete
        for rel, h in after.items():
            out = subprocess.run(["git", "-C", str(repo), "show", f"HEAD:{rel}"], capture_output=True)
            if out.returncode != 0 or hashlib.sha256(out.stdout).hexdigest() != h:
                return False
        return True
    if not lock.held:
        try:
            lock.acquire(timeout=5.0)
        except SystemExit:
            raise SystemExit("refused: the git index is busy (index.lock) — a previous kb write is "
                             "being repaired; retry")
    if committed():
        # the commit landed but the writer died before swapping in the shared index: align it,
        # or a human's next commit would revert this one (review R4-A2)
        rels = [r for r in [*(j.get("files") or {}), "kb/audit.jsonl"] if ".." not in Path(r).parts]
        _align_index(repo, lock, rels)
    else:
        rels = _undo_planned(repo, j)
        # (a failure keeps the journal: the next lock holder retries — R3-B2)
        _align_index(repo, lock, [*rels, "kb/audit.jsonl"])
    jp.unlink(missing_ok=True)


def transaction(repo: Path, writes: dict[Path, tuple[str, "L.Doc | None"]], audits: list[dict],
                msg: str, *, do_commit: bool = True, extra_paths: list[Path] = (),
                keys: dict[Path, set[str]] | None = None) -> str | None:
    """Write files + audit records + ONE commit, all or nothing, holding the shared index.lock
    from the first write to the index swap. A file with uncommitted edits is never written
    (centrally, for every writer: reviews and guidance used to commit an operator's
    half-written edit, R4-A3). If anything fails, every file is restored and the audit log
    is cut back — unless HEAD already holds exactly this content."""
    audit_path = repo / "kb/audit.jsonl"
    for p in [*writes, audit_path]:
        if p.exists() and do_commit and uncommitted(repo, p):
            raise SystemExit(f"refused: {p.relative_to(repo)} has uncommitted edits — commit or revert them first")
    before = {p: (p.read_bytes() if p.exists() else None) for p in writes}
    for p, (text, like) in writes.items():
        # the change was computed from `like`; a commit landing between that read and this
        # snapshot would be reverted by writing it (review R6-A2)
        if like is not None and before[p] is not None and \
                before[p].decode("utf-8", "replace").lstrip("\ufeff").replace("\r\n", "\n") != like.text:
            raise SystemExit(f"refused: {p.relative_to(repo)} changed since kb read it — nothing was written; retry")
    audit_before = audit_path.read_bytes() if audit_path.exists() else None
    audit_size = len(audit_before) if audit_before is not None else None
    paths = [*writes, *extra_paths]
    for p, (text, like) in writes.items():
        _guard(repo, p, text, like, (keys or {}).get(p) if keys is not None else None)
    import base64
    jp = _journal(repo)
    if jp.is_symlink():
        raise SystemExit("refused: the kb journal is a symlink")
    jtmp = jp.with_name("kb-txn.json.tmp")
    lock = _IndexLock(repo)
    jtmp.write_text(json.dumps({"head": L.git(repo, "rev-parse", "HEAD", check=False).strip(),
                                "pid": os.getpid(), "pid_start": _proc_start(os.getpid()), "audit_size": audit_size,
                                "audit_base": _sha(audit_before), "lock_nonce": lock.nonce,
                                "files": {str(p.relative_to(repo)): (base64.b64encode(b).decode() if b is not None
                                                                     else None) for p, b in before.items()}}))
    os.replace(jtmp, jp)
    written: dict[Path, bytes] = {}
    appended = False
    try:
        if do_commit:
            lock.acquire()                    # before the first write: nobody can stage our half-written files
            # the wait for the lock can be long (a human's `git commit` with an open editor): a file
            # edited meanwhile must not be overwritten with a change computed from its old bytes
            # everything read before the lock is re-checked under it: the files, the audit log (a
            # pull meanwhile appends to it — a rollback would cut those lines), and the repository
            # state (a rebase/merge started meanwhile — review R5-B2/B3/B4)
            for p, old in before.items():
                if (p.read_bytes() if p.exists() else None) != old:
                    raise SystemExit(f"{p.relative_to(repo)} changed while kb waited for the git index — "
                                     "nothing was written; retry")
            if (audit_path.read_bytes() if audit_path.exists() else None) != audit_before:
                raise SystemExit("kb/audit.jsonl changed while kb waited for the git index — nothing was "
                                 "written; retry")
            _refuse_mid_operation(repo)
        # what kb is ABOUT to write, recorded before the first byte: recovery undoes a file only
        # while it holds exactly these bytes, the audit log only by exactly this segment (R6-A1)
        lines = "".join(json.dumps({"ts": now_iso(), **rec}, ensure_ascii=False, sort_keys=True) + "\n"
                        for rec in audits).encode("utf-8")
        jd = json.loads(jp.read_text())
        jd["planned"] = {str(p.relative_to(repo)): _sha(_doc_bytes(text, like)) for p, (text, like) in writes.items()}
        jd["audit_added"], jd["audit_added_n"] = _sha(lines), len(lines)
        jtmp.write_text(json.dumps(jd))
        os.replace(jtmp, jp)
        for p, (text, like) in writes.items():
            L.write_doc(p, text, like)
            written[p] = p.read_bytes()
            _WRITTEN.setdefault(str(repo), set()).add(str(p.resolve()))
        if lines:
            appended = True
            M.audit_append(repo, lines)
        if do_commit:   # what the commit must contain: recovery checks HEAD against it
            jd = json.loads(jp.read_text())
            jd["after"] = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in [*writes, repo / "kb/audit.jsonl"] if p.exists()}
            jtmp.write_text(json.dumps(jd))
            os.replace(jtmp, jp)
        sha = commit(repo, paths, msg, lock) if do_commit else None
        if do_commit and sha is None and audits:
            # an unchanged tree although audit lines were appended means someone else carried them:
            # never report a commit that kb did not make (review R4-A4)
            raise SystemExit("nothing was committed although audit lines were appended")
        lock.release()
        jp.unlink(missing_ok=True)
        return sha
    except BaseException as exc:
        try:
            jd = json.loads(jp.read_text()) if jp.is_file() else {}
        except ValueError:
            jd = {}
        cand = jd.get("cand")
        landed = isinstance(cand, str) and _git_ok(repo, "merge-base", "--is-ancestor", cand, "HEAD")
        if landed or jd.get("after") and all(
                hashlib.sha256(_git_run_bytes(repo, f"HEAD:{rel}")).hexdigest() == h for rel, h in jd["after"].items()):
            # the content IS in HEAD: no rollback — but the shared index must follow it, or a human's
            # next commit reverts kb's write (review R5-A2: a failed swap after update-ref)
            sha = L.git(repo, "rev-parse", "--short", "HEAD", check=False).strip()
            try:
                if not lock.held:
                    lock.acquire(timeout=5.0)
                _align_index(repo, lock, [*(jd.get("after") or {})] or [str(x.relative_to(repo)) for x in [*writes, audit_path]])
            except SystemExit as e2:
                # keep the journal: the next kb run's _recover aligns the index
                raise SystemExit(f"committed {sha}, but the git index could not be aligned ({e2.code}) — "
                                 "run `kb heal` before any git commit") from exc
            jp.unlink(missing_ok=True)
            return sha
        kept = []
        for p, old in before.items():
            if p not in written:
                continue                                   # never written by kb: nothing of ours to undo
            cur = p.read_bytes() if p.exists() else None
            if cur != written[p]:
                kept.append(str(p.relative_to(repo)))      # someone else's bytes now: never overwrite them
                continue
            if old is None:
                p.unlink(missing_ok=True)
            else:
                p.write_bytes(old)
        if not appended:
            pass                                           # no line of ours to cut
        elif audit_size is None:
            audit_path.unlink(missing_ok=True)
        elif audit_path.exists():
            with open(audit_path, "r+b") as fh:
                fh.truncate(audit_size)
        # the lock goes first, the journal last: a kill in between leaves a journal _recover can
        # finish (a no-op now), never a nonce lock with no journal naming it (R7-B2)
        lock.release()                      # held through the undo: nobody stages a half-undone file (R6-B2)
        jp.unlink(missing_ok=True)          # only now: a kill during the rollback leaves it for _recover (R6-A7)
        why = exc.code if isinstance(exc, SystemExit) else f"{type(exc).__name__}: {exc}"
        if kept:
            why = f"{why} (left untouched, edited by someone else meanwhile: {kept})"
        raise SystemExit(f"refused: write rolled back — {why}") from exc
    finally:
        lock.release()


def _git_run_bytes(repo: Path, spec: str) -> bytes:
    out = subprocess.run(["git", "-C", str(repo), "show", spec], capture_output=True)
    return out.stdout if out.returncode == 0 else b"\x00missing"


def _journal_set(repo: Path, key: str, val) -> None:
    jp = _journal(repo)
    if not jp.is_file() or jp.is_symlink():
        return
    jd = json.loads(jp.read_text())
    jd[key] = val
    tmp = jp.with_name("kb-txn.json.tmp")
    tmp.write_text(json.dumps(jd))
    os.replace(tmp, jp)


def _drop_unwritten_dead_lock(repo: Path) -> None:
    """A dead writer's journal without `planned` means it wrote NOTHING: its index.lock (held
    only to keep others from staging) and the journal are removed, nothing else is touched.
    A kb nonce lock with NO journal at all belongs to a writer that finished its undo (R7-B2):
    its body names pid + start time; dead → removed."""
    jp = _journal(repo)
    if not jp.exists():
        lk = _gitpath(repo, "index.lock")
        try:
            m = _LOCK_BODY_RE.match(lk.read_bytes()) if lk.is_file() and not lk.is_symlink() else None
        except OSError:
            m = None
        if m and not _writer_alive(int(m.group(2)), None if m.group(3) == b"-" else m.group(3).decode()):
            lk.unlink(missing_ok=True)
        return
    if not jp.is_file() or jp.is_symlink():
        return
    try:
        j = json.loads(jp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    pid, nonce = j.get("pid"), j.get("lock_nonce")
    if "planned" in j or j.get("audit_added_n") or not isinstance(pid, int) or pid == os.getpid() or not isinstance(nonce, str) \
            or len(nonce) < 32 or _writer_alive(pid, j.get("pid_start")):
        return
    lk = _gitpath(repo, "index.lock")
    try:
        if lk.exists() and not lk.is_symlink() and _is_our_lock(lk.read_bytes(), nonce):
            lk.unlink(missing_ok=True)
    except FileNotFoundError:
        pass
    jp.unlink(missing_ok=True)


def _doc_bytes(text: str, like: "L.Doc | None") -> bytes:
    """The exact bytes L.write_doc writes for `text` (its BOM / line-ending restore)."""
    nl, bom = (like.newline, like.bom) if like else ("\n", False)
    return (("\ufeff" if bom else "") + text.replace("\n", nl)).encode("utf-8")


def _sha(b: bytes | None) -> str | None:
    return None if b is None else hashlib.sha256(b).hexdigest()


def _proc_start(pid: int) -> str | None:
    """A process's start time where the OS exposes it (Linux /proc): with the pid it names ONE
    process — a reused pid is not the dead writer (review R6-A8). None elsewhere (pid only)."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat.rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def _windows_pid_alive(pid: int) -> bool:
    """os.kill(pid, 0) TERMINATES the process on Windows; ask the kernel instead."""
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ctypes.GetLastError() == 5          # ERROR_ACCESS_DENIED: alive, someone else's
    try:
        code = ctypes.c_ulong()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def _writer_alive(pid: int, start: str | None) -> bool:
    if os.name == "nt":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                                    # someone else's live process
    return not (start and _proc_start(pid) not in (None, start))


def _undo_planned(repo: Path, j: dict, written_only: bool = True) -> list[str]:
    """Undo what a transaction WROTE — judged by the hashes it recorded before writing: a file is
    restored only while it still holds kb's planned bytes, the audit log is cut only by the exact
    segment kb appended. Anything else (kb wrote nothing yet; a pull or a human changed it since)
    is left alone (review R6-A1: recovery restored a snapshot over a pulled commit)."""
    import base64
    planned = j.get("planned") or {}
    rels = []
    for rel, b64 in (j.get("files") or {}).items():
        p = repo / rel
        parts = Path(rel).parts
        if not parts or parts[0] == ".git" or ".." in parts or Path(rel).is_absolute() \
                or p.is_symlink() or not p.parent.resolve().is_relative_to(repo.resolve()) \
                or not rel.endswith((".md", ".json", ".yaml")):
            continue
        cur = p.read_bytes() if p.exists() else None
        if rel not in planned or _sha(cur) != planned[rel]:
            continue
        if b64 is None:
            p.unlink(missing_ok=True)
        else:
            p.write_bytes(base64.b64decode(b64))
        rels.append(rel)
    ap = repo / "kb/audit.jsonl"
    size, base_h, add_h, add_n = j.get("audit_size"), j.get("audit_base"), j.get("audit_added"), j.get("audit_added_n")
    if isinstance(add_n, int) and add_n > 0 and ap.is_file() and not ap.is_symlink():
        cur = ap.read_bytes()
        n0 = size if isinstance(size, int) else 0
        if _sha(cur[:n0]) == (base_h or _sha(b"")) and _sha(cur[n0:n0 + add_n]) == add_h:
            data = cur[:n0] + cur[n0 + add_n:]
            tmp = ap.with_name(".kbw-audit")
            tmp.write_bytes(data)
            os.replace(tmp, ap)
    return rels


def _align_index(repo: Path, lock: "_IndexLock", rels: list[str]) -> None:
    """Set `rels` in the shared index to HEAD while HOLDING index.lock: the repaired index is built
    in a copy and renamed over `index`, then the lock goes — no window in which a human's
    commit could use the stale index (review R5-B5). A failure releases the lock and raises."""
    shared = _gitpath(repo, f"kb-shared-{os.getpid()}")
    try:
        if lock.index.is_file():
            shared.write_bytes(lock.index.read_bytes())
        env = {**os.environ, "GIT_INDEX_FILE": str(shared), "GIT_CONFIG_COUNT": "1",
               "GIT_CONFIG_KEY_0": "core.splitIndex", "GIT_CONFIG_VALUE_0": "false"}
        r = _git_run(repo, "reset", "-q", "HEAD", "--", *rels, env=env) if lock.index.is_file() \
            else _git_run(repo, "read-tree", "HEAD", env=env)
        if r.returncode:
            lock.release()
            raise SystemExit(f"refused: the git index could not be repaired ({r.stderr.strip()[:120]}) — retry")
        lock.swap_in(shared.read_bytes())
    finally:
        shared.unlink(missing_ok=True)


def _lock_body(nonce: str, pid: int | None = None, start: str | None = None) -> bytes:
    if pid is None:
        pid, start = os.getpid(), _proc_start(os.getpid())
    return f"kb-lock {nonce} {pid} {start or '-'}\n".encode()


_LOCK_BODY_RE = re.compile(rb"^kb-lock ([0-9a-f]{48}) (\d+) (\S+)\n$")


def _is_our_lock(body: bytes, nonce: str) -> bool:
    m = _LOCK_BODY_RE.match(body)
    return bool(m) and m.group(1).decode() == nonce


class _IndexLock:
    """<git-dir>/index.lock held the way `git commit` holds it — from before kb writes its first
    file until the shared index is swapped in. A human's `git add`/`git commit` meanwhile
    fails cleanly on the lock instead of staging kb's half-written files or committing a
    stale index that reverts kb's commit (review R4-A1).

    The lock is created by hard-linking a file that already holds a random nonce: it exists
    either not at all or with its full body, and kb never writes into it — the new index is
    written to its own file and renamed over `index`. So a dead writer's lock is recognised
    by content alone, at every kill point (review R5-A1)."""

    def __init__(self, repo: Path):
        self.repo = repo
        self.path = _gitpath(repo, "index.lock")
        self.index = _gitpath(repo, "index")
        self.nonce = os.urandom(24).hex()
        self.held = False

    def acquire(self, timeout: float = 15.0) -> None:
        seed = _gitpath(self.repo, f"kb-lockseed-{os.getpid()}")
        seed.unlink(missing_ok=True)
        fd = os.open(seed, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, _lock_body(self.nonce))
            os.fsync(fd)
        finally:
            os.close(fd)
        deadline = time.time() + timeout
        try:
            while True:
                try:
                    os.link(seed, self.path)         # atomic, exclusive, born with its body
                    self.held = True
                    return
                except FileExistsError:
                    if time.time() > deadline:
                        raise SystemExit("refused: another git process holds the index (index.lock) — nothing "
                                         "was written; retry")
                    time.sleep(0.1)
        finally:
            seed.unlink(missing_ok=True)

    def swap_in(self, data: bytes) -> None:
        tmp = _gitpath(self.repo, f"kb-swap-{os.getpid()}")
        fd = os.open(tmp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o644)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, self.index)                  # atomic: the new index or the old one, never neither
        self.release()

    def release(self) -> None:
        if self.held:
            self.held = False
            try:
                if _is_our_lock(self.path.read_bytes(), self.nonce):
                    self.path.unlink(missing_ok=True)
            except FileNotFoundError:
                pass


_FLOCK_FDS: list[int] = []          # the kb_lock fd(s) held by this process


def _git_run(repo: Path, *args: str, env: dict | None = None, inp: str | None = None,
             keep_lock: bool = False) -> subprocess.CompletedProcess:
    # the `update-ref` child inherits the kb flock (keep_lock): a SIGKILLed kb whose update-ref
    # is still running keeps the KB locked until it exits — recovery never judges a commit that
    # is about to land (R6-B4). ONLY that child: a hook or fsmonitor that daemonizes would keep
    # the lock for its lifetime (R7-A6). Windows has no fd inheritance by number (pass_fds is
    # POSIX-only): there the lock ends with kb itself.
    return subprocess.run(["git", "-C", str(repo), "-c", f"core.hooksPath={os.devnull}", *args],
                          capture_output=True, text=True, env=env, input=inp,
                          pass_fds=tuple(_FLOCK_FDS) if keep_lock and os.name != "nt" else ())


def commit(repo: Path, paths: list[Path], msg: str, lock: "_IndexLock") -> str | None:
    """Commit exactly `paths` + kb/audit.jsonl while holding the shared index.lock: the commit is
    built in a private GIT_INDEX_FILE seeded from HEAD (the operator's staged work never rides
    along), landed by `update-ref HEAD <new> <old>` (compare-and-swap), and the shared index —
    a copy of it with only these paths refreshed — is swapped in through the lock right after.
    No hooks run (commit-tree), so no long window for an orphaned commit (R3-B3)."""
    rel = sorted({str(p.relative_to(repo)) for p in paths} | {"kb/audit.jsonl"})
    priv = _gitpath(repo, f"kb-index-{os.getpid()}")
    shared = _gitpath(repo, f"kb-shared-{os.getpid()}")
    name = os.environ.get("KB_ACTOR_NAME", "kb")
    mail = os.environ.get("KB_ACTOR_EMAIL", "kb@corvin.local")
    base = {**os.environ, "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": mail,
            "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": mail}
    # a split index would expire (delete) the shared index's sharedindex file (review R5-A6)
    base.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.splitIndex", "GIT_CONFIG_VALUE_0": "false"})
    penv, senv = {**base, "GIT_INDEX_FILE": str(priv)}, {**base, "GIT_INDEX_FILE": str(shared)}

    def stage(env: dict) -> None:
        for f in rel:
            r = (_git_run(repo, "update-index", "--add", "--", f, env=env) if (repo / f).exists()
                 else _git_run(repo, "update-index", "--force-remove", "--", f, env=env))
            if r.returncode:
                raise SystemExit(f"git update-index failed for {f}: {r.stderr.strip()[:200]}")
    new = None
    try:
        for _attempt in range(8):
            old = _git_run(repo, "rev-parse", "-q", "--verify", "HEAD").stdout.strip()
            r = _git_run(repo, "read-tree", *(["HEAD"] if old else ["--empty"]), env=penv)
            if r.returncode:
                raise SystemExit(f"git read-tree failed: {r.stderr.strip()[:200]}")
            stage(penv)
            tree = _git_run(repo, "write-tree", env=penv).stdout.strip()
            if old and tree == _git_run(repo, "rev-parse", f"{old}^{{tree}}").stdout.strip():
                return None                      # nothing to commit: HEAD already holds this content
            r = _git_run(repo, "commit-tree", tree, *(["-p", old] if old else []), "-F", "-", env=penv, inp=msg)
            if r.returncode:
                raise SystemExit(f"git commit-tree failed: {r.stderr.strip()[:200]}")
            cand = r.stdout.strip()
            # the shared index to swap in: the CURRENT one (it may hold the operator's staged work)
            # with only kb's paths refreshed — built before the ref moves, swapped right after
            if lock.index.is_file():
                shared.write_bytes(lock.index.read_bytes())
            else:
                _git_run(repo, "read-tree", *(["HEAD"] if old else ["--empty"]), env=senv)
            stage(senv)
            # the swap targets the BRANCH ref and refuses a HEAD that is no longer on one (plumbing can
            # detach it without the index lock); a rebase cannot start while kb holds index.lock (R4-B3)
            branch = _git_run(repo, "symbolic-ref", "-q", "HEAD").stdout.strip()
            if not branch:
                raise SystemExit("HEAD is not on a branch — commit not made")
            _journal_set(repo, "cand", cand)     # recovery: landed iff cand is in HEAD's history (R7-A2)
            r = _git_run(repo, "update-ref", "-m", msg.splitlines()[0][:120], branch, cand, old or "0" * 40,
                         keep_lock=True)
            if r.returncode == 0:
                new = cand
                lock.swap_in(shared.read_bytes())
                break
            if old == _git_run(repo, "rev-parse", "-q", "--verify", "HEAD").stdout.strip():
                raise SystemExit(f"git update-ref failed: {r.stderr.strip()[:200]}")
            # HEAD moved (a push into this checkout, plumbing): rebuild on the new HEAD
        else:
            raise SystemExit("git: HEAD kept moving — commit not made")
    finally:
        priv.unlink(missing_ok=True)
        shared.unlink(missing_ok=True)
    return _git_run(repo, "rev-parse", "--short", new).stdout.strip()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# --- autonomy A0-A3 + circuit breakers (CONCEPT-0090 §3.2/§3.6, T-0046/T-0047) ---------
#
# Identity is ATTRIBUTION, not security: an actor names itself (--actor / KB_ACTOR). These
# rules hold an honest agent to its level and stop a runaway loop; a process that lies
# about who it is can write files anyway (the same boundary CorvinOS draws for plugins).

AUTONOMY = "kb/_meta/autonomy.yaml"
BREAKERS = "kb/_meta/breakers.json"
BREAKER_CLASSES = ("human_queue_age", "drift_area_pause", "repeated_refusal_park",
                   "postcondition_failure", "budget_window")
# always agents, whatever autonomy.yaml says — a broken or edited file can never turn the
# KB's own automata into humans (fail-closed)
DEFAULT_AGENT_ACTORS = ("agent:*", "kb-orchestrator", "kb-guidance", "kb-sweep")
DEFAULT_LEAD_QUESTIONS = ("correctness", "concurrency and races",
                          "what the docs claim versus the code", "failure paths")


def load_autonomy(repo: Path) -> dict | None:
    """Read at EVERY autonomous transition, never cached: an edit takes effect on the next
    attempt. Missing or malformed -> None, and every agent action is refused."""
    try:
        cfg = yaml.safe_load((repo / AUTONOMY).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(cfg, dict) or not isinstance(cfg.get("agent_actors"), list):
        return None
    return cfg


def is_agent(repo: Path, actor: str) -> bool:
    """Case-insensitive; `agent`, `agent:x`, `Agent-x` and `agent_x` are agents (`agentur-x` is
    not). The default actor
    `kb` is a human — a caller acting autonomously must say so (KB_ACTOR); the KB's own
    automata (orchestrator, sweep, guidance) always do."""
    import fnmatch
    cfg = load_autonomy(repo)
    pats = list(DEFAULT_AGENT_ACTORS) + ["agent", "agent:*", "agent-*", "agent_*"] + \
        [str(x) for x in ((cfg or {}).get("agent_actors") or [])]
    a = (actor or "").lower()
    return any(fnmatch.fnmatchcase(a, pt.lower()) for pt in pats)


def human_required(decision: M.Entity, cfg: dict) -> bool:
    """§3.2: a decision is human-required when its `risk:` names a human-required trigger.
    A MISSING `risk:` is human-required (fail-closed); so is a value the file does not know.
    `risk: []` is the explicit statement 'nothing human-required here'."""
    if "risk" not in decision.fm or not isinstance(decision.fm.get("risk"), list):
        return True
    hr = {str(x) for x in (cfg.get("human_required_risks") or [])}
    ok = {str(x) for x in (cfg.get("autonomous_risks") or [])}
    return any(str(r) in hr or str(r) not in ok for r in decision.fm["risk"])


def _audit_records(repo: Path):
    p = repo / "kb/audit.jsonl"
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _ts(rec: dict) -> "dt.datetime | None":
    try:
        t = dt.datetime.fromisoformat(str(rec.get("ts", "")))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def breakers(repo: Path) -> dict:
    try:
        d = json.loads((repo / BREAKERS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d.get("tripped") or {} if isinstance(d, dict) else {}


def _write_breakers(repo: Path, tripped: dict, audits: list[dict], msg: str, do_commit: bool) -> None:
    text = json.dumps({"version": 1, "note": "circuit breakers (CONCEPT-0090 §3.6) — written only by kb.py",
                       "tripped": tripped}, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    transaction(repo, {repo / BREAKERS: (text, None)}, audits, msg, do_commit=do_commit)


def trip(repo: Path, cls: str, *, actor: str, scope: str = "", detail: str = "",
         extra: dict | None = None, do_commit: bool = True) -> bool:
    """Trip a breaker (idempotent). Every trip is an audited, committed event."""
    if cls not in BREAKER_CLASSES:
        raise SystemExit(f"refused: unknown breaker class {cls!r}")
    tr = breakers(repo)
    key = f"{cls}:{scope}" if scope else cls
    if key in tr:
        # already tripped: a later regression task of the same area joins the record, so the
        # reset waits for ALL of them (it used to know only the first one)
        add = [t for t in (extra or {}).get("regression_tasks") or [] if t not in tr[key].get("regression_tasks", [])]
        if add:
            tr[key]["regression_tasks"] = list(tr[key].get("regression_tasks", [])) + add
            _write_breakers(repo, tr, [dict(op="breaker_extended", breaker_class=cls, scope=scope, actor=actor,
                                            regression_tasks=add)], f"kb: breaker {key} + {add}", do_commit)
        return False
    rec = dict(cls=cls, scope=scope, tripped_at=now_iso(), by=actor, **(extra or {}))
    if detail:
        rec["detail_sha256"] = hashlib.sha256(detail.encode()).hexdigest()
    tr[key] = rec
    _write_breakers(repo, tr, [dict(op="breaker_tripped", breaker_class=cls, scope=scope, actor=actor,
                                    **({"detail_sha256": rec["detail_sha256"]} if detail else {}))],
                    f"kb: breaker {key} tripped", do_commit)
    return True


def breaker_reset(repo: Path, key: str, *, actor: str, reason: str, do_commit: bool = True) -> dict:
    """Resuming after a trip is a HUMAN action (§3.6); the budget window resets by itself."""
    with kb_lock(repo):
        if is_agent(repo, actor):
            refuse(repo, "A3_human_only", f"{actor} may not reset a breaker — resuming is a human action",
                   actor=actor, do_commit=do_commit)
        if not reason:
            raise SystemExit("refused: a breaker reset needs --reason")
        tr = breakers(repo)
        if key not in tr:
            raise SystemExit(f"refused: no tripped breaker {key!r} (tripped: {sorted(tr)})")
        b = tr[key]
        if b["cls"] == "budget_window":
            raise SystemExit("refused: the budget breaker resets with its window — raise the budget in "
                             "autonomy.yaml (human) instead")
        if b["cls"] == "drift_area_pause" and b.get("regression_tasks"):
            idx = M.Index(M.discover(M.load_sources(repo)))
            open_ = [t for t in b["regression_tasks"] if any(
                M.effective_status(x, idx) not in ("done", "cancelled") for x in idx.resolve(t))]
            if open_:
                raise SystemExit(f"refused: the drift area stays paused until its regression tasks are done: {open_}")
        del tr[key]
        _write_breakers(repo, tr, [dict(op="breaker_reset", breaker_class=b["cls"], scope=b.get("scope", ""),
                                        actor=actor, reason_sha256=hashlib.sha256(reason.encode()).hexdigest())],
                        f"kb: breaker {key} reset", do_commit)
        return dict(reset=key, remaining=sorted(tr))


def _park_on_repeat(repo: Path, rec: dict, actor: str, *, do_commit: bool) -> None:
    """Repeated refusal (§3.6): the same class refusing the same proposal twice parks it."""
    key = rec.get("id") or rec.get("detail_sha256")
    if not key:
        return
    seen = sum(1 for r in _audit_records(repo) if r.get("op") == "finding_classified"
               and r.get("finding_class") == rec["finding_class"]
               and (r.get("id") or r.get("detail_sha256")) == key and is_agent(repo, str(r.get("actor", ""))))
    if seen >= 2:
        trip(repo, "repeated_refusal_park", actor=actor, scope=str(key), detail=rec["finding_class"],
             do_commit=do_commit)


def _agent_drafts(repo: Path, idx: M.Index) -> int:
    """Undecided A1 drafts created by agents: proposed idea/concept/decision/plan, open review."""
    uids = {r.get("uid") for r in _audit_records(repo)
            if r.get("op") == "new" and is_agent(repo, str(r.get("actor", "")))}
    n = 0
    for u in uids:
        for e in idx.by_uid.get(u, []):
            if (e.type in ("idea", "concept", "decision", "plan") and e.status == "proposed") or \
               (e.type == "review" and e.status == "open"):
                n += 1
    return n


def _int(v) -> int:
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return 0


def budget_usage(repo: Path, hours: float) -> dict:
    """What agents used in the rolling window, counted ONLY from audited records: `writes` (every
    agent record that is not a breaker/finding bookkeeping op), `proposals` (agent `new`), and
    the `elapsed_s` / `tokens` a review round recorded about its reviewer run (3.6)."""
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    use = dict(writes=0, proposals=0, wall_clock_seconds=0, tokens=0)
    for r in _audit_records(repo):
        if not is_agent(repo, str(r.get("actor", ""))) or (_ts(r) or since) <= since:
            continue
        if r.get("op") not in ("finding_classified", "breaker_tripped", "breaker_reset", "breaker_extended"):
            use["writes"] += 1
        if r.get("op") == "new":
            use["proposals"] += 1
        use["wall_clock_seconds"] += _int(r.get("elapsed_s"))
        use["tokens"] += _int(r.get("tokens"))
    return use


BUDGET_LIMITS = (("writes", "max_autonomous_writes", 200), ("proposals", "max_proposals", None),
                 ("wall_clock_seconds", "max_wall_clock_seconds", None), ("tokens", "max_tokens", None))


def _budget_open(repo: Path, cfg: dict, actor: str, do_commit: bool) -> bool:
    """Budget window: agent writes, proposals, wall-clock and tokens in the rolling window.
    Trips at the first limit reached (a limit that is not configured is not enforced), and
    resets BY ITSELF once the window has rolled past (the one breaker that does)."""
    b = cfg.get("budget") or {}
    hours = float(b.get("window_hours", 24))
    used = budget_usage(repo, hours)
    tr = breakers(repo)
    for key, name, default in BUDGET_LIMITS:
        limit = b.get(name, default)
        if limit is not None and used[key] >= int(limit):
            trip(repo, "budget_window", actor=actor, detail=f"{key} {used[key]}/{int(limit)} in {hours}h",
                 do_commit=do_commit)
            return True
    if "budget_window" in tr:
        del tr["budget_window"]
        _write_breakers(repo, tr, [dict(op="breaker_reset", breaker_class="budget_window", scope="",
                                        actor="window")], "kb: breaker budget_window reset (window rolled)",
                        do_commit)
    return False


def human_queue_items(repo: Path, idx: M.Index, cfg: dict) -> list[dict]:
    """Items waiting for a human (3.6 'Human queue'), oldest first: implementation_ready decisions
    that are human-required and not yet accepted (`decision`), escalated reviews (`review`) and
    escalated tasks - incidents (`incident`). `since` is when the wait started, `hours` its age."""
    now = dt.datetime.now(dt.timezone.utc)

    def since(v) -> str:
        try:
            t = dt.datetime.fromisoformat(str(v))
        except ValueError:
            return now.isoformat()
        return (t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)).isoformat()

    out = []

    def add(e: M.Entity, kind: str, v) -> None:
        sv = since(v)
        out.append(dict(id=e.id, uid=e.uid, kind=kind, title=e.title, since=sv,
                        hours=round((now - dt.datetime.fromisoformat(sv)).total_seconds() / 3600, 4)))
    for e in idx.ents:
        if e.type == "decision" and e.writable and e.status == "proposed" and human_required(e, cfg) \
                and M.implementation_ready(e, idx):
            add(e, "decision", e.fm.get("created", ""))
        if e.type == "review" and e.writable and e.status == "open" \
                and e.fm.get("terminated_reason") in ("max-rounds-reached", "non-convergence"):
            rounds = M.review_rounds(e)
            add(e, "review", rounds[-1].get("at", "") if rounds else e.fm.get("created", ""))
        if e.type == "task" and e.writable and e.status in ("open", "blocked") \
                and "escalated" in L.as_list(e.fm.get("labels")):
            add(e, "incident", e.fm.get("created", ""))        # an incident waiting for a human
    return sorted(out, key=lambda x: -x["hours"])


def human_queue(repo: Path, idx: M.Index, cfg: dict) -> list[tuple[str, float]]:
    """`(id, age in hours)` of everything in the human queue, oldest first."""
    return [(x["id"], x["hours"]) for x in human_queue_items(repo, idx, cfg)]


def queue_status(repo: Path) -> dict:
    """`kb queue`: the human queue plus whether A2 is paused by it - what the board banner shows."""
    idx = M.Index(M.discover(M.load_sources(repo)))
    cfg = load_autonomy(repo) or {}
    items = human_queue_items(repo, idx, cfg)
    max_age = float(cfg.get("human_queue_max_age_hours", 72))
    return dict(queue=items, max_age_hours=max_age,
                paused=bool(items and items[0]["hours"] > max_age) or "human_queue_age" in breakers(repo))


CROSS_FILE_RULES = frozenset({"E03_uid_duplicate", "E06_id_duplicate", "E11_parent_unresolved",
                              "E14_link_dangling", "E15_link_ambiguous", "E17_depends_cycle",
                              "E20_done_with_open_deps", "E24_breaker_state_diverged"})
_PRE_STAMPS: dict[str, dict] = {}   # (mtime_ns, size) of every KB file before an agent's write
_WRITTEN: dict[str, set] = {}       # absolute paths kb wrote in this process, per repo (postcondition scope)
_PRE_BLOCKING: dict[str, set] = {}   # blocking findings before an agent's write, per repo (one process = one write)


def _kb_stamps(repo: Path) -> dict:
    out = {}
    for src in M.load_sources(repo):
        for d in src.dirs:
            base = src.root / d
            if base.is_dir():
                for f in base.rglob("*.md"):
                    try:
                        st = f.stat()
                    except OSError:
                        continue
                    out[str(f.resolve())] = (st.st_mtime_ns, st.st_size)
    return out


def _blocking_keys(repo: Path) -> set:
    res = check(M.discover(M.load_sources(repo)), repo)
    return {(k, x["file"], x["detail"]) for k, v in res["issues"].items() for x in v
            if RULES[k][0] == "error" and x["writable"] and not x["baselined"]}


def _autonomy(repo: Path, actor: str, level: str, *, idx: M.Index, decisions: list[M.Entity] = (),
              proposal: str | None = None, wip: bool = True, do_commit: bool = True) -> None:
    """Refuse an AGENT's action that its level does not allow; humans pass untouched.
    `autonomy.yaml` is read here, on every attempt (T-0046)."""
    if not is_agent(repo, actor):
        return
    _PRE_BLOCKING[str(repo)] = _blocking_keys(repo)
    _PRE_STAMPS[str(repo)] = _kb_stamps(repo)
    cfg = load_autonomy(repo)
    if cfg is None:
        refuse(repo, "A3_human_only", f"{AUTONOMY} is missing or malformed — every agent action is refused "
               "(fail-closed)", actor=actor, do_commit=do_commit)
    if level == "A3":
        refuse(repo, "A3_human_only", f"{actor} attempted a human-only (A3) action", actor=actor,
               do_commit=do_commit)
    tr = breakers(repo)
    stop = [k for k, b in tr.items() if b.get("cls") == "postcondition_failure"]
    if stop:
        refuse(repo, "B_breaker_open", f"postcondition breaker {stop} stops every autonomous write until a "
               "human resets it (kb breaker reset)", actor=actor, do_commit=do_commit)
    if _budget_open(repo, cfg, actor, do_commit):
        refuse(repo, "B_breaker_open", "the autonomous-write budget for this window is used up",
               actor=actor, do_commit=do_commit)
    if proposal and f"repeated_refusal_park:{proposal}" in tr:
        refuse(repo, "B_breaker_open", f"{proposal} is parked after a repeated refusal — escalated to a human",
               actor=actor, do_commit=do_commit)
    if level == "A1" and wip:
        n, limit = _agent_drafts(repo, idx), int(cfg.get("wip_limit", 10))
        if n >= limit:
            refuse(repo, "A1_wip_limit", f"{n} undecided agent drafts >= wip_limit {limit} — amend or close "
                   "your drafts first", actor=actor, do_commit=do_commit)
    if level == "A2":
        q = human_queue(repo, idx, cfg)
        max_age = float(cfg.get("human_queue_max_age_hours", 72))
        if (q and q[0][1] > max_age) or "human_queue_age" in tr:
            if q and q[0][1] > max_age:
                trip(repo, "human_queue_age", actor=actor, detail=f"{q[0][0]} waits {q[0][1]:.0f}h",
                     do_commit=do_commit)
            refuse(repo, "B_breaker_open", f"the human queue is too old ({q[:3]}) — A2 pauses until a human "
                   "works it and resets the breaker", actor=actor, do_commit=do_commit)
        if not decisions:
            refuse(repo, "A2_not_ready", "the task implements no decision — A2 builds implementation_ready "
                   "decisions only", actor=actor, do_commit=do_commit)
        for d in decisions:
            if not M.implementation_ready(d, idx):
                refuse(repo, "A2_not_ready", f"{d.id} is not implementation_ready (G1-G4)", entity_id=d.id,
                       entity_uid=d.uid, actor=actor, do_commit=do_commit)
            if human_required(d, cfg) and d.status != "accepted":
                refuse(repo, "A2_human_required", f"{d.id} is human-required (risk: {d.fm.get('risk', 'missing')}) "
                       "and not accepted", entity_id=d.id, entity_uid=d.uid, actor=actor, do_commit=do_commit)
            dp = set(L.as_list(d.fm.get("paths")))
            for k, b in tr.items():
                if b.get("cls") == "drift_area_pause" and dp & set(b.get("paths") or []):
                    refuse(repo, "B_breaker_open", f"{d.id} touches a drift area ({k}) — paused until its "
                           "regression task is done and a human resets it", actor=actor, do_commit=do_commit)


def _postcondition(repo: Path, actor: str, do_commit: bool) -> None:
    """After an agent write: `kb check` must still be blocking 0 and the audit log must parse;
    otherwise everything stops (§3.6 'Postcondition failure')."""
    if not is_agent(repo, actor):
        return
    bad = []
    for n, line in enumerate((repo / "kb/audit.jsonl").read_text(encoding="utf-8").splitlines(), 1):
        try:
            if line.strip():
                json.loads(line)
        except json.JSONDecodeError:
            bad.append(f"audit line {n} does not parse")
            break
    # only findings THIS write introduced: a human's uncommitted work-in-progress (or any red
    # state that was already there) used to trip stop-all and blame the agent for it
    before = _PRE_BLOCKING.pop(str(repo), None)
    # ... minus findings on files SOMEONE ELSE changed during the write: a human's save or a pull
    # landing in the same second is not the agent's doing (R6-B5); a finding the write causes on an
    # UNCHANGED file (a done task whose dependency it reopened) still counts (R7-A1)
    mine = _WRITTEN.get(str(repo), set())
    stamps = _PRE_STAMPS.pop(str(repo), None) or {}
    now = _kb_stamps(repo)
    foreign = {f for f in set(now) | set(stamps) if now.get(f) != stamps.get(f) and f not in mine}
    # a CROSS-FILE finding (a duplicate id/uid, a dangling or ambiguous link, a cycle, an open
    # dependency) is the pair's, not the agent's, as soon as anything else changed meanwhile —
    # a pull bringing another host's NOTE-N names the agent's own file (review R7-B1)
    new = {k for k in _blocking_keys(repo) - (before if before is not None else set())
           if str(Path(k[1]).resolve()) not in foreign and not (foreign and k[0] in CROSS_FILE_RULES)}
    if new:
        bad.append(f"kb check gained {len(new)} blocking finding(s): {sorted({k for k, _f, _d in new})}")
    if bad:
        trip(repo, "postcondition_failure", actor=actor, detail="; ".join(bad), do_commit=do_commit)
        raise SystemExit(f"refused: postcondition failed after {actor}'s write ({'; '.join(bad)}) — "
                         "every autonomous write is stopped until a human resets the breaker")


def _incident(repo: Path, actor: str, what: str, *, subject: str, do_commit: bool) -> "NoReturn":
    """A postcondition failed after an autonomous write (3.6): trip `postcondition_failure`
    (everything stops until a human resets it), file a NOTE naming the incident and an escalated
    TASK so it reaches the human queue, then refuse. Called with the KB lock held. The records
    are made by `kb-incident`, which is not an agent - an agent's breaker must not stop the
    incident from being written down. The audit carries the hash of `what`, the note carries it."""
    newly = trip(repo, "postcondition_failure", actor=actor, detail=what, do_commit=do_commit)
    if newly:
        # the trip above is what stops the automaton; the records below are best-effort so a
        # misconfigured incident epic can never mask the failure itself
        title = f"Postcondition failure after {actor}'s write: {subject}"[:140]
        try:
            _new_locked(repo, "note", title, fields=None, links=[], do_commit=do_commit, actor="kb-incident",
                        body=f"## Incident\n\n{actor} claimed work that does not hold: {what}.\n\n"
                             "Every autonomous write is stopped until a human resets the breaker "
                             "(`kb breaker reset postcondition_failure --reason ...`).\n")
            cfg = load_autonomy(repo) or {}
            epic = str(cfg.get("incident_epic") or "").strip()
            if epic:
                _new_locked(repo, "task", f"Escalated: {subject}"[:140],
                            fields={"epic": epic, "labels": ["escalated"],
                                    "definition_of_done": f"a human reviewed the incident ({what[:120]}) and reset "
                                                          "the postcondition_failure breaker"},
                            links=[], body="", do_commit=do_commit, actor="kb-incident")
        except SystemExit:
            pass
    raise SystemExit(f"refused: postcondition failed after {actor}'s write ({what}) - every autonomous "
                     "write is stopped until a human resets the breaker")


def _claim_postcondition(repo: Path, actor: str, claim: dict, *, subject: str, do_commit: bool) -> None:
    """After an AGENT claimed work (a review fix, a code task done): the claimed commit must be on
    its repo's origin/main and the claimed test must fail with the commit's non-test changes
    removed (3.6 'a commit not on origin/main, a test not reaching a fix'). Humans pass."""
    if not is_agent(repo, actor):
        return
    wd = Path(claim["workdir"]) if claim.get("workdir") else repo
    bad = None
    if not commit_on_main(wd, str(claim["commit"])):
        bad = f"claimed commit {str(claim['commit'])[:9]} is not on origin/main of {wd.name}"
    elif claim.get("check_test", True):
        result, observed = _mutation_check(repo, claim, 900)
        if result != "pinned":
            bad = f"the claimed test does not reach the fix: {observed}"
    if bad:
        _incident(repo, actor, bad, subject=subject, do_commit=do_commit)


GROWTH_SIGNALS = ("out_of_scope_finding", "epic_follow_up", "note_promoted")
_SAFE_REF = re.compile(r"[A-Za-z0-9_./-]{1,80}")


def _growth_audit(repo: Path, signal: str, *, actor: str, source: str, created: str, do_commit: bool) -> None:
    """One audited `growth_signal` record: which signal made which draft (3.5). Ids only."""
    transaction(repo, {}, [dict(op="growth_signal", signal=signal, actor=actor, source=source, created=created)],
                f"kb: growth signal {signal} -> {created}", do_commit=do_commit)


def _out_of_scope_ideas(repo: Path, r: M.Entity, n: int, findings: list[dict], scope: set[str], *, actor: str,
                        do_commit: bool, limit: int = 3) -> list[str]:
    """3.5: a CONFIRMED finding outside the reviewed files is not this review's business - it
    becomes a proposed idea that cites its source. One idea per (review, file, class), at most
    `limit` per round; a draft the autonomy gates refuse (WIP, budget) is skipped, never forced.
    Called with the KB lock held. The idea names the class and the path, never the finding text."""
    made: list[str] = []
    for x in findings:
        rel = str(x.get("file") or "")
        if rel in scope or len(made) >= limit:
            continue
        cls = str(x.get("class") or "finding")
        cls = cls if re.fullmatch(r"[A-Za-z0-9_-]{1,40}", cls) else "finding"
        where = rel if _SAFE_REF.fullmatch(rel) else "(unnamed location)"
        key = hashlib.sha256(f"{r.uid}|{rel}|{cls}".encode()).hexdigest()[:12]
        idx = M.Index(M.discover(M.load_sources(repo)))
        if any(e.type == "idea" and e.fm.get("growth_key") == key for e in idx.ents):
            continue
        try:
            made_idea = _new_locked(
                repo, "idea", f"Out-of-scope finding in {r.id}: {cls} at {where}"[:140],
                fields={"growth_key": key, "growth_signal": "out_of_scope_finding",
                        "distinct_because": "raised by a confirmed review finding outside the reviewed scope"},
                links=[("derived_from", r.uid)],
                body=f"## Idea\n\nA confirmed finding of {r.id} round {n} lies outside the files that review "
                     "covers, so it is not that review's to fix. The reproduction and the observed result are "
                     "in the review file.\n", do_commit=do_commit, actor=actor)
        except SystemExit:
            continue
        _growth_audit(repo, "out_of_scope_finding", actor=actor, source=r.id, created=made_idea["id"],
                      do_commit=do_commit)
        made.append(made_idea["id"])
    return made


def _apply_follow_up(repo: Path, task_uid: str, *, actor: str, do_commit: bool) -> list[str]:
    """3.5 / MESH-010: when the last task of an epic is done and the epic carries a `follow_up`
    template list, create each template as a SUGGESTED task (`suggested: true`: outside the
    epic's rollup, invisible to agents until a human starts it - suggest, never set). Once per
    epic (`follow_up_created`). Called with the KB lock held, after the task's own commit."""
    idx = M.Index(M.discover(M.load_sources(repo)))
    t = idx.one(task_uid)
    ep = next(iter(idx.resolve(t.parent_id)), None) if t is not None and t.parent_id else None
    if ep is None or ep.type != "epic" or not ep.writable or ep.fm.get("follow_up_created"):
        return []
    templates = [x for x in (ep.fm.get("follow_up") or []) if isinstance(x, dict) and str(x.get("title", "")).strip()]
    if not templates or M.effective_status(ep, idx, regressions=False) != "done":
        return []
    made = []
    for tpl in templates:
        nt = _new_locked(repo, "task", f"Suggested: {str(tpl['title']).strip()}"[:140],
                         fields={"epic": ep.id, "suggested": True,
                                 "definition_of_done": str(tpl.get("dod") or "decide whether this follow-up is wanted")},
                         links=[("derived_from", ep.uid)], body="", do_commit=do_commit, actor=actor)
        _growth_audit(repo, "epic_follow_up", actor=actor, source=ep.id, created=nt["id"], do_commit=do_commit)
        made.append(nt["id"])
    fresh = M.Index(M.discover(M.load_sources(repo)))
    ep2 = fresh.one(ep.uid)
    transaction(repo, {ep2.path: (L.fm_set(ep2.doc.text, "follow_up_created", json.dumps(now_iso())), ep2.doc)},
                [dict(op="follow_up_applied", actor=actor, id=ep2.id, uid=ep2.uid, created=made)],
                f"kb: {ep2.id} follow-ups suggested {made}", do_commit=do_commit, keys={ep2.path: {"follow_up_created"}})
    return made


# --- heal -------------------------------------------------------------------------

def _next_number(ents, type_) -> int:
    pre = M.TYPES[type_]["prefix"]
    nums = [int(m.group(2)) for e in ents if e.type == type_ and e.id
            for m in [M.ID_ANY.match(e.id)] if m and m.group(1) == pre]
    return max(nums, default=0) + 1


def _fmt_id(type_, n) -> str:
    return f"{M.TYPES[type_]['prefix']}-{n:0{M.TYPES[type_]['width']}d}"


def _birth_ms(repo: Path, path: Path) -> int:
    """The file's git birth (first commit) in ms — the same on every host, so two hosts healing
    the same file mint the same uid (the checkout mtime differs per clone, review R3-A8).
    An uncommitted file falls back to its mtime: heal never commits it anyway."""
    b = _born(repo, path)
    return int(b * 1000) if b != float("inf") else int(path.stat().st_mtime * 1000)


def _born(repo: Path, path: Path) -> float:
    out = L.git(repo, "log", "--diff-filter=A", "--follow", "--format=%ct", "--", str(path), check=False).split()
    return float(out[-1]) if out else float("inf")


def heal(repo: Path, *, dry_run: bool = False, do_commit: bool = True, actor: str = "kb-heal") -> dict:
    """Up to three passes: a fix can expose the next derivable finding (a file that got
    frontmatter is then checked for its status spelling)."""
    total, commits, skipped, own = [], [], set(), set()
    for _ in range(1 if dry_run else 3):
        r = _heal_once(repo, dry_run=dry_run, do_commit=do_commit, actor=actor, own=own)
        own |= {repo / f["file"] for f in r["fixes"]}   # --no-commit: our own earlier pass is not foreign WIP
        total += r["fixes"]
        skipped |= set(r.get("skipped_uncommitted") or ())
        if r["commit"]:
            commits.append(r["commit"])
        if not r["fixes"]:
            break
    return dict(fixed=len(total), fixes=total, commit=commits[-1] if commits else None,
                commits=commits, dry_run=dry_run, skipped_uncommitted=sorted(skipped))


def _heal_once(repo: Path, *, dry_run: bool, do_commit: bool, actor: str, own: set | None = None) -> dict:
    with kb_lock(repo):
        ents = M.discover(M.load_sources(repo))
        res = check(ents, repo)
        fixes, touched = [], {}
        by_path = {str(e.path): e for e in ents}

        tkeys: dict[Path, set[str]] = {}
        key_of = {"E01_uid_missing": "uid", "E04_id_missing": "id", "E07_status_invalid": "status",
                  "E08_container_has_status": "status"}

        def edit(e, rule, fn, before, after, keys=None):
            text = touched.get(e.path, e.doc.text)
            new = fn(text)
            if new != text:
                touched[e.path] = new
                tkeys.setdefault(e.path, set()).update(keys or {key_of.get(rule, "")})
                fixes.append(dict(rule=rule, uid=e.uid, id=e.id, file=str(e.path.relative_to(repo)),
                                  before=before, after=after))

        for rule, items in res["issues"].items():
            if not RULES[rule][1]:
                continue
            for it in items:
                e = by_path.get(it["file"])
                if e is None or not e.writable or it.get("baselined"):
                    continue
                if rule == "E21_frontmatter_broken":
                    if it["detail"] != "no_frontmatter" or e.type == "decision":
                        # broken YAML is a judgement; a decision without frontmatter is ADR-2108 B.5
                        # hand work (status from its text, number from its name) — never a new number
                        continue
                    nid = e.id or _fmt_id(e.type, _next_number(ents, e.type))
                    e.id = nid
                    uid = L.ulid(_birth_ms(repo, e.path), f"{e.path.relative_to(repo)}|{nid}")
                    head = f"---\nid: {nid}\nuid: {uid}\ntitle: {json.dumps(e.title, ensure_ascii=False)}\n---\n"
                    edit(e, rule, lambda t, h=head: h + t, None, nid)
                elif rule == "E01_uid_missing":
                    uid = L.ulid(_birth_ms(repo, e.path), f"{e.path.relative_to(repo)}|{e.id}")
                    edit(e, rule, lambda t, u=uid: L.fm_set(t, "uid", u, after="id"), None, uid)
                elif rule == "E04_id_missing":
                    if e.type == "decision":   # an ADR's number is its name's; never mint a new one
                        continue
                    nid = _fmt_id(e.type, _next_number(ents, e.type))
                    e.id = nid
                    edit(e, rule, lambda t, v=nid: L.fm_set(t, "id", v, after="---"), None, nid)
                elif rule == "E07_status_invalid":
                    st = e.status
                    spec = M.TYPES[e.type]["status"]
                    mapped = None
                    if st is not None:
                        low = st.strip().lower().replace("-", "_").replace(" ", "_")
                        mapped = low if low in spec else (L.STATUS_MAP.get(low) if spec == M.DECISION_STATUS else None)
                    if mapped:   # only a deterministic spelling fix; a missing/unknown status is never invented
                        edit(e, rule, lambda t, v=mapped: L.fm_set(t, "status", v), st, mapped)
                elif rule == "E22_field_not_list":
                    v = e.fm.get(it["detail"])
                    if isinstance(v, (str, int)) and str(v).strip():   # a lone scalar -> [scalar]; anything else is judgement
                        edit(e, rule, lambda t, k=it["detail"], x=str(v): L.fm_set(t, k, L.yaml_list([x])), v, [str(v)],
                             {it["detail"]})
                elif rule == "E08_container_has_status":
                    edit(e, rule, lambda t: L.fm_remove(t, "status"), e.status, None)
                elif rule == "E09_derived_field_stored":
                    edit(e, rule, lambda t, k=it["detail"]: L.fm_remove(t, k), it["detail"], None, {it["detail"]})
                elif rule == "E06_id_duplicate":
                    if e.status == "superseded" or not e.doc.fm:   # history / no frontmatter: judgement, not derivable
                        continue
                    # later-born keeps nothing: it is renumbered, the old id kept in renumbered_from
                    group = [x for x in ents if x.id == e.id and x.status != "superseded"]
                    # ADR-2113: the first-COMMITTED file keeps the number; a read-only source always
                    # keeps it (it cannot be renumbered); an uncommitted file is born last.
                    keeper = next((x for x in group if not x.writable), None) or min(
                        group, key=lambda x: (_born(repo, x.path), str(x.path)))
                    if e is keeper:
                        continue
                    nid = _fmt_id(e.type, _next_number(ents, e.type))
                    old = e.id
                    e.id = nid
                    # from the CURRENT text (an E22 fix may already have listed a scalar) and as a
                    # list — map(str, "IDEA-0077") split the alias into characters (review R3-A4)
                    edit(e, rule, lambda t, v=nid, o=old: L.fm_set(
                        L.fm_set(t, "id", v), "renumbered_from",
                        L.yaml_list(sorted({*L.as_list((L.fm_of(t) or {}).get("renumbered_from")), o}))), old, nid,
                         {"id", "renumbered_from"})
        skipped = []
        if not dry_run and touched:
            for p in list(touched):
                if p not in (own or set()) and uncommitted(repo, p):   # never sweep an operator's half-written edit into a heal commit
                    del touched[p]
                    skipped.append(str(p.relative_to(repo)))
            fixes = [f for f in fixes if str(repo / f["file"]) in {str(p) for p in touched}]
        if not dry_run and touched:
            sha = transaction(repo, {p: (t, by_path[str(p)].doc) for p, t in touched.items()},
                              [dict(op="heal", actor=actor, **fx) for fx in fixes],
                              f"kb: heal {len(fixes)} derivable deviation(s)\n\n" +
                              "\n".join(f"- {f['rule']} {f['id']}: {f['before']} -> {f['after']}" for f in fixes),
                              do_commit=do_commit, keys={p: tkeys.get(p, set()) for p in touched})
        else:
            sha = None
        return dict(fixed=len(fixes), fixes=fixes, commit=sha, dry_run=dry_run, skipped_uncommitted=skipped)


# --- new ----------------------------------------------------------------------------

TEMPLATE_BODY = {
    "decision": "## Context\n\n## Decision\n\n## Consequences\n",
    "concept": "## Context\n\n## The Method\n\n## When to use / When NOT to use\n\n## Evidence\n\n## Operator Notes\n",
    "idea": "## Idea\n\n## Why\n",
    "plan": "## Goal\n\n## Steps\n\n## Verification\n",
    "review": "## Scope\n\n## Findings\n\n## Verdict\n",
    "note": "",
    "initiative": "## Goal\n",
    "epic": "## Goal\n",
    "task": "## Notes\n",
}


G0_THRESHOLD = 0.5   # title Jaccard (slug words) at or above which a new idea/concept is a near-duplicate


def _g0_check(repo: Path, type_: str, title: str, links: list[tuple[str, str]], ents: list, idx: M.Index,
              *, actor: str, do_commit: bool, distinct_because: str = "") -> None:
    """G0 dedupe (T-0036, CONCEPT-0090 §3.1): a new idea/concept NEAR an existing one (title
    similarity >= G0_THRESHOLD) must cite the hit it examined with `--link search=<id>`; one
    with no near hit passes. Requiring a search link for EVERY idea (the first G0 cut) broke
    the CI suite and taught authors to cite anything."""
    if type_ not in ("idea", "concept"):
        return
    words = L.slug_words(title)
    near = sorted(((L.jaccard(words, L.slug_words(e.title)), e) for e in ents
                   if e.type in ("idea", "concept") and e.uid), key=lambda x: (-x[0], x[1].id or ""))
    near = [(sc, e) for sc, e in near if sc >= G0_THRESHOLD]
    if not near:
        return
    cited = {x.uid for r, t in links if r == "search" for x in idx.resolve(t)}
    if not any(e.uid in cited for _sc, e in near) and not str(distinct_because or "").strip():
        refuse(repo, "G0_no_search_evidence",
               f"a new {type_} is near {[(e.id, round(sc, 2)) for sc, e in near[:5]]} — examine the hit and "
               "cite it with --link search=<id>, say why it differs with --distinct-because TEXT, or amend it "
               "if it is the same thing",
               detail=f"new {type_} {title}", actor=actor, do_commit=do_commit)


def new(repo: Path, type_: str, title: str, *, fields: dict | None = None, links: list[tuple[str, str]] = (),
        body: str = "", do_commit: bool = True, actor: str = "kb") -> dict:
    if type_ not in M.TYPES:
        raise SystemExit(f"unknown type {type_}; one of {sorted(M.TYPES)}")
    with kb_lock(repo):
        res = _new_locked(repo, type_, title, fields=fields, links=links, body=body,
                          do_commit=do_commit, actor=actor)
        _postcondition(repo, actor, do_commit)
        return res


def _new_locked(repo: Path, type_: str, title: str, *, fields: dict | None, links, body: str,
                do_commit: bool, actor: str) -> dict:
    sources = M.load_sources(repo)
    ents = M.discover(sources)
    idx = M.Index(ents)
    native = next(s for s in sources if s.writable)
    d = next(k for k, v in native.dirs.items() if v == type_)
    nid = _fmt_id(type_, _next_number(ents, type_))
    uid = L.ulid(int(time.time() * 1000), f"{nid}|{title}|{time.time_ns()}")
    fields = dict(fields or {})
    # A1 (agents draft), A3 (an agent never opens an initiative: that is prioritisation)
    if is_agent(repo, actor):
        level = "A3" if type_ == "initiative" or (type_ == "decision" and fields.get("status") not in
                                                  (None, "proposed")) else "A1"
        _autonomy(repo, actor, level, idx=idx, proposal=hashlib.sha256(f"new {type_} {title}".encode()).hexdigest(),
                  wip=type_ in ("idea", "concept", "decision", "plan", "review"), do_commit=do_commit)
        if type_ == "decision" and not any(r in ("inspired_by", "formalized_as") for r, _t in links):
            refuse(repo, "A1_incomplete_draft", "an agent's decision draft must name its concept "
                   "(--link inspired_by=CONCEPT-…, G1)", detail=f"new decision {title}", actor=actor,
                   do_commit=do_commit)
    _g0_check(repo, type_, title, links, ents, idx, actor=actor, do_commit=do_commit,
              distinct_because=str(fields.get("distinct_because") or ""))
    kw = dict(detail=f"new {type_} {title}", actor=actor, do_commit=do_commit)
    # MESH-009 (3.5): a concept/idea drafted FROM an agent note is that note's promotion. Only a
    # human promotes - what an agent wrote down is not yet knowledge until a human says so
    promoted = [h for rel, to in links if rel == "derived_from" and type_ in ("concept", "idea")
                for h in idx.resolve(to) if h.type == "note"]
    if promoted and is_agent(repo, actor):
        refuse(repo, "A3_human_only", f"{actor} attempted to promote {promoted[0].id} - a note becomes a "
               f"{type_} only by a human's decision (A3)", **kw)
    for rel, to in links:
        if rel not in M.RELS:
            refuse(repo, "E13_link_rel_unknown", f"unknown rel {rel!r}", **kw)
        if not M.URI_RE.match(to) or M.ID_ANY.match(to):
            n_hits = len(idx.resolve(to))
            if n_hits != 1:
                refuse(repo, "E14_link_dangling" if n_hits == 0 else "E15_link_ambiguous",
                       f"link {rel} -> {to} resolves to {n_hits} entities", **kw)
        elif (err := external_link_error(repo, to)):
            refuse(repo, "E16_external_link_bad", f"link {rel} -> {err}", **kw)
    if type_ in M.PARENT:
        key, ptype = M.PARENT[type_]
        if not fields.get(key):
            refuse(repo, "E10_parent_missing", f"a {type_} needs --{key}", **kw)
        hits = [h for h in idx.resolve(fields[key]) if h.type == ptype]
        if len(hits) != 1:
            refuse(repo, "E11_parent_unresolved", f"{key} {fields[key]} resolves to {len(hits)} {ptype}(s)", **kw)
        # a new child reopens every DONE container above it; a done task that depends on one of
        # them would turn the KB red (E20) — refuse here instead (review R7-A1)
        chain, c = [], hits[0]
        while c is not None and c not in chain:
            chain.append(c)
            c = next(iter(idx.resolve(c.parent_id)), None) if c.parent_id else None
        for c in chain:
            if fields.get("suggested") or M.effective_status(c, idx, regressions=False) != "done":
                continue
            deps = sorted(x.id for x in idx.ents if x.type == "task" and x.status == "done"
                          and any(ln.rel == "depends_on" and c in idx.resolve(ln.to) for ln in x.links))
            if deps:
                refuse(repo, "E20_done_with_open_deps",
                       f"{c.id} is done and {deps} (done) depend on it — a new {type_} would reopen it; "
                       "put the work under a new epic", **kw)
    fm = {"id": nid, "uid": uid, "title": title}
    st = M.TYPES[type_]["status"]
    want = fields.pop("status", None)
    if want is not None:
        # `new --status done` used to skip the task state machine (no DoD, no deps) and
        # `new epic --status …` stored a container status E08 forbids (review KB-core #2)
        if type_ in ("task", "epic", "initiative") or st is None:
            raise SystemExit(f"refused: a new {type_} has no settable status"
                             + (" — it starts open; move it with `kb task`" if type_ == "task" else ""))
        if want not in st:
            raise SystemExit(f"refused: {want!r} is not a {type_} status {tuple(st)}")
        if type_ == "review" and want != "open":
            raise SystemExit("refused: a review starts open; only `kb review close` sets addressed")
    if st:
        fm["status"] = want or st[0]
    fm["created"] = now_iso()
    fm.update(fields)
    if links:
        fm["links"] = [{"rel": r, "to": t} for r, t in links]
    if type_ == "decision":
        for k in ("depends_on", "related", "supersedes", "paths", "docs", "commits"):
            fm.setdefault(k, [])
    text = "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=100) + \
           f"---\n\n# {nid} — {title}\n\n" + (body or TEMPLATE_BODY[type_])
    if L.fm_of(text) != json.loads(json.dumps(fm, default=str)):
        # a value carrying a line that reads as the closing `---` ended the frontmatter early:
        # committed, the KB turned red (E21) and the board stopped (review R3-A3)
        raise SystemExit("refused: a field value contains a frontmatter delimiter line (---) — rephrase it")
    slug = L.kebab(title)
    if len(slug) > 60:
        slug = slug[:61].rsplit("-", 1)[0]
    path = repo / native.root.relative_to(repo) / d / f"{nid}-{slug.strip('-')}.md"
    if path.exists() or path.is_symlink():
        raise SystemExit(f"refused: {path.relative_to(repo)} already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    audits = [dict(op="new", actor=actor, type=type_, id=nid, uid=uid, file=str(path.relative_to(repo)))]
    for note in promoted:   # the note records it: the backlink is the derived_from edge, the audit names who
        audits += [dict(op="note_promoted", actor=actor, id=note.id, uid=note.uid, promoted_to=nid),
                   dict(op="growth_signal", signal="note_promoted", actor=actor, source=note.id, created=nid)]
    sha = transaction(repo, {path: (text, None)}, audits,
                      f"kb: new {type_} {nid} — {title}", do_commit=do_commit)
    return dict(id=nid, uid=uid, file=str(path), commit=sha)


# --- review loop (T-0041/T-0042/T-0045, CONCEPT-0090 §3.3) ------------------------------
#
# A review is an entity AND the loop's resume state: every round is appended to its file.
# Only `kb review close` sets `addressed`, and only for three consecutive CALIBRATED zero
# rounds under different lead questions by a reviewer who is not the decision's author.

def _one_review(idx: M.Index, ref: str) -> M.Entity:
    hits = [h for h in idx.resolve(ref) if h.type == "review"]
    if len(hits) != 1:
        raise SystemExit(f"refused: {ref} resolves to {len(hits)} review(s)")
    if not hits[0].writable:
        raise SystemExit(f"refused: {hits[0].id} lives in a read-only source")
    return hits[0]


def _reviewed(r: M.Entity, idx: M.Index) -> list[M.Entity]:
    return [x for ln in r.links if ln.rel == "reviews" and not ln.external for x in idx.resolve(ln.to)]


def _reviewed_decisions(r: M.Entity, idx: M.Index) -> list[M.Entity]:
    """The decisions a review is about: reviewed directly, or implemented by a reviewed epic."""
    out = []
    for x in _reviewed(r, idx):
        if x.type == "decision":
            out.append(x)
        elif x.type == "epic":
            out += [d for ln in x.links if ln.rel == "implements" and not ln.external
                    for d in idx.resolve(ln.to) if d.type == "decision"]
    return list({id(d): d for d in out}.values())


def decision_authors(d: M.Entity) -> set[str]:
    """Who wrote the decision (lower-case): the audited `kb new` actor AND an `author:` field —
    a hand-set field never replaces the audited creator (review R2-A5)."""
    return M.authors_of(d)


def review_open(repo: Path, title: str, targets: list[str], *, actor: str = "kb", do_commit: bool = True) -> dict:
    if not targets:
        raise SystemExit("refused: a review needs --reviews <decision|epic> (the edge goes review -> artifact)")
    return new(repo, "review", title, links=[("reviews", t) for t in targets], actor=actor, do_commit=do_commit)


def _check_open(repo: Path, r: M.Entity, actor: str, do_commit: bool) -> None:
    if r.status != "open" or r.fm.get("terminated_reason"):
        refuse(repo, "R_review_refused", f"{r.id} is {r.status}"
               + (f" ({r.fm['terminated_reason']})" if r.fm.get("terminated_reason") else "") + " — no more rounds",
               entity_id=r.id, entity_uid=r.uid, actor=actor, do_commit=do_commit)


def _append_round(repo: Path, r: M.Entity, rnd: dict, *, actor: str, body_add: str = "",
                  do_commit: bool, usage: dict | None = None) -> str | None:
    rounds = M.review_rounds(r) + [rnd]
    value = "\n" + yaml.safe_dump(rounds, sort_keys=False, allow_unicode=True, width=100).rstrip()
    text = L.fm_set(r.doc.text, "rounds", value, after="status")
    if body_add:
        text = text.rstrip("\n") + "\n\n" + body_add.rstrip("\n") + "\n"
    audits = [dict(op="review_round", actor=actor, id=r.id, uid=r.uid, n=rnd["n"], findings=rnd["findings"],
                   calibration=rnd["calibration"], reviewer=rnd["reviewer"], **(usage or {}))]
    if rnd["findings"] > 0:
        det = f"{r.id}:round={rnd['n']}:findings={rnd['findings']}"
        audits.append(dict(op="finding_classified", finding_class="REVIEW_FINDING_CONFIRMED", actor=actor,
                           id=r.id, uid=r.uid, detail_sha256=hashlib.sha256(det.encode()).hexdigest(),
                           detail_len=len(det)))
    return transaction(repo, {r.path: (text, r.doc)}, audits,
                       f"kb: {r.id} round {rnd['n']} findings={rnd['findings']} calibration={rnd['calibration']}",
                       do_commit=do_commit, keys={r.path: {"rounds"}})


def _round_limit(repo: Path, r: M.Entity, actor: str, do_commit: bool) -> None:
    cfg = load_autonomy(repo) or {}
    if len(M.review_rounds(r)) >= int(cfg.get("max_review_rounds", 8)):
        refuse(repo, "R_review_refused", f"{r.id} reached max_review_rounds — close it (escalates to a human)",
               entity_id=r.id, entity_uid=r.uid, actor=actor, do_commit=do_commit)


ACTOR_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._@-]{0,63}")


def _check_reviewer(reviewer: str) -> None:
    """The reviewer is an identity (it goes into kb/audit.jsonl): actor-shaped, no free text."""
    if not ACTOR_RE.fullmatch(reviewer.strip()):
        raise SystemExit("refused: --reviewer must be an actor id like agent:claude-1 (letters, digits, :._@-)")


def review_round(repo: Path, ref: str, *, lead_question: str, reviewer: str, findings: int,
                 actor: str = "kb", delay: float = 0.0, do_commit: bool = True) -> dict:
    """Record an UNCALIBRATED round (calibration: none). It keeps the findings on file but
    never counts toward 3x0 — only `kb review calibrate` produces a counting round."""
    if not lead_question.strip() or not reviewer.strip():
        raise SystemExit("refused: a round needs --lead-question and --reviewer")
    _check_reviewer(reviewer)
    if findings < 0:
        raise SystemExit("refused: --findings must be >= 0")
    with kb_lock(repo):
        idx = M.Index(M.discover(M.load_sources(repo)))
        r = _one_review(idx, ref)
        _autonomy(repo, actor, "A1", idx=idx, wip=False, do_commit=do_commit)
        _check_open(repo, r, actor, do_commit)
        _round_limit(repo, r, actor, do_commit)
        if delay:
            time.sleep(delay)
        rnd = dict(n=len(M.review_rounds(r)) + 1, lead_question=lead_question.strip(), reviewer=reviewer.strip(),
                   findings=int(findings), calibration="none", at=now_iso())
        sha = _append_round(repo, r, rnd, actor=actor, do_commit=do_commit)
        _postcondition(repo, actor, do_commit)
        return dict(id=r.id, round=rnd["n"], findings=rnd["findings"], calibration="none", commit=sha)


# Registered calibration defects: (kind, applies-to-suffix, mutate(lines) -> (lines, line_no) | None).
# Mutation testing applied to the reviewer: a realistic defect, no marker the reviewer could grep.

def _mut_compare(lines: list[str]):
    swap = {" <= ": " < ", " < ": " <= ", " >= ": " > ", " > ": " >= ", " == ": " != ", " != ": " == "}
    for i, ln in enumerate(lines):
        code = ln.split("#", 1)[0]
        if code.lstrip().startswith(("if ", "elif ", "while ", "return ", "assert ")):
            for a, b in swap.items():
                if a in code:
                    out = list(lines)
                    out[i] = ln.replace(a, b, 1)
                    return out, i + 1
    return None


def _mut_negate(lines: list[str]):
    for i, ln in enumerate(lines):
        m = re.match(r"^(\s*)(if|elif) (.+):\s*$", ln)
        if m and "#" not in ln:
            out = list(lines)
            out[i] = f"{m.group(1)}{m.group(2)} not ({m.group(3)}):"
            return out, i + 1
    return None


def _mut_contradiction(lines: list[str]):
    for i, ln in enumerate(lines):
        if re.match(r"^##\s+Decision\b", ln):
            out = list(lines)
            out.insert(i + 1, "")
            out.insert(i + 2, "This decision is withdrawn: none of what follows applies, and the previous "
                              "behaviour stays in force.")
            return out, i + 3
    return None


CALIBRATION_DEFECTS = (
    ("compare-flip", (".py",), _mut_compare),
    ("negate-condition", (".py",), _mut_negate),
    ("contradiction", (".md",), _mut_contradiction),
)


SIBLING_REPOS = ("CorvinOS", "Corvin-Marketplace")


def path_candidates(repo: Path, p: str) -> list[tuple[Path, Path]]:
    """(base, file) candidates for an ADR `paths:` entry, or [] when it is not a safe one.
    Allowed: repo-relative paths (resolved against the KB, CorvinOS, the projects root) and
    the sibling form `../<CorvinOS|Corvin-Marketplace|Corvin-Knowledge>/…`. Never absolute,
    never `~`, never any other `..` — a pulled ADR must not make calibrate copy (and hand to an
    LLM) or sweep scan a file outside the project repos (review R2-B2/B8)."""
    p = str(p).strip()
    if not p or p.startswith(("/", "~", "\\")) or ":" in p.split("/")[0]:
        return []
    parts = Path(p).parts
    root = projects_root(repo)
    if parts and parts[0] == "..":
        if len(parts) < 3 or parts[1] not in (*SIBLING_REPOS, M.KB_NAME) or ".." in parts[2:]:
            return []
        base = repo if parts[1] == M.KB_NAME else root / parts[1]
        return [(base, base.joinpath(*parts[2:]))]
    if ".." in parts:
        return []
    return [(b, b / p) for b in (repo, root / "CorvinOS", root)]


def safe_rel(p: str) -> bool:
    """Shape check only (no filesystem): see path_candidates."""
    return bool(path_candidates(Path("/nonexistent"), p))


def _artifact_files(repo: Path, decisions: list[M.Entity], limit: int = 25) -> list[tuple[str, Path]]:
    """(relative name, source file) for each reviewed decision and its existing `paths:` files —
    only repo-relative entries, only files that resolve inside their base, never symlinks."""
    out, seen = [], set()
    for d in decisions:
        cands = [(f"{d.source.name}/{d.path.name}", d.path)]
        for pth in L.as_list(d.fm.get("paths")):
            for base, f in path_candidates(repo, pth):
                if f.is_file() and not f.is_symlink() and f.resolve().is_relative_to(base.resolve()) \
                        and f.stat().st_size < 400_000:
                    cands.append((str(pth).lstrip("./").replace("../", "_sibling_/"), f))
                    break
        for rel, f in cands:
            if rel not in seen:
                seen.add(rel)
                out.append((rel, f))
    return out[:limit]


def _git_out(wd: Path, *a: str, raw: bool = False):
    r = subprocess.run(["git", "-C", str(wd), *a], capture_output=True)
    return r.returncode, (r.stdout if raw else r.stdout.decode("utf-8", "replace"))


def review_fix(repo: Path, ref: str, *, round_n: int, finding: int, commit: str, test: str,
               test_cmd: str = "", workdir: str = "", actor: str = "kb", do_commit: bool = True) -> dict:
    """Claim a fix for finding `finding` of round `round_n` (3.3 "mutation check of fixes").

    A fix needs a test that turns red WITHOUT it: the claim names the fixing commit and the
    test; the next calibrated round removes the commit's non-test changes from a copy of HEAD
    and runs the test there - a test that still passes is a finding of that round. Only the
    ordinal of the finding is stored (the finding text lives in the round's body)."""
    if not re.fullmatch(r"[0-9a-f]{7,40}", commit.strip().lower()):
        raise SystemExit("refused: --commit must be a hex sha (7-40 characters)")
    tp = Path(test)
    if tp.is_absolute() or ".." in tp.parts or not test.strip():
        raise SystemExit("refused: --test must be a relative path inside the checkout")
    wd = Path(workdir).resolve() if workdir.strip() else repo
    if test_cmd.strip() and is_agent(repo, actor):
        raise SystemExit("refused: an agent cannot set --test-cmd (the default runner is used)")
    rc, _ = _git_out(wd, "cat-file", "-e", f"{commit.strip()}^{{commit}}")
    if rc != 0:
        raise SystemExit(f"refused: commit {commit} does not exist in {wd}")
    rc, _ = _git_out(wd, "cat-file", "-e", f"HEAD:{tp.as_posix()}")
    if rc != 0:
        raise SystemExit(f"refused: test {test} is not tracked at HEAD of {wd}")
    with kb_lock(repo):
        idx = M.Index(M.discover(M.load_sources(repo)))
        r = _one_review(idx, ref)
        _autonomy(repo, actor, "A1", idx=idx, wip=False, do_commit=do_commit)
        _check_open(repo, r, actor, do_commit)
        rounds = M.review_rounds(r)
        if not 1 <= round_n <= len(rounds):
            raise SystemExit(f"refused: {r.id} has no round {round_n}")
        rd = rounds[round_n - 1]
        if not 1 <= finding <= int(rd.get("findings") or 0):
            raise SystemExit(f"refused: round {round_n} of {r.id} has {rd.get('findings') or 0} finding(s) - "
                             f"no finding {finding}")
        fixes = rd.setdefault("fixes", [])
        if any(f.get("finding") == finding and f.get("commit") == commit.strip() for f in fixes):
            raise SystemExit(f"refused: finding {finding} of round {round_n} already carries fix {commit}")
        fixes.append({k: v for k, v in dict(finding=finding, commit=commit.strip(), test=tp.as_posix(),
                                            test_cmd=test_cmd.strip(), workdir=str(wd) if workdir.strip() else "",
                                            claimed_at=now_iso()).items() if v != ""})
        value = "\n" + yaml.safe_dump(rounds, sort_keys=False, allow_unicode=True, width=100).rstrip()
        text = L.fm_set(r.doc.text, "rounds", value, after="status")
        sha = transaction(repo, {r.path: (text, r.doc)},
                          [dict(op="review_fix_claimed", actor=actor, id=r.id, uid=r.uid, n=round_n,
                                finding=finding, commit=commit.strip())],
                          f"kb: {r.id} round {round_n} fix claimed for finding {finding}",
                          do_commit=do_commit, keys={r.path: {"rounds"}})
        _claim_postcondition(repo, actor, dict(commit=commit.strip(), test=tp.as_posix(), test_cmd=test_cmd.strip(),
                                               workdir=str(wd) if workdir.strip() else ""),
                             subject=f"a fix claimed in {r.id} round {round_n}", do_commit=do_commit)
    return dict(id=r.id, round=round_n, finding=finding, commit=commit.strip(), test=tp.as_posix(), kb_commit=sha)


def _mutation_check(repo: Path, fix: dict, timeout: int) -> tuple[str, str]:
    """Remove the fix's non-test changes from a copy of HEAD and run its test there.
    Returns (result, observed): "pinned" when the test fails without the fix, else
    "not_pinned" (it still passes) or "cannot_remove" (the reverse patch does not apply / the
    commit changes nothing but tests) - the last two are findings."""
    import shlex
    import shutil
    import tempfile
    wd = Path(fix["workdir"]) if fix.get("workdir") else repo
    test = str(fix["test"])
    tmp = Path(tempfile.mkdtemp(prefix="kb-mutation-"))
    try:
        rc, tar = _git_out(wd, "archive", "HEAD", raw=True)
        if rc != 0:
            return "cannot_remove", f"git archive HEAD failed in {wd}"
        subprocess.run(["tar", "-x", "-C", str(tmp)], input=tar, check=True, capture_output=True)
        rc, patch = _git_out(wd, "show", "--format=", "--no-color", "--binary", fix["commit"], "--", ".",
                             f":(exclude){test}", raw=True)
        if rc != 0 or not patch.strip():
            return "cannot_remove", f"commit {fix['commit'][:9]} changes nothing but the test"
        ap = subprocess.run(["git", "apply", "-R", "--whitespace=nowarn", "-"], cwd=str(tmp), input=patch,
                            capture_output=True)
        if ap.returncode != 0:
            return "cannot_remove", f"the fix {fix['commit'][:9]} cannot be removed from HEAD (reverse patch does not apply)"
        argv = shlex.split(fix["test_cmd"]) if fix.get("test_cmd") else [sys.executable, "-m", "pytest", "-q", "-x", test]
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "TMPDIR", "VIRTUAL_ENV")}
        try:
            pr = subprocess.run(argv, cwd=str(tmp), capture_output=True, text=True, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            return "pinned", "the test did not finish without the fix (timeout counts as red)"
        if pr.returncode == 0:
            return "not_pinned", f"{test} passes with fix {fix['commit'][:9]} removed"
        return "pinned", f"{test} fails without fix {fix['commit'][:9]}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


MAX_REVIEW_FINDINGS = 30        # more findings than this in one round = shotgun output, the round is void
MAX_REVIEW_LINE_SHARE = 0.05    # ... or findings anchored to more than 5% of the artifact's lines


def review_calibrate(repo: Path, ref: str, *, lead_question: str, reviewer: str, reviewer_cmd: str,
                     seed_kind: str | None = None, actor: str = "kb", delay: float = 0.0,
                     timeout: int = 1800, do_commit: bool = True) -> dict:
    """One CALIBRATED round (T-0045): copy the reviewed artifact into a temp dir, seed one
    registered defect into the copy, run the reviewer on it, and record whether it found the
    seed. A missed seed voids the round (calibration: failed — neither counts nor resets).

    Reviewer contract: `reviewer_cmd` runs with cwd = the copy, KB_REVIEW_DIR set, and gets
    {"files": [...], "lead_question": …, "previous_findings": [...]} on stdin. It prints
    {"findings": [{"file", "line", "class", "repro", "observed"}], "claims_checked": [...],
    "tokens": <int, optional>}; `tokens` is what the reviewer spent and, with the measured
    wall-clock, lands in the audited `review_round` record that the budget (§3.6) counts.
    Only findings with a repro AND an observed result count (§3.3) — the seed too; a zero
    needs a non-empty list of claims; a round that sprays findings over the artifact
    (> MAX_REVIEW_FINDINGS, or anchored to > MAX_REVIEW_LINE_SHARE of its lines) is void.

    The KB lock is held only to prepare the round and to append it, never while the reviewer
    runs (an LLM reviewer takes minutes; holding the lock starved every writer and timed out
    the projector's heal). Calibration checks a reviewer's ATTENTION, not its honesty: a
    reviewer that reads the originals elsewhere on the host can locate the seed — that is
    the same attribution boundary as actor identity (ADR-2208 amendment 4)."""
    import random
    import shlex
    import shutil
    import tempfile
    t_start = time.monotonic()
    if not lead_question.strip() or not reviewer.strip() or not reviewer_cmd.strip():
        raise SystemExit("refused: calibrate needs --lead-question, --reviewer and --reviewer-cmd")
    _check_reviewer(reviewer)
    tmp = Path(tempfile.mkdtemp(prefix="kb-review-"))
    try:
        with kb_lock(repo):
            idx = M.Index(M.discover(M.load_sources(repo)))
            r = _one_review(idx, ref)
            _autonomy(repo, actor, "A1", idx=idx, wip=False, do_commit=do_commit)
            _check_open(repo, r, actor, do_commit)
            _round_limit(repo, r, actor, do_commit)
            # §3.3: a reviewer that missed the seed is REPLACED, never reinstated — the same id
            # may not be sent into another round of this review (case-insensitive, like authors)
            for prior in M.review_rounds(r):
                if (prior.get("void_reason") == "seed missed"
                        and str(prior.get("reviewer", "")).strip().lower() == reviewer.strip().lower()):
                    refuse(repo, "R_review_refused",
                           f"reviewer {reviewer.strip()!r} missed the calibration seed in round {prior.get('n')} "
                           f"of {r.id} — the next round needs a different reviewer",
                           entity_id=r.id, entity_uid=r.uid, actor=actor, do_commit=do_commit)
            decs = _reviewed_decisions(r, idx)
            if not decs:
                raise SystemExit(f"refused: {r.id} reviews no decision or epic — nothing to calibrate against")
            files = _artifact_files(repo, decs)
            for ep in [x for x in _reviewed(r, idx) if x.type == "epic"]:   # the plan is reviewed too
                rel = f"{ep.source.name}/{ep.path.name}"
                if rel not in {f for f, _ in files}:
                    files.append((rel, ep.path))
            n = len(M.review_rounds(r)) + 1
            rng = random.Random(f"{r.uid}:{n}")
            options = [(rel, f, kind, mut) for rel, f in files for kind, sfx, mut in CALIBRATION_DEFECTS
                       if rel.endswith(sfx) and (seed_kind in (None, kind))]
            rng.shuffle(options)
            for rel, f in files:
                dst = tmp / rel
                if not dst.resolve().is_relative_to(tmp.resolve()):
                    raise SystemExit(f"refused: {rel} would be copied outside the review copy")
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, dst)
            seed = None
            for rel, f, kind, mut in options:
                got = mut((tmp / rel).read_text(encoding="utf-8", errors="replace").split("\n"))
                if got:
                    (tmp / rel).write_text("\n".join(got[0]), encoding="utf-8")
                    seed = dict(kind=kind, file=rel, line=got[1])
                    break
            if seed is None:
                raise SystemExit(f"refused: no registered defect applies to {[x for x, _ in files]} — "
                                 "cannot calibrate this round")
            total_lines = sum(len((tmp / rel).read_text(encoding="utf-8", errors="replace").split("\n"))
                              for rel, _f in files) or 1
            pending_fixes = [(i, j, dict(fx)) for i, rr in enumerate(M.review_rounds(r))
                             for j, fx in enumerate(rr.get("fixes") or [])
                             if isinstance(fx, dict) and not fx.get("checked_in_round")]
            stdin = json.dumps(dict(files=[x for x, _ in files], lead_question=lead_question,
                                    previous_findings=[dict(n=x.get("n"), findings=x.get("findings"))
                                                       for x in M.review_rounds(r)]))
        # --- the reviewer runs WITHOUT the KB lock ---
        env = {k: v for k, v in os.environ.items()
               if k in ("PATH", "HOME", "LANG", "TMPDIR", "KB_REVIEWER_MODEL", "KB_REVIEWER_TIMEOUT")}
        env.update(KB_REVIEW_DIR=str(tmp), KB_REVIEW_LEAD_QUESTION=lead_question)
        # a relative script path in the command means "relative to the KB" — the reviewer runs in
        # the temp copy, where `scripts/kb_reviewer_claude.py` does not exist (review R3-C2)
        argv = [str((repo / a).resolve()) if not os.path.isabs(a) and (repo / a).is_file() else a
                for a in shlex.split(reviewer_cmd)]
        try:
            proc = subprocess.run(argv, cwd=str(tmp), input=stdin, text=True,
                                  capture_output=True, timeout=timeout, env=env)
            out = json.loads(proc.stdout or "{}")
            found = out.get("findings") if isinstance(out, dict) else None
            claims = out.get("claims_checked") if isinstance(out, dict) else None
            tokens = _int(out.get("tokens")) if isinstance(out, dict) else 0   # the reviewer's own report
            ok = proc.returncode == 0 and isinstance(found, list)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            found, claims, ok, tokens = [], [], False, 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    found = [x for x in (found or []) if isinstance(x, dict)]

    def confirmed(x: dict) -> bool:
        return bool(str(x.get("repro", "")).strip() and str(x.get("observed", "")).strip())

    def hits_seed(x: dict) -> bool:
        try:
            return str(x.get("file")) == seed["file"] and abs(int(x.get("line", -99)) - seed["line"]) <= 3
        except (TypeError, ValueError):
            return False
    anchored = {(str(x.get("file")), x.get("line")) for x in found}
    # the floor scales with the artifact: on a small one, 10 anchors 7 lines apart cover the seed
    # window blind (review R2-A7); 3 distinct anchors stay allowed for genuine findings
    shotgun = len(found) > MAX_REVIEW_FINDINGS or len(anchored) > max(3, MAX_REVIEW_LINE_SHARE * total_lines)
    seed_found = ok and any(hits_seed(x) and confirmed(x) for x in found)
    real = [x for x in found if not hits_seed(x)]
    good = [x for x in real if confirmed(x)]
    claims_ok = isinstance(claims, list) and any(str(c).strip() for c in claims)
    # 3.3: every fix claimed in an earlier round must turn its test red when removed - only a
    # round that is valid on its own terms runs the check (a void round is retried next time)
    mutation: list[tuple[int, int, str, str]] = []
    if ok and not shotgun and seed_found:
        mutation = [(i, j, *_mutation_check(repo, fx, min(timeout, 900))) for i, j, fx in pending_fixes]
    unpinned = [m for m in mutation if m[2] != "pinned"]
    why = None
    if not ok:
        why = "reviewer failed or printed no findings list"
    elif shotgun:
        why = f"shotgun output ({len(found)} findings over {len(anchored)} anchors)"
    elif not seed_found:
        why = "seed missed"
    elif not good and not unpinned and not claims_ok:
        why = "a zero without claims_checked"
    rnd = dict(n=n, lead_question=lead_question.strip(), reviewer=reviewer.strip(),
               findings=len(good) + (0 if why else len(unpinned)),
               unconfirmed=len(real) - len(good), calibration="failed" if why else "passed",
               seed=dict(kind=seed["kind"], file=seed["file"]), at=now_iso())
    if why:
        rnd["void_reason"] = why
    body = [f"### Round {n} — {lead_question.strip()} ({reviewer.strip()}, calibration {rnd['calibration']})"]
    body += [f"- `{x.get('class', '?')}` {x.get('file')}:{x.get('line')} — repro: {x.get('repro')} — "
             f"observed: {x.get('observed')}" for x in good]
    if not why:
        body += [f"- `fix_not_pinned` round {i + 1} fix {j + 1} — repro: removed the fix from a copy of HEAD "
                 f"and ran its test — observed: {obs}" for i, j, res, obs in unpinned]
    if len(body) == 1:
        body.append("- no confirmed findings")
    if mutation and not why:
        rnd["mutation"] = [dict(round=i + 1, fix=j + 1, result=res) for i, j, res, _o in mutation]
    # defects in an EARLIER round's fixes: a fix whose test does not turn red, or a confirmed
    # finding the reviewer attributes to one (`fix_of` = that round's number) - two rounds in a
    # row with such defects mean the author patches faster than it understands (3.3, T-0063)
    fix_defects = 0 if why else len(unpinned) + sum(
        1 for x in good if isinstance(x.get("fix_of"), int) and 1 <= x["fix_of"] < n)
    if fix_defects:
        rnd["fix_defects"] = fix_defects
    if claims_ok and not good:
        body.append(f"- claims checked: {len(claims)}")
    if delay:
        time.sleep(delay)   # a kill here must leave the round unwritten (T-0050 resume test)
    with kb_lock(repo):
        idx = M.Index(M.discover(M.load_sources(repo)))
        r = _one_review(idx, ref)
        _check_open(repo, r, actor, do_commit)
        if len(M.review_rounds(r)) + 1 != n:
            raise SystemExit(f"refused: {r.id} gained a round while the reviewer ran — run calibrate again")
        if is_agent(repo, actor):   # the reviewer ran unlocked: measure "before" again, right before the write
            _PRE_BLOCKING[str(repo)] = _blocking_keys(repo)
            _PRE_STAMPS[str(repo)] = _kb_stamps(repo)
        if not why:   # the fixes judged in this round are not judged again
            rs = M.review_rounds(r)
            for i, j, _res, _obs in mutation:
                rs[i]["fixes"][j]["checked_in_round"] = n
        usage = dict(elapsed_s=int(time.monotonic() - t_start - delay))
        if tokens:
            usage["tokens"] = tokens
        sha = _append_round(repo, r, rnd, actor=actor, body_add="\n".join(body), do_commit=do_commit,
                            usage=usage)
        if not why:
            _out_of_scope_ideas(repo, r, n, good, {rel for rel, _f in files}, actor=actor, do_commit=do_commit)
        _postcondition(repo, actor, do_commit)
    return dict(id=r.id, round=n, findings=rnd["findings"], calibration=rnd["calibration"],
                void_reason=why, commit=sha)


def review_close(repo: Path, ref: str, *, actor: str = "kb", do_commit: bool = True) -> dict:
    """Terminate the loop (§3.3): three-consecutive-zero -> addressed; max rounds or
    non-convergence (findings not falling over 3 rounds, or two counted rounds in a row that
    found defects in the previous round's fixes) -> stays open and is escalated (human queue).
    Otherwise refused.
    Always committed: G4 recognises the close by kb's own closing commit (review R3-A9)."""
    if not do_commit:
        raise SystemExit("refused: `kb review close` is never --no-commit — G4 rests on its commit")
    with kb_lock(repo):
        idx = M.Index(M.discover(M.load_sources(repo)))
        r = _one_review(idx, ref)
        _autonomy(repo, actor, "A1", idx=idx, wip=False, do_commit=do_commit)
        _check_open(repo, r, actor, do_commit)
        rounds, counted = M.review_rounds(r), M.counted_rounds(r)
        cfg = load_autonomy(repo) or {}
        reason = None
        if M.three_consecutive_zero(r):
            for d in _reviewed_decisions(r, idx):
                authors = decision_authors(d)
                same = [x["reviewer"] for x in counted[-3:] if str(x.get("reviewer", "")).strip().lower() in authors]
                if same:
                    refuse(repo, "R_review_refused", f"reviewer {same[0]!r} is {d.id}'s author — a review needs "
                           "a different reviewer", entity_id=r.id, entity_uid=r.uid, actor=actor, do_commit=do_commit)
            reason = "three-consecutive-zero"
        elif len(rounds) >= int(cfg.get("max_review_rounds", 8)):
            reason = "max-rounds-reached"
        elif M.fix_defect_streak(r) >= 2:
            reason = "non-convergence"
        elif len(counted) >= 3 and counted[-1].get("findings", 0) > 0 and not (
                counted[-1]["findings"] < counted[-2].get("findings", 0) < counted[-3].get("findings", 0)):
            reason = "non-convergence"
        if reason is None:
            refuse(repo, "R_review_refused", f"{r.id} is not closable: it needs three consecutive calibrated "
                   f"zero rounds under different lead questions (counted rounds: "
                   f"{[(x.get('lead_question'), x.get('findings')) for x in counted[-3:]]})",
                   entity_id=r.id, entity_uid=r.uid, actor=actor, do_commit=do_commit)
        text = L.fm_set(r.doc.text, "terminated_reason", reason, after="status")
        keys = {"terminated_reason"}
        if reason == "three-consecutive-zero":
            text = L.fm_set(text, "status", "addressed")
            text = L.fm_set(text, "findings_last_round", "0", after="terminated_reason")
            keys |= {"status", "findings_last_round"}
        sha = transaction(repo, {r.path: (text, r.doc)},
                          [dict(op="review_close", actor=actor, id=r.id, uid=r.uid, terminated_reason=reason)],
                          f"kb: {r.id} closed — {reason}", do_commit=do_commit, keys={r.path: keys})
        return dict(id=r.id, terminated_reason=reason,
                    status="addressed" if reason == "three-consecutive-zero" else "open (escalated)", commit=sha)


def review_set_status(repo: Path, ref: str, to: str, *, reason: str = "", actor: str = "kb",
                      do_commit: bool = True) -> dict:
    """Human moves: dismiss a review, or reopen one. `addressed` is never set here."""
    if to == "addressed":
        raise SystemExit("refused: only `kb review close` sets addressed (three calibrated zero rounds)")
    if to not in ("open", "dismissed"):
        raise SystemExit(f"refused: {to!r} is not a review status this command sets (open, dismissed)")
    with kb_lock(repo):
        idx = M.Index(M.discover(M.load_sources(repo)))
        r = _one_review(idx, ref)
        _autonomy(repo, actor, "A3", idx=idx, do_commit=do_commit)
        if not reason:
            raise SystemExit(f"refused: {to} needs --reason")
        if r.status == to:
            return dict(id=r.id, status=to, changed=False)
        text = L.fm_set(r.doc.text, "status", to)
        keys = {"status"}
        if to == "open" and r.fm.get("terminated_reason"):
            text = L.fm_remove(text, "terminated_reason")
            keys.add("terminated_reason")
        sha = transaction(repo, {r.path: (text, r.doc)},
                          [dict(op="status", actor=actor, type="review", id=r.id, uid=r.uid, **{"from": r.status},
                                to=to, reason_sha256=hashlib.sha256(reason.encode()).hexdigest())],
                          f"kb: review {r.id} {r.status} -> {to}", do_commit=do_commit, keys={r.path: keys})
        return dict(id=r.id, status=to, changed=True, commit=sha)


# --- task transition ----------------------------------------------------------------

EVIDENCE_KEYS = ("call_site", "e2e_test", "exit_code", "commit")


EVIDENCE_REPOS = ("CorvinOS", "Corvin-Marketplace")


def _repo_dir(repo: Path, name: str | None) -> Path | None:
    """The KB itself or a known sibling repo by NAME — never a path (review R2-B7)."""
    if not name or name in (M.KB_NAME, repo.name):
        return repo
    return projects_root(repo) / name if name in EVIDENCE_REPOS else None


def _is_test_path(p: str) -> bool:
    parts = Path(p).parts
    return any(x in ("tests", "test") for x in parts) or Path(p).name.startswith("test_")


def _git_ok(rd: Path, *args: str) -> bool:
    return subprocess.run(["git", "-C", str(rd), *args], capture_output=True).returncode == 0


def commit_on_main(rd: Path, sha: str) -> bool:
    sha = str(sha).strip()
    return bool(re.fullmatch(r"[0-9a-f]{7,40}", sha)) and _git_ok(rd, "cat-file", "-e", f"{sha}^{{commit}}") \
        and _git_ok(rd, "rev-parse", "--verify", "-q", "refs/remotes/origin/main") \
        and _git_ok(rd, "merge-base", "--is-ancestor", sha, "refs/remotes/origin/main")


CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".sh", ".go", ".rs", ".java", ".kt", ".rb",
                 ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".swift", ".sql", ".vue", ".svelte")


def _commit_time(rd: Path, sha: str) -> "dt.datetime | None":
    out = subprocess.run(["git", "-C", str(rd), "show", "-s", "--format=%cI", sha], capture_output=True, text=True)
    try:
        return dt.datetime.fromisoformat(out.stdout.strip()) if out.returncode == 0 else None
    except ValueError:
        return None


def evidence_problems(repo: Path, ev: dict, *, started: "dt.datetime | None" = None,
                      trees: dict | None = None) -> list[tuple[str, str]]:
    """G5 (T-0043): (finding_class, why) for each way the evidence fails to prove the work.
    The call site must be production CODE, the E2E test a test file, the commit on
    origin/main and — when the task's start is known — not older than that start (an
    unrelated old commit proved nothing). exit_code stays self-reported: the KB records the
    claim, it does not re-run the suite (attribution, ADR-2208 amendment 4)."""
    missing = [k for k in EVIDENCE_KEYS if not str(ev.get(k, "")).strip()]
    if missing:
        return [("G5_evidence_invalid", f"done needs evidence {missing} (--evidence key=value)")]
    rd = _repo_dir(repo, ev.get("repo"))
    if rd is None:
        return [("G5_evidence_invalid", f"evidence repo must be one of {(M.KB_NAME,) + EVIDENCE_REPOS}, "
                 f"got {ev.get('repo')!r}")]
    if not (rd / ".git").exists():
        return [("G5_evidence_invalid", f"evidence repo {ev.get('repo')!r} is not a git checkout at {rd}")]
    out = []
    files = _tree_files(repo, rd, {} if trees is None else trees) or set()   # committed, never the working tree
    if str(ev["exit_code"]).strip() != "0":
        out.append(("G5_evidence_invalid", f"the E2E run's exit_code is {ev['exit_code']}, not 0"))
    cs = str(ev["call_site"]).rsplit(":", 1)[0] if re.search(r":\d+$", str(ev["call_site"])) else str(ev["call_site"])
    if _is_test_path(cs):
        out.append(("G5_evidence_invalid", f"call_site {cs} is a test file — the call site must be production code"))
    elif not cs.endswith(CODE_SUFFIXES):
        out.append(("G5_evidence_invalid", f"call_site {cs} is not a code file"))
    elif cs.removeprefix("./") not in files:
        out.append(("G5_evidence_invalid", f"call_site {cs} does not exist in {rd.name}"))
    e2e = str(ev["e2e_test"])
    if not _is_test_path(e2e):
        out.append(("G5_evidence_invalid", f"e2e_test {e2e} is not a test file"))
    elif e2e.removeprefix("./") not in files:
        out.append(("G5_evidence_invalid", f"e2e_test {e2e} does not exist in {rd.name}"))
    if not commit_on_main(rd, str(ev["commit"])):
        out.append(("G5_commit_not_on_main", f"commit {ev['commit']} is not reachable from {rd.name} origin/main"))
    elif started is not None:
        ct = _commit_time(rd, str(ev["commit"]))
        if ct is not None and ct < started - dt.timedelta(minutes=5):
            out.append(("G5_evidence_invalid", f"commit {ev['commit']} ({ct.isoformat()}) predates the task's start "
                        f"({started.isoformat()}) — it cannot be the work"))
    return out


def _task_started(repo: Path, t: M.Entity) -> "dt.datetime | None":
    """When the task FIRST moved to in_progress (its audit record) — work committed before a
    block/resume is still the task's work."""
    for r in _audit_records(repo):
        if r.get("op") == "transition" and r.get("uid") == t.uid and r.get("to") == "in_progress":
            return _ts(r)
    return None


def _epic_decisions(t: M.Entity, idx: M.Index) -> list[M.Entity]:
    """Decisions the task implements, directly or through its epic (M.implemented_decisions)."""
    return M.implemented_decisions(t, idx)


def task(repo: Path, ref: str, to: str, *, reason: str = "", dod: str = "", via: str = "cli",
         actor: str = "kb", evidence: dict | None = None, do_commit: bool = True) -> dict:
    if to not in TASK_FSM:
        raise SystemExit(f"refused: {to!r} is not a task status {tuple(TASK_FSM)}")
    with kb_lock(repo):
        ents = M.discover(M.load_sources(repo))
        idx = M.Index(ents)
        hits = [h for h in idx.resolve(ref) if h.type == "task"]
        if len(hits) != 1:
            raise SystemExit(f"refused: {ref} resolves to {len(hits)} task(s)")
        t = hits[0]
        if not t.writable:
            raise SystemExit(f"refused: {t.id} lives in a read-only source")
        cur = t.status or "open"
        if cur not in TASK_FSM:
            raise SystemExit(f"refused: {t.id} has status {cur!r}, not a task status — fix the file (kb check E07)")
        if uncommitted(repo, t.path):
            raise SystemExit(f"refused: {t.path.relative_to(repo)} has uncommitted edits — commit or revert them first")
        if to == cur:
            return dict(id=t.id, uid=t.uid, status=cur, changed=False, commit=None)
        if to not in TASK_FSM[cur]:
            refuse(repo, "E23_transition_refused", f"{t.id} {cur} -> {to} is not allowed "
                   f"(allowed: {sorted(TASK_FSM[cur]) or 'none — terminal'})", entity_id=t.id, entity_uid=t.uid,
                   detail=f"{cur}->{to}", actor=actor, do_commit=do_commit)
        if t.fm.get("suggested") and is_agent(repo, actor) and to != "cancelled":
            refuse(repo, "A3_human_only", f"{t.id} is only SUGGESTED (an epic follow-up) - a human decides whether "
                   "it is wanted by starting it", entity_id=t.id, entity_uid=t.uid, actor=actor, do_commit=do_commit)
        if is_agent(repo, actor):
            _autonomy(repo, actor, "A3" if to == "cancelled" else "A2", idx=idx,
                      decisions=_epic_decisions(t, idx), proposal=t.id, do_commit=do_commit)
        text = t.doc.text
        claim = None
        if to == "blocked":
            if not reason:
                refuse(repo, "E18_reason_missing", "blocked needs --reason", entity_id=t.id, entity_uid=t.uid,
                       detail="blocked", actor=actor, do_commit=do_commit)
            text = L.fm_set(text, "blocked_reason", json.dumps(reason, ensure_ascii=False), after="status")
        elif "blocked_reason" in t.fm:
            text = L.fm_remove(text, "blocked_reason")
        if to == "cancelled":
            if not reason:
                refuse(repo, "E18_reason_missing", "cancelled needs --reason", entity_id=t.id, entity_uid=t.uid,
                       detail="cancelled", actor=actor, do_commit=do_commit)
            text = L.fm_set(text, "cancelled_reason", json.dumps(reason, ensure_ascii=False), after="status")
        ev = {k: str(v) for k, v in (evidence or {}).items()}
        if to == "done":
            planned = t.fm.get("definition_of_done")
            if not planned and not dod:
                refuse(repo, "E19_done_incomplete", "done needs a definition_of_done (in the file or --dod)",
                       entity_id=t.id, entity_uid=t.uid, actor=actor, do_commit=do_commit)
            deps = [d for ln in t.links if ln.rel == "depends_on" for d in idx.resolve(ln.to)]
            stack, files = list(deps), []
            while stack:                       # a depended-on container counts through its tasks
                d = stack.pop()
                files.append(d.path)
                stack.extend(idx.children(d))
            dirty = [str(f.relative_to(repo)) for f in files if f.is_relative_to(repo) and uncommitted(repo, f)]
            if dirty:
                # the done gate must judge committed state, or a hand-set `status: done` in a
                # dependency's working copy would let this commit pass and block `kb check`
                raise SystemExit(f"refused: dependencies have uncommitted edits: {dirty}")
            open_deps = [x.id for x in open_dependencies(t, idx)]
            if open_deps:
                refuse(repo, "E20_done_with_open_deps", f"depends_on not done: {open_deps}", entity_id=t.id,
                       entity_uid=t.uid, detail=",".join(open_deps), actor=actor, do_commit=do_commit)
            if M.is_code_task(t, idx):
                probs = evidence_problems(repo, ev, started=_task_started(repo, t))
                if probs:
                    refuse(repo, probs[0][0], f"{t.id} is a code task (its epic implements a decision) — "
                           + "; ".join(w for _c, w in probs), entity_id=t.id, entity_uid=t.uid,
                           detail=probs[0][1], actor=actor, do_commit=do_commit)
                text = L.fm_set(text, "done_evidence", json.dumps({k: ev[k] for k in sorted(ev)},
                                                                   ensure_ascii=False), after="status")
                # an agent's claim is re-judged after the write; the test is run against the fix only
                # where the checkout is the KB itself (running a sibling repo's suite is not kb's business)
                erd = _repo_dir(repo, ev.get("repo"))
                claim = dict(commit=str(ev["commit"]), test=str(ev["e2e_test"]), check_test=erd == repo,
                             workdir="" if erd == repo else str(erd))
            if dod and not planned:
                text = L.fm_set(text, "definition_of_done", json.dumps(dod, ensure_ascii=False), after="status")
            elif dod and dod != str(planned):
                # The planned definition_of_done IS the acceptance criterion: a completer's text
                # never replaces it (it did — T-0041..T-0047 were closed against rewritten DoDs).
                text = L.fm_set(text, "completion_note", json.dumps(dod, ensure_ascii=False), after="status")
            text = L.fm_set(text, "completed_at", now_iso(), after="status")
            head = L.git(repo, "rev-parse", "--short", "HEAD", check=False).strip()
            if head:
                text = L.fm_set(text, "completed_in_commit", head, after="completed_at")
        accepted = bool(t.fm.get("suggested")) and to == "in_progress"   # a human starting it accepts it
        if accepted:
            text = L.fm_remove(text, "suggested")
        text = L.fm_set(text, "status", to)
        # The reason/DoD text lives in the task file (that is the record the operator writes
        # knowingly); the audit log and the commit message carry only its hash + length, so
        # free text typed into the console never fans out into further logs (review S-#5).
        free = reason or dod
        trace = dict(text_sha256=hashlib.sha256(free.encode()).hexdigest(), text_len=len(free)) if free else {}
        sha = transaction(repo, {t.path: (text, t.doc)}, keys={t.path: {
                              "status", "blocked_reason", "cancelled_reason", "definition_of_done",
                              "completed_at", "completed_in_commit", "completion_note", "done_evidence",
                              "suggested"}},
                          audits=[dict(op="transition", actor=actor, via=via, uid=t.uid, id=t.id,
                                **{"from": cur, "to": to}, **trace)],
                          msg=f"kb: {t.id} {cur} -> {to}", do_commit=do_commit)
        _postcondition(repo, actor, do_commit)
        if claim is not None:
            _claim_postcondition(repo, actor, claim, subject=f"{t.id} closed as done", do_commit=do_commit)
        follow = _apply_follow_up(repo, t.uid, actor=actor, do_commit=do_commit) if to == "done" else []
        return dict(id=t.id, uid=t.uid, status=to, changed=True, commit=sha, **{"from": cur},
                    **({"follow_up": follow} if follow else {}))


GUIDANCE_DIR = "kb/_meta/guidance"
# classes no proposal can avoid — produced by the KB's own sweep, not by an author's draft;
# they stay visible in `kb learn` but never become guidance (review R2-C4)
LEARN_EXCLUDED = frozenset({"G6_drift"})
PROPOSAL_TYPES = ("idea", "concept", "decision", "plan", "task", "epic", "review")


def _finding_records(repo: Path) -> list[dict]:
    """finding_classified records whose class is in the current closed taxonomy (a record of
    a retired taxonomy version is ignored, never guessed)."""
    return [r for r in _audit_records(repo)
            if r.get("op") == "finding_classified" and r.get("finding_class") in FINDING_CLASSES]


def _proposals_since(repo: Path, since: "dt.datetime | None") -> int:
    """Proposal ATTEMPTS after `since` — the denominator of a class rate: every created draft
    (its uid) plus every refused proposal (entity id, or the detail hash when the refusal
    came before any entity existed). Counting only successful `new` records made a refused
    G0 attempt a finding without a proposal, and the rate meaningless."""
    keys = set()
    for r in _audit_records(repo):
        if since is not None and not ((_ts(r) or since) > since):
            continue
        if r.get("op") == "new" and r.get("type") in PROPOSAL_TYPES:
            keys.add(r.get("uid"))
        elif r.get("op") == "finding_classified" and r.get("finding_class") in FINDING_CLASSES:
            keys.add(r.get("id") or r.get("detail_sha256"))
    keys.discard(None)
    return len(keys)


GUIDANCE_HINT = {
    "G0_no_search_evidence": "A new idea/concept duplicated an existing one. Run `kb find <words>` first and "
                             "amend the hit, or cite it with --link search=<id> when it is genuinely different.",
    "E14_link_dangling": "A link names an id that does not exist. `kb show <id>` before linking; a renumbered "
                         "id resolves through renumbered_from.",
    "E18_reason_missing": "blocked/cancelled carries a reason — say what blocks it or why it is dropped.",
    "E19_done_incomplete": "Write the definition_of_done when you create the task; done is judged against it.",
    "E20_done_with_open_deps": "Finish (or re-plan) the depended-on tasks first; done is terminal.",
    "G5_evidence_invalid": "A code task is done only with call_site (production), e2e_test, exit_code 0 and a "
                           "commit on origin/main — push before you close.",
    "G5_commit_not_on_main": "Push the commit to origin/main before `kb task … done`; a local commit proves nothing.",
    "A2_not_ready": "Bring the decision to implementation_ready (concept, back-edge, plan, closed review) first.",
    "REVIEW_FINDING_CONFIRMED": "Reviews keep finding defects of this shape — run the check yourself before review.",
}


def _guidance_body(fc: str, proposals: list[str], count: int) -> str:
    sev = RULES[fc][0] if fc in RULES else "finding"
    return (f"# Guidance: {fc}\n\n"
            f"**What goes wrong.** `{fc}` ({sev}) recurred: {count} times across {len(proposals)} distinct "
            "proposals.\n\n"
            f"**How to avoid it.** {GUIDANCE_HINT.get(fc, 'See the rule ' + fc + ' in scripts/kb.py RULES.')}\n\n"
            f"**The check that catches it.** `kb check` / the refusal of the write that hit `{fc}`.\n\n"
            "Advisory only: guidance never refuses anything. Turning it into a rule is a human decision "
            "with an ADR (A3, CONCEPT-0090 §3.4).\n")


def guidance_pass(repo: Path, *, actor: str = "kb-guidance", do_commit: bool = True) -> dict:
    """T-0049 lifecycle over kb/_meta/guidance/<finding_class>.md (CONCEPT-0090 §3.4):

      draft:   a class seen in >=2 DISTINCT proposals with no guidance file gets one
               (status active, skillforge_injection pending, rate_before = findings per
               proposal up to now). Proposal key = entity id, else the detail hash (a G0
               refusal has no entity yet).
      measure: rate_after = findings since the draft / proposals since the draft.
      retire:  once proposals_since >= guidance_retire_after_proposals (autonomy.yaml,
               default 10) and rate_after >= rate_before -> status retired (frozen). A
               retired file is never reactivated by this pass.

    This function writes advisory markdown only — never RULES/FINDING_CLASSES (A3)."""
    recs = _finding_records(repo)
    by_class: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        if r["finding_class"] not in LEARN_EXCLUDED:
            by_class[r["finding_class"]].append(r)
    cfg = load_autonomy(repo) or {}
    n_retire = int(cfg.get("guidance_retire_after_proposals", 10))
    gdir = repo / GUIDANCE_DIR
    writes: dict[Path, tuple[str, "L.Doc | None"]] = {}
    audits: list[dict] = []
    created, updated, retired = [], [], []
    with kb_lock(repo):
        # kb-guidance is an agent: a tripped stop-all or an exhausted budget stops it too
        _autonomy(repo, actor, "A1", idx=M.Index(M.discover(M.load_sources(repo))), wip=False, do_commit=do_commit)
        total_props = _proposals_since(repo, None)
        for fc, items in sorted(by_class.items()):
            proposals = sorted({i.get("id") or i.get("detail_sha256") for i in items
                                if i.get("id") or i.get("detail_sha256")})
            gpath = gdir / f"{fc}.md"
            if gpath.is_symlink():
                raise SystemExit(f"refused: {gpath.relative_to(repo)} is a symlink")
            if not gpath.exists():
                if len(proposals) < 2:
                    continue
                fm = dict(finding_class=fc, status="active", created=now_iso(),
                          proposal_count_at_creation=len(proposals), findings_before=len(items),
                          proposals_before=total_props, rate_before=round(len(items) / max(total_props, 1), 4),
                          findings_since=0, proposals_since=0, rate_after=None,
                          skillforge_injection="pending")
                text = ("---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=100) + "---\n\n"
                        + _guidance_body(fc, proposals, len(items)))
                writes[gpath] = (text, None)
                audits.append(dict(op="guidance_created", actor=actor, finding_class=fc, proposal_count=len(proposals)))
                created.append(fc)
                continue
            doc = L.parse(gpath)
            fm = doc.fm or {}
            if fm.get("status") != "active":
                continue
            # deltas of append-only counts, not timestamp comparisons: a refusal in the same
            # second as the draft was otherwise counted on neither side
            f_since = max(0, len(items) - int(fm.get("findings_before") or 0))
            p_since = max(0, total_props - int(fm.get("proposals_before") or 0))
            rate_after = round(f_since / p_since, 4) if p_since else None
            text = L.fm_set(doc.text, "findings_since", str(f_since))
            text = L.fm_set(text, "proposals_since", str(p_since))
            text = L.fm_set(text, "rate_after", "null" if rate_after is None else str(rate_after))
            keys = {"findings_since", "proposals_since", "rate_after"}
            if p_since >= n_retire and rate_after is not None and rate_after >= float(fm.get("rate_before") or 0):
                text = L.fm_set(text, "status", "retired")
                text = L.fm_set(text, "retired_at", json.dumps(now_iso()))
                text = L.fm_set(text, "retired_reason", '"no-effect-after-N"')
                keys |= {"status", "retired_at", "retired_reason"}
                retired.append(fc)
            else:
                updated.append(fc)
            if text != doc.text:
                writes[gpath] = (text, doc)
                audits.append(dict(op="guidance_measured", actor=actor, finding_class=fc, findings_since=f_since,
                                   proposals_since=p_since, retired=fc in retired))
        sha = None
        if writes:
            gdir.mkdir(parents=True, exist_ok=True)
            sha = transaction(repo, writes, audits,
                              f"kb: guidance pass — {len(created)} created, {len(updated)} measured, {len(retired)} retired",
                              do_commit=do_commit)
    return dict(created=created, updated=updated, retired=retired, commit=sha,
                growth_signals=_growth_counts(repo, None))


def guidance_pending(repo: Path) -> dict:
    """What the SkillForge bridge (CorvinOS) must do: mint skills for active guidance not
    yet injected, retire skills of retired guidance. Read-only."""
    mint, retire = [], []
    gdir = repo / GUIDANCE_DIR
    if gdir.is_symlink() or (gdir.exists() and not gdir.resolve().is_relative_to(repo.resolve())):
        raise SystemExit("refused: kb/_meta/guidance is a symlink")
    created = {r.get("finding_class") for r in _audit_records(repo) if r.get("op") == "guidance_created"}
    for p in sorted(gdir.glob("*.md")) if gdir.is_dir() else []:
        if p.is_symlink():
            continue
        doc = L.parse(p)
        fm = doc.fm or {}
        fc = str(fm.get("finding_class") or p.stem)
        # only what the guidance pass itself drafted, and only its OWN text: a hand-committed
        # file would otherwise become a prompt injected into every future turn (review R2-B4)
        if fc not in FINDING_CLASSES or fc in LEARN_EXCLUDED or fc not in created or p.stem != fc:
            continue
        body = _guidance_body(fc, [""] * int(fm.get("proposal_count_at_creation") or 0),
                              int(fm.get("findings_before") or 0))
        if fm.get("status") == "active" and fm.get("skillforge_injection") == "pending":
            mint.append(dict(finding_class=fc, file=str(p.relative_to(repo)), body_md=body[:8000]))
        if fm.get("status") == "retired" and fm.get("skill") and not fm.get("skill_retired"):
            retire.append(dict(finding_class=fc, skill=fm["skill"]))
    return dict(mint=mint, retire=retire)


def guidance_ack(repo: Path, fc: str, *, skill: str = "", retired: bool = False, actor: str = "sync:kb",
                 do_commit: bool = True) -> dict:
    """The bridge reports back through kb.py — the only writer of KB files."""
    with kb_lock(repo):
        p = repo / GUIDANCE_DIR / f"{fc}.md"
        if not p.is_file() or p.is_symlink():
            raise SystemExit(f"refused: no guidance file for {fc!r}")
        doc = L.parse(p)
        if retired:
            text, keys = L.fm_set(doc.text, "skill_retired", "true"), {"skill_retired"}
        else:
            if not re.fullmatch(r"[A-Za-z0-9._]{1,128}", skill or ""):
                raise SystemExit("refused: --skill must be a SkillForge name")
            text = L.fm_set(doc.text, "skillforge_injection", "minted")
            text = L.fm_set(text, "skill", skill)
            text = L.fm_set(text, "minted_at", json.dumps(now_iso()))
            keys = {"skillforge_injection", "skill", "minted_at"}
        sha = transaction(repo, {p: (text, doc)}, [dict(op="guidance_ack", actor=actor, finding_class=fc,
                                                        skill=skill, retired=retired)],
                          f"kb: guidance {fc} — " + ("skill retired" if retired else f"minted as {skill}"),
                          do_commit=do_commit, keys={p: keys})
        return dict(finding_class=fc, commit=sha)


def guidance_retire(repo: Path, fc: str, *, reason: str, actor: str = "kb", do_commit: bool = True) -> dict:
    """Human: retire guidance blamed for a false refusal (§3.4)."""
    with kb_lock(repo):
        if is_agent(repo, actor):
            refuse(repo, "A3_human_only", "retiring guidance by blame is a human action", actor=actor,
                   do_commit=do_commit)
        if not reason:
            raise SystemExit("refused: --reason required")
        p = repo / GUIDANCE_DIR / f"{fc}.md"
        if not p.is_file() or p.is_symlink():
            raise SystemExit(f"refused: no guidance file for {fc!r}")
        doc = L.parse(p)
        text = L.fm_set(doc.text, "status", "retired")
        text = L.fm_set(text, "retired_at", json.dumps(now_iso()))
        text = L.fm_set(text, "retired_reason", '"blamed-false-refusal"')
        sha = transaction(repo, {p: (text, doc)}, [dict(op="guidance_retired", actor=actor, finding_class=fc,
                                                        reason_sha256=hashlib.sha256(reason.encode()).hexdigest())],
                          f"kb: guidance {fc} retired (blamed)", do_commit=do_commit,
                          keys={p: {"status", "retired_at", "retired_reason"}})
        return dict(finding_class=fc, status="retired", commit=sha)


def _growth_counts(repo: Path, since: "dt.datetime | None") -> dict[str, int]:
    """Audited `growth_signal` records by signal (3.5) - the drafts that came from a signal rather
    than from free brainstorming - from `since` on (None = ever)."""
    growth: dict[str, int] = defaultdict(int)
    for rec in _audit_records(repo):
        when = _ts(rec)
        if rec.get("op") == "growth_signal" and rec.get("signal") in GROWTH_SIGNALS \
                and (since is None or (when and when >= since)):
            growth[rec["signal"]] += 1
    return dict(sorted(growth.items()))


def learn(repo: Path, *, days: int = 30) -> dict:
    """T-0048: finding_classified records over a window, grouped by the closed taxonomy."""
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    counts: dict[str, int] = defaultdict(int)
    for rec in _finding_records(repo):
        when = _ts(rec)
        if when and when >= cutoff:
            counts[rec["finding_class"]] += 1
    by_class = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    return dict(window_days=days, total=sum(counts.values()), by_class=by_class,
                growth_signals=_growth_counts(repo, cutoff))


def _orchestrate_review(repo: Path, review_ref: str, *, reviewer: str, reviewer_cmd: str,
                        lead_questions: list[str] | None = None, actor: str = "kb-orchestrator",
                        delay: float = 0.0, do_commit: bool = True) -> dict:
    """T-0050: drive a review ONE step toward G4 — the next calibrated round, then close once
    it can terminate. Its only state is the review file (rounds, terminated_reason): no
    session, no progress file. A process killed mid-round wrote nothing (the round is one
    transaction after the reviewer returns), so the next invocation computes the same step."""
    qs = [q for q in (lead_questions or DEFAULT_LEAD_QUESTIONS) if q.strip()]
    if len(set(qs)) < 3:
        raise SystemExit("refused: 3x0 needs at least three different lead questions")
    idx = M.Index(M.discover(M.load_sources(repo)))
    r = _one_review(idx, review_ref)
    if r.status != "open" or r.fm.get("terminated_reason"):
        return dict(id=r.id, step="none", status=r.status, terminated_reason=r.fm.get("terminated_reason"))
    counted = M.counted_rounds(r)
    recent = {str(x.get("lead_question")) for x in counted[-2:]}
    start = len(M.review_rounds(r)) % len(qs)
    q = next(qq for qq in qs[start:] + qs[:start] if qq not in recent)
    rnd = review_calibrate(repo, review_ref, lead_question=q, reviewer=reviewer, reviewer_cmd=reviewer_cmd,
                           actor=actor, delay=delay, do_commit=do_commit)
    idx = M.Index(M.discover(M.load_sources(repo)))
    r = _one_review(idx, review_ref)
    cfg = load_autonomy(repo) or {}
    c = M.counted_rounds(r)
    can_close = M.three_consecutive_zero(r) or len(M.review_rounds(r)) >= int(cfg.get("max_review_rounds", 8)) \
        or (len(c) >= 3 and c[-1].get("findings", 0) > 0
            and not (c[-1]["findings"] < c[-2].get("findings", 0) < c[-3].get("findings", 0)))
    out = dict(id=r.id, step="round", round=rnd)
    if can_close:
        out["closed"] = review_close(repo, review_ref, actor=actor, do_commit=do_commit)
    return out


# --- pipeline orchestration (T-0068, CONCEPT-0090 3.1) ----------------------------------
#
# `kb orchestrate REF` takes ANY stage of a decision's pipeline - an idea, a concept, a decision,
# or a review - and performs the ONE next step. The stage is a pure function of KB entity state
# (links, gates, reviews): there is no session and no progress file, so a process killed at any
# point has written either a whole step (one transaction) or nothing, and the next invocation
# computes the same step. Drafts are A1 (an agent drafts, a human decides), written from a
# `--drafter-cmd` that sees only the source entity on stdin.

DRAFT_STAGES = ("draft_concept", "draft_decision", "draft_plan", "draft_task")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _linked(e: M.Entity, rel: str, target: M.Entity, idx: M.Index) -> bool:
    return any(ln.rel == rel and not ln.external and target in idx.resolve(ln.to) for ln in e.links)


def _plan_epics(decision: M.Entity, idx: M.Index) -> list[M.Entity]:
    return sorted({id(h): h for h in idx.ents if h.type == "epic" for ln in h.links
                   if ln.rel == "implements" and not ln.external and decision in idx.resolve(ln.to)}.values(),
                  key=lambda x: x.id or "")


def _pipeline_stage(idx: M.Index, root: M.Entity, cfg: dict) -> dict:
    """The next step of `root`'s pipeline, from entity state only. `stage` is one of
    draft_concept | draft_decision | link_backedge | draft_plan | draft_task | open_review |
    review_round | escalated | ready | blocked | none."""
    e = root
    if e.type == "idea":
        cs = [c for c in idx.ents if c.type == "concept" and c.writable and _linked(c, "derived_from", e, idx)]
        if not cs:
            return dict(stage="draft_concept", source=e)
        e = sorted(cs, key=lambda x: x.id or "")[0]
    if e.type == "concept":
        ds = [d for d in idx.ents if d.type == "decision" and d.writable
              and (_linked(d, "inspired_by", e, idx) or _linked(d, "formalized_as", e, idx))]
        if not ds:
            return dict(stage="draft_decision", source=e)
        e = sorted(ds, key=lambda x: x.id or "")[0]
    if e.type != "decision":
        return dict(stage="none", entity=e, reason=f"{e.id} is a {e.type} - the pipeline starts at an idea, concept or decision")
    if not e.writable or e.status != "proposed":
        return dict(stage="none", entity=e, reason=f"{e.id} is {e.status}")
    g = M.gate_status(e, idx)
    if not g["g1"]:
        return dict(stage="blocked", entity=e, reason=f"{e.id} names no concept (G1) - link it with inspired_by")
    if not g["g2"]:
        return dict(stage="link_backedge", entity=e, concept=g["resolved_concepts"][0])
    if not L.as_list(e.fm.get("paths")):
        return dict(stage="blocked", entity=e, reason=f"{e.id} has no paths: - the plan cannot be tied to code")
    epics = _plan_epics(e, idx)
    if not epics:
        return dict(stage="draft_plan", entity=e)
    if not g["g3_overlap"]:
        return dict(stage="blocked", entity=e, reason="an implementing epic does not share the decision's paths")
    if not g["g3_tasks_ok"]:
        bare = [ep for ep in epics if not [t for t in idx.children(ep) if t.type == "task"]]
        if not bare:
            return dict(stage="blocked", entity=e, reason="a task of the plan has no definition_of_done")
        return dict(stage="draft_task", entity=e, epic=bare[0])
    if g["g4"]:
        return dict(stage="ready", entity=e)
    open_rs = [r for r in M.reviews_of(e, idx) if r.status == "open" and r.writable and all(
        any(ln.rel == "reviews" and not ln.external and ep in idx.resolve(ln.to) for ln in r.links) for ep in epics)]
    if any(r.fm.get("terminated_reason") for r in open_rs):
        return dict(stage="escalated", entity=e, review=next(r for r in open_rs if r.fm.get("terminated_reason")))
    if open_rs:
        return dict(stage="review_round", entity=e, review=open_rs[0])
    return dict(stage="open_review", entity=e, epics=epics)


def _run_drafter(repo: Path, cmd: str, payload: dict, timeout: int) -> dict:
    """Run the drafter with ONLY the source entity on stdin, in an empty temp dir and a minimal
    environment. Returns a validated {title, body, ...}; anything else is a refusal."""
    import shlex
    import tempfile
    argv = [str((repo / a).resolve()) if not os.path.isabs(a) and (repo / a).is_file() else a
            for a in shlex.split(cmd)]
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "TMPDIR", "KB_REVIEWER_MODEL",
                                                       "KB_REVIEWER_TIMEOUT")}
    with tempfile.TemporaryDirectory(prefix="kb-draft-") as tmp:
        try:
            proc = subprocess.run(argv, cwd=tmp, input=json.dumps(payload), text=True, capture_output=True,
                                  timeout=timeout, env=env)
            out = json.loads(proc.stdout or "{}")
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
            raise SystemExit(f"refused: the drafter did not produce a draft ({type(exc).__name__})")
    title = str(out.get("title") or "").strip() if isinstance(out, dict) else ""
    body = _CTRL.sub("", str(out.get("body") or "")) if isinstance(out, dict) else ""
    if proc.returncode != 0 or not title or "\n" in title or len(title) > 140 or not body.strip() or len(body) > 20000:
        raise SystemExit("refused: the drafter's answer is not a usable draft (needs a one-line title <= 140 "
                         "characters and a non-empty body <= 20000)")
    return dict(out, title=title, body=body)


def _draft_paths(draft: dict) -> list[str]:
    ps = [str(p) for p in (draft.get("paths") or []) if isinstance(p, str)]
    return [p for p in ps if p and not Path(p).is_absolute() and ".." not in Path(p).parts and "\n" not in p][:12]


def _provenance(actor: str, source: M.Entity) -> str:
    return f"\n\n_Drafted by {actor} from {source.id}; a human decides what becomes of it._\n"


def _orchestrate_pipeline(repo: Path, root_ref: str, *, reviewer: str, reviewer_cmd: str,
                          drafter_cmd: str, lead_questions: list[str] | None, actor: str, delay: float,
                          do_commit: bool) -> dict:
    idx = M.Index(M.discover(M.load_sources(repo)))
    hits = idx.resolve(root_ref)
    if len(hits) != 1:
        raise SystemExit(f"refused: {root_ref} resolves to {len(hits)} entities")
    root = hits[0]
    cfg = load_autonomy(repo) or {}
    st = _pipeline_stage(idx, root, cfg)
    stage = st["stage"]
    ent = st.get("entity") or st.get("source")
    out = dict(id=root.id, step=stage, entity=ent.id if ent else None)
    if stage in ("none", "blocked", "ready"):
        if st.get("reason"):
            out["reason"] = st["reason"]
        return out
    if stage == "escalated":
        return dict(out, review=st["review"].id, reason="the review ended without a pass - a human decides")
    if stage == "review_round":
        if not reviewer.strip() or not reviewer_cmd.strip():
            raise SystemExit("refused: a review round needs --reviewer and --reviewer-cmd")
        res = _orchestrate_review(repo, st["review"].id, reviewer=reviewer, reviewer_cmd=reviewer_cmd,
                                  lead_questions=lead_questions, actor=actor, delay=delay, do_commit=do_commit)
        return dict(out, review=st["review"].id, **{k: v for k, v in res.items() if k in ("round", "closed")})
    if stage == "open_review":
        r = review_open(repo, f"Review of {ent.id} and its plan", [ent.id] + [ep.id for ep in st["epics"]],
                        actor=actor, do_commit=do_commit)
        return dict(out, created=[r["id"]])
    if stage == "link_backedge":
        concept = st["concept"]
        with kb_lock(repo):
            fresh = M.Index(M.discover(M.load_sources(repo)))
            now_st = _pipeline_stage(fresh, fresh.one(root.uid), cfg)
            if now_st["stage"] != "link_backedge":
                raise SystemExit("refused: the pipeline moved while this step was being prepared - run it again")
            c = fresh.one(concept.uid)
            links = [dict(rel=ln.rel, to=ln.to) for ln in c.links] + [dict(rel="formalized_as", to=ent.id)]
            value = "\n" + yaml.safe_dump(links, sort_keys=False, allow_unicode=True, width=100).rstrip()
            transaction(repo, {c.path: (L.fm_set(c.doc.text, "links", value), c.doc)},
                        [dict(op="pipeline_step", actor=actor, stage=stage, id=c.id, uid=c.uid, to=ent.id)],
                        f"kb: {c.id} formalized_as {ent.id}", do_commit=do_commit, keys={c.path: {"links"}})
        return dict(out, linked=[f"{concept.id} formalized_as {ent.id}"])
    # --- drafting stages: the drafter runs WITHOUT the KB lock, like a reviewer ---
    if stage not in DRAFT_STAGES:
        raise SystemExit(f"refused: unknown pipeline stage {stage!r}")
    if not drafter_cmd.strip():
        return dict(out, step="needs_drafter", stage=stage, reason=f"{stage} needs --drafter-cmd")
    src = ent if stage != "draft_task" else st["epic"]
    payload = dict(stage=stage, source=dict(id=src.id, type=src.type, title=src.title,
                                            body=(src.doc.text.split("---", 2)[2] if src.doc and src.doc.text.count("---") >= 2 else "")[:8000]))
    draft = _run_drafter(repo, drafter_cmd, payload, 600)
    if delay:
        time.sleep(delay)      # a kill here leaves nothing written (T-0068 resume test)
    with kb_lock(repo):
        fresh = M.Index(M.discover(M.load_sources(repo)))
        now_st = _pipeline_stage(fresh, fresh.one(root.uid), cfg)
        if now_st["stage"] != stage:
            raise SystemExit("refused: the pipeline moved while the drafter ran - run the step again")
        note = _provenance(actor, src)
        distinct = f"drafted by the orchestrator from {src.id}"
        created: list[str] = []
        if stage == "draft_concept":
            made = _new_locked(repo, "concept", draft["title"], fields={"distinct_because": distinct},
                               links=[("derived_from", src.uid)], body=draft["body"] + note, do_commit=do_commit,
                               actor=actor)
            created.append(made["id"])
        elif stage == "draft_decision":
            fields = {"paths": _draft_paths(draft)}
            if not fields["paths"]:
                raise SystemExit("refused: a decision draft needs at least one repo-relative path")
            made = _new_locked(repo, "decision", draft["title"], fields=fields,
                               links=[("inspired_by", src.uid)], body=draft["body"] + note, do_commit=do_commit,
                               actor=actor)
            created.append(made["id"])
        elif stage == "draft_plan":
            ini = str(cfg.get("plan_initiative") or "").strip()
            if not ini:
                return dict(out, step="blocked", reason="autonomy.yaml names no plan_initiative to put the plan under")
            dec_paths = L.as_list(src.fm.get("paths"))
            epic = _new_locked(repo, "epic", draft["title"],
                               fields={"initiative": ini, "paths": dec_paths}, links=[("implements", src.uid)],
                               body=draft["body"] + note, do_commit=do_commit, actor=actor)
            created.append(epic["id"])
        else:   # draft_task
            task_title = str(draft.get("task_title") or draft["title"]).strip()[:140]
            dod = str(draft.get("task_dod") or "").strip()
            if not dod or "\n" in task_title:
                raise SystemExit("refused: a plan task draft needs a one-line task_title and a task_dod "
                                 "(its acceptance criterion)")
            made = _new_locked(repo, "task", task_title, fields={"epic": st["epic"].id, "definition_of_done": dod},
                               links=[], body="", do_commit=do_commit, actor=actor)
            created.append(made["id"])
        transaction(repo, {}, [dict(op="pipeline_step", actor=actor, stage=stage, id=src.id, uid=src.uid,
                                    created=created)], f"kb: pipeline {stage} for {src.id} -> {created}",
                    do_commit=do_commit)
        if stage == "draft_plan":    # the plan is an epic AND its first task: one step, two commits
            return dict(out, created=created, note="run the step again: the epic still needs its first task")
    return dict(out, created=created)


def orchestrate(repo: Path, ref: str, *, reviewer: str = "", reviewer_cmd: str = "", drafter_cmd: str = "",
                lead_questions: list[str] | None = None, actor: str = "kb-orchestrator",
                delay: float = 0.0, do_commit: bool = True) -> dict:
    """One resumable step. A REVIEW ref drives the calibrated review loop (T-0050); an idea,
    concept or decision ref advances its pipeline from wherever it stands (T-0068)."""
    idx = M.Index(M.discover(M.load_sources(repo)))
    hits = idx.resolve(ref)
    if len(hits) == 1 and hits[0].type == "review":
        if not reviewer.strip() or not reviewer_cmd.strip():
            raise SystemExit("refused: a review round needs --reviewer and --reviewer-cmd")
        return _orchestrate_review(repo, ref, reviewer=reviewer, reviewer_cmd=reviewer_cmd,
                                   lead_questions=lead_questions, actor=actor, delay=delay, do_commit=do_commit)
    return _orchestrate_pipeline(repo, ref, reviewer=reviewer, reviewer_cmd=reviewer_cmd, drafter_cmd=drafter_cmd,
                                 lead_questions=lead_questions, actor=actor, delay=delay, do_commit=do_commit)


# --- G6 drift sweep (T-0044, CONCEPT-0090 §3.1/§3.5) ------------------------------------

def _tree_ref(repo: Path, rd: Path) -> str | None:
    """The committed state a check may read: the KB's own HEAD, a sibling's origin/main —
    never a working tree, which any session can have mid-rename or stashed (review R5-C1).
    None when the repo is absent or has no origin/main: then it cannot be judged at all."""
    if not (rd / ".git").exists():
        return None
    if _git_ok(rd, "rev-parse", "-q", "--verify", "refs/remotes/origin/main"):
        return "refs/remotes/origin/main"     # also for the KB: an unpushed file proves nothing (R6-A4)
    return "HEAD" if rd.resolve() == repo.resolve() else None


def _tree_files(repo: Path, rd: Path, cache: dict) -> "set[str] | None":
    key = str(rd.resolve()) if rd.exists() else str(rd)
    if key not in cache:
        ref = _tree_ref(repo, rd)
        files = None
        if ref is not None:
            out = subprocess.run(["git", "-C", str(rd), "ls-tree", "-r", "-z", "--name-only", ref],
                                 capture_output=True, text=True)
            files = set(out.stdout.split("\0")) - {""} if out.returncode == 0 else None
        cache[key] = files
    return cache[key]


def _path_state(repo: Path, p: str, cache: dict | None = None) -> str:
    """'present' | 'absent' | 'unknown' for an ADR `paths:` entry, judged against TRACKED files of
    committed trees (see _tree_ref). A candidate whose repo is missing makes the answer
    'unknown' unless another candidate has the path — an absent sibling is not drift."""
    import fnmatch
    cache = {} if cache is None else cache
    p = str(p).strip()
    root = projects_root(repo)
    unknown = False
    for base, cand in path_candidates(repo, p):
        if base == root:                                 # "<Repo>/path" form only
            parts = Path(p).parts
            if not parts or parts[0] not in (*SIBLING_REPOS, M.KB_NAME):
                continue
            base = repo if parts[0] == M.KB_NAME else root / parts[0]
            rel = "/".join(parts[1:])
        else:
            rel = cand.relative_to(base).as_posix()
        files = _tree_files(repo, base, cache)
        if files is None:
            unknown = True
            continue
        r = rel.rstrip("/")
        if r in ("", "."):
            if files:
                return "present"
        elif any(ch in r for ch in "*?["):
            if any(L.glob_match(f, r) for f in files):
                return "present"
        elif r in files or any(f.startswith(r + "/") for f in files):
            return "present"
    return "unknown" if unknown else "absent"


def _path_exists(repo: Path, p: str, cache: dict | None = None) -> bool:
    return _path_state(repo, p, cache) == "present"


def _patch_on_main(rd: Path, sha: str) -> bool:
    """The commit's CHANGE is on origin/main under another sha (a rebase, a cherry-pick):
    `git cherry` marks such a commit with '-'."""
    out = subprocess.run(["git", "-C", str(rd), "cherry", "refs/remotes/origin/main", sha, f"{sha}~1"],
                         capture_output=True, text=True)
    return out.returncode == 0 and out.stdout.strip().startswith("-")


def _fm_on_main(repo: Path, e: "M.Entity") -> dict | None:
    """An entity's frontmatter in the tree _tree_ref judges (the KB's origin/main), or None."""
    ref = _tree_ref(repo, repo)
    try:
        rel = e.path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return None
    if ref is None:
        return None
    out = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{rel}"], capture_output=True)
    if out.returncode != 0:
        return None
    return L.fm_of(out.stdout.decode("utf-8", "replace").lstrip("\ufeff").replace("\r\n", "\n"))


def _commit_on_any_main(repo: Path, sha: str) -> bool:
    """A decision's commit is present when it — or an equivalent patch after a rebase — is on
    origin/main of a known repo. ADR-2205's commits were rebased; raw ancestry read the
    rebase as vanished work and the first sweep would have regressed six done tasks."""
    return _commit_state(repo, sha) == "present"


def _commit_state(repo: Path, sha: str) -> str:
    """'present' | 'absent' | 'unknown'. Absent means: some repo HAS the commit object and neither
    it nor a patch-equivalent is on that repo's origin/main (rebased away, reverted out). A sha
    no checked-out repo knows at all — a sibling not checked out here, a stale fetch — cannot be
    judged and is never drift (review R6-A3)."""
    sha = str(sha).strip()
    rds = [rd for rd in (repo, projects_root(repo) / "CorvinOS", projects_root(repo) / "Corvin-Marketplace")
           if (rd / ".git").exists()]
    if any(commit_on_main(rd, sha) for rd in rds):
        return "present"
    have = [rd for rd in rds if _git_ok(rd, "cat-file", "-e", f"{sha}^{{commit}}")]
    if any(_patch_on_main(rd, sha) for rd in have):
        return "present"
    return "absent" if have else "unknown"


def sweep(repo: Path, *, create_tasks: bool = False, actor: str = "kb-sweep", do_commit: bool = True) -> dict:
    """G6: for every BUILT decision (realization == built) its `paths:` must exist and its
    `commits:` must be on origin/main; for every done task its done_evidence must still hold.
    Drift becomes a NEW task with `regresses:` (a done task is never reopened) and pauses the
    drift area for A2 (breaker drift_area_pause). Legacy decisions that were never built are
    not swept — their unresolved paths are the ratchet's business (adr_lint), not drift."""
    idx = M.Index(M.discover(M.load_sources(repo)))
    drift: list[tuple[M.Entity, list[M.Entity], str]] = []
    unswept: list[str] = []
    trees: dict = {}
    for d in idx.ents:
        if d.type != "decision" or not d.writable or M.realization(d, idx) != "built":
            continue
        tasks = [x for x in idx.ents if x.type == "task" and x.status == "done"
                 and (any(ln.rel == "implements" and d in idx.resolve(ln.to) for ln in x.links)
                      or d in _epic_decisions(x, idx))]
        # the decision as it is ON MAIN — its paths are judged on origin/main, so a path added in an
        # unpushed local commit must not read as vanished (review R7-A4)
        dfm = _fm_on_main(repo, d)
        if dfm is None:
            unswept.append(f"{d.id}: not on origin/main yet")
            continue
        for pth in L.as_list(dfm.get("paths")):
            state = _path_state(repo, pth, trees)
            if state == "absent":
                drift.append((d, tasks, f"{d.id}: path {pth} no longer exists"))
            elif state == "unknown":
                unswept.append(f"{d.id}: path {pth} (its repo is not checked out here)")
        for c in L.as_list(dfm.get("commits")):
            cst = _commit_state(repo, c)
            if cst == "absent":
                drift.append((d, tasks, f"{d.id}: commit {c} is not on origin/main"))
            elif cst == "unknown":
                unswept.append(f"{d.id}: commit {c} (no checked-out repo has it)")
    for t in idx.ents:
        if t.type == "task" and t.writable and t.status == "done" and "done_evidence" in t.fm:
            ev = t.fm["done_evidence"]
            if not isinstance(ev, dict):
                drift.append((t, [t], f"{t.id}: done_evidence is not a mapping"))
                continue
            evs = {k: str(v) for k, v in ev.items()}
            rd = _repo_dir(repo, evs.get("repo"))
            if rd is not None and _tree_ref(repo, rd) is None:
                unswept.append(f"{t.id}: evidence repo {evs.get('repo')} is not checked out here")
                continue
            for _cls, why in evidence_problems(repo, evs, trees=trees):
                drift.append((t, [t], f"{t.id}: {why}"))
    created = []
    if create_tasks:
        # one regression task per done task, carrying ALL of its current drift; its drift_key
        # is the hash of that set, so a cancelled regression covers exactly the drift a human
        # looked at — a later, different drift creates a new one (review R2-A6)
        per: dict[str, dict] = {}
        for target, done_tasks, what in drift:
            for dt_ in done_tasks:
                g = per.setdefault(dt_.uid, {"task": dt_, "whats": [], "targets": []})
                g["whats"].append(what)
                g["targets"].append(target)
        for uid, g in per.items():
            whats = sorted(set(g["whats"]))
            key = hashlib.sha256("\n".join(whats).encode()).hexdigest()[:16]
            with kb_lock(repo):
                fresh = M.Index(M.discover(M.load_sources(repo)))
                cur = fresh.one(uid)
                if cur is None or not cur.parent_id:
                    continue
                regs = [o for o in fresh.ents if o.type == "task" and any(
                    ln.rel == "regresses" and cur in fresh.resolve(ln.to) for ln in o.links)]
                if any(o.status not in ("done", "cancelled") for o in regs) \
                        or any(o.status == "cancelled" and str(o.fm.get("drift_key")) == key for o in regs):
                    continue    # one open regression at a time; a cancelled one covers ITS drift set only
                summary = whats[0] + (f" (+{len(whats) - 1} more)" if len(whats) > 1 else "")
                nt = _new_locked(repo, "task", f"Regression: {cur.id} — {summary}"[:140],
                                 fields={"epic": cur.parent_id, "drift_key": key,
                                         "definition_of_done": "restore or re-prove what vanished: " + "; ".join(whats)},
                                 links=[("regresses", cur.uid)], body="", do_commit=do_commit, actor=actor)
                log_finding(repo, "G6_drift", entity_id=cur.id, entity_uid=cur.uid, detail="; ".join(whats),
                            actor=actor, do_commit=do_commit)
                for target in {id(t_): t_ for t_ in g["targets"]}.values():
                    area = [target] if target.type == "decision" else M.implemented_decisions(target, fresh)
                    paths = sorted({p_ for dd in area for p_ in L.as_list(dd.fm.get("paths"))})
                    trip(repo, "drift_area_pause", actor=actor, scope=target.id or target.uid, detail=summary,
                         extra=dict(paths=paths, regression_tasks=[nt["id"]]), do_commit=do_commit)
                created.append(nt["id"])
                _postcondition(repo, actor, do_commit)   # same lock section as its "before"
    return dict(drift=[w for _t, _d, w in drift], created=created, unswept=unswept)


# --- export (projection payload) + verify -------------------------------------------

def export(repo: Path, ents: list[M.Entity] | None = None, res: dict | None = None) -> dict:
    ents = ents if ents is not None else M.discover(M.load_sources(repo))
    res = res or check(ents, repo)
    idx = M.Index(ents)
    items, reviews = [], []
    for e in ents:
        if not e.writable or not e.uid:
            continue
        if e.type == "review":
            # Reviews are NOT board work items: the board's item model knows initiative/epic/
            # task only, and one `kind: review` row put every projector tick into `error`
            # (the board froze from T-0041 on). They travel in their own, unprojected list.
            reviews.append(dict(ref=f"kb:{e.uid}", id=e.id, status=e.status or "open",
                                reviews=[x.id for ln in e.links if ln.rel == "reviews"
                                         for x in idx.resolve(ln.to)]))
            continue
        if e.type not in ("initiative", "epic", "task"):
            continue
        parent = None
        if e.parent_id:
            p = [h for h in idx.resolve(e.parent_id) if h.type == M.PARENT[e.type][1]]
            parent = f"kb:{p[0].uid}" if len(p) == 1 and p[0].uid else None
        impl_decisions = [x for ln in e.links if ln.rel == "implements" for x in idx.resolve(ln.to)
                          if x.type == "decision"]
        impl = [x.id for x in impl_decisions]
        # read-only board badge (T-0040): True only if EVERY implemented decision is ready;
        # None (no badge) when the epic implements no decision at all
        ready = all(M.implementation_ready(x, idx) for x in impl_decisions) if impl_decisions else None
        labels = L.as_list(e.fm.get("labels"))
        if ready is True and "ready" not in labels:
            # read-only board badge (T-0040), carried through the EXISTING labels pipeline
            # (projection.py's PROJECTED/_desired already copies labels verbatim) -- no new
            # writer, no new store column, no CorvinOS backend change needed
            labels.append("ready")
        items.append(dict(
            ref=f"kb:{e.uid}", id=e.id, kind=e.type, parent_ref=parent,
            title=f"{e.id} · {e.title}", status=M.effective_status(e, idx),
            labels=labels, implements=impl,
            implementation_ready=ready,
            completed_at=str(e.fm["completed_at"]) if e.fm.get("completed_at") else None,
            blocked_reason=e.fm.get("blocked_reason"),
        ))
    items.sort(key=lambda x: ({"initiative": 0, "epic": 1, "task": 2}[x["kind"]], x["id"]))
    reviews.sort(key=lambda x: x["id"])
    head = L.git(repo, "rev-parse", "HEAD", check=False).strip() or None
    dirty = bool(L.git(repo, "status", "--porcelain", "--", "kb", check=False).strip())
    return dict(namespace="kb", sha=head, dirty=dirty, ok=res["blocking"] == 0,
                blocking=res["blocking"], failing=res["native_counts"], items=items, reviews=reviews)


PROJECTED_FIELDS = ("kind", "parent_ref", "title", "status")


def verify(expected: dict, actual: list[dict]) -> list[dict]:
    """Diff the export against task-manager items ({ref, kind, parent_ref, title, status})."""
    act = {a["ref"]: a for a in actual if str(a.get("ref", "")).startswith("kb:")}
    diffs = []
    for it in expected["items"]:
        a = act.pop(it["ref"], None)
        if a is None:
            diffs.append(dict(ref=it["ref"], id=it["id"], problem="missing"))
            continue
        for f in PROJECTED_FIELDS:
            if a.get(f) != it[f]:
                diffs.append(dict(ref=it["ref"], id=it["id"], problem="field", field=f,
                                  expected=it[f], actual=a.get(f)))
    for ref, a in act.items():
        if a.get("status") != "archived":
            diffs.append(dict(ref=ref, id=a.get("title"), problem="orphan"))
    return diffs


# --- find / show ------------------------------------------------------------------

_WORD = re.compile(r"[a-z0-9äöüß]+")


def find(repo: Path, terms: list[str], *, type_: str | None = None, status: str | None = None,
         limit: int = 20) -> list[dict]:
    """Ranked search. An exact id/uid hit wins; then title words weigh 5x body words.
    Status filter uses the EFFECTIVE status (rollups for containers)."""
    ents = M.discover(M.load_sources(repo))
    idx = M.Index(ents)
    q = [t.lower() for t in terms if t.strip()]
    exact = {x for t in terms for x in idx.resolve(t)}
    words = [w for t in q for w in _WORD.findall(t)]
    phrase = " ".join(words)
    texts = {id(e): (e.title.lower(), e.doc.text.lower()) for e in ents}
    import math
    df = {w: sum(1 for t, b in texts.values() if w in t or w in b) for w in set(words)}
    idf = {w: math.log((len(ents) + 1) / (df[w] + 1)) + 0.1 for w in df}   # rare words decide
    hits = []
    for e in ents:
        if type_ and e.type != type_:
            continue
        st = M.effective_status(e, idx)
        if status and st != status:
            continue
        if e in exact:
            score = 1000.0
        else:
            title, body = texts[id(e)]
            if not words or not all(w in body or w in title for w in words):
                continue
            score = sum((5 * title.count(w) + min(body.count(w), 5)) * idf[w] for w in words)
            flat_title = " ".join(_WORD.findall(title))
            if phrase and phrase in flat_title:
                score += 50                      # the whole phrase in the title
            elif phrase and phrase in " ".join(_WORD.findall(body)):
                score += 10
        hits.append(dict(score=round(score, 1), id=e.id, type=e.type, status=st, title=e.title,
                         path=os.path.relpath(e.path, repo)))
    hits.sort(key=lambda h: (-h["score"], h["id"] or ""))
    return hits[:limit]


def show(repo: Path, ref: str) -> dict:
    ents = M.discover(M.load_sources(repo))
    idx = M.Index(ents)
    hs = idx.resolve(ref)
    if len(hs) != 1:
        raise SystemExit(f"{ref} resolves to {len(hs)} entities: "
                         + ", ".join(os.path.relpath(h.path, repo) for h in hs))
    e = hs[0]
    out = dict(id=e.id, uid=e.uid, type=e.type, title=e.title, status=M.effective_status(e, idx),
               path=os.path.relpath(e.path, repo), parent=e.parent_id,
               links=[dict(rel=ln.rel, to=ln.to) for ln in e.links],
               backlinks=sorted({f"{o.id} --{ln.rel}-->" for o in ents for ln in o.links
                                 if not ln.external and e in idx.resolve(ln.to)}),
               children=[f"{c.id} [{M.effective_status(c, idx)}] {c.title}" for c in idx.children(e)])
    if e.type == "decision":
        out["realization"] = M.realization(e, idx)
        out["implementation_ready"] = M.implementation_ready(e, idx)
    if e.fm.get("renumbered_from"):
        out["renumbered_from"] = e.fm["renumbered_from"]
    return out


# --- index ----------------------------------------------------------------------------

def index(repo: Path) -> dict:
    ents = M.discover(M.load_sources(repo))
    idx = M.Index(ents)
    g = repo / "kb/graph"
    g.mkdir(parents=True, exist_ok=True)
    n_rel = 0
    with open(g / "entities.jsonl", "w") as fe, open(g / "relations.jsonl", "w") as fr:
        for e in ents:
            row = dict(uid=e.uid, id=e.id, type=e.type, title=e.title, status=M.effective_status(e, idx),
                       source=e.source.name, path=str(e.path),
                       labels=L.as_list(e.fm.get("labels")))
            if e.type == "decision":
                row["realization"] = M.realization(e, idx)
            fe.write(json.dumps(row, ensure_ascii=False) + "\n")
            for ln in e.links:
                tgt = idx.one(ln.to) if not ln.external else None
                fr.write(json.dumps(dict(src=e.uid or e.id, rel=ln.rel,
                                         dst=(tgt.uid or tgt.id) if tgt else ln.to,
                                         external=ln.external, resolved=bool(tgt) or ln.external)) + "\n")
                n_rel += 1
            if e.parent_id:
                p = idx.one(e.parent_id)
                fr.write(json.dumps(dict(src=e.uid, rel="child_of", dst=p.uid if p else e.parent_id,
                                         external=False, resolved=bool(p))) + "\n")
                n_rel += 1
    return dict(entities=len(ents), relations=n_rel, dir=str(g))


# --- cli ------------------------------------------------------------------------------

import yaml  # noqa: E402  (after sys.path setup; kb_lib already requires it)


def _kv(pairs: list[str], flag: str) -> dict:
    bad = [x for x in pairs if "=" not in x]
    if bad:
        raise SystemExit(f"refused: {flag} needs {'rel=target' if flag == '--link' else 'key=value'}, got {bad}")
    return dict(x.split("=", 1) for x in pairs)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kb", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, default=Path(os.environ.get("KB_REPO", M.REPO)))
    actor_default = os.environ.get("KB_ACTOR", "kb")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def with_actor(sp, commit=True):
        sp.add_argument("--actor", default=actor_default)
        if commit:
            sp.add_argument("--no-commit", action="store_true")
        return sp
    c = sub.add_parser("check"); c.add_argument("--json", type=Path); c.add_argument("--strict", action="store_true")
    c.add_argument("--refresh", action="store_true", help="fetch pinned sources first")
    h = with_actor(sub.add_parser("heal")); h.add_argument("--dry-run", action="store_true")
    n = with_actor(sub.add_parser("new")); n.add_argument("type"); n.add_argument("--title", required=True)
    n.add_argument("--epic"); n.add_argument("--initiative"); n.add_argument("--status")
    n.add_argument("--dod", help="definition_of_done (tasks)")
    n.add_argument("--distinct-because", help="G0: why a near-duplicate idea/concept is a different thing")
    n.add_argument("--link", action="append", default=[], help="rel=target (id, uid or URI)")
    n.add_argument("--body", default="")
    rv = sub.add_parser("review", help="the review loop: open | round | calibrate | close | status")
    rsub = rv.add_subparsers(dest="rcmd", required=True)
    ro = with_actor(rsub.add_parser("open")); ro.add_argument("--title", required=True)
    ro.add_argument("--reviews", action="append", default=[], help="decision/epic id (repeatable)")
    rr = with_actor(rsub.add_parser("round")); rr.add_argument("ref")
    rr.add_argument("--lead-question", required=True); rr.add_argument("--reviewer", required=True)
    rr.add_argument("--findings", type=int, required=True); rr.add_argument("--delay", type=float, default=0.0)
    rc = with_actor(rsub.add_parser("calibrate")); rc.add_argument("ref")
    rc.add_argument("--lead-question", required=True); rc.add_argument("--reviewer", required=True)
    rc.add_argument("--reviewer-cmd", required=True); rc.add_argument("--seed-kind")
    rc.add_argument("--delay", type=float, default=0.0); rc.add_argument("--timeout", type=int, default=1800)
    rf = with_actor(rsub.add_parser("fix", help="claim a fix for a finding; the next round removes it again"))
    rf.add_argument("ref"); rf.add_argument("--round", type=int, required=True, dest="fround")
    rf.add_argument("--finding", type=int, required=True, help="ordinal of the finding in that round (1-based)")
    rf.add_argument("--commit", required=True); rf.add_argument("--test", required=True)
    rf.add_argument("--test-cmd", default="", help="humans only; default: python -m pytest -q -x TEST")
    rf.add_argument("--workdir", default="", help="git checkout holding the fix (default: this KB)")
    rcl = with_actor(rsub.add_parser("close")); rcl.add_argument("ref")
    rs = with_actor(rsub.add_parser("status")); rs.add_argument("ref"); rs.add_argument("to")
    rs.add_argument("--reason", default="")
    t = with_actor(sub.add_parser("task")); t.add_argument("ref"); t.add_argument("to")
    t.add_argument("--reason", default=""); t.add_argument("--dod", default="")
    t.add_argument("--evidence", action="append", default=[],
                   help="G5 for code tasks: call_site=… e2e_test=… exit_code=0 commit=<sha> [repo=CorvinOS]")
    t.add_argument("--via", default="cli")
    sub.add_parser("export")
    sub.add_parser("queue", help="the human queue (escalated reviews, human-required decisions, incidents)")
    le = sub.add_parser("learn", help="finding_classified records by class over a window")
    le.add_argument("--days", type=int, default=30)
    gu = sub.add_parser("guidance", help="run | pending | ack | retire (T-0049)")
    gsub = gu.add_subparsers(dest="gcmd", required=True)
    with_actor(gsub.add_parser("run"))
    gsub.add_parser("pending")
    ga = with_actor(gsub.add_parser("ack")); ga.add_argument("finding_class"); ga.add_argument("--skill", default="")
    ga.add_argument("--retired", action="store_true")
    gr = with_actor(gsub.add_parser("retire")); gr.add_argument("finding_class"); gr.add_argument("--reason", default="")
    oc = with_actor(sub.add_parser("orchestrate", help="one resumable step: a review round, or the next pipeline stage"))
    oc.add_argument("ref"); oc.add_argument("--reviewer", default=""); oc.add_argument("--reviewer-cmd", default="")
    oc.add_argument("--drafter-cmd", default="", help="drafts a concept/decision/plan from the source on stdin")
    oc.add_argument("--lead-question", action="append", default=[]); oc.add_argument("--delay", type=float, default=0.0)
    sw = with_actor(sub.add_parser("sweep", help="G6 drift sweep (T-0044)")); sw.add_argument("--create-tasks", action="store_true")
    br = sub.add_parser("breaker", help="status | reset (T-0047)")
    bsub = br.add_subparsers(dest="bcmd", required=True)
    bsub.add_parser("status")
    bres = with_actor(bsub.add_parser("reset")); bres.add_argument("key"); bres.add_argument("--reason", default="")
    v = sub.add_parser("verify"); v.add_argument("--items", type=Path, required=True)
    sub.add_parser("index")
    fd = sub.add_parser("find"); fd.add_argument("terms", nargs="+"); fd.add_argument("--type")
    fd.add_argument("--status"); fd.add_argument("--limit", type=int, default=20)
    sh_ = sub.add_parser("show"); sh_.add_argument("ref")
    b = with_actor(sub.add_parser("baseline", help="shrink the accepted-findings baseline (or --init the first one)"))
    b.add_argument("--init", action="store_true")
    b.add_argument("--init-rule", metavar="RULE", help="admit every current finding of ONE freshly introduced rule, once")
    b.add_argument("--accept", nargs=3, metavar=("RULE", "FILE", "DETAIL"))
    b.add_argument("--reason", default="")
    ns = ap.parse_args(argv)
    repo = ns.repo.resolve()
    dc = not getattr(ns, "no_commit", False)
    try:
        if ns.cmd == "check":
            if ns.refresh:
                M.load_sources(repo, refresh=True)
            res = check(M.discover(M.load_sources(repo)), repo)
            if ns.json:
                ns.json.write_text(json.dumps(res, indent=1, ensure_ascii=False))
            print(json.dumps({k: res[k] for k in ("entities", "blocking", "baselined", "legacy_findings",
                                                  "native_counts", "counts")}, indent=1))
            return 1 if res["blocking"] or (ns.strict and any(res["counts"].values())) else 0
        if ns.cmd == "heal":
            r = heal(repo, dry_run=ns.dry_run, do_commit=dc, actor=ns.actor if ns.actor != "kb" else "kb-heal")
        elif ns.cmd == "new":
            f = {k: v for k, v in (("epic", ns.epic), ("initiative", ns.initiative), ("status", ns.status),
                                   ("definition_of_done", ns.dod), ("distinct_because", ns.distinct_because)) if v}
            _kv(ns.link, "--link")   # validates key=value; a rel may repeat, so the list is kept as-is
            links = [tuple(x.split("=", 1)) for x in ns.link]
            r = new(repo, ns.type, ns.title, fields=f, links=links, body=ns.body, do_commit=dc, actor=ns.actor)
        elif ns.cmd == "review":
            if ns.rcmd == "open":
                r = review_open(repo, ns.title, ns.reviews, actor=ns.actor, do_commit=dc)
            elif ns.rcmd == "round":
                r = review_round(repo, ns.ref, lead_question=ns.lead_question, reviewer=ns.reviewer,
                                 findings=ns.findings, actor=ns.actor, delay=ns.delay, do_commit=dc)
            elif ns.rcmd == "calibrate":
                r = review_calibrate(repo, ns.ref, lead_question=ns.lead_question, reviewer=ns.reviewer,
                                     reviewer_cmd=ns.reviewer_cmd, seed_kind=ns.seed_kind, actor=ns.actor,
                                     delay=ns.delay, timeout=ns.timeout, do_commit=dc)
            elif ns.rcmd == "fix":
                r = review_fix(repo, ns.ref, round_n=ns.fround, finding=ns.finding, commit=ns.commit,
                               test=ns.test, test_cmd=ns.test_cmd, workdir=ns.workdir, actor=ns.actor,
                               do_commit=dc)
            elif ns.rcmd == "close":
                r = review_close(repo, ns.ref, actor=ns.actor, do_commit=dc)
            else:
                r = review_set_status(repo, ns.ref, ns.to, reason=ns.reason, actor=ns.actor, do_commit=dc)
        elif ns.cmd == "task":
            r = task(repo, ns.ref, ns.to, reason=ns.reason, dod=ns.dod, via=ns.via, actor=ns.actor,
                     evidence=_kv(ns.evidence, "--evidence"), do_commit=dc)
        elif ns.cmd == "export":
            r = export(repo)
        elif ns.cmd == "queue":
            r = queue_status(repo)
        elif ns.cmd == "learn":
            r = learn(repo, days=ns.days)
        elif ns.cmd == "guidance":
            if ns.gcmd == "run":
                r = guidance_pass(repo, actor=ns.actor if ns.actor != "kb" else "kb-guidance", do_commit=dc)
            elif ns.gcmd == "pending":
                r = guidance_pending(repo)
            elif ns.gcmd == "ack":
                r = guidance_ack(repo, ns.finding_class, skill=ns.skill, retired=ns.retired, actor=ns.actor,
                                 do_commit=dc)
            else:
                r = guidance_retire(repo, ns.finding_class, reason=ns.reason, actor=ns.actor, do_commit=dc)
        elif ns.cmd == "orchestrate":
            r = orchestrate(repo, ns.ref, reviewer=ns.reviewer, reviewer_cmd=ns.reviewer_cmd,
                            drafter_cmd=ns.drafter_cmd, lead_questions=ns.lead_question or None,
                            actor=ns.actor if ns.actor != "kb" else "kb-orchestrator", delay=ns.delay, do_commit=dc)
        elif ns.cmd == "sweep":
            r = sweep(repo, create_tasks=ns.create_tasks, actor=ns.actor if ns.actor != "kb" else "kb-sweep",
                      do_commit=dc)
        elif ns.cmd == "breaker":
            r = dict(tripped=breakers(repo)) if ns.bcmd == "status" else \
                breaker_reset(repo, ns.key, actor=ns.actor, reason=ns.reason, do_commit=dc)
        elif ns.cmd == "verify":
            d = verify(export(repo), json.loads(ns.items.read_text()))
            print(json.dumps(d, indent=1, ensure_ascii=False))
            return 1 if d else 0
        elif ns.cmd == "index":
            r = index(repo)
        elif ns.cmd == "find":
            r = find(repo, ns.terms, type_=ns.type, status=ns.status, limit=ns.limit)
        elif ns.cmd == "show":
            r = show(repo, ns.ref)
        elif ns.cmd == "baseline":
            r = write_baseline(repo, init=ns.init, accept=tuple(ns.accept) if ns.accept else None,
                               reason=ns.reason, do_commit=dc, init_rule=ns.init_rule, actor=ns.actor)
        print(json.dumps(r, indent=1, ensure_ascii=False, default=str))
        return 0
    except SystemExit as e:
        if isinstance(e.code, str):
            print(json.dumps({"error": e.code}, ensure_ascii=False), file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    sys.exit(main())
