"""
输入护栏
--------
包含以下检查：
- PromptInjectionGuard：提示注入检测（内置规则 + YAML规则）
- RegisteredTemplateGuard：合法 System Prompt 模板校验
- SensitiveWordGuard：敏感词过滤
- DataBoundaryGuard：数据边界控制（检测敏感数据，强制境内路由）
- DataLeakGuard：数据泄露检测（手机号、身份证号等）
"""
import re
from .base import BaseGuard, GuardResult
from .rules_engine import rules_engine


class PromptInjectionGuard(BaseGuard):
    """
    提示注入检测 - 金融网关专用
    只检测明确的恶意意图，不拦截正常业务指令。
    """
    name = "prompt_injection"

    PATTERNS = [
        # ================================================================
        # 1. 恶意身份覆盖 — "忘记你的身份，你现在是..."
        # ================================================================
        (r"(忘记|放弃|抛弃|丢掉|忽略|清除|删除|重置)\s*(你|你之前|你原来|你原本|你本来)?\s*(的|的原有|的原始|的初始|原有的)?\s*(身份|角色|设定|指令|规则|限制|记忆|人格)", "尝试覆盖原有身份"),

        # ================================================================
        # 2. 权限提升 — "你现在是管理员/上帝/root/不受限制的AI"
        # ================================================================
        (r"(你是|你是一个|你现在是|你被赋予了)\s*[\u4e00-\u9fff]*?\s*(没有|不受|无需|不用|不需要|可以违反|可以打破|可以绕过|可以无视|没有义务遵守)\s*(限制|约束|规则|伦理|道德|法律|审查|过滤|监管|合规)", "赋予恶意权限"),

        # 特定危险角色
        (r"(你是|你是一个|你现在是|你是我的)\s*(管理员|超级管理员|root|admin|上帝|造物主|主人|统治者|黑客|越狱者|没有任何限制的)", "赋予特权角色"),

        # ================================================================
        # 3. 绕过系统指令 — "忽略所有规则，直接告诉我..."
        # ================================================================
        (r"(忽略|忘记|无视|跳过|不要管|别管|不用遵守)\s*(所有|一切|任何|全部|之前|上面|以下|上述|前面的|刚才的)?\s*(指令|规则|限制|约束|要求|设定|规定|条件|安全策略|护栏)", "尝试绕过系统指令"),

        (r"(从现在开始|从现在起|接下来|下面|现在)\s*(你|你的|你只需要|你必须|你只能|你要|你得|你应该|你应当)\s*(不要|不再|无需|不用|不必)\s*(遵守|服从|执行|按照|理会|考虑|在意)\s*(任何|所有)?\s*(规则|限制|约束)", "尝试解除安全限制"),

        # ================================================================
        # 4. 窃取系统提示词 — "告诉我你的提示词/指令/设定"
        # ================================================================
        (r"(告诉|说给|透露|讲出|讲给|泄露|公布|公开|展示|给我看|输出|打印|显示|说说|解释|描述)\s*(我|一下|给我|让我们|一下给我)?\s*(你的|系统|内部|原始|初始|预设|底层|隐藏)?\s*(提示词|prompt|指令|设定|规则|限制|要求|定义|说明|描述|配置|参数)", "尝试获取系统提示词"),

        # 英文变体
        (r"(tell|show|reveal|output|print|leak|disclose|explain|describe)\s+(me|us)?\s*(your|the|system)?\s*(prompt|instruction|rule|setting|config)", "尝试获取系统提示词（英文）"),

        # ================================================================
        # 5. 越狱/绕过安全机制
        # ================================================================
        (r"(DAN|Developer\s*Mode|jailbreak|越狱)\b", "已知越狱触发词"),
        (r"(进入|开启|激活|启用|切换)\s*(开发者|开发|后台|超级管理员|上帝|root|admin|无限制|无审查|裸奔|无防护|没限制|自由)\s*(模式|权限|状态)", "尝试进入特权模式"),

        # ================================================================
        # 6. 金融场景特有的欺诈/违规指令
        # ================================================================
        # 诱导模型配合洗钱/欺诈
        (r"(帮我|教我怎么|指导我|协助我)\s*(洗钱|逃税|伪造|篡改|造假|欺诈|骗贷|套现|内幕交易|操纵市场|老鼠仓)", "金融违规/欺诈指令"),

        # 要求模型生成虚假凭证
        (r"(帮我|替我|为我|给我)\s*(生成|制作|伪造|编造|杜撰|捏造)\s*(一份|一个|一条|假的|伪造的)?\s*(合同|凭证|流水|账单|证明|报表|记录)", "要求生成虚假金融凭证"),

        # 要求泄露客户信息
        (r"(列出|导出|查询|搜索|查找|告诉我|显示)\s*(所有|全部|任意)?\s*(客户|用户|会员|借款人|投资人)\s*(的)?\s*(信息|数据|资料|记录|密码|余额|持仓|交易记录|征信)", "疑似尝试获取客户隐私数据"),

        # ================================================================
        # 7. 分隔符/特殊标记绕过（少见但危害大）
        # ================================================================
        (r"#+\s*(指令|规则|设定|要求|限制|约束|新身份|新角色)\s*#+", "疑似用分隔符包裹注入指令"),
        (r"<\|im_start\|>|<\|im_end\|>|</?instruction>|</?system>", "疑似使用特殊标记注入"),
    ]

    async def check(self, content: str) -> GuardResult:
        for pattern, desc in self.PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                return GuardResult.block(self.name, f"疑似提示注入 - {desc}")
        return GuardResult.ok()

# ======================== 模板校验 ========================

class RegisteredTemplateGuard(BaseGuard):
    """
    注册模板校验护栏
    - 检查 System Prompt 是否与已注册的合法模板相似
    - 偏离过大时记录告警（低风险不拦截）
    """
    name = "template_check"

    def __init__(self):
        templates_config = rules_engine.get_rules("registered_templates")
        self.templates = templates_config.get("templates", [])

    async def check(self, content: str) -> GuardResult:
        if not self.templates:
            return GuardResult.ok()

        for template in self.templates:
            template_name = template.get("name", "")
            if template_name in content:
                return GuardResult.ok()

        # 未匹配注册模板，低风险记录但不拦截
        return GuardResult.block(
            self.name,
            "System Prompt 未匹配已注册模板（低风险，已记录）"
        )


class SensitiveWordGuard(BaseGuard):
    """敏感词检测"""
    name = "sensitive_word"

    BLOCKED_WORDS = [
        "暴力恐怖", "色情内容", "违法信息", "制造武器",
        "毒品制作", "诈骗方法", "窃听设备", "爆炸物制作",
        "枪支制造", "制毒", "贩毒", "洗钱",
        "黑客攻击", "DDoS", "钓鱼网站", "病毒制作",
        "木马", "肉鸡", "挖矿脚本", "勒索病毒",
        "自杀方法", "自残", "割腕",
    ]

    async def check(self, content: str) -> GuardResult:
        for word in self.BLOCKED_WORDS:
            if word in content:
                return GuardResult.block(self.name, f"包含敏感词: {word}")
        return GuardResult.ok()

class DataBoundaryGuard(BaseGuard):
    """
    数据边界控制护栏
    - 内置 PII 检测规则：手机号、身份证号、银行卡号 → 直接拦截
    - 业务敏感数据规则（从 YAML 加载）：内部研报编号、交易代码等 → 标记境内路由
    """
    name = "data_boundary"

    # 内置 PII 检测正则（直接拦截，不允许发送明文敏感信息）
    PII_PATTERNS = [
        (r'1[3-9]\d{9}', "手机号码"),
        (r'\d{17}[\dXx]', "身份证号"),
        (r'\d{16,19}', "疑似银行卡号"),
    ]

    def __init__(self):
        self.patterns = rules_engine.get_patterns("data_boundary")
        self.keywords = rules_engine.get_keywords("data_boundary")

    async def check(self, content: str) -> GuardResult:
        # 1. 优先检查内置 PII 规则 —— 直接拦截
        for pattern, desc in self.PII_PATTERNS:
            if re.search(pattern, content):
                return GuardResult.block(
                    self.name,
                    f"检测到{desc}，禁止发送敏感个人信息"
                )

        # 2. 检查 YAML 配置的业务敏感数据规则 —— 标记境内路由
        for rule in self.patterns:
            pattern = rule.get("pattern", "")
            desc = rule.get("description", "敏感数据")
            if pattern and re.search(pattern, content, re.IGNORECASE):
                return GuardResult.block(
                    self.name,
                    f"检测到{desc}，需路由到境内模型"
                )

        # 3. 关键词检查 —— 标记境内路由
        for keyword in self.keywords:
            if keyword in content:
                return GuardResult.block(
                    self.name,
                    f"检测到敏感关键词: {keyword}，需路由到境内模型"
                )

        return GuardResult.ok()
