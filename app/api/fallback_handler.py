from starlette.responses import JSONResponse

from app.services.routing.router import dispatch_to_model
import time as time_module


async def execute_with_fallback(body, ctx, model_router, input_pipeline, output_pipeline):
    candidates = model_router.get_ranked_candidates(
        required_capability="chat",
        messages=body.messages,
        preferred_model=body.model,
    )

    switched_from = None
    attempted = []

    for i, adapter in enumerate(candidates):
        if i == 0:
            switched_from = adapter.model_name
        attempted.append(adapter.model_name)

        model_router.health_tracker.get(adapter.provider, adapter.model_name).current_load += 1

        try:
            response = await dispatch_to_model(
                body.model_dump(), ctx,
                adapter=adapter,
                input_pipeline=input_pipeline,
                output_pipeline=output_pipeline,
            )
        except Exception as e:
            model_router.record_result(adapter.provider, adapter.model_name, False, 0)
            continue

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

    return JSONResponse({
        "error": "所有模型不可用，已尝试切换，请稍后重试",
        "attempted_models": attempted,
    }, status_code=503)