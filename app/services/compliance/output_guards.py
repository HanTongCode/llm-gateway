"""
输出护栏
--------
包含以下检查：
- OutputSensitiveGuard：输出敏感内容检测
- SystemPromptLeakGuard：系统提示词泄露检测
- FinancialComplianceGuard：金融合规审核（投资建议、保本承诺、内幕信息）
"""
import re
from .base import BaseGuard, GuardResult
from .rules_engine import rules_engine


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

# ======================== 金融合规审核 ========================

class FinancialComplianceGuard(BaseGuard):
    """
    金融合规输出审核
    - 检测投资建议用语（"建议买入"、"目标价 XX"）
    - 检测保本承诺（"保证收益"、"稳赚不赔"）
    - 检测疑似内幕信息泄露
    """
    name = "financial_compliance"

    def __init__(self):
        light_rules = rules_engine.get_rules("output_compliance")
        light_weight = light_rules.get("light_weight", {})
        self.patterns = light_weight.get("patterns", [])
        self.keywords = light_weight.get("keywords", [])

    async def check(self, content: str) -> GuardResult:
        # 正则匹配
        for rule in self.patterns:
            pattern = rule.get("pattern", "")
            desc = rule.get("description", "合规风险")
            print(content, pattern, desc, "输出检测")
            if pattern and re.search(pattern, content, re.IGNORECASE):
                return GuardResult.block(
                    self.name,
                    f"检测到合规风险: {desc}"
                )

        # 关键词匹配
        for keyword in self.keywords:
            if keyword in content:
                return GuardResult.block(
                    self.name,
                    f"检测到合规风险关键词: {keyword}"
                )

        return GuardResult.ok()