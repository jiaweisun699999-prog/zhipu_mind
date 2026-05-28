"""
数据库模型定义 (SQLAlchemy + SQLite)
MindMatrix 智谱矩阵 — 多角色版
"""
import decimal
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String,
    Numeric, ForeignKey, Text, DateTime, Enum, Boolean
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from pathlib import Path

# ── 数据库连接 ──────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).parent.parent / "data" / "app.db"
DB_PATH.parent.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite 多线程必须加
    echo=False,  # 调试时可改为 True 查看 SQL 语句
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ── 数据库依赖（FastAPI Depends 用）────────────────────────────────────────
def get_db():
    """FastAPI 依赖函数：每次请求获取一个独立的数据库 Session，用完自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── 模型定义 ────────────────────────────────────────────────────────────────

class User(Base):
    """用户表"""
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    username      = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    balance       = Column(Numeric(precision=10, scale=2), nullable=False, default=decimal.Decimal("10.00"))
    invite_code   = Column(String(64), nullable=True, index=True)  # 注册时使用的邀请码

    # 关联关系
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User id={self.id} username={self.username} balance={self.balance}>"


class Conversation(Base):
    """会话表（对应 ChatGPT 侧边栏中的一个对话）"""
    __tablename__ = "conversations"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title      = Column(String(255), nullable=False, default="新对话")
    # ★ 新增：记录本会话绑定的角色 ID（对应 personas/ 子文件夹名）
    persona_id = Column(String(64), nullable=False, default="hu-chenfeng")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # 关联关系
    user     = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")

    def __repr__(self):
        return f"<Conversation id={self.id} title={self.title} persona={self.persona_id}>"


class Message(Base):
    """消息表（存储每轮对话的用户问和 AI 答）"""
    __tablename__ = "messages"

    id              = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    role            = Column(Enum("user", "assistant", name="role_enum"), nullable=False)
    content         = Column(Text, nullable=False)
    audio_url       = Column(String(512), nullable=True)  # ★ 新增：记录这句回复绑定的语音文件路径
    created_at      = Column(DateTime, nullable=False, default=datetime.utcnow)

    # 关联关系
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self):
        return f"<Message id={self.id} role={self.role} len={len(self.content)}>"


class InviteCode(Base):
    """邀请码表"""
    __tablename__ = "invite_codes"

    id           = Column(Integer, primary_key=True, index=True)
    code         = Column(String(64), unique=True, nullable=False, index=True)  # 邀请码
    distributor  = Column(String(64), nullable=False)                           # 派发人（销售者）名字
    is_used      = Column(Boolean, nullable=False, default=False)               # 是否已被使用
    used_by      = Column(String(64), nullable=True)                            # 使用者用户名
    used_at      = Column(DateTime, nullable=True)                              # 使用时间
    created_at   = Column(DateTime, nullable=False, default=datetime.utcnow)   # 创建时间

    def __repr__(self):
        return f"<InviteCode code={self.code} distributor={self.distributor} used={self.is_used}>"


# ── 初始化建表（应用启动时调用一次）──────────────────────────────────────────
def init_db():
    """创建所有尚不存在的表。安全：已存在的表不会被覆盖。"""
    Base.metadata.create_all(bind=engine)

    # ── 迁移兜底：为旧库补充新列 ──────
    from sqlalchemy import text
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE conversations ADD COLUMN persona_id VARCHAR(64) NOT NULL DEFAULT 'hu-chenfeng'"
            ))
            conn.commit()
        except Exception:
            pass

        try:
            conn.execute(text(
                "ALTER TABLE messages ADD COLUMN audio_url VARCHAR(512)"
            ))
            conn.commit()
        except Exception:
            pass

