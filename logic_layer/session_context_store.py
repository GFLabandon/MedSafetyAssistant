"""Redis adapter for the V1 structured session-context contract."""

from __future__ import annotations

import json

from pydantic import ValidationError

from logic_layer.session import normalize_session_id
from medsafety.session_context import (
    SessionContextReadStatus,
    SessionContextSnapshot,
    StoredSessionContext,
)


class RedisSessionContextStore:
    """Persist only validated entity IDs under a namespace separate from legacy text."""

    KEY_PREFIX = "v1session"

    def __init__(self, redis_client, *, ttl_seconds: int):
        if ttl_seconds <= 0:
            raise ValueError("session context TTL must be positive")
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    def load(
        self,
        session_id: str,
        *,
        expected_data_version: str,
    ) -> SessionContextSnapshot:
        session_id = normalize_session_id(session_id, generate_if_blank=False)
        raw = self._redis.hgetall(self._key(session_id))
        if not raw:
            return SessionContextSnapshot(status=SessionContextReadStatus.EMPTY)
        try:
            stored = StoredSessionContext.model_validate(
                {
                    "schema_version": raw.get("schema_version"),
                    "medication_ids": json.loads(raw.get("medication_ids", "[]")),
                    "context_ids": json.loads(raw.get("context_ids", "[]")),
                    "data_version": raw.get("data_version"),
                    "prior_conclusion_status": raw.get("prior_conclusion_status"),
                }
            )
        except (ValidationError, TypeError, ValueError, json.JSONDecodeError):
            return SessionContextSnapshot(status=SessionContextReadStatus.UNAVAILABLE)
        if stored.data_version != expected_data_version:
            return SessionContextSnapshot(status=SessionContextReadStatus.STALE)
        return SessionContextSnapshot(
            status=SessionContextReadStatus.AVAILABLE,
            medication_ids=stored.medication_ids,
            context_ids=stored.context_ids,
            data_version=stored.data_version,
            prior_conclusion_status=stored.prior_conclusion_status,
        )

    def save(self, session_id: str, context: StoredSessionContext) -> None:
        session_id = normalize_session_id(session_id, generate_if_blank=False)
        key = self._key(session_id)
        self._redis.hset(
            key,
            mapping={
                "schema_version": context.schema_version,
                "medication_ids": json.dumps(
                    context.medication_ids,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "context_ids": json.dumps(
                    context.context_ids,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "data_version": context.data_version,
                "prior_conclusion_status": context.prior_conclusion_status.value,
            },
        )
        if not self._redis.expire(key, self._ttl_seconds):
            raise RuntimeError("Redis rejected session context TTL")

    @classmethod
    def _key(cls, session_id: str) -> str:
        return f"{cls.KEY_PREFIX}:{session_id}:context"
