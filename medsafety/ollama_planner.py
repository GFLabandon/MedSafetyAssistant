"""Ollama adapter for the tightly constrained V1 explanation plan."""

from __future__ import annotations

import json
from typing import Any

import ollama

from medsafety.contracts import EvidencePacket, ExplanationPlan
from medsafety.explanation import PROMPT_VERSION


class OllamaExplanationPlanner:
    """Ask Ollama only to order existing fact IDs; no prose is accepted."""

    def __init__(
        self,
        host: str,
        model: str,
        client: Any | None = None,
        timeout_seconds: float = 5.0,
    ):
        self.model = model
        self.client = client or ollama.Client(host=host, timeout=timeout_seconds)

    def plan(self, packet: EvidencePacket) -> ExplanationPlan:
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
        prompt = (
            f"Prompt version: {PROMPT_VERSION}\n"
            "You are an evidence ordering component, not a medical author. "
            "Return one JSON object with exactly two keys: conclusion_status and "
            "ordered_fact_ids. Preserve conclusion_status. Include every supplied fact_id "
            "exactly once, include no other ID, and order the most severe or actionable "
            "evidence first. Do not output prose, advice, markdown, or new medical facts.\n"
            f"Evidence packet: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
        )
        response = self.client.generate(
            model=self.model,
            prompt=prompt,
            format="json",
            options={"temperature": 0},
        )
        content = response.get("response") if isinstance(response, dict) else response.response
        if not isinstance(content, str):
            raise ValueError("Ollama response does not contain JSON text")
        return ExplanationPlan.model_validate(json.loads(content))
