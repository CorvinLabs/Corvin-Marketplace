# Project Templates

First-party CorvinOS plugin (`buildin`, vetted, local-only, no network, no telemetry). It ships the **catalogue** the
console's *Projects* feature creates projects from: feature fragments and nine role templates (software, data science, marketing, product, sales, legal, video, research, knowledge). It is **pure data** -
nothing in it is executed; the CorvinOS host plans, previews and applies it (ADR-2315, CONCEPT-0126).

| Template | Default features |
|---|---|
| `video-engineering` | core, kb, tasks, graph, gates, claude, ldd, videos, video_producer, directory, dashboard (experiments and acs are offered) |
| `knowledge-only` | core, kb, graph |
| `research-compute` | core, kb, tasks, graph, gates, claude, ldd, experiments, acs, dashboard |

Fragments (`src/fragments/<id>/`): `core`, `kb`, `tasks`, `graph`, `gates`, `claude`, `ldd`, `videos`, `video_producer`,
`directory`, `dashboard`, `experiments`, `acs`. Dependencies and every file a fragment writes are listed in
[docs/CATALOGUE.md](docs/CATALOGUE.md).

The tenant must enable this plugin (a project can never enable a plugin). `kb` additionally needs the *Knowledge Graph*
plugin, `video_producer` the *Video Producer* plugin - the console shows what is missing before anything is written.

Tests: `python -m pytest plugins/buildin/knowledge_management/project_templates/tests` (needs PyYAML). The proof that real
projects come out of it is in CorvinOS: `tests/e2e/test_project_templates_catalogue_e2e.py`.
