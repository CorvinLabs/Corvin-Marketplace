#!/usr/bin/env python3
"""Release lint for the Video Producer plugin (ADR-2247 ``doc_claims``, PLAN-0946 R5, T-0094).

Release documents misled three times (ADR-2247 "Measured state" C): the marketplace index said 1.0.0
while plugin.json said 1.1.0, and provider.py still said 1.0.0 inside the 1.2.0 release; a
RESULTS_PLACEHOLDER stood in the 1.3.0 notes; a release note named a test that does not exist
(``tests/test_api_routes.py::test_video_job_end_to_end``, removed in 301ba23). One check per class:

  version       plugin.json, plugin.yaml, provider.py and setup.py carry one version, and so do the
                plugin's four blocks of the marketplace index (plugins[], by_id, by_category, by_tier)
  placeholder   no placeholder token (PLACEHOLDER, *_PLACEHOLDER, TODO, TBD, FIXME, XXX, {{...}}) in
                the release notes and guides
  reference     every backticked test reference in those documents exists: ``tests/x.py::name`` (file
                and ``def``/``class`` name), ``test_x.py`` / ``tests/x.py`` (file) and a bare
                ``test_name`` (a test function or test file); and every backticked plugin-relative
                path (``src/``, ``scripts/``, ``tests/``, ``docs/``, ``panel/``) exists

Scope of the document checks: README.md, USER-GUIDE.md and, in RELEASE-NOTES.md, the "Unreleased"
sections and the section of the current version - an older section describes the tree of its own
release (a test deleted since was real then). Paths outside the plugin (a CorvinOS ``core/...`` path)
are not checked here. Limits quoted in a guide are not checked yet (ADR-2247 lists that as a fourth check).

Usage: release_lint.py [--plugin-dir DIR] [--index FILE] [--json]
Exit 0 = no finding, 1 = findings (printed one per line), 2 = the lint could not read its inputs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

HERE = Path(__file__).resolve().parents[1]
DOCS = ("README.md", "USER-GUIDE.md", "RELEASE-NOTES.md")
PLACEHOLDER = re.compile(r"\b(?:[A-Z][A-Z0-9]*_)*PLACEHOLDER(?:_[A-Z0-9]+)*\b|\bTODO\b|\bTBD\b|\bFIXME\b|\bXXX\b|\{\{[^}]*\}\}")
BACKTICK = re.compile(r"`([^`\n]+)`")
PATH_PREFIXES = ("src/", "scripts/", "tests/", "docs/", "panel/")
# A path of another repository is not this plugin's to check: a CorvinOS/marketplace root, or any
# reference the line introduces as "CorvinOS `...`" / "Corvin-Knowledge `...`".
EXTERNAL_PREFIXES = ("core/", "corvin_operator/", "corvin_console/", "web-next/", "Corvin-", "CorvinOS/", "plugins/", "~", "/")
EXTERNAL_INTRO = re.compile(r"(?:CorvinOS|Corvin-Knowledge|Corvin-Videos|Corvin-Website|marketplace)\s*\(?$", re.I)


def _finding(kind: str, where: str, what: str) -> Dict[str, str]:
    return {"check": kind, "where": where, "what": what}


# ── version ─────────────────────────────────────────────────────────────────────────────────────

def versions(plugin_dir: Path) -> Dict[str, Optional[str]]:
    def grab(path: Path, pattern: str) -> Optional[str]:
        if not path.is_file():
            return None
        m = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
        return m.group(1) if m else None
    return {
        "plugin.json": json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8")).get("version"),
        "plugin.yaml": grab(plugin_dir / "plugin.yaml", r"^version:\s*['\"]?([^'\"\s#]+)"),
        "provider.py": grab(plugin_dir / "provider.py", r"^\s+version\s*=\s*['\"]([^'\"]+)['\"]"),
        "setup.py": grab(plugin_dir / "setup.py", r"\bversion\s*=\s*['\"]([^'\"]+)['\"]"),
    }


def index_versions(index: Path, plugin_id: str) -> List[Tuple[str, Optional[str]]]:
    d = json.loads(index.read_text(encoding="utf-8"))
    out: List[Tuple[str, Optional[str]]] = []
    for i, e in enumerate(d.get("plugins") or []):
        if e.get("id") == plugin_id:
            out.append((f"index plugins[{i}]", e.get("version")))
    if plugin_id in (d.get("by_id") or {}):
        out.append(("index by_id", d["by_id"][plugin_id].get("version")))
    for group in ("by_category", "by_tier"):
        for key, entries in (d.get(group) or {}).items():
            for i, e in enumerate(entries or []):
                if isinstance(e, dict) and e.get("id") == plugin_id:
                    out.append((f"index {group}.{key}[{i}]", e.get("version")))
    return out


def check_versions(plugin_dir: Path, index: Optional[Path]) -> List[Dict[str, str]]:
    found = versions(plugin_dir)
    want = found["plugin.json"]
    out = [_finding("version", f, f"says {v!r}, plugin.json says {want!r}")
           for f, v in found.items() if f != "plugin.json" and v != want]
    if index is not None:
        plugin_id = json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))["id"]
        blocks = index_versions(index, plugin_id)
        if len(blocks) != 4:
            out.append(_finding("version", str(index.name), f"{len(blocks)} index blocks for {plugin_id}, expected 4"))
        out += [_finding("version", where, f"says {v!r}, plugin.json says {want!r}") for where, v in blocks if v != want]
    return out


# ── documents ───────────────────────────────────────────────────────────────────────────────────

def release_note_scope(text: str, version: Optional[str]) -> str:
    """The "Unreleased" sections and the current version's section of RELEASE-NOTES.md."""
    parts = re.split(r"(?m)^(?=## )", text)
    keep = [p for p in parts if p.startswith("## ") and (
        p.lower().startswith("## unreleased") or (version and re.match(rf"## (?:Version )?v?{re.escape(version)}\b", p)))]
    return "".join(keep)


def doc_texts(plugin_dir: Path, version: Optional[str]) -> Iterable[Tuple[str, str]]:
    for name in DOCS:
        p = plugin_dir / name
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        yield name, (release_note_scope(text, version) if name == "RELEASE-NOTES.md" else text)


def check_placeholders(name: str, text: str) -> List[Dict[str, str]]:
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in PLACEHOLDER.finditer(line):
            out.append(_finding("placeholder", f"{name} (line {n} of the checked text)", m.group(0)))
    return out


def _test_defs(tests_dir: Path) -> Dict[str, set]:
    """file (relative to the plugin) -> the def/class names in it."""
    out: Dict[str, set] = {}
    for f in tests_dir.rglob("*.py"):
        if "__pycache__" in f.parts or "fixtures" in f.relative_to(tests_dir).parts:
            continue
        src = f.read_text(encoding="utf-8", errors="replace")
        out[f.relative_to(tests_dir.parent).as_posix()] = set(re.findall(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)", src, re.M))
    return out


def check_references(plugin_dir: Path, name: str, text: str, defs: Dict[str, set]) -> List[Dict[str, str]]:
    out = []
    all_names = set().union(*defs.values()) if defs else set()
    stems = {Path(f).stem for f in defs}
    by_base: Dict[str, List[str]] = {}
    for f in defs:
        by_base.setdefault(Path(f).name, []).append(f)
    for m in BACKTICK.finditer(text):
        raw = m.group(1).strip()
        line_start = text.rfind("\n", 0, m.start()) + 1
        if EXTERNAL_INTRO.search(text[line_start:m.start()].rstrip()):
            continue
        for ref in re.split(r"[\s,]+", raw):
            ref = ref.strip("()[]{}.;:'\"")
            if not ref or ref.startswith(EXTERNAL_PREFIXES):
                continue
            if "::" in ref:
                file_part, *names = ref.split("::")
                files = [file_part] if file_part in defs else by_base.get(Path(file_part).name, [])
                if not (file_part.endswith(".py") and ("test" in file_part)):
                    continue
                if not files:
                    out.append(_finding("reference", name, f"`{ref}`: test file {file_part} does not exist"))
                    continue
                for nm in names:
                    nm = nm.split("[", 1)[0]
                    if not any(nm in defs[f] for f in files):
                        out.append(_finding("reference", name, f"`{ref}`: {nm} is not defined in {files[0]}"))
                continue
            if re.fullmatch(r"(?:tests/)?[\w/]*test_\w+\.py", ref):
                if ref not in defs and not by_base.get(Path(ref).name):
                    out.append(_finding("reference", name, f"`{ref}`: test file does not exist"))
                continue
            if re.fullmatch(r"test_\w+", ref):
                if ref not in all_names and ref not in stems:
                    out.append(_finding("reference", name, f"`{ref}`: no test of that name"))
                continue
            if ref.startswith(PATH_PREFIXES) and re.fullmatch(r"[\w./\-*]+", ref) and "*" not in ref and "<" not in ref:
                if not (plugin_dir / ref.rstrip("/")).exists():
                    out.append(_finding("reference", name, f"`{ref}`: path does not exist in the plugin"))
    return out


def lint(plugin_dir: Path, index: Optional[Path]) -> List[Dict[str, str]]:
    findings = check_versions(plugin_dir, index)
    version = versions(plugin_dir)["plugin.json"]
    defs = _test_defs(plugin_dir / "tests") if (plugin_dir / "tests").is_dir() else {}
    for name, text in doc_texts(plugin_dir, version):
        findings += check_placeholders(name, text)
        findings += check_references(plugin_dir, name, text, defs)
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plugin-dir", type=Path, default=HERE)
    ap.add_argument("--index", type=Path, default=None,
                    help="marketplace index (default: <repo>/index/plugins.json when the plugin is in the repo)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    index = a.index
    if index is None:
        guess = a.plugin_dir.resolve().parents[3] / "index" / "plugins.json" if len(a.plugin_dir.resolve().parents) > 3 else None
        index = guess if guess is not None and guess.is_file() else None
    try:
        findings = lint(a.plugin_dir, index)
    except (OSError, ValueError, KeyError) as e:
        print(f"release_lint: cannot read inputs: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({"findings": findings, "index": str(index) if index else None}, indent=1))
    else:
        for f in findings:
            print(f"{f['check']}: {f['where']}: {f['what']}")
        print(f"release_lint: {len(findings)} finding(s) in {a.plugin_dir.name}"
              f" (index: {index if index else 'not checked'})")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
