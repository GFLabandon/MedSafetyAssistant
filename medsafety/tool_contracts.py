"""Versioned contracts for the bounded typed-tool safety workflow."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from medsafety.contracts import (
    ConclusionStatus,
    InputResolution,
    InputResolutionStatus,
    SafetyExplanation,
    StrictModel,
)


class ToolName(str, Enum):
    RESOLVE_MEDICATIONS = "resolve_medications"
    QUERY_SAFETY_GRAPH = "query_safety_graph"
    REQUEST_CLARIFICATION = "request_clarification"
    RENDER_EVIDENCE_EXPLANATION = "render_evidence_explanation"


class ToolCallStatus(str, Enum):
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class ToolFailureReason(str, Enum):
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENTS = "invalid_arguments"
    INVALID_ARTIFACT_REFERENCE = "invalid_artifact_reference"
    INVALID_OUTPUT = "invalid_output"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"


class ResolveMedicationsArguments(StrictModel):
    question: str = Field(min_length=1, max_length=500)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()


class QuerySafetyGraphArguments(StrictModel):
    resolution_call_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")


class RequestClarificationArguments(StrictModel):
    resolution_call_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")


class RenderEvidenceExplanationArguments(StrictModel):
    packet_call_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    use_llm_plan: bool = True


class ToolCallRequest(StrictModel):
    """An untrusted tool proposal before registry and argument validation."""

    schema_version: Literal["typed-tool-call-v1"] = "typed-tool-call-v1"
    call_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    arguments: dict[str, Any] = Field(max_length=16)


class ToolDefinition(StrictModel):
    schema_version: Literal["typed-tool-definition-v1"] = "typed-tool-definition-v1"
    name: ToolName
    description: str = Field(min_length=1)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class ToolCallTrace(StrictModel):
    schema_version: Literal["tool-call-trace-v1"] = "tool-call-trace-v1"
    call_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    tool_name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    status: ToolCallStatus
    duration_ms: float = Field(ge=0)
    argument_keys: list[str] = Field(default_factory=list)
    output_schema: str | None = None
    failure_reason: ToolFailureReason | None = None

    @model_validator(mode="after")
    def status_matches_failure_shape(self):
        if self.status == ToolCallStatus.COMPLETED and self.failure_reason is not None:
            raise ValueError("completed tool calls cannot contain a failure reason")
        if self.status != ToolCallStatus.COMPLETED and self.failure_reason is None:
            raise ValueError("non-completed tool calls require a failure reason")
        return self


class ToolWorkflowTrace(StrictModel):
    schema_version: Literal["tool-workflow-trace-v1"] = "tool-workflow-trace-v1"
    request_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    max_steps: int = Field(ge=1, le=8)
    executed_steps: int = Field(ge=1, le=8)
    total_duration_ms: float = Field(ge=0)
    tool_calls: list[ToolCallTrace] = Field(min_length=1, max_length=8)
    resolution_status: InputResolutionStatus
    conclusion_status: ConclusionStatus

    @model_validator(mode="after")
    def steps_match_trace(self):
        if self.executed_steps != len(self.tool_calls):
            raise ValueError("executed_steps must equal the tool call count")
        if self.executed_steps > self.max_steps:
            raise ValueError("tool call count cannot exceed max_steps")
        call_ids = [call.call_id for call in self.tool_calls]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("tool call IDs must be unique")
        return self


class ToolWorkflowResponse(StrictModel):
    schema_version: Literal["typed-safety-workflow-v1"] = "typed-safety-workflow-v1"
    resolution: InputResolution
    explanation: SafetyExplanation
    trace: ToolWorkflowTrace
