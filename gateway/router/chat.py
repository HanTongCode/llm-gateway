from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from gateway.proxy.dispatcher import dispatch_to_model

router = APIRouter()
class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "deepseek-chat"
    messages: List[Message]
    stream: Optional[bool] = False

@router.get("/")
async def index(request: Request):
    return {'msg': 'Hello World'}

@router.post("/v1/chat/completions")
async def chat_completions(body: ChatRequest):
    return await dispatch_to_model(body.model_dump())
