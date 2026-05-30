from fastapi import FastAPI
from gateway.router import chat


def create_app() -> FastAPI:
    app = FastAPI(title="LLM Gateway")
    app.include_router(chat.router)
    return app