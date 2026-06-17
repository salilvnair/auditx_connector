from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Dict, Mapping, Protocol
from uuid import uuid4


class AuditSeverity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class AuditSource(str, Enum):
    UI = "UI"
    BACKEND = "BACKEND"
    EMAIL = "EMAIL"
    CRON = "CRON"
    DB = "DB"
    API = "API"
    OTHER = "OTHER"


class AuditStage(Protocol):
    def stage_name(self) -> str: ...

    def source(self) -> AuditSource: ...

    def severity(self) -> AuditSeverity: ...


@dataclass(frozen=True)
class AuditWriteRequest:
    event_type: str
    severity: AuditSeverity = AuditSeverity.INFO
    source: AuditSource = AuditSource.OTHER
    session_id: str | None = None
    conversation_id: str | None = None
    group_id: str | None = None
    interaction_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    idempotency_key: str | None = None
    business_keys: Dict[str, Any] = field(default_factory=dict)
    extra_map: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)
    actor: Dict[str, Any] = field(default_factory=dict)
    error_map: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalAuditEnvelope:
    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = ""
    severity: AuditSeverity = AuditSeverity.INFO
    source: AuditSource = AuditSource.OTHER
    service_name: str | None = None
    service_version: str | None = None
    environment: str | None = None
    session_id: str | None = None
    conversation_id: str | None = None
    group_id: str | None = None
    interaction_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    idempotency_key: str | None = None
    business_keys: Dict[str, Any] = field(default_factory=dict)
    extra_map: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)
    actor: Dict[str, Any] = field(default_factory=dict)
    error_map: Dict[str, Any] = field(default_factory=dict)

    def with_conversation_id(self, conversation_id: str) -> "CanonicalAuditEnvelope":
        return replace(self, conversation_id=conversation_id)

    def with_idempotency_key(self, idempotency_key: str) -> "CanonicalAuditEnvelope":
        return replace(self, idempotency_key=idempotency_key)


class IdempotencyKeyFactory(Protocol):
    def create(self, envelope: CanonicalAuditEnvelope) -> str: ...


class DefaultIdempotencyKeyFactory:
    def create(self, envelope: CanonicalAuditEnvelope) -> str:
        key_input = "|".join(
            [
                envelope.event_type or "",
                envelope.source.value if envelope.source else "",
                envelope.conversation_id or "",
                envelope.interaction_id or "",
                envelope.group_id or "",
            ]
        )
        return sha256(key_input.encode("utf-8")).hexdigest()


def merge_dicts(*values: Mapping[str, Any] | None) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for value in values:
        if value:
            merged.update(value)
    return merged


