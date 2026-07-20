"""Real Neo4j acceptance for the source-aligned safety projection.

This test is intentionally pinned to the isolated Compose port. It never reads
credentials from the normal application configuration and only removes Safety*
nodes from that disposable test instance.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from neo4j import GraphDatabase

from medsafety.catalog import KnowledgeCatalog
from medsafety.neo4j_repository import Neo4jCatalogImporter, Neo4jKnowledgeRepository
from medsafety.safety_engine import SafetyEngine


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = REPOSITORY_ROOT / "data/v1"
TEST_URI = "bolt://127.0.0.1:17687"
TEST_AUTH = ("neo4j", "medsafety-test")
RUN_INTEGRATION = os.getenv("MEDSAFETY_RUN_NEO4J_INTEGRATION") == "1"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not RUN_INTEGRATION,
        reason="set MEDSAFETY_RUN_NEO4J_INTEGRATION=1 for the isolated Neo4j test",
    ),
]

_CLEAR_PROJECTION = """
MATCH (node)
WHERE node:SafetySource
   OR node:SafetyMedication
   OR node:SafetyIngredient
   OR node:SafetyContext
   OR node:SafetyFact
   OR node:SafetyKnowledgeSnapshot
DETACH DELETE node
"""


@pytest.fixture
def driver():
    test_driver = GraphDatabase.driver(TEST_URI, auth=TEST_AUTH)
    test_driver.verify_connectivity()
    with test_driver.session() as session:
        session.run(_CLEAR_PROJECTION).consume()
    try:
        yield test_driver
    finally:
        with test_driver.session() as session:
            session.run(_CLEAR_PROJECTION).consume()
        test_driver.close()


def _projection_counts(driver) -> dict[str, int]:
    queries = {
        "sources": "MATCH (node:SafetySource) RETURN count(node) AS count",
        "medications": "MATCH (node:SafetyMedication) RETURN count(node) AS count",
        "ingredients": "MATCH (node:SafetyIngredient) RETURN count(node) AS count",
        "contexts": "MATCH (node:SafetyContext) RETURN count(node) AS count",
        "facts": "MATCH (node:SafetyFact) RETURN count(node) AS count",
        "snapshots": "MATCH (node:SafetyKnowledgeSnapshot) RETURN count(node) AS count",
        "ingredient_links": (
            "MATCH (:SafetyMedication)-[link:HAS_ACTIVE_INGREDIENT]->(:SafetyIngredient) "
            "RETURN count(link) AS count"
        ),
        "support_links": (
            "MATCH (subject)-[link:SUPPORTED_BY]->(:SafetySource) "
            "WHERE subject:SafetyMedication OR subject:SafetyFact "
            "RETURN count(link) AS count"
        ),
        "context_links": (
            "MATCH (:SafetyFact)-[link:APPLIES_IN]->(:SafetyContext) "
            "RETURN count(link) AS count"
        ),
    }
    with driver.session() as session:
        return {
            name: int(session.run(query).single()["count"])
            for name, query in queries.items()
        }


def test_real_neo4j_import_is_idempotent_and_matches_json_behavior(driver):
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)
    importer = Neo4jCatalogImporter(driver)

    first_summary = importer.import_catalog(catalog)
    first_counts = _projection_counts(driver)
    second_summary = importer.import_catalog(catalog)
    second_counts = _projection_counts(driver)

    assert first_summary == second_summary
    assert first_counts == second_counts
    assert second_counts == {
        "sources": 7,
        "medications": 4,
        "ingredients": 10,
        "contexts": 2,
        "facts": 3,
        "snapshots": 1,
        "ingredient_links": 11,
        "support_links": 11,
        "context_links": 1,
    }

    neo4j_engine = SafetyEngine(Neo4jKnowledgeRepository(driver))
    json_engine = SafetyEngine(catalog)
    cases = [
        (["泰诺", "感康"], []),
        (["布洛芬", "阿司匹林"], []),
        (["ibuprofen", "aspirin"], ["阿司匹林用于心血管保护"]),
        (["泰诺"], []),
        (["布洛芬"], ["NSAID过敏"]),
        (["布洛芬"], ["哮喘"]),
        (["未收录药"], []),
    ]

    for medications, contexts in cases:
        expected = json_engine.assess(medications, contexts)
        actual = neo4j_engine.assess(medications, contexts)
        assert actual.model_dump(mode="json") == expected.model_dump(mode="json")
