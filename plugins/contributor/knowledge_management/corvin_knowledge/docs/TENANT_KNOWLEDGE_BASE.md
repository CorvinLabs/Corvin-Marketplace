# Tenant knowledge base (since 1.1.0)

Every CorvinOS installation gets this plugin as a **standard plugin**
(`core/console/corvin_console/default_plugins.yaml` in CorvinOS): the first boot installs it
from the marketplace. Like every contributor plugin it is `origin: community`, so it needs
the operator's **consent** — boot never grants that. It stays installed and disabled, and the
task board says so ("The Knowledge Graph plugin is installed but not enabled …").

## What enabling does

1. The operator enables the plugin in the Marketplace (with consent).
2. On its next tick (≤ 2 s) the CorvinOS board projector (`corvin_console/kb_projection.py`)
   runs this plugin's `src/kb_init.py --target <CORVIN_HOME>/tenants/<tenant>/knowledge`
   as a subprocess. It creates a git repository from `src/kb_template/` plus the engine
   from `src/kb_engine/`, and commits it. The host audits `kb.tenant_created`
   (`console.action_performed`).
3. From then on that directory is the tenant's knowledge base. The projector heals, exports
   and projects it onto the board every 2 s, exactly like the maintainers' Corvin-Knowledge.
   The Knowledge Graph panel reads the same repository: `repo_path` empty means the KB bound
   to the board.

A KB the operator already points CorvinOS at (`CORVIN_KB_REPO`, or a sibling
`Corvin-Knowledge` checkout on the install's own home) takes precedence. The tenant KB is
created only when neither exists.

Disabling the plugin unbinds the KB (the board no longer follows it). Its files stay.

## Using it — the three gates

All commands run from the KB directory as `python3 scripts/kb.py …` (Windows: `python`):

```bash
kb.py new initiative --title "Onboarding"
kb.py new concept    --title "Sign-in flow"
kb.py new decision   --title "Sign in with OIDC" --link formalized_as=CONCEPT-0001
kb.py new epic       --title "Build OIDC sign-in" --initiative I-01 --link implements=ADR-0001
kb.py new task       --title "Callback route" --epic E-001 --dod "route answers 200"
kb.py check          # lists every gate that does not hold yet
```

| Gate | Holds when | `kb check` finding while it does not |
|---|---|---|
| Concept gate (G1/G2) | the decision links its concept, and the concept links back | `G1_no_concept`, `G2_no_backedge` |
| ADR gate | the epic `implements` a decision | (no `ready` badge: the epic implements nothing) |
| Implementation-plan gate (G3) | the epic shares a `paths:` entry with the decision; every task has a definition of done | `G3_*` |
| Review gate (G4) | a review of the decision and its epic closed with `kb.py review close` | `G4_*` |

When G1–G4 all hold, the decision is `implementation_ready` and its epic carries the **ready**
badge on the board. A card move on the board runs `kb.py task` (the state machine). Board
edits of title, status or parent are refused (`409 kb_owned`).

## The engine copy

`src/kb_engine/` is a byte-identical copy of `scripts/{kb,kb_lib,kb_model}.py` from
CorvinLabs/Corvin-Knowledge. `ENGINE.json` records the source commit and a sha256 per file.
`kb_init.py` refuses to install an engine that does not match its manifest, and
`tests/test_tenant_kb.py` fails on a hand edit. To update:

```bash
python3 scripts/vendor_kb_engine.py --source /path/to/Corvin-Knowledge   # refuses a dirty engine
```

On the next host boot the projector runs `kb_init.py` once and replaces the engine files of
every existing tenant KB that differ (`kb: engine <sha>` commit; entities are never touched).

## Platforms

`kb_init.py` and the engine are stdlib + PyYAML + `git`. Since Corvin-Knowledge 133f985 the
engine runs without `fcntl` (`msvcrt` lock, Windows process-liveness probe, no `pass_fds`).

| Platform | Status |
|---|---|
| Linux | verified, including a fresh-install E2E |
| Windows | the `msvcrt` lock path is executed by a test on Linux (fcntl blocked, msvcrt stand-in). The Windows-only liveness probe and a run on real Windows are not verified |
| macOS | POSIX path, the same as Linux. Not run on a Mac |

## Limits

* One projected tenant per host process: `CORVIN_KB_TENANT` (default `_default`), the same as
  for the maintainers' KB.
* A new KB has no remote. The panel's sync button needs a `remote_url` you set yourself.
