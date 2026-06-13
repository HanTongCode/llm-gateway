"""
请求收尾
--------
封装"指标记录 + 缓存写入 + 审计日志"的后置处理逻辑。
编排层只需调用 finalize_request，不需要知道内部步骤。
"""
import json
import asyncio
from app.core.metrics import record
from app.core.audit_logger import audit_logger
from app.services.resilience.cache import semantic_cache


def finalize_request(ctx, body, response):
    """请求收尾：指标 → 缓存 → 审计"""
    record(ctx)

    if not body.stream and ctx.status_code == 200:
        try:
            content = json.loads(response.body.decode("utf-8"))
            reply = content["choices"][0]["message"]["content"]
            asyncio.create_task(semantic_cache.set(body.messages[-1].content, reply))
        except (json.JSONDecodeError, KeyError, AttributeError):
            pass

    asyncio.create_task(audit_logger.log(ctx.to_dict()))