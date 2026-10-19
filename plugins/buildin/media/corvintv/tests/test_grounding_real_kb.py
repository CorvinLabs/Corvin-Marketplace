"""Grounding against the REAL knowledge base and code (read-only; PLAN-0942 P1).

The fixture tests cannot show whether the ranking picks the right decisions in a
corpus of 1000+ entries — the adversarial review measured that the first design picked
NBAC/A2A drafts for "audit chain". Skipped where the sibling checkouts do not exist.
"""

import os
from pathlib import Path

import pytest

from src import grounding as g

PROJECTS = Path(os.environ.get("CORVIN_PROJECTS_DIR", Path(__file__).resolve().parents[6]))
KB = PROJECTS / "Corvin-Knowledge"
OS_ROOT = PROJECTS / "CorvinOS"
MARKET = PROJECTS / "Corvin-Marketplace"

pytestmark = pytest.mark.skipif(
    not (KB / "kb" / "graph" / "entities.jsonl").is_file() or not (OS_ROOT / ".git").exists(),
    reason="real Corvin-Knowledge / CorvinOS checkouts not present",
)


def _roots():
    return [g.CodeRoot(OS_ROOT), g.CodeRoot(MARKET, "Corvin-Marketplace/", ("plugins/buildin/",))]


def test_audit_chain_pack_carries_the_current_mechanism():
    pack = g.build_pack("Erkläre in drei Minuten, wie die Auditchain von Corvin funktioniert", KB, _roots())
    ids = [s["id"] for s in pack["sections"]]
    text = g.render_pack(pack)
    assert ids[0] == "ADR-0640"  # forgery resistance + tail anchor: the most cited accepted decision
    assert "ADR-0116" not in ids and "ADR-0117" not in ids  # proposed drafts (A2A anchoring, NBAC)
    assert "sha256(prev_hash || canonical_record_json)[:16]" in text  # the formula, from the code
    assert all(s["status"] == "accepted" for s in pack["sections"])
    assert pack["sections"][0]["truth"] == "live"
    assert "/.corvin/" not in text and "/home/" not in text
    assert len(text) <= g.DEFAULT_BUDGET_CHARS + 400


def test_unrelated_task_gets_no_pack():
    assert g.build_pack("Erkläre Photosynthese für Schüler", KB, _roots()) is None
