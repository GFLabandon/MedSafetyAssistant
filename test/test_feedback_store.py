import sqlite3

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from api import FeedbackRequest, app
from medsafety.feedback_store import FeedbackStore, RETENTION_SECONDS


def test_feedback_is_persistent_idempotent_and_contains_no_question(tmp_path):
    path = tmp_path / "feedback.sqlite3"
    first = FeedbackStore(path)
    feedback_id = first.register("risk_found")
    second = FeedbackStore(path)

    assert second.submit(feedback_id, "not_useful", "missing_evidence") == "recorded"
    assert second.submit(feedback_id, "not_useful", "missing_evidence") == "already_recorded"
    assert second.submit(feedback_id, "useful", None) == "conflict"
    assert second.submit("0" * 32, "useful", None) == "not_found"

    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(query_feedback)")}
        assert columns == {"feedback_id", "conclusion_status", "created_at", "rating", "reason", "submitted_at"}


def test_feedback_expiry_and_input_validation(tmp_path, monkeypatch):
    store = FeedbackStore(tmp_path / "feedback.sqlite3")
    monkeypatch.setattr("medsafety.feedback_store.time", lambda: 100000000)
    feedback_id = store.register("out_of_scope")
    monkeypatch.setattr("medsafety.feedback_store.time", lambda: 100000000 + RETENTION_SECONDS + 1)
    assert store.submit(feedback_id, "useful", None) == "not_found"

    with pytest.raises(ValidationError):
        FeedbackRequest(feedback_id="x", rating="useful")
    with pytest.raises(ValidationError):
        FeedbackRequest(feedback_id="0" * 32, rating="not_useful")
    with pytest.raises(ValidationError):
        FeedbackRequest(feedback_id="0" * 32, rating="useful", question="medical text")


def test_query_issues_feedback_capability_and_accepts_feedback(tmp_path):
    app.state.feedback_store = FeedbackStore(tmp_path / "feedback.sqlite3")
    try:
        client = TestClient(app)
        result = client.post("/api/v1/query", json={"question": "泰诺和感康能一起吃吗？", "use_llm_plan": False})
        assert result.status_code == 200
        feedback_id = result.json()["feedback_id"]
        assert len(feedback_id) == 32
        submitted = client.post("/api/v1/feedback", json={"feedback_id": feedback_id, "rating": "useful"})
        assert submitted.status_code == 200
        assert submitted.json()["status"] == "recorded"
    finally:
        app.state.feedback_store = None


def test_feedback_storage_failure_does_not_change_safety_result():
    class UnavailableStore:
        def register(self, conclusion_status):
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
