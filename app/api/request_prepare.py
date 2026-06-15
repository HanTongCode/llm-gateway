"""
请求准入层
----------
统一处理：
1. 审计上下文初始化
2. 模型权限校验（租户是否有权限使用该模型）
3. 请求体基础校验（消息数量、System Prompt 长度、参数范围）
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.audit_context import AuditContext
from app.models.chat import ChatRequest
from app.adapters.registry import registry


def prepare_request(request: Request, body: ChatRequest):
    """
    请求准入校验
    返回 (ctx, None) 表示通过，由编排层继续处理
    返回 (None, error_response) 表示拦截，直接返回错误
    """
    # ===== 1. 审计上下文初始化 =====
    ctx = AuditContext()
    ctx.ip_address = request.client.host if request.client else ""

    tenant = request.state.tenant
    ctx.tenant_id = tenant["id"]
    ctx.tenant_name = tenant["name"]
    ctx.api_key = request.state.api_key
    ctx.model = body.model
    ctx.stream = body.stream
    ctx.messages_length = sum(len(m.content) for m in body.messages)

    # ===== 2. 模型权限校验 =====
    error = _check_model_access(tenant, body.model)
    if error:
        ctx.status_code = error.status_code
        ctx.error = error.body.decode("utf-8")
        return None, error

    # ===== 3. 请求体校验 =====
    error = _validate_request_body(body)
    if error:
        return None, error

    return ctx, None


# ======================== 内部函数 ========================

def _check_model_access(tenant: dict, model: str) -> JSONResponse | None:
    """
    校验租户是否有权限使用指定模型
    - allowed_models 中包含 "*" 表示允许所有模型
    """
    if model is None:
        return None  # 未指定模型，跳过权限校验
        # 检查模型是否已注册
    try:
        registry.get_adapter_by_model(model)  # 需要一个按 model_name 查找的方法
    except KeyError:
        return JSONResponse(
            {"error": f"无效的模型: {model}"},
            status_code=400,
        )
    allowed = tenant.get("allowed_models", ["*"])
    if model not in allowed and "*" not in allowed:
        return JSONResponse(
            {"error": f"租户 {tenant['name']} 无权限使用模型 {model}"},
            status_code=403,
        )
    return None


def _validate_request_body(body: ChatRequest) -> JSONResponse | None:
    """请求体基础校验"""
    MAX_MESSAGES = 100            # 单次请求消息数上限（防滥用）
    MAX_SYSTEM_LENGTH = 4000      # System Prompt 最大字符数（防注入）

    # 消息数量校验
    if len(body.messages) > MAX_MESSAGES:
        return JSONResponse(
            {"error": f"消息数量超过上限（{MAX_MESSAGES}）"},
            status_code=400,
        )

    # System Prompt 长度校验
    for msg in body.messages:
        if msg.role == "system" and len(msg.content) > MAX_SYSTEM_LENGTH:
            return JSONResponse(
                {"error": f"System Prompt 长度超过上限（{MAX_SYSTEM_LENGTH}字符）"},
                status_code=400,
            )

    # temperature 范围校验
    if body.temperature is not None and not (0 <= body.temperature <= 2):
        return JSONResponse(
            {"error": "temperature 必须在 0-2 之间"},
            status_code=400,
        )

    return None