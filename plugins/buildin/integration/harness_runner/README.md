# Harness Runner (`corvin_harness_runner`)

Headless, single-turn entry point for benchmark harnesses (Harbor adapter side). It drives exactly one
`adapter.call_claude_streaming` turn - the same code path as a bridge message - inside a throwaway
`CORVIN_HOME`, so L34 / L35 / L44 and the hash-chained audit log run for real. It observes the gates
(records, returns the result unchanged); it has no switch that disables any of them.

```
python -m corvin_harness_runner --instruction-file PATH|- --workdir DIR --out-dir DIR --model ID \
    [--effort low|medium|high|max] [--timeout-s N] [--max-output-tokens N] [--context-window N] \
    [--corvin-root PATH] [--version]
```

* `--instruction-file -` reads the task from stdin.
* Endpoint and key: environment only (`ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`), never argv.
  With a base URL the runner declares a provider `harness_meter` in a throwaway registry + tenant config;
  L35 then judges that host.
* `CLAUDE_CODE_MAX_CONTEXT_TOKENS` / `CLAUDE_CODE_MAX_OUTPUT_TOKENS` pass through unchanged to the worker.
* `--model` is a pin: it reaches the worker and the L44 classifier byte for byte (`org/model:provider` too).
* Find CorvinOS: `--corvin-root` / `CORVIN_ROOT` (source tree) or, without it, the installed wheel
  (`corvin_core._operator_bootstrap`).
* Exit codes: 0 completed, 2 refused (a real gate result, never retried), 3 engine error, 4 timeout, 64 usage.
* Output in `--out-dir`: `result.json`, `events.jsonl`, `audit.jsonl` (copy of the throwaway chain),
  `sessions/` (Claude Code JSONL).
* `CORVIN_HARNESS_KEEP_HOME=1` keeps the throwaway home (tests); default is to delete it.

Tests: `CORVIN_ROOT=<checkout> <checkout>/.venv/bin/python -m pytest tests -q`.
Design and alternatives: `docs/ADR-0001-single-turn-runner.md`.
