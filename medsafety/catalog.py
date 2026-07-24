"""Validated, source-aligned knowledge catalog for the V1 Safety Engine."""

from __future__ import annotations

import json
from pathlib import Path

from medsafety.contracts import (
    ClinicalContextRecord,
    FactRecord,
    LabelStatus,
    MedicationRecord,
    ReviewStatus,
    SourceRecord,
)


class CatalogValidationError(ValueError):
    """Raised when source-aligned data cannot be trusted by the engine."""


def _load_json(path: Path):
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        raise CatalogValidationError(f"cannot load {path}: {exc}") from exc


def _index_unique(records, identifier: str, record_type: str):
    indexed = {}
    for record in records:
        record_id = getattr(record, identifier)
        if record_id in indexed:
            raise CatalogValidationError(f"duplicate {record_type} id: {record_id}")
        indexed[record_id] = record
    return indexed


class KnowledgeCatalog:
    def __init__(
        self,
        sources: list[SourceRecord],
        medications: list[MedicationRecord],
        contexts: list[ClinicalContextRecord],
        facts: list[FactRecord],
    ):
        self.sources = _index_unique(sources, "source_id", "source")
        self.medications = _index_unique(medications, "medication_id", "medication")
        self.contexts = _index_unique(contexts, "context_id", "context")
        self.facts = _index_unique(facts, "fact_id", "fact")
        self._medication_aliases: dict[str, MedicationRecord] = {}
        self._context_aliases: dict[str, ClinicalContextRecord] = {}
        self._validate_and_index()

    @classmethod
    def from_directory(cls, directory: str | Path) -> "KnowledgeCatalog":
        root = Path(directory)
        try:
            sources = [SourceRecord.model_validate(item) for item in _load_json(root / "sources.json")]
            medications = [
                MedicationRecord.model_validate(item) for item in _load_json(root / "medications.json")
            ]
            contexts = [
                ClinicalContextRecord.model_validate(item)
                for item in _load_json(root / "contexts.json")
            ]
            facts = [FactRecord.model_validate(item) for item in _load_json(root / "facts.json")]
        except CatalogValidationError:
            raise
        except Exception as exc:
            raise CatalogValidationError(f"invalid V1 catalog in {root}: {exc}") from exc
        return cls(sources=sources, medications=medications, contexts=contexts, facts=facts)

    @property
    def data_version(self) -> str:
        versions = {
            item.data_version
            for item in [*self.medications.values(), *self.contexts.values(), *self.facts.values()]
        }
        if len(versions) != 1:
            raise CatalogValidationError(f"catalog contains inconsistent data versions: {sorted(versions)}")
        return versions.pop()

    def _validate_and_index(self):
        if not self.sources or not self.medications or not self.contexts or not self.facts:
            raise CatalogValidationError("catalog requires sources, medications, contexts, and facts")

        for source in self.sources.values():
            if source.review_status != ReviewStatus.REVIEWED:
                raise CatalogValidationError(f"source is not reviewed: {source.source_id}")

        for record in [*self.medications.values(), *self.facts.values()]:
            if record.review_status != ReviewStatus.REVIEWED:
                raise CatalogValidationError(f"record is not reviewed: {record}")
            if record.label_status not in {LabelStatus.SOURCE_ALIGNED, LabelStatus.CLINICALLY_REVIEWED}:
                raise CatalogValidationError(f"record is not source aligned: {record}")
            missing_sources = set(record.source_ids) - self.sources.keys()
            if missing_sources:
                raise CatalogValidationError(f"record references unknown sources: {sorted(missing_sources)}")

        for context in self.contexts.values():
            if context.review_status != ReviewStatus.REVIEWED:
                raise CatalogValidationError(f"context is not reviewed: {context.context_id}")

        canonical_contexts = {context.canonical_name for context in self.contexts.values()}
        for fact in self.facts.values():
            unknown_contexts = set(fact.required_context) - canonical_contexts
            if unknown_contexts:
                raise CatalogValidationError(
                    f"fact references unknown contexts: {sorted(unknown_contexts)}"
                )
            if fact.predicate == "CONTRAINDICATED_IN" and fact.object not in canonical_contexts:
                raise CatalogValidationError(
                    f"contraindication references unknown context: {fact.object}"
                )

        _ = self.data_version

        for medication in self.medications.values():
            for alias in [medication.canonical_name, *medication.aliases]:
                key = self.normalize_alias(alias)
                existing = self._medication_aliases.get(key)
                if existing and existing.medication_id != medication.medication_id:
                    raise CatalogValidationError(
                        f"ambiguous medication alias {alias!r}: "
                        f"{existing.medication_id} and {medication.medication_id}"
                    )
                self._medication_aliases[key] = medication

        for context in self.contexts.values():
            for alias in [context.canonical_name, *context.aliases]:
                key = self.normalize_alias(alias)
                existing = self._context_aliases.get(key)
                if existing and existing.context_id != context.context_id:
                    raise CatalogValidationError(
                        f"ambiguous context alias {alias!r}: "
                        f"{existing.context_id} and {context.context_id}"
                    )
                self._context_aliases[key] = context

    @staticmethod
    def normalize_alias(value: str) -> str:
        return " ".join(value.casefold().strip().split())

    def resolve_medication(self, value: str) -> MedicationRecord | None:
        return self._medication_aliases.get(self.normalize_alias(value))

    def resolve_context(self, value: str) -> ClinicalContextRecord | None:
        return self._context_aliases.get(self.normalize_alias(value))

    def duplicate_fact_for(self, ingredient: str) -> FactRecord | None:
        return next(
            (
                fact
                for fact in self.facts.values()
                if fact.predicate == "DUPLICATE_INGREDIENT"
                and fact.subject == ingredient
                and fact.object == ingredient
            ),
            None,
        )

    def interaction_facts_for(self, left: set[str], right: set[str]) -> list[FactRecord]:
        matches = []
        for fact in self.facts.values():
            if fact.predicate != "INTERACTS_WITH":
                continue
            if (fact.subject in left and fact.object in right) or (
                fact.subject in right and fact.object in left
            ):
                matches.append(fact)
        return matches

    def contraindication_facts_for(
        self,
        ingredients: set[str],
        contexts: set[str],
    ) -> list[FactRecord]:
        return [
            fact
            for fact in self.facts.values()
            if fact.predicate == "CONTRAINDICATED_IN"
            and fact.subject in ingredients
            and fact.object in contexts
        ]
