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

    # Ollama 配置 deepseek-r1:1.5b / qwen2:7b
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b")
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    
    # Redis 配置（用于向量数据库）
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    # REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", 123456)
    REDIS_DB = int(os.getenv("REDIS_DB", 0))