"""Repository boundary consumed by the deterministic Safety Engine."""

from __future__ import annotations

from typing import Protocol

from medsafety.contracts import FactRecord, MedicationRecord


class KnowledgeRepository(Protocol):
    """Read-only access to reviewed, source-aligned safety knowledge."""

    @property
    def data_version(self) -> str:
        """Return the version of the knowledge snapshot being queried."""

    def resolve_medication(self, value: str) -> MedicationRecord | None:
        """Resolve one user-facing name or alias to a medication record."""

    def duplicate_fact_for(self, ingredient: str) -> FactRecord | None:
        """Return the reviewed duplicate-ingredient fact, if one exists."""

    def interaction_facts_for(self, left: set[str], right: set[str]) -> list[FactRecord]:
        """Return reviewed interactions spanning two ingredient sets."""
