# Extension Layers (Custom Layer System)

An **Extension Layer** bundles a system-prompt injection, skills, tools, and even a
full MCP server into a single installable unit that plugs into CorvinOS's layer stack
**without touching core files**. Core layers (`corvin.*`) are cryptographically
immovable; the extension surface (`<vendor>.<name>`) is freely open — this is the
**Custom Layer System (CLS, ADR-0156)** and the **Layer Extension API (ADR-0142)**.

## Tier model

| Tier | Capability | License gate |
|---|---|---|
| **A** | `system_prompt.md` injection + `skills/*.md` registration | Always free |
| **B** | `tools/*.py \| .sh` (Forge-side) | Counted against `active_custom_layers_bc` limit |
| **C** | `mcp_server.py` | Counted against `active_custom_layers_bc` limit |

Free-tier limit for Tier-B/C: **1** active layer. Any error reading the license is
treated as free tier (**fail-closed — never fail-open**).

## On-disk layout

```
<corvin_home>/tenants/<tid>/custom-layers/<vendor>.<name>/
    layer.corvin.yaml   (REQUIRED)
    system_prompt.md    (Tier A)
    skills/*.md         (Tier A)
    tools/*.py|.sh      (Tier B)
    mcp_server.py       (Tier C)

<corvin_home>/tenants/<tid>/global/custom_layers.json   (registry)
```

## How to build one

1. Create `layer.corvin.yaml` with your `<vendor>.<name>` identity and declared tier.
2. Add the tier's assets (`system_prompt.md` and/or `skills/`, `tools/`, `mcp_server.py`).
3. Install / enable / disable / remove through the registry
   (`custom_layer_registry.py` — M1). The namespace gate rejects any attempt to
   register under the reserved `corvin.*` core namespace.

## Security model

- **Deny-wins:** an extension layer can **never** override a core deny decision.
- Tier-B/C run through the **license gate** (`custom_layer_gate.py`, M2, fail-closed).
- The core `layer_integrity_hash` (ADR-0141) covers **only core files** — adding or
  removing extension layers never changes it, and never boot-fails the core.

## Canonical docs

- **[layer-cls.md — Custom Layer System (ADR-0156)](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/claude-ref/layer-cls.md)** — tiers, layout, license gate, loader
- **[layer-extension-api.md — Layer Extension API (ADR-0142)](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/claude-ref/layer-extension-api.md)** — the two-class core/extension model
- **[layer-integrity-protocol.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/claude-ref/layer-integrity-protocol.md)** — how core immovability is enforced

## Contributing to the marketplace

Add `extension-layers/<vendor>.<name>/` with the `layer.corvin.yaml`, its tier
assets, and a `README.md` (what it adds, which tier, any license requirement). See
[CONTRIBUTING.md](../CONTRIBUTING.md).
