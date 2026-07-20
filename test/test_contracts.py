from datetime import date, datetime

import pytest
from pydantic import ValidationError

from medsafety.contracts import (
    ConclusionStatus,
    EvidencePacket,
    FactRecord,
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
