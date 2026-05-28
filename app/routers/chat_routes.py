import json
import decimal
import asyncio
import traceback
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from pathlib import Path

from app.models import User, Conversation, Message, get_db
from app.auth import get_current_user
from app.config import (
    llm_client, MODEL_NAME, 
    COST_TEXT_CHAT, COST_VOICE_CHAT, MIN_BALANCE, MAX_MSG_LEN, logger
)
from app.rag import AVAILABLE_PERSONAS, search_quotes_for_persona
from app.tts import clean_text_for_speech, generate_volcano_audio

router = APIRouter(prefix="/api", tags=["Chat"])

class ChatRequest(BaseModel):
    text: str
    voice_mode: bool = False

@router.post("/conversations/{conv_id}/chat", summary="流式对话接口：支持文字输入与条件语音播报")
async def chat_endpoint(
    conv_id: int,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    流式响应文本，并在结束时（如果开启语音模式）返回音频 URL。
    """
    # 1. 验证会话
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    persona_id = conv.persona_id
    user_text = body.text.strip()
    voice_mode = body.voice_mode

    # 2. 计算本次对话的实际价格并检查余额
    actual_cost = COST_VOICE_CHAT if voice_mode else COST_TEXT_CHAT
    db.refresh(current_user)
    if decimal.Decimal(str(current_user.balance)) < actual_cost:
        raise HTTPException(status_code=402, detail=f"余额不足 (本次对话需要 {actual_cost} 元)")

    async def event_generator():
        full_reply = ""
        try:
            # RAG 与 Prompt 构建
            quotes = search_quotes_for_persona(user_text, persona_id)
            quotes_text = "\n\n".join([f"参考语录 {i+1}:\n{q['text']}" for i, q in enumerate(quotes)])
            
            persona = AVAILABLE_PERSONAS.get(persona_id, {})
            skill_path = persona.get("skill_path")
            skill_content = Path(skill_path).read_text(encoding="utf-8") if skill_path else ""
            system_prompt = f"{skill_content}\n\n===== 参考语录 =====\n{quotes_text}"
            
            if voice_mode:
                system_prompt += "\n\n【系统重要指令：当前用户正在使用语音模式进行交互。为了保证语音播报的体验并控制成本，你的回复必须极度简短、口语化！像发微信语音一样，每次回复绝对不要超过 50 个字！能一句话说清楚就一句话说完，严禁长篇大论！】"
            
            history_msgs = [{"role": m.role, "content": m.content} for m in conv.messages[-10:]]
            messages = [{"role": "system", "content": system_prompt}] + history_msgs + [{"role": "user", "content": user_text}]

            # 调用 LLM 流式输出
            response = await llm_client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                stream=True,
            )

            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    full_reply += content
                    yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"

            # 结束后：TTS 合成 (如果开启了语音模式)
            audio_url = None
            if voice_mode:
                clean_text = clean_text_for_speech(full_reply)
                audio_url = await generate_volcano_audio(clean_text, persona_id)
                if audio_url:
                    yield f"data: {json.dumps({'audio_url': audio_url}, ensure_ascii=False)}\n\n"

            # 存库与扣费
            db.add(Message(conversation_id=conv.id, role="user", content=user_text))
            db.add(Message(conversation_id=conv.id, role="assistant", content=full_reply, audio_url=audio_url))
            db.query(User).filter(User.id == current_user.id).update({
                User.balance: User.balance - actual_cost
            })
            db.commit()
            
            # [新增] 完整记录聊天日志，包含用户名
            logger.info(f"[Chat Record] User: {current_user.username} (ID: {current_user.id}) | Persona: {persona_id} | Question: {user_text} | AI Reply: {full_reply}")

        except Exception as e:
            logger.error(f"[Chat] 流式异常 (User: {current_user.username}): {e}\n{traceback.format_exc()}")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
