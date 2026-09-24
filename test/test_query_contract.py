import hashlib
import json

import pytest

from evaluation.query_contract import load_cases


def test_query_contract_rejects_changed_dataset(tmp_path):
    dataset = tmp_path / "cases.jsonl"
    checksum = tmp_path / "cases.sha256"
    original = (json.dumps({
        "case_id": "one", "endpoint": "query", "question": "a",
        "expected": {"conclusion_status": "out_of_scope", "resolution_status": "unknown", "fact_ids": []},
    }) + "\n").encode()
    dataset.write_bytes(original)
    checksum.write_text(hashlib.sha256(original).hexdigest() + "\n", encoding="ascii")
    assert len(load_cases(dataset, checksum)[0]) == 1

    dataset.write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_cases(dataset, checksum)


def test_query_contract_rejects_incomplete_expectations(tmp_path):
    dataset = tmp_path / "cases.jsonl"
    checksum = tmp_path / "cases.sha256"
    raw = (json.dumps({
        "case_id": "one", "endpoint": "session", "session_id": "s1", "question": "泰诺",
        "expected": {"conclusion_status": "no_known_risk_in_scope"},
    }) + "\n").encode()
    dataset.write_bytes(raw)
    checksum.write_text(hashlib.sha256(raw).hexdigest() + "\n", encoding="ascii")

    with pytest.raises(ValueError, match="incomplete expected result"):
        load_cases(dataset, checksum)
