"""
身份识别中间件
--------------
从请求头提取 API Key，通过本地缓存 + Redis 验证租户身份。
本地缓存默认 30 秒过期，过期后自动从 Redis 刷新。
首次请求时懒加载所有租户配置到本地内存，后续请求直接读缓存。
"""
import time
import asyncio
import redis.asyncio as redis
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings

# ======================== 本地缓存 ========================
# 结构：{api_key: {"data": {...}, "expire_at": 1234567890.0}}
_tenant_cache: dict[str, dict] = {}
_cache_lock = asyncio.Lock()
CACHE_TTL = 30  # 缓存过期时间（秒）


class TenantAuthMiddleware(BaseHTTPMiddleware):
    """API Key 身份识别中间件"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path != "/v1/chat/completions":
            return await call_next(request)

        # ---- 1. 提取 API Key ----
        auth_header = request.headers.get("Authorization", "")
        api_key = auth_header.replace("Bearer ", "").strip()
        if not api_key:
            return JSONResponse({"error": "缺少 API Key"}, status_code=401)

        # ---- 2. 查询租户信息（优先本地缓存） ----
        tenant = await _get_tenant(api_key)
        if not tenant:
            return JSONResponse({"error": "无效的 API Key"}, status_code=403)

        if tenant["status"] != "active":
            return JSONResponse({"error": "租户已禁用"}, status_code=403)

        # ---- 3. 注入到 request.state ----
        request.state.tenant = tenant
        request.state.api_key = api_key
        return await call_next(request)


async def _get_tenant(api_key: str) -> dict | None:
    """
    获取租户信息，优先从本地缓存读取。
    缓存未命中或过期时，从 Redis 加载并更新缓存。
    """
    now = time.time()

    # ---- 命中缓存且未过期 → 直接返回 ----
    cached = _tenant_cache.get(api_key)
    if cached and cached["expire_at"] > now:
        return cached["data"]

    # ---- 缓存未命中或过期 → 加锁后从 Redis 加载 ----
    async with _cache_lock:
        # 双重检查：可能前一个请求已经刷新了缓存
        cached = _tenant_cache.get(api_key)
        if cached and cached["expire_at"] > now:
            return cached["data"]

        # 从 Redis 加载
        try:
            r = redis.from_url(settings.REDIS_URL, protocol=2)
            tenant_raw = await r.hgetall(f"tenant:{api_key}")
            await r.close()
        except Exception:
            # Redis 不可用时，如果缓存存在（即使过期）也先顶着用
            if cached:
                return cached["data"]
            return None

        if not tenant_raw:
            return None

        tenant = {
            "id": _safe_decode(tenant_raw.get(b"id", b"")),
            "name": _safe_decode(tenant_raw.get(b"name", b"")),
            "allowed_models": _safe_decode(
                tenant_raw.get(b"allowed_models", b"*")
            ).split(","),
            "status": _safe_decode(tenant_raw.get(b"status", b"active")),
        }

        # 更新本地缓存
        _tenant_cache[api_key] = {
            "data": tenant,
            "expire_at": now + CACHE_TTL,
        }

        return tenant


def _safe_decode(b: bytes) -> str:
    """兼容 Windows 终端 GBK 编码"""
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("gbk")