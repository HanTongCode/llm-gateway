"""
多租户鉴权中间件
----------------
功能：
1. 从请求头 Authorization: Bearer <API_KEY> 提取凭证
2. 查询 Redis 中的租户信息（tenant:{api_key}）
3. 验证 API Key 有效性、租户状态（active/disabled）
4. 将租户 ID、名称、允许的模型列表注入 request.state
5. 支持配置热加载：修改 Redis 即时生效，无需重启网关
"""
import redis.asyncio as redis
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# 配置模块
from app.core.config import settings


class TenantAuthMiddleware(BaseHTTPMiddleware):
    """
    多租户鉴权中间件
    - 只拦截聊天接口 /v1/chat/completions
    - 其他路径（/health、/metrics、/docs）直接放行
    """

    async def dispatch(self, request: Request, call_next):
        # ---- 1. 路径过滤：只对聊天接口鉴权 ----
        if request.url.path != "/v1/chat/completions":
            return await call_next(request)

        # ---- 2. 提取 API Key ----
        # 格式：Authorization: Bearer sk-xxx
        auth_header = request.headers.get("Authorization", "")
        api_key = auth_header.replace("Bearer ", "").strip()

        # 无 Key 直接返回 401
        if not api_key:
            return JSONResponse(
                {"error": "缺少 API Key，请在 Authorization 头中提供"},
                status_code=401,
            )

        # ---- 3. 从 Redis 加载租户配置 ----
        try:
            r = redis.from_url(settings.REDIS_URL, protocol=2)
            tenant_raw = await r.hgetall(f"tenant:{api_key}")
            await r.close()
        except Exception:
            return JSONResponse(
                {"error": "鉴权服务不可用"},
                status_code=500,
            )

        # Key 无效返回 403
        if not tenant_raw:
            return JSONResponse(
                {"error": "无效的 API Key"},
                status_code=403,
            )

        # ---- 4. 解析租户配置 ----
        def safe_decode(b: bytes) -> str:
            """兼容 Windows 终端 GBK 编码"""
            try:
                return b.decode("utf-8")
            except UnicodeDecodeError:
                return b.decode("gbk")

        tenant = {
            "id": safe_decode(tenant_raw.get(b"id", b"")),
            "name": safe_decode(tenant_raw.get(b"name", b"")),
            "allowed_models": (
                safe_decode(tenant_raw.get(b"allowed_models", b"*")).split(",")
            ),
            "status": safe_decode(tenant_raw.get(b"status", b"active")),
        }

        # ---- 5. 状态校验 ----
        if tenant["status"] != "active":
            return JSONResponse(
                {"error": "该租户已被禁用"},
                status_code=403,
            )

        # ---- 6. 注入到 request.state，下游模块直接使用 ----
        request.state.tenant = tenant
        request.state.api_key = api_key

        # ---- 7. 放行请求 ----
        return await call_next(request)