"""
审计上下文
----------
定义每次请求的完整审计信息模型。
在请求开始时创建 AuditContext 实例，贯穿整个请求生命周期，
由各中间件和路由层填充字段，最终由 AuditLogger 写入日志。
"""
import time
import uuid
from datetime import datetime
from typing import Optional


class AuditContext:
    """单次请求的审计上下文，记录 15 个维度信息"""

    def __init__(self):
        # 唯一请求 ID，用于全链路追踪
        self.request_id: str = str(uuid.uuid4())
        # 请求开始时间，用于计算延迟
        self.start_time: float = time.time()

        # ---- 以下字段由各模块逐步填充 ----
        self.tenant_id: str = ""
        self.tenant_name: str = ""
        self.api_key: str = ""                  # 最后写入时仅保留后4位
        self.model: str = ""
        self.stream: bool = False
        self.messages_length: int = 0
        self.status_code: int = 0
        self.error: Optional[str] = None
        self.guard_triggered: Optional[str] = None  # 触发的护栏名称
        self.tokens_prompt: int = 0
        self.tokens_completion: int = 0
        self.tokens_total: int = 0
        self.ip_address: str = ""

    def to_dict(self) -> dict:
        """将审计上下文转为字典，供日志写入"""
        # 计算请求延迟（毫秒）
        latency = int((time.time() - self.start_time) * 1000)
        return {
            "request_id": self.request_id,
            "timestamp": datetime.utcnow().isoformat(),
            "tenant_id": self.tenant_id,
            "tenant_name": self.tenant_name,
            "api_key": self.api_key[-4:] if self.api_key else "",  # 脱敏
            "model": self.model,
            "stream": self.stream,
            "messages_length": self.messages_length,
            "status_code": self.status_code,
            "error": self.error,
            "guard_triggered": self.guard_triggered,
            "latency_ms": latency,
            "tokens_prompt": self.tokens_prompt,
            "tokens_completion": self.tokens_completion,
            "tokens_total": self.tokens_total,
            "ip_address": self.ip_address,
        }