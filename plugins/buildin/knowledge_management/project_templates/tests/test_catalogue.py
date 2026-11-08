"""The catalogue is DATA the CorvinOS host plans and applies. These tests need only PyYAML: they check
what the host's engine would otherwise reject at load time, so a broken template never reaches a tenant.
(The full proof - creating real projects from it - lives in CorvinOS: tests/e2e/test_project_templates_catalogue_e2e.py.)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

SRC = Path(__file__).resolve().parents[1] / "src"
PLACEHOLDERS = {"project.id", "project.title", "project.tenant", "paths.python", "paths.repo", "paths.corvin_home",
                "paths.docs", "paths.kb_engine", "paths.pathsep"}
ACTIONS = {"git_init", "git_commit", "kb_scaffold", "kb_seed"}
FILE_KINDS = {"seed", "generated", "local"}
PH = re.compile(r"\{\{\s*([a-z_.]+)\s*\}\}")


def fragments() -> dict[str, dict]:
    out = {}
    for d in sorted((SRC / "fragments").iterdir()):
        out[d.name] = {"dir": d, **yaml.safe_load((d / "fragment.yaml").read_text(encoding="utf-8"))}
    return out


def templates() -> dict[str, dict]:
    return {p.stem: yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((SRC / "templates").glob("*.yaml"))}


def closure(frags, ids):
    seen, stack = set(), list(ids)
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack += frags[n].get("requires") or []
    return seen


def test_ids_match_directories_and_requires_point_at_real_fragments():
    fr = fragments()
    assert {"core", "kb", "tasks", "graph", "gates", "claude", "ldd", "experiments", "acs", "videos",
            "video_producer", "directory", "dashboard"} == set(fr)
    for fid, f in fr.items():
        assert f["id"] == fid
        for r in (f.get("requires") or []) + (f.get("suggests") or []):
            assert r in fr, f"{fid} -> {r}"


def test_requires_has_no_cycle():
    fr = fragments()
    for start in fr:
        seen, stack = set(), [(start, [start])]
        while stack:
            n, path = stack.pop()
            for r in fr[n].get("requires") or []:
                assert r != start, f"cycle: {' -> '.join(path + [r])}"
                if r not in seen:
                    seen.add(r)
                    stack.append((r, path + [r]))


def test_every_template_default_and_offered_set_is_requires_closed_and_has_core():
    fr = fragments()
    for tid, t in templates().items():
        assert t["id"] == tid
        for key in ("features", "offered"):
            assert closure(fr, t[key]) == set(t[key]), (tid, key)
        assert "core" in t["features"] and set(t["features"]) <= set(t["offered"]), tid
        assert t.get("docs_mode", "nested") in ("nested", "plain")


def test_files_exist_kinds_and_paths_are_safe_and_actions_are_in_the_closed_set():
    for fid, f in fragments().items():
        for spec in f.get("files") or []:
            assert (f["dir"] / spec["src"]).is_file(), (fid, spec["src"])
            assert spec["kind"] in FILE_KINDS
            for key in ("src", "dst"):
                v = spec[key]
                assert not v.startswith(("/", "\\")) and ".." not in Path(v).parts and ":" not in v[:3], (fid, v)
        if f.get("claude"):
            assert (f["dir"] / f["claude"]).is_file()
        assert set(f.get("actions") or []) <= ACTIONS, fid
        for t in f.get("seed_tasks") or []:
            assert t["title"].strip() and t["dod"].strip(), f"{fid}: a seed task needs a definition of done"


def test_placeholders_are_the_closed_set_and_no_machine_path_lives_in_the_data():
    for p in SRC.rglob("*"):
        if not p.is_file() or p.suffix not in (".md", ".yaml", ".gitignore"):
            continue
        text = p.read_text(encoding="utf-8")
        for key in PH.findall(text):
            assert key in PLACEHOLDERS, f"{p.relative_to(SRC)}: unknown placeholder {key}"
        for bad in ("/home/", "/Users/", "C:\\Users", "shumway"):
            assert bad not in text, f"{p.relative_to(SRC)} contains {bad}"


def test_acs_declares_exactly_the_three_servers_and_only_through_placeholders():
    acs = fragments()["acs"]
    assert sorted(acs["mcp"]) == ["corvin_orchestration", "forge", "skill_forge"]
    for name, spec in acs["mcp"].items():
        assert spec["command"] == "{{paths.python}}", name


def test_every_video_feature_enforces_both_languages_in_the_template_and_the_rules():
    vid = templates()["video-engineering"]
    assert vid["videos"]["languages"] == ["de", "en"]
    text = (SRC / "fragments" / "videos" / "files" / "claude.md").read_text(encoding="utf-8")
    assert "German and English" in text and "sources.md" in text
    sources = (SRC / "fragments" / "videos" / "files" / "TEMPLATE-sources.md").read_text(encoding="utf-8")
    for section in ("Videoeigenschaften", "Inhalt", "Reproduktion", "Konfiguration", "Pipeline",
                    "Quellen im Codebase", "Bekannte Einschränkungen", "Verwandte ADRs/Konzepte"):
        assert f"## {section}" in sources
    assert len(re.findall(r"^## ", sources, re.M)) == 8


def test_plugin_manifests_agree():
    import json
    pj = json.loads((SRC.parent / "plugin.json").read_text(encoding="utf-8"))
    py = yaml.safe_load((SRC.parent / "plugin.yaml").read_text(encoding="utf-8"))
    assert pj["id"] == "plugin:buildin-knowledge_management-project_templates"
    assert pj["version"] == py["version"] == "1.0.0"
    assert py["plugin_id"] == "project_templates"
    assert pj["category"] == "knowledge_management" and pj["tier"] == "buildin"
    assert py["network_egress"] == "none" and py["requires_consent"] is False
