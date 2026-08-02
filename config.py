# config.py
import os
from dotenv import load_dotenv

# 自动加载 .env 文件（跨 Mac / Windows）
load_dotenv()

class Config:
    # Neo4j 配置
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
    NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
    NEO4J_CONNECTION_TIMEOUT_SECONDS = float(
        os.getenv("NEO4J_CONNECTION_TIMEOUT_SECONDS", "1.5")
    )

    # Ollama 配置：模型版本必须与评测报告或本地验收记录一致。
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct")
    OLLAMA_TOOL_MODEL = os.getenv("OLLAMA_TOOL_MODEL", "qwen3:4b-instruct")
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_EXPLANATION_TIMEOUT_SECONDS = float(
        os.getenv("OLLAMA_EXPLANATION_TIMEOUT_SECONDS", "5")
    )
    # Generation models are not assumed to support /api/embed. Keep this
    # independent until a dedicated embedding model is explicitly validated.
    OLLAMA_EMBEDDING_MODEL = os.getenv(
        "OLLAMA_EMBEDDING_MODEL",
        "deepseek-r1:1.5b",
    )
    OLLAMA_EMBEDDING_TIMEOUT_SECONDS = float(
        os.getenv("OLLAMA_EMBEDDING_TIMEOUT_SECONDS", "5")
    )
    
    # Redis 配置（用于向量数据库）
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    # REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", 123456)
    REDIS_DB = int(os.getenv("REDIS_DB", 0))
    REDIS_SOCKET_TIMEOUT_SECONDS = float(
        os.getenv("REDIS_SOCKET_TIMEOUT_SECONDS", "1.5")
    )
    SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "86400"))

    # 依赖健康探测必须快速返回，不能让 readiness 长时间阻塞。
    HEALTH_PROBE_TIMEOUT_SECONDS = float(
        os.getenv("HEALTH_PROBE_TIMEOUT_SECONDS", "1.5")
    )

    # Rerank 配置（历史对话检索）
    ENABLE_RERANK = os.getenv("ENABLE_RERANK", "true").lower() == "true"
    RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", 10))
    RERANK_TOP_K = int(os.getenv("RERANK_TOP_K", 3))
