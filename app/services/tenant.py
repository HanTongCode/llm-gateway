"""租户权限校验"""
from fastapi import Request
from fastapi.responses import JSONResponse


def check_model_access(request: Request, model: str) -> JSONResponse | None:
    """校验租户是否有权限使用指定模型，返回 None 表示通过"""
    tenant = request.state.tenant
    allowed = tenant.get("allowed_models", ["*"])
    if model not in allowed and "*" not in allowed:
        return JSONResponse(
            {"error": f"租户 {tenant['name']} 无权限使用模型 {model}"},
            status_code=403,
        )
    return None