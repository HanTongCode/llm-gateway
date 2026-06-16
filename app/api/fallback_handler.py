"""
Fallback 处理器
---------------
- 显式指定模型：直接使用该模型，并发满时本地 FIFO 排队等待，不切换。
- 自动路由：按策略排序候选模型，遇并发满则跳过，失败则切换。
"""
import asyncio
import time as time_module
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse

from app.models.chat import ChatRequest
from app.services.routing.router import dispatch_to_model
from app.adapters.registry import registry

async def execute_with_fallback(
    body: ChatRequest,
    ctx,
    model_router,
    input_pipeline,
    output_pipeline,
):
    # ======================== 显式指定模型分支 ========================
    if body.model is not None:
        try:
            adapter = registry.get_adapter_by_model(body.model)
        except (RuntimeError, IndexError):
            return JSONResponse({"error": f"指定模型不可用: {body.model}"}, status_code=503)

        max_load = getattr(adapter, "max_concurrency", 10)

        # 1. 尝试直接获取 Redis 槽位
        acquired = await model_router.health_tracker.acquire_slot(
            adapter.provider, adapter.model_name, max_load
        )

        # 2. 槽位满 → 进入本地 FIFO 排队（阻塞等待，直到被唤醒）
        if not acquired:
            try:
                await model_router.health_tracker.wait_for_slot(
                    adapter.provider, adapter.model_name
                )
            except asyncio.CancelledError:
                # 客户端主动断开，返回错误
                return JSONResponse({"error": "请求已取消"}, status_code=499)

        # 3. 获取到槽位（直接获取或排队转交），调用模型
        try:
            response = await dispatch_to_model(
                body.model_dump(),
                ctx=ctx,
                adapter=adapter,
                input_pipeline=input_pipeline,
                output_pipeline=output_pipeline,
            )
        except Exception:
            model_router.record_result(adapter.provider, adapter.model_name, False, 0)
            await model_router.health_tracker.release_slot(
                adapter.provider, adapter.model_name
            )
            return JSONResponse({"error": "模型调用失败"}, status_code=502)

        latency = time_module.time() - ctx.start_time
        success = ctx.status_code == 200
        model_router.record_result(adapter.provider, adapter.model_name, success, latency)
        await model_router.health_tracker.release_slot(
            adapter.provider, adapter.model_name
        )
        # 如果是流式响应，直接返回，不检查 ctx.status_code
        if isinstance(response, StreamingResponse):
            return response
        return response if success else JSONResponse({"error": "模型返回错误"}, status_code=502)

    # ======================== 自动路由分支 ========================
    candidates = await model_router.get_ranked_candidates(
        required_capability="chat",
        messages=body.messages,
    )
    if not candidates:
        return JSONResponse({"error": "无可用模型"}, status_code=503)

    switched_from = None
    attempted = []

    for i, adapter in enumerate(candidates):
        if i == 0:
            switched_from = adapter.model_name
        attempted.append(adapter.model_name)

        # 抢占槽位（非阻塞）
        max_load = getattr(adapter, "max_concurrency", 10)
        acquired = await model_router.health_tracker.acquire_slot(
            adapter.provider, adapter.model_name, max_load
        )
        if not acquired:
            continue  # 槽位满，跳过

        try:
            response = await dispatch_to_model(
                body.model_dump(),
                ctx=ctx,
                adapter=adapter,
                input_pipeline=input_pipeline,
                output_pipeline=output_pipeline,
            )
            if isinstance(response, StreamingResponse):
                return response
            latency = time_module.time() - ctx.start_time
            success = ctx.status_code == 200
            model_router.record_result(adapter.provider, adapter.model_name, success, latency)

            if success:
                if i > 0 and switched_from:
                    if hasattr(response, "headers"):
                        response.headers["X-Model-Switched"] = "true"
                        response.headers["X-Original-Model"] = switched_from
                        response.headers["X-Actual-Model"] = adapter.model_name
                return response

        except Exception:
            model_router.record_result(adapter.provider, adapter.model_name, False, 0)
            continue
        finally:
            await model_router.health_tracker.release_slot(adapter.provider, adapter.model_name)

    return JSONResponse({
        "error": "所有模型不可用，已尝试切换，请稍后重试",
        "attempted_models": attempted,
    }, status_code=503)