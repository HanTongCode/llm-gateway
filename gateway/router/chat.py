from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from gateway.proxy.dispatcher import dispatch_to_model
from gateway.tenant.service import check_model_access

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
async def chat_completions(body: ChatRequest,request: Request):
    # 模型权限校验
    access_error = check_model_access(request,body.model)
    if access_error:
        return access_error
    return await dispatch_to_model(body.model_dump())
