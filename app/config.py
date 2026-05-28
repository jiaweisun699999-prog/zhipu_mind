"""
MindMatrix —— 全局配置模块
所有环境变量、常量、共享客户端实例、日志在此统一管理。
其他模块统一从这里 import，不要分散读取 os.getenv。
"""
import os
import decimal
import logging
import datetime
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

class SizeDateRotatingFileHandler(RotatingFileHandler):
    """自定义日志滚动：当达到指定大小后，以当前时间重命名归档，并创建新文件。"""
    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        # 使用当前时间作为后缀
        time_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dfn = f"{self.baseFilename}.{time_str}"
        if os.path.exists(dfn):
            os.remove(dfn)
        self.rotate(self.baseFilename, dfn)
        if not self.delay:
            self.stream = self._open()

_handler = SizeDateRotatingFileHandler(
    _log_dir / "chat.log", maxBytes=2 * 1024 * 1024, backupCount=100, encoding="utf-8"
)
_handler.setFormatter(logging.Formatter("%(asctime)s | [%(levelname)s] | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logger = logging.getLogger("chat_logger")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(_handler)

# ── LLM 客户端 ────────────────────────────────────────────────────────────────
llm_client = AsyncOpenAI(
    base_url=os.getenv("OLLAMA_BASE_URL", "https://api.deepseek.com/v1"),
    api_key=os.getenv("DEEPSEEK_API_KEY", ""),
)
MODEL_NAME = os.getenv("LLM_MODEL_NAME", "deepseek-v4-pro")

# ── ASR 客户端（Groq Whisper）─────────────────────────────────────────────────
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

# ── TTS 配置（MiniMax）───────────────────────────────────────────────────────
MINIMAX_API_KEY  = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_GROUP_ID = os.getenv("MINIMAX_GROUP_ID", "1")
FENG_GE_VOICE_ID = os.getenv("FENG_GE_VOICE_ID", "male-qn-qingse")

# ── 计费常量 ──────────────────────────────────────────────────────────────────
COST_TEXT_CHAT  = decimal.Decimal("0.20")  # 普通文字聊天单次扣费
COST_VOICE_CHAT = decimal.Decimal("0.60")  # 语音聊天单次扣费
MIN_BALANCE     = decimal.Decimal("0.20")  # 最小余额限制
MAX_MSG_LEN     = 1000

# ── 管理员密钥 ────────────────────────────────────────────────────────────────
ADMIN_SECRET = os.getenv("ADMIN_SECRET")
if not ADMIN_SECRET:
    logger.warning("警告: 未设置 ADMIN_SECRET 环境变量！将影响邀请码的生成。")
    # raise ValueError("请在 .env 中设置 ADMIN_SECRET！")
