# logic_layer/embedding_service.py
"""
向量化服务模块
使用 Ollama 当前 ``/api/embed`` 契约进行文本向量化
"""
import requests
from typing import List
from config import Config


class EmbeddingService:
    """使用 Ollama 进行文本向量化"""
    
    def __init__(self):
        self.embedding_model = Config.OLLAMA_EMBEDDING_MODEL
        self.ollama_url = Config.OLLAMA_URL.rstrip('/')
        self.embedding_endpoint = f"{self.ollama_url}/api/embed"
    
    def embed_text(self, text: str) -> List[float]:
        """
        对单个文本进行向量化
        
        Args:
            text: 要向量化的文本
            
        Returns:
            向量列表
        """
        try:
            # 输出向量化操作信息（仅在调试模式下）
            import os
            debug_mode = os.getenv("DEBUG_EMBEDDING", "false").lower() == "true"
            
            if debug_mode:
                print(f"      🔄 [向量化] 调用 Ollama API: {self.embedding_model}")
                print(f"         文本长度: {len(text)} 字符")
            
            response = requests.post(
                self.embedding_endpoint,
                json={
                    "model": self.embedding_model,
                    "input": text,
                },
                timeout=Config.OLLAMA_EMBEDDING_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            result = response.json()
            embeddings = result.get("embeddings", [])
            embedding = embeddings[0] if embeddings else []
            
            if debug_mode:
                print(f"      ✅ [向量化] 完成 (维度: {len(embedding)})")
            
            return embedding
        except Exception as exc:
            print(f"      ❌ [向量化] 失败: {type(exc).__name__}")
            return []
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量向量化文本
        
        Args:
            texts: 要向量化的文本列表
            
        Returns:
            向量列表的列表
        """
        if not texts:
            return []
        try:
            response = requests.post(
                self.embedding_endpoint,
                json={
                    "model": self.embedding_model,
                    "input": texts,
                },
                timeout=Config.OLLAMA_EMBEDDING_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            result = response.json()
            embeddings = result.get("embeddings", [])
            if len(embeddings) != len(texts):
                return [[] for _ in texts]
            return embeddings
        except Exception as exc:
            print(f"      ❌ [批量向量化] 失败: {type(exc).__name__}")
            return [[] for _ in texts]

