"""多租户鉴权中间件"""
import traceback

import redis.asyncio as redis
from fastapi import Request
from fastapi.responses import JSONResponse
from pip._internal.cli import status_codes
from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware
from config import settings

def safe_decode(b: bytes) -> str:
    """兼容 Windows 终端 GBK 编码"""
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("gbk")

class TenantAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path != "/v1/chat/completions":
            return await call_next(request)
        # 1.从请求头中获取api_key
        auth_header = request.headers.get("Authorization","")
        api_key = auth_header.replace("Bearer ", "").strip()
        if not api_key:
            return JSONResponse(
                {'error':"缺少API_KEY，请在 Authorization 头中提供"},
                status_code=401)
        # 2.连接redis，查询租户信息
        try:
            r=redis.from_url(settings.REDIS_URL, protocol=2)
            tenant_raw = await r.hgetall(f"tenant:{api_key}")
            await r.close()
        except Exception as e:
            traceback.print_exc()
            return JSONResponse(
                {'error':"鉴权服务不可用"},
                 status_code=500
            )
        if not tenant_raw:
            return JSONResponse(
                {"error":'无效的API_KEY'},
                status_code=401
            )
        # 解析租户配置
        tenant = {
            "id": safe_decode(tenant_raw.get(b"id", b"")),
            "name": safe_decode(tenant_raw.get(b"name", b"")),
            "allowed_models": (
                safe_decode(tenant_raw.get(b"allowed_models", b"*")).split(",")
            ),
            "status": safe_decode(tenant_raw.get(b"status", b"active")),
        }
        # 4. 检查租户状态
        if tenant["status"] != "active":
            return JSONResponse(
                {"error":"该租户被禁用"},
                status_code=403
            )
        # 5.将租户信息注入请求上下文，供下游使用
        request.state.tenant = tenant
        request.state.api_key = api_key
        # 放行
        return await call_next(request)




