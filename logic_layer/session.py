"""Conversation session identifiers and lifecycle validation."""

from __future__ import annotations

import re
from uuid import uuid4


SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def create_session_id() -> str:
    """Create an opaque identifier safe for use inside Redis key namespaces."""

    return uuid4().hex


def normalize_session_id(value: str | None, *, generate_if_blank: bool = True) -> str:
    normalized = (value or "").strip()
    if not normalized and generate_if_blank:
        return create_session_id()
    if not SESSION_ID_PATTERN.fullmatch(normalized):
        raise ValueError(
            "session_id must contain only letters, numbers, underscores, or hyphens"
        )
    return normalized
