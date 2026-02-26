from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from auditx_connector.models import (
    AuditSeverity,
    AuditSource,
    AuditStage,
    AuditWriteRequest,
    CanonicalAuditEnvelope,
    merge_dicts,
)
from auditx_connector.publishers.base import AuditPublisher


class AuditService:
    def __init__(self, publisher: AuditPublisher) -> None:
        self.publisher = publisher

    def publish(self, request: AuditWriteRequest) -> None:
        self._publish_with_severity(request, request.severity)

    def publish_info(self, request: AuditWriteRequest) -> None:
        self._publish_with_severity(request, AuditSeverity.INFO)

    def publish_warn(self, request: AuditWriteRequest) -> None:
        self._publish_with_severity(request, AuditSeverity.WARN)

    def publish_error(self, request: AuditWriteRequest) -> None:
        if not request.error_map:
            raise ValueError("error_map is required for publish_error")
        self._publish_with_severity(request, AuditSeverity.ERROR)

    def publish_envelope(self, envelope: CanonicalAuditEnvelope) -> None:
        self.publisher.publish(envelope)

    def publish_stage(self, stage: str, conversation_id: str, metadata: Mapping[str, Any] | None = None) -> None:
        if not stage:
            raise ValueError("stage is required")
        if not conversation_id:
            raise ValueError("conversation_id is required")

        request = AuditWriteRequest(
            event_type=stage,
            source=AuditSource.OTHER,
            severity=AuditSeverity.INFO,
            conversation_id=conversation_id,
            extra_map=dict(metadata or {}),
        )
        self.publish_info(request)

    def publish_by_stage(
        self,
        stage: AuditStage,
        conversation_id: str,
        trace_id: str | None,
        metadata: Mapping[str, Any] | None,
        base_request: AuditWriteRequest | None = None,
        base_envelope: CanonicalAuditEnvelope | None = None,
    ) -> None:
        self._validate_stage(stage, conversation_id)

        if base_request and base_envelope:
            raise ValueError("Provide only one of base_request or base_envelope")

        if base_envelope:
            envelope = self._build_from_envelope(stage, conversation_id, trace_id, metadata, base_envelope)
            self.publish_envelope(envelope)
            return

        request = self._build_from_request(stage, conversation_id, trace_id, metadata, base_request)
        self.publish(request)

    def _build_from_request(
        self,
        stage: AuditStage,
        conversation_id: str,
        trace_id: str | None,
        metadata: Mapping[str, Any] | None,
        base_request: AuditWriteRequest | None,
    ) -> AuditWriteRequest:
        if not base_request:
            return AuditWriteRequest(
                event_type=stage.stage_name(),
                source=stage.source(),
                severity=stage.severity(),
                conversation_id=conversation_id,
                trace_id=trace_id,
                extra_map=dict(metadata or {}),
            )

        return replace(
            base_request,
            event_type=stage.stage_name(),
            source=stage.source(),
            severity=stage.severity(),
            conversation_id=conversation_id,
            trace_id=trace_id,
            extra_map=merge_dicts(base_request.extra_map, metadata),
        )

    def _build_from_envelope(
        self,
        stage: AuditStage,
        conversation_id: str,
        trace_id: str | None,
        metadata: Mapping[str, Any] | None,
        base_envelope: CanonicalAuditEnvelope,
    ) -> CanonicalAuditEnvelope:
        return replace(
            base_envelope,
            event_type=stage.stage_name(),
            source=stage.source(),
            severity=stage.severity(),
            conversation_id=conversation_id,
            trace_id=trace_id,
            extra_map=merge_dicts(base_envelope.extra_map, metadata),
        )

    def _publish_with_severity(self, request: AuditWriteRequest, severity: AuditSeverity) -> None:
        envelope = CanonicalAuditEnvelope(
            event_type=request.event_type,
            severity=severity,
            source=request.source,
            session_id=request.session_id,
            conversation_id=request.conversation_id,
            group_id=request.group_id,
            interaction_id=request.interaction_id,
            trace_id=request.trace_id,
            span_id=request.span_id,
            idempotency_key=request.idempotency_key,
            business_keys=dict(request.business_keys),
            extra_map=dict(request.extra_map),
            actor=dict(request.actor),
            error_map=dict(request.error_map),
        )
        self.publisher.publish(envelope)

    def _validate_stage(self, stage: AuditStage, conversation_id: str) -> None:
        if stage is None:
            raise ValueError("stage is required")
        if not stage.stage_name():
            raise ValueError("stage.stage_name() is required")
        if stage.source() is None:
            raise ValueError("stage.source() is required")
        if stage.severity() is None:
            raise ValueError("stage.severity() is required")
        if not conversation_id:
            raise ValueError("conversation_id is required")
