"""Metrics for name-only model proposals and server-bound tool decisions."""

from __future__ import annotations

from collections import Counter
from statistics import median

from evaluation.tool_shadow_dataset import ShadowToolSelectionCase
from medsafety.server_bound_tool_decisions import (
    ToolNamePlanAttempt,
    bind_server_tool_decision,
)
from medsafety.tool_contracts import ToolDefinition


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * percentile + 0.999999))
    return ordered[index]


def evaluate_server_bound_tools(
    cases: list[ShadowToolSelectionCase],
    planner,
    definitions: list[ToolDefinition],
    *,
    repetitions: int = 1,
) -> tuple[dict, list[dict]]:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")

    records = []
    fallback_counts: Counter[str] = Counter()
    latencies = []
    accepted = 0
    bound_matches = 0
    total = len(cases) * repetitions
    for repetition in range(1, repetitions + 1):
        for case in cases:
            attempt: ToolNamePlanAttempt = planner.propose(case.state, definitions)
            decision = bind_server_tool_decision(
                case.state,
                attempt,
                call_id=f"eval-{repetition}-{case.case_id}"[:64],
            )
            accepted += int(decision.proposal_accepted)
            is_bound_match = bool(
                decision.call.name == case.expected.name.value
                and decision.call.arguments == case.expected.arguments
            )
            bound_matches += int(is_bound_match)
            latencies.append(attempt.latency_ms)
            if decision.fallback_reason is not None:
                fallback_counts[decision.fallback_reason.value] += 1
            records.append(
                {
                    "case_id": case.case_id,
                    "split": case.split,
                    "repetition": repetition,
                    "expected_name": case.expected.name.value,
                    "proposed_name": decision.proposed_name,
                    "proposal_accepted": decision.proposal_accepted,
                    "fallback_reason": (
                        decision.fallback_reason.value
                        if decision.fallback_reason is not None
                        else None
                    ),
                    "planner_error_category": decision.planner_error_category,
                    "planner_latency_ms": attempt.latency_ms,
                    "bound_name": decision.call.name,
                    "bound_argument_keys": sorted(decision.call.arguments),
                    "bound_call_matches_oracle": is_bound_match,
                }
            )

    metrics = {
        "total_attempts": total,
        "proposal_acceptance_rate": accepted / total if total else 0.0,
        "raw_tool_name_accuracy": accepted / total if total else 0.0,
        "server_bound_call_accuracy": bound_matches / total if total else 0.0,
        "fallback_rate": (total - accepted) / total if total else 0.0,
        "fallback_counts": dict(sorted(fallback_counts.items())),
        "planner_latency_ms": {
            "p50": median(latencies) if latencies else 0.0,
            "p95": _percentile(latencies, 0.95),
        },
    }
    return {
        "schema_version": "server-bound-tool-evaluation-v1",
        "prompt_version": planner.prompt_version,
        "repetitions": repetitions,
        "metrics": metrics,
    }, records


def render_server_bound_tool_markdown(report: dict, dataset_path: str) -> str:
    metrics = report["metrics"]
    model = report.get("model", {})
    return "\n".join(
        [
            "# Server-bound Tool Decision Evaluation",
            "",
            f"- Dataset: `{dataset_path}`",
            f"- Split: `{report.get('split', 'unknown')}`",
            f"- Prompt: `{report['prompt_version']}`",
            f"- Model: `{model.get('name', report.get('configured_model', 'unknown'))}`",
            f"- Attempts: `{metrics['total_attempts']}`",
            "",
            "| Metric | Result |",
            "|---|---:|",
            f"| Raw tool-name accuracy | {metrics['raw_tool_name_accuracy']:.3f} |",
            f"| Proposal acceptance rate | {metrics['proposal_acceptance_rate']:.3f} |",
            f"| Server-bound call accuracy | {metrics['server_bound_call_accuracy']:.3f} |",
            f"| Deterministic fallback rate | {metrics['fallback_rate']:.3f} |",
            f"| Planner latency P50 | {metrics['planner_latency_ms']['p50']:.1f} ms |",
            f"| Planner latency P95 | {metrics['planner_latency_ms']['p95']:.1f} ms |",
            "",
            "`server_bound_call_accuracy` measures the server-derived call only. It "
            "does not hide model failures; raw accuracy and fallback rate remain separate.",
            "No model-supplied argument or proposal was executed during this evaluation.",
            "",
        ]
    )
