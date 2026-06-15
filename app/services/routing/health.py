"""
模型健康度追踪器
----------------
维护所有模型的健康度数据，提供注册、查询、更新等功能。
数据模型定义在 app.models.health 中。
"""
from app.models.health import ModelHealth


class HealthTracker:
    """模型健康度管理器"""

    def __init__(self):
        self._models: dict[str, ModelHealth] = {}

    def register(
        self,
        provider: str,
        model_name: str,
        max_load: int = 10,
        adapter=None
    ) -> ModelHealth:
        """
        注册一个新模型。
        如果提供了 adapter 且它声明了 max_concurrency，优先使用适配器的值。
        """
        if adapter and hasattr(adapter, "max_concurrency"):
            max_load = adapter.max_concurrency

        health = ModelHealth(
            provider=provider,
            model_name=model_name,
            max_load=max_load
        )
        self._models[health.key] = health
        return health

    def get(self, provider: str, model_name: str) -> ModelHealth:
        """获取模型健康度，不存在则自动注册"""
        key = f"{provider}:{model_name}"
        if key not in self._models:
            return self.register(provider, model_name)
        return self._models[key]

    def get_all(self) -> dict:
        """获取所有已注册模型的健康度"""
        return self._models

    def get_candidates(self, capability: str, adapter_registry) -> list:
        """
        获取支持指定能力且未过载的候选模型列表。
        返回 [(BaseAdapter, ModelHealth), ...]。
        """
        candidates = []
        for key, adapter in adapter_registry.find_by_capability(capability).items():
            health = self.get(adapter.provider, adapter.model_name)
            if not health.is_overloaded:
                candidates.append((adapter, health))
        return candidates