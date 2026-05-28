"""
MindMatrix 智谱矩阵 —— 多角色 SaaS 后端
FastAPI + SQLAlchemy + JWT + DeepSeek 流式输出
"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import traceback

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

@app.get("/3e4d1a0c95e2f9ee27ea5e1a593b8936.txt")
async def wechat_verification():
    """微信业务域名验证专用接口"""
    return PlainTextResponse("2ad61874acf092ec08ea5d96ed2d85689e3254b2")

# 挂载静态文件目录，使得 /static/audio/... 能够被外网访问
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static_files")

import os

# 配置 CORS，生产环境建议在 .env 中设置具体的 CORS_ORIGINS，例如：https://yourdomain.com
cors_origins_str = os.getenv("CORS_ORIGINS", "*")
allow_origins = [origin.strip() for origin in cors_origins_str.split(",")] if cors_origins_str else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    """应用启动时：初始化数据库并扫描角色注册表。"""
    init_db()
    scan_personas()
    logger.info("MindMatrix 启动完成（模块化版本）。")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局未捕获异常拦截器：自动把所有崩溃信息和堆栈写入日志。"""
    logger.error(f"全局未捕获异常 | 路径: {request.url.path} | 错误: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部发生严重错误，请联系管理员或查看后台日志。"},
    )

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
