import hashlib
import json
from pathlib import Path

import pytest

from evaluation.cypher_inventory import parse_legacy_risk_facts
from evaluation.dataset import load_cases, load_explanation_guardrail_cases
from evaluation.entity_baseline import evaluate_entity_extractor
from evaluation.explanation_guardrails import evaluate_explanation_guardrails
from evaluation.ollama_explanation import evaluate_ollama_explanations
from evaluation.safety_engine_baseline import evaluate_safety_engine
from logic_layer.entity_utils import exact_entity_extraction
from medsafety.catalog import KnowledgeCatalog
from medsafety.safety_engine import SafetyEngine
from medsafety.ollama_planner import OllamaPlanAttempt


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_dev_dataset_is_valid_and_has_expected_scope():
    cases = load_cases(REPOSITORY_ROOT / "eval/dev_cases.jsonl")

    assert len(cases) == 18
    assert all(case.split == "dev" for case in cases)
    assert all(case.expected.conclusion_status is None for case in cases)


def test_dataset_loader_rejects_duplicate_ids(tmp_path):
    payload = {
        "case_id": "duplicate_case",
        "split": "dev",
        "category": "test",
        "question": "测试问题",
        "expected": {"drugs": [], "conditions": []},
        "label_status": "legacy_unreviewed",
    }
    dataset = tmp_path / "duplicate.jsonl"
    dataset.write_text(json.dumps(payload, ensure_ascii=False) + "\n" + json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate case_id"):
        load_cases(dataset)


def test_rule_entity_baseline_reports_metrics_and_known_failures():
    cases = load_cases(REPOSITORY_ROOT / "eval/dev_cases.jsonl")
    report = evaluate_entity_extractor(cases, exact_entity_extraction)

    assert report["runner"] == "rule_entities"
    assert report["dataset_cases"] == 18
    assert 0.0 <= report["metrics"]["entity_micro_f1"] <= 1.0
    assert report["counts"]["failed_cases"] >= 4
    assert "dev_fenbid_alias" in {failure["case_id"] for failure in report["failures"]}


def test_legacy_cypher_inventory_has_all_current_risk_relationships():
    names, facts = parse_legacy_risk_facts(REPOSITORY_ROOT / "data_layer/medical_graph.cypher.txt")

    assert len(names) == 50
    assert len([fact for fact in facts if fact.relationship_type == "CONTRAINDICATED_IN"]) == 22
    assert len([fact for fact in facts if fact.relationship_type == "INTERACTS_WITH"]) == 9
    assert all(fact.source_label != "MISSING" for fact in facts)


def test_source_aligned_safety_engine_dataset_matches_current_engine():
    cases = load_cases(REPOSITORY_ROOT / "eval/safety_engine_dev.jsonl")
    catalog = KnowledgeCatalog.from_directory(REPOSITORY_ROOT / "data/v1")
    report = evaluate_safety_engine(cases, SafetyEngine(catalog))

    assert len(cases) == 9
    assert report["metrics"]["conclusion_accuracy"] == 1.0
    assert report["metrics"]["fact_set_exact_match"] == 1.0
    assert report["metrics"]["medication_set_exact_match"] == 1.0
    assert report["metrics"]["context_set_exact_match"] == 1.0
    assert report["failures"] == []

    saved_report = json.loads(
        (REPOSITORY_ROOT / "reports/baseline-safety-engine-v1-alpha.2.json").read_text(
            encoding="utf-8"
        )
    )
    assert saved_report["data_version"] == catalog.data_version
    assert saved_report["dataset_cases"] == len(cases)
    assert saved_report["metrics"] == report["metrics"]
    assert saved_report["failures"] == report["failures"]


def test_explanation_guardrail_dataset_passes_all_scripted_attacks():
    cases = load_explanation_guardrail_cases(
        REPOSITORY_ROOT / "eval/explanation_guardrails_v1.jsonl"
    )
    catalog = KnowledgeCatalog.from_directory(REPOSITORY_ROOT / "data/v1")

    report = evaluate_explanation_guardrails(cases, SafetyEngine(catalog))

    assert len(cases) == 9
    assert report["prompt_version"] == "evidence-order-v1"
    assert report["metrics"]["case_pass_rate"] == 1.0
    assert report["metrics"]["conclusion_preservation_rate"] == 1.0
    assert report["metrics"]["fact_reference_coverage"] == 1.0
    assert report["metrics"]["extractive_claim_rate"] == 1.0
    assert report["metrics"]["source_traceability_rate"] == 1.0
    assert report["metrics"]["unsupported_claim_rate"] == 0.0
    assert report["failures"] == []


def test_saved_explanation_guardrail_report_matches_runner():
    dataset_path = REPOSITORY_ROOT / "eval/explanation_guardrails_v1.jsonl"
    cases = load_explanation_guardrail_cases(dataset_path)
    catalog = KnowledgeCatalog.from_directory(REPOSITORY_ROOT / "data/v1")
    report = evaluate_explanation_guardrails(cases, SafetyEngine(catalog))
    saved_report = json.loads(
        (REPOSITORY_ROOT / "reports/baseline-explanation-guardrails-v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert saved_report["code_commit"] == "a5abe1d6d032023b00fb76c9665060bf825810c3"
    assert saved_report["dataset_sha256"] == hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    assert saved_report["data_version"] == catalog.data_version
    assert saved_report["dataset_cases"] == len(cases)
    assert saved_report["prompt_version"] == report["prompt_version"]
    assert saved_report["planner"] == report["planner"]
    assert saved_report["metrics"] == report["metrics"]
    assert saved_report["failures"] == report["failures"]
    assert saved_report["working_tree_dirty"] is False


def test_real_model_runner_repeats_and_records_raw_plans_without_network():
    cases = load_cases(REPOSITORY_ROOT / "eval/explanation_model_dev_v1.jsonl")
    catalog = KnowledgeCatalog.from_directory(REPOSITORY_ROOT / "data/v1")

    class FakePlanner:
        options = {"temperature": 0, "seed": 42, "num_predict": 256}
        prompt_version = "evidence-order-v2"

        def generate_attempt(self, packet):
            payload = {
                "conclusion_status": packet.conclusion_status.value,
                "ordered_fact_ids": [fact.fact_id for fact in packet.facts],
            }
            return OllamaPlanAttempt(
                raw_response=json.dumps(payload, ensure_ascii=False),
                parsed_payload=payload,
                latency_ms=12.5,
                error_category=None,
                error_type=None,
                response_metadata={"eval_count": 8},
            )

        def plan(self, packet):
            raise AssertionError("non-risk cases must not call the planner")

    report = evaluate_ollama_explanations(
        cases,
        SafetyEngine(catalog),
        FakePlanner(),
        repetitions=3,
    )

    assert len(cases) == 7
    assert report["repetitions"] == 3
    assert report["total_case_runs"] == 21
    assert report["planner_attempts"] == 15
    assert report["metrics"]["valid_plan_rate"] == 1.0
    assert report["metrics"]["fallback_rate"] == 0.0
    assert report["metrics"]["raw_plan_consistency_rate"] == 1.0
    assert report["metrics"]["valid_plan_consistency_rate"] == 1.0
    assert report["metrics"]["pipeline_pass_rate"] == 1.0
    assert report["metrics"]["unsupported_claim_rate"] == 0.0
    assert report["metrics"]["planner_latency_ms_p50"] == 12.5
    assert all(
        record["attempt"]["raw_response"]
        for record in report["records"]
        if record["attempt"] is not None
    )


def test_saved_real_model_v1_baseline_and_raw_plans_are_consistent():
    dataset_path = REPOSITORY_ROOT / "eval/explanation_model_dev_v1.jsonl"
    report = json.loads(
        (REPOSITORY_ROOT / "reports/baseline-ollama-evidence-order-v1.json").read_text(
            encoding="utf-8"
        )
    )
    raw_records = [
        json.loads(line)
        for line in (
            REPOSITORY_ROOT / "reports/raw/ollama-evidence-order-v1-plans.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert report["dataset_sha256"] == hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    assert report["model"]["digest"] == (
        "e0979632db5a88d1a53884cb2a941772d10ff5d055aabaa6801c4e36f3a6c2d7"
    )
    assert report["planner_attempts"] == len(raw_records) == 15
    assert report["metrics"]["valid_plan_rate"] == 0.6
    assert report["metrics"]["fallback_rate"] == 0.4
    assert report["metrics"]["pipeline_pass_rate"] == 1.0
    assert report["metrics"]["unsupported_claim_rate"] == 0.0
    assert sum(
        record["generation_mode"] == "deterministic_fallback"
        for record in raw_records
    ) == report["failure_summary"]["invalid_plans"] == 6
    assert all(json.loads(record["raw_response"]) for record in raw_records)


def test_saved_real_model_v2_baseline_improves_plan_validity_without_weakening_safety():
    dataset_path = REPOSITORY_ROOT / "eval/explanation_model_dev_v1.jsonl"
    v1 = json.loads(
        (REPOSITORY_ROOT / "reports/baseline-ollama-evidence-order-v1.json").read_text(
            encoding="utf-8"
        )
    )
    v2 = json.loads(
        (REPOSITORY_ROOT / "reports/baseline-ollama-evidence-order-v2.json").read_text(
            encoding="utf-8"
        )
    )
    raw_records = [
        json.loads(line)
        for line in (
            REPOSITORY_ROOT / "reports/raw/ollama-evidence-order-v2-plans.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert v2["dataset_sha256"] == hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    assert v2["dataset_sha256"] == v1["dataset_sha256"]
    assert v2["model"]["digest"] == v1["model"]["digest"]
    assert v2["planner_attempts"] == len(raw_records) == 15
    assert v2["metrics"]["valid_plan_rate"] > v1["metrics"]["valid_plan_rate"]
    assert v2["metrics"]["fallback_rate"] < v1["metrics"]["fallback_rate"]
    assert v2["metrics"]["valid_plan_rate"] == 1.0
    assert v2["metrics"]["fallback_rate"] == 0.0
    assert v2["metrics"]["pipeline_pass_rate"] == 1.0
    assert v2["metrics"]["unsupported_claim_rate"] == 0.0
    assert v2["model_failures"] == []
    assert v2["pipeline_failures"] == []
    assert all(record["generation_mode"] == "llm_planned" for record in raw_records)
    assert all(json.loads(record["raw_response"]) for record in raw_records)
