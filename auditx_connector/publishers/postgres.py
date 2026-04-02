from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from typing import Any, Callable, Literal

from auditx_connector.config import AuditConnectorConfig, PostgresConfig
from auditx_connector.models import CanonicalAuditEnvelope, IdempotencyKeyFactory, validate_envelope

logger = logging.getLogger(__name__)


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
        self._driver = _detect_postgres_driver()

    def publish(self, envelope: CanonicalAuditEnvelope) -> None:
        if not self.connector_config.enabled:
            self._verbose("publish skipped: connector disabled")
            return

        try:
            validate_envelope(envelope)
            enriched = self._enrich(envelope)

            event_payload = asdict(enriched)
            connect_args = _build_connect_args(self.postgres_config, self._driver)
            json_wrapper = _json_wrapper(self._driver)

            table_name = _validate_table_name(self.postgres_config.table)
            self._verbose(
                "publish start: table=%s event_type=%s conversation_id=%s idempotency_key=%s",
                table_name,
                enriched.event_type,
                enriched.conversation_id,
                enriched.idempotency_key,
            )
            sql = f"""
                INSERT INTO {table_name} (
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

            conn = _connect(self._driver, connect_args)
            with conn:
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
                            "business_keys": json_wrapper(enriched.business_keys),
                            "extra_map": json_wrapper(enriched.extra_map),
                            "actor": json_wrapper(enriched.actor),
                            "error_map": json_wrapper(enriched.error_map),
                            "event_payload": json_wrapper(_json_defaultable(event_payload)),
                        },
                    )
                    rows_affected = cur.rowcount
                    if rows_affected == 0:
                        message = (
                            "AuditX deduplicated event (rows_affected=0). "
                            f"event_type={enriched.event_type}, "
                            f"conversation_id={enriched.conversation_id}, "
                            f"idempotency_key={enriched.idempotency_key}"
                        )
                        if self.connector_config.raise_on_dedup:
                            raise RuntimeError(message)
                        logger.warning(message)
                        self._verbose(message)
                    else:
                        message = (
                            "AuditX insert success. "
                            f"rows_affected={rows_affected} "
                            f"event_id={enriched.event_id} "
                            f"event_type={enriched.event_type} "
                            f"conversation_id={enriched.conversation_id}"
                        )
                        logger.info(message)
                        self._verbose(message)
        except Exception as exc:
            logger.exception("AuditX publish failed: %s", exc)
            self._verbose("AuditX publish failed: %s", exc)
            raise

    def _enrich(self, envelope: CanonicalAuditEnvelope) -> CanonicalAuditEnvelope:
        if not self.connector_config.enforce_idempotency:
            return envelope

        if envelope.idempotency_key:
            return envelope

        return envelope.with_idempotency_key(self.idempotency_key_factory.create(envelope))

    def _verbose(self, message: str, *args: Any) -> None:
        if not self.connector_config.verbose_logging:
            return
        formatted = message % args if args else message
        print(f"[auditx][postgres] {formatted}")


def _json_defaultable(payload: dict[str, Any]) -> dict[str, Any]:
    # Normalize datetime/enum-like values through json round-trip.
    return json.loads(json.dumps(payload, default=str))


def _build_connect_args(config: PostgresConfig, driver: Literal["psycopg", "psycopg2"]) -> dict[str, Any]:
    if config.dsn:
        if driver == "psycopg":
            return {"conninfo": config.dsn}
        return {"dsn": config.dsn}

    required = [config.host, config.database, config.username]
    if any(value is None or str(value).strip() == "" for value in required):
        raise ValueError(
            "PostgresConfig requires either dsn, or host+database+username "
            "(password optional) for connection."
        )

    args: dict[str, Any] = {
        "host": config.host,
        "port": config.port,
        "dbname": config.database,
        "user": config.username,
    }
    if config.password is not None:
        args["password"] = config.password
    return args


def _detect_postgres_driver() -> Literal["psycopg", "psycopg2"]:
    try:
        import psycopg  # noqa: F401
        return "psycopg"
    except ImportError:
        pass

    try:
        import psycopg2  # noqa: F401
        return "psycopg2"
    except ImportError as exc:
        raise RuntimeError(
            "PostgresAuditPublisher requires either psycopg (v3) or psycopg2. "
            "Install with auditx-connector[postgres] or add psycopg2/psycopg2-binary."
        ) from exc


def _json_wrapper(driver: Literal["psycopg", "psycopg2"]) -> Callable[[Any], Any]:
    if driver == "psycopg":
        from psycopg.types.json import Json
        return Json

    from psycopg2.extras import Json
    return Json


def _connect(driver: Literal["psycopg", "psycopg2"], connect_args: dict[str, Any]) -> Any:
    if driver == "psycopg":
        import psycopg
        return psycopg.connect(**connect_args)

    import psycopg2
    return psycopg2.connect(**connect_args)


def _validate_table_name(table_name: str) -> str:
    name = (table_name or "").strip()
    if not name:
        raise ValueError("PostgresConfig.table must not be empty")

    # Allow unquoted identifiers with optional schema: schema.table or table.
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?", name):
        raise ValueError(
            "PostgresConfig.table supports only unquoted table or schema.table names "
            "(alphanumeric and underscores)."
        )
    return name
