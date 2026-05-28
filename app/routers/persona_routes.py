from fastapi import APIRouter
from app.rag import AVAILABLE_PERSONAS
from app.tts import is_voice_supported

router = APIRouter(prefix="/api", tags=["Personas"])

@router.get("/personas", summary="获取所有可用角色列表（无需鉴权）")
def list_personas():
    """返回系统内已注册的全部角色基本信息，供首页角色广场渲染。"""
    return [
        {
            "id":          p["id"],
            "name":        p["name"],
            "description": p["description"],
            "has_voice":   is_voice_supported(p["id"]),
        }
        for p in AVAILABLE_PERSONAS.values()
    ]
