# Agentic Compute

**Agentic Compute** is the CorvinOS layer where the AI dispatches heavy, long-running,
*iterative* work — hyperparameter search, optimization loops, model training — as
managed jobs (budgeted, crash-recovering, audit-logged), instead of doing it inline in
a chat turn. It's exposed to the AI through the `mcp__forge__compute_run` /
`compute_status` / `compute_result` / `compute_abort` tools.

It has a **real, well-defined extension interface** with three plug points. This
folder is where the community shares those extensions.

> ⚠️ **Trust note — read first.** Compute **engines** and **strategies** run *inside
> the worker process*, **not** inside the bwrap sandbox — they are operator-curated
> code, equivalent in trust to the audit chain or path-gate hook. The marketplace
> *lists* them; the **operator reviews and installs** them (venv + entry-point +
> tenant config + worker restart). This is not a drop-in-and-run surface like skills
> or forge tools. Fabric **backend** plugins additionally pass a license + network +
> sandbox gate (see below).

---

## The three plug points

### 1. Compute Engine plugins — `ComputeEngine` protocol (ADR-0029)

The built-in engines (FlatEngine, PipelineEngine, HACEngine) implement the
`ComputeEngine` protocol. Any class that satisfies the same protocol registers as an
additional engine without touching Corvin core. The **unified plugin system** wraps
this into a two-protocol pattern: your class implements both `CorvinPlugin`
(lifecycle: `on_load` / `on_unload` / `health_check`) and `ComputeEngine`
(capability: `submit` / `status` / `result` / `gate_action` / `abort`). `on_load()`
self-registers with `corvin_compute.engine_registry`.

**Quickstart — three files, one PyPI package:**

```bash
cp core/compute/corvin_compute/engines/contrib_template.py mycompany_sa/sa_engine.py
```

```toml
# pyproject.toml
[project.entry-points."corvin.plugins"]
simulated-annealing = "mycompany_sa.sa_engine:SimulatedAnnealingPlugin"
```

```yaml
# tenant.corvin.yaml
spec:
  compute:
    engines_allowed: [flat, pipeline, hac, sa]
  plugins:
    installed:
      - id: simulated-annealing
```

### 2. Fabric backend + data-source plugins — `compute_plugin.yaml` (ADR-0026)

The **Compute Fabric** adds `ComputeBackend` plugins (`create_session` /
`train_epoch` / `finalize` — e.g. a PyTorch/XGBoost training backend) and
`DataSourceAdapter` plugins, installed via a `compute_plugin.yaml` manifest into the
plugin discovery roots (system / tenant / user). These are gated:

- `fabric_enabled: true` is the master switch (all Fabric MCP tools return
  `FabricNotEnabled` otherwise).
- `allow_network_plugins` / `allow_network` default **off** — a backend that wants
  network must be explicitly permitted by the operator.
- Tier-B/C plugins pass the **license gate** (fail-closed).
- Enable/disable emits `compute.backend_plugin_enabled` / `_disabled` audit events.

### 3. Custom optimisation strategies — `Strategy` protocol

A `Strategy` (`suggest_batch` / `update` / `should_stop`) plugs into the ADR-0013
iteration loop alongside the built-in `grid` / `random` / `bayesian`. Install the
module in the worker venv, add the name to `spec.compute.strategies_allowed`, restart
the worker. LLM-assisted strategies authenticate via the subscription-native
`claude -p` CLI and are gated by `disallow_llm_strategies`.

---

## Also useful

- **Any forge tool can be the objective function** — pass its name as `tool_name` to
  `compute_run`; it must return a scalar loss in stdout JSON. Annotate sensitive
  inputs with `x-sensitive: true` and cache keys with `x-cache-key: true`.
- **Large datasets:** register with `data_register`, pass the `data_handle` — the
  worker binds it read-only into each sandboxed call; the LLM never sees raw rows.

## Canonical docs

- **[compute.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/compute.md)** — Agentic Compute, the MCP API, the iteration loop, and the full "How companies can extend Compute" section (strategies, engines, backends, datasets)
- **[data-and-compute.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/data-and-compute.md)** — how compute binds registered datasets
- **ADRs** — 0013 (compute worker), 0026 (Compute Fabric plugins), 0029 (ComputeEngine protocol)

## Contributing to the marketplace

Add `agentic-compute/<your-plugin>/` with the plugin source, its
`pyproject.toml`/`compute_plugin.yaml`, and a `README.md` (which plug point, which
protocol, trust/gate requirements, how to enable). Because these run
operator-curated, be explicit about exactly what the code does. See
[CONTRIBUTING.md](../CONTRIBUTING.md).
