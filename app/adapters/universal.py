"""
通用 OpenAI 兼容适配器
----------------------
所有完全兼容 OpenAI 协议的模型共用此适配器。
新增模型只需在 config.py 的 REGISTERED_MODELS 中添加配置，无需编写代码。
"""
from typing import Dict
from app.adapters.base import BaseAdapter


class UniversalAdapter(BaseAdapter):
    """通用适配器：从配置字典读取模型所有信息"""

    def __init__(self, config: dict):
        self._config = config

    @property
    def provider(self) -> str:
        return self._config["provider"]

    @property
    def model_name(self) -> str:
        return self._config["model_name"]

    @property
    def capabilities(self) -> list:
        return self._config.get("capabilities", ["chat"])

    @property
    def max_context_tokens(self) -> int:
        return self._config.get("max_context_tokens", 4096)

    @property
    def cost_per_1m_input(self) -> float:
        return self._config.get("cost_per_1m_input", 0.0)

    @property
    def cost_per_1m_output(self) -> float:
        return self._config.get("cost_per_1m_output", 0.0)

    @property
    def base_url(self) -> str:
        return self._config.get("base_url", "")

    @property
    def api_key(self) -> str:
        return self._config.get("api_key", "")

    async def translate_request(self, request: Dict) -> Dict:
        # OpenAI 兼容模型，直接透传
        return request

    async def translate_response(self, response: Dict) -> Dict:
        return response

    async def get_health(self) -> bool:
        # 通用适配器不主动检查后端健康，交给熔断器
        return True