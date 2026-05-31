"""模型转发调度：负责跟后端模型通信"""
import aiohttp
from config import settings
from fastapi.responses import JSONResponse, StreamingResponse
from gateway.guard import GuardPipeline,PromptInjectionGuard,SensitiveWordGuard,DataLeakGuard

# 初始化输入护栏管道（模块加载时创建一次，不用每次请求都创建）
input_pipeline = GuardPipeline([
    PromptInjectionGuard(),
    SensitiveWordGuard(),
    DataLeakGuard(),
])

def extract_user_message(messages: list) -> str:
    """从 messages 中提取最后一条用户消息"""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""

async def dispatch_to_model(body: dict) :
    """转发请求到模型后端，返回完整响应"""
    model = body.get("model", "deepseek-chat")
    base_url = settings.MODEL_ROUTES.get(model, settings.LLM_BASE_URL)
    if not base_url:
        return JSONResponse(content={"error": f"不支持的模型: {model}"},status_code=400,)
    # ========== 输入护栏检查 ==========
    user_msg = extract_user_message(body.get("messages", []))
    if user_msg:
        guard_result = await input_pipeline.run(user_msg)
        if not guard_result.passed:
            return JSONResponse(
                content={
                    "error": f"输入内容违反安全策略: {guard_result.reason}",
                    "guard": guard_result.guard_name,
                },
                status_code=422,
            )

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