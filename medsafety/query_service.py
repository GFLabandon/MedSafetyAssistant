"""Application service joining input resolution, safety rules, and explanation."""

from __future__ import annotations

from medsafety.contracts import (
    ConclusionStatus,
    EvidencePacket,
    InputResolution,
    InputResolutionStatus,
    SafetyQueryResponse,
)
from medsafety.entity_resolution import V1EntityResolver
from medsafety.explanation import EvidenceGroundedExplainer
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

    def query(self, question: str, *, use_llm_plan: bool = True) -> SafetyQueryResponse:
        resolution = self._resolver.resolve(question)

        if resolution.status == InputResolutionStatus.RESOLVED:
            packet = self._engine.assess(
                resolution.medications,
                contexts=resolution.contexts,
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
            packet = self._packet_for_unresolved_input(resolution)

        explanation = self._explainer.explain(packet, use_llm_plan=use_llm_plan)
        return SafetyQueryResponse(resolution=resolution, explanation=explanation)

    def _packet_for_unresolved_input(self, resolution: InputResolution) -> EvidencePacket:
        try:
            data_version = self._engine.repository.data_version
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
