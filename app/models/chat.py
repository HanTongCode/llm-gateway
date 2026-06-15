"""聊天相关数据模型"""
from pydantic import BaseModel
from typing import List, Optional


class Message(BaseModel):
    """单条对话消息"""
    role: str       # system / user / assistant
    content: str    # 消息文本


class ChatRequest(BaseModel):
    """聊天请求体，兼容 OpenAI 格式"""
    model: Optional[str] = None          # 模型名称
    messages: List[Message]               # 对话历史
    stream: Optional[bool] = False        # 是否流式输出
    cache_bypass: Optional[bool] = False  # 是否跳过缓存
    temperature: Optional[float] = None   # 温度参数（0-2）
    top_p: Optional[float] = None         # top_p 参数