"""Strict, content-free session context for the V1 safety workflow.

The V1 workflow never reuses legacy conversation text.  It persists only
catalog-backed entity identifiers and bounded conclusion metadata so a later
explicit follow-up can be resolved without giving a model access to Redis.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Protocol

from pydantic import Field, model_validator

from medsafety.contracts import ConclusionStatus, StrictModel


class SessionContextReadStatus(str, Enum):
    DISABLED = "disabled"
    EMPTY = "empty"
    AVAILABLE = "available"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class SessionContextWriteStatus(str, Enum):
    DISABLED = "disabled"
    STORED = "stored"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"


class SessionContextSnapshot(StrictModel):
    schema_version: Literal["session-context-v1"] = "session-context-v1"
    status: SessionContextReadStatus
    medication_ids: list[str] = Field(default_factory=list, max_length=8)
    context_ids: list[str] = Field(default_factory=list, max_length=8)
    data_version: str | None = Field(default=None, min_length=1)
    prior_conclusion_status: ConclusionStatus | None = None

    @model_validator(mode="after")
    def status_matches_payload(self):
        has_payload = bool(
            self.medication_ids
            or self.context_ids
            or self.data_version
            or self.prior_conclusion_status
        )
        if self.status == SessionContextReadStatus.AVAILABLE:
            if not self.medication_ids or self.data_version is None:
                raise ValueError("available session context requires entities and version")
        elif has_payload:
            raise ValueError("non-available session context cannot expose stored payload")
        return self


class StoredSessionContext(StrictModel):
    schema_version: Literal["stored-session-context-v1"] = (
        "stored-session-context-v1"
    )
    medication_ids: list[str] = Field(min_length=1, max_length=8)
    context_ids: list[str] = Field(default_factory=list, max_length=8)
    data_version: str = Field(min_length=1)
    prior_conclusion_status: ConclusionStatus


class SessionContextTrace(StrictModel):
    schema_version: Literal["session-context-trace-v1"] = (
        "session-context-trace-v1"
    )
    read_status: SessionContextReadStatus
    write_status: SessionContextWriteStatus
    context_applied: bool = False

    @model_validator(mode="after")
    def applied_context_must_be_available(self):
        if self.context_applied and self.read_status != SessionContextReadStatus.AVAILABLE:
            raise ValueError("applied context must come from an available snapshot")
        return self


class SessionContextStore(Protocol):
    def load(
        self,
        session_id: str,
        *,
        expected_data_version: str,
    ) -> SessionContextSnapshot: ...

    def save(self, session_id: str, context: StoredSessionContext) -> None: ...
