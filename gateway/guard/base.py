"""护栏基类和管道"""
from abc import ABC, abstractmethod
from typing import List
from pydantic import BaseModel

class GuardResult(BaseModel):
    """护栏检测结果"""
    passed: bool
    guard_name: str=''
    reason: str=''
    @classmethod
    def ok(cls):
        return cls(passed=True)
    @classmethod
    def block(cls,name:str,reason:str):
        return cls(passed=False,guard_name=name,reason=reason)
class BaseGuard(ABC):
    """单个护栏基类"""
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    @abstractmethod
    async def check(self,content:str) -> GuardResult:
        pass

class GuardPipeline:
    """护栏管道：按顺序执行多个护栏，任一拦截即终止"""
    def __init__(self,guards:List[BaseGuard]):
        self.guards = guards
    async def run(self,content:str) -> GuardResult:
        for guard in self.guards:
            result = await guard.check(content)
            if not result.passed:
                return result
        return GuardResult.ok()