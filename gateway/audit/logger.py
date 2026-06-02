"""审计日志模块 - 文件存储"""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
import asyncio


class AuditLogger:
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

    async def log(self, entry: dict):
        """异步写入日志，不阻塞主线程"""
        await asyncio.to_thread(self._write_sync, entry)

    def _write_sync(self, entry: dict):
        """同步写入文件（按日期分片）"""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        file_path = self.log_dir / f"gateway-audit-{today}.jsonl"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# 全局实例
audit_logger = AuditLogger()