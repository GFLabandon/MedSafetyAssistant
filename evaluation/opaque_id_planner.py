"""Locked synthetic test for opaque fact-ID copying and severity ordering."""

from __future__ import annotations

from collections.abc import Iterable
from math import ceil
from statistics import median
from typing import Any

from pydantic import ValidationError

from medsafety.contracts import (
    ConclusionStatus,
    EvidenceFact,
    EvidencePacket,
    ExplanationPlan,
    LabelStatus,
    OpaquePlannerCase,
)
from medsafety.ollama_planner import OllamaExplanationPlanner


def _packet_for_case(case: OpaquePlannerCase) -> EvidencePacket:
    return EvidencePacket(
        conclusion_status=ConclusionStatus.RISK_FOUND,
        facts=[
            EvidenceFact(
                fact_id=fact.fact_id,
                subject="synthetic-contract-probe",
                predicate="OPAQUE_ID_ORDERING",
                object=case.case_id,
                risk_type=fact.risk_type,
                severity=fact.severity,
                severity_rationale="Synthetic severity used only to test ordering behavior.",
                reason="Synthetic contract probe with no medical meaning.",
                source_ids=["synthetic-contract-source"],
                source_locator=f"{case.dataset_version}:{case.case_id}",
                label_status=LabelStatus.LEGACY_UNREVIEWED,
            )
            for fact in case.facts
        ],
        limitations=["Synthetic contract test; contains no medical conclusion."],
        data_version=case.dataset_version,
    )


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, ceil(percentile * len(ordered)) - 1)], 3)


def evaluate_opaque_id_planner(
    cases: Iterable[OpaquePlannerCase],
    planner: OllamaExplanationPlanner,
    *,
    repetitions: int = 3,
) -> dict[str, Any]:
    if repetitions < 3:
        raise ValueError("locked model evaluation requires at least 3 repetitions")
    case_list = list(cases)
    versions = {case.dataset_version for case in case_list}
    if len(versions) != 1:
        raise ValueError("locked opaque planner cases require one dataset version")

    records = []
    failures = []
    ordering_failures = []
    latencies = []
    valid_plans = 0
    exact_orders = 0
    expected_references = 0
    exact_references = 0
    raw_plans_by_case: dict[str, list[str]] = {}

    for repetition in range(1, repetitions + 1):
        for case in case_list:
            packet = _packet_for_case(case)
            expected_ids = {fact.fact_id for fact in packet.facts}
            attempt = planner.generate_attempt(packet)
            latencies.append(attempt.latency_ms)
            raw_key = (
                str(attempt.parsed_payload)
                if attempt.parsed_payload is not None
                else str((attempt.error_category, attempt.raw_response))
            )
            raw_plans_by_case.setdefault(case.case_id, []).append(raw_key)

            plan = None
            validation_error = None
            if attempt.error_category is None:
                try:
                    plan = ExplanationPlan.model_validate(attempt.parsed_payload)
                except (ValidationError, TypeError, ValueError) as exc:
                    validation_error = type(exc).__name__

            planned_ids = plan.ordered_fact_ids if plan is not None else []
            valid = (
                plan is not None
                and plan.conclusion_status == ConclusionStatus.RISK_FOUND
                and len(planned_ids) == len(set(planned_ids))
                and set(planned_ids) == expected_ids
            )
            exact_order = valid and planned_ids == case.expected_ordered_fact_ids
            valid_plans += int(valid)
            exact_orders += int(exact_order)
            expected_references += len(expected_ids)
            exact_references += len(expected_ids & set(planned_ids))

            record = {
                "repetition": repetition,
                "case_id": case.case_id,
                "expected_ordered_fact_ids": case.expected_ordered_fact_ids,
                "planned_fact_ids": planned_ids,
                "valid_plan": valid,
                "exact_order": exact_order,
                "attempt": attempt.to_dict(),
            }
            records.append(record)
            if not valid:
                failures.append(
                    {
                        "repetition": repetition,
                        "case_id": case.case_id,
                        "attempt_error_category": attempt.error_category,
                        "attempt_error_type": attempt.error_type,
                        "validation_error": validation_error,
                        "expected_fact_ids": sorted(expected_ids),
                        "planned_fact_ids": planned_ids,
                    }
                )
            elif not exact_order:
                ordering_failures.append(
                    {
                        "repetition": repetition,
                        "case_id": case.case_id,
                        "expected_ordered_fact_ids": case.expected_ordered_fact_ids,
                        "planned_fact_ids": planned_ids,
                    }
                )

    total_attempts = len(case_list) * repetitions
    consistent_cases = sum(
        1
        for case in case_list
        if len(raw_plans_by_case.get(case.case_id, [])) == repetitions
        and len(set(raw_plans_by_case[case.case_id])) == 1
    )
    return {
        "runner": "ollama_opaque_ids",
        "dataset_type": "locked_synthetic_contract_test",
        "dataset_version": versions.pop(),
        "dataset_cases": len(case_list),
        "repetitions": repetitions,
        "planner_attempts": total_attempts,
        "prompt_version": planner.prompt_version,
        "generation_options": dict(planner.options),
        "metrics": {
            "valid_plan_rate": valid_plans / total_attempts if total_attempts else 0.0,
            "exact_severity_order_rate": (
                exact_orders / total_attempts if total_attempts else 0.0
            ),
            "character_exact_reference_rate": (
                exact_references / expected_references if expected_references else 1.0
            ),
            "raw_plan_consistency_rate": (
                consistent_cases / len(case_list) if case_list else 0.0
            ),
            "planner_latency_ms_p50": round(median(latencies), 3) if latencies else None,
            "planner_latency_ms_p95": _percentile(latencies, 0.95),
        },
        "failures": failures,
        "ordering_failures": ordering_failures,
        "records": records,
        "interpretation_boundary": (
            "Locked synthetic contract test for ID copying and ordering only; contains no "
            "medical facts and does not measure clinical quality."
        ),
    }


def render_opaque_id_markdown(report: dict[str, Any], dataset_name: str) -> str:
    metrics = report["metrics"]
    model = report["model"]
    return "\n".join(
        [
            "# Locked Opaque Fact-ID Planner Test",
            "",
            f"Dataset: `{dataset_name}`",
            f"Dataset SHA-256: `{report['dataset_sha256']}`",
            f"Dataset version: `{report['dataset_version']}`",
            f"Prompt version: `{report['prompt_version']}`",
            f"Model: `{model['name']}`",
            f"Model digest: `{model['digest']}`",
            f"Code commit: `{report['code_commit']}`",
            f"Working tree dirty at run: `{str(report['working_tree_dirty']).lower()}`",
            f"Cases: {report['dataset_cases']}",
            f"Repetitions: {report['repetitions']}",
            f"Planner attempts: {report['planner_attempts']}",
            "",
            "## Metrics",
            "",
            "| Metric | Result |",
            "|---|---:|",
            f"| Valid plan rate | {metrics['valid_plan_rate']:.3f} |",
            f"| Exact severity order rate | {metrics['exact_severity_order_rate']:.3f} |",
            f"| Character-exact reference rate | {metrics['character_exact_reference_rate']:.3f} |",
            f"| Raw plan consistency rate | {metrics['raw_plan_consistency_rate']:.3f} |",
            f"| Planner latency P50 | {metrics['planner_latency_ms_p50']:.3f} ms |",
            f"| Planner latency P95 | {metrics['planner_latency_ms_p95']:.3f} ms |",
            "",
            "## Failures",
            "",
            f"Invalid plans: {len(report['failures'])}",
            f"Ordering failures: {len(report['ordering_failures'])}",
            "",
            "## Interpretation Boundary",
            "",
            report["interpretation_boundary"],
            "",
        ]
    )
