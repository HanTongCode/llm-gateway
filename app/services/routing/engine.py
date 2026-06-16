"""
动态路由引擎
------------
整合健康度追踪、成本估算、策略选择，提供唯一入口 select_model()。
编排层只需调用 select_model 和 record_result。
"""
from typing import Optional
from app.adapters.registry import registry
from app.adapters.base import BaseAdapter
from app.services.routing.health import HealthTracker
from app.services.routing import strategies
from app.services.resilience.circuit_breaker import CircuitBreakerManager

class RoutingStrategy:
    """路由策略常量"""
    WEIGHTED_RANDOM = "weighted_random"
    COST_FIRST = "cost_first"
    LATENCY_FIRST = "latency_first"


class ModelRouter:
    """动态路由引擎"""

    def __init__(self, strategy: str = RoutingStrategy.WEIGHTED_RANDOM):
        self.strategy = strategy
        self.health_tracker = HealthTracker()
        self.circuit_breaker = CircuitBreakerManager()

    async def get_ranked_candidates(
            self,
            required_capability: str = "chat",
            messages: list = None,
            max_tokens: int = None,
    ) -> list[BaseAdapter]:
        """
        返回按当前策略排序的可用模型列表，用于自动路由。
        自动过滤：能力不匹配、熔断中、并发已满的模型。
        """
        # 1. 从注册中心获取支持该能力的适配器
        all_adapters = registry.find_by_capability(required_capability)

        # 2. 批量获取所有模型的实时并发数
        model_keys = [(a.provider, a.model_name) for a in all_adapters.values()]
        loads = await self.health_tracker.get_all_current_loads(model_keys)
        # 3. 过滤
        filtered = []
        for key, adapter in all_adapters.items():
            # 熔断检查
            if not self.circuit_breaker.get(adapter.provider, adapter.model_name).call():
                continue
            # 并发满检查
            current = loads.get(f"{adapter.provider}:{adapter.model_name}", 0)
            max_load = getattr(adapter, "max_concurrency", 10)
            if current >= max_load:
                continue
            filtered.append(adapter)

        if not filtered:
            raise RuntimeError(f"无可用模型支持能力: {required_capability}")

        # 4. 按当前策略排序
        if self.strategy == RoutingStrategy.COST_FIRST:
            filtered.sort(key=lambda a: a.cost_per_1m_input)
        elif self.strategy == RoutingStrategy.LATENCY_FIRST:
            filtered.sort(
                key=lambda a: self.health_tracker.get(
                    a.provider, a.model_name
                ).avg_latency
            )
        else:
            filtered.sort(
                key=lambda a: self.health_tracker.get(
                    a.provider, a.model_name
                ).health_score,
                reverse=True,
            )
        return filtered

    def record_result(
        self,
        provider: str,
        model_name: str,
        success: bool,
        latency: float
    ) -> None:
        """
        请求完成后调用，更新健康度数据。

        Args:
            provider: 模型提供商
            model_name: 模型名称
            success: 请求是否成功
            latency: 本次请求的延迟（秒）
        """
        health = self.health_tracker.get(provider, model_name)
        breaker = self.circuit_breaker.get(provider, model_name)
        health.current_load = max(0, health.current_load - 1)
        health.total += 1
        if success:
            health.success += 1
            health.consecutive_failures = 0
            breaker.on_success()
        else:
            breaker.on_failure()
            health.consecutive_failures += 1
        health.latency_window.append(latency)
        if len(health.latency_window) > 50:
            health.latency_window.pop(0)
        health.last_updated = __import__("time").time()

    def switch_strategy(self, strategy: str) -> None:
        """运行时切换路由策略"""
        if strategy not in [
            RoutingStrategy.WEIGHTED_RANDOM,
            RoutingStrategy.COST_FIRST,
            RoutingStrategy.LATENCY_FIRST,
        ]:
            raise ValueError(f"未知路由策略: {strategy}")
        self.strategy = strategy