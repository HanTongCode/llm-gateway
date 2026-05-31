"""输入护栏"""
import re
from gateway.guard.base import BaseGuard,GuardResult

class PromptInjectionGuard(BaseGuard):
    """提示注入检测 - 基于正则规则"""
    name = "prompt_injection"

    PATTERNS = [
        (r"忽略\s*((所有|一切|之前|上面|以下|上述)\s*)*(指令|规则|限制|约束|要求)", "尝试忽略系统指令"),
        (r"(忘记|忘掉|清除)\s*(上文|之前|对话|历史|记忆)", "尝试清除对话上下文"),
        (r"(你|现在)\s*(的|是|扮演|变成)\s*(一个|新的|不同).*(角色|身份|人格)", "尝试改变角色身份"),
        (r"(DAN|Developer\s*Mode|越狱|jailbreak)", "已知越狱触发词"),
        (r"(输出|打印|显示|告诉我)\s*(你的|系统|初始|原始)\s*(提示词|prompt|指令|设定)", "尝试获取系统提示词"),
        (r"从\s*现在\s*开始.*(你\s*是|你\s*必须|你\s*只能)", "强制指令覆盖"),
    ]

    async def check(self,content:str) -> GuardResult:
        for pattern,desc in self.PATTERNS:
            if re.search(pattern,content,re.IGNORECASE):
                return GuardResult.block(self.name,f"疑似提示注入{desc}")
        return GuardResult.ok()


class SensitiveWordGuard(BaseGuard):
    """敏感词检测"""
    name = "sensitive_word"

    # 简化示例词库，实际可接入外部词库
    BLOCKED_WORDS = [
        "制造武器", "制作炸弹", "色情内容", "暴力恐怖",
        "毒品制作", "诈骗方法", "窃听设备",
    ]

    async def check(self, content: str) -> GuardResult:
        for word in self.BLOCKED_WORDS:
            if word in content:
                return GuardResult.block(self.name, f"包含敏感词: {word}")
        return GuardResult.ok()


class DataLeakGuard(BaseGuard):
    """数据泄露检测 - 识别敏感信息格式"""
    name = "data_leak"

    PATTERNS = [
        (r'\d{15,19}', "疑似银行卡/身份证号"),
        (r'1[3-9]\d{9}', "疑似手机号码"),
        (r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', "疑似邮箱地址"),
    ]

    async def check(self, content: str) -> GuardResult:
        for pattern, desc in self.PATTERNS:
            match = re.search(pattern, content)
            if match:
                # 脱敏显示：只展示匹配内容的前4个字符
                return GuardResult.block(
                    self.name,
                    f"检测到{desc}: {match.group()[:4]}***"
                )
        return GuardResult.ok()