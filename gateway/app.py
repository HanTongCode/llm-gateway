from fastapi import FastAPI
from gateway.router import chat
from gateway.middleware.auth import TenantAuthMiddleware
from gateway.middleware.ratelimit import RateLimitMiddleware
def create_app() -> FastAPI:
    app = FastAPI(title="LLM Gateway")
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(TenantAuthMiddleware)
    app.include_router(chat.router)
    return app