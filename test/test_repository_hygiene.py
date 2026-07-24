from pathlib import PurePosixPath

from scripts.audit_public_repository import path_violations, secret_violations


def test_repository_audit_rejects_machine_local_and_generated_paths():
    assert path_violations(PurePosixPath(".env"), 10)
    assert path_violations(PurePosixPath("frontend/node_modules/pkg/index.js"), 10)
    assert path_violations(PurePosixPath("logic_layer/__pycache__/service.pyc"), 10)
    assert path_violations(PurePosixPath("model.bin"), 6 * 1024 * 1024)


def test_repository_audit_allows_versioned_evidence_and_public_assets():
    assert path_violations(PurePosixPath("eval/locked_cases.jsonl"), 1024) == []
    assert path_violations(PurePosixPath("reports/metrics.csv"), 1024) == []
    assert path_violations(PurePosixPath("assets/architecture.png"), 1024) == []


def test_repository_audit_reports_secret_type_without_echoing_value():
    token = b"sk-" + b"x" * 24
    assert secret_violations(token) == ["OpenAI-style token"]
