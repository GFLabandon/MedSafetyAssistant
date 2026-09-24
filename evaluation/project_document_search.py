"""Compare two local retrieval methods on a tiny development set."""

from __future__ import annotations

import json
from pathlib import Path

from medsafety.document_search import ProjectDocumentSearch


ROOT = Path(__file__).resolve().parents[1]


def evaluate() -> dict:
    index = ProjectDocumentSearch(ROOT, ROOT / "data/document_corpus_v1.json")
    records = [json.loads(line) for line in (ROOT / "eval/project_document_search_dev_v1.jsonl").read_text(encoding="utf-8").splitlines() if line]
    result = {"dataset": "project_document_search_dev_v1", "documents": len(index.documents), "chunks": len(index.chunks), "methods": {}}
    for method in ("lexical", "hashing_vector"):
        cases = []
        for record in records:
            hits = index.search(record["query"], method=method, limit=1)["hits"]
            actual = hits[0]["document_id"] if hits else None
            cases.append({"query": record["query"], "expected": record["expected_document_id"], "actual": actual, "match": actual == record["expected_document_id"]})
        result["methods"][method] = {"top1_document_matches": sum(case["match"] for case in cases), "total": len(cases), "cases": cases}
    return result


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
