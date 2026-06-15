"""
路由策略实现
------------
提供三种路由策略：加权随机、成本优先、延迟优先。
所有策略函数返回选中的 BaseAdapter 实例。
"""
import random
from typing import List, Tuple
from app.adapters.base import BaseAdapter
from app.models.health import ModelHealth
from app.services.routing.cost import CostEstimator


def weighted_random(
    candidates: List[Tuple[BaseAdapter, ModelHealth]]
) -> BaseAdapter:
    """
    加权随机：健康度越高的模型获得越高的选中概率。
    退化为等概率随机的情况：所有模型健康度均为 0。
    """
    if not candidates:
        raise RuntimeError("无可用模型")

    weights = [health.health_score for _, health in candidates]
    total = sum(weights)

    if total == 0:
        return random.choice([adapter for adapter, _ in candidates])

    normalized = [w / total for w in weights]
    adapters = [adapter for adapter, _ in candidates]
    return random.choices(adapters, weights=normalized, k=1)[0]


def cost_first(
    candidates: List[Tuple[BaseAdapter, ModelHealth]],
    messages: list,
    max_tokens: int = None
) -> BaseAdapter:
    """
    成本优先：选择预估成本最低的模型。
    """
    if not candidates:
        raise RuntimeError("无可用模型")

    input_tokens = CostEstimator.estimate_input_tokens(messages)
    output_tokens = CostEstimator.estimate_output_tokens(messages, max_tokens)

    best = min(
        candidates,
        key=lambda c: CostEstimator.calculate(c[0], input_tokens, output_tokens)
    )
    return best[0]


def latency_first(
    candidates: List[Tuple[BaseAdapter, ModelHealth]]
) -> BaseAdapter:
    """
    延迟优先：选择滑动窗口平均延迟最低的模型。
    无延迟数据时退化为加权随机。
    """
    if not candidates:
        raise RuntimeError("无可用模型")

    # 按延迟升序排列，无数据（inf）排到最后
    sorted_candidates = sorted(candidates, key=lambda c: c[1].avg_latency)

    # 如果所有模型都无延迟数据，退化为加权随机
    if sorted_candidates[0][1].avg_latency == float("inf"):
        return weighted_random(candidates)

    return sorted_candidates[0][0]