# auditx-connector (Python)

Python implementation of AuditX connector with canonical audit envelope and pluggable publishers.

Supports:
- ASYNC_DB publisher (`PostgresAuditPublisher`)
- Kafka publisher (`KafkaAuditPublisher`)
- Java API publisher (`JavaApiAuditPublisher`) for remote publish to Spring Boot AuditX endpoint

## Install

```bash
pip install auditx-connector
```

Core package does not force DB/Kafka drivers. Consumers install only needed drivers.

PostgreSQL publisher supports both drivers:
- `psycopg` (v3, preferred)
- `psycopg2` / `psycopg2-binary` (fallback)

Optional extras:

```bash
pip install "auditx-connector[postgres]"
pip install "auditx-connector[kafka]"
pip install "auditx-connector[all]"
```

Publisher modes (`PublisherType`):
- `ASYNC_DB`
- `KAFKA`
- `JAVA_API`

## Consumer Configuration

Consumers set config in code while constructing publisher instances.

### Common connector flags

```python
from auditx_connector import AuditConnectorConfig

connector_config = AuditConnectorConfig(
    enabled=True,
    enforce_idempotency=True,
    raise_on_dedup=False,  # True => raise when DB insert is skipped by ON CONFLICT
    verbose_logging=True,  # True => print execution logs per publish
)
```

### ASYNC_DB (`PostgresConfig`)

```python
from auditx_connector import PostgresConfig

# Option 1: DSN
pg_config = PostgresConfig(
    dsn="postgresql://audit_user:audit_pass@localhost:5432/auditdb",
    table="AUDITX_EVENT",
)

# Option 2: host/port/database/username/password
pg_config = PostgresConfig(
    host="localhost",
    port=5432,
    database="auditdb",
    username="audit_user",
    password="audit_pass",
    table="AUDITX_EVENT",
)
```

### KAFKA (`KafkaConfig`)

```python
from auditx_connector import KafkaConfig, KafkaMessageKeyType

kafka_config = KafkaConfig(
    bootstrap_servers="localhost:9092",
    topic="auditx.events",
    message_key_type=KafkaMessageKeyType.IDEMPOTENCY_KEY,
)
```

### JAVA_API (`JavaApiConfig`)

```python
from auditx_connector import JavaApiConfig

java_api_config = JavaApiConfig(
    base_url="http://localhost:8080",
    publish_path="/auditx/v1/events/publish",
    timeout_seconds=10.0,
    verbose_logging=True,
)
```

### Optional env-based loading in consumer app

The connector does not auto-read env vars; consumer app can map env vars to config objects:

```python
import os
from auditx_connector import AuditConnectorConfig, PostgresConfig

connector_config = AuditConnectorConfig(
    enabled=os.getenv("AUDITX_ENABLED", "true").lower() == "true",
    enforce_idempotency=os.getenv("AUDITX_ENFORCE_IDEMPOTENCY", "true").lower() == "true",
    raise_on_dedup=os.getenv("AUDITX_RAISE_ON_DEDUP", "false").lower() == "true",
    verbose_logging=os.getenv("AUDITX_VERBOSE_LOGGING", "false").lower() == "true",
)

pg_config = PostgresConfig(
    host=os.getenv("AUDITX_DB_HOST"),
    port=int(os.getenv("AUDITX_DB_PORT", "5432")),
    database=os.getenv("AUDITX_DB_NAME"),
    username=os.getenv("AUDITX_DB_USER"),
    password=os.getenv("AUDITX_DB_PASSWORD"),
    table=os.getenv("AUDITX_DB_TABLE", "AUDITX_EVENT"),
)
```

## Quick Start

### 1. Publish via `AuditWriteRequest`

```python
from auditx_connector import (
    AuditConnectorConfig,
    AuditService,
    AuditWriteRequest,
    AuditSource,
    DefaultIdempotencyKeyFactory,
    PostgresAuditPublisher,
    PostgresConfig,
)

publisher = PostgresAuditPublisher(
    postgres_config=PostgresConfig(
        dsn="postgresql://user:pass@localhost:5432/auditdb",
        table="AUDITX_EVENT",
    ),
    connector_config=AuditConnectorConfig(
        enabled=True,
        enforce_idempotency=True,
        raise_on_dedup=False,  # set True to raise when ON CONFLICT skips insert
        verbose_logging=True,  # prints runtime publish logs to console
    ),
    idempotency_key_factory=DefaultIdempotencyKeyFactory(),
)

service = AuditService(publisher)

service.publish(
    AuditWriteRequest(
        event_type="DISCONNECT_REQUEST_RECEIVED",
        source=AuditSource.CRON,
        conversation_id="550e8400-e29b-41d4-a716-446655440000",
        group_id="grp-1001",
        interaction_id="int-2001",
        extra_map={"zapperCustId": "ZP-10091", "plan": "PREMIUM"},
    )
)
```

You can also connect without DSN:

```python
postgres_config=PostgresConfig(
    host="localhost",
    port=5432,
    database="auditdb",
    username="audit_user",
    password="audit_pass",
    table="AUDITX_EVENT",
)
```

### 2. Publish via `CanonicalAuditEnvelope`

```python
from auditx_connector import CanonicalAuditEnvelope, AuditSource, AuditSeverity

envelope = CanonicalAuditEnvelope(
    event_type="DISCONNECT_API_TRIGGERED",
    source=AuditSource.API,
    severity=AuditSeverity.INFO,
    service_name="zapper-disconnect-service",
    environment="prod",
    conversation_id="550e8400-e29b-41d4-a716-446655440000",
    group_id="grp-1001",
    interaction_id="int-2001",
    trace_id="trace-9f8d2",
    business_keys={"zapperCustId": "ZP-10091"},
    extra_map={"decision": "AUTO_DISCONNECT_ELIGIBLE"},
)

service.publish_envelope(envelope)
```

### 3. Publish from Python to Java AuditX API (`JAVA_API`)

Java endpoint used: `POST /auditx/v1/events/publish`

```python
from auditx_connector import (
    JavaApiAuditPublisher,
    JavaApiConfig,
    AuditWriteRequest,
    CanonicalAuditEnvelope,
)

java_api = JavaApiAuditPublisher(
    JavaApiConfig(
        base_url="http://localhost:8080",
        verbose_logging=True,  # prints runtime publish logs to console
    )
)

# mode 1: stage + metadata map
java_api.publish_stage_map(
    stage="DISCONNECT_REQUEST_RECEIVED",
    conversation_id="550e8400-e29b-41d4-a716-446655440000",
    trace_id="trace-2001",
    metadata={"zapperCustId": "ZP-10091", "plan": "PREMIUM"},
)

# mode 2: AuditWriteRequest
java_api.publish_write_request(
    AuditWriteRequest(
        event_type="BILLING_VALIDATION_FAILED",
        conversation_id="550e8400-e29b-41d4-a716-446655440000",
    )
)

# mode 3: CanonicalAuditEnvelope
java_api.publish_envelope(
    CanonicalAuditEnvelope(
        event_type="DISCONNECT_API_TRIGGERED",
        conversation_id="550e8400-e29b-41d4-a716-446655440000",
    )
)
```

## Stage Enum Utility Pattern

Define stage enum with static stage metadata (`stage_name`, `source`, `severity`).

```python
from enum import Enum

from auditx_connector import AuditSeverity, AuditSource, AuditStage


class DisconnectStage(Enum):
    DISCONNECT_REQUEST_RECEIVED = (
        "DISCONNECT_REQUEST_RECEIVED",
        AuditSource.EMAIL_POSTFIX,
        AuditSeverity.INFO,
    )
    BILLING_VALIDATION_FAILED = (
        "BILLING_VALIDATION_FAILED",
        AuditSource.API,
        AuditSeverity.ERROR,
    )

    def stage_name(self) -> str:
        return self.value[0]

    def source(self) -> AuditSource:
        return self.value[1]

    def severity(self) -> AuditSeverity:
        return self.value[2]
```

Publish with stage + trace + metadata:

```python
metadata = {
    "zapperCustId": "ZP-10091",
    "address": "ABCD, XX",
    "plan": "PREMIUM",
}

service.publish_by_stage(
    stage=DisconnectStage.DISCONNECT_REQUEST_RECEIVED,
    conversation_id="550e8400-e29b-41d4-a716-446655440000",
    trace_id="trace-11",
    metadata=metadata,
)
```

Publish with stage + base `AuditWriteRequest`:

```python
base_request = AuditWriteRequest(
    event_type="PLACEHOLDER",
    source=AuditSource.CRON,
    conversation_id="550e8400-e29b-41d4-a716-446655440000",
    group_id="grp-1001",
    interaction_id="int-2001",
    extra_map={"existing": "value"},
)

service.publish_by_stage(
    stage=DisconnectStage.BILLING_VALIDATION_FAILED,
    conversation_id="550e8400-e29b-41d4-a716-446655440000",
    trace_id="trace-12",
    metadata={"errorCode": "ADDRESS_MISMATCH"},
    base_request=base_request,
)
```

Publish with stage + base `CanonicalAuditEnvelope`:

```python
base_envelope = CanonicalAuditEnvelope(
    event_type="PLACEHOLDER",
    source=AuditSource.SYSTEM,
    conversation_id="550e8400-e29b-41d4-a716-446655440000",
    group_id="grp-1001",
    interaction_id="int-2001",
    service_name="zapper-disconnect-service",
    extra_map={"existing": "value"},
)

service.publish_by_stage(
    stage=DisconnectStage.DISCONNECT_REQUEST_RECEIVED,
    conversation_id="550e8400-e29b-41d4-a716-446655440000",
    trace_id="trace-13",
    metadata={"sourceSystem": "CCTEAM_EXCEL"},
    base_envelope=base_envelope,
)
```

## Utility Class Example

```python
from __future__ import annotations

from enum import Enum
from typing import Any

from auditx_connector import (
    AuditService,
    AuditSeverity,
    AuditSource,
    AuditStage,
    AuditWriteRequest,
    CanonicalAuditEnvelope,
)


class DisconnectStage(Enum):
    DISCONNECT_REQUEST_RECEIVED = (
        "DISCONNECT_REQUEST_RECEIVED",
        AuditSource.EMAIL_POSTFIX,
        AuditSeverity.INFO,
    )
    INVENTORY_ENRICHMENT_STARTED = (
        "INVENTORY_ENRICHMENT_STARTED",
        AuditSource.CRON,
        AuditSeverity.INFO,
    )
    BILLING_VALIDATION_FAILED = (
        "BILLING_VALIDATION_FAILED",
        AuditSource.API,
        AuditSeverity.ERROR,
    )

    def stage_name(self) -> str:
        return self.value[0]

    def source(self) -> AuditSource:
        return self.value[1]

    def severity(self) -> AuditSeverity:
        return self.value[2]


class AuditEventUtil:
    @staticmethod
    def base_metadata(zapper_cust_id: str, address: str, plan: str) -> dict[str, Any]:
        return {
            "zapperCustId": zapper_cust_id,
            "address": address,
            "plan": plan,
            "domain": "ELECTRICITY_DISCONNECT",
        }

    @staticmethod
    def build_write_request(
        stage: str,
        conversation_id: str,
        group_id: str,
        interaction_id: str,
        metadata: dict[str, Any] | None,
    ) -> AuditWriteRequest:
        return AuditWriteRequest(
            event_type=stage,
            source=AuditSource.CRON,
            severity=AuditSeverity.INFO,
            conversation_id=conversation_id,
            group_id=group_id,
            interaction_id=interaction_id,
            extra_map=dict(metadata or {}),
        )

    @staticmethod
    def build_canonical_envelope(
        stage: str,
        conversation_id: str,
        group_id: str,
        interaction_id: str,
        metadata: dict[str, Any] | None,
    ) -> CanonicalAuditEnvelope:
        return CanonicalAuditEnvelope(
            event_type=stage,
            source=AuditSource.SYSTEM,
            severity=AuditSeverity.INFO,
            service_name="zapper-disconnect-service",
            environment="prod",
            conversation_id=conversation_id,
            group_id=group_id,
            interaction_id=interaction_id,
            business_keys={"entityType": "disconnect-request"},
            extra_map=dict(metadata or {}),
        )

    @staticmethod
    def publish_by_stage(
        service: AuditService,
        stage: DisconnectStage,
        conversation_id: str,
        trace_id: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        service.publish_by_stage(stage, conversation_id, trace_id, metadata)
```

## Validation Rules

- `conversation_id` is required and must be UUID.
- If `source == AuditSource.UI`, `session_id` is required.

## Idempotency

Default key input:

`event_type | source | conversation_id | interaction_id | group_id`

SHA-256 hash is used as idempotency key when key is missing.

If you are debugging "publish executed but no row inserted":
- turn on Python logging for `auditx_connector.publishers.postgres`
- set `AuditConnectorConfig(raise_on_dedup=True)` to fail fast when insert is skipped by idempotency conflict
- provide `interaction_id/group_id` (or explicit `idempotency_key`) so repeated calls are not treated as duplicates unintentionally
- set `AuditConnectorConfig(verbose_logging=True)` to print execution-level messages (start, rows_affected, dedupe, error)

## Local install without publishing

Use this when you want to test on another system without uploading to PyPI.

### Build wheel

```bash
python -m pip install --upgrade build
python -m build
```

Copy generated `dist/*.whl` to your local package folder, for example:
- `/Users/salilvnair/local-pypi`

### Install directly from local folder (one-time command)

```bash
pip install --no-index --find-links=/Users/salilvnair/local-pypi auditx-connector
```

### Persistent pip config (local folder only, no internet)

`~/.pip/pip.conf`

```ini
[global]
no-index = true
find-links = /Users/salilvnair/local-pypi
```

### Persistent pip config with fallback to indexes

```ini
[global]
find-links =
    /Users/salilvnair/local-pypi
    /Users/salilvnair/team-pypi
index-url = https://your-primary/simple
extra-index-url =
    https://repo1/simple
    https://repo2/simple
```

Notes:
- If `no-index = true`, pip never queries any online index.
- For fallback to indexes, do not set `no-index`.

## Build and Publish to PyPI

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

## Notes

- Package name: `auditx-connector`
- Import path: `auditx_connector`

## Publishing the package

# 1) bump version (example: 1.0.0 -> 1.0.1)
sed -i '' 's/^version = "1.0.0"/version = "1.0.1"/' pyproject.toml

# 2) clean old artifacts
rm -rf dist build *.egg-info

# 3) build
python -m pip install --upgrade build twine
python -m build

# 4) validate package
python -m twine check dist/*

# 5) publish to PyPI
python -m twine upload dist/*
