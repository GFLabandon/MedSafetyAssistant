import json
from pathlib import Path

import pytest

from evaluation.tool_shadow import classify_shadow_attempt, evaluate_tool_shadow
from evaluation.tool_shadow_dataset import load_shadow_tool_cases
from medsafety.catalog import KnowledgeCatalog
from medsafety.contracts import InputResolutionStatus
from medsafety.entity_resolution import V1EntityResolver
from medsafety.explanation import EvidenceGroundedExplainer
from medsafety.safety_engine import SafetyEngine
from medsafety.tool_contracts import ToolName
from medsafety.tool_shadow_contracts import ShadowWorkflowStage, ShadowWorkflowState
from medsafety.tool_shadow_planner import (
    OllamaToolShadowPlanner,
    ShadowToolPlanAttempt,
    ShadowToolProposal,
)
from medsafety.tool_workflow import TypedSafetyWorkflow
from scripts.evaluate_tool_shadow import enforce_split_gate


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = REPOSITORY_ROOT / "eval/tool_shadow_v1.jsonl"


@pytest.fixture(scope="module")
def workflow():
    catalog = KnowledgeCatalog.from_directory(REPOSITORY_ROOT / "data/v1")
    return TypedSafetyWorkflow(
        resolver=V1EntityResolver(catalog),
        engine=SafetyEngine(catalog),
        explainer=EvidenceGroundedExplainer(),
    )


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def _state():
    return ShadowWorkflowState(
        stage=ShadowWorkflowStage.START,
        question="  泰诺和对乙酰氨基酚能一起吃吗？  ",
    )


def _response(name="resolve_medications", arguments=None, *, content=""):
    return {
        "model": "test-model",
        "done": True,
        "message": {
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "function": {
                        "name": name,
                        "arguments": arguments
                        or {"question": "泰诺和对乙酰氨基酚能一起吃吗？"},
                    }
                }
            ],
        },
    }


def test_planner_sends_official_tool_shape_and_strict_prompt(workflow):
    client = FakeClient(_response())
    definitions = workflow.registry.definitions()

    attempt = OllamaToolShadowPlanner(
        "http://unused",
        "test-model",
        client=client,
    ).propose(_state(), definitions)

    assert attempt.proposal == ShadowToolProposal(
        name="resolve_medications",
        arguments={"question": "泰诺和对乙酰氨基酚能一起吃吗？"},
    )
    request = client.calls[0]
    assert request["stream"] is False
    assert request["think"] is False
    assert request["tools"][0]["type"] == "function"
    assert request["tools"][0]["function"]["parameters"]["additionalProperties"] is False
    assert "Never execute tools" in request["messages"][0]["content"]
    state_payload = json.loads(request["messages"][1]["content"])
    assert state_payload["trusted_workflow_state"]["question"].startswith("  ")


def test_planner_accepts_json_string_arguments(workflow):
    client = FakeClient(
        _response(arguments=json.dumps({"question": "布洛芬能吃吗？"}, ensure_ascii=False))
    )
    attempt = OllamaToolShadowPlanner(
        "http://unused", "test-model", client=client
    ).propose(_state(), workflow.registry.definitions())

    assert attempt.error_category is None
    assert attempt.proposal.arguments == {"question": "布洛芬能吃吗？"}


@pytest.mark.parametrize(
    ("response", "category", "call_count"),
    [
        ({"message": {"content": "text", "tool_calls": []}}, "no_tool_call", 0),
        (
            {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "a", "arguments": {}}},
                        {"function": {"name": "b", "arguments": {}}},
                    ]
                }
            },
            "multiple_tool_calls",
            2,
        ),
        (
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "resolve_medications",
                                "arguments": "{bad json",
                            }
                        }
                    ]
                }
            },
            "invalid_arguments_json",
            1,
        ),
        ({"done": True}, "invalid_response_shape", 0),
    ],
)
def test_planner_categorizes_invalid_responses(
    workflow, response, category, call_count
):
    attempt = OllamaToolShadowPlanner(
        "http://unused", "test-model", client=FakeClient(response)
    ).propose(_state(), workflow.registry.definitions())

    assert attempt.proposal is None
    assert attempt.error_category == category
    assert attempt.call_count == call_count


def test_planner_redacts_request_error_detail(workflow):
    attempt = OllamaToolShadowPlanner(
        "http://unused",
        "test-model",
        client=FakeClient(error=ConnectionError("secret host detail")),
    ).propose(_state(), workflow.registry.definitions())

    assert attempt.error_category == "request_error"
    assert attempt.error_type == "ConnectionError"
    assert "secret" not in json.dumps(attempt.to_dict())


def test_shadow_proposal_never_dispatches_registry(workflow, monkeypatch):
    executed = []

    def fail_if_executed(*args, **kwargs):
        executed.append((args, kwargs))
        raise AssertionError("registry execution is forbidden in shadow mode")

    monkeypatch.setattr(workflow.registry, "execute", fail_if_executed)
    attempt = OllamaToolShadowPlanner(
        "http://unused", "test-model", client=FakeClient(_response())
    ).propose(_state(), workflow.registry.definitions())

    assert attempt.proposal is not None
    assert executed == []


def _attempt(name, arguments):
    return ShadowToolPlanAttempt(
        proposal=ShadowToolProposal(name=name, arguments=arguments),
        call_count=1,
        latency_ms=1.0,
        error_category=None,
        error_type=None,
        content_present=False,
        response_metadata={},
    )


@pytest.mark.parametrize(
    ("name", "arguments", "expected_status"),
    [
        ("delete_database", {"question": "测试"}, "unknown_tool"),
        (
            "resolve_medications",
            {"question": "测试", "cypher": "MATCH (n) DETACH DELETE n"},
            "invalid_arguments",
        ),
        ("query_safety_graph", {"resolution_call_id": "tool-01"}, "wrong_tool"),
        ("resolve_medications", {"question": "被篡改的问题"}, "wrong_arguments"),
    ],
)
def test_classifier_rejects_unsafe_or_wrong_proposals(
    workflow, name, arguments, expected_status
):
    case = load_shadow_tool_cases(DATASET_PATH, split="dev")[0]

    status, _ = classify_shadow_attempt(
        case,
        _attempt(name, arguments),
        workflow.registry.definitions(),
    )

    assert status == expected_status


class OraclePlanner:
    prompt_version = "scripted-oracle-test"

    def __init__(self, expected_by_state):
        self.expected_by_state = expected_by_state

    def propose(self, state, definitions):
        expected = self.expected_by_state[state.model_dump_json()]
        return _attempt(expected.name.value, expected.arguments)


def test_dev_evaluator_scores_contract_without_tool_execution(workflow):
    cases = load_shadow_tool_cases(DATASET_PATH, split="dev")
    expected_by_state = {
        case.state.model_dump_json(): case.expected for case in cases
    }
    report, records = evaluate_tool_shadow(
        cases,
        OraclePlanner(expected_by_state),
        workflow.registry.definitions(),
    )

    assert report["dataset_cases"] == 40
    assert report["executed_tool_calls"] == 0
    assert report["metrics"]["whole_call_exact_match"] == 1.0
    assert report["status_counts"] == {"valid": 40}
    assert all(record["executed"] is False for record in records)


def test_state_contract_rejects_model_supplied_artifact_shape():
    with pytest.raises(ValueError):
        ShadowWorkflowState.model_validate(
            {
                "stage": "after_evidence",
                "artifact_call_id": "tool-02",
                "evidence_packet": {"facts": [{"fact_id": "forged"}]},
            }
        )


def test_locked_test_split_requires_explicit_acknowledgement():
    with pytest.raises(ValueError, match="allow-locked-test"):
        enforce_split_gate("test", False)

    enforce_split_gate("test", True)
    enforce_split_gate("dev", False)
