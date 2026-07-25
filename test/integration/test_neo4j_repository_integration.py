"""Real Neo4j acceptance for the source-aligned safety projection.

This test is intentionally pinned to the isolated Compose port. It never reads
credentials from the normal application configuration and only removes Safety*
nodes from that disposable test instance.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from neo4j import GraphDatabase

from api import get_v1_fact_provenance
from medsafety.catalog import KnowledgeCatalog
from medsafety.contracts import KnowledgeEntityKind
from medsafety.neo4j_query_plans import (
    collect_query_plan_evidence,
    collect_safety_index_evidence,
)
from medsafety.neo4j_repository import (
    Neo4jCatalogImporter,
    Neo4jKnowledgeRepository,
    Neo4jProjectionAuditor,
)
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
WHERE any(label IN labels(node) WHERE label STARTS WITH 'Safety')
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
        "medication_aliases": (
            "MATCH (node:SafetyMedicationAlias) RETURN count(node) AS count"
        ),
        "ingredients": "MATCH (node:SafetyIngredient) RETURN count(node) AS count",
        "contexts": "MATCH (node:SafetyContext) RETURN count(node) AS count",
        "context_aliases": (
            "MATCH (node:SafetyContextAlias) RETURN count(node) AS count"
        ),
        "facts": "MATCH (node:SafetyFact) RETURN count(node) AS count",
        "snapshots": "MATCH (node:SafetyKnowledgeSnapshot) RETURN count(node) AS count",
        "ingredient_links": (
            "MATCH (:SafetyMedication)-[link:HAS_ACTIVE_INGREDIENT]->(:SafetyIngredient) "
            "RETURN count(link) AS count"
        ),
        "medication_alias_links": (
            "MATCH (:SafetyMedication)-[link:KNOWN_AS]->(:SafetyMedicationAlias) "
            "RETURN count(link) AS count"
        ),
        "context_alias_links": (
            "MATCH (:SafetyContext)-[link:KNOWN_AS]->(:SafetyContextAlias) "
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
        "subject_links": (
            "MATCH (:SafetyFact)-[link:SUBJECT]->(subject) "
            "WHERE subject:SafetyIngredient OR subject:SafetyMedication "
            "RETURN count(link) AS count"
        ),
        "object_links": (
            "MATCH (:SafetyFact)-[link:OBJECT]->() "
            "RETURN count(link) AS count"
        ),
        "snapshot_links": (
            "MATCH (:SafetyFact)-[link:BELONGS_TO]->(:SafetyKnowledgeSnapshot) "
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
        "context_links": 3,
        "subject_links": 4,
        "object_links": 4,
        "snapshot_links": 4,
    }
    assert Neo4jProjectionAuditor(driver).audit(catalog).valid is True

    neo4j_engine = SafetyEngine(Neo4jKnowledgeRepository(driver))
    json_engine = SafetyEngine(catalog)
    cases = [
        (["泰诺", "感康"], []),
        (["paracetamol", "泰诺"], []),
        (["布洛芬", "阿司匹林"], []),
        (["ibuprofen", "aspirin"], ["阿司匹林用于心血管保护"]),
        (["泰诺"], []),
        (["布洛芬"], ["NSAID过敏"]),
        (["布洛芬"], ["哮喘"]),
        (["泰诺"], ["开车"]),
        (["感康"], ["驾驶"]),
        (["氯苯那敏"], ["驾驶"]),
        (["未收录药"], []),
    ]

    for medications, contexts in cases:
        expected = json_engine.assess(medications, contexts)
        actual = neo4j_engine.assess(medications, contexts)
        assert actual.model_dump(mode="json") == expected.model_dump(mode="json")

    repository = Neo4jKnowledgeRepository(driver)
    for fact_id, expected_fact in catalog.facts.items():
        provenance = repository.fact_provenance(fact_id)
        assert provenance is not None
        assert provenance.fact == expected_fact
        assert {source.source_id for source in provenance.sources} == set(
            expected_fact.source_ids
        )
        assert {context.canonical_name for context in provenance.applies_in} == set(
            expected_fact.required_context
        )

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(neo4j_repository=repository),
        ),
    )
    response = asyncio.run(
        get_v1_fact_provenance(
            fact_id="fact-duplicate-acetaminophen-001",
            request=request,
        )
    )
    assert response["schema_version"] == "fact-provenance-v2"
    assert response["fact"]["fact_id"] == "fact-duplicate-acetaminophen-001"
    assert response["snapshot"]["data_version"] == catalog.data_version


def test_real_neo4j_auditor_detects_a_dangling_fact(driver):
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)
    Neo4jCatalogImporter(driver).import_catalog(catalog)

    with driver.session() as session:
        session.run(
            """
            MATCH (:SafetyFact {fact_id: $fact_id})-[link:SUBJECT]->()
            DELETE link
            """,
            fact_id="fact-duplicate-acetaminophen-001",
        ).consume()

    report = Neo4jProjectionAuditor(driver).audit(catalog)

    assert report.valid is False
    assert report.actual.subject_links == 3
    assert report.orphan_facts == 1


def test_real_neo4j_product_subject_fact_matches_json_and_provenance(driver):
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)
    Neo4jCatalogImporter(driver).import_catalog(catalog)
    repository = Neo4jKnowledgeRepository(driver)

    expected = SafetyEngine(catalog).assess(["泰诺"], contexts=["开车"])
    actual = SafetyEngine(repository).assess(["泰诺"], contexts=["开车"])

    assert actual.model_dump(mode="json") == expected.model_dump(mode="json")
    assert actual.facts[0].fact_id == (
        "fact-activity-restriction-tyno-driving-machinery-001"
    )

    provenance = repository.fact_provenance(
        "fact-activity-restriction-tyno-driving-machinery-001"
    )
    assert provenance is not None
    assert provenance.schema_version == "fact-provenance-v2"
    assert provenance.subject.kind == KnowledgeEntityKind.MEDICATION
    assert provenance.subject.identifier == "medication-tyno-cold-tablet-cn"
    assert provenance.subject.name == "泰诺"
    assert provenance.object.kind == KnowledgeEntityKind.CONTEXT
    assert provenance.object.identifier == "context-driving-or-hazardous-operation"

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(neo4j_repository=repository),
        ),
    )
    response = asyncio.run(
        get_v1_fact_provenance(
            fact_id="fact-activity-restriction-tyno-driving-machinery-001",
            request=request,
        )
    )
    assert response["schema_version"] == "fact-provenance-v2"
    assert response["subject"] == {
        "kind": "medication",
        "identifier": "medication-tyno-cold-tablet-cn",
        "name": "泰诺",
    }


def test_real_neo4j_auditor_rejects_product_fact_linked_to_ingredient(driver):
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)
    Neo4jCatalogImporter(driver).import_catalog(catalog)

    with driver.session() as session:
        session.run(
            """
            MATCH (fact:SafetyFact {fact_id: $fact_id})-[old:SUBJECT]->()
            DELETE old
            WITH fact
            MATCH (ingredient:SafetyIngredient {name: $ingredient})
            CREATE (fact)-[:SUBJECT]->(ingredient)
            """,
            fact_id="fact-activity-restriction-tyno-driving-machinery-001",
            ingredient="马来酸氯苯那敏",
        ).consume()

    report = Neo4jProjectionAuditor(driver).audit(catalog)

    assert report.valid is False
    assert report.subject_property_mismatches == 1


def test_real_neo4j_query_plans_are_read_only_and_use_identity_indexes(driver):
    catalog = KnowledgeCatalog.from_directory(DATA_DIRECTORY)
    Neo4jCatalogImporter(driver).import_catalog(catalog)

    plans = {
        item.case_name: item
        for item in collect_query_plan_evidence(driver, mode="PROFILE")
    }
    indexes = {item.name: item for item in collect_safety_index_evidence(driver)}

    assert set(plans) == {
        "resolve_medication",
        "resolve_context",
        "duplicate_fact",
        "interaction_facts",
        "contraindication_facts",
        "activity_restriction_facts",
        "fact_provenance",
    }
    assert all(plan.query_type == "r" for plan in plans.values())
    assert all(plan.db_hits is not None for plan in plans.values())
    assert all(
        "Neo.ClientNotification.Statement.FeatureDeprecationWarning"
        not in plan.notification_codes
        for plan in plans.values()
    )
    assert all(plan.uses_index for plan in plans.values())
    assert {
        "safety_context_alias_normalized",
        "safety_fact_id",
        "safety_ingredient_name",
        "safety_medication_alias_normalized",
        "safety_snapshot_name",
    }.issubset(indexes)
    assert all(index.state == "ONLINE" for index in indexes.values())
