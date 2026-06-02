import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from gateway.proxy.dispatcher import dispatch_to_model
from gateway.tenant.service import check_model_access
from gateway.audit.context import AuditContext
from gateway.audit.logger import audit_logger
from gateway.metrics import (
    request_total,
    request_duration,
    tokens_total,
    guard_blocks_total,
    rate_limit_hits,
)
import time as time_module  # 避免与 datetime 冲突，如果已引入 time 则直接用 time.time()
router = APIRouter()
class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "deepseek-chat"
    messages: List[Message]
    stream: Optional[bool] = False

@router.get("/")
async def index(request: Request):
    return {'msg': 'Hello World'}

@router.post("/v1/chat/completions")
async def chat_completions(body: ChatRequest,request: Request):
    # 初始化审计上下文
    ctx = AuditContext()
    ctx.ip_address = request.client.host if request.client else ""
    tenant = request.state.tenant
    ctx.tenant_id = tenant["id"]
    ctx.tenant_name = tenant["name"]
    ctx.api_key = request.state.api_key
    ctx.model = body.model
    ctx.stream = body.stream
    ctx.messages_length = sum(len(m.content) for m in body.messages)
    # 模型权限校验
    access_error = check_model_access(request,body.model)
    if access_error:
        ctx.status_code = access_error.status_code
        ctx.error = access_error.body.decode("utf-8")
        asyncio.create_task(audit_logger.log(ctx.to_dict()))
        return access_error
     # 调用分发（内部已包含护栏）
    response = await dispatch_to_model(body.model_dump(), request, ctx)

    # 记录指标
    status_code = ctx.status_code
    request_total.labels(
        tenant=ctx.tenant_id or "unknown",
        model=ctx.model,
        status_code=str(status_code)
    ).inc()
    # 延迟
    latency_s = (time_module.time() - ctx.start_time)
    request_duration.labels(
        tenant=ctx.tenant_id or "unknown",
        model=ctx.model
    ).observe(latency_s)

    # Token 用量（仅成功时）
    if status_code == 200:
        tokens_total.labels(
            tenant=ctx.tenant_id or "unknown",
            model=ctx.model,
            type="prompt"
        ).inc(ctx.tokens_prompt)
        tokens_total.labels(
            tenant=ctx.tenant_id or "unknown",
            model=ctx.model,
            type="completion"
        ).inc(ctx.tokens_completion)
        tokens_total.labels(
            tenant=ctx.tenant_id or "unknown",
            model=ctx.model,
            type="total"
        ).inc(ctx.tokens_total)

    # 护栏拦截
    if ctx.guard_triggered:
        guard_blocks_total.labels(guard_name=ctx.guard_triggered).inc()

    # 限流拦截（在限流中间件中会触发，但我们在此也可以根据错误信息判断，
    # 不过更准确的是在限流中间件中计数，这里先在路由中根据状态码429记录）
    if status_code == 429:
        rate_limit_hits.labels(tenant=ctx.tenant_id or "unknown").inc()

     # 异步记录日志
    asyncio.create_task(audit_logger.log(ctx.to_dict()))
    return response
