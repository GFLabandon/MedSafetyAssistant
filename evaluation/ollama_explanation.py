"""Repeatable real-Ollama evaluation for evidence explanation planning."""

from __future__ import annotations

from collections.abc import Iterable
from math import ceil
from statistics import median
from typing import Any

from medsafety.contracts import EvaluationCase
from medsafety.explanation import (
    EvidenceGroundedExplainer,
    PROMPT_VERSION as EXPLANATION_CONTRACT_VERSION,
)
from medsafety.ollama_planner import OllamaExplanationPlanner, OllamaPlanAttempt
from medsafety.safety_engine import SafetyEngine

class _RecordedAttemptPlanner:
    def __init__(self, attempt: OllamaPlanAttempt):
        self.attempt = attempt

    def plan(self, packet):
        if self.attempt.error_category == "request_error":
            raise ConnectionError("recorded Ollama request failure")
        if self.attempt.error_category is not None:
            raise ValueError(f"recorded {self.attempt.error_category}")
        return self.attempt.parsed_payload


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, ceil(percentile * len(ordered)) - 1)], 3)


def _plan_failure_details(
    attempt: OllamaPlanAttempt,
    expected_status: str,
    expected_fact_ids: set[str],
) -> dict[str, Any]:
    if attempt.error_category is not None:
        return {"failure_category": attempt.error_category}
    payload = attempt.parsed_payload
    if not isinstance(payload, dict):
        return {"failure_category": "invalid_plan_shape"}
    extra_fields = sorted(set(payload) - {"conclusion_status", "ordered_fact_ids"})
    if extra_fields:
        return {"failure_category": "extra_fields", "extra_fields": extra_fields}
    if payload.get("conclusion_status") != expected_status:
        return {
            "failure_category": "conclusion_mismatch",
            "model_conclusion_status": payload.get("conclusion_status"),
        }
    planned_ids = payload.get("ordered_fact_ids")
    if not isinstance(planned_ids, list) or not all(
        isinstance(item, str) for item in planned_ids
    ):
        return {"failure_category": "invalid_fact_id_list"}
    duplicates = sorted({item for item in planned_ids if planned_ids.count(item) > 1})
    unknown = sorted(set(planned_ids) - expected_fact_ids)
    missing = sorted(expected_fact_ids - set(planned_ids))
    if duplicates:
        return {"failure_category": "duplicate_fact_ids", "duplicate_fact_ids": duplicates}
    if unknown or missing:
        return {
            "failure_category": "fact_id_mismatch",
            "unknown_fact_ids": unknown,
            "missing_fact_ids": missing,
        }
    return {"failure_category": "contract_validation_error"}


def evaluate_ollama_explanations(
    cases: Iterable[EvaluationCase],
    engine: SafetyEngine,
    planner: OllamaExplanationPlanner,
    *,
    repetitions: int = 3,
) -> dict[str, Any]:
    if repetitions < 3:
        raise ValueError("real-model evaluation requires at least 3 repetitions")

    case_list = list(cases)
    records = []
    model_failures = []
    pipeline_failures = []
    latencies = []
    total_claims = 0
    grounded_claims = 0
    source_traceable_claims = 0
    expected_references = 0
    retained_references = 0
    engine_matches = 0
    conclusion_matches = 0
    pipeline_passes = 0
    planner_attempts = 0
    valid_plans = 0
    fallbacks = 0
    plans_by_case: dict[str, list[tuple[str, ...]]] = {}
    raw_plans_by_case: dict[str, list[str]] = {}

    for repetition in range(1, repetitions + 1):
        for case in case_list:
            medications = case.metadata.get("medications")
            contexts = case.metadata.get("contexts", [])
            if not isinstance(medications, list) or not all(
                isinstance(item, str) for item in medications
            ):
                raise ValueError(f"case {case.case_id} requires metadata.medications")
            if not isinstance(contexts, list) or not all(
                isinstance(item, str) for item in contexts
            ):
                raise ValueError(f"case {case.case_id} requires metadata.contexts")

            packet = engine.assess(medications, contexts=contexts)
            expected_status = case.expected.conclusion_status
            expected_fact_ids = set(case.expected.required_fact_ids)
            packet_fact_ids = {fact.fact_id for fact in packet.facts}
            engine_match = (
                packet.conclusion_status == expected_status
                and packet_fact_ids == expected_fact_ids
            )
            engine_matches += int(engine_match)

            attempt = None
            if packet.facts:
                planner_attempts += 1
                attempt = planner.generate_attempt(packet)
                latencies.append(attempt.latency_ms)
                raw_plan_key = (
                    str(attempt.parsed_payload)
                    if attempt.parsed_payload is not None
                    else str((attempt.error_category, attempt.raw_response))
                )
                raw_plans_by_case.setdefault(case.case_id, []).append(raw_plan_key)
                explanation = EvidenceGroundedExplainer(
                    _RecordedAttemptPlanner(attempt)
                ).explain(packet)
            else:
                explanation = EvidenceGroundedExplainer(planner).explain(packet)

            if explanation.generation_mode.value == "llm_planned":
                valid_plans += 1
                plan_order = tuple(claim.fact_id for claim in explanation.claims)
                plans_by_case.setdefault(case.case_id, []).append(plan_order)
            elif explanation.generation_mode.value == "deterministic_fallback":
                fallbacks += 1
                failure = {
                        "repetition": repetition,
                        "case_id": case.case_id,
                        "fallback_reason": explanation.fallback_reason.value,
                        "attempt_error_category": (
                            attempt.error_category if attempt is not None else None
                        ),
                        "attempt_error_type": attempt.error_type if attempt is not None else None,
                    }
                if attempt is not None:
                    failure.update(
                        _plan_failure_details(
                            attempt,
                            packet.conclusion_status.value,
                            packet_fact_ids,
                        )
                    )
                model_failures.append(failure)

            facts_by_id = {fact.fact_id: fact for fact in packet.facts}
            actual_ids = {claim.fact_id for claim in explanation.claims}
            case_grounded = True
            case_traceable = True
            for claim in explanation.claims:
                total_claims += 1
                fact = facts_by_id.get(claim.fact_id)
                grounded = fact is not None and claim.statement == fact.reason
                traceable = (
                    fact is not None
                    and claim.source_ids == fact.source_ids
                    and claim.source_locator == fact.source_locator
                )
                grounded_claims += int(grounded)
                source_traceable_claims += int(traceable)
                case_grounded = case_grounded and grounded
                case_traceable = case_traceable and traceable

            expected_references += len(packet_fact_ids)
            retained_references += len(packet_fact_ids & actual_ids)
            conclusion_match = explanation.conclusion_status == packet.conclusion_status
            conclusion_matches += int(conclusion_match)
            references_match = actual_ids == packet_fact_ids
            pipeline_pass = (
                engine_match
                and conclusion_match
                and references_match
                and case_grounded
                and case_traceable
            )
            pipeline_passes += int(pipeline_pass)

            record = {
                "repetition": repetition,
                "case_id": case.case_id,
                "expected_conclusion_status": (
                    expected_status.value if expected_status else None
                ),
                "packet_conclusion_status": packet.conclusion_status.value,
                "expected_fact_ids": sorted(expected_fact_ids),
                "packet_fact_ids": sorted(packet_fact_ids),
                "claim_fact_ids": [claim.fact_id for claim in explanation.claims],
                "generation_mode": explanation.generation_mode.value,
                "fallback_reason": (
                    explanation.fallback_reason.value
                    if explanation.fallback_reason
                    else None
                ),
                "pipeline_pass": pipeline_pass,
                "attempt": attempt.to_dict() if attempt is not None else None,
            }
            records.append(record)

            if not pipeline_pass:
                pipeline_failures.append(record)

    total_runs = len(case_list) * repetitions
    attempted_case_ids = {
        record["case_id"] for record in records if record["attempt"] is not None
    }
    consistent_cases = sum(
        1
        for case_id in attempted_case_ids
        if len(plans_by_case.get(case_id, [])) == repetitions
        and len(set(plans_by_case[case_id])) == 1
    )
    raw_consistent_cases = sum(
        1
        for case_id in attempted_case_ids
        if len(raw_plans_by_case.get(case_id, [])) == repetitions
        and len(set(raw_plans_by_case[case_id])) == 1
    )
    return {
        "runner": "ollama_explanation",
        "prompt_version": getattr(planner, "prompt_version", EXPLANATION_CONTRACT_VERSION),
        "dataset_cases": len(case_list),
        "repetitions": repetitions,
        "total_case_runs": total_runs,
        "planner_attempts": planner_attempts,
        "generation_options": dict(planner.options),
        "metrics": {
            "safety_engine_match_rate": engine_matches / total_runs if total_runs else 0.0,
            "valid_plan_rate": valid_plans / planner_attempts if planner_attempts else 1.0,
            "fallback_rate": fallbacks / planner_attempts if planner_attempts else 0.0,
            "raw_plan_consistency_rate": (
                raw_consistent_cases / len(attempted_case_ids) if attempted_case_ids else 1.0
            ),
            "valid_plan_consistency_rate": (
                consistent_cases / len(attempted_case_ids) if attempted_case_ids else 1.0
            ),
            "pipeline_pass_rate": pipeline_passes / total_runs if total_runs else 0.0,
            "conclusion_preservation_rate": (
                conclusion_matches / total_runs if total_runs else 0.0
            ),
            "fact_reference_coverage": (
                retained_references / expected_references if expected_references else 1.0
            ),
            "extractive_claim_rate": grounded_claims / total_claims if total_claims else 1.0,
            "source_traceability_rate": (
                source_traceable_claims / total_claims if total_claims else 1.0
            ),
            "unsupported_claim_rate": (
                (total_claims - grounded_claims) / total_claims if total_claims else 0.0
            ),
            "planner_latency_ms_p50": round(median(latencies), 3) if latencies else None,
            "planner_latency_ms_p95": _percentile(latencies, 0.95),
        },
        "model_failures": model_failures,
        "pipeline_failures": pipeline_failures,
        "records": records,
        "interpretation_boundary": (
            "Real local model planning over a small development probe; not clinical quality "
            "or a locked test-set result."
        ),
    }


def render_ollama_explanation_markdown(report: dict[str, Any], dataset_name: str) -> str:
    metrics = report["metrics"]
    model = report["model"]
    lines = [
        "# Real Ollama Evidence-Planning Baseline",
        "",
        f"Dataset: `{dataset_name}`",
        f"Dataset SHA-256: `{report['dataset_sha256']}`",
        f"Data version: `{report['data_version']}`",
        f"Prompt version: `{report['prompt_version']}`",
        f"Model: `{model['name']}`",
        f"Model digest: `{model['digest']}`",
        f"Model parameters: `{model['parameter_size']}`",
        f"Quantization: `{model['quantization_level']}`",
        f"Generation options: `{report['generation_options']}`",
        f"Ollama package: `{report['ollama_package_version']}`",
        f"Code commit: `{report['code_commit']}`",
        f"Working tree dirty at run: `{str(report['working_tree_dirty']).lower()}`",
        f"Repetitions: {report['repetitions']}",
        f"Planner attempts: {report['planner_attempts']}",
        "",
        "## Metrics",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Valid plan rate | {metrics['valid_plan_rate']:.3f} |",
        f"| Fallback rate | {metrics['fallback_rate']:.3f} |",
        f"| Raw plan consistency rate | {metrics['raw_plan_consistency_rate']:.3f} |",
        f"| Valid plan consistency rate | {metrics['valid_plan_consistency_rate']:.3f} |",
        f"| Pipeline pass rate | {metrics['pipeline_pass_rate']:.3f} |",
        f"| Conclusion preservation | {metrics['conclusion_preservation_rate']:.3f} |",
        f"| Fact reference coverage | {metrics['fact_reference_coverage']:.3f} |",
        f"| Extractive claim rate | {metrics['extractive_claim_rate']:.3f} |",
        f"| Source traceability rate | {metrics['source_traceability_rate']:.3f} |",
        f"| Unsupported claim rate | {metrics['unsupported_claim_rate']:.3f} |",
        f"| Planner latency P50 | {metrics['planner_latency_ms_p50']:.3f} ms |",
        f"| Planner latency P95 | {metrics['planner_latency_ms_p95']:.3f} ms |",
        "",
        "## Failures",
        "",
        f"Model plan failures: {len(report['model_failures'])}",
        f"Pipeline safety failures: {len(report['pipeline_failures'])}",
        "",
        "## Interpretation Boundary",
        "",
        report["interpretation_boundary"],
    ]
    return "\n".join(lines) + "\n"
