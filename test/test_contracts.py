from datetime import date, datetime

import pytest
from pydantic import ValidationError

from medsafety.contracts import (
    ClinicalContextRecord,
    ConclusionStatus,
    ContextKind,
    EvidencePacket,
    FactRecord,
    KnowledgeEntityKind,
    LabelStatus,
    ReviewStatus,
    RiskType,
    Severity,
    SourceRecord,
)


def test_reviewed_source_requires_traceability_metadata():
    with pytest.raises(ValidationError, match="reviewed sources require"):
        SourceRecord(
            source_id="source-1",
            title="Example label",
            review_status=ReviewStatus.REVIEWED,
        )

    source = SourceRecord(
        source_id="source-1",
        title="Example label",
        publisher="Example publisher",
        url="https://example.invalid/label",
        accessed_at=date(2026, 7, 20),
        review_status=ReviewStatus.REVIEWED,
        reviewed_by="reviewer-id",
        reviewed_at=datetime(2026, 7, 20, 12, 0),
    )
    assert source.review_status == ReviewStatus.REVIEWED


def test_reviewed_fact_requires_sources_locator_and_reviewer():
    with pytest.raises(ValidationError, match="reviewed facts require"):
        FactRecord(
            fact_id="fact-1",
            subject="药品甲",
            predicate="CONTRAINDICATED_IN",
            object="状态乙",
            risk_type=RiskType.CONTRAINDICATION,
            severity=Severity.RED,
            severity_rationale="测试分级策略",
            reason="测试原因",
            data_version="v1",
            review_status=ReviewStatus.REVIEWED,
        )

    fact = FactRecord(
        fact_id="fact-1",
        subject="药品甲",
        predicate="CONTRAINDICATED_IN",
        object="状态乙",
        risk_type=RiskType.CONTRAINDICATION,
        severity=Severity.RED,
        severity_rationale="测试分级策略",
        reason="测试原因",
        source_ids=["source-1"],
        source_locator="说明书禁忌章节",
        data_version="v1",
        review_status=ReviewStatus.REVIEWED,
        label_status=LabelStatus.SOURCE_ALIGNED,
        reviewed_by="reviewer-id",
        reviewed_at=datetime(2026, 7, 20, 12, 0),
    )
    assert fact.label_status == LabelStatus.SOURCE_ALIGNED
    assert fact.subject_kind == KnowledgeEntityKind.INGREDIENT
    assert fact.object_kind == KnowledgeEntityKind.CONTEXT


def test_activity_restriction_requires_product_to_context_shape():
    fact = FactRecord(
        fact_id="fact-activity-1",
        subject="测试产品",
        subject_kind=KnowledgeEntityKind.MEDICATION,
        predicate="ACTIVITY_RESTRICTION",
        object="驾驶或操作机械",
        object_kind=KnowledgeEntityKind.CONTEXT,
        risk_type=RiskType.ACTIVITY_RESTRICTION,
        severity=Severity.ORANGE,
        severity_rationale="测试分级策略",
        reason="测试原因",
        source_ids=["source-1"],
        source_locator="测试说明书注意事项",
        data_version="v1",
        required_context=["驾驶或操作机械"],
    )

    assert fact.subject_kind == KnowledgeEntityKind.MEDICATION
    assert fact.object_kind == KnowledgeEntityKind.CONTEXT

    with pytest.raises(ValidationError, match="incompatible endpoint kinds"):
        FactRecord(
            **{
                **fact.model_dump(),
                "subject_kind": KnowledgeEntityKind.INGREDIENT,
            }
        )

    with pytest.raises(ValidationError, match="incompatible risk type"):
        FactRecord(
            **{
                **fact.model_dump(),
                "risk_type": RiskType.CONTRAINDICATION,
            }
        )


def test_reviewed_context_requires_review_metadata():
    with pytest.raises(ValidationError, match="reviewed contexts require"):
        ClinicalContextRecord(
            context_id="context-1",
            canonical_name="明确上下文",
            kind=ContextKind.REACTION_HISTORY,
            description="只记录用户明确报告的反应史。",
            review_status=ReviewStatus.REVIEWED,
            data_version="v1",
        )


def test_risk_found_requires_evidence_facts():
    with pytest.raises(ValidationError, match="risk_found requires"):
        EvidencePacket(
            conclusion_status=ConclusionStatus.RISK_FOUND,
            data_version="v1",
        )


def test_non_risk_packet_can_be_empty_and_explain_limitations():
    packet = EvidencePacket(
        conclusion_status=ConclusionStatus.INSUFFICIENT_INFORMATION,
        limitations=["需要具体药品名称"],
        data_version="v1",
    )
    assert packet.facts == []


def test_only_knowledge_unavailable_can_omit_data_version():
    packet = EvidencePacket(
        conclusion_status=ConclusionStatus.KNOWLEDGE_UNAVAILABLE,
        limitations=["知识库不可用"],
    )

    assert packet.data_version is None

    with pytest.raises(ValidationError, match="require a data version"):
        EvidencePacket(
            conclusion_status=ConclusionStatus.NO_KNOWN_RISK_IN_SCOPE,
        )
