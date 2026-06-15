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
from app.core.config import settings
from app.core.audit_context import AuditContext
from app.services.compliance import RegisteredTemplateGuard

# ======================== 自定义异常 ========================

class OutputGuardViolation(Exception):
    """输出护栏违规异常，用于中断流式输出"""
    def __init__(self, reason: str):
        self.reason = reason


# ======================== 辅助函数 ========================

def extract_user_message(messages: list) -> str:
    """从 messages 列表中提取最后一条用户消息"""
    for msg in reversed(messages):
        # 兼容 Pydantic 对象和原始字典
        role = msg.role if hasattr(msg, "role") else msg.get("role", "")
        content = msg.content if hasattr(msg, "content") else msg.get("content", "")
        if role == "user":
            return content
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


async def _check_output(data: dict, pipeline):
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
    pipeline,
) -> str:
    """
    流式生成器：逐块转发 SSE 数据，同时增量执行输出护栏检查
    - 每累积 20 个字符触发一次护栏检查
    - 检测到违规时主动切断流，返回错误消息
    """
    accumulated = ""
    check_interval = 20

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers=headers) as resp:
            async for chunk in resp.content.iter_any():
                yield chunk

                text = _extract_delta_text(chunk)
                if text:
                    accumulated += text

                    if len(accumulated) >= check_interval:
                        result = await pipeline.run(accumulated)
                        if not result.passed:
                            error_msg = json.dumps({
                                "error": f"输出内容违反安全策略: {result.reason}",
                                "guard": result.guard_name,
                            })
                            yield f"data: {error_msg}\n\n".encode("utf-8")
                            return
                        check_interval += 20

# ---- System Prompt 模板校验（单独处理） ----
def _extract_first_system_message(messages: list) -> str | None:
    """从消息列表中提取第一条 System Prompt"""
    for msg in messages:
        if msg.get("role") == "system":
            return msg.get("content", "")
    return None

def _update_last_user_message(messages: list, new_content: str):
    """替换最后一条 user 消息的内容（用于脱敏后更新）"""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            msg["content"] = new_content
            break
# ======================== 核心转发函数 ========================

async def dispatch_to_model(
    body: dict,
    ctx: AuditContext,
    adapter=None,
    input_pipeline=None,
    output_pipeline=None,
):
    # 如果有适配器，用适配器的 base_url；否则走旧逻辑
    if adapter:
        base_url = adapter.base_url
        model = adapter.model_name
        # 覆盖请求体中的 model，确保发给后端的请求格式正确
        body["model"] = adapter.model_name
    else:
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
    system_msgs = _extract_first_system_message(body.get("messages", []))
    if system_msgs:
        template_guard = RegisteredTemplateGuard()
        guard_result = await template_guard.check(system_msgs)
        if not guard_result.passed:
            ctx.guard_triggered = guard_result.guard_name
            # 低风险策略：记录但不拦截，继续处理请求
    # ---- 构造转发请求 ----
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {adapter.api_key}",
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
            ctx.status_code = resp.status
            if resp.status != 200:
                ctx.error = data.get("error", {}).get("message", "unknown error")
                return JSONResponse(content=data, status_code=resp.status)
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