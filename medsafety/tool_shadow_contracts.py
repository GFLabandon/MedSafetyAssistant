"""Strict workflow-state contracts accepted by the shadow tool planner."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from medsafety.contracts import InputResolutionStatus, StrictModel


class ShadowWorkflowStage(str, Enum):
    START = "start"
    AFTER_RESOLUTION = "after_resolution"
    AFTER_EVIDENCE = "after_evidence"


class ShadowWorkflowState(StrictModel):
    """Trusted server state exposed to the model as a read-only JSON value."""

    stage: ShadowWorkflowStage
    question: str | None = Field(default=None, min_length=1, max_length=500)
    artifact_call_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9._-]{1,64}$",
    )
    resolution_status: InputResolutionStatus | None = None
    use_llm_plan: bool = True

    @model_validator(mode="after")
    def stage_matches_state_shape(self):
        if self.stage == ShadowWorkflowStage.START:
            if self.question is None:
                raise ValueError("start state requires a question")
            if self.artifact_call_id is not None or self.resolution_status is not None:
                raise ValueError("start state cannot contain a prior artifact")
            return self

        if self.question is not None or self.artifact_call_id is None:
            raise ValueError("post-tool states require only an artifact reference")
        if self.stage == ShadowWorkflowStage.AFTER_RESOLUTION:
            if self.resolution_status is None:
                raise ValueError("after_resolution requires resolution_status")
        elif self.resolution_status is not None:
            raise ValueError("after_evidence cannot contain resolution_status")
        return self
