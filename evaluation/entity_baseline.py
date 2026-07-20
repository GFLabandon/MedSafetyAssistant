"""Evaluate the existing deterministic entity extractor without live services."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from medsafety.contracts import EvaluationCase


EntityExtractor = Callable[[str], tuple[list[str], list[str]]]


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _score_counts(expected: set[str], predicted: set[str]) -> tuple[int, int, int]:
    return len(expected & predicted), len(predicted - expected), len(expected - predicted)


def evaluate_entity_extractor(
    cases: Iterable[EvaluationCase],
    extractor: EntityExtractor,
) -> dict[str, Any]:
    case_list = list(cases)
    drug_tp = drug_fp = drug_fn = 0
    condition_tp = condition_fp = condition_fn = 0
    drug_exact = condition_exact = all_exact = 0
    failures: list[dict[str, Any]] = []

    for case in case_list:
        predicted_drugs, predicted_conditions = extractor(case.question)
        expected_drugs = set(case.expected.drugs)
        expected_conditions = set(case.expected.conditions)
        actual_drugs = set(predicted_drugs)
        actual_conditions = set(predicted_conditions)

        counts = _score_counts(expected_drugs, actual_drugs)
        drug_tp += counts[0]
        drug_fp += counts[1]
        drug_fn += counts[2]

        counts = _score_counts(expected_conditions, actual_conditions)
        condition_tp += counts[0]
        condition_fp += counts[1]
        condition_fn += counts[2]

        drugs_match = expected_drugs == actual_drugs
        conditions_match = expected_conditions == actual_conditions
        drug_exact += int(drugs_match)
        condition_exact += int(conditions_match)
        all_exact += int(drugs_match and conditions_match)

        if not (drugs_match and conditions_match):
            failures.append(
                {
                    "case_id": case.case_id,
                    "category": case.category,
                    "question": case.question,
                    "expected_drugs": sorted(expected_drugs),
                    "actual_drugs": sorted(actual_drugs),
                    "expected_conditions": sorted(expected_conditions),
                    "actual_conditions": sorted(actual_conditions),
                }
            )

    entity_tp = drug_tp + condition_tp
    entity_fp = drug_fp + condition_fp
    entity_fn = drug_fn + condition_fn
    precision = _safe_ratio(entity_tp, entity_tp + entity_fp)
    recall = _safe_ratio(entity_tp, entity_tp + entity_fn)
    f1 = _safe_ratio(2 * precision * recall, precision + recall)
    total = len(case_list)

    return {
        "runner": "rule_entities",
        "dataset_cases": total,
        "label_scope": "entity labels only; medical risk labels are legacy_unreviewed",
        "metrics": {
            "entity_micro_precision": round(precision, 6),
            "entity_micro_recall": round(recall, 6),
            "entity_micro_f1": round(f1, 6),
            "drug_exact_match": round(_safe_ratio(drug_exact, total), 6),
            "condition_exact_match": round(_safe_ratio(condition_exact, total), 6),
            "case_exact_match": round(_safe_ratio(all_exact, total), 6),
        },
        "counts": {
            "drug": {"tp": drug_tp, "fp": drug_fp, "fn": drug_fn},
            "condition": {"tp": condition_tp, "fp": condition_fp, "fn": condition_fn},
            "failed_cases": len(failures),
        },
        "failures": failures,
    }


def render_markdown(report: dict[str, Any], dataset_name: str) -> str:
    metrics = report["metrics"]
    counts = report["counts"]
    lines = [
        "# Current Rule Entity Baseline",
        "",
        f"Dataset: `{dataset_name}`  ",
        f"Runner: `{report['runner']}`  ",
        f"Cases: {report['dataset_cases']}  ",
        f"Label scope: {report['label_scope']}",
        "",
        "## Metrics",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Entity micro precision | {metrics['entity_micro_precision']:.3f} |",
        f"| Entity micro recall | {metrics['entity_micro_recall']:.3f} |",
        f"| Entity micro F1 | {metrics['entity_micro_f1']:.3f} |",
        f"| Drug exact match | {metrics['drug_exact_match']:.3f} |",
        f"| Condition exact match | {metrics['condition_exact_match']:.3f} |",
        f"| Whole-case exact match | {metrics['case_exact_match']:.3f} |",
        "",
        f"Failed cases: {counts['failed_cases']}",
        "",
        "## Failure Details",
        "",
    ]
    if not report["failures"]:
        lines.append("No failures.")
    else:
        for failure in report["failures"]:
            lines.extend(
                [
                    f"### {failure['case_id']}",
                    "",
                    f"- Category: `{failure['category']}`",
                    f"- Question: {failure['question']}",
                    f"- Expected drugs: {failure['expected_drugs']}",
                    f"- Actual drugs: {failure['actual_drugs']}",
                    f"- Expected conditions: {failure['expected_conditions']}",
                    f"- Actual conditions: {failure['actual_conditions']}",
                    "",
                ]
            )
    lines.extend(
        [
            "## Interpretation Boundary",
            "",
            "This report evaluates only the current deterministic entity extractor. It does not evaluate medical correctness, knowledge-graph retrieval, answer faithfulness, or end-to-end safety.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
