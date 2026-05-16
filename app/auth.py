"""
鉴权模块：JWT Token 生成与验证、密码哈希、FastAPI 依赖函数
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.models import User, get_db

# ── 配置 ──────────────────────────────────────────────────────────────────────
# 生产环境务必在 .env 中设置强随机密钥：openssl rand -hex 32
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION_USE_OPENSSL_RAND_HEX_32")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))  # 默认 7 天

# ── 密码哈希 ──────────────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    """将明文密码哈希为 bcrypt 字符串。"""
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码是否与哈希匹配。"""
    return pwd_context.verify(plain, hashed)

# ── JWT Token ─────────────────────────────────────────────────────────────────
def create_access_token(user_id: int, username: str) -> str:
    """
    生成 JWT Access Token。
    Payload 包含：sub（用户名）、uid（用户 ID）、exp（过期时间）。
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "uid": user_id,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    """
    解码并校验 JWT Token，返回 payload dict。
    失败时抛出 HTTPException 401。
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token 无效或已过期，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[int] = payload.get("uid")
        if user_id is None:
            raise credentials_exception
        return payload
    except JWTError:
        raise credentials_exception

# ── FastAPI Bearer 方案 ───────────────────────────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=True)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI 依赖函数：从 Authorization: Bearer <token> 中解析并返回当前登录用户。
    任何受保护接口只需在参数中声明 `current_user: User = Depends(get_current_user)` 即可。
    """
    payload = decode_token(credentials.credentials)
    user_id: int = payload["uid"]

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    return user
