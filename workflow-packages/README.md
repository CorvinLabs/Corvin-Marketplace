# Workflow Packages

A **workflow package** (`.corvin-pkg`) bundles personas, forge tools, skills, and
configuration into a single **signed** archive. It's the distribution unit for
CorvinOS extensions — share one package and the recipient gets a complete, coherent
capability without placing files by hand.

## Installing

```bash
corvin-pkg install <name>.corvin-pkg     # verify signature, extract, register
corvin-pkg inspect <name>.corvin-pkg     # preview contents before installing
```

The installer verifies the signature, extracts personas to
`~/.corvin/cowork/personas/`, registers forge tools + skills at their declared
scope, and emits a `corvin_pkg.installed` audit event. Package contents land in the
**user-override** locations — never committed to the repo, never overwritten by
`git pull`.

## Building & signing

A package is built from a `manifest.json`:

```json
{
  "name": "acme-support-workflow",
  "version": "1.0.0",
  "description": "Customer support: persona, ticket tool, escalation skill.",
  "publisher": "Acme Corp",
  "min_corvin_version": "0.9.0",
  "contents": {
    "personas": ["personas/customer-support.json"],
    "forge_tools": ["tools/fetch_ticket.json"],
    "skills": ["skills/escalation-checklist.md"]
  }
}
```

```bash
corvin-pkg build manifest.json --out acme-support-workflow.corvin-pkg
```

## Security

- **Unsigned packages are rejected.** Each trusted publisher's public key is pinned:
  `corvin-pkg trust add <publisher> <public-key.pem>`.
- A package whose `min_corvin_version` exceeds your installed version is rejected with an upgrade prompt.

## Canonical docs

- **[awpkg.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/awpkg.md)** — manifest format, signing, install flow
- **[extending.md §5 — Workflow Packages](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/extending.md)**

## Contributing to the marketplace

Add `workflow-packages/<name>/` with the `manifest.json`, the source assets, and a
`README.md` (what the bundle installs, publisher, min version). Ship the built
`.corvin-pkg` in the PR or a GitHub Release. See [CONTRIBUTING.md](../CONTRIBUTING.md).
