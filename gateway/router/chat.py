import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from gateway.proxy.dispatcher import dispatch_to_model
from gateway.tenant.service import check_model_access
from gateway.audit.context import AuditContext
from gateway.audit.logger import audit_logger

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

    # 记录状态码（根据响应类型处理）
    if hasattr(response, "status_code"):
        ctx.status_code = response.status_code
    else:
        ctx.status_code = 200  # 流式可能没直接状态码

     # 异步记录日志
    asyncio.create_task(audit_logger.log(ctx.to_dict()))
    return response
