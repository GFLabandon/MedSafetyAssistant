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
        actual_fact_ids = {fact.fact_id for fact in result.facts}
        status_match = result.conclusion_status == expected_status
        facts_match = actual_fact_ids == expected_fact_ids
        conclusion_matches += int(status_match)
        fact_matches += int(facts_match)
        full_matches += int(status_match and facts_match)

        if not (status_match and facts_match):
            failures.append(
                {
                    "case_id": case.case_id,
                    "expected_status": expected_status.value if expected_status else None,
                    "actual_status": result.conclusion_status.value,
                    "expected_fact_ids": sorted(expected_fact_ids),
                    "actual_fact_ids": sorted(actual_fact_ids),
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
            "This is a deterministic regression baseline over a seven-case development set and two source-aligned facts. It is not a clinical-accuracy claim and is not a locked test-set result.",
        ]
    )
    return "\n".join(lines) + "\n"
