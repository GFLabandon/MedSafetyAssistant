"""Deterministic medication risk evaluation over source-aligned facts."""

from __future__ import annotations

import logging
from itertools import combinations

from medsafety.contracts import (
    ConclusionStatus,
    EvidenceFact,
    EvidencePacket,
    FactRecord,
    MedicationRecord,
)
from medsafety.repositories import KnowledgeRepository, KnowledgeUnavailableError


logger = logging.getLogger(__name__)


class SafetyEngine:
    def __init__(self, repository: KnowledgeRepository):
        self.repository = repository

    def assess(self, medication_names: list[str], contexts: list[str] | None = None) -> EvidencePacket:
        try:
            return self._assess(medication_names, contexts=contexts)
        except KnowledgeUnavailableError:
            logger.warning("safety knowledge repository unavailable", exc_info=True)
            return EvidencePacket(
                conclusion_status=ConclusionStatus.KNOWLEDGE_UNAVAILABLE,
                limitations=["用药安全知识库当前不可用，系统未进行风险判断，请稍后重试。"],
                unresolved_inputs=list(dict.fromkeys(medication_names)),
                data_version=None,
            )

    def _assess(
        self,
        medication_names: list[str],
        contexts: list[str] | None = None,
    ) -> EvidencePacket:
        context_set = {item.strip() for item in (contexts or []) if item.strip()}
        resolved: list[MedicationRecord] = []
        unresolved: list[str] = []
        seen_medication_ids: set[str] = set()

        for raw_name in medication_names:
            medication = self.repository.resolve_medication(raw_name)
            if medication is None:
                unresolved.append(raw_name)
            elif medication.medication_id not in seen_medication_ids:
                resolved.append(medication)
                seen_medication_ids.add(medication.medication_id)

        resolved_names = [item.canonical_name for item in resolved]
        if not resolved:
            return EvidencePacket(
                conclusion_status=ConclusionStatus.OUT_OF_SCOPE,
                limitations=["输入药品不在当前来源对齐目录中，系统未进行风险判断。"],
                resolved_medications=[],
                unresolved_inputs=unresolved or medication_names,
                data_version=self.repository.data_version,
            )

        evidence_by_fact_id: dict[str, EvidenceFact] = {}
        missing_context: set[str] = set()

        ingredient_owners: dict[str, list[MedicationRecord]] = {}
        for medication in resolved:
            for ingredient in set(medication.active_ingredients):
                ingredient_owners.setdefault(ingredient, []).append(medication)

        for ingredient, owners in ingredient_owners.items():
            if len(owners) < 2:
                continue
            fact = self.repository.duplicate_fact_for(ingredient)
            if fact:
                evidence_by_fact_id[fact.fact_id] = self._to_evidence(fact, owners)

        for left, right in combinations(resolved, 2):
            for fact in self.repository.interaction_facts_for(
                set(left.active_ingredients), set(right.active_ingredients)
            ):
                required = set(fact.required_context)
                if required and not required.issubset(context_set):
                    missing_context.update(required - context_set)
                    continue
                evidence_by_fact_id[fact.fact_id] = self._to_evidence(fact, [left, right])

        limitations = []
        if unresolved:
            limitations.append("部分输入不在当前来源对齐目录中，结果只覆盖已识别药品。")
        if missing_context:
            limitations.append("存在带条件的相互作用事实，需要补充药品用途后才能判断。")

        evidence = list(evidence_by_fact_id.values())
        if evidence:
            return EvidencePacket(
                conclusion_status=ConclusionStatus.RISK_FOUND,
                facts=evidence,
                limitations=limitations,
                resolved_medications=resolved_names,
                unresolved_inputs=unresolved,
                missing_context=sorted(missing_context),
                data_version=self.repository.data_version,
            )

        if missing_context:
            return EvidencePacket(
                conclusion_status=ConclusionStatus.INSUFFICIENT_INFORMATION,
                limitations=limitations,
                resolved_medications=resolved_names,
                unresolved_inputs=unresolved,
                missing_context=sorted(missing_context),
                data_version=self.repository.data_version,
            )

        if unresolved:
            return EvidencePacket(
                conclusion_status=ConclusionStatus.OUT_OF_SCOPE,
                limitations=limitations,
                resolved_medications=resolved_names,
                unresolved_inputs=unresolved,
                data_version=self.repository.data_version,
            )

        return EvidencePacket(
            conclusion_status=ConclusionStatus.NO_KNOWN_RISK_IN_SCOPE,
            limitations=["当前来源对齐目录内未命中风险；这不代表该药品或组合安全。"],
            resolved_medications=resolved_names,
            data_version=self.repository.data_version,
        )

    @staticmethod
    def _to_evidence(fact: FactRecord, medications: list[MedicationRecord]) -> EvidenceFact:
        source_ids = set(fact.source_ids)
        locators = [fact.source_locator]
        for medication in medications:
            source_ids.update(medication.source_ids)
            locators.append(medication.source_locator)
        return EvidenceFact(
            fact_id=fact.fact_id,
            subject=fact.subject,
            predicate=fact.predicate,
            object=fact.object,
            risk_type=fact.risk_type,
            severity=fact.severity,
            severity_rationale=fact.severity_rationale,
            reason=fact.reason,
            source_ids=sorted(source_ids),
            source_locator="；".join(dict.fromkeys(locators)),
            label_status=fact.label_status,
        )
