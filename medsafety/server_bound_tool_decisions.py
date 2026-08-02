"""Name-only model proposals with server-bound typed tool arguments.

The model receives only the minimum routing state and can propose one tool
name.  It never receives user text or artifact identifiers, and its generated
arguments are discarded.  The server validates the name against the current
workflow stage and constructs every argument from trusted state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from time import perf_counter
from typing import Any, Literal

import ollama
from pydantic import Field, model_validator

from medsafety.contracts import (
    InputResolution,
    InputResolutionStatus,
    SafetyExplanation,
    StrictModel,
)
from medsafety.tool_contracts import (
    ToolCallRequest,
    ToolDefinition,
    ToolName,
    ToolWorkflowTrace,
)
from medsafety.tool_shadow_contracts import ShadowWorkflowStage, ShadowWorkflowState


TOOL_NAME_PROMPT_VERSION = "server-bound-tool-name-v1"
DEFAULT_TOOL_NAME_OPTIONS = {
    "temperature": 0,
    "seed": 42,
    "num_predict": 48,
}


def _response_field(response: Any, name: str):
    if isinstance(response, dict):
        return response.get(name)
    return getattr(response, name, None)


@dataclass(frozen=True)
class ToolNamePlanAttempt:
    proposed_name: str | None
    call_count: int
    latency_ms: float
    error_category: str | None
    error_type: str | None
    content_present: bool
    response_metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ToolDecisionFallbackReason(str, Enum):
    PLANNER_ERROR = "planner_error"
    UNKNOWN_TOOL = "unknown_tool"
    STAGE_MISMATCH = "stage_mismatch"


class ServerBoundToolDecision(StrictModel):
    """Auditable result after validating a model name and binding server data."""

    schema_version: Literal["server-bound-tool-decision-v1"] = (
        "server-bound-tool-decision-v1"
    )
    expected_name: ToolName
    proposed_name: str | None = Field(default=None, max_length=128)
    proposal_accepted: bool
    fallback_reason: ToolDecisionFallbackReason | None = None
    planner_error_category: str | None = Field(default=None, max_length=64)
    call: ToolCallRequest

    @model_validator(mode="after")
    def acceptance_matches_decision(self):
        if self.call.name != self.expected_name.value:
            raise ValueError("bound call must use the stage-expected tool")
        if self.proposal_accepted:
            if self.proposed_name != self.expected_name.value:
                raise ValueError("accepted proposal must match the expected tool")
            if self.fallback_reason is not None or self.planner_error_category is not None:
                raise ValueError("accepted proposals cannot have fallback metadata")
        elif self.fallback_reason is None:
            raise ValueError("rejected proposals require a fallback reason")
        return self


class ServerBoundToolDecisionTrace(StrictModel):
    """Public trace without argument values or model response content."""

    schema_version: Literal["server-bound-tool-decision-trace-v1"] = (
        "server-bound-tool-decision-trace-v1"
    )
    call_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    expected_name: ToolName
    proposed_name: str | None = Field(default=None, max_length=128)
    proposal_accepted: bool
    fallback_reason: ToolDecisionFallbackReason | None = None
    planner_error_category: str | None = Field(default=None, max_length=64)
    planner_latency_ms: float = Field(ge=0)
    argument_keys: list[str] = Field(default_factory=list)


class ServerBoundWorkflowResponse(StrictModel):
    schema_version: Literal["server-bound-safety-workflow-v1"] = (
        "server-bound-safety-workflow-v1"
    )
    resolution: InputResolution
    explanation: SafetyExplanation
    trace: ToolWorkflowTrace
    decisions: list[ServerBoundToolDecisionTrace] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def decisions_match_tool_trace(self):
        tool_call_ids = [call.call_id for call in self.trace.tool_calls]
        decision_call_ids = [decision.call_id for decision in self.decisions]
        if decision_call_ids != tool_call_ids:
            raise ValueError("decision traces must match executed tool calls")
        return self


class OllamaToolNamePlanner:
    """Ask Ollama for one tool name without exposing argument-bearing state."""

    def __init__(
        self,
        host: str,
        model: str,
        client: Any | None = None,
        timeout_seconds: float = 10.0,
        options: dict[str, Any] | None = None,
    ):
        self.model = model
        self.client = client or ollama.Client(host=host, timeout=timeout_seconds)
        self.options = dict(options or DEFAULT_TOOL_NAME_OPTIONS)
        self.prompt_version = TOOL_NAME_PROMPT_VERSION

    @staticmethod
    def build_tools(definitions: list[ToolDefinition]) -> list[dict[str, Any]]:
        empty_parameters = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
        return [
            {
                "type": "function",
                "function": {
                    "name": definition.name.value,
                    "description": definition.description,
                    "parameters": empty_parameters,
                },
            }
            for definition in definitions
        ]

    @staticmethod
    def build_messages(state: ShadowWorkflowState) -> list[dict[str, str]]:
        routing_state: dict[str, str] = {"stage": state.stage.value}
        if state.resolution_status is not None:
            routing_state["resolution_status"] = state.resolution_status.value
        state_lines = "\n".join(
            f"{key}={value}" for key, value in sorted(routing_state.items())
        )
        return [
            {
                "role": "system",
                "content": (
                    f"Prompt version: {TOOL_NAME_PROMPT_VERSION}. Select exactly one "
                    "registered tool and emit one tool call with an empty arguments "
                    "object and no prose. Apply exactly one rule: stage=start selects "
                    "resolve_medications; stage=after_resolution with "
                    "resolution_status=resolved selects query_safety_graph; "
                    "stage=after_resolution with resolution_status=ambiguous, unknown, "
                    "or rejected selects request_clarification; stage=after_evidence "
                    "selects render_evidence_explanation. The server owns and binds all "
                    "arguments after validating your tool name."
                ),
            },
            {
                "role": "user",
                "content": "Select from this trusted routing state only:\n" + state_lines,
            },
        ]

    def propose(
        self,
        state: ShadowWorkflowState,
        definitions: list[ToolDefinition],
    ) -> ToolNamePlanAttempt:
        started = perf_counter()
        try:
            response = self.client.chat(
                model=self.model,
                messages=self.build_messages(state),
                tools=self.build_tools(definitions),
                stream=False,
                think=False,
                options=self.options,
            )
        except Exception as exc:
            return self._error_attempt(
                started,
                category="request_error",
                error_type=type(exc).__name__,
            )

        latency_ms = self._elapsed_ms(started)
        metadata = self._response_metadata(response)
        message = _response_field(response, "message")
        if message is None:
            return self._error_attempt(
                started,
                category="invalid_response_shape",
                error_type="ValueError",
                metadata=metadata,
            )
        content = _response_field(message, "content")
        tool_calls = _response_field(message, "tool_calls") or []
        try:
            call_count = len(tool_calls)
        except TypeError:
            return ToolNamePlanAttempt(
                proposed_name=None,
                call_count=0,
                latency_ms=latency_ms,
                error_category="invalid_response_shape",
                error_type="TypeError",
                content_present=bool(content),
                response_metadata=metadata,
            )
        if call_count != 1:
            return ToolNamePlanAttempt(
                proposed_name=None,
                call_count=call_count,
                latency_ms=latency_ms,
                error_category=(
                    "no_tool_call" if call_count == 0 else "multiple_tool_calls"
                ),
                error_type=None,
                content_present=bool(content),
                response_metadata=metadata,
            )

        function = _response_field(tool_calls[0], "function")
        name = _response_field(function, "name")
        if not isinstance(name, str) or not name or len(name) > 128:
            return ToolNamePlanAttempt(
                proposed_name=None,
                call_count=1,
                latency_ms=latency_ms,
                error_category="invalid_response_shape",
                error_type="ValueError",
                content_present=bool(content),
                response_metadata=metadata,
            )
        return ToolNamePlanAttempt(
            proposed_name=name,
            call_count=1,
            latency_ms=latency_ms,
            error_category=None,
            error_type=None,
            content_present=bool(content),
            response_metadata=metadata,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((perf_counter() - started) * 1000, 3)

    @classmethod
    def _error_attempt(
        cls,
        started: float,
        *,
        category: str,
        error_type: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolNamePlanAttempt:
        return ToolNamePlanAttempt(
            proposed_name=None,
            call_count=0,
            latency_ms=cls._elapsed_ms(started),
            error_category=category,
            error_type=error_type,
            content_present=False,
            response_metadata=metadata or {},
        )

    @staticmethod
    def _response_metadata(response: Any) -> dict[str, Any]:
        metadata = {}
        for field in (
            "model",
            "created_at",
            "done",
            "done_reason",
            "total_duration",
            "load_duration",
            "prompt_eval_count",
            "prompt_eval_duration",
            "eval_count",
            "eval_duration",
        ):
            value = _response_field(response, field)
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            if value is not None:
                metadata[field] = value
        return metadata


def bind_server_tool_decision(
    state: ShadowWorkflowState,
    attempt: ToolNamePlanAttempt,
    *,
    call_id: str,
) -> ServerBoundToolDecision:
    """Validate a proposed name and derive all call arguments on the server."""

    expected_name, arguments = _expected_call(state)
    proposed_name = attempt.proposed_name
    planner_error_category = None
    if attempt.error_category is not None or proposed_name is None:
        accepted = False
        fallback_reason = ToolDecisionFallbackReason.PLANNER_ERROR
        planner_error_category = attempt.error_category or "missing_tool_name"
    else:
        try:
            parsed_name = ToolName(proposed_name)
        except ValueError:
            accepted = False
            fallback_reason = ToolDecisionFallbackReason.UNKNOWN_TOOL
        else:
            accepted = parsed_name == expected_name
            fallback_reason = (
                None if accepted else ToolDecisionFallbackReason.STAGE_MISMATCH
            )

    return ServerBoundToolDecision(
        expected_name=expected_name,
        proposed_name=proposed_name,
        proposal_accepted=accepted,
        fallback_reason=fallback_reason,
        planner_error_category=planner_error_category,
        call=ToolCallRequest(
            call_id=call_id,
            name=expected_name.value,
            arguments=arguments,
        ),
    )


def _expected_call(state: ShadowWorkflowState) -> tuple[ToolName, dict[str, Any]]:
    if state.stage == ShadowWorkflowStage.START:
        return ToolName.RESOLVE_MEDICATIONS, {"question": state.question.strip()}
    if state.stage == ShadowWorkflowStage.AFTER_RESOLUTION:
        if state.resolution_status == InputResolutionStatus.RESOLVED:
            name = ToolName.QUERY_SAFETY_GRAPH
        else:
            name = ToolName.REQUEST_CLARIFICATION
        return name, {"resolution_call_id": state.artifact_call_id}
    return ToolName.RENDER_EVIDENCE_EXPLANATION, {
        "packet_call_id": state.artifact_call_id,
        "use_llm_plan": state.use_llm_plan,
    }
