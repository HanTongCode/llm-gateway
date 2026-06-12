"""
令牌桶限流器
------------
基于 Redis + Lua 脚本实现原子性令牌桶算法。
核心逻辑：
1. 每个租户对应一个 Redis Hash，存储 tokens（剩余令牌）和 last_time（上次填充时间）
2. 请求到达时计算时间差 delta，填充 tokens = min(capacity, tokens + delta * rate)
3. 如果 tokens >= 1，消耗 1 个令牌，返回 True（放行）
4. 否则返回 False（限流），由中间件返回 429 状态码
"""
import time
import redis.asyncio as redis

# 配置模块
from app.core.config import settings


class TokenBucket:
    """
    令牌桶限流器
    - rate: 每秒生成令牌数（如 10 = 每秒10个请求）
    - capacity: 桶容量，允许的最大突发请求数
    """

    def __init__(self):
        self.redis: redis.Redis | None = None

    async def _get_redis(self) -> redis.Redis:
        """延迟初始化 Redis 连接"""
        if self.redis is None:
            self.redis = redis.from_url(settings.REDIS_URL, protocol=2)
        return self.redis

    async def consume(self, key: str, rate: float, capacity: int) -> bool:
        """
        消耗一个令牌
        Args:
            key: Redis 键名，如 "rate:dev_team"
            rate: 每秒填充令牌数
            capacity: 桶容量
        Returns:
            True: 放行, False: 限流
        """
        r = await self._get_redis()
        now = time.time()

        # Lua 脚本，保证读取-计算-更新三步原子执行
        script = """
        local key = KEYS[1]
        local rate = tonumber(ARGV[1])
        local capacity = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])

        -- 从 Redis 读取当前状态
        local tokens = tonumber(redis.call('hget', key, 'tokens'))
        local last_time = tonumber(redis.call('hget', key, 'last_time'))

        -- 首次请求：令牌桶满
        if tokens == nil then
            tokens = capacity
            last_time = now
        else
            -- 根据时间差填充令牌
            local delta = math.max(0, now - last_time)
            tokens = math.min(capacity, tokens + delta * rate)
            last_time = now
        end

        -- 判断是否有可用令牌
        if tokens >= 1 then
            tokens = tokens - 1
            redis.call('hset', key, 'tokens', tokens)
            redis.call('hset', key, 'last_time', last_time)
            redis.call('expire', key, 60)
            return 1  -- 放行
        end

        -- 令牌不足，更新 last_time 后拒绝
        redis.call('hset', key, 'last_time', last_time)
        redis.call('expire', key, 60)
        return 0  -- 限流
        """

        result = await r.eval(script, 1, key, rate, capacity, now)
        return result == 1


# 全局单例，供中间件调用
token_bucket = TokenBucket()