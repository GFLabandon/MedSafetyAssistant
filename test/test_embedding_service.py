from math import isclose, sqrt

from logic_layer.embedding_service import EmbeddingService


def _cosine(left, right):
    return sum(a * b for a, b in zip(left, right))


def test_local_vector_is_deterministic_normalized_and_versioned():
    service = EmbeddingService()

    first = service.embed_text("泰诺和感康能一起吃吗？")
    second = service.embed_text("泰诺和感康能一起吃吗？")

    assert first == second
    assert len(first) == service.dimensions == 512
    assert service.vectorizer_id == "local-char-ngram-hashing-v1"
    assert isclose(sqrt(sum(value * value for value in first)), 1.0)


def test_nfkc_case_and_whitespace_normalization_are_stable():
    service = EmbeddingService()

    assert service.embed_text("  ＴＹＬＥＮＯＬ   500MG ") == service.embed_text(
        "tylenol 500mg"
    )


def test_lexically_related_medication_history_outranks_unrelated_text():
    service = EmbeddingService()
    query = service.embed_text("泰诺和感康能一起吃吗")
    related = service.embed_text("之前问过泰诺和感康一起服用")
    unrelated = service.embed_text("今天北京天气怎么样")

    assert _cosine(query, related) > _cosine(query, unrelated)


def test_empty_and_batch_inputs_are_shape_safe_and_ordered():
    service = EmbeddingService()

    assert service.embed_text("   ") == []
    assert service.embed_text(None) == []
    assert service.embed_batch([]) == []
    assert service.embed_batch(["泰诺", "感康"]) == [
        service.embed_text("泰诺"),
        service.embed_text("感康"),
    ]


def test_langchain_demo_reuses_local_vectorizer_and_configured_model():
    from examples.langchain_rag_demo import LocalHashingEmbeddings

    adapter = LocalHashingEmbeddings()

    assert adapter.embed_query("泰诺") == EmbeddingService().embed_text("泰诺")
    assert len(adapter.embed_documents(["泰诺", "感康"])) == 2
