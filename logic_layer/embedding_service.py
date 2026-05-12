# logic_layer/embedding_service.py
"""
向量化服务模块
使用 Ollama 的 mxbai-embed-large:latest 模型进行文本向量化
"""
import requests
from typing import List
from config import Config


class EmbeddingService:
    """使用 Ollama 进行文本向量化"""
    
    def __init__(self):
        self.embedding_model = "mxbai-embed-large:latest"
        self.ollama_url = Config.OLLAMA_URL.rstrip('/')
        self.embedding_endpoint = f"{self.ollama_url}/api/embeddings"
    
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
                    "prompt": text
                },
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            embedding = result.get("embedding", [])
            
            if debug_mode:
                print(f"      ✅ [向量化] 完成 (维度: {len(embedding)})")
            
            return embedding
        except Exception as e:
            print(f"      ❌ [向量化] 失败: {e}")
            return []
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量向量化文本
        
        Args:
            texts: 要向量化的文本列表
            
        Returns:
            向量列表的列表
        """
        embeddings = []
        for text in texts:
            embedding = self.embed_text(text)
            if embedding:
                embeddings.append(embedding)
            else:
                # 如果向量化失败，返回空向量
                embeddings.append([])
        return embeddings

