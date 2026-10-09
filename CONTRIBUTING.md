# Contributing to Corvin Marketplace

Thank you for contributing to the Corvin Marketplace! This guide explains how to add extensions.

## Getting Started

1. **Fork** this repository
2. **Create a branch** for your contribution: `git checkout -b add/my-plugin`
3. **Add your extension** to the appropriate folder
4. **Test** that it works with CorvinOS
5. **Open a Pull Request** with a clear description

## Adding a Plugin

Plugins go in either:
- **`buildin/`** — core, CorvinLabs-maintained plugins (request access)
- **`contributor/`** — community-contributed plugins

### Plugin Structure

```
contributor/my-plugin/
├── plugin.json          # Required: metadata
├── README.md            # Required: usage guide
├── src/                 # Optional: implementation
│   └── my_plugin.py
└── tests/               # Optional: tests
    └── test_my_plugin.py
```

### plugin.json Format

```json
{
  "id": "com.company.my-plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "category": "Integration",
  "description": "What this plugin does",
  "author": "Your Name",
  "repository_url": "https://github.com/...",
  "tier": "contributor",
  "boot_layer": "installed",
  "rating_average": 0,
  "install_count": 0,
  "dependencies": [],
  "tags": ["tag1", "tag2"]
}
```

### README.md Format

Include:
- Overview (1 paragraph)
- Features (bulleted list)
- Installation steps
- Configuration
- Usage examples
- Security/permissions required
- Support link

## Releasing an Update

Users who installed your plugin get an "update available" badge (Marketplace → Installed) as
soon as the marketplace source carries a **higher `version`** than the one they installed.

1. Bump `version` (semver) in **both** `plugin.yaml` and `plugin.json`; the index
   (`scripts/generate_index_v3.py`) is regenerated from them.
2. Keep `settings_schema` keys stable. A key you remove is dropped from the user's settings
   (they are told which); a new key gets its `default`.
3. If the new version raises `pii_risk`, `network_egress`, adds `egress_hosts` or newly
   requires consent, the user must explicitly approve the update. Say why in your changelog.
4. A version that is not strictly newer is never offered, and a version that fails to load
   is rolled back automatically.

## Review Process

1. **Automated checks:** CI validates plugin.json and README
2. **Code review:** Team reviews for security, quality
3. **Testing:** Plugin tested with CorvinOS
4. **Approval:** PR approved by maintainer
5. **Merge:** Plugin goes live on next release

## Code of Conduct

- Be respectful
- No spam or malicious code
- Follow CorvinOS security guidelines
- Include security disclosures responsibly

## License

All contributions to Corvin Marketplace are licensed under Apache-2.0.
