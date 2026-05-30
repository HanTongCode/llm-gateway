"""全局配置，集中读取 .env"""
import os
from dotenv import load_dotenv


load_dotenv()

class Settings():
    """所有配置项统一从这里取"""
    LLM_API_KEY = os.getenv("LLM_API_KEY")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL")
    #路由修改
    MODEL_ROUTES = {
        "deepseek-chat": LLM_BASE_URL,
        "gpt-3.5-turbo": "https://api.openai.com/v1",
        "gpt-4": "https://api.openai.com/v1"
    }

settings = Settings()
