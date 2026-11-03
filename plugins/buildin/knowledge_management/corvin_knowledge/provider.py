"""Corvin-Knowledge — CorvinOS-loadable provider (first-party buildin plugin).

Shape required by the CorvinOS loader (``corvin_plugins.bootstrap._load_builtin_class``
+ ``registry.register``): class attributes ``plugin_id``/``plugin_type``/``version``/
``display_name`` and the ``on_load``/``on_unload``/``health_check`` lifecycle.

``plugin_type`` is ``web_surface`` (since 1.3.0; before: ``context_retriever``). ``on_load``
takes NO provider slot, but ``context_retriever`` IS a process-wide provider-slot type
(CorvinOS ADR-0250): on every install with more than one tenant the loader refused this
plugin (``multi_tenant_provider_slot``) and it never loaded. What the plugin contributes to a running console is its panel
(``console_panel`` in plugin.yaml → "Knowledge Graph" under Marketplace, backed by
the console's ``/plugins/corvin-knowledge/*`` routes); the SDK and the ``mesh``
CLI live in ``src/``.
"""
from __future__ import annotations

from corvin_plugins.protocol import HealthStatus, PluginContext


class CorvinKnowledgeProvider:
    plugin_id = "corvin_knowledge"
    plugin_type = "web_surface"
    version = "1.3.0"
    display_name = "Knowledge Graph"

    def __init__(self) -> None:
        self._ctx: PluginContext | None = None

    def on_load(self, ctx: PluginContext) -> None:
        self._ctx = ctx

    def on_unload(self) -> None:
        self._ctx = None

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=True, message="loaded")
