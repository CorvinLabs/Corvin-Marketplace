"""Agent Conversations — CorvinOS-loadable provider (contributor plugin).

Same shape as ``corvin_knowledge``: class attributes plus the ``on_load``/``on_unload``/
``health_check`` lifecycle. ``plugin_type`` is a TAXONOMY label (``on_load`` takes no provider
slot). What the plugin contributes to a running console is its panel (``console_panel`` in
plugin.yaml → "Agent conversations" under Marketplace), which talks to the console's
``/v1/console/federation/conversations*`` routes; the moderator itself is core
(``core/federation/conversation.py``, ADR-2234) — this plugin owns the UI and its docs.
"""
from __future__ import annotations

from corvin_plugins.protocol import HealthStatus, PluginContext


class AgentConversationsProvider:
    plugin_id = "agent_conversations"
    plugin_type = "context_retriever"
    version = "1.0.0"
    display_name = "Agent Conversations"

    def __init__(self) -> None:
        self._ctx: PluginContext | None = None

    def on_load(self, ctx: PluginContext) -> None:
        self._ctx = ctx

    def on_unload(self) -> None:
        self._ctx = None

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=True, message="loaded")
