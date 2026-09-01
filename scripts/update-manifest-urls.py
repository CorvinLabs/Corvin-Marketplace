#!/usr/bin/env python3
"""Update plugin manifest URLs to GitHub Releases."""

import json
from pathlib import Path

MARKETPLACE_ROOT = Path(__file__).parent.parent
PLUGINS_DIR = MARKETPLACE_ROOT / "plugins" / "buildin"

# GitHub Releases base URL
GITHUB_ORG = "CorvinLabs"
GITHUB_REPO = "Corvin-Marketplace"
RELEASE_TAG = "v1.0.0"  # Can be updated per release
BASE_RELEASE_URL = f"https://github.com/{GITHUB_ORG}/{GITHUB_REPO}/releases/download/{RELEASE_TAG}"


def update_plugin_manifest(plugin_dir: Path) -> bool:
    """Update a plugin manifest with GitHub Releases URL."""

    manifest_file = plugin_dir / "plugin.json"

    if not manifest_file.exists():
        return False

    with open(manifest_file, "r") as f:
        manifest = json.load(f)

    plugin_id = manifest.get("id", "")
    version = manifest.get("version", "1.0.0")

    # Extract wheel name from plugin_id
    # Format: plugin:tier-category-name
    parts = plugin_id.split("-", 2)
    if len(parts) >= 3:
        wheel_name = f"{'-'.join(parts[1:])}-{version}-py3-none-any.whl"
    else:
        # Fallback: use plugin name directly
        wheel_name = f"{plugin_dir.name}-{version}-py3-none-any.whl"

    wheel_url = f"{BASE_RELEASE_URL}/{wheel_name}"

    # Update distribution
    if "distribution" not in manifest:
        manifest["distribution"] = {}

    manifest["distribution"]["wheel_url"] = wheel_url
    manifest["distribution"]["supports_wheel"] = True

    # Update source URL (still points to CorvinOS for now)
    # In future, could point to marketplace source tree
    if "source_url" not in manifest["distribution"]:
        manifest["distribution"]["source_url"] = (
            f"https://github.com/{GITHUB_ORG}/Corvin-Marketplace/tree/main/"
            f"plugins/buildin/{plugin_dir.parent.name}/{plugin_dir.name}/src"
        )

    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2)

    return True


def main():
    print(f"🔄 Updating manifests with GitHub Releases URLs\n")
    print(f"   Release: {RELEASE_TAG}")
    print(f"   Base URL: {BASE_RELEASE_URL}\n")

    updated = 0
    for category_dir in sorted(PLUGINS_DIR.iterdir()):
        if not category_dir.is_dir():
            continue

        category = category_dir.name
        for plugin_dir in sorted(category_dir.iterdir()):
            if not plugin_dir.is_dir():
                continue

            plugin_id = plugin_dir.name
            if update_plugin_manifest(plugin_dir):
                updated += 1
                print(f"  ✅ {category}/{plugin_id}")

    print(f"\n✅ Updated {updated} manifests")
    print(f"\nPlugins now point to GitHub Releases for wheel downloads")


if __name__ == "__main__":
    main()
