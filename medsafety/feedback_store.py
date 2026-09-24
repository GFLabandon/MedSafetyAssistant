"""Anonymous, bounded query feedback without question text or user identifiers."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from time import time
from uuid import uuid4


RETENTION_SECONDS = 30 * 24 * 60 * 60
ATTRIBUTION_COLUMNS = {
    "data_version": "TEXT",
    "resolution_status": "TEXT",
    "generation_mode": "TEXT",
    "fallback_reason": "TEXT",
    "context_applied": "INTEGER",
}


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
                    submitted_at INTEGER,
                    data_version TEXT,
                    resolution_status TEXT,
                    generation_mode TEXT,
                    fallback_reason TEXT,
                    context_applied INTEGER
                )
            """)
            existing = {
                row[1] for row in connection.execute("PRAGMA table_info(query_feedback)")
            }
            for column, column_type in ATTRIBUTION_COLUMNS.items():
                if column not in existing:
                    connection.execute(
                        f"ALTER TABLE query_feedback ADD COLUMN {column} {column_type}"
                    )

    def _connect(self):
        return sqlite3.connect(self.path, timeout=2)

    def register(
        self,
        conclusion_status: str,
        *,
        data_version: str | None = None,
        resolution_status: str | None = None,
        generation_mode: str | None = None,
        fallback_reason: str | None = None,
        context_applied: bool | None = None,
    ) -> str:
        feedback_id = uuid4().hex
        now = int(time())
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM query_feedback WHERE created_at < ?",
                (now - RETENTION_SECONDS,),
            )
            connection.execute(
                "INSERT INTO query_feedback "
                "(feedback_id, conclusion_status, created_at, data_version, "
                "resolution_status, generation_mode, fallback_reason, context_applied) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    feedback_id,
                    conclusion_status,
                    now,
                    data_version,
                    resolution_status,
                    generation_mode,
                    fallback_reason,
                    None if context_applied is None else int(context_applied),
                ),
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

    def summary(self) -> dict:
        """Aggregate current-window feedback without exposing row identifiers."""
        cutoff = int(time()) - RETENTION_SECONDS
        with self._connect() as connection:
            registered, submitted = connection.execute(
                "SELECT COUNT(*), COUNT(rating) FROM query_feedback WHERE created_at >= ?",
                (cutoff,),
            ).fetchone()
            ratings = dict(connection.execute(
                "SELECT rating, COUNT(*) FROM query_feedback "
                "WHERE created_at >= ? AND rating IS NOT NULL GROUP BY rating",
                (cutoff,),
            ).fetchall())
            reasons = dict(connection.execute(
                "SELECT reason, COUNT(*) FROM query_feedback "
                "WHERE created_at >= ? AND reason IS NOT NULL GROUP BY reason",
                (cutoff,),
            ).fetchall())
            columns = (
                "data_version", "conclusion_status", "resolution_status",
                "generation_mode", "fallback_reason", "context_applied", "rating", "reason",
            )
            groups = [
                dict(zip((*columns, "count"), row))
                for row in connection.execute(
                    "SELECT data_version, conclusion_status, resolution_status, "
                    "generation_mode, fallback_reason, context_applied, rating, reason, COUNT(*) "
                    "FROM query_feedback WHERE created_at >= ? AND rating IS NOT NULL "
                    "GROUP BY data_version, conclusion_status, resolution_status, "
                    "generation_mode, fallback_reason, context_applied, rating, reason "
                    "ORDER BY COUNT(*) DESC, conclusion_status, rating",
                    (cutoff,),
                )
            ]
        return {
            "window_days": 30,
            "registered_queries": registered,
            "submitted_feedback": submitted,
            "ratings": ratings,
            "reasons": reasons,
            "groups": groups,
        }
