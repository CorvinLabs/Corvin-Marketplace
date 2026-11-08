## Agentic compute (ACS, compute runs, workflows)

The MCP servers are in `.mcp.json` (machine-local, generated, git-ignored; approve them on the first `claude` start here). Needs a licence tier that allows forging and compute, and a running compute worker - the engine cannot verify either, so check the first run.

- `mcp__corvin_orchestration__acs_delegate`: open-ended manager/worker loop; use `dry_run: true` to validate. `workflow_run` / `workflow_resume` / `workflow_list_paused`: registered DAG workflows (they may spend LLM budget).
- `mcp__forge__compute_run` / `compute_submit` / `compute_status` / `compute_result` / `compute_abort`: sweeps (grid / random / bayesian), pipeline and HAC engines over an existing Forge tool. `data_register` / `data_snapshot` register local files.

Traps (each one fails silently as `best_loss: null`):
- The compute worker reads ONLY the user-scope tool registry. Always `forge_promote(name, to="user")` before `compute_run` / `compute_submit`.
- A persona may only forge tools named `assistant.<name>`.
- `param_grid` keys must be the tool's input fields; check `<run>/iterations/0001.json` first.
- Set `steering_gate: false` (pipeline) / `backprop_gate: false` (HAC) for unattended runs, or they wait for a human.
