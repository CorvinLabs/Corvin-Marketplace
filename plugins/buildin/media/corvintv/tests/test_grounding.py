"""Grounding pack (CONCEPT-0100, PLAN-0942 P1): resolver, safety limits, truth labels.

A fixture knowledge base and a fixture git checkout reproduce the structures the real
ones have (graph JSONL, decision markdown with ``paths:``, renamed directories, untracked
tenant data next to tracked code). ``test_grounding_real_kb.py`` checks the ranking on
the real knowledge base.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from src import grounding as g


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _decision(kb: Path, did: str, title: str, status: str, *, paths=(), depends=(), body="") -> dict:
    lines = ["---", f"id: {did}", f"status: {status}", "created: '2026-09-01T00:00:00+00:00'"]
    lines.append("paths:" + ("" if paths else " []"))
    lines += [f"- {p}" for p in paths]
    lines.append("depends_on:" + ("" if depends else " []"))
    lines += [f"- {d}" for d in depends]
    lines += ["---", "", f"# {did} — {title}", "", body or "## Context\n\nSome context.\n\n## Decision\n\nWe decide."]
    path = kb / "decisions" / f"{did}-x.md"
    path.write_text("\n".join(lines) + "\n")
    return {"uid": f"U{did[-4:]}", "id": did, "type": "decision", "title": title, "status": status,
            "path": str(path)}


@pytest.fixture
def world(tmp_path):
    kb = tmp_path / "kb"
    (kb / "decisions").mkdir(parents=True)
    (kb / "kb" / "graph").mkdir(parents=True)
    code = tmp_path / "code"
    (code / "corvin_operator" / "chain").mkdir(parents=True)
    (code / "core").mkdir()
    (code / "tests").mkdir()
    (code / "corvin_operator" / "chain" / "writer.py").write_text(
        '"""Hash chain writer.\n\nEach record carries prev_hash and hash = sha256(prev_hash || record)[:16].\n'
        'Contact ops@example.com on 10.0.0.7, key sk-abcdefghijklmnop, see /home/alice/notes.\n"""\n\n'
        "def append_record(path, record):\n    \"\"\"Append one chained record.\"\"\"\n    return record\n\n"
        "class ChainVerifier:\n    \"\"\"Walks the file and checks every link.\"\"\"\n"
    )
    (code / "core" / "boot.py").write_text("from corvin_operator.chain.writer import append_record\n\nappend_record('a', {})\n")
    (code / "tests" / "test_writer.py").write_text("ChainVerifier()\n")
    (code / "core" / "only_in_tests.py").write_text('"""Module."""\n\ndef lonely_helper_fn():\n    pass\n')
    (code / "core" / "big.py").write_text('"""Huge module."""\n' + "#" * (g.MAX_CODE_BYTES + 10) + "\n")
    _git(code, "init", "-q")
    _git(code, "add", "-A")
    _git(code, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init")
    # untracked tenant data next to the tracked tree (like <repo>/.corvin)
    (code / ".corvin" / "tenants" / "acme").mkdir(parents=True)
    (code / ".corvin" / "tenants" / "acme" / "tool.py").write_text('"""ACME PRIVATE TOOL."""\n')

    ents = [
        _decision(kb, "ADR-0001", "Audit chain — hash linking of records", "accepted",
                  paths=["operator/chain/writer.py"],  # stale name: lives under corvin_operator/ now
                  body="## Decision\n\nRecords are linked by `append_record` and checked by `ChainVerifier`. "
                       "Verification of 1,000 records takes 12 ms.\n\n## Alternatives considered\n\n"
                       "### A. Signed files\n\n### B. Database triggers\n"),
        _decision(kb, "ADR-0002", "Audit chain — a proposed redesign", "proposed",
                  paths=["corvin_operator/chain/writer.py"]),
        _decision(kb, "ADR-0003", "Audit chain — the old way", "superseded"),
        _decision(kb, "ADR-0004", "Audit chain without any code anchors", "accepted"),
        _decision(kb, "ADR-0005", "Audit chain planned extension", "accepted", paths=["core/not_written_yet.py"]),
        _decision(kb, "ADR-0006", "Audit chain tenant tool", "accepted", paths=[".corvin/tenants/acme/tool.py"]),
        _decision(kb, "ADR-0007", "Audit chain helper only used by tests", "accepted",
                  paths=["core/only_in_tests.py"], body="## Decision\n\nUse `lonely_helper_fn`.\n"),
        _decision(kb, "ADR-0008", "Audit chain giant module", "accepted", paths=["core/big.py"]),
        _decision(kb, "ADR-0009", "Unrelated photosynthesis note", "accepted"),
    ]
    outside = tmp_path / "elsewhere.md"
    outside.write_text("---\nid: ADR-0099\n---\n# leaked\n")
    ents.append({"uid": "U0099", "id": "ADR-0099", "type": "decision", "title": "Audit chain outside", "status": "accepted",
                 "path": str(outside)})
    ents.append({"uid": "C1", "id": "CONCEPT-0001", "type": "concept", "title": "Audit chain concept", "status": "accepted",
                 "path": str(kb / "decisions" / "ADR-0001-x.md")})
    (kb / "kb" / "graph" / "entities.jsonl").write_text("\n".join(json.dumps(e) for e in ents) + "\n")
    # ADR-0004 is referenced by two other decisions -> more central than ADR-0005
    rels = [{"src": "U0001", "rel": "related", "dst": "U0004"}, {"src": "U0002", "rel": "related", "dst": "U0004"},
            {"src": "C1", "rel": "related", "dst": "U0005"}]
    (kb / "kb" / "graph" / "relations.jsonl").write_text("\n".join(json.dumps(r) for r in rels) + "\n")
    roots = [g.CodeRoot(code)]
    return kb, code, roots


def _ids(pack):
    return [s["id"] for s in pack["sections"]]


def _section(pack, did):
    return next(s for s in pack["sections"] if s["id"] == did)


def test_non_corvin_task_gets_no_pack(world):
    kb, _code, roots = world
    assert g.build_pack("Erkläre Photosynthese für Schüler", kb, roots) is None
    assert g.build_pack("Explain the audit chain", kb, roots) is None  # not about Corvin, names no decision


def test_ranking_accepted_before_proposed_and_superseded_excluded(world):
    kb, _code, roots = world
    pack = g.build_pack("Erkläre die Corvin Auditchain", kb, roots)
    ids = _ids(pack)
    assert "ADR-0003" not in ids and "ADR-0002" not in ids  # superseded out; proposed behind 4 accepted
    assert len(ids) == g.MAX_DECISIONS
    assert ids[0] == "ADR-0004"  # two decisions link to it; ADR-0005's only link is from a concept (does not count)
    assert "ADR-0099" not in ids  # entity file outside <kb>/decisions is never read
    assert "CONCEPT-0001" not in ids


def test_explicit_id_wins(world):
    kb, _code, roots = world
    pack = g.build_pack("Ein Video über ADR-0002 bitte", kb, roots)
    assert _ids(pack)[0] == "ADR-0002"


def test_truth_labels_need_evidence(world):
    kb, _code, roots = world
    pack = g.build_pack("Corvin ADR-0001 ADR-0004 ADR-0005 ADR-0007", kb, roots)
    s1 = _section(pack, "ADR-0001")
    assert s1["truth"] == "live"  # stale operator/ path resolved via the rename map, caller in core/boot.py
    assert "core/boot.py" in s1["evidence"]
    assert _section(pack, "ADR-0004")["truth"] == "unknown"  # no paths: never "live", never "planned"
    assert _section(pack, "ADR-0005")["truth"] == "planned"  # declared anchors, none exists
    assert _section(pack, "ADR-0007")["truth"] == "unknown"  # only a test calls it


def test_existing_but_unreadable_anchor_is_unknown_not_planned(tmp_path):
    code = tmp_path / "market"
    (code / "plugins" / "contributor" / "x").mkdir(parents=True)
    (code / "plugins" / "contributor" / "x" / "mod.py").write_text('"""Contributor module text."""\n')
    _git(code, "init", "-q")
    _git(code, "add", "-A")
    _git(code, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init")
    kb = tmp_path / "kb"
    (kb / "decisions").mkdir(parents=True)
    (kb / "kb" / "graph").mkdir(parents=True)
    ent = _decision(kb, "ADR-0020", "Audit chain in a contributor plugin", "accepted",
                    paths=["Corvin-Marketplace/plugins/contributor/x/mod.py"])
    (kb / "kb" / "graph" / "entities.jsonl").write_text(json.dumps(ent) + "\n")
    roots = [g.CodeRoot(code, "Corvin-Marketplace/", ("plugins/buildin/",))]
    pack = g.build_pack("Corvin ADR-0020", kb, roots)
    s = _section(pack, "ADR-0020")
    assert s["truth"] == "unknown"  # it exists; contributor code is just not excerpted
    assert "Contributor module text" not in g.render_pack(pack)


def test_untracked_tenant_data_is_never_read(world):
    kb, _code, roots = world
    pack = g.build_pack("Corvin ADR-0006", kb, roots)
    s = _section(pack, "ADR-0006")
    assert s["truth"] == "planned"
    assert "ACME" not in g.render_pack(pack)


def test_oversized_file_is_not_read(world):
    kb, _code, roots = world
    pack = g.build_pack("Corvin ADR-0008", kb, roots)
    assert "Huge module" not in g.render_pack(pack)


def test_pack_content_and_scrubbing(world):
    kb, _code, roots = world
    pack = g.build_pack("Corvin ADR-0001", kb, roots)
    text = g.render_pack(pack)
    assert "sha256(prev_hash || record)[:16]" in text  # module docstring excerpt
    assert "def append_record(path, record)" in text
    assert "Alternatives considered: A. Signed files; B. Database triggers" in text
    assert "12 ms" in text
    for leaked in ("ops@example.com", "10.0.0.7", "sk-abcdefghijklmnop", "/home/alice"):
        assert leaked not in text
    assert "<email>" in text and "<ip>" in text


def test_budget_is_respected(world):
    kb, _code, roots = world
    pack = g.build_pack("Erkläre die Corvin Auditchain", kb, roots, budget_chars=1200)
    assert len(g.render_pack(pack)) <= 1200 + 200  # sections have a 600-char floor; never unbounded


def test_symlinked_decision_is_refused(world, tmp_path):
    kb, _code, roots = world
    target = tmp_path / "secret.md"
    target.write_text("---\nid: ADR-0010\n---\n# Audit chain SECRET\n")
    link = kb / "decisions" / "ADR-0010-x.md"
    os.symlink(target, link)
    ents = (kb / "kb" / "graph" / "entities.jsonl").read_text()
    ents += json.dumps({"uid": "U0010", "id": "ADR-0010", "type": "decision", "title": "Audit chain linked",
                        "status": "accepted", "path": str(link)}) + "\n"
    (kb / "kb" / "graph" / "entities.jsonl").write_text(ents)
    pack = g.build_pack("Corvin ADR-0010 ADR-0001", kb, roots)
    assert "SECRET" not in g.render_pack(pack)
    assert "ADR-0010" not in _ids(pack)


def test_missing_graph_means_no_pack(tmp_path):
    (tmp_path / "decisions").mkdir()
    assert g.build_pack("Corvin audit chain", tmp_path, []) is None


def test_scrub_never_truncates():
    text = "x" * 5000 + " mail me at a@b.de"
    out = g.scrub(text)
    assert len(out) > 5000 and "a@b.de" not in out


def test_validate_pack_and_with_sections(world):
    kb, _code, roots = world
    pack = g.build_pack("Erkläre die Corvin Auditchain", kb, roots)
    assert g.validate_pack(pack)["sections"]
    assert g.validate_pack({"version": 1, "sections": [{"id": "x"}]}) is None
    assert g.validate_pack({"version": 2, "sections": pack["sections"]}) is None
    assert g.validate_pack("nope") is None
    bad = {"version": 1, "sections": [dict(pack["sections"][0], truth="definitely")]}
    assert g.validate_pack(bad) is None
    first = pack["sections"][0]["id"]
    assert _ids(g.with_sections(pack, [first])) == [first]
    assert g.with_sections(pack, []) is None
    assert len(g.pack_digest(pack)) == 64


def test_percent_figures_are_number_facts():
    # `%` followed by a space or full stop has no word boundary after it; `\b` never matched a percentage
    body = ("Intro line without figures here at all. On the seven tasks the share fell from 57 % to 19 %. "
            "Coverage reached 80% on the suite overall. A plain sentence that names 5 sentences only.")
    got = g._number_sentences(body, limit=5)
    assert got == ["On the seven tasks the share fell from 57 % to 19 %.",
                   "Coverage reached 80% on the suite overall."]
