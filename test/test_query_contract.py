import hashlib

import pytest

from evaluation.query_contract import load_cases


def test_query_contract_rejects_changed_dataset(tmp_path):
    dataset = tmp_path / "cases.jsonl"
    checksum = tmp_path / "cases.sha256"
    original = b'{"case_id":"one","endpoint":"query","question":"a","expected":{}}\n'
    dataset.write_bytes(original)
    checksum.write_text(hashlib.sha256(original).hexdigest() + "\n", encoding="ascii")
    assert len(load_cases(dataset, checksum)[0]) == 1

    dataset.write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_cases(dataset, checksum)
