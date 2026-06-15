"""
适配器注册器
------------
提供 @register_adapter 装饰器，实现插件的自动注册和发现。
新增模型只需在 adapters/ 目录下添加文件并使用装饰器，核心路由引擎会自动加载。
"""
import inspect
import importlib
import pkgutil
from typing import Dict, Type
from app.adapters.base import BaseAdapter


class AdapterRegistry:
    """适配器注册中心"""

    def __init__(self):
        self._adapters: Dict[str, BaseAdapter] = {}  # provider:model_name -> 实例

    def register(self, provider: str, model_name: str, adapter_cls: Type[BaseAdapter]):
        """
        注册一个适配器类
        Args:
            provider: 提供商名称
            model_name: 模型名称
            adapter_cls: 适配器类（非实例）
        """
        key = f"{provider}:{model_name}"
        self._adapters[key] = adapter_cls()

    def get_adapter_by_model(self, model_name: str):
        """根据模型名查找适配器（忽略 provider）"""
        for key, adapter in self._adapters.items():
            if adapter.model_name == model_name:
                return adapter
        raise KeyError(f"未注册的模型: {model_name}")

    def get_adapter(self, provider: str, model_name: str) -> BaseAdapter:
        """
        根据提供商和模型名获取适配器实例
        Raises:
            KeyError: 适配器未注册
        """
        key = f"{provider}:{model_name}"
        if key not in self._adapters:
            raise KeyError(f"未找到适配器: {key}")
        return self._adapters[key]

    def get_all_adapters(self) -> Dict[str, BaseAdapter]:
        """获取所有已注册的适配器"""
        return self._adapters

    def find_by_capability(self, capability: str) -> Dict[str, BaseAdapter]:
        """
        根据能力筛选适配器
        返回所有支持指定能力的适配器
        """
        return {
            key: adapter
            for key, adapter in self._adapters.items()
            if adapter.supports_capability(capability)
        }

    def auto_discover(self, package_path: str = "app.adapters"):
        """
        自动扫描 adapters/ 目录，加载所有已注册的适配器。
        在应用启动时调用一次即可。
        """
        package = importlib.import_module(package_path)
        for _, module_name, _ in pkgutil.iter_modules(package.__path__):
            importlib.import_module(f"{package_path}.{module_name}")


# 全局注册中心实例
registry = AdapterRegistry()


def register_adapter(provider: str, model_name: str):
    """
    装饰器：用于注册适配器类
    用法：
        @register_adapter("openai", "gpt-4")
        class GPT4Adapter(BaseAdapter):
            ...
    """
    def decorator(cls):
        registry.register(provider, model_name, cls)
        return cls
    return decorator