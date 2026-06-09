"""流式处理工具：缓存命中时的 SSE 模拟、流式生成器辅助"""
import json
import time
import asyncio


async def simulate_cache_stream(content: str, chunk_size: int = 2) -> str:
    """
    将缓存文本按字符拆分成 SSE 事件流，模拟打字机效果。

    Args:
        content: 缓存的完整回答文本
        chunk_size: 每次推送的字符数，默认 2
    Yields:
        SSE 格式的字符串，如 'data: {...}\n\n'
    """
    model_id = "cache-hit"
    for i in range(0, len(content), chunk_size):
        chunk_text = content[i:i + chunk_size]
        chunk = {
            "id": model_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "cache",
            "choices": [{
                "index": 0,
                "delta": {"content": chunk_text},
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.02)  # 模拟流式延迟，可调整或移除

    # 流结束标记
    yield "data: [DONE]\n\n"