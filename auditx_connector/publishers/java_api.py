from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Mapping
from urllib import request as urllib_request

from auditx_connector.config import JavaApiConfig
from auditx_connector.models import AuditSeverity, AuditSource, AuditWriteRequest, CanonicalAuditEnvelope


class JavaApiAuditPublisher:
    """
    Publishes audit payloads to Java AuditX endpoint.

    Supports 3 payload modes:
    1) stage + metadata map
    2) AuditWriteRequest
    3) CanonicalAuditEnvelope
    """

    def __init__(self, java_api_config: JavaApiConfig) -> None:
        self.java_api_config = java_api_config

    def publish_stage_map(
        self,
        stage: str,
        conversation_id: str,
        trace_id: str | None,
        metadata: Mapping[str, Any] | None,
        source: AuditSource = AuditSource.OTHER,
        severity: AuditSeverity = AuditSeverity.INFO,
    ) -> dict[str, str]:
        payload = {
            "stage": stage,
            "conversationId": conversation_id,
            "traceId": trace_id,
            "source": source.value,
            "severity": severity.value,
            "metadata": dict(metadata or {}),
        }
        return self._post(payload)

    def publish_write_request(self, request: AuditWriteRequest) -> dict[str, str]:
        payload = {"auditWriteRequest": _to_api_map(request)}
        return self._post(payload)

    def publish_envelope(self, envelope: CanonicalAuditEnvelope) -> dict[str, str]:
        payload = {"canonicalEnvelope": _to_api_map(envelope)}
        return self._post(payload)

    def _post(self, payload: Mapping[str, Any]) -> dict[str, str]:
        endpoint = f"{self.java_api_config.base_url.rstrip('/')}{self.java_api_config.publish_path}"
        req = urllib_request.Request(
            endpoint,
            data=json.dumps(payload, default=str).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib_request.urlopen(req, timeout=self.java_api_config.timeout_seconds) as response:
            body = response.read().decode("utf-8")
            if not body:
                return {"status": "UNKNOWN"}
            decoded = json.loads(body)
            return {str(k): str(v) for k, v in decoded.items()}


def _to_api_map(value: Any) -> dict[str, Any]:
    payload = asdict(value)

    # Convert enum + datetime friendly values to JSON-safe primitives.
    normalized = json.loads(json.dumps(payload, default=lambda v: getattr(v, "value", str(v))))

    # Convert snake_case keys to Java API camelCase expected keys.
    mapped: dict[str, Any] = {}
    for key, item in normalized.items():
        mapped[_snake_to_camel(key)] = item
    return mapped


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])
