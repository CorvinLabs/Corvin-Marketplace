# Knowledge base

This tenant's knowledge base, created by the CorvinOS **Knowledge Graph** plugin. Every
entity is a Markdown file with frontmatter; its type is its directory. The CorvinOS task
board is a projection of `kb/initiatives`, `kb/epics` and `kb/tasks` and follows every
change within seconds.

Run every command as `python3 scripts/kb.py …` from this directory (on Windows: `python`).

| Create | Command |
|---|---|
| initiative | `kb.py new initiative --title "…"` |
| concept | `kb.py new concept --title "…"` |
| decision (ADR) | `kb.py new decision --title "…" --link formalized_as=CONCEPT-0001` |
| epic (implementation plan) | `kb.py new epic --title "…" --initiative I-01 --link implements=ADR-0001` |
| task | `kb.py new task --title "…" --epic E-001 --dod "…"` |

Task status changes only through `kb.py task <T-id> <to>` (or by moving the card on the
board, which runs the same state machine).

## The gates

A decision is `implementation_ready` — the epic shows a **ready** badge on the board — when:

* **G1 concept gate** — the decision links its concept (`formalized_as` / `inspired_by`),
* **G2** — the concept links back to the decision,
* **G3 implementation-plan gate** — an epic `implements` the decision, shares a `paths:`
  entry with it (edit `paths:` in both files' frontmatter and commit), and every task of
  that epic has a `definition_of_done` (`--dod`),
* **G4** — a review of the decision and its epic was closed with `kb.py review close`.

`kb.py check` lists every gate that does not hold yet (`G1_…`–`G4_…` warnings);
`kb.py show ADR-0001` shows `implementation_ready`.

The engine in `scripts/` is maintained by the plugin and refreshed when the plugin is
updated — edit your entities, not the engine.
