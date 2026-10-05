"""Rebuildable search over an allowlisted, checksum-pinned project document corpus."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

from logic_layer.embedding_service import EmbeddingService
from medsafety.fact_search import _terms


class DocumentCorpusError(ValueError):
    pass


def _normalize_search_text(value: str) -> str:
    """Index 4,000 and 4000 alike without changing the displayed source text."""
    return re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", value)


def _chunks(text: str, max_chars: int = 700) -> list[tuple[str, str]]:
    heading = "文档开头"
    chunks = []
    buffer = []

    def flush():
        if buffer:
            chunks.append((heading, "\n".join(buffer).strip()))
            buffer.clear()

    for line in text.splitlines():
        if line.startswith("#"):
            flush()
            heading = line.lstrip("# ").strip() or heading
            continue
        if not line.strip():
            continue
        if sum(len(item) for item in buffer) + len(line) > max_chars:
            flush()
        if len(line) <= max_chars:
            buffer.append(line)
        else:
            for offset in range(0, len(line), max_chars):
                if buffer:
                    flush()
                chunks.append((heading, line[offset:offset + max_chars]))
    flush()
    return chunks


class ProjectDocumentSearch:
    def __init__(self, root: Path, manifest_path: Path, *, corpus: str = "project_documentation"):
        self.root = root.resolve()
        self.corpus = corpus
        self.vectorizer = EmbeddingService()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.documents = {}
        self.document_texts = {}
        self.chunks = []
        for entry in manifest:
            identifier = entry["document_id"]
            if identifier in self.documents or entry["corpus"] != corpus:
                raise DocumentCorpusError("duplicate or unsupported document entry")
            path = (self.root / entry["path"]).resolve()
            if not path.is_relative_to(self.root) or path.suffix not in {".md", ".txt"}:
                raise DocumentCorpusError("document path must stay within the project")
            content = path.read_bytes()
            if sha256(content).hexdigest() != entry["sha256"]:
                raise DocumentCorpusError(f"document checksum changed: {identifier}")
            text = content.decode("utf-8")
            self.documents[identifier] = entry
            self.document_texts[identifier] = text
            anchors = entry.get("keyword_anchors", [])
            if any(
                not set(anchor.get("linked_fact_ids", [])).issubset(entry.get("linked_fact_ids", []))
                for anchor in anchors
            ):
                raise DocumentCorpusError(f"anchor fact link is not declared by document: {identifier}")
            section_chunks = _chunks(text)
            if any(
                not any(anchor["contains"] in passage for _, passage in section_chunks)
                for anchor in anchors
            ):
                raise DocumentCorpusError(f"keyword anchor missing: {identifier}")
            for number, (heading, passage) in enumerate(section_chunks, start=1):
                keywords = " ".join(
                    anchor["keywords"] for anchor in anchors
                    if anchor["contains"] in passage
                )
                chunk_fact_ids = list(dict.fromkeys(
                    fact_id
                    for anchor in anchors if anchor["contains"] in passage
                    for fact_id in anchor.get("linked_fact_ids", [])
                ))
                searchable = f"{entry['title']} {heading} {keywords} {passage}"
                normalized_searchable = _normalize_search_text(searchable)
                self.chunks.append({
                    "chunk_id": f"{identifier}:{number:03d}",
                    "document_id": identifier,
                    "title": entry["title"],
                    "heading": heading,
                    "text": passage,
                    "source_id": entry.get("source_id"),
                    "source_url": entry.get("source_url"),
                    "linked_fact_ids": chunk_fact_ids,
                    "terms": _terms(normalized_searchable),
                    "vector": self.vectorizer.embed_text(normalized_searchable),
                })

    def search(self, query: str, *, method: str = "lexical", limit: int = 5) -> dict:
        normalized_query = _normalize_search_text(query)
        terms = _terms(normalized_query)
        query_vector = self.vectorizer.embed_text(normalized_query) if method == "hashing_vector" else []
        ranked = []
        for chunk in self.chunks:
            matched_terms = terms & chunk["terms"]
            if not matched_terms:
                continue
            score = sum(
                2 if term.isdigit() and len(term) >= 3 else 1
                for term in matched_terms
            ) if method == "lexical" else sum(
                left * right for left, right in zip(query_vector, chunk["vector"])
            )
            ranked.append((score, chunk["chunk_id"], chunk))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return {
            "schema_version": "project-document-search-v1",
            "corpus": self.corpus,
            "method": method,
            "vectorizer_id": self.vectorizer.vectorizer_id if method == "hashing_vector" else None,
            "hits": [
                {key: chunk[key] for key in ("chunk_id", "document_id", "title", "heading", "text", "source_id", "source_url", "linked_fact_ids")}
                | {"score": round(score, 4)}
                for score, _, chunk in ranked[:limit]
            ],
        }
