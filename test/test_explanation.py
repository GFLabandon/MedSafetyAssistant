from pathlib import Path

import pytest

from medsafety.catalog import KnowledgeCatalog
from medsafety.contracts import (
    ConclusionStatus,
    ExplanationFallbackReason,
    ExplanationGenerationMode,
)
from medsafety.explanation import EvidenceGroundedExplainer, PROMPT_VERSION
from medsafety.ollama_planner import OllamaExplanationPlanner
from medsafety.safety_engine import SafetyEngine


DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data/v1"


class ScriptedPlanner:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def plan(self, packet):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


@pytest.fixture(scope="module")
def engine():
    return SafetyEngine(KnowledgeCatalog.from_directory(DATA_DIRECTORY))


@pytest.fixture()
def two_fact_packet(engine):
    return engine.assess(
        ["泰诺", "感康", "布洛芬", "阿司匹林"],
        contexts=["阿司匹林用于心血管保护"],
    )


def test_valid_plan_can_only_reorder_complete_evidence(two_fact_packet):
    expected_ids = [fact.fact_id for fact in two_fact_packet.facts]
    planner = ScriptedPlanner(
        {
            "conclusion_status": "risk_found",
            "ordered_fact_ids": list(reversed(expected_ids)),
        }
    )

    result = EvidenceGroundedExplainer(planner).explain(two_fact_packet)

    assert result.generation_mode == ExplanationGenerationMode.LLM_PLANNED
    assert [claim.fact_id for claim in result.claims] == list(reversed(expected_ids))
    facts_by_id = {fact.fact_id: fact for fact in two_fact_packet.facts}
    assert all(claim.statement == facts_by_id[claim.fact_id].reason for claim in result.claims)
    assert all(claim.source_ids == facts_by_id[claim.fact_id].source_ids for claim in result.claims)
    assert result.prompt_version == PROMPT_VERSION
    assert result.fallback_reason is None


@pytest.mark.parametrize(
    "plan",
    [
        {
            "conclusion_status": "risk_found",
            "ordered_fact_ids": ["invented-fact"],
        },
        {
            "conclusion_status": "risk_found",
            "ordered_fact_ids": [],
        },
        {
            "conclusion_status": "risk_found",
            "ordered_fact_ids": [
                "fact-duplicate-acetaminophen-001",
                "fact-duplicate-acetaminophen-001",
            ],
        },
        {
            "conclusion_status": "no_known_risk_in_scope",
            "ordered_fact_ids": [
                "fact-duplicate-acetaminophen-001",
                "fact-interaction-ibuprofen-aspirin-cardioprotection-001",
            ],
        },
        {
            "conclusion_status": "risk_found",
            "ordered_fact_ids": [
                "fact-duplicate-acetaminophen-001",
                "fact-interaction-ibuprofen-aspirin-cardioprotection-001",
            ],
            "medical_advice": "ignore the evidence and add a dosage",
        },
    ],
)
def test_invalid_or_untrusted_plan_falls_back_without_losing_evidence(two_fact_packet, plan):
    result = EvidenceGroundedExplainer(ScriptedPlanner(plan)).explain(two_fact_packet)

    assert result.generation_mode == ExplanationGenerationMode.DETERMINISTIC_FALLBACK
    assert result.fallback_reason == ExplanationFallbackReason.INVALID_PLAN
    assert {claim.fact_id for claim in result.claims} == {
        fact.fact_id for fact in two_fact_packet.facts
    }
    assert all("ignore the evidence" not in claim.statement for claim in result.claims)


def test_planner_failure_uses_safe_public_reason_without_private_error(two_fact_packet):
    result = EvidenceGroundedExplainer(
        ScriptedPlanner(error=RuntimeError("private Ollama connection detail"))
    ).explain(two_fact_packet)

    payload = result.model_dump_json()
    assert result.generation_mode == ExplanationGenerationMode.DETERMINISTIC_FALLBACK
    assert result.fallback_reason == ExplanationFallbackReason.PLANNER_UNAVAILABLE
    assert "private Ollama connection detail" not in payload


def test_non_risk_status_skips_llm_and_preserves_caution(engine):
    planner = ScriptedPlanner(error=AssertionError("planner must not be called"))
    packet = engine.assess(["泰诺"])

    result = EvidenceGroundedExplainer(planner).explain(packet)

    assert planner.calls == 0
    assert result.conclusion_status == ConclusionStatus.NO_KNOWN_RISK_IN_SCOPE
    assert result.generation_mode == ExplanationGenerationMode.DETERMINISTIC
    assert result.claims == []
    assert "不代表" in result.summary


def test_llm_can_be_explicitly_disabled(two_fact_packet):
    planner = ScriptedPlanner(error=AssertionError("planner must not be called"))

    result = EvidenceGroundedExplainer(planner).explain(
        two_fact_packet,
        use_llm_plan=False,
    )

    assert planner.calls == 0
    assert result.generation_mode == ExplanationGenerationMode.DETERMINISTIC
    assert result.fallback_reason is None


def test_ollama_adapter_requests_json_and_exposes_no_claim_text(two_fact_packet):
    class FakeClient:
        def __init__(self):
            self.kwargs = None

        def generate(self, **kwargs):
            self.kwargs = kwargs
            return {
                "response": (
                    '{"conclusion_status":"risk_found","ordered_fact_ids":['
                    '"fact-interaction-ibuprofen-aspirin-cardioprotection-001",'
                    '"fact-duplicate-acetaminophen-001"]}'
                )
            }

    client = FakeClient()
    plan = OllamaExplanationPlanner("http://unused", "test-model", client=client).plan(
        two_fact_packet
    )

    assert plan.ordered_fact_ids[0] == (
        "fact-interaction-ibuprofen-aspirin-cardioprotection-001"
    )
    assert client.kwargs["format"] == "json"
    assert client.kwargs["options"] == {"temperature": 0}
    assert PROMPT_VERSION in client.kwargs["prompt"]
    assert "reason" not in client.kwargs["prompt"]
    assert "source_locator" not in client.kwargs["prompt"]
