from fastapi import FastAPI
from fastapi.responses import Response
from gateway.router import chat
from gateway.middleware.auth import TenantAuthMiddleware
from gateway.middleware.ratelimit import RateLimitMiddleware
from prometheus_client import generate_latest, REGISTRY

def create_app() -> FastAPI:
    app = FastAPI(title="LLM Gateway")
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(TenantAuthMiddleware)
    app.include_router(chat.router)

    @app.get("/metrics")
    async def metrics():
        return Response(content=generate_latest(REGISTRY), media_type="text/plain")

    return app