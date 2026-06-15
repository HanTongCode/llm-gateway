"""
FastAPI 应用入口
----------------
组装中间件、路由，创建应用实例。
"""
from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import generate_latest, REGISTRY

# 中间件（注意添加顺序：后添加的先执行，所以先添加限流，后添加鉴权）
from app.middleware.ratelimit import RateLimitMiddleware
from app.middleware.authentication import TenantAuthMiddleware

# 路由
from app.api.v1 import chat
from app.api import admin

def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(title="FinTech LLM Gateway")

    # 注册中间件
    app.add_middleware(RateLimitMiddleware)      # 限流中间件（后执行）
    app.add_middleware(TenantAuthMiddleware)    # 鉴权中间件（先执行）

    # 注册路由
    app.include_router(chat.router)
    app.include_router(admin.router)
    # Prometheus 指标端点
    @app.get("/metrics")
    async def metrics():
        return Response(content=generate_latest(REGISTRY), media_type="text/plain")

    # 健康检查
    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "fintech-llm-gateway"}

    return app