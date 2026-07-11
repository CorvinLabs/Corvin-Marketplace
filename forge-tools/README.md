# Forge Tools

**Forge tools** are schema-bound, sandboxed tools the AI can create at runtime and
call as MCP tools. They persist across sessions and can do anything a subprocess can
— file I/O, HTTP calls, running scripts — **within the sandbox policy**. No changes
to CorvinOS core required. Once registered, a tool is callable as
`mcp__forge__<name>` in the same session (MCP hot-register).

## How to build one

The easiest path is to ask in chat:

> Create a forge tool called `fetch_weather` that takes a city and returns the
> current weather via the Open-Meteo API (no key needed). Store at project scope.

Or write the JSON yourself:

```json
{
  "name": "fetch_weather",
  "description": "Fetch current weather for a city using the Open-Meteo API.",
  "input_schema": {
    "type": "object",
    "properties": { "city": { "type": "string", "description": "City name, e.g. Berlin" } },
    "required": ["city"]
  },
  "implementation": { "type": "python", "code": "import urllib.request, json\n..." },
  "meta": { "scope": "project", "secrets": [], "network": "allow" }
}
```

Register it: `mcp__forge__artifact_register path=<tool-file.json>`

## Scopes & promotion

| Scope | Lifetime |
|---|---|
| `task` | Current turn |
| `session` | Until `/new` or `/clear` |
| `project` | Permanent, all sessions in the project |
| `user` | Permanent, all projects |

Promote: `mcp__forge__forge_promote name=fetch_weather target_scope=user`

## Sandbox & security

- Runs in a `bwrap` sandbox: **no network** (unless `meta.network: "allow"` **and** the persona permits it), fresh `/tmp`, read-only `/usr` + `/etc`.
- **No access** to `~/.corvin/`, audit chains, or policy files — enforced by the path-gate hook.
- **Secrets** are injected from the vault at runtime (`meta.secrets: ["MY_API_KEY"]` + `/vault set MY_API_KEY ...`) — the value never appears in the tool definition, AI context, or any log.
- Every create / promote / invoke writes an audit event (name, scope, persona) — never code or output.

## Canonical docs

- **[forge.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/forge.md)** — full schema, policy fields, sandbox options
- **[extending.md §2 — Forge Tools](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/extending.md)**

## Contributing to the marketplace

Add `forge-tools/<your-tool>/` with the `.json` and a `README.md` (what it does,
required secrets, whether it needs network). See [CONTRIBUTING.md](../CONTRIBUTING.md).
