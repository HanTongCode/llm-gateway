"""
熔断器（3 状态）
----------------
每个模型/供应商独立维护熔断状态。
Closed（正常）：请求正常通过，失败计数递增
Open（熔断）：失败率超阈值 → 直接跳过，不请求该模型
Half-Open（试探）：冷却期后放行少量请求探测恢复
"""
import time
from enum import Enum
from typing import Optional


class CircuitState(Enum):
    CLOSED = "closed"           # 正常
    OPEN = "open"               # 熔断
    HALF_OPEN = "half_open"     # 试探


class CircuitBreaker:
    """单模型熔断器"""

    def __init__(
        self,
        fail_threshold: int = 5,       # 连续失败次数阈值
        fail_rate_threshold: float = 0.5,  # 失败率阈值（窗口内）
        timeout: float = 30.0,          # 熔断冷却时间（秒）
        half_open_limit: int = 2,       # 半开状态允许的探测请求数
        window_size: int = 20,          # 滑动窗口大小（用于计算失败率）
    ):
        self.fail_threshold = fail_threshold
        self.fail_rate_threshold = fail_rate_threshold
        self.timeout = timeout
        self.half_open_limit = half_open_limit
        self.window_size = window_size

        self.state: CircuitState = CircuitState.CLOSED
        self.consecutive_failures: int = 0      # 连续失败次数
        self.last_failure_time: float = 0.0     # 最近一次失败时间
        self.half_open_count: int = 0            # 半开状态已放行请求数
        self.window: list = []                   # 滑动窗口 [(timestamp, success), ...]

    def call(self) -> bool:
        """
        请求前调用，判断是否允许通过。
        返回 True 表示放行，False 表示熔断。
        """
        now = time.time()

        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # 检查冷却期是否结束
            if now - self.last_failure_time >= self.timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_count = 0
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # 允许少量探测请求
            if self.half_open_count < self.half_open_limit:
                self.half_open_count += 1
                return True
            return False

        return True  # 兜底

    def on_success(self):
        """请求成功时调用"""
        now = time.time()
        self.window.append((now, True))
        self._trim_window()

        if self.state == CircuitState.HALF_OPEN:
            # 试探成功，恢复为关闭状态
            self.state = CircuitState.CLOSED
            self.consecutive_failures = 0
        elif self.state == CircuitState.CLOSED:
            self.consecutive_failures = 0

    def on_failure(self):
        """请求失败时调用"""
        now = time.time()
        self.window.append((now, False))
        self._trim_window()

        self.consecutive_failures += 1
        self.last_failure_time = now

        # 触发熔断条件：
        # 1. 连续失败次数达到阈值
        # 2. 滑动窗口内失败率超过阈值
        window_failure_rate = self._failure_rate()

        if self.consecutive_failures >= self.fail_threshold or \
           (len(self.window) >= 5 and window_failure_rate >= self.fail_rate_threshold):
            self.state = CircuitState.OPEN

    def _failure_rate(self) -> float:
        """计算滑动窗口内的失败率"""
        if not self.window:
            return 0.0
        failures = sum(1 for _, success in self.window if not success)
        return failures / len(self.window)

    def _trim_window(self):
        """移除窗口外的旧记录"""
        if len(self.window) > self.window_size:
            self.window = self.window[-self.window_size:]

    def get_state(self) -> dict:
        """获取当前状态（供管理接口查看）"""
        return {
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "failure_rate": round(self._failure_rate(), 4),
            "window_size": len(self.window),
        }


class CircuitBreakerManager:
    """熔断器管理器：为每个模型/供应商维护独立的熔断器"""

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, provider: str, model_name: str) -> CircuitBreaker:
        """获取或创建指定模型的熔断器"""
        key = f"{provider}:{model_name}"
        if key not in self._breakers:
            self._breakers[key] = CircuitBreaker()
        return self._breakers[key]

    def get_all_states(self) -> dict:
        """获取所有熔断器的状态"""
        return {
            key: breaker.get_state()
            for key, breaker in self._breakers.items()
        }