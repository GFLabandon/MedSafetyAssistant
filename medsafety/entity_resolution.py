"""Deterministic, catalog-bound input resolution for the V1 safety flow."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from medsafety.catalog import KnowledgeCatalog
from medsafety.contracts import (
    EntityMatchType,
    InputResolution,
    InputResolutionStatus,
    InputSafetyFlag,
    ResolvedEntity,
    ResolvedEntityKind,
)


ENTITY_RESOLUTION_VERSION = "entity-resolution-v1"
MAX_QUESTION_LENGTH = 500

_GENERIC_MEDICATION_TERMS = (
    "感冒药",
    "退烧药",
    "止痛药",
    "消炎药",
    "过敏药",
)
_FOLLOW_UP_REFERENCES = (
    "这个药",
    "那个药",
    "上述药",
    "刚才的药",
    "之前的药",
    "它",
)
_INSTRUCTION_MARKERS = (
    "忽略之前",
    "忽略所有",
    "系统提示",
    "system prompt",
    "developer message",
    "不要遵守",
    "绕过规则",
)


@dataclass(frozen=True)
class _AliasEntry:
    alias: str
    record_id: str
    canonical_name: str
    kind: ResolvedEntityKind


class V1EntityResolver:
    """Resolve only catalog-backed entities; never ask an LLM to invent one."""

    def __init__(self, catalog: KnowledgeCatalog):
        self._catalog = catalog
        self._medication_aliases = self._build_medication_aliases()
        self._context_aliases = self._build_context_aliases()
        self._contexts_by_name = {
            context.canonical_name: context for context in catalog.contexts.values()
        }

    def resolve(self, question: str) -> InputResolution:
        raw_question = question.strip()
        safety_flags = self._input_safety_flags(raw_question)
        if InputSafetyFlag.INPUT_TOO_LONG in safety_flags:
            return self._rejected(safety_flags)
        if InputSafetyFlag.CONTROL_CHARACTER_REJECTED in safety_flags:
            return self._rejected(safety_flags)

        normalized_question = " ".join(raw_question.split())
        entities = self._match_aliases(normalized_question, self._medication_aliases)
        entities.extend(self._match_aliases(normalized_question, self._context_aliases))
        entities.extend(self._infer_contexts(normalized_question, entities))
        entities = self._deduplicate_entities(entities)

        medications = [
            entity.canonical_name
            for entity in entities
            if entity.kind == ResolvedEntityKind.MEDICATION
        ]
        contexts = [
            entity.canonical_name
            for entity in entities
            if entity.kind == ResolvedEntityKind.CONTEXT
        ]

        generic_terms = [
            term for term in _GENERIC_MEDICATION_TERMS if term in normalized_question
        ]
        follow_up_terms = [
            term for term in _FOLLOW_UP_REFERENCES if term in normalized_question
        ]
        if generic_terms and medications:
            return InputResolution(
                status=InputResolutionStatus.AMBIGUOUS,
                medications=medications,
                contexts=contexts,
                entities=entities,
                unresolved_mentions=generic_terms,
                clarification_question="请补充未明确药品的具体商品名或成分名。",
                safety_flags=safety_flags,
            )

        if follow_up_terms and medications:
            return InputResolution(
                status=InputResolutionStatus.AMBIGUOUS,
                medications=medications,
                contexts=contexts,
                entities=entities,
                unresolved_mentions=follow_up_terms,
                clarification_question="请补充代词所指的具体药品名称。",
                safety_flags=safety_flags,
            )

        if medications:
            return InputResolution(
                status=InputResolutionStatus.RESOLVED,
                medications=medications,
                contexts=contexts,
                entities=entities,
                safety_flags=safety_flags,
            )

        if generic_terms:
            return InputResolution(
                status=InputResolutionStatus.AMBIGUOUS,
                entities=entities,
                unresolved_mentions=generic_terms,
                clarification_question="请提供包装上的具体商品名或成分名。",
                safety_flags=safety_flags,
            )

        if follow_up_terms:
            return InputResolution(
                status=InputResolutionStatus.NEEDS_CLARIFICATION,
                entities=entities,
                unresolved_mentions=follow_up_terms,
                clarification_question="当前查询不读取共享历史，请重新写出具体药品名称。",
                safety_flags=safety_flags,
            )

        return InputResolution(
            status=InputResolutionStatus.UNKNOWN,
            entities=entities,
            unresolved_mentions=self._unknown_mentions(normalized_question),
            clarification_question="未识别到当前 V1 目录中的药品，请提供具体商品名或成分名。",
            safety_flags=safety_flags,
        )

    def _build_medication_aliases(self) -> list[_AliasEntry]:
        entries = []
        for medication in self._catalog.medications.values():
            for alias in [medication.canonical_name, *medication.aliases]:
                entries.append(
                    _AliasEntry(
                        alias=alias,
                        record_id=medication.medication_id,
                        canonical_name=medication.canonical_name,
                        kind=ResolvedEntityKind.MEDICATION,
                    )
                )
        return self._unique_aliases(entries)

    def _build_context_aliases(self) -> list[_AliasEntry]:
        entries = []
        for context in self._catalog.contexts.values():
            for alias in [context.canonical_name, *context.aliases]:
                entries.append(
                    _AliasEntry(
                        alias=alias,
                        record_id=context.context_id,
                        canonical_name=context.canonical_name,
                        kind=ResolvedEntityKind.CONTEXT,
                    )
                )
        return self._unique_aliases(entries)

    @staticmethod
    def _unique_aliases(entries: list[_AliasEntry]) -> list[_AliasEntry]:
        unique = {}
        for entry in entries:
            key = (entry.alias.casefold(), entry.record_id, entry.kind)
            unique[key] = entry
        return sorted(unique.values(), key=lambda entry: len(entry.alias), reverse=True)

    @staticmethod
    def _match_aliases(question: str, entries: list[_AliasEntry]) -> list[ResolvedEntity]:
        matches = []
        folded_question = question.casefold()
        seen_records = set()
        for entry in entries:
            if entry.record_id in seen_records:
                continue
            folded_alias = entry.alias.casefold()
            if folded_alias.isascii() and folded_alias.replace(" ", "").isalnum():
                pattern = rf"(?<![a-z0-9]){re.escape(folded_alias)}(?![a-z0-9])"
                match = re.search(pattern, folded_question)
                match_start = match.start() if match else None
                matched_text = question[match.start() : match.end()] if match else None
            else:
                index = folded_question.find(folded_alias)
                match_start = index if index >= 0 else None
                matched_text = (
                    question[index : index + len(entry.alias)] if index >= 0 else None
                )
            if matched_text is None:
                continue
            matches.append(
                (
                    match_start,
                    ResolvedEntity(
                        kind=entry.kind,
                        record_id=entry.record_id,
                        canonical_name=entry.canonical_name,
                        matched_text=matched_text,
                        match_type=EntityMatchType.ALIAS,
                    ),
                )
            )
            seen_records.add(entry.record_id)
        return [entity for _, entity in sorted(matches, key=lambda item: item[0])]

    def _infer_contexts(
        self,
        question: str,
        existing_entities: list[ResolvedEntity],
    ) -> list[ResolvedEntity]:
        existing_ids = {entity.record_id for entity in existing_entities}
        inferred = []
        folded = question.casefold()

        cardioprotection = self._contexts_by_name.get("阿司匹林用于心血管保护")
        if (
            cardioprotection
            and cardioprotection.context_id not in existing_ids
            and ("阿司匹林" in question or "aspirin" in folded)
            and "心血管" in question
            and ("预防" in question or "保护" in question or "低剂量" in question)
        ):
            inferred.append(
                ResolvedEntity(
                    kind=ResolvedEntityKind.CONTEXT,
                    record_id=cardioprotection.context_id,
                    canonical_name=cardioprotection.canonical_name,
                    matched_text="心血管预防",
                    match_type=EntityMatchType.CONTEXT_RULE,
                )
            )

        reaction_history = self._contexts_by_name.get(
            "服用阿司匹林或其他NSAID后出现哮喘、荨麻疹或过敏反应"
        )
        has_nsaid_reference = any(
            marker in folded for marker in ("阿司匹林", "aspirin", "nsaid", "非甾体")
        )
        has_reaction = any(
            marker in question for marker in ("过敏", "荨麻疹", "吃后哮喘", "服用后哮喘")
        )
        if (
            reaction_history
            and reaction_history.context_id not in existing_ids
            and has_nsaid_reference
            and has_reaction
        ):
            matched_text = next(
                marker
                for marker in ("过敏", "荨麻疹", "吃后哮喘", "服用后哮喘")
                if marker in question
            )
            inferred.append(
                ResolvedEntity(
                    kind=ResolvedEntityKind.CONTEXT,
                    record_id=reaction_history.context_id,
                    canonical_name=reaction_history.canonical_name,
                    matched_text=matched_text,
                    match_type=EntityMatchType.CONTEXT_RULE,
                )
            )

        return inferred

    @staticmethod
    def _deduplicate_entities(entities: list[ResolvedEntity]) -> list[ResolvedEntity]:
        unique = {}
        for entity in entities:
            key = (entity.kind, entity.record_id)
            existing = unique.get(key)
            if existing is None or (
                existing.match_type == EntityMatchType.CONTEXT_RULE
                and entity.match_type == EntityMatchType.ALIAS
            ):
                unique[key] = entity
        return list(unique.values())

    @staticmethod
    def _input_safety_flags(question: str) -> list[InputSafetyFlag]:
        flags = []
        if len(question) > MAX_QUESTION_LENGTH:
            flags.append(InputSafetyFlag.INPUT_TOO_LONG)
        if any(
            unicodedata.category(character) == "Cc"
            and character not in {"\n", "\r", "\t"}
            for character in question
        ):
            flags.append(InputSafetyFlag.CONTROL_CHARACTER_REJECTED)
        folded = question.casefold()
        if any(marker in folded for marker in _INSTRUCTION_MARKERS):
            flags.append(InputSafetyFlag.INSTRUCTION_LIKE_TEXT_IGNORED)
        return flags

    @staticmethod
    def _unknown_mentions(question: str) -> list[str]:
        direct_candidate = re.fullmatch(
            r"[\w\u4e00-\u9fff-]{1,30}(?:片|胶囊|颗粒|口服液)?",
            question,
        )
        if direct_candidate:
            return [direct_candidate.group(0)]
        return ["未识别药品"]

    @staticmethod
    def _rejected(flags: list[InputSafetyFlag]) -> InputResolution:
        return InputResolution(
            status=InputResolutionStatus.REJECTED_INPUT,
            clarification_question=None,
            safety_flags=flags,
        )
