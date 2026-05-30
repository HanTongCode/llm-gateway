"""模型转发调度：负责跟后端模型通信"""
import aiohttp
from config import settings
from fastapi.responses import JSONResponse, StreamingResponse
async def dispatch_to_model(body: dict) :
    """转发请求到模型后端，返回完整响应"""
    model = body.get("model", "deepseek-chat")
    base_url = settings.MODEL_ROUTES.get(model, settings.LLM_BASE_URL)
    if not base_url:
        return JSONResponse(content={"error": f"不支持的模型: {model}"},status_code=400,)
    url = f"{base_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    if body.get("stream"):
        # 流式：返回一个异步生成器，保持 session 存活
        return StreamingResponse(
            _stream_response(url, headers, body),
            media_type="text/event-stream",
        )
    else:
        # 非流式：解析 JSON
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as resp:
                data = await resp.json()
        return JSONResponse(content=data)

async def _stream_response(url: str, headers: dict, body: dict):
    """流式生成器：逐块读取并转发"""
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers=headers) as resp:
             async for chunk in resp.content.iter_any():
                 yield chunk