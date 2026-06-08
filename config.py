"""全局配置，集中读取 .env"""
import os
from dotenv import load_dotenv


load_dotenv()

class Settings():
    """所有配置项统一从这里取"""
    LLM_API_KEY = os.getenv("LLM_API_KEY")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    CACHE_SIMILARITY_THRESHOLD = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.92"))
    #路由修改
    MODEL_ROUTES = {
        "deepseek-chat": os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
        "gpt-3.5-turbo": os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "gpt-4": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    }

settings = Settings()
