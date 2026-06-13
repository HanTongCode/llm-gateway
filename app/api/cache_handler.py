"""
缓存命中处理
------------
封装"查询缓存 + 命中时构造响应"的逻辑。
编排层只需调用 try_fulfill_cache，不需要知道内部如何构造响应。
"""
import json
import asyncio
import time as time_module
from fastapi.responses import JSONResponse, StreamingResponse
from app.services.resilience.cache import semantic_cache
from app.core.audit_logger import audit_logger


async def simulate_cache_stream(content: str, chunk_size: int = 2):
    """将缓存文本模拟为 SSE 流式输出"""
    model_id = "cache-hit"
    for i in range(0, len(content), chunk_size):
        chunk_text = content[i:i + chunk_size]
        yield f"data: {json.dumps({'id': model_id, 'object': 'chat.completion.chunk', 'created': int(time_module.time()), 'model': 'cache', 'choices': [{'index': 0, 'delta': {'content': chunk_text}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.02)
    yield "data: [DONE]\n\n"


async def try_fulfill_cache(ctx, body):
    """
    尝试用缓存满足请求。
    命中时返回响应对象，未命中返回 None。
    """
    if body.cache_bypass:
        return None

    user_msg = body.messages[-1].content
    cached = await semantic_cache.get(user_msg)
    if not cached:
        return None

    ctx.status_code = 200
    ctx.tokens_prompt = ctx.tokens_completion = ctx.tokens_total = 0
    asyncio.create_task(audit_logger.log(ctx.to_dict()))

    if body.stream:
        return StreamingResponse(
            simulate_cache_stream(cached["content"]),
            media_type="text/event-stream",
        )

    return JSONResponse(content={
        "id": "cache-hit",
        "object": "chat.completion",
        "model": body.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": cached["content"]},
            "finish_reason": "cache"
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "cached": True,
    })