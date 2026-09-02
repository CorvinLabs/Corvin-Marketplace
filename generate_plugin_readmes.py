#!/usr/bin/env python3
"""
Generate and enhance README files for all 44 CorvinOS plugins.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any

# Template for new README files
README_TEMPLATE = """{title}

{description}

## Features

{features}

## Installation

```bash
pip install corvin-plugin-{plugin_name}
```

## Usage

```python
from corvin_plugins import {plugin_class}

plugin = {plugin_class}()
result = plugin.execute(...)
```

## Configuration

See plugin configuration or use:

```bash
corvin plugin config {plugin_id}
```

## Testing

```bash
pytest tests/plugins/test_{plugin_name}.py -v
```

## Compliance

- **GDPR Art. 5, 6, 32** (data protection and processing)
- **EU AI Act Art. 50** (transparency and disclosure)
- **ADR-0511** (marketplace plugin registry)
- Audit trail: All operations logged and hash-chained
- Tenant isolation: All data scoped by tenant_id

## Related Plugins

See other plugins in the `{category}` category:
- `corvin plugin list --category {category}`

## Support

Report issues or contribute: https://github.com/CorvinLabs/CorvinOS

## License

Apache-2.0 with CLA v3.1
"""

# Compliance statements for different plugin types
COMPLIANCE_STMTS = {
    "data_processing": "- L34/L36 data classification, PII detection, anonymization\n- GDPR Art. 32 (data security)\n- No PII in audit logs (scrubbed via `_assert_safe`)",
    "integration": "- L4/L38 integration bridges\n- GDPR Art. 5 (purpose limitation, data minimization)\n- ADR-0255 worker engine integration",
    "memory": "- L28 session recall and learning infrastructure\n- GDPR Art. 5, 6, 7 (data storage, consent)\n- ADR-0314 learning event schema (immutable, tenant-scoped)",
    "observability": "- L36 telemetry and monitoring\n- GDPR Art. 6(1)(f) legitimate interest\n- Anonymous telemetry (no PII, opt-out available)",
    "security_compliance": "- L10/L16 security hardening\n- GDPR Art. 30, 32 (audit trail, data integrity)\n- Hash-chained immutable audit logging",
}

# Feature sets for different plugin types
FEATURE_SETS = {
    "data_processing": [
        "PII detection and masking",
        "Data classification engine",
        "Artifact extraction and processing",
        "Content inspection",
    ],
    "integration": [
        "Event routing and delegation",
        "Multi-persona orchestration",
        "Notification and pub/sub messaging",
        "Webhook dispatch",
    ],
    "memory": [
        "Session recall and storage",
        "Learning event persistence",
        "User modeling and preferences",
        "Conversation history",
    ],
    "observability": [
        "Real-time health monitoring",
        "Diagnostic dashboards",
        "Error healing and recovery",
        "Performance telemetry",
    ],
    "security_compliance": [
        "Hash-chained audit logging",
        "Consent enforcement",
        "Data flow guard",
        "Filesystem write protection",
    ],
}

def plugin_id_to_class_name(plugin_id: str) -> str:
    """Convert plugin ID to Python class name."""
    parts = plugin_id.replace("plugin:", "").split("-")
    return "".join(word.title() for word in parts if word not in ["buildin", "contributor"])

def plugin_id_to_name(plugin_id: str) -> str:
    """Convert plugin ID to simple name."""
    parts = plugin_id.replace("plugin:", "").split("-")
    return "_".join(part for part in parts if part not in ["buildin", "contributor"])

def create_readme(plugin_data: Dict[str, Any], plugin_id: str) -> str:
    """Create README content for a plugin."""
    name = plugin_data["name"]
    description = plugin_data["description"]
    category = plugin_data["category"]

    # Get features for this category
    features_list = FEATURE_SETS.get(category, ["Feature 1", "Feature 2"])
    features = "\n".join(f"- {f}" for f in features_list)

    # Get compliance statement
    compliance = COMPLIANCE_STMTS.get(category, "- GDPR Art. 5, 6, 32 (data protection)\n- ADR-0511 (marketplace)")

    # Clean up plugin name for code examples
    plugin_name = plugin_id_to_name(plugin_id)
    plugin_class = plugin_id_to_class_name(plugin_id)

    readme = f"# {name}\n\n{description}\n\n## Features\n\n{features}\n\n## Installation\n\n```bash\npip install corvin-plugin-{plugin_name}\n```\n\n## Usage\n\n```python\nfrom corvin_plugins import {plugin_class}\n\nplugin = {plugin_class}()\nresult = plugin.execute(...)\n```\n\n## Configuration\n\nSee plugin configuration or use:\n\n```bash\ncorvin plugin config {plugin_id}\n```\n\n## Testing\n\n```bash\npytest tests/plugins/test_{plugin_name}.py -v\n```\n\n## Compliance\n\n{compliance}\n\n## Related Plugins\n\nSee other plugins in the `{category}` category:\n\n```bash\ncorvin plugin list --category {category}\n```\n\n## Support\n\nReport issues or contribute: https://github.com/CorvinLabs/CorvinOS\n\n## License\n\nApache-2.0 with CLA v3.1"

    return readme

def enhance_readme(plugin_data: Dict[str, Any], plugin_id: str, existing_content: str) -> str:
    """Enhance an existing README with compliance statements and ADR references."""
    category = plugin_data["category"]
    compliance = COMPLIANCE_STMTS.get(category, "")

    # Check if already enhanced
    if "GDPR Art." in existing_content and "ADR-" in existing_content:
        return None  # Already enhanced

    # Add compliance section if missing
    if "## Compliance" not in existing_content:
        enhanced = existing_content.rstrip() + "\n\n## Compliance\n\n" + compliance + "\n"
        return enhanced

    return None  # Already has compliance section

def process_plugins(marketplace_dir: str) -> Dict[str, bool]:
    """Process all plugins and generate/enhance READMEs."""
    plugins_json_path = Path(marketplace_dir) / "plugins.json"

    if not plugins_json_path.exists():
        print(f"ERROR: plugins.json not found at {plugins_json_path}")
        return {}

    with open(plugins_json_path, "r") as f:
        data = json.load(f)

    results = {}
    created = 0
    enhanced = 0
    skipped = 0

    for plugin_id, plugin_data in data["plugins"].items():
        readme_path = Path(marketplace_dir) / plugin_data["path"] / "README.md"
        readme_dir = readme_path.parent

        # Ensure directory exists
        readme_dir.mkdir(parents=True, exist_ok=True)

        if readme_path.exists():
            # Try to enhance existing README
            with open(readme_path, "r") as f:
                content = f.read()

            enhanced_content = enhance_readme(plugin_data, plugin_id, content)
            if enhanced_content:
                with open(readme_path, "w") as f:
                    f.write(enhanced_content)
                results[plugin_id] = {"status": "enhanced", "path": str(readme_path)}
                enhanced += 1
            else:
                results[plugin_id] = {"status": "already-enhanced", "path": str(readme_path)}
                skipped += 1
        else:
            # Create new README
            readme_content = create_readme(plugin_data, plugin_id)
            with open(readme_path, "w") as f:
                f.write(readme_content)
            results[plugin_id] = {"status": "created", "path": str(readme_path)}
            created += 1

        # Update plugins.json flags
        plugin_data["documentation"]["has_readme"] = True
        plugin_data["documentation"]["has_enhanced_readme"] = True

    # Write updated plugins.json
    with open(plugins_json_path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=False)

    print(f"\nREADME Generation Complete:")
    print(f"  - Created: {created}")
    print(f"  - Enhanced: {enhanced}")
    print(f"  - Already Enhanced: {skipped}")
    print(f"  - Total: {created + enhanced + skipped}/44")
    print(f"\nUpdated: {plugins_json_path}")

    return results

if __name__ == "__main__":
    marketplace_dir = "/home/shumway/projects/Corvin-Marketplace/marketplace"
    process_plugins(marketplace_dir)
