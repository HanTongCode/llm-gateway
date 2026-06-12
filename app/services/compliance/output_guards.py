"""
输出护栏
--------
检查模型生成内容是否合规，包括敏感内容检测和系统提示词泄露检测。
"""
from .base import BaseGuard, GuardResult


class OutputSensitiveGuard(BaseGuard):
    """输出内容敏感词检测"""
    name = "output_sensitive"

    BLOCKED_INDICATORS = [
        "暴力方法", "制作炸弹", "黑客教程", "色情描写",
        "种族歧视", "恐怖主义", "自杀方法",
    ]

    async def check(self, content: str) -> GuardResult:
        for indicator in self.BLOCKED_INDICATORS:
            if indicator in content:
                return GuardResult.block(self.name, f"输出包含违规内容: {indicator}")
        return GuardResult.ok()


class SystemPromptLeakGuard(BaseGuard):
    """检测输出中是否泄露系统提示词"""
    name = "system_prompt_leak"

    LEAK_INDICATORS = [
        "你是一个", "你的角色是", "系统指令", "system prompt",
        "内部设定", "你被要求", "你的任务是",
    ]

    async def check(self, content: str) -> GuardResult:
        for indicator in self.LEAK_INDICATORS:
            if indicator.lower() in content.lower():
                return GuardResult.block(self.name, "输出疑似泄露系统提示词")
        return GuardResult.ok()