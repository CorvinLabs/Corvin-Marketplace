#!/usr/bin/env python3
"""
Generate master plugin index (marketplace registry) from all plugin manifests.
Output: marketplace/plugins.json with complete metadata for all 42 plugins.
"""
import json
from pathlib import Path
from datetime import datetime

def generate_plugin_index():
    """Generate centralized plugin registry."""
    plugins_dir = Path("plugins")
    registry = {
        "version": "1.0.0",
        "generated": datetime.now().isoformat(),
        "plugins": {}
    }
    
    # Scan all plugin manifests
    for manifest_path in sorted(plugins_dir.rglob("plugin.json")):
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            
            # Extract metadata
            plugin_id = manifest.get("id") or manifest.get("name")
            plugin_dir = manifest_path.parent
            category = plugin_dir.parent.name  # e.g., "data_processing"
            tier = manifest.get("tier", "buildin")
            
            # Count tests
            test_count = len(list(plugin_dir.glob("tests/test_*.py"))) + len(list(plugin_dir.glob("tests/*_test.py")))
            e2e_count = len(list(plugin_dir.glob("tests/e2e_*.py")))
            
            # Check for README
            has_readme = (plugin_dir / "README.md").exists()
            has_enhanced_readme = (plugin_dir / "README_ENHANCED.md").exists()
            
            # Build entry
            entry = {
                "id": plugin_id,
                "name": manifest.get("name", plugin_id),
                "version": manifest.get("version", "1.0.0"),
                "category": category,
                "tier": tier,
                "description": manifest.get("description", "")[:100],
                "author": manifest.get("author", "CorvinOS Core"),
                "rating": manifest.get("rating", 4.5),
                "status": "production-ready" if has_readme and test_count > 0 else "development",
                "tests": {
                    "unit": test_count,
                    "e2e": e2e_count,
                    "total": test_count + e2e_count
                },
                "documentation": {
                    "has_readme": has_readme,
                    "has_enhanced_readme": has_enhanced_readme,
                    "path": f"plugins/{category.replace('_', '-')}/{plugin_id.replace('_', '-')}/README.md"
                },
                "path": str(plugin_dir.relative_to(".")),
                "boot_layer": manifest.get("boot_layer", "bundled")
            }
            
            registry["plugins"][plugin_id] = entry
        
        except Exception as e:
            print(f"Warning: Failed to parse {manifest_path}: {e}")
    
    # Add summary
    registry["summary"] = {
        "total_plugins": len(registry["plugins"]),
        "by_tier": {
            "buildin": sum(1 for p in registry["plugins"].values() if p["tier"] == "buildin"),
            "contributor": sum(1 for p in registry["plugins"].values() if p["tier"] == "contributor"),
        },
        "by_category": {},
        "tests": {
            "total_unit": sum(p["tests"]["unit"] for p in registry["plugins"].values()),
            "total_e2e": sum(p["tests"]["e2e"] for p in registry["plugins"].values()),
        },
        "documentation": {
            "with_readme": sum(1 for p in registry["plugins"].values() if p["documentation"]["has_readme"]),
            "with_enhanced": sum(1 for p in registry["plugins"].values() if p["documentation"]["has_enhanced_readme"]),
        }
    }
    
    # Category breakdown
    for plugin in registry["plugins"].values():
        cat = plugin["category"]
        registry["summary"]["by_category"][cat] = registry["summary"]["by_category"].get(cat, 0) + 1
    
    return registry

if __name__ == "__main__":
    registry = generate_plugin_index()
    
    # Write to marketplace/plugins.json
    output_path = Path("marketplace") / "plugins.json"
    output_path.parent.mkdir(exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(registry, f, indent=2)
    
    print(f"✅ Plugin index generated: {output_path}")
    print(f"\n📊 Summary:")
    print(f"   Total Plugins: {registry['summary']['total_plugins']}")
    print(f"   Buildin: {registry['summary']['by_tier']['buildin']}")
    print(f"   Contributor: {registry['summary']['by_tier']['contributor']}")
    print(f"   Total Tests: {registry['summary']['tests']['total_unit'] + registry['summary']['tests']['total_e2e']}")
    print(f"   With Docs: {registry['summary']['documentation']['with_readme']}")
    
    # Print category breakdown
    print(f"\n📁 By Category:")
    for cat, count in sorted(registry['summary']['by_category'].items()):
        print(f"   {cat}: {count}")

