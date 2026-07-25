"""Bounded typed-tool orchestration for the evidence-grounded safety flow.

The registry is the trust boundary for controller calls: a tool name must be
registered and its arguments must pass a strict Pydantic schema before any
handler can run. A future model may propose a registered name, but server-held
artifacts remain the only way to pass domain objects between tools. This first
version uses a deterministic controller; it does not give an LLM an execution
loop or permit generated Cypher.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from pydantic import BaseModel, ValidationError

from medsafety.contracts import (
    EvidencePacket,
    InputResolution,
    InputResolutionStatus,
    SafetyExplanation,
)
from medsafety.entity_resolution import V1EntityResolver
from medsafety.explanation import EvidenceGroundedExplainer
from medsafety.observability import normalize_request_id
from medsafety.query_service import packet_for_unresolved_input
from medsafety.safety_engine import SafetyEngine
from medsafety.tool_contracts import (
    QuerySafetyGraphArguments,
    RenderEvidenceExplanationArguments,
    RequestClarificationArguments,
    ResolveMedicationsArguments,
    ToolCallRequest,
    ToolCallStatus,
    ToolCallTrace,
    ToolDefinition,
    ToolFailureReason,
    ToolName,
    ToolWorkflowResponse,
    ToolWorkflowTrace,
)


DEFAULT_MAX_TOOL_STEPS = 4


@dataclass(frozen=True)
class TypedToolSpec:
    name: ToolName
    description: str
    arguments_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[BaseModel, Mapping[str, BaseModel]], BaseModel | dict]


@dataclass(frozen=True)
class ToolExecutionOutcome:
    trace: ToolCallTrace
    output: BaseModel | None


class TypedToolRegistry:
    """Validate every controller call before dispatch and result before release.

    A future model may propose a registered tool name, but domain objects move
    between tools only as server-held artifact references. The model cannot
    supply an EvidencePacket or entity-resolution result directly.
    """

    def __init__(self, specs: list[TypedToolSpec]):
        self._specs: dict[str, TypedToolSpec] = {}
        for spec in specs:
            if spec.name.value in self._specs:
                raise ValueError(f"duplicate tool registration: {spec.name.value}")
            self._specs[spec.name.value] = spec

    def definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=spec.name,
                description=spec.description,
                input_schema=spec.arguments_model.model_json_schema(),
                output_schema=spec.output_model.model_json_schema(),
            )
            for spec in self._specs.values()
        ]

    def execute(
        self,
        call: ToolCallRequest,
        *,
        artifacts: Mapping[str, BaseModel] | None = None,
    ) -> ToolExecutionOutcome:
        started = perf_counter()
        argument_keys = sorted(call.arguments)
        spec = self._specs.get(call.name)
        if spec is None:
            return self._failure(
                call,
                started,
                argument_keys,
                status=ToolCallStatus.REJECTED,
                reason=ToolFailureReason.UNKNOWN_TOOL,
            )

        try:
            arguments = spec.arguments_model.model_validate(call.arguments)
        except ValidationError:
            return self._failure(
                call,
                started,
                argument_keys,
                status=ToolCallStatus.REJECTED,
                reason=ToolFailureReason.INVALID_ARGUMENTS,
            )

        try:
            raw_output = spec.handler(arguments, artifacts or {})
        except ToolArtifactReferenceError:
            return self._failure(
                call,
                started,
                argument_keys,
                status=ToolCallStatus.REJECTED,
                reason=ToolFailureReason.INVALID_ARTIFACT_REFERENCE,
            )
        except Exception:
            return self._failure(
                call,
                started,
                argument_keys,
                status=ToolCallStatus.FAILED,
                reason=ToolFailureReason.TOOL_EXECUTION_FAILED,
            )

        try:
            output = spec.output_model.model_validate(raw_output)
        except (ValidationError, TypeError, ValueError):
            return self._failure(
                call,
                started,
                argument_keys,
                status=ToolCallStatus.FAILED,
                reason=ToolFailureReason.INVALID_OUTPUT,
            )

        return ToolExecutionOutcome(
            trace=ToolCallTrace(
                call_id=call.call_id,
                tool_name=call.name,
                status=ToolCallStatus.COMPLETED,
                duration_ms=self._elapsed_ms(started),
                argument_keys=argument_keys,
                output_schema=spec.output_model.__name__,
            ),
            output=output,
        )

    @staticmethod
    def _failure(
        call: ToolCallRequest,
        started: float,
        argument_keys: list[str],
        *,
        status: ToolCallStatus,
        reason: ToolFailureReason,
    ) -> ToolExecutionOutcome:
        return ToolExecutionOutcome(
            trace=ToolCallTrace(
                call_id=call.call_id,
                tool_name=call.name,
                status=status,
                duration_ms=TypedToolRegistry._elapsed_ms(started),
                argument_keys=argument_keys,
                failure_reason=reason,
            ),
            output=None,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((perf_counter() - started) * 1000, 3)


class ToolWorkflowExecutionError(RuntimeError):
    """Stable, non-sensitive failure exposed by the bounded workflow."""

    def __init__(self, code: str, traces: list[ToolCallTrace]):
        super().__init__(code)
        self.code = code
        self.traces = tuple(traces)


class ToolArtifactReferenceError(ValueError):
    """Raised before domain execution when a call references invalid state."""


class TypedSafetyWorkflow:
    """Execute exactly one bounded deterministic safety workflow."""

    def __init__(
        self,
        resolver: V1EntityResolver,
        engine: SafetyEngine,
        explainer: EvidenceGroundedExplainer,
        *,
        max_steps: int = DEFAULT_MAX_TOOL_STEPS,
    ):
        if not 1 <= max_steps <= 8:
            raise ValueError("max_steps must be between 1 and 8")
        self._resolver = resolver
        self._engine = engine
        self._explainer = explainer
        self._max_steps = max_steps
        self.registry = TypedToolRegistry(self._tool_specs())

    def run(
        self,
        question: str,
        *,
        use_llm_plan: bool = True,
        request_id: str | None = None,
    ) -> ToolWorkflowResponse:
        started = perf_counter()
        traces: list[ToolCallTrace] = []
        artifacts: dict[str, BaseModel] = {}

        resolution = self._invoke(
            traces,
            artifacts,
            ToolName.RESOLVE_MEDICATIONS,
            {"question": question},
            InputResolution,
        )
        if resolution.status == InputResolutionStatus.RESOLVED:
            packet = self._invoke(
                traces,
                artifacts,
                ToolName.QUERY_SAFETY_GRAPH,
                {
                    "resolution_call_id": traces[-1].call_id,
                },
                EvidencePacket,
            )
        else:
            packet = self._invoke(
                traces,
                artifacts,
                ToolName.REQUEST_CLARIFICATION,
                {"resolution_call_id": traces[-1].call_id},
                EvidencePacket,
            )

        explanation = self._invoke(
            traces,
            artifacts,
            ToolName.RENDER_EVIDENCE_EXPLANATION,
            {
                "packet_call_id": traces[-1].call_id,
                "use_llm_plan": use_llm_plan,
            },
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
        return ToolWorkflowResponse(
            resolution=resolution,
            explanation=explanation,
            trace=trace,
        )

    def _invoke(
        self,
        traces: list[ToolCallTrace],
        artifacts: dict[str, BaseModel],
        name: ToolName,
        arguments: dict,
        output_model: type[BaseModel],
    ) -> BaseModel:
        if len(traces) >= self._max_steps:
            raise ToolWorkflowExecutionError("step_limit_exceeded", traces)
        call = ToolCallRequest(
            call_id=f"tool-{len(traces) + 1:02d}",
            name=name.value,
            arguments=arguments,
        )
        outcome = self.registry.execute(call, artifacts=artifacts)
        traces.append(outcome.trace)
        if outcome.trace.status != ToolCallStatus.COMPLETED or outcome.output is None:
            reason = outcome.trace.failure_reason
            code = reason.value if reason is not None else "tool_execution_failed"
            raise ToolWorkflowExecutionError(code, traces)
        if not isinstance(outcome.output, output_model):
            raise ToolWorkflowExecutionError("invalid_output", traces)
        artifacts[call.call_id] = outcome.output
        return outcome.output

    def _tool_specs(self) -> list[TypedToolSpec]:
        return [
            TypedToolSpec(
                name=ToolName.RESOLVE_MEDICATIONS,
                description=(
                    "Resolve catalog-backed medication and context entities from one "
                    "question without creating new medical entities."
                ),
                arguments_model=ResolveMedicationsArguments,
                output_model=InputResolution,
                handler=lambda arguments, _artifacts: self._resolver.resolve(
                    arguments.question
                ),
            ),
            TypedToolSpec(
                name=ToolName.QUERY_SAFETY_GRAPH,
                description=(
                    "Run the deterministic Safety Engine against the governed knowledge "
                    "repository; callers cannot provide Cypher."
                ),
                arguments_model=QuerySafetyGraphArguments,
                output_model=EvidencePacket,
                handler=self._query_safety_graph,
            ),
            TypedToolSpec(
                name=ToolName.REQUEST_CLARIFICATION,
                description=(
                    "Convert unresolved or ambiguous input into a bounded EvidencePacket "
                    "that requests clarification without making a risk claim."
                ),
                arguments_model=RequestClarificationArguments,
                output_model=EvidencePacket,
                handler=self._request_clarification,
            ),
            TypedToolSpec(
                name=ToolName.RENDER_EVIDENCE_EXPLANATION,
                description=(
                    "Render only claims already present in an EvidencePacket and apply "
                    "the existing server-side explanation guardrails."
                ),
                arguments_model=RenderEvidenceExplanationArguments,
                output_model=SafetyExplanation,
                handler=self._render_evidence_explanation,
            ),
        ]

    def _query_safety_graph(
        self,
        arguments: QuerySafetyGraphArguments,
        artifacts: Mapping[str, BaseModel],
    ) -> EvidencePacket:
        resolution = self._require_artifact(
            artifacts,
            arguments.resolution_call_id,
            InputResolution,
        )
        if resolution.status != InputResolutionStatus.RESOLVED:
            raise ToolArtifactReferenceError(
                "safety graph queries require a resolved input artifact"
            )
        return self._engine.assess(
            resolution.medications,
            contexts=resolution.contexts,
        )

    def _request_clarification(
        self,
        arguments: RequestClarificationArguments,
        artifacts: Mapping[str, BaseModel],
    ) -> EvidencePacket:
        resolution = self._require_artifact(
            artifacts,
            arguments.resolution_call_id,
            InputResolution,
        )
        if resolution.status == InputResolutionStatus.RESOLVED:
            raise ToolArtifactReferenceError(
                "clarification requires an unresolved input artifact"
            )
        return packet_for_unresolved_input(resolution, self._engine)

    def _render_evidence_explanation(
        self,
        arguments: RenderEvidenceExplanationArguments,
        artifacts: Mapping[str, BaseModel],
    ) -> SafetyExplanation:
        packet = self._require_artifact(
            artifacts,
            arguments.packet_call_id,
            EvidencePacket,
        )
        return self._explainer.explain(
            packet,
            use_llm_plan=arguments.use_llm_plan,
        )

    @staticmethod
    def _require_artifact(
        artifacts: Mapping[str, BaseModel],
        call_id: str,
        expected_model: type[BaseModel],
    ) -> BaseModel:
        artifact = artifacts.get(call_id)
        if not isinstance(artifact, expected_model):
            raise ToolArtifactReferenceError(
                f"{call_id} does not reference {expected_model.__name__}"
            )
        return artifact

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((perf_counter() - started) * 1000, 3)
