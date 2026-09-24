import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api import DocumentSearchRequest, get_project_document, search_project_documents
from medsafety.document_search import DocumentCorpusError, ProjectDocumentSearch


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/document_corpus_v1.json"


def test_document_index_rebuilds_deterministically_and_retrieves_source_text():
    first = ProjectDocumentSearch(ROOT, MANIFEST)
    second = ProjectDocumentSearch(ROOT, MANIFEST)
    assert [item["chunk_id"] for item in first.chunks] == [item["chunk_id"] for item in second.chunks]

    for method in ("lexical", "hashing_vector"):
        result = first.search("知识不可用时拒绝风险判断", method=method, limit=3)
        assert result["corpus"] == "project_documentation"
        assert result["hits"]
        assert all(hit["text"] for hit in result["hits"])
        assert all(hit["document_id"] in first.documents for hit in result["hits"])


def test_document_index_rejects_changed_checksum_and_path_escape(tmp_path):
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries[0]["sha256"] = "0" * 64
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(DocumentCorpusError, match="checksum"):
        ProjectDocumentSearch(ROOT, manifest)

    entries[0]["path"] = "../outside.md"
    manifest.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(DocumentCorpusError, match="path"):
        ProjectDocumentSearch(ROOT, manifest)


def test_document_search_api_rejects_unknown_method_and_uses_index():
    with pytest.raises(ValidationError):
        DocumentSearchRequest(query="安全边界", method="semantic")

    index = ProjectDocumentSearch(ROOT, MANIFEST)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(document_search=index)))
    result = asyncio.run(search_project_documents(DocumentSearchRequest(query="安全边界"), request))
    assert result["hits"]
    assert result["method"] == "lexical"

    source = asyncio.run(get_project_document("project-safety-boundary", request))
    assert "不是医疗器械" in source.body.decode("utf-8")
    missing = asyncio.run(get_project_document("project-missing", request))
    assert missing.status_code == 404
