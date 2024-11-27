from datetime import datetime, timedelta
import secrets
from typing import Optional
from sqlalchemy.orm import Session
from app.models import UserToken, Account
from fastapi import HTTPException

# 配置
SECRET_KEY = "your-secret-key"  # 请更改为安全的密钥
TOKEN_EXPIRE_HOURS = 24  # Token 有效期（小时）
MAX_ACTIVE_DEVICES = 3   # 每个账号最大活跃设备数

def create_token(db: Session, account_id: int, device_name: str, device_id: str) -> str:
    """创建新的token"""
    # 检查设备数量限制
    active_tokens = db.query(UserToken).filter(
        UserToken.account_id == account_id,
        UserToken.expired == 0
    ).all()
    
    # 如果已达到最大设备数，使最早的token过期
    if len(active_tokens) >= MAX_ACTIVE_DEVICES:
        oldest_token = min(active_tokens, key=lambda x: x.created_at)
        oldest_token.expired = 1
        db.commit()
    
    # 检查是否存在相同设备的token
    existing_token = db.query(UserToken).filter(
        UserToken.account_id == account_id,
        UserToken.device_id == device_id,
        UserToken.expired == 0
    ).first()
    
    if existing_token:
        existing_token.expired = 1
        db.commit()
    
    # 生成新token
    token = secrets.token_urlsafe(32)
    
    # 创建token记录
    db_token = UserToken(
        account_id=account_id,
        token=token,
        device_name=device_name,
        device_id=device_id
    )
    db.add(db_token)
    db.commit()
    db.refresh(db_token)
    
    return token

def verify_token(db: Session, token: str) -> Optional[int]:
    """验证token并返回account_id"""
    db_token = db.query(UserToken).filter(
        UserToken.token == token,
        UserToken.expired == 0
    ).first()
    
    if not db_token:
        return None
    
    # 检查token是否过期
    if datetime.utcnow() - db_token.last_active > timedelta(hours=TOKEN_EXPIRE_HOURS):
        db_token.expired = 1
        db.commit()
        return None
    
    # 更新最后活跃时间
    db_token.last_active = datetime.utcnow()
    db.commit()
    
    return db_token.account_id

def invalidate_token(db: Session, token: str) -> bool:
    """使token失效"""
    db_token = db.query(UserToken).filter(UserToken.token == token).first()
    if db_token:
        db_token.expired = 1
        db.commit()
        return True
    return False 