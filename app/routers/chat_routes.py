import json
import decimal
import asyncio
from typing import Optional, List
from fastapi import APIRouter, Request, Depends, HTTPException, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from pathlib import Path

from app.models import User, Conversation, Message, get_db
from app.auth import get_current_user
from app.config import (
    llm_client, MODEL_NAME, groq_client, 
    COST_PER_CHAT, MIN_BALANCE, MAX_MSG_LEN, logger
)
from app.rag import AVAILABLE_PERSONAS, search_quotes_for_persona
from app.tts import clean_text_for_speech, generate_minimax_audio

router = APIRouter(prefix="/api", tags=["Chat"])

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    conversation_id: int
    messages: List[ChatMessage]
    image_url:    Optional[str] = None
    image_base64: Optional[str] = None

@router.post("/chat", summary="流式对话（需鉴权，自动路由到会话对应角色）")
async def chat_endpoint(
    request: Request,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 1. 验证会话
    conv = db.query(Conversation).filter(
        Conversation.id == body.conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")

    # 2. 动态加载角色
    persona_id = conv.persona_id
    persona = AVAILABLE_PERSONAS.get(persona_id)
    if not persona:
        persona_id = "hu-chenfeng"
        persona = AVAILABLE_PERSONAS.get(persona_id, {})
        logger.warning(f"[chat] 角色 {conv.persona_id} 不存在，降级到 hu-chenfeng")

    # 3. 取最新用户消息
    last_user_msg = next(
        (m.content for m in reversed(body.messages) if m.role == "user"), ""
    )

    # 4. 字数限制
    if len(last_user_msg) > MAX_MSG_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"消息超过 {MAX_MSG_LEN} 字限制，请缩短后重试",
        )

    # 5. 余额检查
    db.refresh(current_user)
    if decimal.Decimal(str(current_user.balance)) < MIN_BALANCE:
        raise HTTPException(status_code=402, detail="余额不足，请充值后继续使用")

    # 6. RAG 检索
    quotes = search_quotes_for_persona(last_user_msg, persona_id) if last_user_msg else []
    quotes_text = "\n\n".join(
        [f"原文片段 {i+1}:\n{q['text']}" for i, q in enumerate(quotes)]
    )

    # 7. 系统提示词
    try:
        skill_content = Path(persona["skill_path"]).read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"[chat] 读取 SKILL.md 失败 {persona_id}: {e}")
        skill_content = f"你是 {persona.get('name', persona_id)} 的数字分身，请基于角色设定回答用户问题。"

    system_prompt = f"""{skill_content}

===== 检索到的语录参考 =====
在回答时，请参考以下相关原文片段（如果有助于回答的话）：

{quotes_text if quotes_text else "（无相关检索结果）"}
================================
"""

    llm_msgs = [{"role": "system", "content": system_prompt}] + [
        {"role": m.role, "content": m.content} for m in body.messages
    ]

    # 8. 定义流式生成器
    async def event_generator():
        full_reply = ""
        try:
            response = await llm_client.chat.completions.create(
                model=MODEL_NAME,
                messages=llm_msgs,
                stream=True,
            )
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_reply += content
                    yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
            
            # 结束后：扣费 + 存库 (注意：StreamingResponse 运行在不同上下文中，建议在这里使用新的 DB session 或处理事务)
            # 为了简单起见，这里直接使用依赖注入的 db，但需注意某些环境下可能需要 scope 管理
            db.add(Message(conversation_id=conv.id, role="user", content=last_user_msg))
            db.add(Message(conversation_id=conv.id, role="assistant", content=full_reply))
            db.query(User).filter(User.id == current_user.id).update({User.balance: User.balance - COST_PER_CHAT})
            db.commit()
            
        except Exception as e:
            logger.error(f"[chat] 流式输出异常: {e}")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/conversations/{conv_id}/chat", summary="多模态交互接口（支持语音输入及语音合成返回）")
async def voice_chat_endpoint(
    conv_id: int,
    text: Optional[str] = Form(None),
    audio_file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 1. 验证会话
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    persona_id = conv.persona_id
    user_text = text or ""

    # 2. ASR 转录
    if audio_file:
        try:
            audio_bytes = await audio_file.read()
            from io import BytesIO
            bio = BytesIO(audio_bytes)
            bio.name = "input.wav"
            
            transcription = groq_client.audio.transcriptions.create(
                file=bio,
                model="whisper-large-v3",
                response_format="text"
            )
            user_text = str(transcription).strip()
            logger.info(f"[ASR] 转录成功 uid:{current_user.id} -> {user_text}")
        except Exception as e:
            logger.error(f"[ASR] 语音转录失败: {e}")
            raise HTTPException(status_code=500, detail="语音转录失败，请重试")

    if not user_text:
        raise HTTPException(status_code=400, detail="内容不能为空")

    # 3. 余额检查
    db.refresh(current_user)
    if decimal.Decimal(str(current_user.balance)) < MIN_BALANCE:
        raise HTTPException(status_code=402, detail="余额不足")

    # 4. RAG + LLM
    quotes = search_quotes_for_persona(user_text, persona_id)
    quotes_text = "\n\n".join([f"原文片段 {i+1}:\n{q['text']}" for i, q in enumerate(quotes)])
    
    try:
        persona = AVAILABLE_PERSONAS.get(persona_id, {})
        skill_path = persona.get("skill_path")
        skill_content = Path(skill_path).read_text(encoding="utf-8") if skill_path else ""
    except:
        skill_content = ""

    system_prompt = f"{skill_content}\n\n参考语录:\n{quotes_text}"
    history_msgs = [{"role": m.role, "content": m.content} for m in conv.messages[-10:]]
    messages = [{"role": "system", "content": system_prompt}] + history_msgs + [{"role": "user", "content": user_text}]

    try:
        response = await llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            stream=False,
        )
        reply_text = response.choices[0].message.content
    except Exception as e:
        logger.error(f"[LLM] 生成回复失败: {e}")
        raise HTTPException(status_code=500, detail="AI 响应失败")

    # 5. TTS 合成
    clean_text = clean_text_for_speech(reply_text)
    audio_url = await generate_minimax_audio(clean_text, persona_id)

    # 6. 扣费与存库
    db.add(Message(conversation_id=conv.id, role="user", content=user_text))
    db.add(Message(conversation_id=conv.id, role="assistant", content=reply_text))
    db.query(User).filter(User.id == current_user.id).update({User.balance: User.balance - COST_PER_CHAT})
    db.commit()

    return {
        "user_text": user_text,
        "reply": reply_text,
        "audio_url": audio_url
    }
