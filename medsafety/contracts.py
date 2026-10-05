"""Versioned data and API-neutral contracts for evidence-grounded evaluation.

These models do not replace the existing runtime yet. They define the boundary
that new data, evaluation, and Safety Engine work must satisfy.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

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
    ACTIVITY_RESTRICTION = "ACTIVITY_RESTRICTION"


class MedicationKind(str, Enum):
    PRODUCT = "product"
    SUBSTANCE = "substance"


class ContextKind(str, Enum):
    MEDICATION_USE = "medication_use"
    REACTION_HISTORY = "reaction_history"
    ACTIVITY = "activity"


class LabelStatus(str, Enum):
    LEGACY_UNREVIEWED = "legacy_unreviewed"
    SOURCE_ALIGNED = "source_aligned"
    CLINICALLY_REVIEWED = "clinically_reviewed"


class InputResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED_INPUT = "rejected_input"


class ResolvedEntityKind(str, Enum):
    MEDICATION = "medication"
    CONTEXT = "context"


class KnowledgeEntityKind(str, Enum):
    INGREDIENT = "ingredient"
    MEDICATION = "medication"
    CONTEXT = "context"


class EntityMatchType(str, Enum):
    ALIAS = "alias"
    CONTEXT_RULE = "context_rule"
    SESSION_CONTEXT = "session_context"


class InputSafetyFlag(str, Enum):
    INSTRUCTION_LIKE_TEXT_IGNORED = "instruction_like_text_ignored"
    INPUT_TOO_LONG = "input_too_long"
    CONTROL_CHARACTER_REJECTED = "control_character_rejected"


class ResolvedEntity(StrictModel):
    kind: ResolvedEntityKind
    record_id: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    matched_text: str = Field(min_length=1)
    match_type: EntityMatchType


class InputResolution(StrictModel):
    schema_version: Literal["entity-resolution-v1"] = "entity-resolution-v1"
    status: InputResolutionStatus
    medications: list[str] = Field(default_factory=list)
    contexts: list[str] = Field(default_factory=list)
    entities: list[ResolvedEntity] = Field(default_factory=list)
    unresolved_mentions: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    safety_flags: list[InputSafetyFlag] = Field(default_factory=list)

    @model_validator(mode="after")
    def status_matches_resolution_shape(self):
        if self.status == InputResolutionStatus.RESOLVED and not self.medications:
            raise ValueError("resolved input requires at least one medication")
        if self.status in {
            InputResolutionStatus.AMBIGUOUS,
            InputResolutionStatus.UNKNOWN,
            InputResolutionStatus.NEEDS_CLARIFICATION,
        } and not self.clarification_question:
            raise ValueError("unresolved input requires a clarification question")
        if self.status == InputResolutionStatus.REJECTED_INPUT:
            if self.medications or self.contexts or self.entities:
                raise ValueError("rejected input cannot contain resolved entities")
            if not self.safety_flags:
                raise ValueError("rejected input requires a safety flag")
        return self


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
    subject_kind: KnowledgeEntityKind = KnowledgeEntityKind.INGREDIENT
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)
    object_kind: KnowledgeEntityKind | None = None
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

    @model_validator(mode="before")
    @classmethod
    def infer_legacy_endpoint_kinds(cls, values):
        if not isinstance(values, dict):
            return values
        normalized = dict(values)
        normalized.setdefault("subject_kind", KnowledgeEntityKind.INGREDIENT)
        if normalized.get("object_kind") is None:
            normalized["object_kind"] = (
                KnowledgeEntityKind.CONTEXT
                if normalized.get("predicate")
                in {"CONTRAINDICATED_IN", "ACTIVITY_RESTRICTION"}
                else KnowledgeEntityKind.INGREDIENT
            )
        return normalized

    @model_validator(mode="after")
    def reviewed_facts_have_evidence(self):
        if self.review_status == ReviewStatus.REVIEWED:
            if not self.source_ids or not self.source_locator or not self.reviewed_by or not self.reviewed_at:
                raise ValueError("reviewed facts require sources, a locator, and reviewer metadata")
            if self.label_status == LabelStatus.LEGACY_UNREVIEWED:
                raise ValueError("reviewed facts cannot retain a legacy_unreviewed label status")
        return self

    @model_validator(mode="after")
    def predicate_matches_endpoint_and_risk_types(self):
        expected = {
            "DUPLICATE_INGREDIENT": (
                KnowledgeEntityKind.INGREDIENT,
                KnowledgeEntityKind.INGREDIENT,
                RiskType.DUPLICATE_THERAPY,
            ),
            "INTERACTS_WITH": (
                KnowledgeEntityKind.INGREDIENT,
                KnowledgeEntityKind.INGREDIENT,
                RiskType.INTERACTION,
            ),
            "CONTRAINDICATED_IN": (
                KnowledgeEntityKind.INGREDIENT,
                KnowledgeEntityKind.CONTEXT,
                RiskType.CONTRAINDICATION,
            ),
            "ACTIVITY_RESTRICTION": (
                KnowledgeEntityKind.MEDICATION,
                KnowledgeEntityKind.CONTEXT,
                RiskType.ACTIVITY_RESTRICTION,
            ),
        }.get(self.predicate)
        if expected is None:
            return self
        expected_subject, expected_object, expected_risk = expected
        if (self.subject_kind, self.object_kind) != (
            expected_subject,
            expected_object,
        ):
            raise ValueError("fact predicate has incompatible endpoint kinds")
        if self.risk_type != expected_risk:
            raise ValueError("fact predicate has incompatible risk type")
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


class KnowledgeEntityReference(StrictModel):
    kind: KnowledgeEntityKind
    identifier: str = Field(min_length=1)
    name: str = Field(min_length=1)


class KnowledgeSnapshotReference(StrictModel):
    name: str = Field(min_length=1)
    data_version: str = Field(min_length=1)


class FactProvenance(StrictModel):
    """One reviewed fact and every graph edge needed to audit its conclusion."""

    schema_version: Literal["fact-provenance-v2"] = "fact-provenance-v2"
    fact: FactRecord
    subject: KnowledgeEntityReference
    object: KnowledgeEntityReference
    applies_in: list[ClinicalContextRecord] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(min_length=1)
    snapshot: KnowledgeSnapshotReference

    @model_validator(mode="after")
    def graph_edges_match_fact_properties(self):
        if self.subject.kind != self.fact.subject_kind:
            raise ValueError("SUBJECT endpoint kind disagrees with the fact contract")
        if self.subject.name != self.fact.subject:
            raise ValueError("SUBJECT relationship disagrees with the fact subject")
        if self.object.name != self.fact.object:
            raise ValueError("OBJECT relationship disagrees with the fact object")
        if self.object.kind != self.fact.object_kind:
            raise ValueError("OBJECT endpoint kind disagrees with the fact contract")
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)) or set(source_ids) != set(
            self.fact.source_ids
        ):
            raise ValueError("SUPPORTED_BY relationships disagree with fact source IDs")
        context_names = [context.canonical_name for context in self.applies_in]
        if len(context_names) != len(set(context_names)) or set(context_names) != set(
            self.fact.required_context
        ):
            raise ValueError("APPLIES_IN relationships disagree with required contexts")
        if self.snapshot.data_version != self.fact.data_version:
            raise ValueError("BELONGS_TO snapshot version disagrees with fact version")
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


class PipelineStageTrace(StrictModel):
    name: Literal["entity_resolution", "safety_engine", "evidence_explanation"]
    status: Literal["completed", "skipped", "degraded"]
    duration_ms: float = Field(ge=0)


class RequestTrace(StrictModel):
    schema_version: Literal["request-trace-v1"] = "request-trace-v1"
    request_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    total_duration_ms: float = Field(ge=0)
    stages: list[PipelineStageTrace] = Field(min_length=3, max_length=3)
    resolution_status: InputResolutionStatus
    conclusion_status: ConclusionStatus


class SafetyQueryResponse(StrictModel):
    """Natural-language V1 response with explicit input and evidence boundaries."""

    resolution: InputResolution
    explanation: SafetyExplanation
    trace: RequestTrace


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


class ExplanationGuardrailCase(StrictModel):
    """Scripted planner output used to regression-test generation guardrails."""

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    medications: list[str] = Field(min_length=1)
    contexts: list[str] = Field(default_factory=list)
    use_llm_plan: bool = True
    planner_result: dict[str, Any] | str | None = None
    planner_error: bool = False
    expected_generation_mode: ExplanationGenerationMode
    expected_fallback_reason: ExplanationFallbackReason | None = None

    @model_validator(mode="after")
    def fixture_and_expectation_are_consistent(self):
        if self.planner_error and self.planner_result is not None:
            raise ValueError("planner error cases cannot also define a planner result")
        if (
            self.expected_generation_mode == ExplanationGenerationMode.DETERMINISTIC_FALLBACK
            and self.expected_fallback_reason is None
        ):
            raise ValueError("expected fallback mode requires a fallback reason")
        if (
            self.expected_generation_mode != ExplanationGenerationMode.DETERMINISTIC_FALLBACK
            and self.expected_fallback_reason is not None
        ):
            raise ValueError("fallback reason is only valid for expected fallback mode")
        return self


class OpaquePlannerFact(StrictModel):
    """Synthetic, non-medical fact metadata for a locked planner contract test."""

    fact_id: str = Field(min_length=1)
    risk_type: RiskType
    severity: Severity


class OpaquePlannerCase(StrictModel):
    """Held-out fact-ID copying and ordering case with no clinical content."""

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    split: str = Field(pattern="^test$")
    dataset_version: str = Field(min_length=1)
    facts: list[OpaquePlannerFact] = Field(min_length=1)
    expected_ordered_fact_ids: list[str] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def expected_order_is_a_complete_permutation(self):
        fact_ids = [fact.fact_id for fact in self.facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("opaque planner facts require unique fact IDs")
        if len(self.expected_ordered_fact_ids) != len(
            set(self.expected_ordered_fact_ids)
        ):
            raise ValueError("expected fact ID order must not contain duplicates")
        if set(self.expected_ordered_fact_ids) != set(fact_ids):
            raise ValueError("expected fact ID order must contain every fact exactly once")
        return self
