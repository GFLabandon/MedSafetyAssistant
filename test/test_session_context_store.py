import json

from logic_layer.session_context_store import RedisSessionContextStore
from medsafety.contracts import ConclusionStatus
from medsafety.session_context import (
    SessionContextReadStatus,
    StoredSessionContext,
)


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.ttls = {}

    def hgetall(self, key):
        return dict(self.data.get(key, {}))

    def hset(self, key, mapping):
        self.data[key] = dict(mapping)

    def expire(self, key, ttl):
        self.ttls[key] = ttl
        return True


def _stored_context(data_version="v1.0.0-alpha.4"):
    return StoredSessionContext(
        medication_ids=["med-tylenol", "med-gankang"],
        context_ids=[],
        data_version=data_version,
        prior_conclusion_status=ConclusionStatus.RISK_FOUND,
    )


def test_structured_context_round_trip_contains_ids_but_no_conversation_text():
    redis = FakeRedis()
    store = RedisSessionContextStore(redis, ttl_seconds=86400)

    store.save("session-a", _stored_context())
    snapshot = store.load(
        "session-a",
        expected_data_version="v1.0.0-alpha.4",
    )

    assert snapshot.status == SessionContextReadStatus.AVAILABLE
    assert snapshot.medication_ids == ["med-tylenol", "med-gankang"]
    assert redis.ttls == {"v1session:session-a:context": 86400}
    serialized = json.dumps(redis.data, ensure_ascii=False)
    assert "泰诺和感康能一起吃吗" not in serialized
    assert "assistant" not in serialized


def test_missing_stale_and_corrupt_contexts_are_not_released():
    redis = FakeRedis()
    store = RedisSessionContextStore(redis, ttl_seconds=60)

    missing = store.load("missing", expected_data_version="current")
    store.save("stale", _stored_context(data_version="old"))
    stale = store.load("stale", expected_data_version="current")
    redis.data["v1session:corrupt:context"] = {
        "schema_version": "stored-session-context-v1",
        "medication_ids": "not-json",
    }
    corrupt = store.load("corrupt", expected_data_version="current")

    assert missing.status == SessionContextReadStatus.EMPTY
    assert stale.status == SessionContextReadStatus.STALE
    assert stale.medication_ids == []
    assert corrupt.status == SessionContextReadStatus.UNAVAILABLE
    assert corrupt.medication_ids == []
