"""
聊天接口编排层
--------------
职责：只负责调度请求处理流程。不包含任何具体业务逻辑。
每个步骤都是一个独立的函数调用，函数实现分布在各自的模块中。
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
import time as time_module
from app.models.chat import ChatRequest
from app.api.request_prepare import prepare_request
from app.api.cache_handler import try_fulfill_cache
from app.api.finalizer import finalize_request
from app.services.routing.router import dispatch_to_model
from app.services.routing import ModelRouter, RoutingStrategy
from app.adapters.registry import registry
from app.core.config import settings
# 护栏管道初始化
from app.services.compliance import (
    GuardPipeline,
    PromptInjectionGuard,
    SensitiveWordGuard,
    DataBoundaryGuard,
    OutputSensitiveGuard,
    SystemPromptLeakGuard,
    FinancialComplianceGuard,
)

input_pipeline = GuardPipeline([
    PromptInjectionGuard(),
    SensitiveWordGuard(),
    DataBoundaryGuard(),
])

output_pipeline = GuardPipeline([
    OutputSensitiveGuard(),
    SystemPromptLeakGuard(),
    FinancialComplianceGuard(),
])

router = APIRouter()
# 自动发现并加载所有适配器（必须在 model_router 初始化之前执行）
registry.load_from_config(settings.REGISTERED_MODELS)
# 模型路由器（选择最优大模型）
model_router = ModelRouter(strategy=RoutingStrategy.COST_FIRST)

@router.post("/v1/chat/completions")
async def chat_completions(body: ChatRequest, request: Request):
    """

    聊天补全接口：准入 → 缓存 → 路由选模型 → 转发 → 收尾
    """
    # 1. 请求准入（审计上下文 + 权限 + 校验）
    ctx, error = prepare_request(request, body)
    if error:
        return error

    # 2. 缓存查询（命中则直接返回）
    response = await try_fulfill_cache(ctx, body)
    if response:
        return response

    # 3. 路由引擎选择最优模型
    try:
        adapter = model_router.select_model(
            required_capability="chat",
             messages=body.messages,
            preferred_model=body.model,  # 客户端指定时优先，为None时自动选择
        )
    except RuntimeError as e:
        return JSONResponse(
            {"error": f"无可用模型: {str(e)}"},
            status_code=503,
        )

    # 4. 模型转发（护栏 + 路由 + 调用）
    response = await dispatch_to_model(
        body.model_dump(), request, ctx,
        adapter=adapter,
        input_pipeline=input_pipeline,
        output_pipeline=output_pipeline  # 传入管道
    )
    # 5. 记录路由结果
    model_router.record_result(
        provider=adapter.provider,
        model_name=adapter.model_name,
        success=ctx.status_code == 200,
        latency=time_module.time() - ctx.start_time,
    )

    # 6. 后置收尾（指标 + 缓存 + 审计）
    finalize_request(ctx, body, response)

    return response