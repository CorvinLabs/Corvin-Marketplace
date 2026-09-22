#!/usr/bin/env python3
"""
Generate README.md + SVG diagrams for all marketplace plugins.

Usage:
  python3 scripts/plugin_docs_generator.py --audit        # Report gaps
  python3 scripts/plugin_docs_generator.py --generate <name>  # Generate for one plugin

"""

import sys
import json
from pathlib import Path

MARKETPLACE_ROOT = Path(__file__).parent.parent
PLUGINS_DIR = MARKETPLACE_ROOT / "plugins" / "buildin"

PLUGIN_CATEGORIES = {
    "orchestration": "Workflow Automation",
    "data_processing": "Data Processing & Transformation",
    "integration": "Integrations & Connectors",
    "memory": "Memory & Context Management",
    "security_compliance": "Security & Compliance",
    "observability": "Monitoring & Observability",
    "visualization": "Data Visualization",
    "ai_models": "AI & LLM Integration",
}


class PluginDocsAudit:
    """Audit plugin documentation completeness."""

    def __init__(self):
        self.plugins = []
        self.missing_docs = []
        self.complete_docs = []

    def scan_plugin(self, plugin_dir: Path):
        """Scan a single plugin for documentation."""

        plugin_json_path = plugin_dir / "plugin.json"
        if not plugin_json_path.exists():
            return None

        try:
            with open(plugin_json_path) as f:
                plugin_config = json.load(f)
        except json.JSONDecodeError:
            print(f"  ❌ Invalid plugin.json: {plugin_dir}")
            return None

        plugin_info = {
            "path": str(plugin_dir),
            "name": plugin_config.get("name", plugin_dir.name),
            "category": plugin_config.get("category", "unknown"),
            "version": plugin_config.get("version", "unknown"),
            "has_readme": (plugin_dir / "README.md").exists(),
            "has_assets_dir": (plugin_dir / "docs" / "assets").exists(),
            "has_architecture_svg": (plugin_dir / "docs" / "assets" / "architecture.svg").exists(),
            "has_workflow_svg": (plugin_dir / "docs" / "assets" / "workflow-execution-flow.svg").exists(),
        }

        # Check README.md quality
        if plugin_info["has_readme"]:
            readme_path = plugin_dir / "README.md"
            with open(readme_path) as f:
                content = f.read()
            plugin_info["readme_word_count"] = len(content.split())
            plugin_info["readme_quality"] = self._assess_readme_quality(content)
        else:
            plugin_info["readme_word_count"] = 0
            plugin_info["readme_quality"] = "missing"

        # Track completeness
        is_complete = (
            plugin_info["has_readme"] and
            plugin_info["readme_word_count"] >= 1000 and
            plugin_info["has_architecture_svg"] and
            plugin_info["has_workflow_svg"]
        )

        if is_complete:
            self.complete_docs.append(plugin_info)
        else:
            self.missing_docs.append(plugin_info)

        self.plugins.append(plugin_info)
        return plugin_info

    def _assess_readme_quality(self, content: str) -> str:
        """Simple quality assessment based on content."""

        has_sections = (
            "##" in content and
            "API" in content and
            "Example" in content
        )

        if len(content.split()) < 500:
            return "too-short"
        elif len(content.split()) < 1000:
            return "incomplete"
        elif has_sections:
            return "good"
        else:
            return "needs-improvement"

    def audit(self):
        """Run audit on all plugins."""

        print("🔍 Scanning Marketplace plugins...")
        print()

        if not PLUGINS_DIR.exists():
            print(f"Error: {PLUGINS_DIR} not found")
            return

        # Iterate over categories
        for category_dir in sorted(PLUGINS_DIR.iterdir()):
            if not category_dir.is_dir():
                continue

            category_name = category_dir.name
            category_display = PLUGIN_CATEGORIES.get(category_name, category_name)
            print(f"📁 {category_display}")

            # Iterate over plugins in category
            for plugin_dir in sorted(category_dir.iterdir()):
                if not plugin_dir.is_dir():
                    continue

                self.scan_plugin(plugin_dir)

            print()

        # Report summary
        self._print_summary()

    def _print_summary(self):
        """Print audit summary."""

        print("=" * 80)
        print("DOCUMENTATION AUDIT SUMMARY")
        print("=" * 80)
        print()

        total = len(self.plugins)
        complete = len(self.complete_docs)
        missing = len(self.missing_docs)
        completion_rate = (complete / total * 100) if total > 0 else 0

        print(f"Total Plugins: {total}")
        print(f"Complete Documentation: {complete} ({completion_rate:.0f}%)")
        print(f"Incomplete Documentation: {missing}")
        print()

        if missing > 0:
            print("PLUGINS NEEDING DOCUMENTATION:")
            print()

            for plugin in sorted(self.missing_docs, key=lambda p: (p["category"], p["name"])):
                print(f"  • {plugin['name']} ({plugin['category']})")

                # List what's missing
                missing_items = []
                if not plugin["has_readme"]:
                    missing_items.append("README.md")
                elif plugin["readme_word_count"] < 1000:
                    missing_items.append(f"README.md (only {plugin['readme_word_count']} words, need ≥1000)")

                if not plugin["has_architecture_svg"]:
                    missing_items.append("docs/assets/architecture.svg")

                if not plugin["has_workflow_svg"]:
                    missing_items.append("docs/assets/workflow-execution-flow.svg")

                for item in missing_items:
                    print(f"      ├─ Missing: {item}")

                print()

        if complete > 0:
            print("PLUGINS WITH COMPLETE DOCUMENTATION:")
            print()

            for plugin in sorted(self.complete_docs, key=lambda p: (p["category"], p["name"])):
                print(f"  ✓ {plugin['name']} ({plugin['category']})")
                print(f"      ├─ README.md: {plugin['readme_word_count']} words")
                print(f"      ├─ architecture.svg: ✓")
                print(f"      └─ workflow-execution-flow.svg: ✓")
                print()

        print("=" * 80)
        print()

    def generate_template(self, plugin_name: str):
        """Generate documentation template for a plugin."""

        print(f"🔍 Searching for plugin: {plugin_name}")

        # Find plugin directory
        plugin_dir = None
        for category_dir in PLUGINS_DIR.iterdir():
            if not category_dir.is_dir():
                continue

            candidate = category_dir / plugin_name
            if candidate.exists() and candidate.is_dir():
                plugin_dir = candidate
                break

        if not plugin_dir:
            print(f"❌ Plugin not found: {plugin_name}")
            return

        # Load plugin.json
        plugin_json_path = plugin_dir / "plugin.json"
        try:
            with open(plugin_json_path) as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"❌ No valid plugin.json found in {plugin_dir}")
            return

        print(f"✓ Found plugin: {config.get('name', plugin_name)}")
        print()

        # Check what's missing
        readme_missing = not (plugin_dir / "README.md").exists()
        assets_missing = not (plugin_dir / "docs" / "assets").exists()

        if readme_missing:
            print(f"📝 Would generate README.md")
            print(f"   → {plugin_dir}/README.md")
        else:
            print(f"✓ README.md already exists")

        if assets_missing:
            print(f"📐 Would create docs/assets/ directory")
            print(f"   → {plugin_dir}/docs/assets/")
            print(f"   → {plugin_dir}/docs/assets/architecture.svg")
            print(f"   → {plugin_dir}/docs/assets/workflow-execution-flow.svg")
        else:
            arch_exists = (plugin_dir / "docs" / "assets" / "architecture.svg").exists()
            flow_exists = (plugin_dir / "docs" / "assets" / "workflow-execution-flow.svg").exists()

            if arch_exists:
                print(f"✓ architecture.svg already exists")
            else:
                print(f"📐 Would generate architecture.svg")

            if flow_exists:
                print(f"✓ workflow-execution-flow.svg already exists")
            else:
                print(f"📐 Would generate workflow-execution-flow.svg")

        print()
        print("To generate documentation, use:")
        print(f"  python3 scripts/plugin_docs_validator.py --generate-for {plugin_name}")
        print()


def main():
    """Main entry point."""

    if len(sys.argv) < 2:
        audit = PluginDocsAudit()
        audit.audit()
        return

    command = sys.argv[1]

    if command == "--audit":
        audit = PluginDocsAudit()
        audit.audit()

    elif command == "--generate" and len(sys.argv) > 2:
        plugin_name = sys.argv[2]
        audit = PluginDocsAudit()
        audit.generate_template(plugin_name)

    else:
        print("Usage:")
        print("  python3 scripts/plugin_docs_generator.py --audit")
        print("  python3 scripts/plugin_docs_generator.py --generate <plugin-name>")
        print()
        print("Commands:")
        print("  --audit          Report documentation gaps for all plugins")
        print("  --generate NAME  Generate template docs for a specific plugin")
        print()


if __name__ == "__main__":
    main()
