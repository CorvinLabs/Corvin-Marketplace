# Skills

**Skills** are Markdown documents injected into future conversation turns as
additional system-prompt context. Unlike forge tools (which *do* things), skills
*shape how the AI thinks and responds* — they encode workflows, checklists,
domain-specific reasoning patterns, or project conventions.

Skills are **self-improving**: the system grades each skill after every turn based on
whether the AI applied it, and automatically **promotes** skills that earn consistent
positive grades to wider scopes.

## How to build one

In chat:

> Create a skill `code-review-checklist` that always checks for missing error
> handling, hardcoded secrets, and missing tests. Save at session scope.

Or via MCP directly:

```
mcp__skill_forge__skill_create(
  name="code-review-checklist",
  body="When reviewing code, always check:\n1. Missing error handling\n2. ...",
  scope="session"
)
```

> SkillForge must be **explicitly opted in** on the persona: `"skill_forge_enabled": true`.

## The linter

Every skill passes a linter before it is saved. It **rejects**:

- Prompt-injection patterns (ignore-previous-instructions, roleplay-as-another-AI, reveal-system-prompt)
- Embedded secrets (API-key shapes, private-key PEM blocks)
- Persona-boundary phrases (anything that would override the persona definition)
- Oversized bodies (default 8 KB)

## Grading & promotion ladder

| Promotion | Requirement |
|---|---|
| task → session | ≥ 1 positive grade |
| session → project | ≥ 3 grades, mean ≥ 0.5 |
| project → user | explicit `force=True` |

Grades are automatic (mention/apply `0.7`, user-approval `0.9`, rejection `0.1`,
rephrase `0.3`) and can be set manually:
`mcp__skill_forge__skill_grade name=... score=0.9`.

Manage: `skill_list` · `skill_get` · `skill_diff` · `skill_purge`. All emit audit
events (name, scope, grade) — never the skill body.

## Canonical docs

- **[extending.md §3 — Skills](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/extending.md)**
- **[plugin-system.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/plugin-system.md)** — grading + promotion model in depth

## Contributing to the marketplace

Add `skills/<your-skill>.md` (the skill body) plus a short note in the PR describing
when it should fire. Keep bodies tight and instruction-shaped. See
[CONTRIBUTING.md](../CONTRIBUTING.md).
