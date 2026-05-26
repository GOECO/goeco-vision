from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services import ai_agent

router = APIRouter(prefix="/agent", tags=["ai-agent"])


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class ChatResponse(BaseModel):
    reply: str
    history: list[dict]
    role: str
    user: str


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Gửi tin nhắn đến AI Agent GOECO.
    Agent tự động chọn system prompt và tools phù hợp với role của user.

    Ví dụ:
    - Cư dân: "Đơn hàng GOECO-2024-001 của tôi đang ở đâu?"
    - Ban quản lý: "Tổng quan vận hành hôm nay tòa PARK-HILL-A?"
    - Shipper: "Kệ tầng 1 còn chỗ không?"
    """
    messages = list(payload.history)
    messages.append({"role": "user", "content": payload.message})

    reply, updated_history = await ai_agent.chat(current_user, messages, db)

    return ChatResponse(
        reply=reply,
        history=updated_history,
        role=current_user.role.value,
        user=current_user.full_name,
    )
