"""
模型健康度追踪器
----------------
维护健康度数据（内存），管理 Redis 并发槽位和本地 FIFO 等待队列。
使用 asyncio.Condition + deque 实现公平排队，释放时主动唤醒下一个等待者。
"""
import asyncio
import redis.asyncio as redis
from collections import deque
from app.models.health import ModelHealth
from app.core.config import settings


class HealthTracker:
    def __init__(self):
        self._models: dict[str, ModelHealth] = {}
        self._redis: redis.Redis | None = None

        # 本地等待队列：{"provider:model": {"queue": deque, "condition": asyncio.Condition}}
        self._wait_lists: dict[str, dict] = {}

    # ======================== 注册与查询（内存） ========================

    def register(self, provider: str, model_name: str, max_load: int = 10, adapter=None):
        if adapter and hasattr(adapter, "max_concurrency"):
            max_load = adapter.max_concurrency
        health = ModelHealth(provider=provider, model_name=model_name, max_load=max_load)
        self._models[health.key] = health
        return health

    def get(self, provider: str, model_name: str) -> ModelHealth:
        key = f"{provider}:{model_name}"
        if key not in self._models:
            return self.register(provider, model_name)
        return self._models[key]

    def get_all(self) -> dict:
        return self._models

    # ======================== Redis 连接 ========================

    async def _get_redis(self):
        if self._redis is None:
            self._redis = redis.from_url(settings.REDIS_URL, protocol=2)
        return self._redis

    # ======================== 并发槽位操作（Redis） ========================

    async def get_all_current_loads(self, models: list) -> dict:
        """批量获取多个模型的当前并发数（单次 MGET）"""
        r = await self._get_redis()
        keys = [f"concurrency:{p}:{m}" for p, m in models]
        values = await r.mget(keys)
        result = {}
        for (provider, model_name), value in zip(models, values):
            result[f"{provider}:{model_name}"] = int(value) if value else 0
        return result

    async def acquire_slot(self, provider: str, model_name: str, max_load: int) -> bool:
        """
        原子性抢占一个 Redis 并发槽位。
        成功返回 True，槽位已满返回 False。
        """
        r = await self._get_redis()
        key = f"concurrency:{provider}:{model_name}"
        script = """
        local key = KEYS[1]
        local max_load = tonumber(ARGV[1])
        local current = redis.call('INCR', key)
        if current > max_load then
            redis.call('DECR', key)
            return 0
        end
        return 1
        """
        result = await r.eval(script, 1, key, max_load)
        current = await r.get(key)
        return result == 1

    async def _release_redis_slot(self, provider: str, model_name: str):
        """释放 Redis 槽位（内部方法，仅在没有等待者时调用）"""
        r = await self._get_redis()
        key = f"concurrency:{provider}:{model_name}"
        await r.decr(key)
        if int(await r.get(key) or 0) < 0:
            await r.set(key, 0)

    # ======================== 本地 FIFO 排队 ========================

    def _get_wait_list(self, provider: str, model_name: str) -> dict:
        """获取或创建模型的本地等待列表"""
        key = f"{provider}:{model_name}"
        if key not in self._wait_lists:
            self._wait_lists[key] = {
                "queue": deque(),
                "condition": asyncio.Condition(),
            }
        return self._wait_lists[key]

    async def wait_for_slot(self, provider: str, model_name: str) -> bool:
        """
        进入本地等待队列，阻塞直到被 release_slot 唤醒。
        被唤醒后直接使用槽位（无需再次请求 Redis）。
        如果客户端断开连接，自动从队列中移除。
        """
        wait_list = self._get_wait_list(provider, model_name)
        event = asyncio.Event()

        # 入队
        async with wait_list["condition"]:
            wait_list["queue"].append(event)

        try:
            # 阻塞等待，直到被唤醒
            await event.wait()
            return True
        except asyncio.CancelledError:
            # 客户端断开，从队列中移除自己的事件
            async with wait_list["condition"]:
                try:
                    wait_list["queue"].remove(event)
                except ValueError:
                    pass  # 可能已被取出并设置
            raise

    async def release_slot(self, provider: str, model_name: str):
        """
        释放槽位。
        优先检查本地等待队列，如果有等待者则直接唤醒（槽位转交）。
        如果队列为空，则正常释放 Redis 槽位。
        """
        wait_list = self._get_wait_list(provider, model_name)

        async with wait_list["condition"]:
            if wait_list["queue"]:
                # 取出队首等待者并唤醒
                next_event = wait_list["queue"].popleft()
                next_event.set()
                return  # 槽位已转交，不释放 Redis

        # 无等待者，释放 Redis 槽位
        await self._release_redis_slot(provider, model_name)

