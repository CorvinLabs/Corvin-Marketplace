"""Project Templates - CorvinOS-loadable provider (first-party plugin).

Shape required by the CorvinOS loader: class attributes ``plugin_id``/``plugin_type``/``version``/
``display_name`` and the ``on_load``/``on_unload``/``health_check`` lifecycle.

``plugin_type`` is ``context_retriever`` only as a TAXONOMY label (the closest extension surface in
``KNOWN_PLUGIN_TYPES``); ``on_load`` takes NO provider slot and registers nothing. What this plugin
contributes is DATA under ``src/`` (fragments and templates) that the console's projects service
(``corvin_console.projects_service``) reads when the TENANT enabled the plugin. No template code is
ever executed: the engine's only active steps are a closed set of named actions it implements itself.
"""
from __future__ import annotations

from corvin_plugins.protocol import HealthStatus, PluginContext


class ProjectTemplatesProvider:
    plugin_id = "project_templates"
    plugin_type = "context_retriever"
    version = "1.0.0"
    display_name = "Project Templates"

    def __init__(self) -> None:
        self._ctx: PluginContext | None = None

    def on_load(self, ctx: PluginContext) -> None:
        self._ctx = ctx

    def on_unload(self) -> None:
        self._ctx = None

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=True, message="loaded")
