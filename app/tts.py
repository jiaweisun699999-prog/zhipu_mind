"""
MindMatrix —— TTS 模块
语音合成与文本清洗（切换至火山引擎-豆包语音集群）。
"""
import re
import datetime
import httpx
import uuid
import base64
import os
from typing import Optional
from app.config import AUDIO_DIR, logger

def clean_text_for_speech(text: str) -> str:
    """使用正则去除所有全角/半角圆括号、方括号及其内部的动作/情绪描写词汇。"""
    # 匹配 (xxx), （xxx）, [xxx], 【xxx】
    pattern = r"\(.*?\)|（.*?）|\[.*?\]|【.*?】"
    cleaned = re.sub(pattern, "", text)
    # 替换连续空格并去除首尾空白
    return re.sub(r"\s+", " ", cleaned).strip()

def is_voice_supported(persona_id: str) -> bool:
    """检查指定角色是否配置了语音克隆 ID。"""
    # 规则 1：查精准的环境变量
    env_key = f"{persona_id.upper().replace('-', '_')}_VOICE_ID"
    if os.getenv(env_key):
        return True
        
    # 规则 2：查内置的火山语音映射表
    voice_map = {
        "feng-ge": "S_hKStQfZ22",
        "hu-chenfeng": "S_N0XLQfZ22",
    }
    return persona_id in voice_map

async def generate_volcano_audio(clean_text: str, persona_id: str) -> Optional[str]:
    """调用字节火山引擎 TTS 接口生成角色专属语音，并返回相对路径。"""
    if not clean_text:
        return None
    
    # 优先寻找环境变量，其次找内置映射
    env_key = f"{persona_id.upper().replace('-', '_')}_VOICE_ID"
    target_voice = os.getenv(env_key)
    
    # if not target_voice:
    #     voice_map = {
    #         "feng-ge": "S_hKStQfZ22",
    #         "hu-chenfeng": "S_N0XLQfZ22",
    #     }
    #     target_voice = voice_map.get(persona_id)

    if not target_voice:
        return None # 暂不支持语音的角色直接跳过

    # 优先从环境变量取，如果没有则使用用户提供的固定 Key
    api_key = os.getenv("VOLCANO_API_KEY")
    url = "https://openspeech.bytedance.com/api/v1/tts"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "app": {
            "cluster": "volcano_icl"
        },
        "user": {
            "uid": "mindmatrix_user"
        },
        "audio": {
            "voice_type": target_voice,
            "encoding": "mp3",
            "speed_ratio": 1.0
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": clean_text,
            "operation": "query"
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                data = response.json()
                # Volcano 成功返回码一般是 3000
                if data.get("code") == 3000 and "data" in data:
                    audio_b64 = data["data"]
                    audio_bytes = base64.b64decode(audio_b64)
                    
                    filename = f"{persona_id}_{int(datetime.datetime.now().timestamp())}.mp3"
                    file_path = AUDIO_DIR / filename
                    file_path.write_bytes(audio_bytes)
                    return f"/static/audio/{filename}"
                else:
                    logger.error(f"[TTS] Volcano 返回数据异常: {data}")
            else:
                logger.error(f"[TTS] Volcano 请求失败 HTTP {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"[TTS] Volcano 语音合成异常: {e}")
    return None

