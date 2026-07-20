import json
from pathlib import Path

import pytest

from evaluation.cypher_inventory import parse_legacy_risk_facts
from evaluation.dataset import load_cases, load_explanation_guardrail_cases
from evaluation.entity_baseline import evaluate_entity_extractor
from evaluation.explanation_guardrails import evaluate_explanation_guardrails
from evaluation.safety_engine_baseline import evaluate_safety_engine
from logic_layer.entity_utils import exact_entity_extraction
from medsafety.catalog import KnowledgeCatalog
from medsafety.safety_engine import SafetyEngine


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
