---
id: harness_runner-ADR-0001
status: PROPOSED
depends_on: []
related: []
paths:
  - src/corvin_harness_runner/runner.py
  - src/corvin_harness_runner/__main__.py
docs:
  - README.md
---

# harness_runner-ADR-0001 - Single-turn runner on `call_claude_streaming`

## Context
Benchmark harnesses (Harbor: Terminal-Bench, DeepSWE) need a headless command that takes a task, runs it
once without questions and exits. CorvinOS has none. The runner must keep L34/L35/L44 and the audit chain.

## Decision
Drive `adapter.call_claude_streaming(prompt, channel, chat_key, mode, add_dir, ...)` from a plain process
inside a throwaway `CORVIN_HOME`/tenant. Gates are only observed (wrappers record and return the original
result). The endpoint becomes a provider in a throwaway registry and tenant config, so L35 judges its host.
The board's model id is a pin the runner answers itself (see consequences).

## Alternatives
* (a) `call_claude_streaming` - chosen: the real bridge path, gates and audit for free.
* (e) raw `ClaudeCodeEngine.spawn` - fewer prompt additions, but no L34/L35/L44, no audit: not CorvinOS.
* Gateway REST - needs a running service (other services, ports, auth); heavier, same code underneath.

## Consequences
* The worker gets the bridge persona prompt, always-on core skills and a `User input:` sentinel (disclosed).
* `model_selector.normalise_pin` is overridden in the runner process for the one board id (it would cut
  `org/`). A CorvinOS-side fix would remove this override.
* The L44 classifier is a second `claude -p` call to the same endpoint and model.
