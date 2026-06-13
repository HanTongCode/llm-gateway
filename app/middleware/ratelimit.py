"""
限流中间件
----------
功能：
1. 基于令牌桶算法，对每个租户的 API 调用进行频率限制
2. 使用 Redis + Lua 保证高并发下的原子性
3. 限流时返回 HTTP 429 Too Many Requests
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# 令牌桶实例
from app.services.resilience.token_bucket import token_bucket


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    租户级别限流中间件
    - 只拦截聊天接口，其他路径放行
    - 通过 request.state.tenant 获取租户信息（由鉴权中间件注入）
    """

    # 默认限流参数（后续可改为从 Redis 租户配置中动态读取）
    DEFAULT_RATE = 10       # 每秒生成 10 个令牌
    DEFAULT_CAPACITY = 20   # 桶容量 20，允许短时突发 20 个请求

    async def dispatch(self, request: Request, call_next):
        # ---- 1. 路径过滤 ----
        if request.url.path != "/v1/chat/completions":
            return await call_next(request)

        # ---- 2. 获取租户信息 ----
        tenant = getattr(request.state, "tenant", None)
        if tenant is None:
            # 理论上鉴权中间件会处理，这里兜底放行
            return await call_next(request)

        tenant_id = tenant["id"]
        key = f"rate:{tenant_id}"
        # ---- 3. 消耗令牌 ----
        allowed = await token_bucket.consume(
            key,
            self.DEFAULT_RATE,
            self.DEFAULT_CAPACITY
        )

        # ---- 4. 令牌不足，返回 429 ----
        if not allowed:
            return JSONResponse(
                {"error": "请求过于频繁，请稍后再试"},
                status_code=429,
            )
        # ---- 5. 令牌充足，放行 ----
        return await call_next(request)