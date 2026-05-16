from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import datetime

from app.models import User, InviteCode, get_db
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)

router = APIRouter(prefix="/api", tags=["Auth"])

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)

class RegisterRequest(BaseModel):
    username:    str = Field(..., min_length=2, max_length=64)
    password:    str = Field(..., min_length=6)
    invite_code: str = Field(..., min_length=1, max_length=64)

@router.post("/register", summary="注册新用户（需要邀请码）")
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

@router.post("/login", summary="登录并获取 JWT Token")
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

@router.get("/me", summary="获取当前用户信息")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "user_id": current_user.id,
        "username": current_user.username,
        "balance": float(current_user.balance),
    }
