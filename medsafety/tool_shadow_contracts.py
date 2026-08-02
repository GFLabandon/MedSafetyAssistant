"""Strict workflow-state contracts accepted by the shadow tool planner."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from medsafety.contracts import InputResolutionStatus, StrictModel


class ShadowWorkflowStage(str, Enum):
    SESSION_START = "session_start"
    START = "start"
    AFTER_RESOLUTION = "after_resolution"
    AFTER_EVIDENCE = "after_evidence"


class ShadowWorkflowState(StrictModel):
    """Trusted state that planner adapters must project to a non-sensitive view."""

    stage: ShadowWorkflowStage
    question: str | None = Field(default=None, min_length=1, max_length=500)
    session_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_-]{1,128}$",
    )
    context_call_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9._-]{1,64}$",
    )
    artifact_call_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9._-]{1,64}$",
    )
    resolution_status: InputResolutionStatus | None = None
    use_llm_plan: bool = True

    @model_validator(mode="after")
    def stage_matches_state_shape(self):
        if self.stage == ShadowWorkflowStage.SESSION_START:
            if (
                self.question is not None
                or self.context_call_id is not None
                or self.artifact_call_id is not None
                or self.resolution_status is not None
            ):
                raise ValueError("session_start accepts only an optional session ID")
            return self

        if self.stage == ShadowWorkflowStage.START:
            if self.question is None:
                raise ValueError("start state requires a question")
            if (
                self.session_id is not None
                or self.artifact_call_id is not None
                or self.resolution_status is not None
            ):
                raise ValueError("start state accepts only a session-context artifact")
            return self

        if (
            self.question is not None
            or self.session_id is not None
            or self.context_call_id is not None
            or self.artifact_call_id is None
        ):
            raise ValueError("post-tool states require only an artifact reference")
        if self.stage == ShadowWorkflowStage.AFTER_RESOLUTION:
            if self.resolution_status is None:
                raise ValueError("after_resolution requires resolution_status")
        elif self.resolution_status is not None:
            raise ValueError("after_evidence cannot contain resolution_status")
        return self
