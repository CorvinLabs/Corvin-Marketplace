"""Video Producer — CorvinOS-loadable provider (contributor plugin).

Shape required by the CorvinOS loader (``corvin_plugins.bootstrap._load_builtin_class``
+ ``registry.register``): class attributes ``plugin_id``/``plugin_type``/``version``/
``display_name`` and the ``on_load``/``on_unload``/``health_check`` lifecycle.

``plugin_type`` is ``web_surface``: what this plugin contributes to a running
CorvinOS is a console panel (``console_panel`` in plugin.yaml → the sidebar
entry "Video Producer" appears on enable and leaves on uninstall); the
production pipeline itself lives in ``src/`` and is driven through the console's
video routes. ``on_load`` deliberately takes NO provider slot.
"""
from __future__ import annotations

from corvin_plugins.protocol import HealthStatus, PluginContext


class VideoProducerPlugin:
    plugin_id = "video_producer"
    plugin_type = "web_surface"
    version = "1.0.0"
    display_name = "Video Producer"

    def __init__(self) -> None:
        self._ctx: PluginContext | None = None

    def on_load(self, ctx: PluginContext) -> None:
        self._ctx = ctx

    def on_unload(self) -> None:
        self._ctx = None

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=True, message="loaded")
