# Catalogue reference

A **fragment** is `src/fragments/<id>/fragment.yaml` plus files under `files/`. A **template** is
`src/templates/<id>.yaml`. The engine is `core/projects/fragments.py` in CorvinOS (docs: `docs/claude-ref/projects.md`).

## Fragment keys

| Key | Meaning |
|---|---|
| `requires` | hard, transitive, acyclic - switching on pulls these in (with the user's consent) |
| `suggests` | a hint only |
| `requires_plugins` | tenant plugins (registry ids) that must be enabled; a project never enables one |
| `files` | `{src, dst, kind}`; `seed` is written once and never overwritten, `generated` is the engine's, `local` is machine-local (mode 0600, git-ignored) |
| `claude` | a section of the generated `CLAUDE.md`, written while the `claude` feature is on; the user's own block is never overwritten |
| `gitignore` | lines for the managed `.gitignore` block |
| `mcp` | MCP servers for `.mcp.json` / `.corvin/local/mcp.json` (machine-local) |
| `kb`, `seed_tasks` | initiative/epic of the project and the tasks seeded into epic `E-001` (only with `kb` on) |
| `actions` | from a CLOSED set the host implements: `git_init`, `git_commit`, `kb_scaffold`, `kb_seed` |

Placeholders (closed set): `{{project.id}}`, `{{project.title}}`, `{{project.tenant}}`, `{{paths.python}}`, `{{paths.repo}}`,
`{{paths.corvin_home}}`, `{{paths.docs}}`, `{{paths.kb_engine}}`, `{{paths.pathsep}}`. An unknown one is an error.

## Fragments

| Fragment | Requires | Needs plugin | Writes |
|---|---|---|---|
| `core` | - | - | `README.md` (seed), rules section, `git init` |
| `kb` | core | corvin_knowledge | `docs/` scaffold (`kb_init --no-engine`), initiative + epic + 1 task, rules section |
| `tasks` | kb | - | nothing (a scope of the console Tasks board) |
| `graph` | kb | - | nothing (a scope of the Knowledge Graph panel) |
| `gates` | kb | - | rules section (display and guidance; the engine enforces its rules always) |
| `claude` | core | - | enables the generated `CLAUDE.md` |
| `ldd` | claude | - | rules section |
| `videos` | core | - | `videos/INDEX.md`, `videos/TEMPLATE-sources.md` (seed), 2 tasks, rules section |
| `video_producer` | videos | video_producer | rules section, 1 task |
| `directory` | core | - | rules section; manifest `directory.peers: []` |
| `dashboard` | core | - | nothing (a console page) |
| `experiments` | kb | - | `docs/data/experiments/README.md`, `docs/data/scratch/.gitignore` (seed), rules section |
| `acs` | claude | - | `.mcp.json` + `.corvin/local/mcp.json` (machine-local), `.corvin/forge/README.md`, rules section with the known traps |

## Rules for changing this catalogue

- A new file or fragment: add its row above in the same commit; keep every default and offered set requires-closed.
- Never put an absolute path, a user name or a secret into a template file (a test greps for them).
- A change to a fragment shifts what Repair writes into existing projects - bump the template `version` when the effect is visible.

## Role templates (1.1.0)

Each template names a `role` (closed list: software, data_science, marketing, product, sales, legal, video, research, knowledge),
a default data `classification` (public, internal, confidential, secret) and `assistant_access` (read, write), and an `outcome` in
plain words. The host (CorvinOS, ADR-2319) enforces the class through its data-flow gate; the template only proposes defaults.
Role fragments (`software`, `datasci`, `marketing`, `product`, `sales`, `legal`) are seed files plus a Claude Code rules section.

1.1.1: no template pins `videos.root` any more - the host chooses the shared `../Corvin-Videos` only for a project that lies
directly in the projects folder and `videos/` inside the project otherwise (a pinned `../Corvin-Videos` broke New video in
the managed workspace, CorvinOS REVIEW-0068 #1). `research-compute` is titled "Research and experiments": a project named
after its template must not carry a word the assistant's path gate protects (`compute`), which the managed workspace refuses
as an id (REVIEW-0068 #6).
