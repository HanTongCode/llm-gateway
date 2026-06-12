"""
审计日志写入器
--------------
功能：
1. 接收 AuditContext.to_dict() 生成的字典
2. 异步写入本地 JSONL 文件，按日期分片
3. 不阻塞主请求链路（通过 asyncio.to_thread 在后台线程执行 I/O）
4. 后续可扩展为写入 Elasticsearch、ClickHouse 等专业日志平台
"""
import json
import asyncio
from datetime import datetime
from pathlib import Path


class AuditLogger:
    """审计日志写入器"""

    def __init__(self, log_dir: str = "logs"):
        # 日志存储目录，默认在项目根目录下的 logs/
        self.log_dir = Path(log_dir)
        # 确保目录存在
        self.log_dir.mkdir(exist_ok=True)

    async def log(self, entry: dict):
        """
        异步写入日志
        使用 asyncio.to_thread 将阻塞的文件 I/O 操作移到线程池，
        避免阻塞事件循环。
        """
        await asyncio.to_thread(self._write_sync, entry)

    def _write_sync(self, entry: dict):
        """
        同步写入文件（在线程池中执行）
        - 按日期分片：每天一个文件，命名格式 gateway-audit-2024-01-01.jsonl
        - 每行一条 JSON，便于后续批量分析
        """
        today = datetime.utcnow().strftime("%Y-%m-%d")
        file_path = self.log_dir / f"gateway-audit-{today}.jsonl"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# 全局单例，供路由层调用
audit_logger = AuditLogger()