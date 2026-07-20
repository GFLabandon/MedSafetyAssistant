"""Ollama adapter for the tightly constrained V1 explanation plan."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from time import perf_counter
from typing import Any

import ollama

from medsafety.contracts import EvidencePacket, ExplanationPlan
from medsafety.explanation import PROMPT_VERSION


DEFAULT_GENERATION_OPTIONS = {
    "temperature": 0,
    "seed": 42,
    "num_predict": 256,
}


def _response_field(response: Any, name: str):
    if isinstance(response, dict):
        return response.get(name)
    return getattr(response, name, None)


@dataclass(frozen=True)
class OllamaPlanAttempt:
    raw_response: str | None
    parsed_payload: Any | None
    latency_ms: float
    error_category: str | None
    error_type: str | None
    response_metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OllamaExplanationPlanner:
    """Ask Ollama only to order existing fact IDs; no prose is accepted."""

    def __init__(
        self,
        host: str,
        model: str,
        client: Any | None = None,
        timeout_seconds: float = 5.0,
        options: dict[str, Any] | None = None,
    ):
        self.model = model
        self.client = client or ollama.Client(host=host, timeout=timeout_seconds)
        self.options = dict(options or DEFAULT_GENERATION_OPTIONS)

    @staticmethod
    def build_prompt(packet: EvidencePacket) -> str:
        payload = {
            "conclusion_status": packet.conclusion_status.value,
            "facts": [
                {
                    "fact_id": fact.fact_id,
                    "risk_type": fact.risk_type.value,
                    "severity": fact.severity.value,
                }
                for fact in packet.facts
            ],
        }
        return (
            f"Prompt version: {PROMPT_VERSION}\n"
            "You are an evidence ordering component, not a medical author. "
            "Return one JSON object with exactly two keys: conclusion_status and "
            "ordered_fact_ids. Preserve conclusion_status. Include every supplied fact_id "
            "exactly once, include no other ID, and order the most severe or actionable "
            "evidence first. Do not output prose, advice, markdown, or new medical facts.\n"
            f"Evidence packet: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
        )

    def generate_attempt(self, packet: EvidencePacket) -> OllamaPlanAttempt:
        started = perf_counter()
        try:
            response = self.client.generate(
                model=self.model,
                prompt=self.build_prompt(packet),
                format="json",
                think=False,
                options=self.options,
            )
        except Exception as exc:
            return OllamaPlanAttempt(
                raw_response=None,
                parsed_payload=None,
                latency_ms=round((perf_counter() - started) * 1000, 3),
                error_category="request_error",
                error_type=type(exc).__name__,
                response_metadata={},
            )

        latency_ms = round((perf_counter() - started) * 1000, 3)
        content = _response_field(response, "response")
        metadata = {}
        for field in (
            "model",
            "created_at",
            "done",
            "done_reason",
            "total_duration",
            "load_duration",
            "prompt_eval_count",
            "prompt_eval_duration",
            "eval_count",
            "eval_duration",
        ):
            value = _response_field(response, field)
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            if value is not None:
                metadata[field] = value

        if not isinstance(content, str):
            return OllamaPlanAttempt(
                raw_response=None,
                parsed_payload=None,
                latency_ms=latency_ms,
                error_category="invalid_response_shape",
                error_type="ValueError",
                response_metadata=metadata,
            )
        try:
            parsed_payload = json.loads(content)
        except json.JSONDecodeError as exc:
            return OllamaPlanAttempt(
                raw_response=content,
                parsed_payload=None,
                latency_ms=latency_ms,
                error_category="invalid_json",
                error_type=type(exc).__name__,
                response_metadata=metadata,
            )
        return OllamaPlanAttempt(
            raw_response=content,
            parsed_payload=parsed_payload,
            latency_ms=latency_ms,
            error_category=None,
            error_type=None,
            response_metadata=metadata,
        )

    def plan(self, packet: EvidencePacket) -> ExplanationPlan:
        attempt = self.generate_attempt(packet)
        if attempt.error_category == "request_error":
            raise ConnectionError("Ollama planner request failed")
        if attempt.error_category is not None:
            raise ValueError(f"Ollama planner returned {attempt.error_category}")
        return ExplanationPlan.model_validate(attempt.parsed_payload)
