"""Fast, bounded liveness and dependency readiness diagnostics."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from typing import Callable

from neo4j import GraphDatabase
import redis
import requests

from config import Config
from medsafety.catalog import KnowledgeCatalog


V1_DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data/v1"


class DependencyNotConfigured(RuntimeError):
    pass


def get_liveness_diagnostics() -> dict:
    """Liveness means the API process can execute Python code."""

    return {"status": "alive"}


def _catalog_probe() -> dict:
    catalog = KnowledgeCatalog.from_directory(V1_DATA_DIRECTORY)
    return {
        "data_version": catalog.data_version,
        "sources": len(catalog.sources),
        "medications": len(catalog.medications),
        "contexts": len(catalog.contexts),
        "facts": len(catalog.facts),
    }


def _redis_probe() -> dict:
    client = redis.Redis(
        host=Config.REDIS_HOST,
        port=Config.REDIS_PORT,
        password=getattr(Config, "REDIS_PASSWORD", None),
        db=Config.REDIS_DB,
        socket_connect_timeout=Config.HEALTH_PROBE_TIMEOUT_SECONDS,
        socket_timeout=Config.HEALTH_PROBE_TIMEOUT_SECONDS,
        decode_responses=True,
    )
    try:
        client.ping()
    finally:
        client.close()
    return {
        "role": "optional_session_memory",
        "vectorizer": Config.SESSION_VECTORIZER_ID,
        "vector_dimensions": Config.SESSION_VECTOR_DIMENSIONS,
    }


def _neo4j_probe() -> dict:
    if not Config.NEO4J_PASSWORD:
        raise DependencyNotConfigured("Neo4j credentials are not configured")
    driver = GraphDatabase.driver(
        Config.NEO4J_URI,
        auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD),
        connection_timeout=Config.HEALTH_PROBE_TIMEOUT_SECONDS,
        connection_acquisition_timeout=Config.HEALTH_PROBE_TIMEOUT_SECONDS,
    )
    try:
        driver.verify_connectivity()
    finally:
        driver.close()
    return {"role": "optional_graph_projection"}


def _ollama_probe() -> dict:
    response = requests.get(
        f"{Config.OLLAMA_URL.rstrip('/')}/api/tags",
        timeout=Config.HEALTH_PROBE_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    models = {
        item.get("model") or item.get("name")
        for item in payload.get("models", [])
        if isinstance(item, dict)
    }
    required_models = {
        Config.OLLAMA_MODEL,
        Config.OLLAMA_TOOL_MODEL,
    }
    if not required_models.issubset(models):
        raise LookupError("A configured Ollama model is not installed")
    return {
        "role": "optional_generation_and_tools",
        "model": Config.OLLAMA_MODEL,
        "tool_model": Config.OLLAMA_TOOL_MODEL,
    }


def _error_category(exc: Exception) -> str:
    if isinstance(exc, DependencyNotConfigured):
        return "not_configured"
    if isinstance(exc, (TimeoutError, requests.Timeout, redis.exceptions.TimeoutError)):
        return "timeout"
    if isinstance(exc, LookupError):
        return "model_unavailable"
    return "connection_failed"


def _run_probe(name: str, required: bool, probe: Callable[[], dict]) -> tuple[str, dict]:
    started = perf_counter()
    try:
        metadata = probe()
    except Exception as exc:
        return name, {
            "required": required,
            "ready": False,
            "status": _error_category(exc),
            "latency_ms": round((perf_counter() - started) * 1000, 3),
        }
    return name, {
        "required": required,
        "ready": True,
        "status": "ready",
        "latency_ms": round((perf_counter() - started) * 1000, 3),
        **metadata,
    }


def get_readiness_diagnostics(
    probe_overrides: dict[str, Callable[[], dict]] | None = None,
) -> dict:
    """Probe required and optional dependencies concurrently.

    The versioned JSON catalog is the only required dependency for the formal
    V1 safety flow. Redis, Neo4j, and Ollama are optional capabilities and may
    degrade independently without turning a deterministic V1 response into a
    false outage.
    """

    overrides = probe_overrides or {}
    definitions = {
        "catalog": (True, overrides.get("catalog", _catalog_probe)),
        "redis": (False, overrides.get("redis", _redis_probe)),
        "neo4j": (False, overrides.get("neo4j", _neo4j_probe)),
        "ollama": (False, overrides.get("ollama", _ollama_probe)),
    }
    with ThreadPoolExecutor(max_workers=len(definitions)) as executor:
        futures = [
            executor.submit(_run_probe, name, required, probe)
            for name, (required, probe) in definitions.items()
        ]
        services = dict(future.result() for future in futures)

    required_ready = all(
        service["ready"] for service in services.values() if service["required"]
    )
    all_dependencies_ready = all(service["ready"] for service in services.values())
    return {
        "status": (
            "ready"
            if required_ready and all_dependencies_ready
            else "degraded"
            if required_ready
            else "not_ready"
        ),
        "ready": required_ready,
        "all_dependencies_ready": all_dependencies_ready,
        "services": services,
    }


def get_environment_diagnostics() -> dict:
    """Compatibility wrapper now backed by real, bounded readiness probes."""

    return get_readiness_diagnostics()
