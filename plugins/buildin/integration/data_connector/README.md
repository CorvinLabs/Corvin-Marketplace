# Data Connector

## Overview

The Data Connector plugin provides seamless integration with external data sources for artifact processing, classification, and enrichment. It abstracts connection management, query optimization, and data transformation logic into a unified interface compatible with CorvinOS's artifact pipeline (L25). The plugin handles data format conversion, schema validation, connection pooling, and type-safe query execution across SQL databases, NoSQL stores, and REST APIs.

## Use Case

**Scenario:** Enriching artifacts with external data

- A document processing workflow needs to fetch customer metadata from a PostgreSQL database to enrich extracted artifacts with business context before analysis
- An ML training pipeline needs to stream large datasets from S3 and Azure Blob Storage, dynamically sample them based on class distribution, and feed them into an annotation workflow
- A compliance audit system needs to cross-reference extracted PII against multiple external databases (employee records, vendor list, regulatory registry) to tag sensitive information before redaction

**Impact:** Artifact processing workflows integrate live data without custom glue code; external data sources are transparently accessed via a query interface; data transformations are reusable across multiple artifact processing tasks.

## API Example

```python
from corvin_plugins.providers.data_connector import DataConnector, QueryConfig, DataSource

# Initialize connector with multiple sources
connector = DataConnector(
    sources=[
        DataSource(
            name="customer_db",
            type="postgresql",
            connection_string="postgresql://user:pass@localhost/customers",
            pool_size=10
        ),
        DataSource(
            name="metadata_cache",
            type="redis",
            connection_string="redis://localhost:6379",
            ttl_seconds=3600
        )
    ]
)

# Query external data to enrich an artifact
artifact = {
    "extracted_customer_id": "cust-12345",
    "extracted_email": "john.doe@example.com",
    "extracted_amount": 1500.00
}

# Fetch customer metadata
customer_data = connector.query(
    source="customer_db",
    query_config=QueryConfig(
        sql="SELECT id, name, tier, created_at FROM customers WHERE id = %s",
        params=[artifact["extracted_customer_id"]],
        timeout_seconds=10
    )
)

# Validate against external list
email_check = connector.query(
    source="metadata_cache",
    query_config=QueryConfig(
        key=f"email:{artifact['extracted_email']}",
        operation="exists"
    )
)

# Enrich artifact with external data
enriched_artifact = {
    **artifact,
    "customer_tier": customer_data.rows[0]["tier"],
    "is_known_email": email_check.result,
    "enrichment_timestamp": connector.get_timestamp()
}

print(f"Enriched artifact: {enriched_artifact}")
```

## Configuration

The Data Connector requires the following configuration in `tenant.corvin.yaml`:

```yaml
plugins:
  data_connector:
    enabled: true
    sources:
      - name: customer_db
        type: postgresql
        connection_string: "postgresql://user:pass@db.example.com/customers"
        pool_size: 10
        ssl_mode: "require"
        timeout_seconds: 10
      - name: metadata_cache
        type: redis
        connection_string: "redis://cache.example.com:6379"
        db: 0
        ttl_seconds: 3600
    default_timeout: 10
    enable_query_logging: true
    enable_connection_pooling: true
```

## Status

**Implementation:** Production Ready
**Tests:** 22 unit tests + 16 integration tests (38 total)
**Compliance:** ADR-0297 (PII Detection), ADR-0034 (Data Flow), ADR-0205/0206/0208 (Geo-Tracking Tiers)

---
**Plugin ID:** plugin:buildin-integration-data_connector
**Version:** 1.0.0 | **Boot Layer:** bundled
**Maintainer:** plugins@anthropic.com
**License:** Apache-2.0
