# Knowledge Graph — release notes

## 1.3.0 (2026-11-03) — the tenant knowledge base works on Windows and on multi-tenant installs

Until 1.2.0 a fresh Windows install never got its knowledge base, and no install with more than one
tenant ever loaded the plugin. Fixed:

* **CRLF checkout refused the engine.** Git for Windows (`core.autocrlf=true`) checks the vendored
  engine out with CRLF, its sha256 no longer matched `ENGINE.json`, and `kb_init.py` refused to install
  "a modified engine" — every tick, on every Windows install. `kb_init.py` now verifies the committed
  (LF) form, always installs LF bytes (byte-identical to the CorvinOS path-gate pin), writes the
  template LF, ships a `.gitattributes` (`eol=lf`) into every tenant KB, and normalises a CRLF engine
  in an existing KB without an empty commit. The plugin directory pins `eol=lf` for the engine too.
* **The engine corrupted `.git/index` on Windows.** `os.open()` is text mode on Windows: the index kb
  swaps in was written with `\n` → `\r\n` (the next write was refused as "unmerged paths") and the
  `index.lock` body never matched its own pattern, so the lock was never released. Every raw fd is now
  opened `O_BINARY`; audit lines are written LF; `kb/graph/*.jsonl` is UTF-8 + LF (non-ASCII titles).
  `ENGINE.json` records this as `local_patch` on top of Corvin-Knowledge `133f985` — Corvin-Knowledge
  must carry the same change before the next `vendor_kb_engine.py` run.
* **Refused a provider slot on multi-tenant installs.** As `plugin_type: context_retriever` the loader
  treated the plugin as a process-wide provider (CorvinOS ADR-0250) and refused it
  (`multi_tenant_provider_slot`) as soon as a second tenant directory existed. It takes no slot: it is
  now a `web_surface`, like CorvinTV.

CorvinOS side (same day): the standalone console host (every Windows install, `corvinos-serve`) now
starts the board projector at all; the KB binding, the Tasks board, the Knowledge Graph panel, Quality
Gates and the path-gate pin are per tenant; the ADR/Concept gate skills name the tenant's own `kb.py`.
`default_plugins.yaml` requires 1.3.0.

Version: `plugin.json`, `plugin.yaml`, `provider.py` and the four `index/plugins.json` blocks.

## 1.2.0 (2026-10-17)

First-party buildin plugin, installed and enabled at first boot without a consent step (ADR-2265).
