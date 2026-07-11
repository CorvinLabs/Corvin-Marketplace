# Contributing to the Corvin Marketplace

Thanks for extending CorvinOS! This repo is a **community marketplace** — a curated,
browsable collection of extensions organized by the six extension surfaces CorvinOS
supports. This guide covers how to submit one.

## Before you start

- Read the **[Extensibility Hub](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/extending.md)**
  and the folder `README.md` for the surface you're targeting
  ([personas](personas/), [forge-tools](forge-tools/), [skills](skills/),
  [extension-layers](extension-layers/), [bridge-adapters](bridge-adapters/),
  [workflow-packages](workflow-packages/)).
- Extensions here are **community-maintained and not part of CorvinOS core.**

## How to submit

1. **Fork** this repository.
2. **Add your extension** under the matching top-level folder, in its own subfolder:
   `<surface>/<your-extension-name>/`.
3. Include a **`README.md`** next to your extension with:
   - What it does, in one or two sentences.
   - Requirements: engine, minimum CorvinOS version, any MCP servers.
   - **Any secrets or network access it needs**, and why.
   - Setup / install steps.
4. Keep it **self-contained** — no hidden downloads, no obfuscated code.
5. Open a **Pull Request** describing the extension and how you tested it.

## Quality bar

| Surface | Must include |
|---|---|
| Personas | the `.json` + a README; no secrets baked into `append_system` |
| Forge Tools | the `.json`; declare `meta.secrets` + `meta.network` honestly |
| Skills | the `.md`; tight, instruction-shaped; passes the SkillForge linter (no injection patterns, no embedded secrets) |
| Extension Layers | `layer.corvin.yaml` + tier assets; declare the tier (A/B/C) |
| Bridge Adapters | `daemon.js` + `settings.example.json` + `install.sh` |
| Workflow Packages | `manifest.json` + source assets; ship the signed `.corvin-pkg` |

## Security & trust

CorvinOS runs every extension inside structural boundaries — the bwrap sandbox, the
fail-closed path-gate hook, the license gate for Tier-B/C layers, and the
hash-chained audit log. **But listing here is not an endorsement.** Reviewers and
users are expected to read the code. Specifically, we will reject PRs that:

- Embed secrets or credentials.
- Contain prompt-injection patterns or persona-boundary overrides.
- Request network or filesystem access without a clear, stated reason.
- Obfuscate their behavior.

## Licensing

- This repository is licensed under the **[MIT License](LICENSE)** — simple and permissive.
- By contributing, you agree your contribution is licensed under MIT and that you have
  the right to submit it.

> Note: the **CorvinOS core** project has its own license and Contributor License
> Agreement — see the [CorvinOS repo](https://github.com/CorvinLabs/CorvinOS). Those
> terms govern the platform; this marketplace of community extensions is MIT.

## Questions

Open an issue, or start a discussion on the
[CorvinOS repo](https://github.com/CorvinLabs/CorvinOS). Happy building! 🛠️
