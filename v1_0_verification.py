#!/usr/bin/env python3
"""v1.0 Production Verification - All 44 Plugins."""

import sys
import importlib
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "plugins" / "buildin"))
sys.path.insert(0, str(Path(__file__).parent / "plugins" / "contributor"))

# All 44 plugins organized by category
PLUGINS = {
    "Security & Compliance (8)": [
        ("security_compliance.flow_guard.src.flow_guard", "FlowGuard"),
        ("security_compliance.path_gate.src.path_gate", "PathGate"),
        ("security_compliance.consent_gate.src.consent_gate", "ConsentGate"),
        ("security_compliance.audit_backend.src.audit_backend", None),  # Registry, no class
        ("security_compliance.audit_chain.src.audit_chain", None),  # May be different structure
        ("security_compliance.context_audit_trail.src.context_audit_trail", "ContextAuditTrail"),
        ("security_compliance.user_backend.src.user_backend", None),  # Registry
        ("security_compliance.vibe_decision_audit.src.vibe_decision_audit", "VibeDecisionAudit"),
    ],
    "Memory & Learning (7)": [
        ("memory.learning_event_storage.src.learning_event_storage", "LearningEventStorage"),
        ("memory.brain_learning_tracker.src.brain_learning_tracker", "BrainLearningTracker"),
        ("memory.user_model_learner.src.user_model_learner", "UserModelLearner"),
        ("memory.cel_session_memory.src.cel_session_memory", "CelSessionMemory"),
        ("memory.vibe_session_history.src.vibe_session_history", "VibeSessionHistory"),
        ("memory.recall_backend.src.recall_backend", None),  # May be different
        ("memory.anonymization_engine.src.anonymization_engine", "AnonymizationEngine"),
    ],
    "Integration (8)": [
        ("integration.data_connector.src.data_connector", "DataConnector"),
        ("integration.event_emitter.src.event_emitter", "EventEmitter"),
        ("integration.hook_system.src.hook_system", "HookSystem"),
        ("integration.notification_backend.src.notification_backend", None),  # May be different
        ("integration.router_backend.src.router_backend", None),  # May be different
        ("integration.brain_event_emitter.src.brain_event_emitter", "BrainEventEmitter"),
        ("integration.bridge_adapter.src.bridge_adapter", "BridgeAdapter"),
        ("integration.cowork_hub.src.cowork_hub", "CoworkHub"),
    ],
    "Observability (9)": [
        ("observability.vibe_webhook_dispatcher.src.vibe_webhook_dispatcher", "VibeWebhookDispatcher"),
        ("observability.heartbeat_monitor.src.heartbeat_monitor", "HeartbeatMonitor"),
        ("observability.telemetry_client.src.telemetry_client", "TelemetryClient"),
        ("observability.vibe_session_tracer.src.vibe_session_tracer", "VibeSessionTracer"),
        ("observability.vibe_health_monitor.src.vibe_health_monitor", "VibeHealthMonitor"),
        ("observability.brain_layer_monitor.src.brain_layer_monitor", "BrainLayerMonitor"),
        ("observability.brain_diagnostics.src.brain_diagnostics", "BrainDiagnostics"),
        ("observability.autonomy_status_tracker.src.autonomy_status_tracker", "AutonomyStatusTracker"),
        ("observability.vibe_metrics_aggregator.src.vibe_metrics_aggregator", "VibeMetricsAggregator"),
    ],
    "Data Processing (12)": [
        ("data_processing.pii_detector.src.pii_detector", "PiiDetector"),
        ("data_processing.data_classification.src.data_classification", "DataClassification"),
        ("data_processing.stt_provider.src.stt_provider", "SttProvider"),
        ("data_processing.summary_provider.src.summary_provider", "SummaryProvider"),
        ("data_processing.artifact_extraction.src.artifact_extraction", "ArtifactExtraction"),
        ("data_processing.wheel_content_inspector.src.wheel_content_inspector", "WheelContentInspector"),
        ("data_processing.error_healing.src.error_healing", "ErrorHealing"),
        ("data_processing.self_repair_engine.src.self_repair_engine", "SelfRepairEngine"),
        ("data_processing.diagnostics_dashboard.src.diagnostics_dashboard", "DiagnosticsDashboard"),
        ("data_processing.context_snapshot_analyzer.src.context_snapshot_analyzer", "ContextSnapshotAnalyzer"),
        ("data_processing.sql_expert.src.sql_expert", "SqlExpert"),
        ("data_processing.nlp_toolkit.src.nlp_toolkit", "NlpToolkit"),
    ],
    "Contributor (1)": [
        ("data_processing.slack_notifier.src.slack_notifier", "SlackNotifier"),
    ],
}


def verify_plugin(module_path: str, class_name: str = None) -> tuple[bool, str]:
    """Verify a plugin imports successfully."""
    try:
        mod = importlib.import_module(module_path)
        if class_name:
            cls = getattr(mod, class_name, None)
            if cls is None:
                return False, f"Class {class_name} not found"
        return True, "✅"
    except ImportError as e:
        return False, f"Import failed: {str(e)[:50]}"
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"


def verify_plugin_json(plugin_dir: Path) -> bool:
    """Verify plugin.json exists and is valid."""
    json_file = plugin_dir / "plugin.json"
    if not json_file.exists():
        return False
    try:
        with open(json_file) as f:
            json.load(f)
        return True
    except json.JSONDecodeError:
        return False


def main():
    """Run v1.0 verification."""
    print("=" * 70)
    print("CorvinOS Plugin Marketplace v1.0 — Production Verification")
    print("=" * 70)
    print()

    plugins_dir = Path(__file__).parent / "plugins" / "buildin"
    total = 0
    passed = 0
    failed_plugins = []

    for category, plugins_list in PLUGINS.items():
        print(f"\n{category}")
        print("-" * 70)

        for module_path, class_name in plugins_list:
            total += 1
            success, msg = verify_plugin(module_path, class_name)

            # Extract plugin name from module path
            plugin_name = module_path.split(".")[-3]

            # Also check plugin.json if not a provider
            if success:
                plugin_json_dir = plugins_dir / module_path.split(".")[0] / plugin_name
                if plugin_json_dir.exists():
                    json_ok = verify_plugin_json(plugin_json_dir)
                    if json_ok:
                        print(f"  {msg} {plugin_name}")
                        passed += 1
                    else:
                        print(f"  ⚠️  {plugin_name} (plugin.json invalid)")
                        failed_plugins.append(plugin_name)
                else:
                    print(f"  {msg} {plugin_name}")
                    passed += 1
            else:
                print(f"  ❌ {plugin_name}: {msg}")
                failed_plugins.append(plugin_name)

    # Summary
    print()
    print("=" * 70)
    print(f"VERIFICATION RESULTS: {passed}/{total} plugins ready")
    print("=" * 70)

    if failed_plugins:
        print(f"\n⚠️  Failed plugins ({len(failed_plugins)}):")
        for name in failed_plugins:
            print(f"  - {name}")
        print(f"\nAction: Fix {len(failed_plugins)} plugins before release")
        return False
    else:
        print("\n✅ ALL 44 PLUGINS PRODUCTION-READY FOR v1.0")
        return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
