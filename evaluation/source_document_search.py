"""Development-set audit of the first external source excerpt."""

from __future__ import annotations

import json
from pathlib import Path

from api import build_reviewed_source_search


ROOT = Path(__file__).resolve().parents[1]


def evaluate() -> dict:
    index = build_reviewed_source_search()
    records = [json.loads(line) for line in (ROOT / "eval/source_document_search_dev_v1.jsonl").read_text(encoding="utf-8").splitlines() if line]
    cases = []
    for record in records:
        hits = index.search(record["query"], method="lexical", limit=1)["hits"]
        actual = hits[0]["chunk_id"] if hits else None
        cases.append({"query": record["query"], "expected": record["expected_chunk_id"], "actual": actual, "match": actual == record["expected_chunk_id"]})
    return {"dataset": "source_document_search_dev_v1", "source_documents": len(index.documents), "chunks": len(index.chunks), "top1_matches": sum(case["match"] for case in cases), "total": len(cases), "cases": cases}


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
