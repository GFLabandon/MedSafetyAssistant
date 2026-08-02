"""Application service joining input resolution, safety rules, and explanation."""

from __future__ import annotations

from time import perf_counter

from medsafety.contracts import (
    ConclusionStatus,
    EvidencePacket,
    InputResolution,
    InputResolutionStatus,
    PipelineStageTrace,
    RequestTrace,
    SafetyQueryResponse,
)
from medsafety.entity_resolution import V1EntityResolver
from medsafety.explanation import EvidenceGroundedExplainer
from medsafety.observability import normalize_request_id
from medsafety.repositories import KnowledgeUnavailableError
from medsafety.safety_engine import SafetyEngine


class SafetyQueryService:
    def __init__(
        self,
        resolver: V1EntityResolver,
        engine: SafetyEngine,
        explainer: EvidenceGroundedExplainer,
    ):
        self._resolver = resolver
        self._engine = engine
        self._explainer = explainer

    def query(
        self,
        question: str,
        *,
        use_llm_plan: bool = True,
        request_id: str | None = None,
    ) -> SafetyQueryResponse:
        request_started = perf_counter()

        stage_started = perf_counter()
        resolution = self._resolver.resolve(question)
        stages = [
            PipelineStageTrace(
                name="entity_resolution",
                status="completed",
                duration_ms=self._elapsed_ms(stage_started),
            )
        ]

        if resolution.status == InputResolutionStatus.RESOLVED:
            stage_started = perf_counter()
            packet = self._engine.assess(
                resolution.medications,
                contexts=resolution.contexts,
            )
            engine_status = (
                "degraded"
                if packet.conclusion_status == ConclusionStatus.KNOWLEDGE_UNAVAILABLE
                else "completed"
            )
            stages.append(
                PipelineStageTrace(
                    name="safety_engine",
                    status=engine_status,
                    duration_ms=self._elapsed_ms(stage_started),
                )
            )
            if (
                packet.conclusion_status == ConclusionStatus.INSUFFICIENT_INFORMATION
                and packet.missing_context
            ):
                resolution = resolution.model_copy(
                    update={
                        "status": InputResolutionStatus.NEEDS_CLARIFICATION,
                        "clarification_question": (
                            "请补充以下判断条件："
                            + "、".join(packet.missing_context)
                            + "。"
                        ),
                    }
                )
        else:
            packet = packet_for_unresolved_input(resolution, self._engine)
            stages.append(
                PipelineStageTrace(
                    name="safety_engine",
                    status="skipped",
                    duration_ms=0,
                )
            )

        stage_started = perf_counter()
        explanation = self._explainer.explain(packet, use_llm_plan=use_llm_plan)
        explanation_status = (
            "degraded"
            if explanation.generation_mode.value == "deterministic_fallback"
            or explanation.conclusion_status == ConclusionStatus.KNOWLEDGE_UNAVAILABLE
            else "completed"
        )
        stages.append(
            PipelineStageTrace(
                name="evidence_explanation",
                status=explanation_status,
                duration_ms=self._elapsed_ms(stage_started),
            )
        )
        trace = RequestTrace(
            request_id=normalize_request_id(request_id),
            total_duration_ms=self._elapsed_ms(request_started),
            stages=stages,
            resolution_status=resolution.status,
            conclusion_status=explanation.conclusion_status,
        )
        return SafetyQueryResponse(
            resolution=resolution,
            explanation=explanation,
            trace=trace,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((perf_counter() - started) * 1000, 3)


def packet_for_unresolved_input(
    resolution: InputResolution,
    engine: SafetyEngine,
) -> EvidencePacket:
    """Create a deterministic non-risk packet for unresolved input."""

    try:
        data_version = engine.repository.data_version
    except KnowledgeUnavailableError:
        return EvidencePacket(
            conclusion_status=ConclusionStatus.KNOWLEDGE_UNAVAILABLE,
            limitations=["用药安全知识库当前不可用，系统未进行风险判断，请稍后重试。"],
            unresolved_inputs=list(resolution.unresolved_mentions),
            data_version=None,
        )

    if resolution.status == InputResolutionStatus.UNKNOWN:
        return EvidencePacket(
            conclusion_status=ConclusionStatus.OUT_OF_SCOPE,
            limitations=["未识别到当前来源对齐目录中的药品，系统未进行风险判断。"],
            unresolved_inputs=list(resolution.unresolved_mentions),
            data_version=data_version,
        )

    return EvidencePacket(
        conclusion_status=ConclusionStatus.INSUFFICIENT_INFORMATION,
        limitations=[
            resolution.clarification_question
            or "输入信息不足，系统未进行风险判断。"
        ],
        resolved_medications=list(resolution.medications),
        unresolved_inputs=list(resolution.unresolved_mentions),
        resolved_contexts=list(resolution.contexts),
        data_version=data_version,
    )
