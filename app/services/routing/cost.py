"""
成本估算器
----------
根据消息内容和模型单价，计算单次调用的预估成本。
"""
from app.adapters.base import BaseAdapter


class CostEstimator:
    """成本估算器"""

    @staticmethod
    def estimate_input_tokens(messages: list) -> int:
        """
        估算输入 token 数。
        当前简化实现：按字符数 / 3（中文场景近似）。
        生产环境建议接入 tiktoken 库。
        """
        total_chars = sum(
            len(msg.content) if hasattr(msg, "content") else len(msg.get("content", ""))
            for msg in messages
        )
        return max(1, total_chars // 3)

    @staticmethod
    def estimate_output_tokens(messages: list, max_tokens: int = None) -> int:
        """
        预估输出 token 数。
        优先使用 max_tokens，否则按输入 token 的 50% 估算（至少 100）。
        """
        if max_tokens:
            return max_tokens
        input_tokens = CostEstimator.estimate_input_tokens(messages)
        return max(100, int(input_tokens * 0.5))

    @staticmethod
    def calculate(
        adapter: BaseAdapter,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """
        计算本次调用的预估成本（美元）。
        """
        input_cost = (input_tokens * adapter.cost_per_1m_input) / 1_000_000
        output_cost = (output_tokens * adapter.cost_per_1m_output) / 1_000_000
        return input_cost + output_cost