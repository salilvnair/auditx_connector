from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PublisherType(str, Enum):
    ASYNC_DB = "ASYNC_DB"
    KAFKA = "KAFKA"
    JAVA_API = "JAVA_API"


class KafkaMessageKeyType(str, Enum):
    IDEMPOTENCY_KEY = "IDEMPOTENCY_KEY"
    EVENT_ID = "EVENT_ID"
    CONVERSATION_ID = "CONVERSATION_ID"


@dataclass(frozen=True)
class KafkaConfig:
    bootstrap_servers: str
    topic: str = "auditx.events"
    message_key_type: KafkaMessageKeyType = KafkaMessageKeyType.IDEMPOTENCY_KEY


@dataclass(frozen=True)
class PostgresConfig:
    dsn: str | None = None
    host: str | None = None
    port: int = 5432
    database: str | None = None
    username: str | None = None
    password: str | None = None
    table: str = "AUDITX_EVENT"


@dataclass(frozen=True)
class JavaApiConfig:
    base_url: str
    publish_path: str = "/auditx/v1/events/publish"
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class AuditConnectorConfig:
    enabled: bool = True
    enforce_idempotency: bool = True
    async_publish: bool = True
