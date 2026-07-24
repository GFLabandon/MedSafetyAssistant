"""Offline evaluation for the deterministic, source-aligned Safety Engine."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from medsafety.contracts import EvaluationCase
from medsafety.safety_engine import SafetyEngine


def evaluate_safety_engine(
    cases: Iterable[EvaluationCase],
    engine: SafetyEngine,
) -> dict[str, Any]:
    case_list = list(cases)
    conclusion_matches = 0
    fact_matches = 0
    medication_matches = 0
    context_matches = 0
    full_matches = 0
    failures = []

    for case in case_list:
        medications = case.metadata.get("medications")
        contexts = case.metadata.get("contexts", [])
        if not isinstance(medications, list) or not all(isinstance(item, str) for item in medications):
            raise ValueError(f"case {case.case_id} requires metadata.medications as a list of strings")
        if not isinstance(contexts, list) or not all(isinstance(item, str) for item in contexts):
            raise ValueError(f"case {case.case_id} requires metadata.contexts as a list of strings")

        result = engine.assess(medications, contexts=contexts)
        expected_status = case.expected.conclusion_status
        expected_fact_ids = set(case.expected.required_fact_ids)
        expected_medications = set(case.expected.drugs)
        expected_contexts = set(case.expected.conditions)
        actual_fact_ids = {fact.fact_id for fact in result.facts}
        actual_medications = set(result.resolved_medications)
        actual_contexts = set(result.resolved_contexts)
        status_match = result.conclusion_status == expected_status
        facts_match = actual_fact_ids == expected_fact_ids
        medications_match = actual_medications == expected_medications
        contexts_match = actual_contexts == expected_contexts
        conclusion_matches += int(status_match)
        fact_matches += int(facts_match)
        medication_matches += int(medications_match)
        context_matches += int(contexts_match)
        full_matches += int(
            status_match and facts_match and medications_match and contexts_match
        )

        if not (status_match and facts_match and medications_match and contexts_match):
            failures.append(
                {
                    "case_id": case.case_id,
                    "expected_status": expected_status.value if expected_status else None,
                    "actual_status": result.conclusion_status.value,
                    "expected_fact_ids": sorted(expected_fact_ids),
                    "actual_fact_ids": sorted(actual_fact_ids),
                    "expected_medications": sorted(expected_medications),
                    "actual_medications": sorted(actual_medications),
                    "expected_contexts": sorted(expected_contexts),
                    "actual_contexts": sorted(actual_contexts),
                }
            )

    total = len(case_list)
    return {
        "runner": "safety_engine",
        "dataset_cases": total,
        "label_scope": "source_aligned facts; not clinically reviewed",
        "metrics": {
            "conclusion_accuracy": conclusion_matches / total if total else 0.0,
            "fact_set_exact_match": fact_matches / total if total else 0.0,
            "medication_set_exact_match": medication_matches / total if total else 0.0,
            "context_set_exact_match": context_matches / total if total else 0.0,
            "case_exact_match": full_matches / total if total else 0.0,
        },
        "failures": failures,
    }


def render_safety_markdown(report: dict[str, Any], dataset_name: str, data_version: str) -> str:
    metrics = report["metrics"]
    lines = [
        "# Source-Aligned Safety Engine Baseline",
        "",
        f"Dataset: `{dataset_name}`",
        f"Data version: `{data_version}`",
        f"Cases: {report['dataset_cases']}",
        f"Label scope: {report['label_scope']}",
        "",
        "## Metrics",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Conclusion accuracy | {metrics['conclusion_accuracy']:.3f} |",
        f"| Fact-set exact match | {metrics['fact_set_exact_match']:.3f} |",
        f"| Medication-set exact match | {metrics['medication_set_exact_match']:.3f} |",
        f"| Context-set exact match | {metrics['context_set_exact_match']:.3f} |",
        f"| Whole-case exact match | {metrics['case_exact_match']:.3f} |",
        "",
        "## Failures",
        "",
    ]
    if report["failures"]:
        for failure in report["failures"]:
            lines.append(f"- `{failure['case_id']}`: {failure}")
    else:
        lines.append("No failures in this small development set.")
    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            "This is a deterministic regression baseline over a small development set and a limited source-aligned fact catalog. It is not a clinical-accuracy claim and is not a locked test-set result.",
        ]
    )
    return "\n".join(lines) + "\n"
