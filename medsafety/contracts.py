"""Versioned data and API-neutral contracts for evidence-grounded evaluation.

These models do not replace the existing runtime yet. They define the boundary
that new data, evaluation, and Safety Engine work must satisfy.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class ConclusionStatus(str, Enum):
    RISK_FOUND = "risk_found"
    NO_KNOWN_RISK_IN_SCOPE = "no_known_risk_in_scope"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    OUT_OF_SCOPE = "out_of_scope"
    KNOWLEDGE_UNAVAILABLE = "knowledge_unavailable"


class ExplanationGenerationMode(str, Enum):
    DETERMINISTIC = "deterministic"
    LLM_PLANNED = "llm_planned"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class ExplanationFallbackReason(str, Enum):
    PLANNER_UNAVAILABLE = "planner_unavailable"
    INVALID_PLAN = "invalid_plan"


class Severity(str, Enum):
    INFO = "INFO"
    ORANGE = "ORANGE"
    RED = "RED"
    FATAL = "FATAL"


class RiskType(str, Enum):
    DUPLICATE_THERAPY = "DUPLICATE_THERAPY"
    CONTRAINDICATION = "CONTRAINDICATION"
    INTERACTION = "INTERACTION"


class MedicationKind(str, Enum):
    PRODUCT = "product"
    SUBSTANCE = "substance"


class ContextKind(str, Enum):
    MEDICATION_USE = "medication_use"
    REACTION_HISTORY = "reaction_history"


class LabelStatus(str, Enum):
    LEGACY_UNREVIEWED = "legacy_unreviewed"
    SOURCE_ALIGNED = "source_aligned"
    CLINICALLY_REVIEWED = "clinically_reviewed"


class SourceRecord(StrictModel):
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    publisher: str | None = None
    url: str | None = None
    published_at: date | None = None
    version: str | None = None
    license_note: str | None = None
    accessed_at: date | None = None
    review_status: ReviewStatus = ReviewStatus.DRAFT
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def reviewed_sources_are_traceable(self):
        if self.review_status == ReviewStatus.REVIEWED:
            required = (self.publisher, self.url, self.accessed_at, self.reviewed_by, self.reviewed_at)
            if any(value in (None, "") for value in required):
                raise ValueError("reviewed sources require publisher, url, access date, and reviewer metadata")
        return self


class FactRecord(StrictModel):
    fact_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)
    risk_type: RiskType
    severity: Severity
    severity_rationale: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    source_locator: str | None = None
    review_status: ReviewStatus = ReviewStatus.DRAFT
    label_status: LabelStatus = LabelStatus.LEGACY_UNREVIEWED
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    data_version: str = Field(min_length=1)
    required_context: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def reviewed_facts_have_evidence(self):
        if self.review_status == ReviewStatus.REVIEWED:
            if not self.source_ids or not self.source_locator or not self.reviewed_by or not self.reviewed_at:
                raise ValueError("reviewed facts require sources, a locator, and reviewer metadata")
            if self.label_status == LabelStatus.LEGACY_UNREVIEWED:
                raise ValueError("reviewed facts cannot retain a legacy_unreviewed label status")
        return self


class EvidenceFact(StrictModel):
    fact_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)
    risk_type: RiskType
    severity: Severity
    severity_rationale: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)
    source_locator: str = Field(min_length=1)
    label_status: LabelStatus


class MedicationRecord(StrictModel):
    medication_id: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    kind: MedicationKind
    aliases: list[str] = Field(default_factory=list)
    active_ingredients: list[str] = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)
    source_locator: str = Field(min_length=1)
    review_status: ReviewStatus = ReviewStatus.DRAFT
    label_status: LabelStatus = LabelStatus.LEGACY_UNREVIEWED
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    data_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def reviewed_medications_are_traceable(self):
        if self.review_status == ReviewStatus.REVIEWED:
            if self.label_status == LabelStatus.LEGACY_UNREVIEWED:
                raise ValueError("reviewed medications cannot retain legacy_unreviewed status")
            if not self.reviewed_by or not self.reviewed_at:
                raise ValueError("reviewed medications require reviewer metadata")
        return self


class ClinicalContextRecord(StrictModel):
    context_id: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    kind: ContextKind
    aliases: list[str] = Field(default_factory=list)
    description: str = Field(min_length=1)
    review_status: ReviewStatus = ReviewStatus.DRAFT
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    data_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def reviewed_contexts_have_review_metadata(self):
        if self.review_status == ReviewStatus.REVIEWED:
            if not self.reviewed_by or not self.reviewed_at:
                raise ValueError("reviewed contexts require reviewer metadata")
        return self


class EvidencePacket(StrictModel):
    conclusion_status: ConclusionStatus
    facts: list[EvidenceFact] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    resolved_medications: list[str] = Field(default_factory=list)
    unresolved_inputs: list[str] = Field(default_factory=list)
    resolved_contexts: list[str] = Field(default_factory=list)
    unresolved_contexts: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    data_version: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def risk_conclusions_require_facts(self):
        if self.conclusion_status == ConclusionStatus.RISK_FOUND and not self.facts:
            raise ValueError("risk_found requires at least one evidence fact")
        if self.conclusion_status != ConclusionStatus.RISK_FOUND and self.facts:
            raise ValueError("non-risk conclusions must not contain risk facts")
        if (
            self.conclusion_status != ConclusionStatus.KNOWLEDGE_UNAVAILABLE
            and self.data_version is None
        ):
            raise ValueError("available knowledge conclusions require a data version")
        return self


class ExplanationPlan(StrictModel):
    """The complete set of decisions an LLM may make for a V1 explanation."""

    conclusion_status: ConclusionStatus
    ordered_fact_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def fact_ids_match_conclusion_shape(self):
        if self.conclusion_status == ConclusionStatus.RISK_FOUND and not self.ordered_fact_ids:
            raise ValueError("risk_found plans require fact IDs")
        if self.conclusion_status != ConclusionStatus.RISK_FOUND and self.ordered_fact_ids:
            raise ValueError("non-risk plans must not contain fact IDs")
        return self


class ExplanationClaim(StrictModel):
    """An extractive claim copied from one validated Evidence Fact."""

    fact_id: str = Field(min_length=1)
    risk_type: RiskType
    severity: Severity
    statement: str = Field(min_length=1)
    severity_rationale: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)
    source_locator: str = Field(min_length=1)
    label_status: LabelStatus


class SafetyExplanation(StrictModel):
    """User-facing V1 explanation with machine-checkable evidence links."""

    conclusion_status: ConclusionStatus
    summary: str = Field(min_length=1)
    claims: list[ExplanationClaim] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    resolved_medications: list[str] = Field(default_factory=list)
    unresolved_inputs: list[str] = Field(default_factory=list)
    resolved_contexts: list[str] = Field(default_factory=list)
    unresolved_contexts: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    data_version: str | None = Field(default=None, min_length=1)
    generation_mode: ExplanationGenerationMode
    prompt_version: str = Field(min_length=1)
    fallback_reason: ExplanationFallbackReason | None = None

    @model_validator(mode="after")
    def claims_match_conclusion(self):
        if self.conclusion_status == ConclusionStatus.RISK_FOUND and not self.claims:
            raise ValueError("risk_found explanations require at least one claim")
        if self.conclusion_status != ConclusionStatus.RISK_FOUND and self.claims:
            raise ValueError("non-risk explanations must not contain claims")
        if (
            self.generation_mode == ExplanationGenerationMode.DETERMINISTIC_FALLBACK
            and self.fallback_reason is None
        ):
            raise ValueError("deterministic fallback requires a reason")
        if (
            self.generation_mode != ExplanationGenerationMode.DETERMINISTIC_FALLBACK
            and self.fallback_reason is not None
        ):
            raise ValueError("fallback reason is only valid for deterministic fallback")
        claim_ids = [claim.fact_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("explanations must not contain duplicate fact IDs")
        if (
            self.conclusion_status != ConclusionStatus.KNOWLEDGE_UNAVAILABLE
            and self.data_version is None
        ):
            raise ValueError("available knowledge explanations require a data version")
        return self


class ConversationTurn(StrictModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1)


class ExpectedResult(StrictModel):
    drugs: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    conclusion_status: ConclusionStatus | None = None
    required_fact_ids: list[str] = Field(default_factory=list)


class EvaluationCase(StrictModel):
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    split: str = Field(pattern="^(dev|test)$")
    category: str = Field(min_length=1)
    question: str = Field(min_length=1)
    history: list[ConversationTurn] = Field(default_factory=list)
    expected: ExpectedResult
    label_status: LabelStatus = LabelStatus.LEGACY_UNREVIEWED
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reviewed_labels_require_a_conclusion(self):
        if self.label_status != LabelStatus.LEGACY_UNREVIEWED and self.expected.conclusion_status is None:
            raise ValueError("reviewed evaluation labels require an expected conclusion")
        return self
