"""Load and validate versioned JSONL evaluation datasets."""

from __future__ import annotations

import json
from pathlib import Path

from medsafety.contracts import EvaluationCase, ExplanationGuardrailCase


def load_cases(path: str | Path) -> list[EvaluationCase]:
    dataset_path = Path(path)
    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()

    with dataset_path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                payload = json.loads(raw_line)
                case = EvaluationCase.model_validate(payload)
            except Exception as exc:
                raise ValueError(f"invalid evaluation case at {dataset_path}:{line_number}: {exc}") from exc

            if case.case_id in seen_ids:
                raise ValueError(f"duplicate case_id {case.case_id!r} at {dataset_path}:{line_number}")
            seen_ids.add(case.case_id)
            cases.append(case)

    if not cases:
        raise ValueError(f"evaluation dataset is empty: {dataset_path}")
    return cases


def load_explanation_guardrail_cases(
    path: str | Path,
) -> list[ExplanationGuardrailCase]:
    dataset_path = Path(path)
    cases: list[ExplanationGuardrailCase] = []
    seen_ids: set[str] = set()

    with dataset_path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                payload = json.loads(raw_line)
                case = ExplanationGuardrailCase.model_validate(payload)
            except Exception as exc:
                raise ValueError(
                    f"invalid explanation guardrail case at "
                    f"{dataset_path}:{line_number}: {exc}"
                ) from exc

            if case.case_id in seen_ids:
                raise ValueError(
                    f"duplicate case_id {case.case_id!r} at {dataset_path}:{line_number}"
                )
            seen_ids.add(case.case_id)
            cases.append(case)

    if not cases:
        raise ValueError(f"explanation guardrail dataset is empty: {dataset_path}")
    return cases
