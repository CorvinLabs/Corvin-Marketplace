"""The plugin's manifest and provider are consistent and loadable (static wiring)."""
import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_and_yaml_agree():
    j = json.loads((ROOT / "plugin.json").read_text())
    y = yaml.safe_load((ROOT / "plugin.yaml").read_text())
    panel = j["entry_points"]["console_panels"][0]
    assert y["console_panel"]["route"] == panel["route"] == "agent-conversations"
    assert y["console_panel"]["component"] == panel["component"] == "AgentConversationsPage"
    assert j["version"] == y["version"]
    assert j["id"].endswith(y["plugin_id"])
    assert y["boot_layer"] == "installed"          # community origin may not claim a privileged layer
    assert y["network_egress"] == "none"           # all traffic goes through core federation


def test_docs_exist_and_concept_names_this_plugin():
    concept = ROOT / "docs" / "CONCEPT-0001-peer-chat-patterns-for-agent-conversations.md"
    assert "agent-conversations-CONCEPT-0001" in concept.read_text()


def test_provider_class_shape():
    spec = importlib.util.spec_from_file_location("ac_provider", ROOT / "provider.py")
    src = (ROOT / "provider.py").read_text()
    assert spec is not None and "class AgentConversationsProvider" in src
    for attr in ("plugin_id", "plugin_type", "version", "display_name", "on_load", "on_unload", "health_check"):
        assert attr in src
