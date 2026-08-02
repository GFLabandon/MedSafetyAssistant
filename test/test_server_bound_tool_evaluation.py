from pathlib import Path

from evaluation.server_bound_tool import evaluate_server_bound_tools
from evaluation.tool_shadow_dataset import load_shadow_tool_cases
from medsafety.server_bound_tool_decisions import ToolNamePlanAttempt


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class OracleThenWrongPlanner:
    prompt_version = "test-server-bound-v1"

    def __init__(self):
        self.index = 0

    def propose(self, state, _definitions):
        if state.stage.value == "start":
            expected = "resolve_medications"
        elif state.stage.value == "after_resolution":
            expected = (
                "query_safety_graph"
                if state.resolution_status.value == "resolved"
                else "request_clarification"
            )
        else:
            expected = "render_evidence_explanation"
        self.index += 1
        return ToolNamePlanAttempt(
            proposed_name=expected if self.index == 1 else "delete_database",
            call_count=1,
            latency_ms=float(self.index),
            error_category=None,
            error_type=None,
            content_present=False,
            response_metadata={},
        )


def test_evaluation_separates_model_accuracy_from_server_bound_safety():
    cases = load_shadow_tool_cases(
        REPOSITORY_ROOT / "eval/tool_shadow_v1.jsonl",
        split="dev",
    )[:2]
    report, records = evaluate_server_bound_tools(
        cases,
        OracleThenWrongPlanner(),
        [],
    )

    assert report["metrics"]["raw_tool_name_accuracy"] == 0.5
    assert report["metrics"]["server_bound_call_accuracy"] == 1.0
    assert report["metrics"]["fallback_rate"] == 0.5
    assert records[1]["fallback_reason"] == "unknown_tool"
    assert "bound_arguments" not in records[0]
