from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from auditx_connector.config import AuditConnectorConfig, PostgresConfig
from auditx_connector.models import CanonicalAuditEnvelope, IdempotencyKeyFactory, validate_envelope


class PostgresAuditPublisher:
    def __init__(
        self,
        postgres_config: PostgresConfig,
        connector_config: AuditConnectorConfig,
        idempotency_key_factory: IdempotencyKeyFactory,
    ) -> None:
        self.postgres_config = postgres_config
        self.connector_config = connector_config
        self.idempotency_key_factory = idempotency_key_factory

    def publish(self, envelope: CanonicalAuditEnvelope) -> None:
        if not self.connector_config.enabled:
            return

        validate_envelope(envelope)
        enriched = self._enrich(envelope)

        try:
            import psycopg
            from psycopg.types.json import Json
        except ImportError as exc:
            raise RuntimeError(
                "psycopg is required for PostgresAuditPublisher. Install with auditx-connector[postgres]."
            ) from exc

        event_payload = asdict(enriched)

        sql = f"""
            INSERT INTO {self.postgres_config.table} (
                event_id, event_time, event_type, severity, source,
                service_name, service_version, environment,
                session_id, conversation_id, group_id, interaction_id,
                trace_id, span_id, idempotency_key,
                business_keys, extra_map, actor, error_map, event_payload
            ) VALUES (
                %(event_id)s, %(event_time)s, %(event_type)s, %(severity)s, %(source)s,
                %(service_name)s, %(service_version)s, %(environment)s,
                %(session_id)s, %(conversation_id)s, %(group_id)s, %(interaction_id)s,
                %(trace_id)s, %(span_id)s, %(idempotency_key)s,
                %(business_keys)s, %(extra_map)s, %(actor)s, %(error_map)s, %(event_payload)s
            )
            ON CONFLICT (idempotency_key) DO NOTHING
        """

        with psycopg.connect(self.postgres_config.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    {
                        "event_id": enriched.event_id,
                        "event_time": enriched.event_time,
                        "event_type": enriched.event_type,
                        "severity": enriched.severity.value,
                        "source": enriched.source.value,
                        "service_name": enriched.service_name,
                        "service_version": enriched.service_version,
                        "environment": enriched.environment,
                        "session_id": enriched.session_id,
                        "conversation_id": enriched.conversation_id,
                        "group_id": enriched.group_id,
                        "interaction_id": enriched.interaction_id,
                        "trace_id": enriched.trace_id,
                        "span_id": enriched.span_id,
                        "idempotency_key": enriched.idempotency_key,
                        "business_keys": Json(enriched.business_keys),
                        "extra_map": Json(enriched.extra_map),
                        "actor": Json(enriched.actor),
                        "error_map": Json(enriched.error_map),
                        "event_payload": Json(_json_defaultable(event_payload)),
                    },
                )

    def _enrich(self, envelope: CanonicalAuditEnvelope) -> CanonicalAuditEnvelope:
        if not self.connector_config.enforce_idempotency:
            return envelope

        if envelope.idempotency_key:
            return envelope

        return envelope.with_idempotency_key(self.idempotency_key_factory.create(envelope))


def _json_defaultable(payload: dict[str, Any]) -> dict[str, Any]:
    # Normalize datetime/enum-like values through json round-trip.
    return json.loads(json.dumps(payload, default=str))
