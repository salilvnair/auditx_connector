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
        table="audit_event",
    ),
    connector_config=AuditConnectorConfig(enabled=True, enforce_idempotency=True),
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
    JavaApiConfig(base_url="http://localhost:8080")
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
