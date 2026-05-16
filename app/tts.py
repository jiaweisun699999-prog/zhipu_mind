"""
MindMatrix —— TTS 模块
语音合成与文本清洗。
"""
import re
import datetime
import httpx
from typing import Optional
from app.config import MINIMAX_API_KEY, AUDIO_DIR, FENG_GE_VOICE_ID, logger

def clean_text_for_speech(text: str) -> str:
    """使用正则去除所有全角/半角圆括号、方括号及其内部的动作/情绪描写词汇。"""
    # 匹配 (xxx), （xxx）, [xxx], 【xxx】
    pattern = r"\(.*?\)|（.*?）|\[.*?\]|【.*?】"
    cleaned = re.sub(pattern, "", text)
    # 替换连续空格并去除首尾空白
    return re.sub(r"\s+", " ", cleaned).strip()

async def generate_minimax_audio(clean_text: str, persona_id: str) -> Optional[str]:
    """调用 MiniMax TTS 接口生成角色专属语音，并返回相对路径。"""
    if not MINIMAX_API_KEY or not clean_text:
        return None
    
    # 语音映射表：目前仅试点角色“峰哥”
    voice_map = {
        "feng-ge": FENG_GE_VOICE_ID,
        "hu-chenfeng": FENG_GE_VOICE_ID, # 试点阶段，户晨风也用峰哥音色
    }
    
    target_voice = voice_map.get(persona_id)
    if not target_voice:
        return None # 暂不支持语音的角色直接跳过

    url = "https://api.minimax.chat/v1/t2a_v2?GroupId=1" # 默认 GroupId，可按需修改
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "speech-01-turbo",
        "text": clean_text,
        "stream": False,
        "voice_setting": {
            "voice_id": target_voice,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3"
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                data = response.json()
                if "data" in data and "audio" in data["data"]:
                    audio_hex = data["data"]["audio"]
                    # MiniMax v2 返回的是 hex 字符串
                    audio_bytes = bytes.fromhex(audio_hex)
                    
                    filename = f"{persona_id}_{int(datetime.datetime.now().timestamp())}.mp3"
                    file_path = AUDIO_DIR / filename
                    file_path.write_bytes(audio_bytes)
                    return f"/audio/{filename}"
            logger.error(f"[TTS] MiniMax 请求失败: {response.text}")
    except Exception as e:
        logger.error(f"[TTS] 语音合成异常: {e}")
    return None
