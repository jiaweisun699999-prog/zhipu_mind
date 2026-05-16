"""
MindMatrix —— 全局配置模块
所有环境变量、常量、共享客户端实例、日志在此统一管理。
其他模块统一从这里 import，不要分散读取 os.getenv。
"""
import os
import decimal
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from openai import AsyncOpenAI
from groq import Groq

# ── 路径 ──────────────────────────────────────────────────────────────────────
ROOT_DIR     = Path(__file__).parent.parent
PERSONAS_DIR = ROOT_DIR / "personas"
AUDIO_DIR    = Path(__file__).parent / "static" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# ── 日志 ──────────────────────────────────────────────────────────────────────
_log_dir = ROOT_DIR / "logs"
_log_dir.mkdir(exist_ok=True)

_handler = RotatingFileHandler(
    _log_dir / "chat.log", maxBytes=2 * 1024 * 1024, backupCount=1000, encoding="utf-8"
)
_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logger = logging.getLogger("chat_logger")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(_handler)

# ── LLM 客户端 ────────────────────────────────────────────────────────────────
llm_client = AsyncOpenAI(
    base_url=os.getenv("OLLAMA_BASE_URL", "https://api.deepseek.com/v1"),
    api_key=os.getenv("DEEPSEEK_API_KEY", "sk-89c410a7dd2e4f85a53420f00b1938c6"),
)
MODEL_NAME = os.getenv("LLM_MODEL_NAME", "deepseek-v4-pro")

# ── ASR 客户端（Groq Whisper）─────────────────────────────────────────────────
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

# ── TTS 配置（MiniMax）───────────────────────────────────────────────────────
MINIMAX_API_KEY  = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_GROUP_ID = os.getenv("MINIMAX_GROUP_ID", "1")
FENG_GE_VOICE_ID = os.getenv("FENG_GE_VOICE_ID", "male-qn-qingse")

# ── 计费常量 ──────────────────────────────────────────────────────────────────
COST_PER_CHAT = decimal.Decimal("0.05")
MIN_BALANCE   = decimal.Decimal("0.05")
MAX_MSG_LEN   = 1000

# ── 管理员密钥 ────────────────────────────────────────────────────────────────
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "CHANGE_ME_ADMIN_SECRET")
