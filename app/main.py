"""
MindMatrix 智谱矩阵 —— 多角色 SaaS 后端
FastAPI + SQLAlchemy + JWT + DeepSeek 流式输出
"""
import os
import re
import json
import decimal
import asyncio
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

# ── 环境变量 ─────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── 数据库 & 模型 ─────────────────────────────────────────────────────────────
from app.models import User, Conversation, Message, InviteCode, get_db, init_db

# ── 鉴权 ─────────────────────────────────────────────────────────────────────
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)

# ── 日志配置 ──────────────────────────────────────────────────────────────────
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

_handler = RotatingFileHandler(
    log_dir / "chat.log",
    maxBytes=2 * 1024 * 1024,
    backupCount=1000,
    encoding="utf-8",
)
_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logger = logging.getLogger("chat_logger")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(_handler)

# ── RAG / 向量检索 ────────────────────────────────────────────────────────────
import sys
import numpy as np
from fastembed import TextEmbedding

sys.path.append(str(Path(__file__).parent.parent))
from tools.search import load_index, cosine_similarity

# 根目录路径
ROOT_DIR = Path(__file__).parent.parent
PERSONAS_DIR = ROOT_DIR / "personas"

# ── 全局单例：只加载一次向量模型（防 OOM）───────────────────────────────────
# 读取任意一个 vector_index.json 以获取 model_name，然后丢弃数据
_sample_index_path = next(PERSONAS_DIR.rglob("vector_index.json"), None)
if _sample_index_path is None:
    raise RuntimeError("找不到任何 vector_index.json，请先运行 build_index.py")
_sample_index = load_index(str(_sample_index_path))
_embed_model = TextEmbedding(model_name=_sample_index["model"])
del _sample_index  # 立即释放，只保留模型本身
logger.info(f"向量模型已加载，所有角色共享同一实例")

# ── 全局角色注册表（启动时扫描，内存中只存元数据，不存向量）────────────────
AVAILABLE_PERSONAS: Dict[str, Dict[str, Any]] = {}


def _parse_skill_frontmatter(skill_path: Path) -> Dict[str, str]:
    """解析 SKILL.md 的 YAML frontmatter 和 H1 标题，提取更友好的展示名和描述。"""
    try:
        text = skill_path.read_text(encoding="utf-8")
        
        # 1. 提取 H1 标题作为首选名称
        h1_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        h1_name = ""
        if h1_match:
            # 去掉常见的后缀如 "· 思维操作系统", "视角" 等
            h1_name = h1_match.group(1).split("·")[0].split("视角")[0].strip()

        # 2. 匹配 --- ... --- 的 frontmatter 块
        fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not fm_match:
            return {"name": h1_name} if h1_name else {}
        
        fm_block = fm_match.group(1)

        # 提取 name
        name_match = re.search(r"^name:\s*(.+)$", fm_block, re.MULTILINE)
        name = name_match.group(1).strip() if name_match else h1_name

        # 如果 H1 名字看起来比 frontmatter 里的 ID 更好（含有中文或空格），则使用 H1
        if h1_name and (re.search(r"[\u4e00-\u9fa5]", h1_name) or " " in h1_name):
            name = h1_name

        # 提取 description
        desc_match = re.search(r"^description:\s*\|?\s*\n((?:[ \t]+.+\n?)+)", fm_block, re.MULTILINE)
        if desc_match:
            raw_lines = desc_match.group(1).splitlines()
            desc = " ".join(line.strip() for line in raw_lines if line.strip())
        else:
            inline = re.search(r"^description:\s*(.+)$", fm_block, re.MULTILINE)
            desc = inline.group(1).strip() if inline else ""

        return {"name": name, "description": desc}
    except Exception as e:
        logger.warning(f"解析 frontmatter 失败 {skill_path}: {e}")
        return {}


def scan_personas() -> None:
    """
    启动时扫描 personas/ 目录，将每个角色的元数据注册到 AVAILABLE_PERSONAS。
    内存中只保留 id / name / description / skill_path / index_path，不加载向量数据。
    """
    global AVAILABLE_PERSONAS
    AVAILABLE_PERSONAS = {}

    for persona_dir in sorted(PERSONAS_DIR.iterdir()):
        if not persona_dir.is_dir():
            continue
        persona_id = persona_dir.name

        # 每个 persona 子目录内的 SKILL.md（hu-chenfeng 特殊处理：回退到根目录）
        skill_path = persona_dir / "SKILL.md"
        if not skill_path.exists():
            if persona_id == "hu-chenfeng":
                skill_path = ROOT_DIR / "SKILL.md"
            else:
                logger.warning(f"[personas] {persona_id} 缺少 SKILL.md，跳过")
                continue

        # vector_index.json 必须在 persona 子目录内
        index_path = persona_dir / "vector_index.json"
        if not index_path.exists():
            logger.warning(f"[personas] {persona_id} 缺少 vector_index.json，跳过")
            continue

        fm = _parse_skill_frontmatter(skill_path)
        display_name = fm.get("name") or persona_id
        description  = fm.get("description") or f"{display_name} 数字分身"

        AVAILABLE_PERSONAS[persona_id] = {
            "id":          persona_id,
            "name":        display_name,
            "description": description,
            "skill_path":  str(skill_path),   # 路径字符串，供运行时动态读取
            "index_path":  str(index_path),   # 路径字符串，供运行时懒加载
        }

    logger.info(f"[personas] 扫描完成，共注册 {len(AVAILABLE_PERSONAS)} 个角色：{list(AVAILABLE_PERSONAS.keys())}")


def get_persona_or_404(persona_id: str) -> Dict[str, Any]:
    """从注册表获取角色信息，不存在则抛 404。"""
    persona = AVAILABLE_PERSONAS.get(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail=f"角色 '{persona_id}' 不存在")
    return persona


def search_quotes_for_persona(query: str, persona_id: str, top_k: int = 5) -> list[dict]:
    """
    懒加载指定角色的 vector_index.json，执行语义检索后立即释放。
    全程不在内存中保留向量数据，适配 2核2G 小内存服务器。
    """
    persona = AVAILABLE_PERSONAS.get(persona_id)
    if not persona:
        return []
    try:
        # 按需从硬盘读取，用完即丢
        index = load_index(persona["index_path"])
        query_emb = list(_embed_model.embed([query]))[0].tolist()
        scored = [
            {"text": chunk["text"], "score": cosine_similarity(query_emb, chunk["embedding"])}
            for chunk in index["chunks"]
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]
    except Exception as e:
        logger.error(f"[RAG] 角色 {persona_id} 检索失败: {e}")
        return []


# ── DeepSeek / OpenAI 客户端 ──────────────────────────────────────────────────
llm_client = AsyncOpenAI(
    base_url=os.getenv("OLLAMA_BASE_URL", "https://api.deepseek.com/v1"),
    api_key=os.getenv("DEEPSEEK_API_KEY", "your-api-key-here"),
)
MODEL_NAME = os.getenv("LLM_MODEL_NAME", "deepseek-v4-pro")

# ── 计费常量 ──────────────────────────────────────────────────────────────────
COST_PER_CHAT = decimal.Decimal("0.05")
MIN_BALANCE   = decimal.Decimal("0.05")
MAX_MSG_LEN   = 1000

# ══════════════════════════════════════════════════════════════════════════════
# FastAPI 应用
# ══════════════════════════════════════════════════════════════════════════════
app = FastAPI(title="MindMatrix 智谱矩阵", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """应用启动时：建表 + 扫描角色注册表。"""
    init_db()
    scan_personas()
    logger.info("MindMatrix 启动完成。")


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic Schema
# ══════════════════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)

class RegisterRequest(BaseModel):
    username:    str = Field(..., min_length=2, max_length=64)
    password:    str = Field(..., min_length=6)
    invite_code: str = Field(..., min_length=1, max_length=64)

class ConversationCreate(BaseModel):
    title:      str = Field(default="新对话", max_length=255)
    persona_id: str = Field(default="hu-chenfeng", max_length=64)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    conversation_id: int
    messages: List[ChatMessage]
    image_url:    Optional[str] = None
    image_base64: Optional[str] = None

# ══════════════════════════════════════════════════════════════════════════════
# 角色广场接口
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/personas", summary="获取所有可用角色列表（无需鉴权）")
def list_personas():
    """返回系统内已注册的全部角色基本信息，供首页角色广场渲染。"""
    return [
        {
            "id":          p["id"],
            "name":        p["name"],
            "description": p["description"],
        }
        for p in AVAILABLE_PERSONAS.values()
    ]


# ══════════════════════════════════════════════════════════════════════════════
# 用户注册 / 登录
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/register", summary="注册新用户（需要邀请码）")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")

    invite = db.query(InviteCode).filter(InviteCode.code == body.invite_code).first()
    if not invite:
        raise HTTPException(status_code=400, detail="邀请码不存在，请确认后重试")
    if invite.is_used:
        raise HTTPException(status_code=400, detail="该邀请码已被使用，每个邀请码只能使用一次")

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        invite_code=body.invite_code,
    )
    db.add(user)
    invite.is_used = True
    invite.used_by = body.username
    invite.used_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return {"message": "注册成功", "user_id": user.id}


@app.post("/api/login", summary="登录并获取 JWT Token")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user_id=user.id, username=user.username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user.username,
        "balance": float(user.balance),
    }


@app.get("/api/me", summary="获取当前用户信息")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "user_id": current_user.id,
        "username": current_user.username,
        "balance": float(current_user.balance),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 邀请码管理 API（管理员路由）
# ══════════════════════════════════════════════════════════════════════════════

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "CHANGE_ME_ADMIN_SECRET")

class InviteCodeCreate(BaseModel):
    code:         str = Field(..., min_length=4, max_length=64)
    distributor:  str = Field(..., min_length=1, max_length=64)
    admin_secret: str = Field(...)


@app.post("/api/admin/invite-codes", summary="创建邀请码（需管理员密钥）", status_code=201)
def create_invite_code(body: InviteCodeCreate, db: Session = Depends(get_db)):
    if body.admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="管理员密钥错误")
    if db.query(InviteCode).filter(InviteCode.code == body.code).first():
        raise HTTPException(status_code=400, detail="该邀请码已存在")
    invite = InviteCode(code=body.code, distributor=body.distributor)
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return {
        "id": invite.id,
        "code": invite.code,
        "distributor": invite.distributor,
        "is_used": invite.is_used,
        "created_at": invite.created_at.isoformat(),
    }


@app.get("/api/admin/invite-codes", summary="查看所有邀请码（需管理员密钥）")
def list_invite_codes(admin_secret: str, db: Session = Depends(get_db)):
    if admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="管理员密钥错误")
    codes = db.query(InviteCode).order_by(InviteCode.created_at.desc()).all()
    return [
        {
            "id":          c.id,
            "code":        c.code,
            "distributor": c.distributor,
            "is_used":     c.is_used,
            "used_by":     c.used_by,
            "used_at":     c.used_at.isoformat() if c.used_at else None,
            "created_at":  c.created_at.isoformat(),
        }
        for c in codes
    ]


# ══════════════════════════════════════════════════════════════════════════════
# 会话管理 API
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/conversations", summary="获取当前用户的历史会话列表")
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
            # 附带角色显示名，前端侧边栏直接可用
            "persona_name": AVAILABLE_PERSONAS.get(c.persona_id, {}).get("name", c.persona_id),
            "created_at": c.created_at.isoformat(),
        }
        for c in convs
    ]


@app.post("/api/conversations", summary="创建新会话（指定角色）", status_code=201)
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


@app.get("/api/conversations/{conv_id}/messages", summary="获取某会话的历史消息")
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


@app.delete("/api/conversations/{conv_id}", summary="删除某个会话及其全部消息")
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


# ══════════════════════════════════════════════════════════════════════════════
# 核心 /chat 接口（流式输出 + 鉴权 + 计费 + 落库 + 动态角色切换）
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/chat", summary="流式对话（需鉴权，自动路由到会话对应角色）")
async def chat_endpoint(
    request: Request,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"

    # ── 1. 验证会话归属 ───────────────────────────────────────────────────
    conv = db.query(Conversation).filter(
        Conversation.id == body.conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")

    # ── 2. 根据会话的 persona_id 动态加载角色配置 ─────────────────────────
    persona_id = conv.persona_id
    persona = AVAILABLE_PERSONAS.get(persona_id)
    if not persona:
        # 角色已被移除，降级到 hu-chenfeng
        persona_id = "hu-chenfeng"
        persona = AVAILABLE_PERSONAS.get(persona_id, {})
        logger.warning(f"[chat] 角色 {conv.persona_id} 不存在，降级到 hu-chenfeng")

    # ── 3. 取最新一条用户消息 ─────────────────────────────────────────────
    last_user_msg = next(
        (m.content for m in reversed(body.messages) if m.role == "user"), ""
    )

    # ── 4. 字数限制 ───────────────────────────────────────────────────────
    if len(last_user_msg) > MAX_MSG_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"消息超过 {MAX_MSG_LEN} 字限制，请缩短后重试",
        )

    # ── 5. 余额检查 ───────────────────────────────────────────────────────
    db.refresh(current_user)
    if decimal.Decimal(str(current_user.balance)) < MIN_BALANCE:
        raise HTTPException(status_code=402, detail="余额不足，请充值后继续使用")

    # ── 6. 懒加载 RAG：按需从硬盘读取当前角色的向量索引，检索后立即丢弃 ──
    quotes = search_quotes_for_persona(last_user_msg, persona_id) if last_user_msg else []
    quotes_text = "\n\n".join(
        [f"原文片段 {i+1}:\n{q['text']}" for i, q in enumerate(quotes)]
    )

    # ── 7. 动态读取当前角色的 SKILL.md 作为 system prompt ────────────────
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

    if body.image_base64 or body.image_url:
        logger.info(f"[多模态预留] user_id={current_user.id} 上传了图片，待后续接入多模态模型。")

    llm_msgs = [{"role": "system", "content": system_prompt}] + [
        {"role": m.role, "content": m.content} for m in body.messages
    ]

    # ── 8. 流式生成器 ─────────────────────────────────────────────────────
    async def event_generator():
        full_response = ""
        success = False
        try:
            stream = await llm_client.chat.completions.create(
                model=MODEL_NAME,
                messages=llm_msgs,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
            success = True

        except Exception as e:
            logger.error(f"IP:{client_ip} | uid:{current_user.id} | persona:{persona_id} | LLM Error: {e}")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        finally:
            # ── 9. 落库 & 扣费（仅成功时执行）────────────────────────────
            if success and full_response:
                try:
                    from app.models import SessionLocal
                    sync_db = SessionLocal()
                    try:
                        sync_db.add(Message(
                            conversation_id=conv.id,
                            role="user",
                            content=last_user_msg,
                        ))
                        sync_db.add(Message(
                            conversation_id=conv.id,
                            role="assistant",
                            content=full_response,
                        ))
                        sync_db.query(User).filter(User.id == current_user.id).update(
                            {User.balance: User.balance - COST_PER_CHAT}
                        )
                        sync_db.commit()
                        logger.info(
                            f"IP:{client_ip} | uid:{current_user.id} | "
                            f"conv:{conv.id} | persona:{persona_id} | cost:{COST_PER_CHAT} | "
                            f"Q:{last_user_msg} | "
                            f"A:{full_response}"
                        )
                    finally:
                        sync_db.close()
                except Exception as db_err:
                    logger.error(f"落库失败 uid:{current_user.id} | {db_err}")

            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ══════════════════════════════════════════════════════════════════════════════
# 静态文件（前端）—— 必须最后挂载
# ══════════════════════════════════════════════════════════════════════════════
app.mount(
    "/",
    StaticFiles(directory=Path(__file__).parent / "static", html=True),
    name="static",
)
