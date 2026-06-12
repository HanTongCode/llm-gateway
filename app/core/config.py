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

    # ======================== 多模型路由表 ========================
    # 模型名 → API 基础 URL 映射，新增模型只需在此添加一行
    MODEL_ROUTES = {
        "deepseek-chat": os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
        "gpt-3.5-turbo": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "gpt-4": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    }

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