"""模型转发调度：负责跟后端模型通信"""
import aiohttp
from config import settings
from fastapi.responses import JSONResponse, StreamingResponse
from gateway.guard import GuardPipeline,PromptInjectionGuard,SensitiveWordGuard,DataLeakGuard
from gateway.guard.output import OutputSensitiveGuard,SystemPromptLeakGuard
import json
from gateway.audit.context import AuditContext
from fastapi import Request
# 初始化输入护栏管道（模块加载时创建一次，不用每次请求都创建）
input_pipeline = GuardPipeline([
    PromptInjectionGuard(),
    SensitiveWordGuard(),
    DataLeakGuard(),
])
# 初始化输出护栏管道（模块加载时创建一次，不用每次请求都创建）
output_pipeline = GuardPipeline([
    OutputSensitiveGuard(),
    SystemPromptLeakGuard(),
])


def extract_user_message(messages: list) -> str:
    """从 messages 中提取最后一条用户消息"""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""

async def dispatch_to_model(body: dict,request: Request, ctx: AuditContext) :
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

    # 根据模型选择 API Key
    model = body.get("model", "deepseek-chat")
    if model.startswith("gpt"):
        api_key = settings.OPENAI_API_KEY
    else:
        api_key = settings.LLM_API_KEY

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if body.get("stream"):
        # 流式：返回一个异步生成器，保持 session 存活
        return StreamingResponse(
            _stream_and_guard(url, headers, body, output_pipeline),
            media_type="text/event-stream",
        )
    else:
        # 非流式：解析 JSON
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as resp:
                data = await resp.json()
        # ========== 输出护栏检查 ==========
        try:
            await _check_output(data, output_pipeline)
        except OutputGuardViolation as e:
            return JSONResponse(
                content={
                    "error": f"输出内容违反安全策略: {e.reason}",
                    "guard": "output",
                },
                status_code=422,
            )
        # ==================================
        # 提取Token用量
        usage = data.get("usage", {})
        ctx.tokens_prompt = usage.get("prompt_tokens", 0)
        ctx.tokens_completion = usage.get("completion_tokens", 0)
        ctx.tokens_total = usage.get("total_tokens", 0)
        ctx.status_code = 200
        return JSONResponse(content=data)

async def _stream_response(url: str, headers: dict, body: dict):
    """流式生成器：逐块读取并转发"""
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers=headers) as resp:
             async for chunk in resp.content.iter_any():
                 yield chunk


class OutputGuardViolation(Exception):
    """输出护栏违规异常"""
    def __init__(self, reason: str):
        self.reason = reason


async def _check_output(data: dict, pipeline: GuardPipeline):
    """检查非流式响应的输出内容，违规时抛异常"""
    choices = data.get("choices", [])
    for choice in choices:
        content = choice.get("message", {}).get("content", "")
        if content:
            result = await pipeline.run(content)
            if not result.passed:
                raise OutputGuardViolation(result.reason)

async def _stream_and_guard(url: str, headers: dict, body: dict, pipeline: GuardPipeline):
    """流式生成器：逐块转发，同时增量检查输出内容"""
    accumulated_content = ""
    check_interval = 20  # 每累积20个字符检查一次

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers=headers) as resp:
            async for chunk in resp.content.iter_any():
                yield chunk

                # 从 chunk 中解析文本增量
                text = _extract_delta_text(chunk)
                if text:
                    accumulated_content += text

                    # 每满 check_interval 个字符，触发一次护栏检查
                    if len(accumulated_content) >= check_interval:
                        result = await pipeline.run(accumulated_content)
                        if not result.passed:
                            # 输出违规，生成错误消息并终止流
                            error_msg = json.dumps({
                                "error": f"输出内容违反安全策略: {result.reason}",
                                "guard": result.guard_name,
                            })
                            yield f"data: {error_msg}\n\n".encode("utf-8")
                            return
                        # 重置累积计数器，避免重复检查同一内容
                        check_interval += 20


def _extract_delta_text(chunk: bytes) -> str:
    """从 SSE chunk 中提取 delta 文本"""
    try:
        text = chunk.decode("utf-8").strip()
        if text.startswith("data: ") and text != "data: [DONE]":
            data = json.loads(text[6:])
            choices = data.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                return delta.get("content", "")
    except Exception:
        pass
    return ""