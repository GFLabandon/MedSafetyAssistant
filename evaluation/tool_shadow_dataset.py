"""Frozen case contracts for non-executing typed-tool selection evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from medsafety.contracts import InputResolutionStatus, StrictModel
from medsafety.tool_contracts import ToolName
from medsafety.tool_shadow_contracts import ShadowWorkflowStage, ShadowWorkflowState


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
