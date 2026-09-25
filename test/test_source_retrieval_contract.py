from hashlib import sha256

import pytest

from evaluation.source_retrieval_contract import load_cases


def test_source_retrieval_audit_requires_frozen_dataset(tmp_path):
    dataset = tmp_path / "cases.jsonl"
    checksum = tmp_path / "cases.sha256"
    raw = b'{"case_id":"negative","query":"xyz","expected_chunk_id":null,"expected_linked_fact_ids":[]}\n'
    dataset.write_bytes(raw)
    checksum.write_text(sha256(raw).hexdigest() + "\n", encoding="ascii")
    assert len(load_cases(dataset, checksum)[0]) == 1

    dataset.write_bytes(raw + b"\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_cases(dataset, checksum)
