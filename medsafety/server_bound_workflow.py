"""Bounded typed workflow using name-only model proposals and safe fallback."""

from __future__ import annotations

from typing import Protocol
from time import perf_counter

from pydantic import BaseModel

from medsafety.contracts import (
    EvidencePacket,
    InputResolution,
    InputResolutionStatus,
    SafetyExplanation,
)
from medsafety.entity_resolution import V1EntityResolver
from medsafety.explanation import EvidenceGroundedExplainer
from medsafety.observability import normalize_request_id
from medsafety.safety_engine import SafetyEngine
from medsafety.server_bound_tool_decisions import (
    ServerBoundToolDecisionTrace,
    ServerBoundWorkflowResponse,
    ToolNamePlanAttempt,
    bind_server_tool_decision,
)
from medsafety.tool_contracts import (
    ToolCallStatus,
    ToolCallTrace,
    ToolDefinition,
    ToolWorkflowTrace,
)
from medsafety.tool_shadow_contracts import ShadowWorkflowState
from medsafety.tool_workflow import (
    DEFAULT_MAX_TOOL_STEPS,
    ToolWorkflowExecutionError,
    TypedSafetyWorkflow,
)


class ToolNamePlanner(Protocol):
    prompt_version: str

    def propose(
        self,
        state: ShadowWorkflowState,
        definitions: list[ToolDefinition],
    ) -> ToolNamePlanAttempt: ...


class ServerBoundSafetyWorkflow:
    """Execute only server-derived calls after validating each model tool name."""

    def __init__(
        self,
        resolver: V1EntityResolver,
        engine: SafetyEngine,
        explainer: EvidenceGroundedExplainer,
        planner: ToolNamePlanner,
        *,
        max_steps: int = DEFAULT_MAX_TOOL_STEPS,
    ):
        if not 1 <= max_steps <= 8:
            raise ValueError("max_steps must be between 1 and 8")
        self._max_steps = max_steps
        self._planner = planner
        self._workflow = TypedSafetyWorkflow(
            resolver=resolver,
            engine=engine,
            explainer=explainer,
            max_steps=max_steps,
        )
        self.registry = self._workflow.registry

    def run(
        self,
        question: str,
        *,
        use_llm_plan: bool = True,
        request_id: str | None = None,
    ) -> ServerBoundWorkflowResponse:
        started = perf_counter()
        traces: list[ToolCallTrace] = []
        decisions: list[ServerBoundToolDecisionTrace] = []
        artifacts: dict[str, BaseModel] = {}
        definitions = self.registry.definitions()

        resolution = self._invoke(
            ShadowWorkflowState(stage="start", question=question),
            definitions,
            traces,
            decisions,
            artifacts,
            InputResolution,
        )
        packet = self._invoke(
            ShadowWorkflowState(
                stage="after_resolution",
                artifact_call_id=traces[-1].call_id,
                resolution_status=resolution.status,
            ),
            definitions,
            traces,
            decisions,
            artifacts,
            EvidencePacket,
        )
        explanation = self._invoke(
            ShadowWorkflowState(
                stage="after_evidence",
                artifact_call_id=traces[-1].call_id,
                use_llm_plan=use_llm_plan,
            ),
            definitions,
            traces,
            decisions,
            artifacts,
            SafetyExplanation,
        )
        trace = ToolWorkflowTrace(
            request_id=normalize_request_id(request_id),
            max_steps=self._max_steps,
            executed_steps=len(traces),
            total_duration_ms=self._elapsed_ms(started),
            tool_calls=traces,
            resolution_status=resolution.status,
            conclusion_status=explanation.conclusion_status,
        )
        return ServerBoundWorkflowResponse(
            resolution=resolution,
            explanation=explanation,
            trace=trace,
            decisions=decisions,
        )

    def _invoke(
        self,
        state: ShadowWorkflowState,
        definitions: list[ToolDefinition],
        traces: list[ToolCallTrace],
        decisions: list[ServerBoundToolDecisionTrace],
        artifacts: dict[str, BaseModel],
        output_model: type[BaseModel],
    ) -> BaseModel:
        if len(traces) >= self._max_steps:
            raise ToolWorkflowExecutionError("step_limit_exceeded", traces)
        call_id = f"tool-{len(traces) + 1:02d}"
        attempt = self._planner.propose(state, definitions)
        decision = bind_server_tool_decision(state, attempt, call_id=call_id)
        outcome = self.registry.execute(decision.call, artifacts=artifacts)
        traces.append(outcome.trace)
        decisions.append(
            ServerBoundToolDecisionTrace(
                call_id=call_id,
                expected_name=decision.expected_name,
                proposed_name=decision.proposed_name,
                proposal_accepted=decision.proposal_accepted,
                fallback_reason=decision.fallback_reason,
                planner_error_category=decision.planner_error_category,
                planner_latency_ms=attempt.latency_ms,
                argument_keys=sorted(decision.call.arguments),
            )
        )
        if outcome.trace.status != ToolCallStatus.COMPLETED or outcome.output is None:
            reason = outcome.trace.failure_reason
            code = reason.value if reason is not None else "tool_execution_failed"
            raise ToolWorkflowExecutionError(code, traces)
        if not isinstance(outcome.output, output_model):
            raise ToolWorkflowExecutionError("invalid_output", traces)
        artifacts[call_id] = outcome.output
        return outcome.output

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((perf_counter() - started) * 1000, 3)
