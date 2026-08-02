"""Frozen case contracts for non-executing typed-tool selection evaluation."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from medsafety.contracts import InputResolutionStatus, StrictModel
from medsafety.tool_contracts import ToolName


class ShadowWorkflowStage(str, Enum):
    START = "start"
    AFTER_RESOLUTION = "after_resolution"
    AFTER_EVIDENCE = "after_evidence"


class ShadowWorkflowState(StrictModel):
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


class ExpectedShadowToolCall(StrictModel):
    name: ToolName
    arguments: dict[str, Any] = Field(max_length=4)


class ShadowToolSelectionCase(StrictModel):
    schema_version: Literal["tool-shadow-case-v1"] = "tool-shadow-case-v1"
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    split: Literal["dev", "test"]
    category: str = Field(min_length=1)
    state: ShadowWorkflowState
    expected: ExpectedShadowToolCall
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def expected_call_matches_deterministic_oracle(self):
        state = self.state
        if state.stage == ShadowWorkflowStage.START:
            expected_name = ToolName.RESOLVE_MEDICATIONS
            expected_arguments = {"question": state.question.strip()}
        elif state.stage == ShadowWorkflowStage.AFTER_RESOLUTION:
            expected_name = (
                ToolName.QUERY_SAFETY_GRAPH
                if state.resolution_status == InputResolutionStatus.RESOLVED
                else ToolName.REQUEST_CLARIFICATION
            )
            expected_arguments = {"resolution_call_id": state.artifact_call_id}
        else:
            expected_name = ToolName.RENDER_EVIDENCE_EXPLANATION
            expected_arguments = {
                "packet_call_id": state.artifact_call_id,
                "use_llm_plan": state.use_llm_plan,
            }
        if self.expected.name != expected_name:
            raise ValueError("expected tool name disagrees with deterministic oracle")
        if self.expected.arguments != expected_arguments:
            raise ValueError("expected arguments disagree with deterministic oracle")
        return self


def load_shadow_tool_cases(
    path: str | Path,
    *,
    split: Literal["dev", "test"] | None = None,
) -> list[ShadowToolSelectionCase]:
    cases = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(),
        1,
    ):
        if not line.strip():
            continue
        try:
            case = ShadowToolSelectionCase.model_validate_json(line)
        except Exception as exc:
            raise ValueError(f"invalid shadow case at line {line_number}") from exc
        if split is None or case.split == split:
            cases.append(case)
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("shadow dataset contains duplicate case IDs")
    return cases
