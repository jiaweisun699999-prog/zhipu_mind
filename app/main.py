"""
MindMatrix 智谱矩阵 —— 多角色 SaaS 后端
FastAPI + SQLAlchemy + JWT + DeepSeek 流式输出
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.models import init_db
from app.rag import scan_personas
from app.config import logger

# 引入路由模块
from app.routers import (
    auth_routes, 
    persona_routes, 
    conversation_routes, 
    admin_routes, 
    chat_routes
)

app = FastAPI(title="MindMatrix 智谱矩阵", version="3.0.0")

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    """应用启动时：初始化数据库并扫描角色注册表。"""
    init_db()
    scan_personas()
    logger.info("MindMatrix 启动完成（模块化版本）。")

# 挂载业务路由
app.include_router(auth_routes.router)
app.include_router(persona_routes.router)
app.include_router(conversation_routes.router)
app.include_router(admin_routes.router)
app.include_router(chat_routes.router)

# 静态文件挂载（必须放在最后，否则会覆盖 API 路由）
app.mount(
    "/",
    StaticFiles(directory=Path(__file__).parent / "static", html=True),
    name="static",
)
