<div align="center">

# 🛒 Corvin Marketplace

**The community hub for extending [CorvinOS](https://github.com/CorvinLabs/CorvinOS).**

*CorvinOS is a platform, not a product — you extend it by dropping files into a
configuration tree. No forking, no patching core, no restart in most cases.*

</div>

---

## What this is

This repository is a **community marketplace**: a curated, browsable collection of
extensions the CorvinOS community builds and shares — personas, tools, skills,
extension layers, messaging bridges, and full workflow bundles.

Each top-level folder maps to one of the **eight extension surfaces** CorvinOS
officially supports. Every folder has its own `README.md` that explains, for that
surface: what it is, how to build one, the security/scope model, and where the
**canonical documentation** lives in the CorvinOS repo.

> ⚠️ **Community content.** Extensions here are contributed by the community and are
> **not** part of the CorvinOS core. Review anything you install. CorvinOS runs every
> extension inside its structural security boundaries (sandbox, path-gate, license
> gate, hash-chained audit log) — but trust is still yours to grant. See
> [CONTRIBUTING.md](CONTRIBUTING.md) for the review + signing model.

---

## The eight extension surfaces

| Folder | Surface | What it does | Hot-reload | Canonical docs |
|---|---|---|---|---|
| [`personas/`](personas/) | **Personas** | An AI identity: system prompt, tool set, engine choice, LDD preset | ✅ next message | [extending.md §1](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/extending.md) · [personas-and-routing.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/personas-and-routing.md) |
| [`forge-tools/`](forge-tools/) | **Forge Tools** | Sandboxed, bwrap-isolated, MCP-callable Python tools | ✅ MCP hot-register | [forge.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/forge.md) |
| [`skills/`](skills/) | **Skills** | Markdown instruction files injected into future turns; self-grading | ✅ per turn | [extending.md §3](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/extending.md) |
| [`extension-layers/`](extension-layers/) | **Extension Layers** | Custom Layers (CLS): prompt + skills + tools + MCP server as a unit | ✅ per turn (Tier A) | [layer-cls.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/claude-ref/layer-cls.md) · [layer-extension-api.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/claude-ref/layer-extension-api.md) |
| [`bridge-adapters/`](bridge-adapters/) | **Bridge Adapters** | New messaging channels (Matrix, Signal, Teams, custom) | 🔄 daemon restart | [extending.md §4](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/extending.md) |
| [`workflow-packages/`](workflow-packages/) | **Workflow Packages** | Signed `.corvin-pkg` bundles of personas + tools + skills | ➖ one-time install | [awpkg.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/awpkg.md) |
| [`agentic-compute/`](agentic-compute/) | **Agentic Compute** | Pluggable compute engines, Fabric backends, and optimisation strategies for dispatched iterative jobs | 🔄 operator-installed | [compute.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/compute.md) |
| [`plugins/`](plugins/) | **Plugins** | Code-shaped extensions with a lifecycle: routers, notification/recall/audit/user backends. Run **in-process** — read the folder README before installing | 🔄 declared in tenant config | [plugin-architecture.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/plugin-architecture.md) |

---

## Start here

- 📖 **The extensibility hub** — one page, all five core surfaces:
  [docs/extending.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/extending.md)
- 🧩 **The plugin system model** (grading, promotion, scope ladder):
  [docs/plugin-system.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/plugin-system.md)
- 🏛️ **Architecture & layer stack**:
  [docs/architecture.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/architecture.md)
  · [layer-summary.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/claude-ref/layer-summary.md)

## The core idea: drop-in, hot-reload, self-grading

1. **Drop a file** into the right place (a persona JSON, a skill Markdown, a tool JSON).
2. CorvinOS **reads it on the next message** — most surfaces need no restart.
3. Every extension event is written to the **hash-chained audit log** — nothing happens silently.
4. Skills and tools are **graded against real usage** and automatically **promoted**
   through a scope ladder (`task → session → project → user`) when they earn their keep.

## Contributing an extension

1. Fork this repo.
2. Add your extension to the matching folder, following that folder's `README.md` format.
3. Include a short `README.md` next to your extension: what it does, requirements, and any secrets/network it needs.
4. Open a Pull Request. See [CONTRIBUTING.md](CONTRIBUTING.md) for the format, review, and CLA details.

---

## Links

- **CorvinOS** — the platform: <https://github.com/CorvinLabs/CorvinOS>
- **Website** — <https://corvin-labs.com>
- **License** — [MIT](LICENSE)

<div align="center">
<sub>Built by the CorvinOS community · Extensions are community-maintained, not core.</sub>
</div>
