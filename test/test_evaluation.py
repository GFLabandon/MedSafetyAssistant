import json
from pathlib import Path

import pytest

from evaluation.cypher_inventory import parse_legacy_risk_facts
from evaluation.dataset import load_cases
from evaluation.entity_baseline import evaluate_entity_extractor
from logic_layer.entity_utils import exact_entity_extraction


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
