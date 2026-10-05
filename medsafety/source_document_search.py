"""Conservative medication-topic gate for reviewed source excerpts."""

from __future__ import annotations

from medsafety.catalog import KnowledgeCatalog
from medsafety.contracts import ResolvedEntityKind
from medsafety.document_search import DocumentCorpusError, ProjectDocumentSearch
from medsafety.entity_resolution import V1EntityResolver


class ReviewedSourceDocumentSearch:
    def __init__(self, index: ProjectDocumentSearch, catalog: KnowledgeCatalog):
        self.index = index
        self.documents = index.documents
        self.document_texts = index.document_texts
        self.chunks = index.chunks
        self._resolver = V1EntityResolver(catalog)
        for document_id, entry in self.documents.items():
            topics = entry.get("topic_medication_ids", [])
            if not topics or any(topic not in catalog.medications for topic in topics):
                raise DocumentCorpusError(f"invalid source medication topics: {document_id}")

    def search(self, query: str, *, method: str = "lexical", limit: int = 5) -> dict:
        explicit_ids = {
            entity.record_id
            for entity in self._resolver.resolve(query).entities
            if entity.kind == ResolvedEntityKind.MEDICATION
        }
        result = self.index.search(query, method=method, limit=len(self.chunks))
        if explicit_ids:
            result["hits"] = [
                hit for hit in result["hits"]
                if explicit_ids.issubset(
                    self.documents[hit["document_id"]]["topic_medication_ids"]
                )
            ]
        result["hits"] = result["hits"][:limit]
        return result
