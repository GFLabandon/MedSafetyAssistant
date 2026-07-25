import json
from datetime import date, datetime
from pathlib import Path

import pytest

from medsafety.catalog import CatalogValidationError, KnowledgeCatalog
from medsafety.contracts import (
    ClinicalContextRecord,
    ConclusionStatus,
    ContextKind,
    FactRecord,
    KnowledgeEntityKind,
    LabelStatus,
    ReviewStatus,
    RiskType,
    Severity,
    SourceRecord,
)
from medsafety.safety_engine import SafetyEngine
from medsafety.repositories import KnowledgeUnavailableError


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_DIRECTORY = REPOSITORY_ROOT / "data/v1"


@pytest.fixture(scope="module")
def catalog():
    return KnowledgeCatalog.from_directory(DATA_DIRECTORY)


@pytest.fixture(scope="module")
def engine(catalog):
    return SafetyEngine(catalog)


def test_catalog_loads_only_source_aligned_v1_records(catalog):
    assert catalog.data_version == "v1.0.0-alpha.3"
    assert len(catalog.sources) == 8
    assert len(catalog.medications) == 5
    assert len(catalog.contexts) == 2
    assert len(catalog.facts) == 3


def test_catalog_loading_is_idempotent(catalog):
    second = KnowledgeCatalog.from_directory(DATA_DIRECTORY)

    assert second.data_version == catalog.data_version
    assert set(second.sources) == set(catalog.sources)
    assert set(second.medications) == set(catalog.medications)
    assert set(second.contexts) == set(catalog.contexts)
    assert set(second.facts) == set(catalog.facts)


def test_tyno_and_gankang_return_source_backed_duplicate_ingredient_risk(engine):
    result = engine.assess(["泰诺", "感康"])

    assert result.conclusion_status == ConclusionStatus.RISK_FOUND
    assert result.resolved_medications == ["泰诺", "感康"]
    assert len(result.facts) == 1
    assert result.facts[0].fact_id == "fact-duplicate-acetaminophen-001"
    assert result.facts[0].risk_type == RiskType.DUPLICATE_THERAPY
    assert "source-fda-acetaminophen-2025" in result.facts[0].source_ids
    assert "source-shanghai-mpa-2021-176" in result.facts[0].source_ids
    assert "source-hohhot-procurement-2025" in result.facts[0].source_ids


@pytest.mark.parametrize("alias", ["paracetamol", "PARACETAMOL", "acetaminophen"])
def test_source_aligned_acetaminophen_aliases_resolve(alias, catalog):
    medication = catalog.resolve_medication(alias)

    assert medication is not None
    assert medication.medication_id == "medication-acetaminophen-substance"
    assert medication.canonical_name == "对乙酰氨基酚"


def test_unverified_colloquial_acetaminophen_alias_is_not_admitted(catalog):
    assert catalog.resolve_medication("扑热息痛") is None


def test_paracetamol_and_tyno_return_duplicate_ingredient_risk(engine):
    result = engine.assess(["paracetamol", "泰诺"])

    assert result.conclusion_status == ConclusionStatus.RISK_FOUND
    assert result.resolved_medications == ["对乙酰氨基酚", "泰诺"]
    assert [fact.fact_id for fact in result.facts] == [
        "fact-duplicate-acetaminophen-001"
    ]
    assert "source-nhc-essential-medicines-2018" in result.facts[0].source_ids


def test_ibuprofen_and_aspirin_require_cardioprotection_context(engine):
    result = engine.assess(["布洛芬", "阿司匹林"])

    assert result.conclusion_status == ConclusionStatus.INSUFFICIENT_INFORMATION
    assert result.facts == []
    assert result.missing_context == ["阿司匹林用于心血管保护"]


def test_ibuprofen_and_aspirin_return_conditional_interaction_when_context_is_present(engine):
    result = engine.assess(
        ["ibuprofen", "aspirin"],
        contexts=["阿司匹林用于心血管保护"],
    )

    assert result.conclusion_status == ConclusionStatus.RISK_FOUND
    assert result.facts[0].fact_id == "fact-interaction-ibuprofen-aspirin-cardioprotection-001"
    assert result.facts[0].risk_type == RiskType.INTERACTION


def test_known_single_medication_never_claims_safety(engine):
    result = engine.assess(["泰诺"])

    assert result.conclusion_status == ConclusionStatus.NO_KNOWN_RISK_IN_SCOPE
    assert result.facts == []
    assert any("不代表" in limitation for limitation in result.limitations)


def test_unknown_medication_is_out_of_scope(engine):
    result = engine.assess(["星云片"])

    assert result.conclusion_status == ConclusionStatus.OUT_OF_SCOPE
    assert result.unresolved_inputs == ["星云片"]


def test_ibuprofen_contraindication_requires_explicit_nsaid_reaction_history(engine):
    result = engine.assess(["布洛芬"], contexts=["NSAID过敏"])

    assert result.conclusion_status == ConclusionStatus.RISK_FOUND
    assert result.resolved_contexts == [
        "服用阿司匹林或其他NSAID后出现哮喘、荨麻疹或过敏反应"
    ]
    assert result.facts[0].fact_id == (
        "fact-contraindication-ibuprofen-nsaid-allergic-reaction-001"
    )
    assert result.facts[0].risk_type == RiskType.CONTRAINDICATION
    assert "source-dailymed-ibuprofen-amneal-2024" in result.facts[0].source_ids


def test_plain_asthma_does_not_expand_into_nsaid_reaction_history(engine):
    result = engine.assess(["布洛芬"], contexts=["哮喘"])

    assert result.conclusion_status == ConclusionStatus.OUT_OF_SCOPE
    assert result.facts == []
    assert result.resolved_contexts == []
    assert result.unresolved_contexts == ["哮喘"]


def _catalog_with_test_only_activity_restriction(catalog):
    source = SourceRecord(
        source_id="source-test-product-label",
        title="Test-only product label",
        publisher="Test fixture",
        url="https://example.invalid/test-product-label",
        accessed_at=date(2026, 7, 25),
        review_status=ReviewStatus.REVIEWED,
        reviewed_by="test-fixture",
        reviewed_at=datetime(2026, 7, 25, 12, 0),
    )
    activity = ClinicalContextRecord(
        context_id="context-driving-or-machinery",
        canonical_name="驾驶或操作机械",
        kind=ContextKind.ACTIVITY,
        aliases=["开车", "操作机械"],
        description="测试夹具：用户明确询问驾驶或机械操作。",
        review_status=ReviewStatus.REVIEWED,
        reviewed_by="test-fixture",
        reviewed_at=datetime(2026, 7, 25, 12, 0),
        data_version=catalog.data_version,
    )
    fact = FactRecord(
        fact_id="fact-test-tyno-activity-restriction",
        subject="泰诺",
        subject_kind=KnowledgeEntityKind.MEDICATION,
        predicate="ACTIVITY_RESTRICTION",
        object=activity.canonical_name,
        object_kind=KnowledgeEntityKind.CONTEXT,
        risk_type=RiskType.ACTIVITY_RESTRICTION,
        severity=Severity.ORANGE,
        severity_rationale="测试夹具分级，不是临床分级。",
        reason="测试夹具：该产品存在活动限制。",
        source_ids=[source.source_id],
        source_locator="测试说明书注意事项",
        review_status=ReviewStatus.REVIEWED,
        label_status=LabelStatus.SOURCE_ALIGNED,
        reviewed_by="test-fixture",
        reviewed_at=datetime(2026, 7, 25, 12, 0),
        data_version=catalog.data_version,
        required_context=[activity.canonical_name],
    )
    return KnowledgeCatalog(
        sources=[*catalog.sources.values(), source],
        medications=list(catalog.medications.values()),
        contexts=[*catalog.contexts.values(), activity],
        facts=[*catalog.facts.values(), fact],
    )


def test_product_activity_restriction_requires_explicit_activity_context(catalog):
    activity_catalog = _catalog_with_test_only_activity_restriction(catalog)
    activity_engine = SafetyEngine(activity_catalog)

    result = activity_engine.assess(["泰诺"], contexts=["开车"])

    assert result.conclusion_status == ConclusionStatus.RISK_FOUND
    assert result.resolved_contexts == ["驾驶或操作机械"]
    assert result.facts[0].fact_id == "fact-test-tyno-activity-restriction"
    assert result.facts[0].risk_type == RiskType.ACTIVITY_RESTRICTION

    no_context = activity_engine.assess(["泰诺"])
    assert no_context.conclusion_status == ConclusionStatus.NO_KNOWN_RISK_IN_SCOPE


def test_catalog_rejects_activity_restriction_on_substance_subject(catalog):
    activity_catalog = _catalog_with_test_only_activity_restriction(catalog)
    activity_fact = activity_catalog.facts[
        "fact-test-tyno-activity-restriction"
    ].model_copy(update={"subject": "对乙酰氨基酚"})

    with pytest.raises(
        CatalogValidationError,
        match="product-subject facts require a product medication record",
    ):
        KnowledgeCatalog(
            sources=list(activity_catalog.sources.values()),
            medications=list(activity_catalog.medications.values()),
            contexts=list(activity_catalog.contexts.values()),
            facts=[
                *(
                    fact
                    for fact_id, fact in activity_catalog.facts.items()
                    if fact_id != activity_fact.fact_id
                ),
                activity_fact,
            ],
        )


def test_catalog_rejects_unknown_source_reference(tmp_path):
    for name in ("sources.json", "medications.json", "contexts.json", "facts.json"):
        payload = json.loads((DATA_DIRECTORY / name).read_text(encoding="utf-8"))
        if name == "facts.json":
            payload[0]["source_ids"] = ["missing-source"]
        (tmp_path / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(CatalogValidationError, match="unknown sources"):
        KnowledgeCatalog.from_directory(tmp_path)


def test_catalog_rejects_unknown_required_context(tmp_path):
    for name in ("sources.json", "medications.json", "contexts.json", "facts.json"):
        payload = json.loads((DATA_DIRECTORY / name).read_text(encoding="utf-8"))
        if name == "facts.json":
            payload[0]["required_context"] = ["不存在的上下文"]
        (tmp_path / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(CatalogValidationError, match="unknown contexts"):
        KnowledgeCatalog.from_directory(tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("predicate", "UNSUPPORTED_RELATION", "unsupported predicate"),
        ("subject", "不存在的成分", "unknown subject ingredient"),
        ("object", "不存在的成分", "unknown object ingredient"),
    ],
)
def test_catalog_rejects_fact_endpoints_that_cannot_form_the_graph(
    tmp_path,
    field,
    value,
    message,
):
    for name in ("sources.json", "medications.json", "contexts.json", "facts.json"):
        payload = json.loads((DATA_DIRECTORY / name).read_text(encoding="utf-8"))
        if name == "facts.json":
            payload[0][field] = value
        (tmp_path / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(CatalogValidationError, match=message):
        KnowledgeCatalog.from_directory(tmp_path)


def test_catalog_rejects_duplicate_stable_ids(tmp_path):
    for name in ("sources.json", "medications.json", "contexts.json", "facts.json"):
        payload = json.loads((DATA_DIRECTORY / name).read_text(encoding="utf-8"))
        if name == "contexts.json":
            payload.append(payload[0])
        (tmp_path / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(CatalogValidationError, match="duplicate context id"):
        KnowledgeCatalog.from_directory(tmp_path)


def test_repository_failure_never_becomes_no_known_risk():
    class UnavailableRepository:
        @property
        def data_version(self):
            raise KnowledgeUnavailableError("private database detail")

        def resolve_medication(self, _value):
            raise KnowledgeUnavailableError("private database detail")

        def duplicate_fact_for(self, _ingredient):
            raise AssertionError("not reached")

        def interaction_facts_for(self, _left, _right):
            raise AssertionError("not reached")

    result = SafetyEngine(UnavailableRepository()).assess(["泰诺"])

    assert result.conclusion_status == ConclusionStatus.KNOWLEDGE_UNAVAILABLE
    assert result.data_version is None
    assert result.facts == []
    assert result.unresolved_inputs == ["泰诺"]
    assert "private database detail" not in " ".join(result.limitations)
