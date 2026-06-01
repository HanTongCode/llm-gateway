"""令牌桶限流器 - Redis Lua 原子实现"""
import time
import redis.asyncio as redis
from config import settings


class TokenBucket:
    def __init__(self):
        self.redis: redis.Redis | None = None

    async def _get_redis(self) -> redis.Redis:
        if self.redis is None:
            self.redis = redis.from_url(settings.REDIS_URL, protocol=2)
        return self.redis

    async def consume(self, key: str, rate: float, capacity: int) -> bool:
        r = await self._get_redis()
        now = time.time()

        script = """
        local key = KEYS[1]
        local rate = tonumber(ARGV[1])
        local capacity = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])

        local tokens = tonumber(redis.call('hget', key, 'tokens'))
        local last_time = tonumber(redis.call('hget', key, 'last_time'))

        if tokens == nil then
            tokens = capacity
            last_time = now
        else
            local delta = math.max(0, now - last_time)
            tokens = math.min(capacity, tokens + delta * rate)
            last_time = now
        end

        if tokens >= 1 then
            tokens = tokens - 1
            redis.call('hset', key, 'tokens', tokens)
            redis.call('hset', key, 'last_time', last_time)
            redis.call('expire', key, 60)
            return 1
        end

        redis.call('hset', key, 'last_time', last_time)
        redis.call('expire', key, 60)
        return 0
        """

        result = await r.eval(script, 1, key, rate, capacity, now)
        return result == 1


token_bucket = TokenBucket()