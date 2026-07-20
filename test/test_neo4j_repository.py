from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from medsafety.catalog import KnowledgeCatalog
from medsafety.contracts import ConclusionStatus
from medsafety.neo4j_repository import Neo4jCatalogImporter, Neo4jKnowledgeRepository
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
    assert first.data_version == "v1.0.0-alpha.1"
    assert first.sources == 6
    assert first.medications == 4
    assert first.ingredients == 10
    assert first.facts == 2
    assert first.support_links == 10
    assert len(driver.calls) == first_call_count * 2

    constraint_calls = [query for query, _ in driver.calls if query.startswith("CREATE CONSTRAINT")]
    data_calls = [(query, params) for query, params in driver.calls if not query.startswith("CREATE")]
    assert constraint_calls
    assert all("IF NOT EXISTS" in query for query in constraint_calls)
    assert all("MERGE" in query for query, _ in data_calls)
    assert all("DETACH DELETE" not in query for query, _ in driver.calls)

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
