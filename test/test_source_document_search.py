import asyncio
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from api import (
    DocumentSearchRequest,
    build_reviewed_source_search,
    get_reviewed_source_document,
    search_reviewed_source_documents,
)
from scripts.extract_fda_safe_use import extract_section
from medsafety.document_search import DocumentCorpusError, ProjectDocumentSearch


ROOT = Path(__file__).resolve().parents[1]


def test_fda_extractor_accepts_only_the_target_section():
    html = '''<article id="main-content"><h2>Safe Use of Acetaminophen</h2>
    <p>Read the label.</p><ul><li>Avoid duplicate products.</li></ul>
    <h2>Other medical topic</h2><p>Do not include.</p></article>'''
    result = extract_section(html)
    assert "Read the label." in result
    assert "Avoid duplicate products." in result
    assert "Do not include." not in result


def test_reviewed_source_search_links_only_catalog_fact_and_source():
    index = build_reviewed_source_search()
    result = index.search("acetaminophen containing products", limit=2)
    assert result["corpus"] == "reviewed_source_excerpt"
    assert result["hits"]
    assert result["hits"][0]["source_id"] == "source-fda-acetaminophen-2025"
    assert result["hits"][0]["linked_fact_ids"] == ["fact-duplicate-acetaminophen-001"]
    assert result["hits"][0]["source_url"].startswith("https://www.fda.gov/")

    unrelated = index.search("follow dosing directions on the label", limit=1)["hits"][0]
    assert unrelated["chunk_id"].endswith(":002")
    assert unrelated["linked_fact_ids"] == []
    assert index.search("1-800-222-1222", limit=1)["hits"][0]["linked_fact_ids"] == []

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(source_document_search=index)))
    api_result = asyncio.run(search_reviewed_source_documents(DocumentSearchRequest(query="对乙酰氨基酚重复成分"), request))
    assert api_result["hits"]
    source = asyncio.run(get_reviewed_source_document(index.chunks[0]["document_id"], request))
    assert source.status_code == 200


def test_source_corpus_rejects_anchor_fact_outside_document_declaration(tmp_path):
    text = b"# Heading\n\nEvidence anchor.\n"
    (tmp_path / "source.txt").write_bytes(text)
    manifest = [{
        "document_id": "source-test",
        "title": "Test source",
        "path": "source.txt",
        "sha256": sha256(text).hexdigest(),
        "corpus": "reviewed_source_excerpt",
        "linked_fact_ids": ["fact-declared"],
        "keyword_anchors": [{
            "contains": "Evidence anchor.",
            "keywords": "anchor",
            "linked_fact_ids": ["fact-undeclared"],
        }],
    }]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(DocumentCorpusError, match="anchor fact link"):
        ProjectDocumentSearch(tmp_path, path, corpus="reviewed_source_excerpt")
