"""Evidence-grounded explanation planning and deterministic rendering."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from pydantic import ValidationError

from medsafety.contracts import (
    ConclusionStatus,
    EvidenceFact,
    EvidencePacket,
    ExplanationClaim,
    ExplanationFallbackReason,
    ExplanationGenerationMode,
    ExplanationPlan,
    SafetyExplanation,
    Severity,
)


PROMPT_VERSION = "evidence-order-v1"
logger = logging.getLogger(__name__)


class ExplanationPlanner(Protocol):
    def plan(self, packet: EvidencePacket) -> ExplanationPlan | dict[str, Any]: ...


class InvalidExplanationPlan(ValueError):
    """Raised when a planner tries to change or incompletely cite evidence."""


_SEVERITY_PRIORITY = {
    Severity.FATAL: 0,
    Severity.RED: 1,
    Severity.ORANGE: 2,
    Severity.INFO: 3,
}


_SUMMARY_BY_STATUS = {
    ConclusionStatus.NO_KNOWN_RISK_IN_SCOPE: (
        "当前来源对齐目录内未命中已收录风险；这不代表该药品或组合安全。"
    ),
    ConclusionStatus.INSUFFICIENT_INFORMATION: (
        "现有信息不足，系统未作完整风险判断，请先补充缺失信息。"
    ),
    ConclusionStatus.OUT_OF_SCOPE: (
        "部分或全部输入超出当前来源对齐目录，系统未作完整风险判断。"
    ),
    ConclusionStatus.KNOWLEDGE_UNAVAILABLE: (
        "用药安全知识库当前不可用，系统未进行风险判断，请稍后重试。"
    ),
}


class EvidenceGroundedExplainer:
    """Let an LLM order evidence, but never author a medical claim."""

    def __init__(self, planner: ExplanationPlanner | None = None):
        self.planner = planner

    def explain(self, packet: EvidencePacket, *, use_llm_plan: bool = True) -> SafetyExplanation:
        ordered_facts = self._deterministic_order(packet.facts)
        mode = ExplanationGenerationMode.DETERMINISTIC
        fallback_reason = None

        if use_llm_plan and packet.facts:
            if self.planner is None:
                mode = ExplanationGenerationMode.DETERMINISTIC_FALLBACK
                fallback_reason = ExplanationFallbackReason.PLANNER_UNAVAILABLE
            else:
                try:
                    plan = ExplanationPlan.model_validate(self.planner.plan(packet))
                    ordered_facts = self._validate_and_apply_plan(packet, plan)
                    mode = ExplanationGenerationMode.LLM_PLANNED
                except (InvalidExplanationPlan, ValidationError, TypeError, ValueError) as exc:
                    logger.info(
                        "explanation planner returned an invalid plan (%s)",
                        type(exc).__name__,
                    )
                    mode = ExplanationGenerationMode.DETERMINISTIC_FALLBACK
                    fallback_reason = ExplanationFallbackReason.INVALID_PLAN
                except Exception as exc:
                    logger.warning(
                        "explanation planner unavailable (%s)",
                        type(exc).__name__,
                    )
                    logger.debug("explanation planner failure detail", exc_info=True)
                    mode = ExplanationGenerationMode.DETERMINISTIC_FALLBACK
                    fallback_reason = ExplanationFallbackReason.PLANNER_UNAVAILABLE

        claims = [self._claim_from_fact(fact) for fact in ordered_facts]
        prompt_version = getattr(self.planner, "prompt_version", PROMPT_VERSION)
        return SafetyExplanation(
            conclusion_status=packet.conclusion_status,
            summary=self._summary(packet, len(claims)),
            claims=claims,
            limitations=list(packet.limitations),
            resolved_medications=list(packet.resolved_medications),
            unresolved_inputs=list(packet.unresolved_inputs),
            resolved_contexts=list(packet.resolved_contexts),
            unresolved_contexts=list(packet.unresolved_contexts),
            missing_context=list(packet.missing_context),
            data_version=packet.data_version,
            generation_mode=mode,
            prompt_version=prompt_version,
            fallback_reason=fallback_reason,
        )

    @staticmethod
    def _validate_and_apply_plan(
        packet: EvidencePacket,
        plan: ExplanationPlan,
    ) -> list[EvidenceFact]:
        if plan.conclusion_status != packet.conclusion_status:
            raise InvalidExplanationPlan("planner changed the conclusion status")

        expected_ids = [fact.fact_id for fact in packet.facts]
        planned_ids = plan.ordered_fact_ids
        if len(planned_ids) != len(set(planned_ids)):
            raise InvalidExplanationPlan("planner returned duplicate fact IDs")
        if set(planned_ids) != set(expected_ids):
            raise InvalidExplanationPlan("planner omitted or invented fact IDs")

        by_id = {fact.fact_id: fact for fact in packet.facts}
        return [by_id[fact_id] for fact_id in planned_ids]

    @staticmethod
    def _deterministic_order(facts: list[EvidenceFact]) -> list[EvidenceFact]:
        return sorted(
            facts,
            key=lambda fact: (_SEVERITY_PRIORITY[fact.severity], fact.fact_id),
        )

    @staticmethod
    def _claim_from_fact(fact: EvidenceFact) -> ExplanationClaim:
        return ExplanationClaim(
            fact_id=fact.fact_id,
            risk_type=fact.risk_type,
            severity=fact.severity,
            statement=fact.reason,
            severity_rationale=fact.severity_rationale,
            source_ids=list(fact.source_ids),
            source_locator=fact.source_locator,
            label_status=fact.label_status,
        )

    @staticmethod
    def _summary(packet: EvidencePacket, claim_count: int) -> str:
        if packet.conclusion_status == ConclusionStatus.RISK_FOUND:
            return f"在当前来源对齐数据范围内发现 {claim_count} 条需要关注的用药风险。"
        return _SUMMARY_BY_STATUS[packet.conclusion_status]
