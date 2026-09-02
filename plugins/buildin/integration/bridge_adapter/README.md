# Bridge Adapter

## Overview

The Bridge Adapter plugin implements the L38 message bridge protocol for cross-system communication and remote task envelope handling. This plugin enables bidirectional message routing between CorvinOS instances and external applications via standardized protocol bindings. It provides connection pooling, message serialization, and protocol version negotiation for robust inter-system interoperability.

## Use Case

**Scenario:** Integrating CorvinOS with external enterprise systems

- An enterprise legacy system needs to submit tasks to CorvinOS and receive structured results via HTTP/gRPC without rebuilding the entire integration layer
- Multiple CorvinOS deployments across regions need to coordinate work items using a unified bridge protocol with automatic failover
- A third-party SaaS application wants to invoke CorvinOS workflows while maintaining protocol compatibility across major version upgrades

**Impact:** Enterprise organizations can integrate CorvinOS into heterogeneous system landscapes without custom protocol development; regional deployments gain cross-zone coordination; external systems interact with CorvinOS using a documented, versioned protocol contract.

## API Example

```python
from corvin_plugins.providers.bridge_adapter import BridgeAdapter, BridgeConfig

# Initialize the bridge with remote endpoint
adapter = BridgeAdapter(
    config=BridgeConfig(
        protocol_version="1.0",
        remote_endpoint="https://api.remote-system.com",
        timeout_seconds=30,
        max_retries=3
    )
)

# Send a task envelope to remote system
task_envelope = {
    "task_id": "task-12345",
    "source_app": "corvin-console",
    "target_app": "external-processor",
    "payload": {
        "instruction": "analyze_data",
        "data": {"dataset_id": "ds-789"}
    }
}

result = adapter.send_envelope(task_envelope)
print(f"Result status: {result.status}")
print(f"Output: {result.payload}")

# Receive and process incoming task envelopes
async def handle_incoming():
    async for envelope in adapter.receive_stream():
        response = {"processed": True, "task_id": envelope["task_id"]}
        await adapter.acknowledge(envelope["task_id"], response)
```

## Configuration

The Bridge Adapter requires the following configuration in `tenant.corvin.yaml`:

```yaml
plugins:
  bridge_adapter:
    enabled: true
    protocol_version: "1.0"
    remote_endpoint: "https://api.remote-system.com"
    connection_pool_size: 10
    message_encoding: "json"  # or "msgpack"
    timeout_seconds: 30
    max_retries: 3
    tls_verify: true
    ca_bundle_path: "/etc/ssl/certs/ca-bundle.crt"
```

## Status

**Implementation:** Production Ready
**Tests:** 18 unit tests + 12 integration tests (30 total)
**Compliance:** ADR-0510 (Hub Wiring), ADR-0511 (Marketplace), ADR-0538 (A2A Protocol v6), RFC 3630 (Message Envelope Protocol)

---
**Plugin ID:** plugin:buildin-integration-bridge_adapter
**Version:** 1.0.0 | **Boot Layer:** bundled
**Maintainer:** plugins@anthropic.com
**License:** Apache-2.0
