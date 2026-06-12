"""
合规服务 - 护栏基类与管道
--------------------------
定义安全护栏的统一接口和管道执行逻辑。
所有具体护栏（输入/输出）均继承 BaseGuard，通过 GuardPipeline 串联执行。
"""
from abc import ABC, abstractmethod
from typing import List
from pydantic import BaseModel


class GuardResult(BaseModel):
    """护栏检测结果"""
    passed: bool                    # 是否通过
    guard_name: str = ""            # 触发拦截的护栏名称
    reason: str = ""                # 拦截原因

    @classmethod
    def ok(cls):
        """创建通过结果"""
        return cls(passed=True)

    @classmethod
    def block(cls, name: str, reason: str):
        """创建拦截结果"""
        return cls(passed=False, guard_name=name, reason=reason)


class BaseGuard(ABC):
    """单个护栏抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """护栏名称，用于标识"""
        pass

    @abstractmethod
    async def check(self, content: str) -> GuardResult:
        """
        执行安全检查
        Args:
            content: 待检查的文本内容
        Returns:
            GuardResult: 通过或拦截的结果
        """
        pass


class GuardPipeline:
    """
    护栏管道：按顺序执行多个护栏，任一拦截即终止
    支持动态组合不同的护栏实例
    """

    def __init__(self, guards: List[BaseGuard]):
        self.guards = guards

    async def run(self, content: str) -> GuardResult:
        """按顺序执行所有护栏，任一未通过则立即返回拦截结果"""
        for guard in self.guards:
            result = await guard.check(content)
            if not result.passed:
                return result
        return GuardResult.ok()