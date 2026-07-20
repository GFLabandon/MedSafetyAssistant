"""Validated, source-aligned knowledge catalog for the V1 Safety Engine."""

from __future__ import annotations

import json
from pathlib import Path

from medsafety.contracts import (
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


class KnowledgeCatalog:
    def __init__(
        self,
        sources: list[SourceRecord],
        medications: list[MedicationRecord],
        facts: list[FactRecord],
    ):
        self.sources = {item.source_id: item for item in sources}
        self.medications = {item.medication_id: item for item in medications}
        self.facts = {item.fact_id: item for item in facts}
        self._aliases: dict[str, MedicationRecord] = {}
        self._validate_and_index()

    @classmethod
    def from_directory(cls, directory: str | Path) -> "KnowledgeCatalog":
        root = Path(directory)
        try:
            sources = [SourceRecord.model_validate(item) for item in _load_json(root / "sources.json")]
            medications = [
                MedicationRecord.model_validate(item) for item in _load_json(root / "medications.json")
            ]
            facts = [FactRecord.model_validate(item) for item in _load_json(root / "facts.json")]
        except CatalogValidationError:
            raise
        except Exception as exc:
            raise CatalogValidationError(f"invalid V1 catalog in {root}: {exc}") from exc
        return cls(sources=sources, medications=medications, facts=facts)

    @property
    def data_version(self) -> str:
        versions = {item.data_version for item in [*self.medications.values(), *self.facts.values()]}
        if len(versions) != 1:
            raise CatalogValidationError(f"catalog contains inconsistent data versions: {sorted(versions)}")
        return versions.pop()

    def _validate_and_index(self):
        if not self.sources or not self.medications or not self.facts:
            raise CatalogValidationError("catalog requires sources, medications, and facts")

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

        _ = self.data_version

        for medication in self.medications.values():
            for alias in [medication.canonical_name, *medication.aliases]:
                key = self.normalize_alias(alias)
                existing = self._aliases.get(key)
                if existing and existing.medication_id != medication.medication_id:
                    raise CatalogValidationError(
                        f"ambiguous medication alias {alias!r}: "
                        f"{existing.medication_id} and {medication.medication_id}"
                    )
                self._aliases[key] = medication

    @staticmethod
    def normalize_alias(value: str) -> str:
        return " ".join(value.casefold().strip().split())

    def resolve_medication(self, value: str) -> MedicationRecord | None:
        return self._aliases.get(self.normalize_alias(value))

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
