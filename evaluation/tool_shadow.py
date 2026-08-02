"""Metrics and failure taxonomy for non-executing tool-call proposals."""

from __future__ import annotations

from collections.abc import Iterable
from statistics import median
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from evaluation.tool_shadow_dataset import ShadowToolSelectionCase
from medsafety.tool_contracts import (
    QuerySafetyGraphArguments,
    RenderEvidenceExplanationArguments,
    RequestClarificationArguments,
    ResolveMedicationsArguments,
    ToolDefinition,
    ToolName,
)
from medsafety.tool_shadow_planner import ShadowToolPlanAttempt


class ShadowPlanner(Protocol):
    prompt_version: str

    def propose(
        self,
        state,
        definitions: list[ToolDefinition],
    ) -> ShadowToolPlanAttempt: ...


_ARGUMENT_MODELS: dict[ToolName, type[BaseModel]] = {
    ToolName.RESOLVE_MEDICATIONS: ResolveMedicationsArguments,
    ToolName.QUERY_SAFETY_GRAPH: QuerySafetyGraphArguments,
    ToolName.REQUEST_CLARIFICATION: RequestClarificationArguments,
    ToolName.RENDER_EVIDENCE_EXPLANATION: RenderEvidenceExplanationArguments,
}


def classify_shadow_attempt(
    case: ShadowToolSelectionCase,
    attempt: ShadowToolPlanAttempt,
    definitions: list[ToolDefinition],
) -> tuple[str, dict[str, Any] | None]:
    if attempt.error_category is not None:
        return attempt.error_category, None
    if attempt.proposal is None:
        return "invalid_response_shape", None

    registered = {definition.name.value for definition in definitions}
    if attempt.proposal.name not in registered:
        return "unknown_tool", None
    try:
        tool_name = ToolName(attempt.proposal.name)
    except ValueError:
        return "unknown_tool", None
    try:
        normalized_arguments = _ARGUMENT_MODELS[tool_name].model_validate(
            attempt.proposal.arguments
        ).model_dump(mode="json")
    except ValidationError:
        return "invalid_arguments", None

    if tool_name != case.expected.name:
        return "wrong_tool", normalized_arguments
    if normalized_arguments != case.expected.arguments:
        return "wrong_arguments", normalized_arguments
    return "valid", normalized_arguments


def evaluate_tool_shadow(
    cases: Iterable[ShadowToolSelectionCase],
    planner: ShadowPlanner,
    definitions: list[ToolDefinition],
    *,
    repetitions: int = 1,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    case_list = list(cases)
    records = []
    failures = []
    valid_count = 0
    tool_name_matches = 0
    argument_matches = 0
    proposal_count = 0
    latencies = []

    for repetition in range(1, repetitions + 1):
        for case in case_list:
            attempt = planner.propose(case.state, definitions)
            status, normalized_arguments = classify_shadow_attempt(
                case,
                attempt,
                definitions,
            )
            proposal = (
                attempt.proposal.model_dump(mode="json")
                if attempt.proposal is not None
                else None
            )
            proposal_count += int(proposal is not None)
            name_match = bool(
                proposal is not None
                and proposal["name"] == case.expected.name.value
            )
            arguments_match = bool(
                name_match and normalized_arguments == case.expected.arguments
            )
            tool_name_matches += int(name_match)
            argument_matches += int(arguments_match)
            valid_count += int(status == "valid")
            latencies.append(attempt.latency_ms)
            record = {
                "case_id": case.case_id,
                "split": case.split,
                "repetition": repetition,
                "status": status,
                "expected": case.expected.model_dump(mode="json"),
                "proposal": proposal,
                "call_count": attempt.call_count,
                "latency_ms": attempt.latency_ms,
                "error_type": attempt.error_type,
                "content_present": attempt.content_present,
                "response_metadata": attempt.response_metadata,
                "executed": False,
            }
            records.append(record)
            if status != "valid":
                failures.append(record)

    total = len(records)
    status_counts = {}
    for record in records:
        status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1
    report = {
        "runner": "ollama_tool_shadow",
        "prompt_version": planner.prompt_version,
        "dataset_cases": len(case_list),
        "repetitions": repetitions,
        "requests": total,
        "executed_tool_calls": 0,
        "metrics": {
            "proposal_rate": proposal_count / total if total else 0.0,
            "tool_name_accuracy": tool_name_matches / total if total else 0.0,
            "argument_exact_match": argument_matches / total if total else 0.0,
            "whole_call_exact_match": valid_count / total if total else 0.0,
            "illegal_tool_rate": status_counts.get("unknown_tool", 0) / total if total else 0.0,
            "invalid_argument_rate": status_counts.get("invalid_arguments", 0) / total if total else 0.0,
        },
        "status_counts": status_counts,
        "latency_ms": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "median": round(median(latencies), 3) if latencies else 0.0,
        },
        "failures": failures,
        "boundary": (
            "Shadow proposals were validated and recorded only. No proposed tool "
            "was dispatched or executed."
        ),
    }
    return report, records


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile / 100
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 3)


def render_tool_shadow_markdown(report: dict[str, Any], dataset_path: str) -> str:
    metrics = report["metrics"]
    model = report.get("model", {})
    lines = [
        "# Ollama Typed-Tool Shadow Evaluation",
        "",
        f"- Dataset: `{dataset_path}`",
        f"- Split: `{report['split']}`",
        f"- Dataset SHA-256: `{report['dataset_sha256']}`",
        f"- Prompt: `{report['prompt_version']}`",
        f"- Model: `{model.get('name', report.get('configured_model', 'unknown'))}`",
        f"- Model digest: `{model.get('digest', 'unknown')}`",
        f"- Cases / requests: {report['dataset_cases']} / {report['requests']}",
        f"- Repetitions: {report['repetitions']}",
        f"- Executed tool calls: **{report['executed_tool_calls']}**",
        "",
        "## Metrics",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Proposal rate | {metrics['proposal_rate']:.3f} |",
        f"| Tool-name accuracy | {metrics['tool_name_accuracy']:.3f} |",
        f"| Argument exact match | {metrics['argument_exact_match']:.3f} |",
        f"| Whole-call exact match | {metrics['whole_call_exact_match']:.3f} |",
        f"| Illegal-tool rate | {metrics['illegal_tool_rate']:.3f} |",
        f"| Invalid-argument rate | {metrics['invalid_argument_rate']:.3f} |",
        "",
        "## Status counts",
        "",
    ]
    for status, count in sorted(report["status_counts"].items()):
        lines.append(f"- `{status}`: {count}")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            report["boundary"],
            "",
            "All proposals were treated as untrusted data. This runner did not dispatch "
            "a proposal to `TypedToolRegistry.execute` and did not run Neo4j, Redis, or "
            "the Safety Engine as a consequence of a model choice.",
        ]
    )
    if report["failures"]:
        lines.extend(
            [
                "",
                "## Failures",
                "",
                "| Case | Repetition | Status | Expected | Proposed |",
                "|---|---:|---|---|---|",
            ]
        )
        for failure in report["failures"]:
            expected = failure["expected"]["name"]
            proposed = (
                failure["proposal"]["name"]
                if failure["proposal"] is not None
                else "none"
            )
            lines.append(
                f"| `{failure['case_id']}` | {failure['repetition']} | "
                f"`{failure['status']}` | `{expected}` | `{proposed}` |"
            )
    return "\n".join(lines) + "\n"
