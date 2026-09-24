import sqlite3

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from api import FeedbackRequest, app
from evaluation.feedback_report import feedback_report
from medsafety.feedback_store import FeedbackStore, RETENTION_SECONDS


def test_feedback_is_persistent_idempotent_and_contains_no_question(tmp_path):
    path = tmp_path / "feedback.sqlite3"
    first = FeedbackStore(path)
    feedback_id = first.register(
        "risk_found",
        data_version="v1.0.0-alpha.4",
        resolution_status="resolved",
        generation_mode="deterministic",
        context_applied=False,
    )
    second = FeedbackStore(path)

    assert second.submit(feedback_id, "not_useful", "missing_evidence") == "recorded"
    assert second.submit(feedback_id, "not_useful", "missing_evidence") == "already_recorded"
    assert second.submit(feedback_id, "useful", None) == "conflict"
    assert second.submit("0" * 32, "useful", None) == "not_found"

    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(query_feedback)")}
        assert columns == {
            "feedback_id", "conclusion_status", "created_at", "rating", "reason",
            "submitted_at", "data_version", "resolution_status", "generation_mode",
            "fallback_reason", "context_applied",
        }
    summary = second.summary()
    assert summary["registered_queries"] == 1
    assert summary["submitted_feedback"] == 1
    assert summary["reasons"] == {"missing_evidence": 1}
    assert summary["groups"][0]["data_version"] == "v1.0.0-alpha.4"
    assert summary["groups"][0]["context_applied"] == 0
    assert "feedback_id" not in str(summary)


def test_feedback_expiry_and_input_validation(tmp_path, monkeypatch):
    store = FeedbackStore(tmp_path / "feedback.sqlite3")
    monkeypatch.setattr("medsafety.feedback_store.time", lambda: 100000000)
    feedback_id = store.register("out_of_scope")
    monkeypatch.setattr("medsafety.feedback_store.time", lambda: 100000000 + RETENTION_SECONDS + 1)
    assert store.submit(feedback_id, "useful", None) == "not_found"
    assert store.summary()["registered_queries"] == 0

    with pytest.raises(ValidationError):
        FeedbackRequest(feedback_id="x", rating="useful")
    with pytest.raises(ValidationError):
        FeedbackRequest(feedback_id="0" * 32, rating="not_useful")
    with pytest.raises(ValidationError):
        FeedbackRequest(feedback_id="0" * 32, rating="useful", question="medical text")


def test_query_issues_feedback_capability_and_accepts_feedback(tmp_path):
    store = FeedbackStore(tmp_path / "feedback.sqlite3")
    app.state.feedback_store = store
    try:
        client = TestClient(app)
        result = client.post("/api/v1/query", json={"question": "泰诺和感康能一起吃吗？", "use_llm_plan": False})
        assert result.status_code == 200
        feedback_id = result.json()["feedback_id"]
        assert len(feedback_id) == 32
        submitted = client.post("/api/v1/feedback", json={"feedback_id": feedback_id, "rating": "useful"})
        assert submitted.status_code == 200
        assert submitted.json()["status"] == "recorded"
        group = store.summary()["groups"][0]
        assert group["conclusion_status"] == "risk_found"
        assert group["resolution_status"] == "resolved"
        assert group["data_version"] == "v1.0.0-alpha.4"
        assert group["generation_mode"] == "deterministic"
    finally:
        app.state.feedback_store = None


def test_feedback_storage_failure_does_not_change_safety_result():
    class UnavailableStore:
        def register(self, conclusion_status, **kwargs):
            raise sqlite3.OperationalError("disk unavailable")

    app.state.feedback_store = UnavailableStore()
    try:
        result = TestClient(app).post(
            "/api/v1/query",
            json={"question": "泰诺和感康能一起吃吗？", "use_llm_plan": False},
        )
        assert result.status_code == 200
        assert result.json()["explanation"]["conclusion_status"] == "risk_found"
        assert result.json()["feedback_id"] is None
    finally:
        app.state.feedback_store = None


def test_existing_feedback_database_is_migrated_without_losing_rows(tmp_path):
    path = tmp_path / "feedback.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE query_feedback (feedback_id TEXT PRIMARY KEY, "
            "conclusion_status TEXT NOT NULL, created_at INTEGER NOT NULL, "
            "rating TEXT, reason TEXT, submitted_at INTEGER)"
        )
        connection.execute(
            "INSERT INTO query_feedback VALUES (?, ?, ?, ?, ?, ?)",
            ("a" * 32, "risk_found", 9999999999, "useful", None, 9999999999),
        )

    store = FeedbackStore(path)
    summary = store.summary()
    assert summary["submitted_feedback"] == 1
    assert summary["groups"][0]["data_version"] is None
    assert store.submit("a" * 32, "useful", None) == "already_recorded"


def test_feedback_report_requires_existing_database_and_only_returns_aggregates(tmp_path):
    path = tmp_path / "feedback.sqlite3"
    with pytest.raises(FileNotFoundError):
        feedback_report(path)
    store = FeedbackStore(path)
    feedback_id = store.register("out_of_scope", resolution_status="unknown")
    store.submit(feedback_id, "not_useful", "wrong_entity")
    report = feedback_report(path)
    assert report["ratings"] == {"not_useful": 1}
    assert report["groups"][0]["resolution_status"] == "unknown"
    assert feedback_id not in str(report)
