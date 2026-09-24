import asyncio
from types import SimpleNamespace

from api import FactSearchRequest, build_v1_catalog, search_reviewed_facts
from medsafety.fact_search import ReviewedFactSearch
from pydantic import ValidationError


def test_reviewed_fact_search_returns_versioned_citations():
    index = ReviewedFactSearch(build_v1_catalog())

    result = index.search("布洛芬和阿司匹林")

    assert result["data_version"] == "v1.0.0-alpha.4"
    assert result["hits"][0]["fact_id"] == "fact-interaction-ibuprofen-aspirin-cardioprotection-001"
    assert result["hits"][0]["source_locator"]
    assert result["hits"][0]["sources"][0]["url"].startswith("https://")


def test_reviewed_fact_search_has_no_unsupported_fallback():
    index = ReviewedFactSearch(build_v1_catalog())

    assert index.search("xyzunknown123")["hits"] == []
    assert len(index.search("布洛芬和阿司匹林", limit=1)["hits"]) == 1


def test_search_request_rejects_blank_and_unbounded_input():
    for query in ("  ", "x" * 301):
        try:
            FactSearchRequest(query=query)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"invalid query accepted: {query[:10]}")


def test_search_endpoint_uses_prebuilt_catalog_index():
    index = ReviewedFactSearch(build_v1_catalog())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(fact_search=index)))

    result = asyncio.run(search_reviewed_facts(FactSearchRequest(query="布洛芬和阿司匹林"), request))

    assert result["hits"][0]["fact_id"] == "fact-interaction-ibuprofen-aspirin-cardioprotection-001"
