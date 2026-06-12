"""
语义缓存服务
------------
基于 TF-IDF 向量 + 余弦相似度的相似问题匹配。
核心流程：
1. 请求进入 → 提取用户消息 → 计算向量 → 与 Redis 中缓存的向量做相似度匹配
2. 相似度超过阈值 → 直接返回缓存答案（零 Token 消耗）
3. 未命中 → 调大模型 → 异步写入缓存

设计权衡：
- 使用 jieba 分词 + TF-IDF 而非专用嵌入模型，零额外依赖，CPU 毫秒级响应
- 架构预留了嵌入模型接口，未来可无缝升级为 Sentence-BERT 或接入 Milvus
"""
import numpy as np
import redis.asyncio as redis
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import jieba

from app.core.config import settings


def jieba_tokenizer(text):
    """jieba 分词器，供 TfidfVectorizer 使用"""
    return jieba.lcut(text)


class SemanticCache:
    """
    语义缓存类
    - 存储：用户问题 → TF-IDF 向量 + 回答文本
    - 检索：全量遍历 + 余弦相似度（可升级为 HNSW 索引）
    - 写入：异步执行，不阻塞主请求链路
    """

    def __init__(self):
        self.redis: redis.Redis | None = None
        self.threshold = settings.CACHE_SIMILARITY_THRESHOLD
        self.vectorizer = TfidfVectorizer(tokenizer=jieba_tokenizer)

    async def _get_redis(self) -> redis.Redis:
        """延迟初始化 Redis 连接"""
        if self.redis is None:
            self.redis = redis.from_url(settings.REDIS_URL, protocol=2)
        return self.redis

    async def get(self, user_input: str) -> dict | None:
        """
        查找缓存
        Args:
            user_input: 用户最后一条消息
        Returns:
            命中时返回 {"content": "...", "score": 0.95}
            未命中时返回 None
        """
        r = await self._get_redis()

        # ---- 1. 先从 Redis 加载所有已缓存的问题文本 ----
        cached_texts = []
        keys = []
        cursor = 0
        while True:
            cursor, batch = await r.scan(cursor, match="cache:vec:*", count=100)
            for key in batch:
                text = await r.hget(key, "input")
                if text:
                    cached_texts.append(text.decode("utf-8"))
                    keys.append(key)
            if cursor == 0:
                break

        if not cached_texts:
            return None

        # ---- 2. 将当前输入与所有历史输入合并，构建 TF-IDF 矩阵 ----
        all_texts = cached_texts + [user_input]
        try:
            tfidf_matrix = self.vectorizer.fit_transform(all_texts)
        except ValueError:
            return None

        # ---- 3. 计算余弦相似度 ----
        user_vec = tfidf_matrix[-1]           # 当前输入向量
        cache_vecs = tfidf_matrix[:-1]        # 历史缓存向量
        similarities = cosine_similarity(user_vec, cache_vecs).flatten()

        best_idx = int(np.argmax(similarities))
        best_score = float(similarities[best_idx])

        # ---- 4. 判断是否超过阈值 ----
        if best_score >= self.threshold:
            best_key = keys[best_idx]
            cached = await r.hgetall(best_key)
            return {
                "content": cached.get(b"content", b"").decode("utf-8"),
                "score": best_score,
            }
        return None

    async def set(self, user_input: str, response_content: str):
        """
        存入缓存（异步调用，不阻塞主流程）
        Args:
            user_input: 用户问题
            response_content: 模型回答
        """
        r = await self._get_redis()
        key = f"cache:vec:{hash(user_input)}"

        await r.hset(key, "input", user_input)
        await r.hset(key, "content", response_content)
        await r.expire(key, 3600 * 24)  # 24 小时后自动过期


# 全局单例，供路由层调用
semantic_cache = SemanticCache()