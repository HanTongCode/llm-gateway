"""审计上下文管理器"""
import time
import uuid
from datetime import datetime
from typing import Optional


class AuditContext:
    def __init__(self):
        self.request_id: str = str(uuid.uuid4())
        self.start_time: float = time.time()
        self.tenant_id: str = ""
        self.tenant_name: str = ""
        self.api_key: str = ""
        self.model: str = ""
        self.stream: bool = False
        self.messages_length: int = 0
        self.status_code: int = 0
        self.error: Optional[str] = None
        self.guard_triggered: Optional[str] = None
        self.tokens_prompt: int = 0
        self.tokens_completion: int = 0
        self.tokens_total: int = 0
        self.ip_address: str = ""

    def to_dict(self) -> dict:
        latency = int((time.time() - self.start_time) * 1000)
        return {
            "request_id": self.request_id,
            "timestamp": datetime.utcnow().isoformat(),
            "tenant_id": self.tenant_id,
            "tenant_name": self.tenant_name,
            "api_key": self.api_key[-4:] if self.api_key else "",
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