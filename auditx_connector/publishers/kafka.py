from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

from auditx_connector.config import AuditConnectorConfig, KafkaConfig, KafkaMessageKeyType
from auditx_connector.models import CanonicalAuditEnvelope, IdempotencyKeyFactory, validate_envelope

logger = logging.getLogger(__name__)


class KafkaAuditPublisher:
    def __init__(
        self,
        kafka_config: KafkaConfig,
        connector_config: AuditConnectorConfig,
        idempotency_key_factory: IdempotencyKeyFactory,
    ) -> None:
        self.kafka_config = kafka_config
        self.connector_config = connector_config
        self.idempotency_key_factory = idempotency_key_factory

        try:
            from kafka import KafkaProducer
        except ImportError as exc:
            raise RuntimeError(
                "kafka-python is required for KafkaAuditPublisher. Install with auditx-connector[kafka]."
            ) from exc

        self._producer = KafkaProducer(
            bootstrap_servers=self.kafka_config.bootstrap_servers,
            key_serializer=lambda value: value.encode("utf-8"),
            value_serializer=lambda value: value.encode("utf-8"),
        )

    def publish(self, envelope: CanonicalAuditEnvelope) -> None:
        if not self.connector_config.enabled:
            self._verbose("publish skipped: connector disabled")
            return

        try:
            validate_envelope(envelope)
            enriched = self._enrich(envelope)
            message_key = self._message_key(enriched)
            payload = json.dumps(asdict(enriched), default=str)

            self._verbose(
                "publish start: topic=%s key=%s event_type=%s conversation_id=%s",
                self.kafka_config.topic,
                message_key,
                enriched.event_type,
                enriched.conversation_id,
            )
            self._producer.send(self.kafka_config.topic, key=message_key, value=payload)
            logger.info(
                "AuditX kafka publish queued. topic=%s key=%s event_type=%s conversation_id=%s",
                self.kafka_config.topic,
                message_key,
                enriched.event_type,
                enriched.conversation_id,
            )
            self._verbose(
                "publish queued: topic=%s key=%s event_type=%s conversation_id=%s",
                self.kafka_config.topic,
                message_key,
                enriched.event_type,
                enriched.conversation_id,
            )
        except Exception as exc:
            logger.exception("AuditX kafka publish failed: %s", exc)
            self._verbose("publish failed: %s", exc)
            raise

    def close(self) -> None:
        self._producer.flush()
        self._producer.close()

    def _enrich(self, envelope: CanonicalAuditEnvelope) -> CanonicalAuditEnvelope:
        if not self.connector_config.enforce_idempotency:
            return envelope

        if envelope.idempotency_key:
            return envelope

        return envelope.with_idempotency_key(self.idempotency_key_factory.create(envelope))

    def _message_key(self, envelope: CanonicalAuditEnvelope) -> str:
        key_type = self.kafka_config.message_key_type

        if key_type == KafkaMessageKeyType.EVENT_ID:
            return envelope.event_id

        if key_type == KafkaMessageKeyType.CONVERSATION_ID:
            return envelope.conversation_id or envelope.event_id

        return envelope.idempotency_key or envelope.event_id

    def _verbose(self, message: str, *args: Any) -> None:
        if not self.connector_config.verbose_logging:
            return
        formatted = message % args if args else message
        print(f"[auditx][kafka] {formatted}")
