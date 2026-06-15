"""
全局配置模块
------------
所有配置项统一从环境变量读取，通过 pydantic Settings 类集中管理。
配置来源：.env 文件 + 系统环境变量
"""
import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量（必须在读取配置之前调用）
load_dotenv()


class Settings:
    """应用配置类，所有配置项均以类属性形式访问"""

    # ======================== 基础服务配置 ========================
    # 服务监听地址和端口
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Redis 连接地址，用于缓存、限流、会话管理
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # ======================== 大模型 API 配置 ========================
    # 默认模型 API Key（DeepSeek 或其他 OpenAI 兼容厂商）
    LLM_API_KEY: str = os.getenv("LLM_API_KEY")
    # 默认模型 API 地址
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    # OpenAI 独立 Key（可选，若与 LLM_API_KEY 不同则配置）
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")

    # ======================== 注册模型列表（新增） ========================
    REGISTERED_MODELS = [
        {
            "provider": "deepseek",
            "model_name": "deepseek-chat",
            "capabilities": ["chat", "long_context", "function_calling", "json_mode"],
            "max_context_tokens": 131072,
            "cost_per_1m_input": 0.14,
            "cost_per_1m_output": 0.28,
            "base_url": os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
            "api_key": os.getenv("DEEPSEEK_API_KEY", os.getenv("LLM_API_KEY", "")),
        },
        {
            "provider": "openai",
            "model_name": "gpt-4",
            "capabilities": ["chat", "reasoning", "function_calling", "json_mode"],
            "max_context_tokens": 8192,
            "cost_per_1m_input": 30.0,
            "cost_per_1m_output": 60.0,
            "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "api_key": os.getenv("OPENAI_API_KEY", ""),
        },
        # ======================== 模拟模型（不可用，仅验证路由） ========================
        {
            "provider": "moonshot",
            "model_name": "moonshot-v1",
            "capabilities": ["chat", "long_context"],
            "max_context_tokens": 128000,
            "cost_per_1m_input": 0.14,
            "cost_per_1m_output": 0.28,
            "base_url": os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1"),
            "api_key": os.getenv("MOONSHOT_API_KEY", ""),
        },
        {
            "provider": "aliyun",
            "model_name": "qwen-plus",
            "capabilities": ["chat", "reasoning", "function_calling"],
            "max_context_tokens": 131072,
            "cost_per_1m_input": 0.14,
            "cost_per_1m_output": 0.28,
            "base_url": os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            "api_key": os.getenv("DASHSCOPE_API_KEY", ""),
        },
        {
            "provider": "local",
            "model_name": "local-qwen",
            "capabilities": ["chat"],
            "max_context_tokens": 8192,
            "cost_per_1m_input": 0.14,
            "cost_per_1m_output": 0.28,
            "base_url": os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1"),
            "api_key": "",  # 本地模型无需 Key
        },
    ]
    # ======================== 语义缓存配置 ========================
    # 缓存相似度阈值（0~1），值越大匹配越严格
    CACHE_SIMILARITY_THRESHOLD: float = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.55"))

    # ======================== 金融合规扩展（预留字段） ========================
    # 模型计费单价（元/百万Token），用于成本精确核算
    # 示例：{"deepseek-chat": 1.0, "gpt-4": 70.0}
    # 正式上线时从环境变量或配置中心加载
    MODEL_PRICES: dict = {}

    # PII 脱敏规则（预留），可配置需要脱敏的正则表达式列表
    # 例如：["phone", "id_card", "email"]
    PII_RULES: list = []

    # 熔断器参数（预留）
    # 连续失败次数阈值、熔断打开时间（秒）、半开状态允许的探测请求数
    CIRCUIT_BREAKER_FAIL_THRESHOLD: int = 5
    CIRCUIT_BREAKER_TIMEOUT: int = 30
    CIRCUIT_BREAKER_HALF_OPEN_LIMIT: int = 2


# 全局配置单例，供其他模块导入
settings = Settings()