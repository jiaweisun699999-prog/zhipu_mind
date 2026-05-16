from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.models import InviteCode, get_db
from app.config import ADMIN_SECRET

router = APIRouter(prefix="/api/admin", tags=["Admin"])

class InviteCodeCreate(BaseModel):
    code:         str = Field(..., min_length=4, max_length=64)
    distributor:  str = Field(..., min_length=1, max_length=64)
    admin_secret: str = Field(...)

@router.post("/invite-codes", summary="创建邀请码（需管理员密钥）", status_code=201)
def create_invite_code(body: InviteCodeCreate, db: Session = Depends(get_db)):
    if body.admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="管理员密钥错误")
    if db.query(InviteCode).filter(InviteCode.code == body.code).first():
        raise HTTPException(status_code=400, detail="该邀请码已存在")
    invite = InviteCode(code=body.code, distributor=body.distributor)
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return {
        "id": invite.id,
        "code": invite.code,
        "distributor": invite.distributor,
        "is_used": invite.is_used,
        "created_at": invite.created_at.isoformat(),
    }

@router.get("/invite-codes", summary="查看所有邀请码（需管理员密钥）")
def list_invite_codes(admin_secret: str, db: Session = Depends(get_db)):
    if admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="管理员密钥错误")
    codes = db.query(InviteCode).order_by(InviteCode.created_at.desc()).all()
    return [
        {
            "id":          c.id,
            "code":        c.code,
            "distributor": c.distributor,
            "is_used":     c.is_used,
            "used_by":     c.used_by,
            "used_at":     c.used_at.isoformat() if c.used_at else None,
            "created_at":  c.created_at.isoformat(),
        }
        for c in codes
    ]
