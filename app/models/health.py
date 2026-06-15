"""
模型健康度数据模型
------------------
定义单个模型运行时的健康度数据结构。
供 HealthTracker、路由引擎、熔断器等组件使用。
"""
from dataclasses import dataclass, field
from typing import List
import time


@dataclass
class ModelHealth:
    """单个模型的运行时健康度数据"""

    provider: str                           # 模型提供商（如 "deepseek"）
    model_name: str                         # 模型名称（如 "deepseek-chat"）
    max_load: int = 10                      # 最大并发能力

    # 实时状态
    current_load: int = 0                   # 当前并发请求数
    success: int = 0                        # 累计成功次数
    total: int = 0                          # 累计总调用次数
    latency_window: List[float] = field(default_factory=list)  # 最近50次延迟（秒）
    last_updated: float = field(default_factory=time.time)
    consecutive_failures: int = 0
    @property
    def key(self) -> str:
        """唯一标识"""
        return f"{self.provider}:{self.model_name}"

    @property
    def success_rate(self) -> float:
        """成功率（0.0 ~ 1.0）"""
        return self.success / self.total if self.total > 0 else 1.0

    @property
    def load_rate(self) -> float:
        """负载率（0.0 ~ 1.0）"""
        return self.current_load / self.max_load if self.max_load > 0 else 1.0

    @property
    def health_score(self) -> float:
        """
        综合健康度评分（0.0 ~ 1.0）
        成功率权重 60%，负载率权重 40%
        """
        return (self.success_rate * 0.6) + ((1.0 - self.load_rate) * 0.4)

    @property
    def avg_latency(self) -> float:
        """滑动窗口平均延迟（秒），无数据返回正无穷"""
        if not self.latency_window:
            return float("inf")
        return sum(self.latency_window) / len(self.latency_window)

    @property
    def is_overloaded(self) -> bool:
        """是否已过载"""
        return self.current_load >= self.max_load