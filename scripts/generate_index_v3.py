#!/usr/bin/env python3
"""
Generate marketplace_index_v3.json from all artifact sources.

Sources:
  - Corvin-Marketplace/index/plugins.json (existing plugins)
  - Skill-Forge output (skills) — TBD
  - MCP registry (tools) — TBD
  - Connector registry (connectors) — TBD
  - Layer metadata (layers) — TBD

Aggregates all 5 types into a unified index with per-type schemas.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def load_plugins() -> Dict[str, Any]:
    """Load plugins from existing v2 index."""
    v2_path = Path(__file__).parent.parent / "index" / "plugins.json"

    if not v2_path.exists():
        print(f"Warning: {v2_path} not found, using empty list", file=sys.stderr)
        return {
            "count": 0,
            "schema_ref": "plugin-schema.json",
            "items": [],
        }

    with open(v2_path) as f:
        v2 = json.load(f)

    return {
        "count": len(v2.get("plugins", [])),
        "schema_ref": "plugin-schema.json",
        "items": v2.get("plugins", []),
    }


def load_skills() -> Dict[str, Any]:
    """Load skills (placeholder until Skill-Forge integration)."""
    # TODO: Fetch from Skill-Forge API or directory
    return {
        "count": 0,
        "schema_ref": "skill-schema.json",
        "items": [],
    }


def load_tools() -> Dict[str, Any]:
    """Load MCP tools (placeholder until MCP registry integration)."""
    # TODO: Fetch from MCP registry
    return {
        "count": 0,
        "schema_ref": "mcp-tools-schema.json",
        "items": [],
    }


def load_connectors() -> Dict[str, Any]:
    """Load connectors (placeholder until Connector system is ready)."""
    # TODO: Fetch from Connector registry
    return {
        "count": 0,
        "schema_ref": "connector-schema.json",
        "items": [],
    }


def load_layers() -> Dict[str, Any]:
    """Load layers (compliance-critical, builtin)."""
    # TODO: Fetch from layer metadata
    # For now, return empty
    return {
        "count": 0,
        "schema_ref": "layer-schema.json",
        "items": [],
    }


def generate_index_v3() -> Dict[str, Any]:
    """Generate marketplace_index_v3.json."""
    index = {
        "version": "3.0",
        "schema": "ADR-0678",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "artifacts": {
            "plugins": load_plugins(),
            "skills": load_skills(),
            "tools": load_tools(),
            "connectors": load_connectors(),
            "layers": load_layers(),
        }
    }

    return index


def main():
    """Generate and write index v3."""
    print("Generating marketplace_index_v3.json...")

    index = generate_index_v3()

    # Write to file
    output_path = Path(__file__).parent.parent / "index" / "marketplace_index_v3.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(index, f, indent=2)

    # Print summary
    total = sum(s["count"] for s in index["artifacts"].values())
    print(f"✅ Generated index_v3.json with {total} artifacts")
    print(f"  - Plugins: {index['artifacts']['plugins']['count']}")
    print(f"  - Skills: {index['artifacts']['skills']['count']}")
    print(f"  - Tools: {index['artifacts']['tools']['count']}")
    print(f"  - Connectors: {index['artifacts']['connectors']['count']}")
    print(f"  - Layers: {index['artifacts']['layers']['count']}")
    print(f"  Written to: {output_path}")


if __name__ == "__main__":
    main()
