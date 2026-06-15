"""
聊天接口编排层
--------------
职责：只负责调度请求处理流程。不包含任何具体业务逻辑。
每个步骤都是一个独立的函数调用，函数实现分布在各自的模块中。
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
import time as time_module

from app.api.fallback_handler import execute_with_fallback
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
# 初始化所有模型的健康度数据
for adapter in registry.get_all_adapters().values():
    model_router.health_tracker.get(adapter.provider, adapter.model_name)
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

    # 3. 模型调用（内部包含 Fallback 处理）
    response = await execute_with_fallback(
            body, ctx, model_router, input_pipeline, output_pipeline,
        )

    finalize_request(ctx, body, response)
    return response
