"""限流中间件"""
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from gateway.ratelimit.token_bucket import token_bucket
from gateway.metrics import rate_limit_hits
class RateLimitMiddleware(BaseHTTPMiddleware):
    """租户级别限流中间件"""
    # 默认限流参数
    DEFAULT_RATE = 10      # 每秒生成10个令牌
    DEFAULT_CAPACITY = 20  # 桶容量20，允许突发20个请求

    async def dispatch(self, request: Request, call_next):
        if request.url.path != "/v1/chat/completions":
            return await call_next(request)
        # 从鉴权中间件注入的租户信息获取 tenant_id
        tenant = getattr(request.state, "tenant", None)
        if tenant is None:
            # 没有租户信息（理论上鉴权中间件会处理），暂放行
            return await call_next(request)

        tenant_id = tenant["id"]
        key = f"rate:{tenant_id}"

        # 消耗令牌
        allowed = await token_bucket.consume(key, self.DEFAULT_RATE, self.DEFAULT_CAPACITY)
        if not allowed:
            # 记录限流指标
            rate_limit_hits.labels(tenant=tenant_id).inc()
            return JSONResponse(
                {"error": "请求过于频繁，请稍后再试", "retry_after": "1"},
                status_code=429,
            )

        return await call_next(request)