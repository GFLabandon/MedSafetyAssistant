from unittest.mock import Mock, patch

from logic_layer.embedding_service import EmbeddingService


def test_embed_text_uses_current_ollama_embed_contract():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
    service = EmbeddingService()

    with patch("logic_layer.embedding_service.requests.post", return_value=response) as post:
        embedding = service.embed_text("测试文本")

    assert embedding == [0.1, 0.2, 0.3]
    assert post.call_args.args[0].endswith("/api/embed")
    assert post.call_args.kwargs["json"] == {
        "model": service.embedding_model,
        "input": "测试文本",
    }


def test_embed_batch_uses_one_request_and_preserves_input_order():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"embeddings": [[1.0, 0.0], [0.0, 1.0]]}
    service = EmbeddingService()

    with patch("logic_layer.embedding_service.requests.post", return_value=response) as post:
        embeddings = service.embed_batch(["第一条", "第二条"])

    assert embeddings == [[1.0, 0.0], [0.0, 1.0]]
    assert post.call_count == 1
    assert post.call_args.kwargs["json"]["input"] == ["第一条", "第二条"]


def test_embed_batch_returns_shape_safe_empty_vectors_on_bad_response():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"embeddings": [[1.0]]}
    service = EmbeddingService()

    with patch("logic_layer.embedding_service.requests.post", return_value=response):
        embeddings = service.embed_batch(["第一条", "第二条"])

    assert embeddings == [[], []]
