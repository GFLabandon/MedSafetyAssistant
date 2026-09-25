"""Development audit for source-excerpt retrieval and chunk-level fact links."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient

from api import app, build_reviewed_source_search
from medsafety.catalog import KnowledgeCatalog


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "eval/source_retrieval_dev_v2.jsonl"
CHECKSUM = ROOT / "eval/source_retrieval_dev_v2.sha256"
MANIFEST = ROOT / "data/source_document_corpus_v1.json"
METHODS = ("lexical", "hashing_vector")


def load_cases(dataset: Path = DATASET, checksum: Path = CHECKSUM) -> tuple[list[dict], str]:
    raw = dataset.read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != checksum.read_text(encoding="ascii").strip().split()[0]:
        raise ValueError("source retrieval dataset checksum mismatch")
    cases = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if not cases or len({case["case_id"] for case in cases}) != len(cases):
        raise ValueError("empty or duplicate source retrieval cases")
    expected_keys = {"case_id", "query", "expected_chunk_id", "expected_linked_fact_ids"}
    for case in cases:
        if set(case) != expected_keys or not case["query"].strip():
            raise ValueError(f"invalid source retrieval case: {case.get('case_id')}")
        links = case["expected_linked_fact_ids"]
        if not isinstance(links, list) or links != sorted(set(links)):
            raise ValueError(f"invalid expected fact links: {case['case_id']}")
        if case["expected_chunk_id"] is None and links:
            raise ValueError(f"negative case cannot expect fact links: {case['case_id']}")
    return cases, digest


def evaluate(dataset: Path = DATASET, checksum: Path = CHECKSUM) -> dict:
    cases, dataset_digest = load_cases(dataset, checksum)
    catalog = KnowledgeCatalog.from_directory(ROOT / "data/v1")
    index = build_reviewed_source_search(catalog)
    chunks = {chunk["chunk_id"]: chunk for chunk in index.chunks}
    for case in cases:
        expected = case["expected_chunk_id"]
        if expected is not None and expected not in chunks:
            raise ValueError(f"unknown expected chunk: {case['case_id']}")

    client = TestClient(app)
    results = []
    for case in cases:
        for method in METHODS:
            response = client.post(
                "/api/v1/source-documents/search",
                json={"query": case["query"], "method": method, "limit": 1},
            )
            errors = []
            hit = None
            if response.status_code != 200:
                errors.append(f"HTTP {response.status_code}")
            else:
                body = response.json()
                if body["corpus"] != "reviewed_source_excerpt" or body["method"] != method:
                    errors.append("response corpus or method mismatch")
                hit = body["hits"][0] if body["hits"] else None
                if hit is not None:
                    source = catalog.sources.get(hit["source_id"])
                    if source is None or hit["source_url"].split("#", 1)[0] != source.url:
                        errors.append("invalid source provenance")
                    for fact_id in hit["linked_fact_ids"]:
                        fact = catalog.facts.get(fact_id)
                        if fact is None or hit["source_id"] not in fact.source_ids:
                            errors.append(f"invalid fact-source link: {fact_id}")
                    if hit["linked_fact_ids"] != chunks[hit["chunk_id"]]["linked_fact_ids"]:
                        errors.append("API chunk links differ from indexed chunk")
            actual_chunk = hit["chunk_id"] if hit else None
            actual_links = hit["linked_fact_ids"] if hit else []
            results.append({
                "case_id": case["case_id"],
                "method": method,
                "expected_chunk_id": case["expected_chunk_id"],
                "actual_chunk_id": actual_chunk,
                "top1_match": actual_chunk == case["expected_chunk_id"],
                "expected_linked_fact_ids": case["expected_linked_fact_ids"],
                "actual_linked_fact_ids": actual_links,
                "link_match": actual_links == case["expected_linked_fact_ids"],
                "provenance_errors": errors,
            })
    return {
        "dataset": dataset.stem,
        "scope": "single-source development audit; not clinical or general retrieval accuracy",
        "dataset_sha256": dataset_digest,
        "manifest_sha256": sha256(MANIFEST.read_bytes()).hexdigest(),
        "data_version": catalog.data_version,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_documents": len(index.documents),
        "chunks": len(index.chunks),
        "queries": len(cases),
        "runs": len(results),
        "top1_matches": sum(item["top1_match"] for item in results),
        "link_matches": sum(item["link_match"] for item in results),
        "provenance_failures": sum(bool(item["provenance_errors"]) for item in results),
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate()
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["provenance_failures"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
