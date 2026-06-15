"""
适配器注册中心
--------------
存储所有已注册的模型适配器，提供查找功能。
模型通过配置驱动加载，不再使用装饰器注册。
"""
from app.adapters.base import BaseAdapter
from app.adapters.universal import UniversalAdapter

class AdapterRegistry:
    def __init__(self):
        self._adapters: dict[str, BaseAdapter] = {}

    def load_from_config(self, models_config: list):
        """从配置列表批量注册通用适配器"""
        for item in models_config:
            adapter = UniversalAdapter(item)
            key = f"{adapter.provider}:{adapter.model_name}"
            self._adapters[key] = adapter

    def get_adapter(self, provider: str, model_name: str) -> BaseAdapter:
        key = f"{provider}:{model_name}"
        if key not in self._adapters:
            raise KeyError(f"未找到适配器: {key}")
        return self._adapters[key]

    def get_adapter_by_model(self, model_name: str) -> BaseAdapter:
        for adapter in self._adapters.values():
            if adapter.model_name == model_name:
                return adapter
        raise KeyError(f"未注册的模型: {model_name}")

    def get_all_adapters(self) -> dict:
        return self._adapters

    def find_by_capability(self, capability: str) -> dict:
        return {
            key: adapter
            for key, adapter in self._adapters.items()
            if adapter.supports_capability(capability)
        }


registry = AdapterRegistry()