"""
DeepSeek 模型适配器
-------------------
支持 deepseek-chat（V3）和 deepseek-reasoner（R1）。
"""
from typing import Dict
from app.adapters.base import BaseAdapter
from app.adapters.registry import register_adapter


@register_adapter("deepseek", "deepseek-chat")
class DeepSeekChatAdapter(BaseAdapter):
    provider = "deepseek"
    model_name = "deepseek-chat"
    capabilities = ["chat", "long_context", "function_calling", "json_mode", "batch"]
    max_context_tokens = 131072
    cost_per_1m_input = 0.14   # 美元（示例价格）
    cost_per_1m_output = 0.28

    async def translate_request(self, request: Dict) -> Dict:
        # DeepSeek 完全兼容 OpenAI 格式，直接透传
        return request

    async def translate_response(self, response: Dict) -> Dict:
        return response

    async def get_health(self) -> bool:
        # 简单判断：配置了 API Key 即可用
        from app.core.config import settings
        return bool(settings.LLM_API_KEY)


@register_adapter("deepseek", "deepseek-reasoner")
class DeepSeekReasonerAdapter(BaseAdapter):
    provider = "deepseek"
    model_name = "deepseek-reasoner"
    capabilities = ["reasoning", "long_context"]  # 推理类
    max_context_tokens = 131072
    cost_per_1m_input = 0.55
    cost_per_1m_output = 2.19

    async def translate_request(self, request: Dict) -> Dict:
        # DeepSeek R1 同样兼容 OpenAI
        return request

    async def translate_response(self, response: Dict) -> Dict:
        return response

    async def get_health(self) -> bool:
        from app.core.config import settings
        return bool(settings.LLM_API_KEY)