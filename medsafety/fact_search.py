"""Deterministic retrieval baseline over reviewed fact summaries, not source PDFs."""

from __future__ import annotations

import re

from medsafety.catalog import KnowledgeCatalog


def _terms(value: str) -> set[str]:
    normalized = value.lower()
    chinese = re.findall(r"[\u4e00-\u9fff]+", normalized)
    latin = re.findall(r"[a-z0-9]+", normalized)
    terms = set(latin)
    for segment in chinese:
        terms.update(segment[index:index + 2] for index in range(len(segment) - 1))
    return terms


class ReviewedFactSearch:
    def __init__(self, catalog: KnowledgeCatalog):
        self.catalog = catalog
        self.index = {
            fact.fact_id: (
                _terms(" ".join((fact.subject, fact.object, fact.reason))),
                _terms(" ".join((fact.subject, fact.object))),
            )
            for fact in catalog.facts.values()
        }

    def search(self, query: str, limit: int = 5) -> dict:
        terms = _terms(query)
        ranked = []
        for fact in self.catalog.facts.values():
            all_terms, entity_terms = self.index[fact.fact_id]
            score = len(terms & all_terms) + 3 * len(terms & entity_terms)
            if fact.subject in query and fact.object in query:
                score += 10
            if score:
                ranked.append((score, fact.fact_id, fact))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        hits = []
        for score, _, fact in ranked[:limit]:
            hits.append({
                "fact_id": fact.fact_id,
                "summary": fact.reason,
                "source_locator": fact.source_locator,
                "sources": [
                    {
                        "source_id": source_id,
                        "title": self.catalog.sources[source_id].title,
                        "url": self.catalog.sources[source_id].url,
                    }
                    for source_id in fact.source_ids
                ],
                "score": score,
            })
        return {
            "schema_version": "reviewed-fact-search-v1",
            "data_version": self.catalog.data_version,
            "retrieval_method": "character-bigram-over-reviewed-summaries",
            "hits": hits,
        }
