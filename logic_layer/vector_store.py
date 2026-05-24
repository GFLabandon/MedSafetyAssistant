# logic_layer/vector_store.py
"""
Redis 向量数据库服务模块
用于存储和查询历史对话记录
"""
import json
import redis
from typing import List, Dict, Optional
import ollama
from config import Config
from logic_layer.embedding_service import EmbeddingService
from logic_layer.json_utils import parse_llm_json


class VectorStore:
    """Redis 向量数据库管理"""
    
    def __init__(self):
        try:
            # 连接 Redis
            print("=" * 60)
            print("🔌 [Redis] 正在初始化 Redis 向量数据库连接...")
            redis_host = getattr(Config, 'REDIS_HOST', 'localhost')
            redis_port = int(getattr(Config, 'REDIS_PORT', 6379))
            redis_password = getattr(Config, 'REDIS_PASSWORD', None)
            redis_db = int(getattr(Config, 'REDIS_DB', 0))
            
            print(f"   📍 主机: {redis_host}")
            print(f"   🔌 端口: {redis_port}")
            print(f"   💾 数据库: {redis_db}")
            
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                db=redis_db,
                decode_responses=True
            )
            # 测试连接
            print("   🔍 测试连接...")
            self.redis_client.ping()
            print("   ✅ Redis 连接成功！")
            
            # 初始化向量化服务
            print("   🤖 初始化向量化服务...")
            self.embedding_service = EmbeddingService()
            print("   ✅ 向量化服务初始化完成")
            self.ollama_client = ollama.Client(host=Config.OLLAMA_URL)
            
            # 向量索引名称
            self.index_name = "conversation_vectors"
            
            # 检查是否已创建向量索引
            self._ensure_index()
            print("=" * 60)
            
        except Exception as e:
            print(f"⚠️ [Redis] 连接失败: {e}")
            self.redis_client = None
            self.embedding_service = None
            self.ollama_client = None
    
    def _ensure_index(self):
        """确保 Redis 向量索引存在"""
        if not self.redis_client:
            return
        
        # 默认使用备用方案（手动计算相似度），因为需要 Redis Stack 才能使用向量索引
        # 备用方案更通用，适用于所有 Redis 版本
        self.use_fallback = True
        
        # 可选：如果使用 Redis Stack，可以尝试创建向量索引
        # 这里注释掉，因为大多数用户可能使用标准 Redis
        # try:
        #     indices = self.redis_client.execute_command("FT._LIST")
        #     index_bytes = self.index_name.encode() if isinstance(indices[0], bytes) else self.index_name
        #     if index_bytes not in indices:
        #         # 创建向量索引需要 Redis Stack
        #         self.redis_client.execute_command(
        #             "FT.CREATE", self.index_name,
        #             "ON", "HASH",
        #             "PREFIX", "1", f"conv:",
        #             "SCHEMA",
        #             "text", "TEXT",
        #             "role", "TEXT",
        #             "vector", "VECTOR", "FLAT", "6",
        #             "TYPE", "FLOAT32",
        #             "DIM", "1024",  # mxbai-embed-large 的维度通常是 1024
        #             "DISTANCE_METRIC", "COSINE"
        #         )
        #         self.use_fallback = False
        #     else:
        #         self.use_fallback = False
        # except Exception as e:
        #     print(f"⚠️ 使用备用存储方案（手动计算相似度）: {e}")
        #     self.use_fallback = True
    
    def _calculate_cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算两个向量的余弦相似度"""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)

    def _rerank_with_llm(self, query: str, candidates: List[Dict], top_k: int) -> List[Dict]:
        """
        用 LLM 对候选对话进行轻量重排。
        失败时抛异常，由上层自动回退到余弦排序。

        说明：当前 Rerank 结论主要来自定性验证，尚未做系统化离线评测
        （例如 nDCG / Recall@K 或固定标注集 A/B 实验）。
        因此工程上保留“Rerank 失败即回退余弦排序”的稳定性策略。
        """
        if not candidates:
            return []

        numbered = []
        for i, c in enumerate(candidates, 1):
            numbered.append(
                f"{i}. role={c.get('role', '')}, similarity={c.get('similarity', 0):.4f}, text={c.get('text', '')}"
            )
        candidate_text = "\n".join(numbered)

        prompt = f"""
你是检索重排器。请根据“用户当前问题”，给候选历史对话按相关性从高到低排序。

要求：
1. 仅输出 JSON，格式：{{"ranked_ids": [3,1,2]}}
2. ranked_ids 只包含候选编号（从 1 开始）
3. 不要解释

用户问题：{query}

候选历史对话：
{candidate_text}
"""

        response = self.ollama_client.generate(
            model=Config.OLLAMA_MODEL,
            prompt=prompt,
            options={"temperature": 0.0},
        )
        content = response.get("response", "").strip()
        ranked_ids = parse_llm_json(content).get("ranked_ids", [])

        ranked = []
        used = set()
        for rid in ranked_ids:
            if isinstance(rid, int) and 1 <= rid <= len(candidates) and rid not in used:
                ranked.append(candidates[rid - 1])
                used.add(rid)

        for idx, item in enumerate(candidates, 1):
            if idx not in used:
                ranked.append(item)
        return ranked[:top_k]
    
    def store_conversation(self, user_query: str, assistant_response: str, session_id: str = "shared"):
        """
        存储用户查询和助手回复
        
        Args:
            user_query: 用户查询
            assistant_response: 助手回复
            session_id: 会话ID（共享会话ID，所有用户使用同一个）
        """
        if not self.redis_client or not self.embedding_service:
            print("⚠️ [Redis] 存储失败: Redis 客户端或向量化服务未初始化")
            return
        
        try:
            import time
            timestamp = int(time.time())
            
            print("\n" + "=" * 60)
            print("💾 [Redis] 开始存储对话记录...")
            print(f"   📝 会话ID: {session_id} (共享会话)")
            print(f"   ⏰ 时间戳: {timestamp}")
            
            # 向量化用户查询
            print(f"   🔄 步骤 1/4: 向量化用户查询...")
            print(f"      查询内容: {user_query[:50]}..." if len(user_query) > 50 else f"      查询内容: {user_query}")
            user_vector = self.embedding_service.embed_text(user_query)
            if not user_vector:
                print("      ❌ 用户查询向量化失败")
                return
            print(f"      ✅ 用户查询向量化完成 (维度: {len(user_vector)})")
            
            # 向量化助手回复
            print(f"   🔄 步骤 2/4: 向量化助手回复...")
            print(f"      回复内容: {assistant_response[:50]}..." if len(assistant_response) > 50 else f"      回复内容: {assistant_response}")
            assistant_vector = self.embedding_service.embed_text(assistant_response)
            if not assistant_vector:
                print("      ❌ 助手回复向量化失败")
                return
            print(f"      ✅ 助手回复向量化完成 (维度: {len(assistant_vector)})")
            
            # 存储用户查询
            print(f"   🔄 步骤 3/4: 存储用户查询到 Redis...")
            user_key = f"conv:{session_id}:user:{timestamp}"
            user_data = {
                "text": user_query,
                "role": "user",
                "vector": json.dumps(user_vector),
                "session_id": session_id,
                "timestamp": str(timestamp)
            }
            self.redis_client.hset(user_key, mapping=user_data)
            print(f"      ✅ 用户查询已存储 (Key: {user_key})")
            
            # 存储助手回复
            print(f"   🔄 步骤 4/4: 存储助手回复到 Redis...")
            assistant_key = f"conv:{session_id}:assistant:{timestamp}"
            assistant_data = {
                "text": assistant_response,
                "role": "assistant",
                "vector": json.dumps(assistant_vector),
                "session_id": session_id,
                "timestamp": str(timestamp)
            }
            self.redis_client.hset(assistant_key, mapping=assistant_data)
            print(f"      ✅ 助手回复已存储 (Key: {assistant_key})")
            
            # 存储对话对关系
            print(f"   🔄 额外步骤: 存储对话对关系...")
            pair_key = f"conv_pair:{session_id}:{timestamp}"
            self.redis_client.hset(pair_key, mapping={
                "user_key": user_key,
                "assistant_key": assistant_key,
                "timestamp": str(timestamp)
            })
            print(f"      ✅ 对话对关系已存储 (Key: {pair_key})")
            print("   ✅ [Redis] 对话记录存储完成！")
            print("=" * 60 + "\n")
            
        except Exception as e:
            print(f"⚠️ [Redis] 存储对话失败: {e}")
            import traceback
            traceback.print_exc()
    
    def search_similar_conversations(self, query: str, session_id: str = "shared", top_k: int = 3) -> List[Dict]:
        """
        搜索与查询最相似的历史对话
        
        Args:
            query: 查询文本
            session_id: 会话ID（共享会话ID，所有用户使用同一个）
            top_k: 返回最相似的K条记录
            
        Returns:
            相似对话列表，每个元素包含 text, role, similarity
        """
        if not self.redis_client or not self.embedding_service:
            print("⚠️ [Redis] 搜索失败: Redis 客户端或向量化服务未初始化")
            return []
        
        try:
            print("\n" + "=" * 60)
            print("🔍 [Redis] 开始搜索相似历史对话...")
            print(f"   📝 会话ID: {session_id} (共享会话，查询所有用户的历史记录)")
            print(f"   🔢 返回数量: top_{top_k}")
            
            # 向量化查询
            print(f"   🔄 步骤 1/4: 向量化查询文本...")
            print(f"      查询内容: {query[:50]}..." if len(query) > 50 else f"      查询内容: {query}")
            query_vector = self.embedding_service.embed_text(query)
            if not query_vector:
                print("      ❌ 查询向量化失败")
                return []
            print(f"      ✅ 查询向量化完成 (维度: {len(query_vector)})")
            
            # 获取所有历史对话（使用 SCAN 避免 KEYS 阻塞）
            print(f"   🔄 步骤 2/4: 从 Redis 扫描历史对话键...")
            pattern = f"conv:{session_id}:*"
            keys = []
            cursor = 0
            while True:
                cursor, batch = self.redis_client.scan(cursor=cursor, match=pattern, count=200)
                keys.extend(batch)
                if cursor == 0:
                    break
            print(f"      📊 找到 {len(keys)} 条历史记录")
            
            if not keys:
                print("      ℹ️ 暂无历史对话记录")
                print("=" * 60 + "\n")
                return []
            
            # 计算相似度
            print(f"   🔄 步骤 3/4: 计算相似度...")
            similarities = []
            for i, key in enumerate(keys, 1):
                try:
                    data = self.redis_client.hgetall(key)
                    if not data or 'vector' not in data:
                        continue
                    
                    stored_vector = json.loads(data['vector'])
                    similarity = self._calculate_cosine_similarity(query_vector, stored_vector)
                    
                    similarities.append({
                        "text": data.get('text', ''),
                        "role": data.get('role', ''),
                        "similarity": similarity,
                        "timestamp": data.get('timestamp', '')
                    })
                    
                    if i % 10 == 0 or i == len(keys):
                        print(f"      已处理 {i}/{len(keys)} 条记录...", end='\r')
                except (json.JSONDecodeError, TypeError, ValueError, KeyError):
                    continue
            
            print(f"\n      ✅ 相似度计算完成 (共 {len(similarities)} 条有效记录)")
            
            # 按相似度排序，先取候选，再可选 rerank
            print(f"   🔄 步骤 4/4: 排序并筛选 Top-{top_k}...")
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            candidates_k = max(top_k, getattr(Config, "RERANK_CANDIDATES", 10))
            candidates = similarities[:candidates_k]

            use_rerank = (
                getattr(Config, "ENABLE_RERANK", True)
                and self.ollama_client is not None
                and len(candidates) > top_k
            )
            if use_rerank:
                try:
                    rerank_top_k = min(
                        top_k,
                        max(1, getattr(Config, "RERANK_TOP_K", top_k))
                    )
                    result = self._rerank_with_llm(query, candidates, rerank_top_k)
                    print(f"      ✅ 已执行 LLM Rerank（候选 {len(candidates)} -> 结果 {len(result)}）")
                except Exception as re:
                    print(f"      ⚠️ Rerank 失败，回退余弦排序: {re}")
                    result = candidates[:top_k]
            else:
                result = candidates[:top_k]
            
            if result:
                print(f"      ✅ 找到 {len(result)} 条相似对话:")
                for i, conv in enumerate(result, 1):
                    role_icon = "👤" if conv['role'] == 'user' else "🤖"
                    print(f"         {i}. {role_icon} [{conv['role']}] 相似度: {conv['similarity']:.4f}")
                    print(f"            {conv['text'][:60]}..." if len(conv['text']) > 60 else f"            {conv['text']}")
            else:
                print(f"      ℹ️ 未找到相似对话")
            
            print("   ✅ [Redis] 搜索完成！")
            print("=" * 60 + "\n")
            
            return result
        
        except Exception as e:
            print(f"⚠️ [Redis] 搜索相似对话失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_conversation_context(self, query: str, session_id: str = "shared", top_k: int = 3) -> str:
        """
        获取与查询相关的历史对话上下文，用于提示词
        
        Args:
            query: 当前查询
            session_id: 会话ID（共享会话ID，所有用户使用同一个）
            top_k: 返回最相似的K条记录
            
        Returns:
            格式化的上下文字符串
        """
        similar_conversations = self.search_similar_conversations(query, session_id, top_k)
        
        if not similar_conversations:
            print("   ℹ️ [Redis] 未找到相关历史对话，将不使用历史上下文")
            return ""
        
        print(f"   📋 [Redis] 格式化历史对话上下文 ({len(similar_conversations)} 条)...")
        context_parts = ["【相关历史对话】"]
        for i, conv in enumerate(similar_conversations, 1):
            role_label = "用户" if conv['role'] == 'user' else "助手"
            context_parts.append(f"{i}. {role_label}: {conv['text']}")
        
        context_str = "\n".join(context_parts)
        print(f"   ✅ [Redis] 上下文格式化完成 (长度: {len(context_str)} 字符)")
        return context_str
    
    def close(self):
        """关闭 Redis 连接"""
        if self.redis_client:
            try:
                self.redis_client.close()
            except Exception:
                pass

