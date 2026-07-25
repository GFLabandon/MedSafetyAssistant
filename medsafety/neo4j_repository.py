"""Neo4j projection and read repository for source-aligned V1 knowledge.

The JSON catalog in ``data/v1`` remains the canonical source. Neo4j is a
derived, rebuildable read model. Each import transaction clears only the
dedicated ``Safety*`` projection before parameterized upserts, so removed
catalog records cannot remain queryable after a successful rebuild.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from neo4j.exceptions import DriverError, Neo4jError
from pydantic import ValidationError

from medsafety.catalog import KnowledgeCatalog
from medsafety.contracts import (
    ClinicalContextRecord,
    FactProvenance,
    FactRecord,
    KnowledgeEntityKind,
    KnowledgeEntityReference,
    KnowledgeSnapshotReference,
    MedicationRecord,
    SourceRecord,
)
from medsafety.repositories import KnowledgeUnavailableError


_SNAPSHOT_NAME = "source-aligned-v1"

_CONSTRAINT_QUERIES = (
    "CREATE CONSTRAINT safety_source_id IF NOT EXISTS "
    "FOR (source:SafetySource) REQUIRE source.source_id IS UNIQUE",
    "CREATE CONSTRAINT safety_medication_id IF NOT EXISTS "
    "FOR (medication:SafetyMedication) REQUIRE medication.medication_id IS UNIQUE",
    "CREATE CONSTRAINT safety_medication_alias_normalized IF NOT EXISTS "
    "FOR (alias:SafetyMedicationAlias) REQUIRE alias.normalized_name IS UNIQUE",
    "CREATE CONSTRAINT safety_ingredient_name IF NOT EXISTS "
    "FOR (ingredient:SafetyIngredient) REQUIRE ingredient.name IS UNIQUE",
    "CREATE CONSTRAINT safety_context_id IF NOT EXISTS "
    "FOR (context:SafetyContext) REQUIRE context.context_id IS UNIQUE",
    "CREATE CONSTRAINT safety_context_alias_normalized IF NOT EXISTS "
    "FOR (alias:SafetyContextAlias) REQUIRE alias.normalized_name IS UNIQUE",
    "CREATE CONSTRAINT safety_fact_id IF NOT EXISTS "
    "FOR (fact:SafetyFact) REQUIRE fact.fact_id IS UNIQUE",
    "CREATE CONSTRAINT safety_snapshot_name IF NOT EXISTS "
    "FOR (snapshot:SafetyKnowledgeSnapshot) REQUIRE snapshot.name IS UNIQUE",
)

_RESET_PROJECTION = """
MATCH (node)
WHERE any(label IN labels(node) WHERE label STARTS WITH 'Safety')
DETACH DELETE node
"""

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

_LINK_MEDICATION_ALIAS = """
MATCH (medication:SafetyMedication {medication_id: $medication_id})
MERGE (alias:SafetyMedicationAlias {normalized_name: $normalized_name})
SET alias.display_name = $display_name,
    alias.alias_type = $alias_type,
    alias.data_version = $data_version
MERGE (medication)-[:KNOWN_AS]->(alias)
"""

_LINK_CONTEXT_ALIAS = """
MATCH (context:SafetyContext {context_id: $context_id})
MERGE (alias:SafetyContextAlias {normalized_name: $normalized_name})
SET alias.display_name = $display_name,
    alias.alias_type = $alias_type,
    alias.data_version = $data_version
MERGE (context)-[:KNOWN_AS]->(alias)
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

_LINK_FACT_SUBJECT = """
MATCH (fact:SafetyFact {fact_id: $fact_id})
MATCH (ingredient:SafetyIngredient {name: $ingredient})
MERGE (fact)-[:SUBJECT]->(ingredient)
"""

_LINK_FACT_OBJECT_INGREDIENT = """
MATCH (fact:SafetyFact {fact_id: $fact_id})
MATCH (ingredient:SafetyIngredient {name: $ingredient})
MERGE (fact)-[:OBJECT]->(ingredient)
"""

_LINK_FACT_OBJECT_CONTEXT = """
MATCH (fact:SafetyFact {fact_id: $fact_id})
MATCH (context:SafetyContext {context_id: $context_id})
MERGE (fact)-[:OBJECT]->(context)
"""

_LINK_FACT_SNAPSHOT = """
MATCH (fact:SafetyFact {fact_id: $fact_id})
MATCH (snapshot:SafetyKnowledgeSnapshot {name: $snapshot_name})
MERGE (fact)-[:BELONGS_TO]->(snapshot)
"""

_RESOLVE_MEDICATION = """
MATCH (medication:SafetyMedication)-[:KNOWN_AS]->(
  alias:SafetyMedicationAlias {normalized_name: $normalized_name}
)
WHERE medication.review_status = 'reviewed'
  AND medication.label_status IN ['source_aligned', 'clinically_reviewed']
RETURN properties(medication) AS medication
LIMIT 1
"""

_RESOLVE_CONTEXT = """
MATCH (context:SafetyContext)-[:KNOWN_AS]->(
  alias:SafetyContextAlias {normalized_name: $normalized_name}
)
WHERE context.review_status = 'reviewed'
RETURN properties(context) AS context
LIMIT 1
"""

_DUPLICATE_FACT = """
MATCH (fact:SafetyFact)-[:SUBJECT]->(subject:SafetyIngredient)
MATCH (fact)-[:OBJECT]->(object:SafetyIngredient)
MATCH (fact)-[:BELONGS_TO]->(snapshot:SafetyKnowledgeSnapshot {name: $snapshot_name})
WHERE fact.review_status = 'reviewed'
  AND fact.label_status IN ['source_aligned', 'clinically_reviewed']
  AND fact.predicate = 'DUPLICATE_INGREDIENT'
  AND subject.name = $ingredient
  AND object.name = $ingredient
  AND fact.data_version = snapshot.data_version
RETURN properties(fact) AS fact
LIMIT 1
"""

_INTERACTION_FACTS = """
MATCH (fact:SafetyFact)-[:SUBJECT]->(subject:SafetyIngredient)
MATCH (fact)-[:OBJECT]->(object:SafetyIngredient)
MATCH (fact)-[:BELONGS_TO]->(snapshot:SafetyKnowledgeSnapshot {name: $snapshot_name})
WHERE fact.review_status = 'reviewed'
  AND fact.label_status IN ['source_aligned', 'clinically_reviewed']
  AND fact.predicate = 'INTERACTS_WITH'
  AND (
    (subject.name IN $left AND object.name IN $right)
    OR (subject.name IN $right AND object.name IN $left)
  )
  AND fact.data_version = snapshot.data_version
RETURN properties(fact) AS fact
ORDER BY fact.fact_id
"""

_CONTRAINDICATION_FACTS = """
MATCH (fact:SafetyFact)-[:SUBJECT]->(subject:SafetyIngredient)
MATCH (fact)-[:OBJECT]->(object:SafetyContext)
MATCH (fact)-[:APPLIES_IN]->(object)
MATCH (fact)-[:BELONGS_TO]->(snapshot:SafetyKnowledgeSnapshot {name: $snapshot_name})
WHERE fact.review_status = 'reviewed'
  AND fact.label_status IN ['source_aligned', 'clinically_reviewed']
  AND fact.predicate = 'CONTRAINDICATED_IN'
  AND subject.name IN $ingredients
  AND object.canonical_name IN $contexts
  AND fact.data_version = snapshot.data_version
RETURN properties(fact) AS fact
ORDER BY fact.fact_id
"""

_DATA_VERSION = """
MATCH (snapshot:SafetyKnowledgeSnapshot {name: $snapshot_name})
RETURN snapshot.data_version AS data_version
"""

_FACT_PROVENANCE = """
MATCH (fact:SafetyFact {fact_id: $fact_id})
MATCH (fact)-[:SUBJECT]->(subject:SafetyIngredient)
MATCH (fact)-[:OBJECT]->(object)
MATCH (fact)-[:BELONGS_TO]->(
  snapshot:SafetyKnowledgeSnapshot {name: $snapshot_name}
)
WHERE fact.review_status = 'reviewed'
  AND fact.label_status IN ['source_aligned', 'clinically_reviewed']
  AND fact.data_version = snapshot.data_version
OPTIONAL MATCH (fact)-[:APPLIES_IN]->(context:SafetyContext)
WITH fact, subject, object, snapshot,
     collect(DISTINCT properties(context)) AS contexts
MATCH (fact)-[:SUPPORTED_BY]->(source:SafetySource)
RETURN properties(fact) AS fact,
       subject.name AS subject_name,
       CASE
         WHEN object:SafetyIngredient THEN 'ingredient'
         WHEN object:SafetyContext THEN 'context'
         ELSE 'unsupported'
       END AS object_kind,
       CASE
         WHEN object:SafetyIngredient THEN object.name
         WHEN object:SafetyContext THEN object.context_id
         ELSE ''
       END AS object_identifier,
       CASE
         WHEN object:SafetyIngredient THEN object.name
         WHEN object:SafetyContext THEN object.canonical_name
         ELSE ''
       END AS object_name,
       contexts,
       collect(DISTINCT properties(source)) AS sources,
       snapshot.name AS snapshot_name,
       snapshot.data_version AS snapshot_data_version
"""

_PROJECTION_INTEGRITY = """
CALL () { MATCH (node:SafetySource) RETURN count(node) AS sources }
CALL () { MATCH (node:SafetyMedication) RETURN count(node) AS medications }
CALL () { MATCH (node:SafetyMedicationAlias) RETURN count(node) AS medication_aliases }
CALL () { MATCH (node:SafetyIngredient) RETURN count(node) AS ingredients }
CALL () { MATCH (node:SafetyContext) RETURN count(node) AS contexts }
CALL () { MATCH (node:SafetyContextAlias) RETURN count(node) AS context_aliases }
CALL () { MATCH (node:SafetyFact) RETURN count(node) AS facts }
CALL () { MATCH (node:SafetyKnowledgeSnapshot) RETURN count(node) AS snapshots }
CALL () {
  MATCH (:SafetyMedication)-[link:HAS_ACTIVE_INGREDIENT]->(:SafetyIngredient)
  RETURN count(link) AS ingredient_links
}
CALL () {
  MATCH (:SafetyMedication)-[link:KNOWN_AS]->(:SafetyMedicationAlias)
  RETURN count(link) AS medication_alias_links
}
CALL () {
  MATCH (:SafetyContext)-[link:KNOWN_AS]->(:SafetyContextAlias)
  RETURN count(link) AS context_alias_links
}
CALL () {
  MATCH (subject)-[link:SUPPORTED_BY]->(:SafetySource)
  WHERE subject:SafetyMedication OR subject:SafetyFact
  RETURN count(link) AS support_links
}
CALL () {
  MATCH (:SafetyFact)-[link:SUBJECT]->(:SafetyIngredient)
  RETURN count(link) AS subject_links
}
CALL () {
  MATCH (:SafetyFact)-[link:OBJECT]->(target)
  WHERE target:SafetyIngredient OR target:SafetyContext
  RETURN count(link) AS object_links
}
CALL () {
  MATCH (:SafetyFact)-[link:APPLIES_IN]->(:SafetyContext)
  RETURN count(link) AS context_links
}
CALL () {
  MATCH (:SafetyFact)-[link:BELONGS_TO]->(:SafetyKnowledgeSnapshot)
  RETURN count(link) AS snapshot_links
}
CALL () {
  MATCH (node)
  WHERE (
    node:SafetyMedication
    OR node:SafetyMedicationAlias
    OR node:SafetyContext
    OR node:SafetyContextAlias
    OR node:SafetyFact
  )
    AND coalesce(node.data_version, '') <> $data_version
  RETURN count(node) AS mixed_version_nodes
}
CALL () {
  MATCH (snapshot:SafetyKnowledgeSnapshot)
  WHERE snapshot.name <> $snapshot_name
     OR coalesce(snapshot.data_version, '') <> $data_version
  RETURN count(snapshot) AS invalid_snapshots
}
CALL () {
  MATCH (fact:SafetyFact)
  WHERE NOT EXISTS { MATCH (fact)-[:SUBJECT]->(:SafetyIngredient) }
     OR NOT EXISTS { MATCH (fact)-[:OBJECT]->() }
     OR NOT EXISTS { MATCH (fact)-[:SUPPORTED_BY]->(:SafetySource) }
     OR NOT EXISTS { MATCH (fact)-[:BELONGS_TO]->(:SafetyKnowledgeSnapshot) }
  RETURN count(fact) AS orphan_facts
}
CALL () {
  MATCH (fact:SafetyFact)-[:SUBJECT]->(subject:SafetyIngredient)
  WHERE fact.subject <> subject.name
  RETURN count(fact) AS subject_property_mismatches
}
CALL () {
  MATCH (fact:SafetyFact)-[:OBJECT]->(object)
  WITH fact,
       CASE
         WHEN object:SafetyIngredient THEN object.name
         WHEN object:SafetyContext THEN object.canonical_name
         ELSE null
       END AS object_name
  WHERE object_name IS NULL OR fact.object <> object_name
  RETURN count(fact) AS object_property_mismatches
}
CALL () {
  MATCH (medication:SafetyMedication)
  OPTIONAL MATCH (medication)-[:HAS_ACTIVE_INGREDIENT]->(ingredient:SafetyIngredient)
  WITH medication, collect(ingredient.name) AS linked_ingredients
  WHERE size(medication.active_ingredients) <> size(linked_ingredients)
     OR any(value IN medication.active_ingredients WHERE NOT value IN linked_ingredients)
  RETURN count(medication) AS medication_ingredient_mismatches
}
CALL () {
  MATCH (subject)
  WHERE subject:SafetyMedication OR subject:SafetyFact
  OPTIONAL MATCH (subject)-[:SUPPORTED_BY]->(source:SafetySource)
  WITH subject, collect(source.source_id) AS linked_sources
  WHERE size(subject.source_ids) <> size(linked_sources)
     OR any(value IN subject.source_ids WHERE NOT value IN linked_sources)
  RETURN count(subject) AS support_reference_mismatches
}
CALL () {
  MATCH (fact:SafetyFact)
  OPTIONAL MATCH (fact)-[:APPLIES_IN]->(context:SafetyContext)
  WITH fact, collect(context.canonical_name) AS linked_contexts
  WHERE size(fact.required_context) <> size(linked_contexts)
     OR any(value IN fact.required_context WHERE NOT value IN linked_contexts)
  RETURN count(fact) AS context_reference_mismatches
}
CALL () {
  MATCH (medication:SafetyMedication)
  OPTIONAL MATCH (medication)-[:KNOWN_AS]->(alias:SafetyMedicationAlias)
  WITH medication, collect(alias.normalized_name) AS linked_aliases
  WITH medication, linked_aliases,
       [medication.canonical_name_normalized] + medication.aliases_normalized
       AS expected_aliases
  WHERE size(expected_aliases) <> size(linked_aliases)
     OR any(value IN expected_aliases WHERE NOT value IN linked_aliases)
  RETURN count(medication) AS medication_alias_mismatches
}
CALL () {
  MATCH (context:SafetyContext)
  OPTIONAL MATCH (context)-[:KNOWN_AS]->(alias:SafetyContextAlias)
  WITH context, collect(alias.normalized_name) AS linked_aliases
  WITH context, linked_aliases,
       [context.canonical_name_normalized] + context.aliases_normalized
       AS expected_aliases
  WHERE size(expected_aliases) <> size(linked_aliases)
     OR any(value IN expected_aliases WHERE NOT value IN linked_aliases)
  RETURN count(context) AS context_alias_mismatches
}
RETURN sources, medications, medication_aliases, ingredients, contexts,
       context_aliases, facts, snapshots, ingredient_links,
       medication_alias_links, context_alias_links, support_links,
       subject_links, object_links,
       context_links, snapshot_links, mixed_version_nodes, orphan_facts,
       invalid_snapshots, subject_property_mismatches, object_property_mismatches,
       medication_ingredient_mismatches, support_reference_mismatches,
       context_reference_mismatches, medication_alias_mismatches,
       context_alias_mismatches
"""


@dataclass(frozen=True)
class ProjectionCounts:
    sources: int
    medications: int
    medication_aliases: int
    ingredients: int
    contexts: int
    context_aliases: int
    facts: int
    snapshots: int
    ingredient_links: int
    medication_alias_links: int
    context_alias_links: int
    support_links: int
    subject_links: int
    object_links: int
    context_links: int
    snapshot_links: int


@dataclass(frozen=True)
class ProjectionIntegrityReport:
    expected: ProjectionCounts
    actual: ProjectionCounts
    mixed_version_nodes: int
    invalid_snapshots: int
    orphan_facts: int
    subject_property_mismatches: int
    object_property_mismatches: int
    medication_ingredient_mismatches: int
    support_reference_mismatches: int
    context_reference_mismatches: int
    medication_alias_mismatches: int
    context_alias_mismatches: int

    @property
    def issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        if self.actual != self.expected:
            issues.append("projection counts do not match the canonical catalog")
        if self.mixed_version_nodes:
            issues.append("projection contains mixed data versions")
        if self.invalid_snapshots:
            issues.append("projection snapshot identity or version is invalid")
        if self.orphan_facts:
            issues.append("projection contains facts with missing required relationships")
        if self.subject_property_mismatches:
            issues.append("fact subject properties disagree with SUBJECT relationships")
        if self.object_property_mismatches:
            issues.append("fact object properties disagree with OBJECT relationships")
        if self.medication_ingredient_mismatches:
            issues.append("medication ingredient properties disagree with graph relationships")
        if self.support_reference_mismatches:
            issues.append("source references disagree with SUPPORTED_BY relationships")
        if self.context_reference_mismatches:
            issues.append("required contexts disagree with APPLIES_IN relationships")
        if self.medication_alias_mismatches:
            issues.append("medication aliases disagree with KNOWN_AS relationships")
        if self.context_alias_mismatches:
            issues.append("context aliases disagree with KNOWN_AS relationships")
        return tuple(issues)

    @property
    def valid(self) -> bool:
        return not self.issues


class ProjectionIntegrityError(RuntimeError):
    """Raised before commit when a rebuilt graph violates the P2 projection contract."""


@dataclass(frozen=True)
class ImportSummary:
    data_version: str
    sources: int
    medications: int
    medication_aliases: int
    ingredients: int
    contexts: int
    context_aliases: int
    facts: int
    snapshots: int
    ingredient_links: int
    medication_alias_links: int
    context_alias_links: int
    support_links: int
    subject_links: int
    object_links: int
    context_links: int
    snapshot_links: int
    integrity_verified: bool


def _json_properties(model: Any) -> dict[str, Any]:
    """Convert Pydantic values to Neo4j-safe primitive properties."""

    return model.model_dump(mode="json")


def _contract_properties(model_type: Any, values: dict[str, Any]) -> dict[str, Any]:
    """Discard projection-only fields before strict contract validation."""

    return {name: values[name] for name in model_type.model_fields if name in values}


def _normalized_alias_records(
    canonical_name: str,
    aliases: list[str],
) -> list[tuple[str, str, str]]:
    records: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for display_name, alias_type in [
        (canonical_name, "canonical"),
        *((alias, "alias") for alias in aliases),
    ]:
        normalized_name = KnowledgeCatalog.normalize_alias(display_name)
        if normalized_name in seen:
            continue
        seen.add(normalized_name)
        records.append((normalized_name, display_name, alias_type))
    return records


def _expected_projection_counts(catalog: KnowledgeCatalog) -> ProjectionCounts:
    ingredients = {
        ingredient
        for medication in catalog.medications.values()
        for ingredient in medication.active_ingredients
    }
    return ProjectionCounts(
        sources=len(catalog.sources),
        medications=len(catalog.medications),
        medication_aliases=sum(
            len(
                {
                    KnowledgeCatalog.normalize_alias(value)
                    for value in [medication.canonical_name, *medication.aliases]
                }
            )
            for medication in catalog.medications.values()
        ),
        ingredients=len(ingredients),
        contexts=len(catalog.contexts),
        context_aliases=sum(
            len(
                {
                    KnowledgeCatalog.normalize_alias(value)
                    for value in [context.canonical_name, *context.aliases]
                }
            )
            for context in catalog.contexts.values()
        ),
        facts=len(catalog.facts),
        snapshots=1,
        ingredient_links=sum(
            len(medication.active_ingredients) for medication in catalog.medications.values()
        ),
        medication_alias_links=sum(
            len(
                {
                    KnowledgeCatalog.normalize_alias(value)
                    for value in [medication.canonical_name, *medication.aliases]
                }
            )
            for medication in catalog.medications.values()
        ),
        context_alias_links=sum(
            len(
                {
                    KnowledgeCatalog.normalize_alias(value)
                    for value in [context.canonical_name, *context.aliases]
                }
            )
            for context in catalog.contexts.values()
        ),
        support_links=(
            sum(len(medication.source_ids) for medication in catalog.medications.values())
            + sum(len(fact.source_ids) for fact in catalog.facts.values())
        ),
        subject_links=len(catalog.facts),
        object_links=len(catalog.facts),
        context_links=sum(
            len(set(fact.required_context)) for fact in catalog.facts.values()
        ),
        snapshot_links=len(catalog.facts),
    )


def _projection_integrity_report(
    runner: Any,
    catalog: KnowledgeCatalog,
) -> ProjectionIntegrityReport:
    record = runner.run(
        _PROJECTION_INTEGRITY,
        data_version=catalog.data_version,
        snapshot_name=_SNAPSHOT_NAME,
    ).single()
    if record is None:
        raise ProjectionIntegrityError("projection integrity query returned no result")
    values = dict(record)
    actual = ProjectionCounts(
        **{
            field: int(values[field])
            for field in ProjectionCounts.__dataclass_fields__
        }
    )
    return ProjectionIntegrityReport(
        expected=_expected_projection_counts(catalog),
        actual=actual,
        mixed_version_nodes=int(values["mixed_version_nodes"]),
        invalid_snapshots=int(values["invalid_snapshots"]),
        orphan_facts=int(values["orphan_facts"]),
        subject_property_mismatches=int(values["subject_property_mismatches"]),
        object_property_mismatches=int(values["object_property_mismatches"]),
        medication_ingredient_mismatches=int(values["medication_ingredient_mismatches"]),
        support_reference_mismatches=int(values["support_reference_mismatches"]),
        context_reference_mismatches=int(values["context_reference_mismatches"]),
        medication_alias_mismatches=int(values["medication_alias_mismatches"]),
        context_alias_mismatches=int(values["context_alias_mismatches"]),
    )


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
        # This runs in the same write transaction as all upserts. If any
        # validation or write fails, Neo4j rolls the reset back as well.
        transaction.run(_RESET_PROJECTION).consume()
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
            for normalized_name, display_name, alias_type in _normalized_alias_records(
                context.canonical_name,
                context.aliases,
            ):
                transaction.run(
                    _LINK_CONTEXT_ALIAS,
                    context_id=context.context_id,
                    normalized_name=normalized_name,
                    display_name=display_name,
                    alias_type=alias_type,
                    data_version=context.data_version,
                )

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
            for normalized_name, display_name, alias_type in _normalized_alias_records(
                medication.canonical_name,
                medication.aliases,
            ):
                transaction.run(
                    _LINK_MEDICATION_ALIAS,
                    medication_id=medication.medication_id,
                    normalized_name=normalized_name,
                    display_name=display_name,
                    alias_type=alias_type,
                    data_version=medication.data_version,
                )
            for ingredient in medication.active_ingredients:
                transaction.run(
                    _LINK_MEDICATION_INGREDIENT,
                    medication_id=medication.medication_id,
                    ingredient=ingredient,
                )
            for source_id in medication.source_ids:
                transaction.run(
                    _LINK_MEDICATION_SOURCE,
                    medication_id=medication.medication_id,
                    source_id=source_id,
                )

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
                transaction.run(
                    _LINK_FACT_SOURCE,
                    fact_id=fact.fact_id,
                    source_id=source_id,
                )
            transaction.run(
                _LINK_FACT_SUBJECT,
                fact_id=fact.fact_id,
                ingredient=fact.subject,
            )
            if fact.predicate == "CONTRAINDICATED_IN":
                transaction.run(
                    _LINK_FACT_OBJECT_CONTEXT,
                    fact_id=fact.fact_id,
                    context_id=context_ids_by_name[fact.object],
                )
            else:
                transaction.run(
                    _LINK_FACT_OBJECT_INGREDIENT,
                    fact_id=fact.fact_id,
                    ingredient=fact.object,
                )
            for context_name in set(fact.required_context):
                transaction.run(
                    _LINK_FACT_CONTEXT,
                    fact_id=fact.fact_id,
                    context_id=context_ids_by_name[context_name],
                )
            transaction.run(
                _LINK_FACT_SNAPSHOT,
                fact_id=fact.fact_id,
                snapshot_name=_SNAPSHOT_NAME,
            )

        integrity = _projection_integrity_report(transaction, catalog)
        if not integrity.valid:
            raise ProjectionIntegrityError("; ".join(integrity.issues))
        return ImportSummary(
            data_version=catalog.data_version,
            **{
                field: getattr(integrity.actual, field)
                for field in ProjectionCounts.__dataclass_fields__
            },
            integrity_verified=True,
        )


class Neo4jProjectionAuditor:
    """Inspect an existing projection without mutating it."""

    def __init__(self, driver: Any, database: str | None = None):
        self._driver = driver
        self._database = database

    def audit(self, catalog: KnowledgeCatalog) -> ProjectionIntegrityReport:
        with self._driver.session(database=self._database) as session:
            return _projection_integrity_report(session, catalog)


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
        record = self._single(
            _DUPLICATE_FACT,
            ingredient=ingredient,
            snapshot_name=_SNAPSHOT_NAME,
        )
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
            snapshot_name=_SNAPSHOT_NAME,
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
            snapshot_name=_SNAPSHOT_NAME,
        )
        facts = [self._validate_record(FactRecord, record, "fact") for record in records]
        for fact in facts:
            self._require_current_version(fact.data_version)
        return facts

    def fact_provenance(self, fact_id: str) -> FactProvenance | None:
        record = self._single(
            _FACT_PROVENANCE,
            fact_id=fact_id,
            snapshot_name=_SNAPSHOT_NAME,
        )
        if record is None:
            return None
        try:
            fact = FactRecord.model_validate(
                _contract_properties(FactRecord, record["fact"])
            )
            contexts = [
                ClinicalContextRecord.model_validate(
                    _contract_properties(ClinicalContextRecord, item)
                )
                for item in record["contexts"]
            ]
            sources = [
                SourceRecord.model_validate(_contract_properties(SourceRecord, item))
                for item in record["sources"]
            ]
            provenance = FactProvenance(
                fact=fact,
                subject=KnowledgeEntityReference(
                    kind=KnowledgeEntityKind.INGREDIENT,
                    identifier=record["subject_name"],
                    name=record["subject_name"],
                ),
                object=KnowledgeEntityReference(
                    kind=KnowledgeEntityKind(record["object_kind"]),
                    identifier=record["object_identifier"],
                    name=record["object_name"],
                ),
                applies_in=sorted(contexts, key=lambda item: item.context_id),
                sources=sorted(sources, key=lambda item: item.source_id),
                snapshot=KnowledgeSnapshotReference(
                    name=record["snapshot_name"],
                    data_version=record["snapshot_data_version"],
                ),
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise KnowledgeUnavailableError(
                "Neo4j safety knowledge contains invalid provenance"
            ) from exc
        self._require_current_version(provenance.fact.data_version)
        return provenance

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
