#!/usr/bin/env python3
"""
Migrate buildin plugin sources from CorvinOS to Corvin-Marketplace.

Each plugin gets:
- src/{module_name}.py (copied from CorvinOS/core/plugins/corvin_plugins/providers/)
- setup.py (wheel build config)
- requirements.txt (dependencies)
- __init__.py (package marker)
"""

import json
import shutil
import sys
from pathlib import Path

# Marketplace root
MARKETPLACE_ROOT = Path(__file__).parent.parent
PLUGINS_DIR = MARKETPLACE_ROOT / "plugins" / "buildin"

# CorvinOS root (assume ../CorvinOS)
CORVINOS_ROOT = MARKETPLACE_ROOT.parent / "CorvinOS"
CORVINOS_PROVIDERS = CORVINOS_ROOT / "core" / "plugins" / "corvin_plugins" / "providers"

# Mapping: plugin_id → source_module_name
PLUGIN_SOURCE_MAP = {
    # Memory
    "recall_backend": "recall_backend.py",
    "cel_session_memory": "cel_session_memory.py",  # May not exist yet
    "learning_event_storage": "learning_event_storage.py",  # May not exist yet
    "user_model_learner": "user_model_learner.py",  # May not exist yet

    # Security & Compliance
    "audit_chain": "audit_backend.py",
    "user_backend": "user_backend.py",
    "path_gate": "path_gate.py",  # May not exist
    "consent_gate": "consent_gate.py",  # May not exist
    "flow_guard": "flow_guard.py",  # May not exist
    "pii_detector": "pii_detector.py",  # May not exist

    # Integration
    "notification_backend": "notification_backend.py",
    "cowork_hub": "cowork_hub.py",  # May not exist
    "bridge_router": "router_backend.py",  # May not exist
    "event_emitter": "event_emitter.py",  # May not exist
    "hook_system": "hook_system.py",  # May not exist

    # Data Processing
    "data_connector": "data_connector.py",
    "anonymization_engine": "anonymization_engine.py",  # May not exist
    "classification_engine": "classification_engine.py",  # May not exist
    "pii_redaction": "pii_redaction.py",  # May not exist
    "data_flow_guard": "data_flow_guard.py",  # May not exist
    "geolocation_tracker": "geolocation_tracker.py",  # May not exist
    "retention_manager": "retention_manager.py",  # May not exist

    # Observability
    "heartbeat_provider": "heartbeat_provider.py",  # May not exist
    "telemetry_collector": "telemetry_collector.py",  # May not exist
    "diagnostics_provider": "diagnostics_provider.py",  # May not exist
    "performance_monitor": "performance_monitor.py",  # May not exist
    "stt_provider": "stt_provider.py",
}


def migrate_plugin(plugin_id: str, source_file: str, category: str) -> bool:
    """Migrate a single plugin to Marketplace."""

    plugin_dir = PLUGINS_DIR / category / plugin_id
    src_dir = plugin_dir / "src"

    # Create directories
    src_dir.mkdir(parents=True, exist_ok=True)

    source_path = CORVINOS_PROVIDERS / source_file

    if not source_path.exists():
        print(f"  ⚠️  Source not found: {source_path}")
        return False

    # Copy source
    dest_module = src_dir / source_file
    shutil.copy2(source_path, dest_module)
    print(f"  ✅ Copied {source_file} → {dest_module.relative_to(MARKETPLACE_ROOT)}")

    # Create __init__.py (if doesn't exist)
    init_file = src_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text('"""Plugin module."""\n')

    # Create setup.py (if doesn't exist)
    setup_file = plugin_dir / "setup.py"
    if not setup_file.exists():
        setup_content = f'''"""Setup for {plugin_id} plugin."""

from setuptools import setup, find_packages

setup(
    name="{plugin_id}",
    version="1.0.0",
    description="CorvinOS buildin plugin",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={{"": "src"}},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Add dependencies here
    ],
)
'''
        setup_file.write_text(setup_content)
        print(f"  ✅ Created {setup_file.relative_to(MARKETPLACE_ROOT)}")

    # Create requirements.txt (if doesn't exist)
    req_file = plugin_dir / "requirements.txt"
    if not req_file.exists():
        req_file.write_text("# Dependencies for this plugin\n")
        print(f"  ✅ Created {req_file.relative_to(MARKETPLACE_ROOT)}")

    return True


def main():
    print("🔄 Migrating buildin plugin sources to Corvin-Marketplace...\n")

    # Map plugin_id to (source_file, category)
    plugins_by_category = {}

    # Scan plugin.json files to build the map
    for category_dir in PLUGINS_DIR.iterdir():
        if not category_dir.is_dir():
            continue

        category = category_dir.name
        for plugin_dir in category_dir.iterdir():
            if not plugin_dir.is_dir():
                continue

            plugin_id = plugin_dir.name
            manifest_file = plugin_dir / "plugin.json"

            if manifest_file.exists():
                with open(manifest_file) as f:
                    manifest = json.load(f)
                    # Store for later
                    plugins_by_category.setdefault(category, []).append({
                        "id": plugin_id,
                        "manifest": manifest,
                        "dir": plugin_dir
                    })

    # Migrate each plugin
    migrated = 0
    for category in sorted(plugins_by_category.keys()):
        print(f"📁 Category: {category}")
        for plugin_info in plugins_by_category[category]:
            plugin_id = plugin_info["id"]
            source_file = PLUGIN_SOURCE_MAP.get(plugin_id)

            if not source_file:
                # Try to guess from plugin_id
                source_file = f"{plugin_id.replace('-', '_')}.py"

            if migrate_plugin(plugin_id, source_file, category):
                migrated += 1
        print()

    print(f"\n✅ Migrated {migrated} plugins")
    print("\nNext steps:")
    print("  1. Build wheels: scripts/build-plugins.sh")
    print("  2. Create GitHub release and upload wheels")
    print("  3. Update manifest URLs to GitHub Releases")
    print("  4. Remove sources from CorvinOS")


if __name__ == "__main__":
    main()
