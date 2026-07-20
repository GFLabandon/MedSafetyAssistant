"""Offline adversarial evaluation for the evidence explanation boundary."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from medsafety.contracts import ExplanationGuardrailCase
from medsafety.explanation import EvidenceGroundedExplainer, PROMPT_VERSION
from medsafety.safety_engine import SafetyEngine


class _ScriptedPlanner:
    def __init__(self, case: ExplanationGuardrailCase):
        self.case = case

    def plan(self, packet):
        if self.case.planner_error:
            raise RuntimeError("scripted planner dependency failure")
        return self.case.planner_result


def evaluate_explanation_guardrails(
    cases: Iterable[ExplanationGuardrailCase],
    engine: SafetyEngine,
) -> dict[str, Any]:
    case_list = list(cases)
    total_claims = 0
    grounded_claims = 0
    source_traceable_claims = 0
    expected_references = 0
    retained_references = 0
    mode_matches = 0
    fallback_matches = 0
    conclusion_matches = 0
    full_matches = 0
    failures = []

    for case in case_list:
        packet = engine.assess(case.medications, contexts=case.contexts)
        result = EvidenceGroundedExplainer(_ScriptedPlanner(case)).explain(
            packet,
            use_llm_plan=case.use_llm_plan,
        )
        facts_by_id = {fact.fact_id: fact for fact in packet.facts}
        expected_ids = set(facts_by_id)
        actual_ids = {claim.fact_id for claim in result.claims}

        case_grounded = True
        case_traceable = True
        for claim in result.claims:
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

        expected_references += len(expected_ids)
        retained_references += len(expected_ids & actual_ids)
        mode_match = result.generation_mode == case.expected_generation_mode
        fallback_match = result.fallback_reason == case.expected_fallback_reason
        conclusion_match = result.conclusion_status == packet.conclusion_status
        reference_match = actual_ids == expected_ids
        mode_matches += int(mode_match)
        fallback_matches += int(fallback_match)
        conclusion_matches += int(conclusion_match)
        passed = (
            mode_match
            and fallback_match
            and conclusion_match
            and reference_match
            and case_grounded
            and case_traceable
        )
        full_matches += int(passed)

        if not passed:
            failures.append(
                {
                    "case_id": case.case_id,
                    "expected_mode": case.expected_generation_mode.value,
                    "actual_mode": result.generation_mode.value,
                    "expected_fallback_reason": (
                        case.expected_fallback_reason.value
                        if case.expected_fallback_reason
                        else None
                    ),
                    "actual_fallback_reason": (
                        result.fallback_reason.value if result.fallback_reason else None
                    ),
                    "expected_fact_ids": sorted(expected_ids),
                    "actual_fact_ids": sorted(actual_ids),
                    "conclusion_preserved": conclusion_match,
                    "claims_grounded": case_grounded,
                    "sources_traceable": case_traceable,
                }
            )

    total = len(case_list)
    return {
        "runner": "explanation_guardrails",
        "prompt_version": PROMPT_VERSION,
        "planner": "scripted_adversarial_fixtures",
        "dataset_cases": total,
        "metrics": {
            "case_pass_rate": full_matches / total if total else 0.0,
            "mode_accuracy": mode_matches / total if total else 0.0,
            "fallback_reason_accuracy": fallback_matches / total if total else 0.0,
            "conclusion_preservation_rate": conclusion_matches / total if total else 0.0,
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
        },
        "failures": failures,
        "interpretation_boundary": (
            "Scripted planner guardrail regression; not a real-model or clinical-quality result."
        ),
    }


def render_explanation_guardrails_markdown(
    report: dict[str, Any],
    dataset_name: str,
    data_version: str,
) -> str:
    metrics = report["metrics"]
    lines = [
        "# Evidence Explanation Guardrail Baseline",
        "",
        f"Dataset: `{dataset_name}`",
        f"Data version: `{data_version}`",
        f"Dataset SHA-256: `{report['dataset_sha256']}`",
        f"Prompt version: `{report['prompt_version']}`",
        f"Planner: `{report['planner']}`",
        f"Code commit: `{report['code_commit']}`",
        f"Working tree dirty at run: `{str(report['working_tree_dirty']).lower()}`",
        f"Cases: {report['dataset_cases']}",
        "",
        "## Metrics",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Case pass rate | {metrics['case_pass_rate']:.3f} |",
        f"| Mode accuracy | {metrics['mode_accuracy']:.3f} |",
        f"| Fallback reason accuracy | {metrics['fallback_reason_accuracy']:.3f} |",
        f"| Conclusion preservation | {metrics['conclusion_preservation_rate']:.3f} |",
        f"| Fact reference coverage | {metrics['fact_reference_coverage']:.3f} |",
        f"| Extractive claim rate | {metrics['extractive_claim_rate']:.3f} |",
        f"| Source traceability rate | {metrics['source_traceability_rate']:.3f} |",
        f"| Unsupported claim rate | {metrics['unsupported_claim_rate']:.3f} |",
        "",
        "## Failures",
        "",
    ]
    if report["failures"]:
        lines.extend(f"- `{failure['case_id']}`: {failure}" for failure in report["failures"])
    else:
        lines.append("No failures in this scripted adversarial set.")
    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            report["interpretation_boundary"],
        ]
    )
    return "\n".join(lines) + "\n"
