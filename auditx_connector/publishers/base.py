from __future__ import annotations

from typing import Protocol

from auditx_connector.models import CanonicalAuditEnvelope


class AuditPublisher(Protocol):
    def publish(self, envelope: CanonicalAuditEnvelope) -> None: ...
