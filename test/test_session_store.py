from concurrent.futures import ThreadPoolExecutor
from fnmatch import fnmatch
from threading import Lock

import pytest

from config import Config
from logic_layer.session import create_session_id, normalize_session_id
from logic_layer.vector_store import VectorStore


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.ttls = {}
        self._lock = Lock()

    def hset(self, key, mapping):
        with self._lock:
            self.data[key] = dict(mapping)

    def expire(self, key, ttl):
        with self._lock:
            self.ttls[key] = ttl
        return True

    def scan(self, cursor=0, match=None, count=None):
        del cursor, count
        with self._lock:
            keys = [key for key in self.data if fnmatch(key, match)]
        return 0, keys

    def scan_iter(self, match=None):
        with self._lock:
            return iter([key for key in self.data if fnmatch(key, match)])

    def hgetall(self, key):
        with self._lock:
            return dict(self.data.get(key, {}))

    def delete(self, *keys):
        deleted = 0
        with self._lock:
            for key in keys:
                if key in self.data:
                    deleted += 1
                    del self.data[key]
                    self.ttls.pop(key, None)
        return deleted


class FakeEmbeddingService:
    embedding_model = "test-embedding-v1"

    @staticmethod
    def embed_text(text):
        return [1.0, float(len(text) % 2)]


def build_store():
    store = VectorStore.__new__(VectorStore)
    store.redis_client = FakeRedis()
    store.embedding_service = FakeEmbeddingService()
    store.ollama_client = None
    return store


def test_session_ids_are_opaque_and_reject_redis_glob_characters():
    assert normalize_session_id(create_session_id())
    with pytest.raises(ValueError):
        normalize_session_id("user:*", generate_if_blank=False)
    with pytest.raises(ValueError):
        normalize_session_id("", generate_if_blank=False)


def test_concurrent_sessions_receive_ttl_and_never_cross_read():
    store = build_store()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                store.store_conversation,
                "A 用户问题",
                "A 助手回答",
                "session-a",
            ),
            executor.submit(
                store.store_conversation,
                "B 用户问题",
                "B 助手回答",
                "session-b",
            ),
        ]
        for future in futures:
            future.result()

    assert len(store.redis_client.data) == 6
    assert set(store.redis_client.ttls.values()) == {Config.SESSION_TTL_SECONDS}

    session_a = store.search_similar_conversations(
        "A 用户问题",
        "session-a",
        top_k=3,
    )
    session_b = store.search_similar_conversations(
        "B 用户问题",
        "session-b",
        top_k=3,
    )

    assert session_a
    assert session_b
    assert all(item["text"].startswith("A") for item in session_a)
    assert all(item["text"].startswith("B") for item in session_b)


def test_clear_session_removes_only_target_namespace():
    store = build_store()
    store.store_conversation("A question", "A answer", "session-a")
    store.store_conversation("B question", "B answer", "session-b")

    deleted = store.clear_session("session-a")

    assert deleted == 3
    assert not any(":session-a:" in key for key in store.redis_client.data)
    assert any(":session-b:" in key for key in store.redis_client.data)


def test_vector_search_skips_unknown_model_and_dimension_records():
    store = build_store()
    store.store_conversation("current question", "current answer", "session-a")
    store.redis_client.hset(
        "conv:session-a:user:legacy",
        mapping={
            "text": "legacy without provenance",
            "role": "user",
            "vector": "[1.0, 1.0]",
            "session_id": "session-a",
            "timestamp": "1",
        },
    )
    store.redis_client.hset(
        "conv:session-a:user:wrong-model",
        mapping={
            "text": "wrong model",
            "role": "user",
            "vector": "[1.0, 1.0]",
            "embedding_model": "different-embedding-v2",
            "embedding_dimensions": "2",
            "session_id": "session-a",
            "timestamp": "2",
        },
    )
    store.redis_client.hset(
        "conv:session-a:user:wrong-dimension",
        mapping={
            "text": "wrong dimension",
            "role": "user",
            "vector": "[1.0, 1.0, 1.0]",
            "embedding_model": "test-embedding-v1",
            "embedding_dimensions": "3",
            "session_id": "session-a",
            "timestamp": "3",
        },
    )

    results = store.search_similar_conversations(
        "current question",
        "session-a",
        top_k=10,
    )

    assert {item["text"] for item in results} == {
        "current question",
        "current answer",
    }
    current_records = [
        data
        for data in store.redis_client.data.values()
        if data.get("text", "").startswith("current")
    ]
    assert all(data["embedding_model"] == "test-embedding-v1" for data in current_records)
    assert all(data["embedding_dimensions"] == "2" for data in current_records)
