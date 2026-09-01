# Personas

A **persona** is a JSON file that defines how the AI behaves in a specific chat
context: its identity, its system-prompt additions, its tool access, its engine
choice, and its LDD preset. Drop a file in the right place and it is **live on the
next message** — no restart, no service interruption.

## How to build one

Minimal persona:

```json
{
  "name": "customer-support",
  "description": "First-line support agent for Acme Corp.",
  "append_system": "You are a customer support agent for Acme Corp. Always be polite. For billing/refunds/account-deletion, say 'I will connect you with our billing team' and stop.",
  "permission_mode": "bypassPermissions",
  "forge_enabled": false,
  "skill_forge_enabled": false,
  "memory_recall_enabled": true,
  "ldd_preset": "off"
}
```

Attach any MCP server to a persona without touching global config:

```json
{
  "name": "research",
  "mcp_servers": {
    "acme-kb": { "command": "python3", "args": ["/opt/acme/kb_server.py"] }
  }
}
```

## Where it goes

| Location | Scope | Survives `git pull` |
|---|---|---|
| `~/.corvin/cowork/personas/<name>.json` | Your deployment only (user override) | ✅ |
| `operator/cowork/personas/<name>.json` | Committed, all deployments | — |

User-override personas take priority over bundle personas with the same name.

## Using it

- Pin to the current chat: `/pin customer-support` · remove: `/unpin`
- Assign permanently via a chat profile's `persona` field in the bridge `settings.json`.
- First load emits a `persona.loaded` audit event (metadata only — no prompt content).

## Canonical docs

- **[extending.md §1 — Personas](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/extending.md)** — full field reference (all 17 fields)
- **[personas-and-routing.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/personas-and-routing.md)** — auto-routing, LDD presets, persona merge order

## Contributing to the marketplace

Add `personas/<your-persona>/` containing the `.json` and a short `README.md`
(what it does, which engine/tools it expects). See the repo
[CONTRIBUTING.md](../CONTRIBUTING.md).
