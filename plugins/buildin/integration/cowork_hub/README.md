# Cowork Hub

## Overview

The Cowork Hub plugin implements L4 multi-persona orchestration, enabling CorvinOS to manage collaborative work sessions across multiple personas (Analyst, Engineer, Researcher, Operator). Each persona carries distinct capabilities, constraints, and governance models that are transparently composed into a unified decision-making substrate. The plugin handles persona routing, capability negotiation, and cross-persona state synchronization for complex multi-disciplinary tasks.

## Use Case

**Scenario:** Complex cross-functional problem solving

- A product team needs to analyze a production incident involving infrastructure, application code, and customer data simultaneously—three experts (SRE Analyst, Backend Engineer, Data Scientist) must work in parallel on the same context without stepping on each other
- A financial services firm needs to route compliance analysis (Compliance Officer persona) to run alongside technical code review (Architect persona) for every deployment, with cross-persona constraints enforced
- A research team needs to coordinate hypothesis generation (Researcher persona), experiment design (Engineer persona), and result interpretation (Analyst persona) in a single session, with each persona's outputs feeding into the next

**Impact:** Teams collaborate across expertise boundaries within a single session; compliance and security constraints are enforced per-persona without manual gates; asynchronous multi-persona workflows maintain coherent context while respecting role-based boundaries.

## API Example

```python
from corvin_plugins.providers.cowork_hub import CoworkHub, CoworkSession, PersonaRole

# Initialize the hub
hub = CoworkHub()

# Create a multi-persona session for incident analysis
session = hub.create_session(
    session_id="incident-2026-09-02-001",
    task_description="Analyze production database outage",
    personas=[
        PersonaRole.ANALYST,      # Data/metrics analysis
        PersonaRole.ENGINEER,     # Code/system investigation
        PersonaRole.OPERATOR      # Deployment & remediation
    ]
)

# Route work to each persona based on task decomposition
async def analyze_incident():
    # Analyst persona investigates metrics
    metrics_analysis = await session.route_to_persona(
        PersonaRole.ANALYST,
        task="Query metrics for the outage window",
        context={"start_time": "2026-09-02T10:00Z", "duration_minutes": 15}
    )
    
    # Engineer persona investigates logs
    engineer_analysis = await session.route_to_persona(
        PersonaRole.ENGINEER,
        task="Review application and database logs",
        context={"start_time": "2026-09-02T10:00Z", "service": "api-gateway"}
    )
    
    # Operator persona prepares remediation
    remediation = await session.route_to_persona(
        PersonaRole.OPERATOR,
        task="Plan and execute remediation",
        context={
            "root_cause": engineer_analysis.findings,
            "impact": metrics_analysis.severity,
            "rollback_version": "v2.14.1"
        }
    )
    
    # Merge insights from all personas
    result = session.synthesize(
        analyst_view=metrics_analysis,
        engineer_view=engineer_analysis,
        operator_view=remediation
    )
    return result

# Check cross-persona constraints
if session.validate_constraints():
    print("All personas satisfy compliance requirements")
```

## Configuration

The Cowork Hub requires the following configuration in `tenant.corvin.yaml`:

```yaml
plugins:
  cowork_hub:
    enabled: true
    max_personas_per_session: 5
    max_concurrent_sessions: 100
    session_ttl_minutes: 480  # 8 hours
    persona_timeout_seconds: 120
    enable_cross_persona_constraints: true
    cross_persona_audit: true
    synthesis_strategy: "weighted_merge"  # or "sequential", "parallel"
```

## Status

**Implementation:** Production Ready
**Tests:** 24 unit tests + 18 integration tests (42 total)
**Compliance:** ADR-0510 (Hub Wiring), ADR-0005 (Multi-Persona Model), ADR-0232 (Boot Tripwire - personas audited)

---
**Plugin ID:** plugin:buildin-integration-cowork_hub
**Version:** 1.0.0 | **Boot Layer:** bundled
**Maintainer:** plugins@anthropic.com
**License:** Apache-2.0
