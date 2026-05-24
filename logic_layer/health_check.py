from config import Config


def get_environment_diagnostics():
    """
    Return a non-blocking configuration diagnostic summary.

    This intentionally does not connect to Redis, Neo4j, or Ollama. It only
    reports whether the app has enough configuration to try those services.
    """
    services = {
        "neo4j": {
            "uri": Config.NEO4J_URI,
            "user": Config.NEO4J_USER,
            "password_configured": bool(Config.NEO4J_PASSWORD),
            "ready": bool(Config.NEO4J_URI and Config.NEO4J_USER and Config.NEO4J_PASSWORD),
        },
        "ollama": {
            "url": Config.OLLAMA_URL,
            "model": Config.OLLAMA_MODEL,
            "ready": bool(Config.OLLAMA_URL and Config.OLLAMA_MODEL),
        },
        "redis": {
            "host": Config.REDIS_HOST,
            "port": Config.REDIS_PORT,
            "db": Config.REDIS_DB,
            "ready": bool(Config.REDIS_HOST and Config.REDIS_PORT is not None),
        },
    }

    missing = []
    if not services["neo4j"]["password_configured"]:
        missing.append("NEO4J_PASSWORD")
    if not services["ollama"]["url"]:
        missing.append("OLLAMA_URL")
    if not services["ollama"]["model"]:
        missing.append("OLLAMA_MODEL")
    if not services["redis"]["host"]:
        missing.append("REDIS_HOST")

    return {
        "ready": not missing,
        "missing": missing,
        "services": services,
    }
