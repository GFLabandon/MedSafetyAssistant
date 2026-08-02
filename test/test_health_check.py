from unittest.mock import Mock, patch

from config import Config
from logic_layer.health_check import _ollama_probe, _redis_probe


def test_ollama_readiness_requires_only_the_single_configured_model():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "models": [{"model": "qwen3:4b-instruct"}],
    }

    with (
        patch.object(Config, "OLLAMA_MODEL", "qwen3:4b-instruct"),
        patch.object(Config, "OLLAMA_TOOL_MODEL", "qwen3:4b-instruct"),
        patch("logic_layer.health_check.requests.get", return_value=response),
    ):
        metadata = _ollama_probe()

    assert metadata == {
        "role": "optional_generation_and_tools",
        "model": "qwen3:4b-instruct",
        "tool_model": "qwen3:4b-instruct",
    }


def test_redis_readiness_exposes_local_vectorizer_metadata():
    client = Mock()
    client.ping.return_value = True

    with patch("logic_layer.health_check.redis.Redis", return_value=client):
        metadata = _redis_probe()

    assert metadata == {
        "role": "optional_session_memory",
        "vectorizer": "local-char-ngram-hashing-v1",
        "vector_dimensions": 512,
    }
    client.close.assert_called_once_with()
