"""Safe request identifiers and structured application events."""

from __future__ import annotations

import json
import re
from uuid import uuid4


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def create_request_id() -> str:
    return uuid4().hex


def normalize_request_id(value: str | None) -> str:
    normalized = (value or "").strip()
    if normalized and REQUEST_ID_PATTERN.fullmatch(normalized):
        return normalized
    return create_request_id()


def structured_event(event: str, **fields) -> str:
    return json.dumps(
        {"event": event, **fields},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
