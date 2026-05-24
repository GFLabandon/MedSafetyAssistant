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

    # Ollama 配置：默认 deepseek（开箱即用）；推荐 qwen2.5-coder:14b（效果更好）
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:1.5b")
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    
    # Redis 配置（用于向量数据库）
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    # REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", 123456)
    REDIS_DB = int(os.getenv("REDIS_DB", 0))

    # Rerank 配置（历史对话检索）
    ENABLE_RERANK = os.getenv("ENABLE_RERANK", "true").lower() == "true"
    RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", 10))
    RERANK_TOP_K = int(os.getenv("RERANK_TOP_K", 3))
