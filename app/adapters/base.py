"""
模型适配器基类
--------------
定义所有模型适配器的统一接口和能力声明。
"""
from abc import ABC, abstractmethod
from typing import List


class BaseAdapter(ABC):
    """模型适配器抽象基类"""

    # 子类必须定义以下属性
    provider: str
    model_name: str
    capabilities: List[str] = ["chat"]
    max_context_tokens: int = 4096
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0

    @property
    @abstractmethod
    def base_url(self) -> str:
        """模型 API 基础地址，子类必须提供"""
        raise NotImplementedError

    @abstractmethod
    async def translate_request(self, request: dict) -> dict:
        """将统一请求格式转换为模型厂商特定格式"""
        ...

    @abstractmethod
    async def translate_response(self, response: dict) -> dict:
        """将模型厂商响应转换为统一格式"""
        ...

    @abstractmethod
    async def get_health(self) -> bool:
        """判断模型后端是否可用"""
        ...

    def supports_capability(self, capability: str) -> bool:
        return capability in self.capabilities

    def get_cost_estimate(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.cost_per_1m_input + output_tokens * self.cost_per_1m_output) / 1_000_000