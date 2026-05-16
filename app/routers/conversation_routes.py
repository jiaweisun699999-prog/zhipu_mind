from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List

from app.models import User, Conversation, Message, get_db
from app.auth import get_current_user
from app.rag import AVAILABLE_PERSONAS, get_persona_or_404

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])

class ConversationCreate(BaseModel):
    title:      str = Field(default="新对话", max_length=255)
    persona_id: str = Field(default="hu-chenfeng", max_length=64)

@router.get("", summary="获取当前用户的历史会话列表")
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convs = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.created_at.desc())
        .all()
    )
    return [
        {
            "id":         c.id,
            "title":      c.title,
            "persona_id": c.persona_id,
            "persona_name": AVAILABLE_PERSONAS.get(c.persona_id, {}).get("name", c.persona_id),
            "created_at": c.created_at.isoformat(),
        }
        for c in convs
    ]

@router.post("", summary="创建新会话（指定角色）", status_code=201)
def create_conversation(
    body: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 校验角色是否存在
    get_persona_or_404(body.persona_id)

    conv = Conversation(
        user_id=current_user.id,
        title=body.title,
        persona_id=body.persona_id,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {
        "id":         conv.id,
        "title":      conv.title,
        "persona_id": conv.persona_id,
        "persona_name": AVAILABLE_PERSONAS.get(conv.persona_id, {}).get("name", conv.persona_id),
        "created_at": conv.created_at.isoformat(),
    }

@router.get("/{conv_id}/messages", summary="获取某会话的历史消息")
def get_messages(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    return [
        {
            "id":         m.id,
            "role":       m.role,
            "content":    m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in conv.messages
    ]

@router.delete("/{conv_id}", summary="删除某个会话及其全部消息")
def delete_conversation(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.delete(conv)
    db.commit()
    return {"message": "已删除"}
