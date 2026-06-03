"""语义缓存：基于 TF-IDF + 余弦相似度的本地缓存（可替换为更强模型）"""
import numpy as np
import redis.asyncio as redis
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import jieba
from config import settings


def jieba_tokenizer(text):
    """jieba 分词器，供 TfidfVectorizer 使用"""
    return jieba.lcut(text)


class SemanticCache:
    def __init__(self):
        self.redis: redis.Redis | None = None
        self.threshold = settings.CACHE_SIMILARITY_THRESHOLD
        # 用 TF-IDF 向量器，使用 jieba 分词，支持中文
        self.vectorizer = TfidfVectorizer(tokenizer=jieba_tokenizer)

    async def _get_redis(self) -> redis.Redis:
        if self.redis is None:
            self.redis = redis.from_url(settings.REDIS_URL, protocol=2)
        return self.redis

    async def get(self, user_input: str) -> dict | None:
        """查找缓存：返回命中的缓存数据，或 None"""
        r = await self._get_redis()

        # 获取所有已缓存的输入文本
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

        # 将当前输入与所有历史输入合并，构建 TF-IDF 矩阵
        all_texts = cached_texts + [user_input]
        try:
            tfidf_matrix = self.vectorizer.fit_transform(all_texts)
        except ValueError:
            # 如果词汇表为空（极少情况），跳过
            return None

        # 最后一行是当前输入向量，前面各行是历史缓存向量
        user_vec = tfidf_matrix[-1]
        cache_vecs = tfidf_matrix[:-1]

        # 计算余弦相似度
        similarities = cosine_similarity(user_vec, cache_vecs).flatten()
        best_idx = np.argmax(similarities)
        best_score = similarities[best_idx]
        if best_score >= self.threshold:
            best_key = keys[best_idx]
            cached = await r.hgetall(best_key)
            return {
                "content": cached.get(b"content", b"").decode("utf-8"),
                "score": float(best_score),
            }
        return None

    async def set(self, user_input: str, response_content: str):
        """存入缓存：保存输入文本和响应内容，下次计算时动态生成向量"""
        r = await self._get_redis()
        key = f"cache:vec:{hash(user_input)}"

        await r.hset(key, "input", user_input)
        await r.hset(key, "content", response_content)
        await r.expire(key, 3600 * 24)  # 24小时过期


# 全局实例
semantic_cache = SemanticCache()