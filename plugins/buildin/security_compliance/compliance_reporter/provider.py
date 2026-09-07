"""Compliance Reporter — CorvinOS-loadable provider (compliance_reporter).

Shape required by the CorvinOS loader (``corvin_plugins.bootstrap._load_builtin_class``
+ ``registry.register``): class attributes ``plugin_id``/``plugin_type``/``version``/
``display_name`` and the ``on_load``/``on_unload``/``health_check`` lifecycle.
``plugin_type`` is the closest CorvinOS extension surface for this plugin's domain
(L16 AuditBackend: an observer of the committed audit stream); it is a TAXONOMY label here — ``on_load`` deliberately takes NO
provider slot (no ``set_active``), so loading this plugin never displaces the core
provider of that type. ``invoke`` is the ACP Skills capability entry point.
"""
from __future__ import annotations

from corvin_plugins.protocol import HealthStatus, PluginContext


class ComplianceReporterPlugin:
    """Infrastructure plugin — always active, not orchestrated by Skills."""

    plugin_id = "compliance_reporter"
    plugin_type = "audit_backend"
    version = "0.1.0"
    display_name = "Compliance Reporter"
    is_infrastructure = True

    def __init__(self) -> None:
        self._ctx: PluginContext | None = None

    def on_load(self, ctx: PluginContext) -> None:
        # Registers only; no provider slot is claimed (see module docstring).
        self._ctx = ctx

    def on_unload(self) -> None:
        self._ctx = None

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=True, message="loaded")

    def invoke(self, capability_id: str | None = None, input_data=None, **kwargs):
        """ACP capability entry point (see ``capabilities`` in plugin.yaml)."""
        return {"status": "ok"}


#: Backwards-compatible name used by the ACP orchestration loader.
Plugin = ComplianceReporterPlugin
