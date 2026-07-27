# 🔌 Plugins

**Code-shaped extensions that register with the CorvinOS plugin registry.**

The other seven folders in this marketplace hold *file-shaped* extensions — you
drop a file into a configuration tree and it takes effect, often within a turn.
This folder is different. A plugin here is a **Python class with a lifecycle**:
it implements `CorvinPlugin` (`on_load` / `on_unload` / `health_check`), it
registers with a provider registry, it gets health-polled, and it runs
**in the same process as the CorvinOS core**.

That last point is why this folder has stricter rules than the others.

---

## ⚠️ Read this before installing anything here

**A plugin manifest is a declaration, not a sandbox.** A plugin's `plugin.yaml`
may say `network_egress: none` and `pii_risk: low`. Those fields inform review and
gate prompts — they are **not enforced by the interpreter**. Once loaded, a plugin
can call arbitrary Python in the process that holds the audit chain writer, the
consent gate, and your tenant keys.

CorvinOS's provenance model (ADR-0249) gives you **attribution, not containment**:

- `origin: community` — unreviewed. Under `plugin_trust_enforcement` it requires
  an explicit, per-plugin operator approval, recorded as an audit event.
- `origin: vetted` — signed with Ed25519 by a key **pinned to a maintainer trust
  anchor**. A valid signature from an unpinned key does *not* count: anyone can
  generate a keypair and self-sign, so "signed" alone is not a provenance claim.
- `origin: builtin` — ships in the CorvinOS wheel. Nothing here is builtin.

**Everything in this folder is `origin: community`.** A merged pull request means
the entry is *listed*, not *endorsed*. It passed a mechanical check; a human read
the diff for obvious problems. That is not a warranty. Review what you install.

---

## Installing

There is **no marketplace installer, and there will not be one.** CorvinOS does
not fetch and execute code from a network location — `corvin plugin install`
accepts a local path only and never resolves a name (ADR-0233, ADR-0248). The
manual step is not friction to be optimised away; it is where a human looks at the
code.

```bash
git clone https://github.com/CorvinLabs/Corvin-Marketplace
cd Corvin-Marketplace/plugins/<type>/<plugin-id>

# read the code — this is the step that matters

corvin plugin check .              # validates against the real registry rules
corvin plugin check . --no-import  # manifest only; does NOT execute plugin.py
```

Then declare it in your tenant config — the reviewable option:

```yaml
spec:
  plugins:
    installed:
      - id: com.example.my-router
        class_path: "your_package.plugin:YourPluginClass"
```

> Shipping a `corvin.plugins` entry point is **not sufficient on its own**:
> `spec.plugins.auto_discover_entry_points` defaults to `false`, and an
> unresolvable plugin is skipped at debug level with no visible error.

---

## Before you build one: check whether your type is ever called

**Six of the eleven plugin types register successfully and are never invoked.** A
plugin of one of those loads, registers, reports healthy, shows up in the Console
— and nothing calls it. No error, no log line.

```bash
corvin plugin types      # prints which types are live and which are dead
```

| Consumed | Never invoked |
|---|---|
| `router_backend`, `summary_provider`, `notification_backend`, `recall_backend`, `audit_backend` | `user_backend`, `stt_provider`, `data_connector`, `compute_engine`, `worker_engine`, `bridge_channel` |

`corvin plugin new` warns you before you write a line. This is not a defect in
your plugin, and no amount of debugging on your side will fix it.

---

## Building one

```bash
corvin plugin new router_backend com.example.my-router
```

That scaffolds `plugin.py` (from the shipped template for that type),
`plugin.yaml` with least-privileged defaults (`layer: installed`,
`origin: community`, `pii_risk: low`), a `pyproject.toml` with the entry point,
and a README stating the discovery step.

Each plugin type carries an invariant you must not break. The generated template
states yours in comments; the load-bearing ones:

| Type | Invariant |
|---|---|
| `router_backend` | `route()` must **not** raise — return `None` on no-match or error |
| `notification_backend` | Must not block >100 ms, and must carry **no** message content or PII |
| `recall_backend` | Must not store un-redacted text |
| `audit_backend` | **Additive only** — receives a copy *after* the core write commits; can never suppress, delay or rewrite the core chain |
| `user_backend` | Failure, timeout or rejection means **deny** — never fall back to guest |
| `stt_provider` | Audit metadata **only** — never the transcript text |

---

## Contributing

Submit a PR adding `plugins/<plugin_type>/<plugin-id>/` containing your
`plugin.py`, `plugin.yaml`, tests, and a README. Requirements:

1. `corvin plugin check` passes, and the CorvinOS version it passed against is
   recorded in your README (the protocol moves; a plugin validated against
   0.10.x may fail against 0.11.x).
2. `origin: community`. A PR cannot grant itself `vetted` — that requires
   maintainer review plus an Ed25519 signature over the artifact digest,
   performed out of band from the merge.
3. No network access at import time. Module-level code runs during
   `corvin plugin check` and at boot.

→ Canonical docs: [plugin-architecture.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/plugin-architecture.md)
· ADR-0244 (builder) · ADR-0245 (surface map) · ADR-0248 (distribution) ·
ADR-0249 (provenance)
