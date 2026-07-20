import json
from pathlib import Path

import pytest

from medsafety.catalog import CatalogValidationError, KnowledgeCatalog
from medsafety.contracts import ConclusionStatus, RiskType
from medsafety.safety_engine import SafetyEngine


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_DIRECTORY = REPOSITORY_ROOT / "data/v1"


@pytest.fixture(scope="module")
def catalog():
    return KnowledgeCatalog.from_directory(DATA_DIRECTORY)


@pytest.fixture(scope="module")
def engine(catalog):
    return SafetyEngine(catalog)


def test_catalog_loads_only_source_aligned_v1_records(catalog):
    assert catalog.data_version == "v1.0.0-alpha.1"
    assert len(catalog.sources) == 6
    assert len(catalog.medications) == 4
    assert len(catalog.facts) == 2


def test_catalog_loading_is_idempotent(catalog):
    second = KnowledgeCatalog.from_directory(DATA_DIRECTORY)

    assert second.data_version == catalog.data_version
    assert set(second.sources) == set(catalog.sources)
    assert set(second.medications) == set(catalog.medications)
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


def test_catalog_rejects_unknown_source_reference(tmp_path):
    for name in ("sources.json", "medications.json", "facts.json"):
        payload = json.loads((DATA_DIRECTORY / name).read_text(encoding="utf-8"))
        if name == "facts.json":
            payload[0]["source_ids"] = ["missing-source"]
        (tmp_path / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(CatalogValidationError, match="unknown sources"):
        KnowledgeCatalog.from_directory(tmp_path)
