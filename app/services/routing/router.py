"""
模型转发与路由服务
------------------
核心职责：
1. 输入安全护栏检查（在请求转发前拦截违规输入）
2. 多模型路由：根据 model 参数选择后端 API 地址
3. 流式/非流式透传：SSE 流逐块转发，JSON 响应完整解析
4. 输出安全护栏检查（含流式增量检查）
5. Token 用量提取（非流式从响应体解析，流式从 SSE 末尾 chunk 提取）
6. 审计上下文填充（状态码、Token 数、护栏触发信息等）
"""
import json
import aiohttp
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

# ---- 已迁移的新路径模块 ----
from app.core.config import settings
from app.services.compliance import (
    GuardPipeline,
    PromptInjectionGuard,
    SensitiveWordGuard,
    DataLeakGuard,
)
from app.services.compliance.output_guards import OutputSensitiveGuard, SystemPromptLeakGuard
from app.services.resilience.cache import semantic_cache
from app.core.audit_context import AuditContext

# ======================== 护栏管道初始化 ========================

# 输入护栏：在请求转发到模型之前执行
input_pipeline = GuardPipeline([
    PromptInjectionGuard(),    # 检测提示注入攻击
    SensitiveWordGuard(),      # 过滤敏感词汇
    DataLeakGuard(),           # 拦截手机号、身份证等敏感信息
])

# 输出护栏：在模型响应返回给客户端之前执行
output_pipeline = GuardPipeline([
    OutputSensitiveGuard(),    # 检查生成内容是否违规
    SystemPromptLeakGuard(),   # 检测是否泄露了系统提示词
])


# ======================== 自定义异常 ========================

class OutputGuardViolation(Exception):
    """输出护栏违规异常，用于中断流式输出"""
    def __init__(self, reason: str):
        self.reason = reason


# ======================== 辅助函数 ========================

def extract_user_message(messages: list) -> str:
    """从 messages 列表中提取最后一条用户消息"""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


def _extract_delta_text(chunk: bytes) -> str:
    """
    从 SSE chunk 中提取 delta 文本
    SSE 格式：data: {"choices":[{"delta":{"content":"xxx"}}]}\n\n
    """
    try:
        text = chunk.decode("utf-8").strip()
        if text.startswith("data: ") and text != "data: [DONE]":
            data = json.loads(text[6:])
            delta = data.get("choices", [{}])[0].get("delta", {})
            return delta.get("content", "")
    except Exception:
        pass
    return ""


async def _check_output(data: dict, pipeline: GuardPipeline):
    """
    检查非流式响应的输出内容
    违规时抛出 OutputGuardViolation 异常
    """
    choices = data.get("choices", [])
    for choice in choices:
        content = choice.get("message", {}).get("content", "")
        if content:
            result = await pipeline.run(content)
            if not result.passed:
                raise OutputGuardViolation(result.reason)


# ======================== 流式输出增量护栏 ========================

async def _stream_and_guard(
    url: str,
    headers: dict,
    body: dict,
    pipeline: GuardPipeline,
) -> str:
    """
    流式生成器：逐块转发 SSE 数据，同时增量执行输出护栏检查
    - 每累积 20 个字符触发一次护栏检查
    - 检测到违规时主动切断流，返回错误消息
    """
    accumulated = ""
    check_interval = 20  # 每累积 20 字符检查一次

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers=headers) as resp:
            async for chunk in resp.content.iter_any():
                yield chunk

                # 提取本次 chunk 中的文本增量
                text = _extract_delta_text(chunk)
                if text:
                    accumulated += text

                    # 满 check_interval 字符时触发护栏检查
                    if len(accumulated) >= check_interval:
                        result = await pipeline.run(accumulated)
                        if not result.passed:
                            # 违规：生成错误消息并终止流
                            error_msg = json.dumps({
                                "error": f"输出内容违反安全策略: {result.reason}",
                                "guard": result.guard_name,
                            })
                            yield f"data: {error_msg}\n\n".encode("utf-8")
                            return
                        # 增加检查间隔，避免对同一内容重复检查
                        check_interval += 20


# ======================== 核心转发函数 ========================

async def dispatch_to_model(body: dict, request: Request, ctx: AuditContext):
    """
    将请求转发到对应的模型后端，执行完整的护栏流程。

    Args:
        body: 客户端请求体
        request: FastAPI Request 对象
        ctx: 审计上下文，用于填充状态码、Token 等信息

    Returns:
        JSONResponse（非流式）或 StreamingResponse（流式）
    """
    model = body.get("model", "deepseek-chat")
    base_url = settings.MODEL_ROUTES.get(model)

    # ---- 模型路由校验 ----
    if not base_url:
        ctx.status_code = 400
        ctx.error = f"不支持的模型: {model}"
        return JSONResponse(content={"error": ctx.error}, status_code=400)

    # ---- 输入护栏检查 ----
    user_msg = extract_user_message(body.get("messages", []))
    if user_msg:
        guard_result = await input_pipeline.run(user_msg)
        if not guard_result.passed:
            ctx.status_code = 422
            ctx.error = guard_result.reason
            ctx.guard_triggered = guard_result.guard_name
            return JSONResponse(
                content={
                    "error": f"输入违反安全策略: {guard_result.reason}",
                    "guard": guard_result.guard_name,
                },
                status_code=422,
            )

    # ---- 构造转发请求 ----
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    # ---- 流式请求 ----
    if body.get("stream"):
        return StreamingResponse(
            _stream_and_guard(url, headers, body, output_pipeline),
            media_type="text/event-stream",
        )

    # ---- 非流式请求 ----
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers=headers) as resp:
            data = await resp.json()

    # ---- 输出护栏检查 ----
    try:
        await _check_output(data, output_pipeline)
    except OutputGuardViolation as e:
        ctx.status_code = 422
        ctx.error = e.reason
        ctx.guard_triggered = "output"
        return JSONResponse(
            content={"error": f"输出违反安全策略: {e.reason}"},
            status_code=422,
        )

    # ---- 提取 Token 用量 ----
    usage = data.get("usage", {})
    ctx.tokens_prompt = usage.get("prompt_tokens", 0)
    ctx.tokens_completion = usage.get("completion_tokens", 0)
    ctx.tokens_total = usage.get("total_tokens", 0)
    ctx.status_code = 200

    return JSONResponse(content=data)