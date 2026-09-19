"""Slack Notifier — CorvinOS-loadable provider (contributor plugin).

Shape required by the CorvinOS loader (``corvin_plugins.bootstrap._load_builtin_class``
+ ``registry.register``): class attributes ``plugin_id``/``plugin_type``/``version``/
``display_name`` and the ``on_load``/``on_unload``/``health_check`` lifecycle.
``plugin_type`` is the closest CorvinOS extension surface for this plugin's domain —
a TAXONOMY label; ``on_load`` deliberately takes NO provider slot. The plugin's own
implementation lives in ``src/``.
"""
from __future__ import annotations

from corvin_plugins.protocol import HealthStatus, PluginContext


class SlackNotifierPlugin:
    plugin_id = "slack_notifier"
    plugin_type = "notification_backend"
    version = "1.0.0"
    display_name = "Slack Notifier"

    def __init__(self) -> None:
        self._ctx: PluginContext | None = None

    def on_load(self, ctx: PluginContext) -> None:
        self._ctx = ctx

    def on_unload(self) -> None:
        self._ctx = None

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=True, message="loaded")
