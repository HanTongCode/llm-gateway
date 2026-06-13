"""
聊天接口编排层
--------------
职责：只负责调度请求处理流程。不包含任何具体业务逻辑。
每个步骤都是一个独立的函数调用，函数实现分布在各自的模块中。
"""
from fastapi import APIRouter, Request
from app.models.chat import ChatRequest
from app.api.request_prepare import prepare_request
from app.api.cache_handler import try_fulfill_cache
from app.api.finalizer import finalize_request
from app.services.routing.router import dispatch_to_model

router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(body: ChatRequest, request: Request):
    """
    聊天补全接口
    编排顺序：准入 → 缓存 → 转发 → 收尾
    """
    # 1. 请求准入（审计上下文 + 权限 + 校验）
    ctx, error = prepare_request(request, body)
    if error:
        return error

    # 2. 缓存查询（命中则直接返回）
    response = await try_fulfill_cache(ctx, body)
    if response:
        return response

    # 3. 模型转发（护栏 + 路由 + 调用）
    response = await dispatch_to_model(body.model_dump(), request, ctx)

    # 4. 后置收尾（指标 + 缓存 + 审计）
    finalize_request(ctx, body, response)

    return response