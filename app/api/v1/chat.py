"""
聊天接口路由
------------
网关的核心 API 端点：POST /v1/chat/completions
负责：
1. 接收 OpenAI 兼容格式的请求
2. 模型权限校验（租户是否允许使用该模型）
3. 语义缓存查询/写入（非流式请求）
4. 调用转发调度器（dispatcher）执行护栏检查 + 模型转发
5. 记录审计日志和 Prometheus 指标
"""
import json
import asyncio
import time as time_module
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

# ---- 已迁移的新路径模块 ----
from app.services.routing.router import dispatch_to_model
from app.services.tenant import check_model_access
from app.services.resilience.cache import semantic_cache
from app.core.audit_logger import audit_logger
from app.core.audit_context import AuditContext
from app.core.metrics import (
    request_total,
    request_duration,
    tokens_total,
    guard_blocks_total,
    rate_limit_hits,
)

router = APIRouter()


# ======================== 请求体模型定义 ========================

class Message(BaseModel):
    """单条消息"""
    role: str      # user / assistant / system
    content: str   # 消息内容


class ChatRequest(BaseModel):
    """聊天请求体（兼容 OpenAI 格式）"""
    model: str = "deepseek-chat"                       # 模型名
    messages: List[Message]                            # 对话历史
    stream: Optional[bool] = False                     # 是否流式输出
    cache_bypass: Optional[bool] = False               # 是否绕过缓存（审查重试时使用）


# ======================== 流式模拟生成器 ========================

async def simulate_cache_stream(content: str, chunk_size: int = 2):
    """
    将缓存文本模拟为 SSE 流式输出（逐字符推送，打字机效果）
    用于缓存命中时保持前端流式渲染体验
    """
    model_id = "cache-hit"
    for i in range(0, len(content), chunk_size):
        chunk_text = content[i:i + chunk_size]
        chunk = {
            "id": model_id,
            "object": "chat.completion.chunk",
            "created": int(time_module.time()),
            "model": "cache",
            "choices": [{
                "index": 0,
                "delta": {"content": chunk_text},
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.02)  # 模拟流式延迟

    yield "data: [DONE]\n\n"


# ======================== 核心接口 ========================

@router.post("/v1/chat/completions")
async def chat_completions(body: ChatRequest, request: Request):
    """
    聊天补全接口
    - 鉴权：由 TenantAuthMiddleware 处理，租户信息在 request.state.tenant 中
    - 限流：由 RateLimitMiddleware 处理
    - 护栏 + 转发：由 dispatch_to_model 处理
    - 缓存：由 semantic_cache 处理
    """
    # ======================== 审计上下文初始化 ========================
    ctx = AuditContext()
    ctx.ip_address = request.client.host if request.client else ""
    tenant = request.state.tenant
    ctx.tenant_id = tenant["id"]
    ctx.tenant_name = tenant["name"]
    ctx.api_key = request.state.api_key
    ctx.model = body.model
    ctx.stream = body.stream
    ctx.messages_length = sum(len(m.content) for m in body.messages)

    # ======================== 模型权限校验 ========================
    access_error = check_model_access(request, body.model)
    if access_error:
        ctx.status_code = access_error.status_code
        ctx.error = access_error.body.decode("utf-8")
        asyncio.create_task(audit_logger.log(ctx.to_dict()))
        return access_error

    # ======================== 语义缓存查询 ========================
    user_msg = body.messages[-1].content
    cached = None
    if not body.cache_bypass:
        cached = await semantic_cache.get(user_msg)

    # ---- 缓存命中 ----
    if cached:
        ctx.status_code = 200
        ctx.tokens_prompt = 0
        ctx.tokens_completion = 0
        ctx.tokens_total = 0
        asyncio.create_task(audit_logger.log(ctx.to_dict()))

        if body.stream:
            # 缓存命中 + 流式请求：模拟 SSE 打字机效果
            return StreamingResponse(
                simulate_cache_stream(cached["content"]),
                media_type="text/event-stream",
            )
        else:
            # 缓存命中 + 非流式请求：直接返回 JSON
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

    # ======================== 缓存未命中，调用模型 ========================
    response = await dispatch_to_model(body.model_dump(), request, ctx)

    # ======================== Prometheus 指标记录 ========================
    status_code = ctx.status_code
    request_total.labels(
        tenant=ctx.tenant_id,
        model=ctx.model,
        status_code=str(status_code)
    ).inc()

    # 请求延迟
    latency_s = time_module.time() - ctx.start_time
    request_duration.labels(
        tenant=ctx.tenant_id,
        model=ctx.model
    ).observe(latency_s)

    # Token 用量（仅成功时）
    if status_code == 200:
        tokens_total.labels(
            tenant=ctx.tenant_id, model=ctx.model, type="prompt"
        ).inc(ctx.tokens_prompt)
        tokens_total.labels(
            tenant=ctx.tenant_id, model=ctx.model, type="completion"
        ).inc(ctx.tokens_completion)
        tokens_total.labels(
            tenant=ctx.tenant_id, model=ctx.model, type="total"
        ).inc(ctx.tokens_total)

    # 护栏拦截
    if ctx.guard_triggered:
        guard_blocks_total.labels(guard_name=ctx.guard_triggered).inc()

    # 限流拦截
    if status_code == 429:
        rate_limit_hits.labels(tenant=ctx.tenant_id).inc()

    # ======================== 非流式缓存写入 ========================
    if not body.stream and status_code == 200:
        try:
            content = json.loads(response.body.decode("utf-8"))
            reply = content["choices"][0]["message"]["content"]
            # 异步写入，不阻塞响应
            asyncio.create_task(semantic_cache.set(user_msg, reply))
        except (json.JSONDecodeError, KeyError, AttributeError):
            pass  # 缓存写入失败不影响主流程

    # ======================== 异步记录审计日志 ========================
    asyncio.create_task(audit_logger.log(ctx.to_dict()))

    return response