from unittest.mock import patch

from fastapi.testclient import TestClient

from api import app
from medsafety.session_context import SessionContextReadStatus, SessionContextSnapshot


class MemorySessionStore:
    def __init__(self):
        self.items = {}

    def load(self, session_id, *, expected_data_version):
        stored = self.items.get(session_id)
        if stored is None:
            return SessionContextSnapshot(status=SessionContextReadStatus.EMPTY)
        if stored.data_version != expected_data_version:
            return SessionContextSnapshot(status=SessionContextReadStatus.STALE)
        return SessionContextSnapshot(
            status=SessionContextReadStatus.AVAILABLE,
            medication_ids=stored.medication_ids,
            context_ids=stored.context_ids,
            data_version=stored.data_version,
            prior_conclusion_status=stored.prior_conclusion_status,
        )

    def save(self, session_id, context):
        self.items[session_id] = context


def test_session_query_resolves_only_explicit_same_session_follow_up():
    store = MemorySessionStore()
    client = TestClient(app)
    with patch("api.get_session_context_store", return_value=store):
        first = client.post(
            "/api/v1/query/session",
            json={"question": "泰诺和感康能一起吃吗？", "session_id": "session-one", "use_llm_plan": False},
        )
        second = client.post(
            "/api/v1/query/session",
            json={"question": "刚才的药还能一起吃吗？", "session_id": "session-one", "use_llm_plan": False},
        )
        isolated = client.post(
            "/api/v1/query/session",
            json={"question": "刚才的药还能一起吃吗？", "session_id": "session-two", "use_llm_plan": False},
        )
        explicit = client.post(
            "/api/v1/query/session",
            json={"question": "布洛芬和阿司匹林能一起吃吗？", "session_id": "session-one", "use_llm_plan": False},
        )

    assert first.status_code == 200
    assert first.json()["session_context"]["write_status"] == "stored"
    assert second.status_code == 200
    assert second.json()["session_context"]["context_applied"] is True
    assert second.json()["resolution"]["medications"] == ["泰诺", "感康"]
    assert second.json()["explanation"]["conclusion_status"] == "risk_found"
    assert isolated.status_code == 200
    assert isolated.json()["session_context"]["context_applied"] is False
    assert isolated.json()["explanation"]["conclusion_status"] != "risk_found"
    assert explicit.status_code == 200
    assert explicit.json()["session_context"]["context_applied"] is False
    assert explicit.json()["resolution"]["medications"] == ["布洛芬", "阿司匹林"]


def test_session_query_without_store_requires_full_medication_names():
    client = TestClient(app)
    with patch("api.get_session_context_store", return_value=None):
        first = client.post(
            "/api/v1/query/session",
            json={"question": "泰诺和感康能一起吃吗？", "session_id": "session-one", "use_llm_plan": False},
        )
        follow_up = client.post(
            "/api/v1/query/session",
            json={"question": "刚才的药还能一起吃吗？", "session_id": "session-one", "use_llm_plan": False},
        )
    assert first.json()["session_context"]["write_status"] == "unavailable"
    assert follow_up.json()["session_context"]["context_applied"] is False
    assert follow_up.json()["resolution"]["status"] == "needs_clarification"

    invalid = client.post(
        "/api/v1/query/session",
        json={"question": "泰诺", "session_id": "user:*"},
    )
    assert invalid.status_code == 422
