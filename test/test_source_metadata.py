from types import SimpleNamespace

from api import build_v1_catalog, source_metadata_for_claims


def test_source_metadata_uses_only_claim_sources_and_deduplicates():
    catalog = build_v1_catalog()
    claims = [
        SimpleNamespace(source_ids=["source-fda-acetaminophen-2025"]),
        SimpleNamespace(source_ids=["source-fda-acetaminophen-2025"]),
    ]

    sources = source_metadata_for_claims(claims, catalog)

    assert len(sources) == 1
    assert sources[0]["source_id"] == "source-fda-acetaminophen-2025"
    assert sources[0]["title"] == catalog.sources[sources[0]["source_id"]].title
    assert sources[0]["url"].startswith("https://")
    assert source_metadata_for_claims([], catalog) == []
