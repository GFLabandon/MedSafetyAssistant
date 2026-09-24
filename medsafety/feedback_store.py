"""Anonymous, bounded query feedback without question text or user identifiers."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from time import time
from uuid import uuid4


RETENTION_SECONDS = 30 * 24 * 60 * 60


class FeedbackStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS query_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    conclusion_status TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    rating TEXT,
                    reason TEXT,
                    submitted_at INTEGER
                )
            """)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=2)

    def register(self, conclusion_status: str) -> str:
        feedback_id = uuid4().hex
        now = int(time())
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM query_feedback WHERE created_at < ?",
                (now - RETENTION_SECONDS,),
            )
            connection.execute(
                "INSERT INTO query_feedback (feedback_id, conclusion_status, created_at) VALUES (?, ?, ?)",
                (feedback_id, conclusion_status, now),
            )
        return feedback_id

    def submit(self, feedback_id: str, rating: str, reason: str | None) -> str:
        now = int(time())
        with self._connect() as connection:
            updated = connection.execute(
                "UPDATE query_feedback SET rating = ?, reason = ?, submitted_at = ? "
                "WHERE feedback_id = ? AND rating IS NULL AND created_at >= ?",
                (rating, reason, now, feedback_id, now - RETENTION_SECONDS),
            )
            if updated.rowcount:
                return "recorded"
            existing = connection.execute(
                "SELECT rating, reason FROM query_feedback WHERE feedback_id = ? AND created_at >= ?",
                (feedback_id, now - RETENTION_SECONDS),
            ).fetchone()
        if existing is None:
            return "not_found"
        return "already_recorded" if existing == (rating, reason) else "conflict"
