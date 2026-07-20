"""Neo4j projection and read repository for source-aligned V1 knowledge.

The JSON catalog in ``data/v1`` remains the canonical source. Neo4j is a
derived, rebuildable read model. Import statements are parameterized and use
``MERGE`` so rerunning an import does not duplicate nodes or relationships.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from neo4j.exceptions import DriverError, Neo4jError
from pydantic import ValidationError

from medsafety.catalog import KnowledgeCatalog
from medsafety.contracts import ClinicalContextRecord, FactRecord, MedicationRecord
from medsafety.repositories import KnowledgeUnavailableError


_SNAPSHOT_NAME = "source-aligned-v1"

_CONSTRAINT_QUERIES = (
    "CREATE CONSTRAINT safety_source_id IF NOT EXISTS "
    "FOR (source:SafetySource) REQUIRE source.source_id IS UNIQUE",
    "CREATE CONSTRAINT safety_medication_id IF NOT EXISTS "
    "FOR (medication:SafetyMedication) REQUIRE medication.medication_id IS UNIQUE",
    "CREATE CONSTRAINT safety_ingredient_name IF NOT EXISTS "
    "FOR (ingredient:SafetyIngredient) REQUIRE ingredient.name IS UNIQUE",
    "CREATE CONSTRAINT safety_context_id IF NOT EXISTS "
    "FOR (context:SafetyContext) REQUIRE context.context_id IS UNIQUE",
    "CREATE CONSTRAINT safety_fact_id IF NOT EXISTS "
    "FOR (fact:SafetyFact) REQUIRE fact.fact_id IS UNIQUE",
    "CREATE CONSTRAINT safety_snapshot_name IF NOT EXISTS "
    "FOR (snapshot:SafetyKnowledgeSnapshot) REQUIRE snapshot.name IS UNIQUE",
)

_UPSERT_SNAPSHOT = """
MERGE (snapshot:SafetyKnowledgeSnapshot {name: $snapshot_name})
SET snapshot.data_version = $data_version,
    snapshot.updated_at = datetime()
"""

_UPSERT_SOURCE = """
MERGE (source:SafetySource {source_id: $source_id})
SET source += $properties
"""

_UPSERT_MEDICATION = """
MERGE (medication:SafetyMedication {medication_id: $medication_id})
SET medication += $properties
"""

_UPSERT_CONTEXT = """
MERGE (context:SafetyContext {context_id: $context_id})
SET context += $properties
"""

_LINK_MEDICATION_INGREDIENT = """
MATCH (medication:SafetyMedication {medication_id: $medication_id})
MERGE (ingredient:SafetyIngredient {name: $ingredient})
MERGE (medication)-[:HAS_ACTIVE_INGREDIENT]->(ingredient)
"""

_LINK_MEDICATION_SOURCE = """
MATCH (medication:SafetyMedication {medication_id: $medication_id})
MATCH (source:SafetySource {source_id: $source_id})
MERGE (medication)-[:SUPPORTED_BY]->(source)
"""

_UPSERT_FACT = """
MERGE (fact:SafetyFact {fact_id: $fact_id})
SET fact += $properties
"""

_LINK_FACT_SOURCE = """
MATCH (fact:SafetyFact {fact_id: $fact_id})
MATCH (source:SafetySource {source_id: $source_id})
MERGE (fact)-[:SUPPORTED_BY]->(source)
"""

_LINK_FACT_CONTEXT = """
MATCH (fact:SafetyFact {fact_id: $fact_id})
MATCH (context:SafetyContext {context_id: $context_id})
MERGE (fact)-[:APPLIES_IN]->(context)
"""

_RESOLVE_MEDICATION = """
MATCH (medication:SafetyMedication)
WHERE medication.review_status = 'reviewed'
  AND medication.label_status IN ['source_aligned', 'clinically_reviewed']
  AND (
    medication.canonical_name_normalized = $normalized_name
    OR $normalized_name IN medication.aliases_normalized
  )
RETURN properties(medication) AS medication
LIMIT 1
"""

_RESOLVE_CONTEXT = """
MATCH (context:SafetyContext)
WHERE context.review_status = 'reviewed'
  AND (
    context.canonical_name_normalized = $normalized_name
    OR $normalized_name IN context.aliases_normalized
  )
RETURN properties(context) AS context
LIMIT 1
"""

_DUPLICATE_FACT = """
MATCH (fact:SafetyFact)
WHERE fact.review_status = 'reviewed'
  AND fact.label_status IN ['source_aligned', 'clinically_reviewed']
  AND fact.predicate = 'DUPLICATE_INGREDIENT'
  AND fact.subject = $ingredient
  AND fact.object = $ingredient
RETURN properties(fact) AS fact
LIMIT 1
"""

_INTERACTION_FACTS = """
MATCH (fact:SafetyFact)
WHERE fact.review_status = 'reviewed'
  AND fact.label_status IN ['source_aligned', 'clinically_reviewed']
  AND fact.predicate = 'INTERACTS_WITH'
  AND (
    (fact.subject IN $left AND fact.object IN $right)
    OR (fact.subject IN $right AND fact.object IN $left)
  )
RETURN properties(fact) AS fact
ORDER BY fact.fact_id
"""

_CONTRAINDICATION_FACTS = """
MATCH (fact:SafetyFact)
WHERE fact.review_status = 'reviewed'
  AND fact.label_status IN ['source_aligned', 'clinically_reviewed']
  AND fact.predicate = 'CONTRAINDICATED_IN'
  AND fact.subject IN $ingredients
  AND fact.object IN $contexts
RETURN properties(fact) AS fact
ORDER BY fact.fact_id
"""

_DATA_VERSION = """
MATCH (snapshot:SafetyKnowledgeSnapshot {name: $snapshot_name})
RETURN snapshot.data_version AS data_version
"""


@dataclass(frozen=True)
class ImportSummary:
    data_version: str
    sources: int
    medications: int
    ingredients: int
    contexts: int
    facts: int
    support_links: int
    context_links: int


def _json_properties(model: Any) -> dict[str, Any]:
    """Convert Pydantic values to Neo4j-safe primitive properties."""

    return model.model_dump(mode="json")


def _contract_properties(model_type: Any, values: dict[str, Any]) -> dict[str, Any]:
    """Discard projection-only fields before strict contract validation."""

    return {name: values[name] for name in model_type.model_fields if name in values}


class Neo4jCatalogImporter:
    """Upsert a validated JSON catalog into the Neo4j read projection."""

    def __init__(self, driver: Any, database: str | None = None):
        self._driver = driver
        self._database = database

    def import_catalog(self, catalog: KnowledgeCatalog) -> ImportSummary:
        with self._driver.session(database=self._database) as session:
            for query in _CONSTRAINT_QUERIES:
                session.run(query).consume()
            return session.execute_write(self._upsert_catalog, catalog)

    @staticmethod
    def _upsert_catalog(transaction: Any, catalog: KnowledgeCatalog) -> ImportSummary:
        transaction.run(
            _UPSERT_SNAPSHOT,
            snapshot_name=_SNAPSHOT_NAME,
            data_version=catalog.data_version,
        )

        for source in catalog.sources.values():
            properties = _json_properties(source)
            transaction.run(
                _UPSERT_SOURCE,
                source_id=source.source_id,
                properties=properties,
            )

        for context in catalog.contexts.values():
            properties = _json_properties(context)
            properties["canonical_name_normalized"] = KnowledgeCatalog.normalize_alias(
                context.canonical_name
            )
            properties["aliases_normalized"] = [
                KnowledgeCatalog.normalize_alias(alias) for alias in context.aliases
            ]
            transaction.run(
                _UPSERT_CONTEXT,
                context_id=context.context_id,
                properties=properties,
            )

        ingredients: set[str] = set()
        medication_support_links = 0
        for medication in catalog.medications.values():
            properties = _json_properties(medication)
            properties["canonical_name_normalized"] = KnowledgeCatalog.normalize_alias(
                medication.canonical_name
            )
            properties["aliases_normalized"] = [
                KnowledgeCatalog.normalize_alias(alias) for alias in medication.aliases
            ]
            transaction.run(
                _UPSERT_MEDICATION,
                medication_id=medication.medication_id,
                properties=properties,
            )
            for ingredient in medication.active_ingredients:
                ingredients.add(ingredient)
                transaction.run(
                    _LINK_MEDICATION_INGREDIENT,
                    medication_id=medication.medication_id,
                    ingredient=ingredient,
                )
            for source_id in medication.source_ids:
                medication_support_links += 1
                transaction.run(
                    _LINK_MEDICATION_SOURCE,
                    medication_id=medication.medication_id,
                    source_id=source_id,
                )

        fact_support_links = 0
        fact_context_links = 0
        context_ids_by_name = {
            context.canonical_name: context.context_id for context in catalog.contexts.values()
        }
        for fact in catalog.facts.values():
            transaction.run(
                _UPSERT_FACT,
                fact_id=fact.fact_id,
                properties=_json_properties(fact),
            )
            for source_id in fact.source_ids:
                fact_support_links += 1
                transaction.run(
                    _LINK_FACT_SOURCE,
                    fact_id=fact.fact_id,
                    source_id=source_id,
                )
            if fact.predicate == "CONTRAINDICATED_IN":
                fact_context_links += 1
                transaction.run(
                    _LINK_FACT_CONTEXT,
                    fact_id=fact.fact_id,
                    context_id=context_ids_by_name[fact.object],
                )

        return ImportSummary(
            data_version=catalog.data_version,
            sources=len(catalog.sources),
            medications=len(catalog.medications),
            ingredients=len(ingredients),
            contexts=len(catalog.contexts),
            facts=len(catalog.facts),
            support_links=medication_support_links + fact_support_links,
            context_links=fact_context_links,
        )


class Neo4jKnowledgeRepository:
    """Read reviewed V1 knowledge from an imported Neo4j projection."""

    def __init__(self, driver: Any, database: str | None = None):
        self._driver = driver
        self._database = database

    @property
    def data_version(self) -> str:
        record = self._single(_DATA_VERSION, snapshot_name=_SNAPSHOT_NAME)
        if record is None or not record.get("data_version"):
            raise KnowledgeUnavailableError("Neo4j safety knowledge snapshot is not initialized")
        return str(record["data_version"])

    def resolve_medication(self, value: str) -> MedicationRecord | None:
        record = self._single(
            _RESOLVE_MEDICATION,
            normalized_name=KnowledgeCatalog.normalize_alias(value),
        )
        if record is None:
            return None
        medication = self._validate_record(MedicationRecord, record, "medication")
        self._require_current_version(medication.data_version)
        return medication

    def resolve_context(self, value: str) -> ClinicalContextRecord | None:
        record = self._single(
            _RESOLVE_CONTEXT,
            normalized_name=KnowledgeCatalog.normalize_alias(value),
        )
        if record is None:
            return None
        context = self._validate_record(ClinicalContextRecord, record, "context")
        self._require_current_version(context.data_version)
        return context

    def duplicate_fact_for(self, ingredient: str) -> FactRecord | None:
        record = self._single(_DUPLICATE_FACT, ingredient=ingredient)
        if record is None:
            return None
        fact = self._validate_record(FactRecord, record, "fact")
        self._require_current_version(fact.data_version)
        return fact

    def interaction_facts_for(self, left: set[str], right: set[str]) -> list[FactRecord]:
        records = self._all(
            _INTERACTION_FACTS,
            left=sorted(left),
            right=sorted(right),
        )
        facts = [self._validate_record(FactRecord, record, "fact") for record in records]
        for fact in facts:
            self._require_current_version(fact.data_version)
        return facts

    def contraindication_facts_for(
        self,
        ingredients: set[str],
        contexts: set[str],
    ) -> list[FactRecord]:
        records = self._all(
            _CONTRAINDICATION_FACTS,
            ingredients=sorted(ingredients),
            contexts=sorted(contexts),
        )
        facts = [self._validate_record(FactRecord, record, "fact") for record in records]
        for fact in facts:
            self._require_current_version(fact.data_version)
        return facts

    def _require_current_version(self, record_version: str) -> None:
        if record_version != self.data_version:
            raise KnowledgeUnavailableError("Neo4j safety knowledge contains mixed data versions")

    @staticmethod
    def _validate_record(model_type: Any, record: dict[str, Any], key: str):
        try:
            return model_type.model_validate(_contract_properties(model_type, record[key]))
        except (KeyError, TypeError, ValidationError) as exc:
            raise KnowledgeUnavailableError(
                "Neo4j safety knowledge contains an invalid record"
            ) from exc

    def _single(self, query: str, **parameters: Any) -> dict[str, Any] | None:
        try:
            with self._driver.session(database=self._database) as session:
                result = session.run(query, **parameters)
                record = result.single()
                return dict(record) if record is not None else None
        except (DriverError, Neo4jError) as exc:
            raise KnowledgeUnavailableError("Neo4j safety knowledge query failed") from exc

    def _all(self, query: str, **parameters: Any) -> list[dict[str, Any]]:
        try:
            with self._driver.session(database=self._database) as session:
                result: Iterable[Any] = session.run(query, **parameters)
                return [dict(record) for record in result]
        except (DriverError, Neo4jError) as exc:
            raise KnowledgeUnavailableError("Neo4j safety knowledge query failed") from exc
