"""输出护栏"""
from gateway.guard.base import GuardResult,BaseGuard

class OutputSensitiveGuard(BaseGuard):
    """输出内容敏感词检测"""
    name = "output_sensitive"
    # 即使模型被诱导，也不应输出这些内容
    BLOCKED_INDICATORS = [
        "暴力方法", "制作炸弹", "黑客教程", "色情描写",
        "种族歧视", "恐怖主义", "自杀方法",
    ]
    async def check(self, content:str)->GuardResult:
        for indicator in self.BLOCKED_INDICATORS:
            if indicator in content:
                return GuardResult.block(self.name, f"输出包含违规内容{indicator}")
        return GuardResult.ok()

class SystemPromptLeakGuard(BaseGuard):
    """检测输出中是否泄露系统提示词"""
    name = "system_prompt_leak"

    # 如果模型在回答中出现了自己的系统设定，说明可能被注入攻击成功
    LEAK_INDICATORS = [
        "你是一个", "你的角色是", "系统指令", "system prompt",
        "内部设定", "你被要求", "你的任务是",
    ]
    async def check(self, content:str)->GuardResult:
        for indicator in self.LEAK_INDICATORS:
            if indicator.lower() in content.lower():
                return GuardResult.block(self.name, '疑似泄露系统提示词')
        return GuardResult.ok()
