## Knowledge base (docs/)

`docs/` is this project's knowledge base: every entity is a Markdown file whose TYPE is its directory.
The commands, with the engine path of this machine, are in `.corvin/local/kb-commands.md` (generated, git-ignored).
The path gate runs `kb.py` only from the engine of the tenant's bound knowledge base, always with `--repo <project>/docs`.

- Find before you write: `kb find <words>`; amend an existing entity instead of duplicating it.
- Create only with `kb new <type> --title ...` (it numbers, links and commits); never hand-number or hand-create an entity file.
- Task status changes only through `kb task <id> <to>`; `done` needs a definition of done.
- `kb check` must report `blocking: 0` before you push.
- Ids are local to this knowledge base: qualify cross-base references (`repo:<project>/docs/...`).
- Decisions about CorvinOS itself (core, layers, plugins) belong in Corvin-Knowledge, never here.
