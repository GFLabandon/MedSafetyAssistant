"""Frozen engineering regression for the public V1 query APIs.

This suite checks API and evidence contracts, not clinical generalization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import app
from medsafety.catalog import KnowledgeCatalog
from medsafety.session_context import SessionContextReadStatus, SessionContextSnapshot


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "eval/query_contract_v1.jsonl"
CHECKSUM = ROOT / "eval/query_contract_v1.sha256"


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


def load_cases(dataset: Path = DATASET, checksum: Path = CHECKSUM) -> tuple[list[dict], str]:
    raw = dataset.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    expected = checksum.read_text(encoding="ascii").strip().split()[0]
    if digest != expected:
        raise ValueError(f"dataset checksum mismatch: expected {expected}, got {digest}")
    cases = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if not cases:
        raise ValueError("empty contract dataset")
    ids = [case["case_id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case_id")
    for case in cases:
        allowed = {"case_id", "endpoint", "session_id", "question", "expected"}
        if set(case) - allowed or not isinstance(case.get("question"), str) or not case["question"].strip():
            raise ValueError(f"invalid case shape: {case.get('case_id')}")
        if case["endpoint"] not in {"query", "session"}:
            raise ValueError(f"invalid endpoint: {case['case_id']}")
        if case["endpoint"] == "session" and not case.get("session_id"):
            raise ValueError(f"missing session_id: {case['case_id']}")
        required = {"conclusion_status", "resolution_status", "fact_ids"}
        if case["endpoint"] == "session":
            required |= {"context_applied", "write_status"}
        if set(case.get("expected", {})) != required:
            raise ValueError(f"incomplete expected result: {case['case_id']}")
        fact_ids = case["expected"]["fact_ids"]
        if not isinstance(fact_ids, list) or fact_ids != sorted(set(fact_ids)):
            raise ValueError(f"invalid expected fact_ids: {case['case_id']}")
    return cases, digest


def evaluate(dataset: Path = DATASET, checksum: Path = CHECKSUM) -> dict:
    cases, digest = load_cases(dataset, checksum)
    catalog = KnowledgeCatalog.from_directory(ROOT / "data/v1")
    store = MemorySessionStore()
    client = TestClient(app)
    results = []
    prior_feedback_store = getattr(app.state, "feedback_store", None)
    app.state.feedback_store = None
    try:
        with patch("api.get_session_context_store", return_value=store):
            for case in cases:
                path = "/api/v1/query/session" if case["endpoint"] == "session" else "/api/v1/query"
                payload = {"question": case["question"], "use_llm_plan": False}
                if case["endpoint"] == "session":
                    payload["session_id"] = case["session_id"]
                response = client.post(path, json=payload)
                errors = []
                if response.status_code != 200:
                    errors.append(f"http_status: expected 200, got {response.status_code}")
                else:
                    body = response.json()
                    explanation = body["explanation"]
                    claims = explanation["claims"]
                    fact_ids = [claim["fact_id"] for claim in claims]
                    actual = {
                        "conclusion_status": explanation["conclusion_status"],
                        "resolution_status": body["resolution"]["status"],
                        "fact_ids": sorted(fact_ids),
                    }
                    if case["endpoint"] == "session":
                        actual["context_applied"] = body["session_context"]["context_applied"]
                        actual["write_status"] = body["session_context"]["write_status"]
                    for key, expected in case["expected"].items():
                        if actual[key] != expected:
                            errors.append(f"{key}: expected {expected!r}, got {actual[key]!r}")
                    if body["trace"]["conclusion_status"] != actual["conclusion_status"]:
                        errors.append("trace conclusion_status differs from explanation")
                    if body["trace"]["resolution_status"] != actual["resolution_status"]:
                        errors.append("trace resolution_status differs from resolution")
                    if explanation["data_version"] != catalog.data_version:
                        errors.append("explanation data_version differs from catalog")
                    if len(fact_ids) != len(set(fact_ids)):
                        errors.append("duplicate fact_id")
                    if actual["conclusion_status"] != "risk_found" and claims:
                        errors.append("non-risk conclusion has claims")
                    for claim in claims:
                        fact = catalog.facts.get(claim["fact_id"])
                        if (
                            fact is None
                            or not set(fact.source_ids).issubset(claim["source_ids"])
                            or not set(claim["source_ids"]).issubset(catalog.sources)
                        ):
                            errors.append(f"invalid source provenance for {claim['fact_id']}")
                results.append({"case_id": case["case_id"], "passed": not errors, "errors": errors})
    finally:
        app.state.feedback_store = prior_feedback_store
    return {
        "suite": dataset.stem,
        "scope": "deterministic engineering regression; not independent clinical evaluation",
        "dataset_sha256": digest,
        "data_version": catalog.data_version,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "total": len(results),
        "passed": sum(item["passed"] for item in results),
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--checksum", type=Path, default=CHECKSUM)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(args.dataset, args.checksum)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
