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

    def select_model(
        self,
        required_capability: str = "chat",
        messages: list = None,
        max_tokens: int = None,
        agent_id: Optional[str] = None,
        preferred_provider: Optional[str] = None,
        preferred_model: Optional[str] = None,
    ) -> BaseAdapter:
        """
        选择最优模型。

        Args:
            required_capability: 请求需要的能力（如 "chat", "reasoning"）
            messages: 请求消息列表（用于成本估算）
            max_tokens: 最大输出 token 数（用于成本估算）
            agent_id: Agent 标识（预留）
            preferred_provider: 优先提供商（可选）

        Returns:
            选中的适配器实例

        Raises:
            RuntimeError: 无可用模型
        """
        # 1. 获取候选模型（已过滤不支持能力和过载的）
        candidates = self.health_tracker.get_candidates(required_capability, registry)
        if not candidates:
            raise RuntimeError(f"无可用模型支持能力: {required_capability}")
        # 2. 如果客户端指定了模型，优先查找
        if preferred_model:
            for adapter, health in candidates:
                if adapter.model_name == preferred_model:
                    # 检查是否过载
                    if health.is_overloaded:
                        raise RuntimeError(f"指定模型 {preferred_model} 当前过载，请稍后重试")
                    health.current_load += 1
                    return adapter
            raise RuntimeError(f"指定模型 {preferred_model} 不支持能力 {required_capability} 或未注册")
        # 2. 如果指定优先提供商，进一步筛选
        if preferred_provider:
            candidates = [
                (a, h) for a, h in candidates
                if a.provider == preferred_provider
            ]
            if not candidates:
                raise RuntimeError(f"提供商 {preferred_provider} 无可用模型")

        # 3. 根据策略选择
        if self.strategy == RoutingStrategy.WEIGHTED_RANDOM:
            adapter = strategies.weighted_random(candidates)
        elif self.strategy == RoutingStrategy.COST_FIRST:
            adapter = strategies.cost_first(candidates, messages or [], max_tokens)
        elif self.strategy == RoutingStrategy.LATENCY_FIRST:
            adapter = strategies.latency_first(candidates)
        else:
            raise ValueError(f"未知路由策略: {self.strategy}")

        # 4. 记录并发
        self.health_tracker.get(adapter.provider, adapter.model_name).current_load += 1

        return adapter

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
        health.current_load = max(0, health.current_load - 1)
        health.total += 1
        if success:
            health.success += 1
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