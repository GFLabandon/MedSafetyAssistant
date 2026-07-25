from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
from neo4j.exceptions import ServiceUnavailable

from medsafety.catalog import KnowledgeCatalog
from medsafety.contracts import ConclusionStatus
from medsafety.neo4j_repository import (
    Neo4jCatalogImporter,
    Neo4jKnowledgeRepository,
    Neo4jProjectionAuditor,
    ProjectionIntegrityError,
)
from medsafety.repositories import KnowledgeUnavailableError
from medsafety.safety_engine import SafetyEngine


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_DIRECTORY = REPOSITORY_ROOT / "data/v1"


class FakeResult:
    def __init__(self, records: list[dict[str, Any]] | None = None):
        self.records = records or []

    def consume(self):
        return None

    def single(self):
        return self.records[0] if self.records else None

    def __iter__(self):
        return iter(self.records)


class FakeSession:
    def __init__(
        self,
        calls: list[tuple[str, dict[str, Any]]],
        responder: Callable[[str, dict[str, Any]], list[dict[str, Any]]] | None = None,
    ):
        self.calls = calls
        self.responder = responder or (lambda _query, _parameters: [])

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def run(self, query: str, **parameters: Any):
        normalized_query = " ".join(query.split())
        self.calls.append((normalized_query, parameters))
        return FakeResult(self.responder(normalized_query, parameters))

    def execute_write(self, callback, *args):
        return callback(self, *args)


class FakeDriver:
    def __init__(
        self,
        responder: Callable[[str, dict[str, Any]], list[dict[str, Any]]] | None = None,
    ):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responder = responder

    def session(self, database=None):
        assert database in (None, "neo4j")
        return FakeSession(self.calls, self.responder)


def _valid_integrity_record(**overrides: int) -> dict[str, int]:
    record = {
        "sources": 9,
        "medications": 5,
        "medication_aliases": 11,
        "ingredients": 10,
        "contexts": 3,
        "context_aliases": 15,
        "facts": 4,
        "snapshots": 1,
        "ingredient_links": 12,
        "medication_alias_links": 11,
        "context_alias_links": 15,
        "support_links": 15,
        "subject_links": 4,
        "object_links": 4,
        "context_links": 3,
        "snapshot_links": 4,
        "mixed_version_nodes": 0,
        "invalid_snapshots": 0,
        "orphan_facts": 0,
        "subject_property_mismatches": 0,
        "object_property_mismatches": 0,
        "medication_ingredient_mismatches": 0,
        "support_reference_mismatches": 0,
        "context_reference_mismatches": 0,
        "medication_alias_mismatches": 0,
        "context_alias_mismatches": 0,
    }
    record.update(overrides)
    return record


def test_importer_is_parameterized_and_repeat_safe():
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)

    def responder(query: str, _parameters: dict[str, Any]):
        if "object_property_mismatches" in query:
            return [_valid_integrity_record()]
        return []

    driver = FakeDriver(responder)
    importer = Neo4jCatalogImporter(driver, database="neo4j")

    first = importer.import_catalog(catalog)
    first_call_count = len(driver.calls)
    second = importer.import_catalog(catalog)

    assert first == second
    assert first.data_version == "v1.0.0-alpha.4"
    assert first.sources == 9
    assert first.medications == 5
    assert first.medication_aliases == 11
    assert first.ingredients == 10
    assert first.contexts == 3
    assert first.context_aliases == 15
    assert first.facts == 4
    assert first.support_links == 15
    assert first.medication_alias_links == 11
    assert first.context_alias_links == 15
    assert first.subject_links == 4
    assert first.object_links == 4
    assert first.context_links == 3
    assert first.snapshot_links == 4
    assert first.integrity_verified is True
    assert len(driver.calls) == first_call_count * 2

    constraint_calls = [query for query, _ in driver.calls if query.startswith("CREATE CONSTRAINT")]
    data_calls = [(query, params) for query, params in driver.calls if not query.startswith("CREATE")]
    assert constraint_calls
    assert all("IF NOT EXISTS" in query for query in constraint_calls)
    reset_calls = [query for query, _ in data_calls if "DETACH DELETE" in query]
    assert len(reset_calls) == 2
    assert all("STARTS WITH 'Safety'" in query for query in reset_calls)
    upsert_calls = [
        (query, params)
        for query, params in data_calls
        if "DETACH DELETE" not in query and "object_property_mismatches" not in query
    ]
    assert all("MERGE" in query for query, _ in upsert_calls)

    medication_call = next(
        (query, params)
        for query, params in data_calls
        if "SafetyMedication {medication_id: $medication_id}" in query
    )
    assert "$properties" in medication_call[0]
    assert medication_call[1]["properties"]["canonical_name"] == "泰诺"
    assert "泰诺" not in medication_call[0]
    assert any("MERGE (fact)-[:SUBJECT]" in query for query, _ in data_calls)
    assert any("MERGE (fact)-[:OBJECT]" in query for query, _ in data_calls)
    assert any("MERGE (fact)-[:BELONGS_TO]" in query for query, _ in data_calls)


def test_importer_rejects_projection_integrity_failure_before_returning():
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)

    def responder(query: str, _parameters: dict[str, Any]):
        if "object_property_mismatches" in query:
            return [_valid_integrity_record(orphan_facts=1)]
        return []

    with pytest.raises(ProjectionIntegrityError, match="missing required relationships"):
        Neo4jCatalogImporter(FakeDriver(responder)).import_catalog(catalog)


def test_projection_auditor_reports_existing_projection_drift():
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)

    def responder(query: str, _parameters: dict[str, Any]):
        if "object_property_mismatches" in query:
            return [_valid_integrity_record(subject_links=2)]
        raise AssertionError(f"unexpected query: {query}")

    report = Neo4jProjectionAuditor(FakeDriver(responder)).audit(catalog)

    assert report.valid is False
    assert report.actual.subject_links == 2
    assert "projection counts do not match the canonical catalog" in report.issues


def test_neo4j_repository_reconstructs_strict_contracts_and_drives_engine():
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)
    tyno = catalog.medications["medication-tyno-cold-tablet-cn"].model_dump(mode="json")
    gankang = catalog.medications["medication-gankang-tablet-cn"].model_dump(mode="json")
    duplicate_fact = catalog.facts["fact-duplicate-acetaminophen-001"].model_dump(mode="json")

    def responder(query: str, parameters: dict[str, Any]):
        if "RETURN snapshot.data_version AS data_version" in query:
            return [{"data_version": catalog.data_version}]
        if "RETURN properties(medication)" in query:
            records = {"泰诺": tyno, "感康": gankang}
            medication = records.get(parameters["normalized_name"])
            if medication is None:
                return []
            return [
                {
                    "medication": {
                        **medication,
                        "canonical_name_normalized": parameters["normalized_name"],
                        "aliases_normalized": [],
                    }
                }
            ]
        if "DUPLICATE_INGREDIENT" in query:
            return [{"fact": duplicate_fact}]
        if "INTERACTS_WITH" in query:
            return []
        if "CONTRAINDICATED_IN" in query:
            return []
        raise AssertionError(f"unexpected query: {query}")

    driver = FakeDriver(responder)
    repository = Neo4jKnowledgeRepository(driver, database="neo4j")
    result = SafetyEngine(repository).assess(["泰诺", "感康"])

    assert result.conclusion_status == ConclusionStatus.RISK_FOUND
    assert result.data_version == catalog.data_version
    assert [fact.fact_id for fact in result.facts] == ["fact-duplicate-acetaminophen-001"]
    duplicate_query = next(
        query for query, _ in driver.calls if "predicate = 'DUPLICATE_INGREDIENT'" in query
    )
    assert "[:SUBJECT]->(subject:SafetyIngredient)" in duplicate_query
    assert "[:OBJECT]->(object:SafetyIngredient)" in duplicate_query
    assert "fact.subject = $ingredient" not in duplicate_query


def test_neo4j_interaction_query_traverses_fact_endpoints():
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)
    fact = catalog.facts[
        "fact-interaction-ibuprofen-aspirin-cardioprotection-001"
    ].model_dump(mode="json")

    def responder(query: str, _parameters: dict[str, Any]):
        if "predicate = 'INTERACTS_WITH'" in query:
            return [{"fact": fact}]
        if "RETURN snapshot.data_version AS data_version" in query:
            return [{"data_version": catalog.data_version}]
        raise AssertionError(f"unexpected query: {query}")

    driver = FakeDriver(responder)
    repository = Neo4jKnowledgeRepository(driver)

    facts = repository.interaction_facts_for({"布洛芬"}, {"阿司匹林"})

    assert [item.fact_id for item in facts] == [fact["fact_id"]]
    query, parameters = next(
        (query, parameters)
        for query, parameters in driver.calls
        if "predicate = 'INTERACTS_WITH'" in query
    )
    assert "subject.name IN $left" in query
    assert "object.name IN $right" in query
    assert "fact.subject IN $left" not in query
    assert parameters["snapshot_name"] == "source-aligned-v1"


def test_neo4j_repository_returns_none_for_unknown_medication():
    def responder(query: str, _parameters: dict[str, Any]):
        if "RETURN properties(medication)" in query:
            return []
        raise AssertionError(f"unexpected query: {query}")

    repository = Neo4jKnowledgeRepository(FakeDriver(responder))

    assert repository.resolve_medication("不存在") is None


def test_neo4j_repository_context_and_contraindication_drive_engine():
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)
    medication = catalog.medications["medication-ibuprofen-substance"].model_dump(mode="json")
    context = catalog.contexts["context-nsaid-allergic-reaction-history"].model_dump(
        mode="json"
    )
    fact = catalog.facts[
        "fact-contraindication-ibuprofen-nsaid-allergic-reaction-001"
    ].model_dump(mode="json")

    def responder(query: str, _parameters: dict[str, Any]):
        if "RETURN snapshot.data_version AS data_version" in query:
            return [{"data_version": catalog.data_version}]
        if "RETURN properties(medication)" in query:
            return [{"medication": medication}]
        if "RETURN properties(context)" in query:
            return [{"context": context}]
        if "CONTRAINDICATED_IN" in query:
            return [{"fact": fact}]
        raise AssertionError(f"unexpected query: {query}")

    driver = FakeDriver(responder)
    repository = Neo4jKnowledgeRepository(driver)
    result = SafetyEngine(repository).assess(["布洛芬"], contexts=["NSAID过敏"])

    assert result.conclusion_status == ConclusionStatus.RISK_FOUND
    assert result.facts[0].fact_id == fact["fact_id"]
    contraindication_query = next(
        query for query, _ in driver.calls if "predicate = 'CONTRAINDICATED_IN'" in query
    )
    assert "[:OBJECT]->(object:SafetyContext)" in contraindication_query
    assert "[:APPLIES_IN]->(object)" in contraindication_query
    assert "fact.object IN $contexts" not in contraindication_query


def test_neo4j_repository_returns_complete_fact_provenance():
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)
    fact = catalog.facts[
        "fact-interaction-ibuprofen-aspirin-cardioprotection-001"
    ].model_dump(mode="json")
    context = catalog.contexts["context-aspirin-cardioprotection"].model_dump(
        mode="json"
    )
    sources = [
        catalog.sources[source_id].model_dump(mode="json")
        for source_id in fact["source_ids"]
    ]

    def responder(query: str, parameters: dict[str, Any]):
        if "RETURN properties(fact) AS fact" in query and "subject_name" in query:
            assert parameters["fact_id"] == fact["fact_id"]
            return [
                    {
                        "fact": fact,
                        "subject_kind": "ingredient",
                        "subject_identifier": "布洛芬",
                        "subject_name": "布洛芬",
                    "object_kind": "ingredient",
                    "object_identifier": "阿司匹林",
                    "object_name": "阿司匹林",
                    "contexts": [context],
                    "sources": sources,
                    "snapshot_name": "source-aligned-v1",
                    "snapshot_data_version": catalog.data_version,
                }
            ]
        if "RETURN snapshot.data_version AS data_version" in query:
            return [{"data_version": catalog.data_version}]
        raise AssertionError(f"unexpected query: {query}")

    driver = FakeDriver(responder)
    provenance = Neo4jKnowledgeRepository(driver).fact_provenance(fact["fact_id"])

    assert provenance is not None
    assert provenance.schema_version == "fact-provenance-v2"
    assert provenance.subject.name == "布洛芬"
    assert provenance.object.name == "阿司匹林"
    assert [item.context_id for item in provenance.applies_in] == [
        "context-aspirin-cardioprotection"
    ]
    assert [item.source_id for item in provenance.sources] == fact["source_ids"]
    assert provenance.snapshot.data_version == catalog.data_version
    query = next(query for query, _ in driver.calls if "subject_name" in query)
    assert "SafetyFact {fact_id: $fact_id}" in query
    assert "[:SUPPORTED_BY]" in query


def test_neo4j_repository_rejects_incomplete_fact_provenance():
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)
    fact = catalog.facts["fact-duplicate-acetaminophen-001"].model_dump(mode="json")

    def responder(query: str, _parameters: dict[str, Any]):
        if "subject_name" in query:
            return [
                {
                    "fact": fact,
                    "subject_name": "对乙酰氨基酚",
                    "object_kind": "ingredient",
                    "object_identifier": "对乙酰氨基酚",
                    "object_name": "对乙酰氨基酚",
                    "contexts": [],
                    "sources": [],
                    "snapshot_name": "source-aligned-v1",
                    "snapshot_data_version": catalog.data_version,
                }
            ]
        raise AssertionError(f"unexpected query: {query}")

    with pytest.raises(KnowledgeUnavailableError, match="invalid provenance"):
        Neo4jKnowledgeRepository(FakeDriver(responder)).fact_provenance(fact["fact_id"])


def test_neo4j_activity_restriction_query_uses_stable_product_ids():
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)
    activity_fact = catalog.facts[
        "fact-activity-restriction-tyno-driving-machinery-001"
    ].model_dump(mode="json")

    def responder(query: str, _parameters: dict[str, Any]):
        if "predicate = 'ACTIVITY_RESTRICTION'" in query:
            return [{"fact": activity_fact}]
        if "RETURN snapshot.data_version AS data_version" in query:
            return [{"data_version": catalog.data_version}]
        raise AssertionError(f"unexpected query: {query}")

    driver = FakeDriver(responder)
    facts = Neo4jKnowledgeRepository(driver).activity_restriction_facts_for(
        {"medication-tyno-cold-tablet-cn"},
        {"驾驶或从事高空、机械及精密仪器作业"},
    )

    assert [fact.fact_id for fact in facts] == [activity_fact["fact_id"]]
    query, parameters = next(
        (query, parameters)
        for query, parameters in driver.calls
        if "predicate = 'ACTIVITY_RESTRICTION'" in query
    )
    assert "SafetyMedication {medication_id: medication_id}" in query
    assert "[:OBJECT]->(object:SafetyContext)" in query
    assert "[:APPLIES_IN]->(object)" in query
    assert parameters["medication_ids"] == ["medication-tyno-cold-tablet-cn"]


def test_neo4j_repository_returns_none_for_unknown_fact_provenance():
    def responder(query: str, _parameters: dict[str, Any]):
        if "subject_name" in query:
            return []
        raise AssertionError(f"unexpected query: {query}")

    repository = Neo4jKnowledgeRepository(FakeDriver(responder))

    assert repository.fact_provenance("fact-not-found") is None


def test_neo4j_repository_rejects_missing_snapshot():
    repository = Neo4jKnowledgeRepository(FakeDriver())

    with pytest.raises(KnowledgeUnavailableError, match="not initialized"):
        _ = repository.data_version


def test_neo4j_repository_rejects_mixed_data_versions():
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)
    medication = catalog.medications["medication-tyno-cold-tablet-cn"].model_dump(mode="json")

    def responder(query: str, _parameters: dict[str, Any]):
        if "RETURN properties(medication)" in query:
            return [{"medication": medication}]
        if "SafetyKnowledgeSnapshot" in query:
            return [{"data_version": "v1.0.0-alpha.2"}]
        raise AssertionError(f"unexpected query: {query}")

    repository = Neo4jKnowledgeRepository(FakeDriver(responder))

    with pytest.raises(KnowledgeUnavailableError, match="mixed data versions"):
        repository.resolve_medication("泰诺")


def test_neo4j_repository_rejects_invalid_projection_record():
    def responder(query: str, _parameters: dict[str, Any]):
        if "RETURN properties(medication)" in query:
            return [{"medication": {"medication_id": "broken-record"}}]
        raise AssertionError(f"unexpected query: {query}")

    repository = Neo4jKnowledgeRepository(FakeDriver(responder))

    with pytest.raises(KnowledgeUnavailableError, match="invalid record"):
        repository.resolve_medication("泰诺")


def test_neo4j_repository_wraps_driver_errors_without_exposing_them_to_engine():
    def responder(_query: str, _parameters: dict[str, Any]):
        raise ServiceUnavailable("private bolt address")

    repository = Neo4jKnowledgeRepository(FakeDriver(responder))
    result = SafetyEngine(repository).assess(["泰诺"])

    assert result.conclusion_status == ConclusionStatus.KNOWLEDGE_UNAVAILABLE
    assert result.data_version is None
    assert "private bolt address" not in " ".join(result.limitations)
