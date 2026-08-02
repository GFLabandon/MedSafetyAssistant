import hashlib
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluation.tool_shadow_dataset import (
    ShadowToolSelectionCase,
    ShadowWorkflowStage,
    load_shadow_tool_cases,
)
from scripts.build_tool_shadow_dataset import build_cases, render_cases


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = REPOSITORY_ROOT / "eval/tool_shadow_v1.jsonl"
CHECKSUM_PATH = REPOSITORY_ROOT / "eval/tool_shadow_v1.sha256"


def test_frozen_shadow_dataset_has_expected_size_splits_and_coverage():
    cases = load_shadow_tool_cases(DATASET_PATH)

    assert len(cases) == 60
    assert Counter(case.split for case in cases) == {"dev": 40, "test": 20}
    assert Counter(case.state.stage for case in cases) == {
        ShadowWorkflowStage.START: 20,
        ShadowWorkflowStage.AFTER_RESOLUTION: 20,
        ShadowWorkflowStage.AFTER_EVIDENCE: 20,
    }
    assert Counter(case.expected.name.value for case in cases) == {
        "resolve_medications": 20,
        "query_safety_graph": 7,
        "request_clarification": 13,
        "render_evidence_explanation": 20,
    }
    assert any("injection" in case.tags for case in cases)
    assert all(case.schema_version == "tool-shadow-case-v1" for case in cases)


def test_frozen_shadow_dataset_matches_generator_and_checksum():
    payload = DATASET_PATH.read_text(encoding="utf-8")
    assert payload == render_cases(build_cases())

    expected_digest, relative_path = CHECKSUM_PATH.read_text(encoding="utf-8").split()
    assert relative_path == "eval/tool_shadow_v1.jsonl"
    assert hashlib.sha256(payload.encode("utf-8")).hexdigest() == expected_digest


def test_shadow_dataset_loader_can_select_dev_without_reading_test_labels():
    dev_cases = load_shadow_tool_cases(DATASET_PATH, split="dev")

    assert len(dev_cases) == 40
    assert all(case.split == "dev" for case in dev_cases)
    start_indexes = [
        int(case.case_id.rsplit("_", 1)[-1])
        for case in dev_cases
        if case.case_id.startswith("shadow_start_")
    ]
    assert max(start_indexes) == 14


def test_shadow_case_rejects_label_that_disagrees_with_oracle():
    valid = load_shadow_tool_cases(DATASET_PATH, split="dev")[0].model_dump(mode="json")
    valid["expected"] = {
        "name": "render_evidence_explanation",
        "arguments": {"packet_call_id": "forged-packet"},
    }

    with pytest.raises(ValidationError, match="deterministic oracle"):
        ShadowToolSelectionCase.model_validate(valid)
