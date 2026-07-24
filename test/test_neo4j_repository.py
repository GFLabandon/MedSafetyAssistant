from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
from neo4j.exceptions import ServiceUnavailable

from medsafety.catalog import KnowledgeCatalog
from medsafety.contracts import ConclusionStatus
from medsafety.neo4j_repository import Neo4jCatalogImporter, Neo4jKnowledgeRepository
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


def test_importer_is_parameterized_and_repeat_safe():
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)
    driver = FakeDriver()
    importer = Neo4jCatalogImporter(driver, database="neo4j")

    first = importer.import_catalog(catalog)
    first_call_count = len(driver.calls)
    second = importer.import_catalog(catalog)

    assert first == second
    assert first.data_version == "v1.0.0-alpha.2"
    assert first.sources == 7
    assert first.medications == 4
    assert first.ingredients == 10
    assert first.contexts == 2
    assert first.facts == 3
    assert first.support_links == 11
    assert first.context_links == 1
    assert len(driver.calls) == first_call_count * 2

    constraint_calls = [query for query, _ in driver.calls if query.startswith("CREATE CONSTRAINT")]
    data_calls = [(query, params) for query, params in driver.calls if not query.startswith("CREATE")]
    assert constraint_calls
    assert all("IF NOT EXISTS" in query for query in constraint_calls)
    reset_calls = [query for query, _ in data_calls if "DETACH DELETE" in query]
    assert len(reset_calls) == 2
    assert all("STARTS WITH 'Safety'" in query for query in reset_calls)
    upsert_calls = [(query, params) for query, params in data_calls if "DETACH DELETE" not in query]
    assert all("MERGE" in query for query, _ in upsert_calls)

    medication_call = next(
        (query, params)
        for query, params in data_calls
        if "SafetyMedication {medication_id: $medication_id}" in query
    )
    assert "$properties" in medication_call[0]
    assert medication_call[1]["properties"]["canonical_name"] == "泰诺"
    assert "泰诺" not in medication_call[0]


def test_neo4j_repository_reconstructs_strict_contracts_and_drives_engine():
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)
    tyno = catalog.medications["medication-tyno-cold-tablet-cn"].model_dump(mode="json")
    gankang = catalog.medications["medication-gankang-tablet-cn"].model_dump(mode="json")
    duplicate_fact = catalog.facts["fact-duplicate-acetaminophen-001"].model_dump(mode="json")

    def responder(query: str, parameters: dict[str, Any]):
        if "SafetyKnowledgeSnapshot" in query:
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

    repository = Neo4jKnowledgeRepository(FakeDriver(responder), database="neo4j")
    result = SafetyEngine(repository).assess(["泰诺", "感康"])

    assert result.conclusion_status == ConclusionStatus.RISK_FOUND
    assert result.data_version == catalog.data_version
    assert [fact.fact_id for fact in result.facts] == ["fact-duplicate-acetaminophen-001"]


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
        if "SafetyKnowledgeSnapshot" in query:
            return [{"data_version": catalog.data_version}]
        if "RETURN properties(medication)" in query:
            return [{"medication": medication}]
        if "RETURN properties(context)" in query:
            return [{"context": context}]
        if "CONTRAINDICATED_IN" in query:
            return [{"fact": fact}]
        raise AssertionError(f"unexpected query: {query}")

    repository = Neo4jKnowledgeRepository(FakeDriver(responder))
    result = SafetyEngine(repository).assess(["布洛芬"], contexts=["NSAID过敏"])

    assert result.conclusion_status == ConclusionStatus.RISK_FOUND
    assert result.facts[0].fact_id == fact["fact_id"]


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
            return [{"data_version": "v1.0.0-alpha.3"}]
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
