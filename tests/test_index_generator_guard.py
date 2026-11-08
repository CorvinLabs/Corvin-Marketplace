"""T-0367: the index generator never silently shrinks index/plugins.json.

Driven as a real subprocess against a throwaway marketplace root with the real schemas: a current index that lists
a plugin the tree no longer has must be refused (exit 3, file byte-identical), and --accept-removals is the only way
through.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "generate_index_v2.py"


def _plugin(root: Path, pid: str, category: str = "integration") -> dict:
    d = root / "plugins" / "buildin" / category / pid
    d.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": f"plugin:buildin-{category}-{pid}", "type": "plugin", "name": pid.title(), "version": "1.0.0",
        "author": "CorvinLabs", "license": "Apache-2.0",
        "license_url": "https://github.com/CorvinLabs/Corvin-Marketplace/blob/main/LICENSE", "tier": "buildin",
        "category": category, "description": "A fixture plugin used by the index generator guard test.", "readme_url": "https://example.invalid/README.md",
        "distribution": {"supports_source": True, "supports_wheel": False, "source_url": "https://example.invalid/src"},
        "dependencies": [], "requires_version": ">=1.0.0", "boot_layer": "installed", "sla_level": "buildin",
        "security_audit": {"audited": False}, "maintainer_url": "https://example.invalid", "tags": ["integration"],
    }
    (d / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (d / "plugin.yaml").write_text(f"plugin_id: {pid}\n", encoding="utf-8")
    return manifest


def _root(tmp: Path) -> Path:
    root = tmp / "mp"
    root.mkdir()
    for s in ("index-schema-v2.json", "plugin-schema.json"):
        shutil.copy(ROOT / s, root / s)
    return root


def _run(root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GEN), "--marketplace", str(root), *extra],
                          capture_output=True, text=True, cwd=str(root))


def test_a_run_that_would_drop_an_indexed_plugin_is_refused_and_writes_nothing(tmp_path):
    root = _root(tmp_path)
    _plugin(root, "alpha")
    _plugin(root, "beta")
    first = _run(root)
    assert first.returncode == 0, first.stderr
    out = root / "index" / "plugins.json"
    before = out.read_bytes()
    shutil.rmtree(root / "plugins" / "buildin" / "integration" / "beta")       # beta is gone from the tree
    second = _run(root)
    assert second.returncode == 3, (second.returncode, second.stderr)
    assert "would drop 1 entry" in second.stderr and "beta" in second.stderr
    assert out.read_bytes() == before, "the refused run changed the index"


def test_accept_removals_is_the_only_way_to_write_a_shrinking_index(tmp_path):
    root = _root(tmp_path)
    _plugin(root, "alpha")
    _plugin(root, "beta")
    assert _run(root).returncode == 0
    shutil.rmtree(root / "plugins" / "buildin" / "integration" / "beta")
    ok = _run(root, "--accept-removals")
    assert ok.returncode == 0, ok.stderr
    ids = [p["id"] for p in json.loads((root / "index" / "plugins.json").read_text())["plugins"]]
    assert ids == ["plugin:buildin-integration-alpha"]


def test_growing_the_index_needs_no_flag(tmp_path):
    root = _root(tmp_path)
    _plugin(root, "alpha")
    assert _run(root).returncode == 0
    _plugin(root, "gamma", "media")
    grow = _run(root)
    assert grow.returncode == 0, grow.stderr
    ids = {p["id"] for p in json.loads((root / "index" / "plugins.json").read_text())["plugins"]}
    assert "plugin:buildin-media-gamma" in ids


def test_the_default_marketplace_root_is_the_repository_not_a_path_that_no_longer_exists():
    """T-0367: the default used to be ./operator/marketplace, which does not exist any more."""
    import subprocess, sys
    here = Path(__file__).resolve().parent.parent
    out = subprocess.run([sys.executable, str(here / "generate_index_v2.py"), "--help"], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0
    assert "operator/marketplace" not in out.stdout
    assert "repository root" in out.stdout
