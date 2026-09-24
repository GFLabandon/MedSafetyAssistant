"""Small development-set audit for the reviewed-fact retrieval baseline."""

from __future__ import annotations

import json
from pathlib import Path

from medsafety.catalog import KnowledgeCatalog
from medsafety.fact_search import ReviewedFactSearch


ROOT = Path(__file__).resolve().parents[1]


def evaluate() -> dict:
    index = ReviewedFactSearch(KnowledgeCatalog.from_directory(ROOT / "data/v1"))
    records = [json.loads(line) for line in (ROOT / "eval/reviewed_fact_search_dev_v1.jsonl").read_text(encoding="utf-8").splitlines() if line]
    results = []
    for record in records:
        hits = index.search(record["query"], limit=1)["hits"]
        actual = hits[0]["fact_id"] if hits else None
        results.append({"query": record["query"], "expected": record["expected_fact_id"], "actual": actual, "match": actual == record["expected_fact_id"]})
    return {"dataset": "reviewed_fact_search_dev_v1", "data_version": index.catalog.data_version, "top1_matches": sum(item["match"] for item in results), "total": len(results), "cases": results}


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
