"""
模型适配器基类
--------------
定义所有模型适配器的统一接口和能力声明。
每个新增模型只需继承此基类并使用 @register_adapter 装饰器注册即可。
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from app.core.config import settings
class BaseAdapter(ABC):
    """模型适配器抽象基类"""

    # 子类必须定义以下属性
    provider: str                       # 模型提供商名称（如 "openai", "deepseek"）
    model_name: str                     # 模型标识（如 "gpt-4", "deepseek-chat"）

    # 能力声明（子类覆盖）
    # 可选值：chat, reasoning, long_context, vision, function_calling, embedding, json_mode, batch
    capabilities: List[str] = ["chat"]

    # 可选：模型支持的上下文窗口大小
    max_context_tokens: int = 4096

    # 可选：模型成本（美元/百万token），用于成本路由
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0
    @property
    def base_url(self) -> str:
        """模型 API 基础地址"""
        return settings.MODEL_ROUTES.get(self.model_name, "")

    @abstractmethod
    async def translate_request(self, request: Dict) -> Dict:
        """
        将统一的内部请求格式转换为模型厂商特定的请求格式。
        大多数 OpenAI 兼容模型可以直接透传，非兼容模型需要重写此方法。
        """
        ...

    @abstractmethod
    async def translate_response(self, response: Dict) -> Dict:
        """
        将模型厂商的响应格式转换为统一的内部响应格式。
        """
        ...

    @abstractmethod
    async def get_health(self) -> bool:
        """
        健康检查：判断模型后端是否可用。
        返回 True 表示可用，False 表示不可用。
        """
        ...

    def supports_capability(self, capability: str) -> bool:
        """判断此模型是否支持指定能力"""
        return capability in self.capabilities

    def get_cost_estimate(self, input_tokens: int, output_tokens: int) -> float:
        """估算本次调用的成本（美元）"""
        return (input_tokens * self.cost_per_1m_input + output_tokens * self.cost_per_1m_output) / 1_000_000