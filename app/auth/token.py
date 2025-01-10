from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Account, UserToken
from app.utils.response import response, ResponseCode
import logging
import traceback

logger = logging.getLogger(__name__)

# JWT 配置
SECRET_KEY = "your-secret-key"  # 应该从配置文件读取
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24 * 7  # Token有效期7天

def create_access_token(data: Dict[str, Any]) -> str:
    """
    创建访问令牌
    
    参数：
        data: 要编码到令牌中的数据
        
    返回：
        生成的JWT令牌
    """
    try:
        to_encode = data.copy()
        # 设置过期时间
        expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
        to_encode.update({"exp": expire})
        # 创建JWT
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception as e:
        logger.error(f"创建访问令牌时发生异常: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return None

def verify_token(db: Session, token: str) -> Optional[int]:
    """
    验证token是否有效
    
    参数：
        db: 数据库会话
        token: 要验证的token
        
    返回：
        如果token有效，返回account_id；否则返回None
    """
    try:
        # 检查token是否存在且未过期
        token_record = db.query(UserToken).filter(
            UserToken.token == token,
            UserToken.expired == False
        ).first()
        
        if not token_record:
            logger.error(f"Token不存在或已过期: {token[:10]}...")
            return None
            
        # 检查token是否过期（使用last_active时间）
        if datetime.utcnow() - token_record.last_active > timedelta(hours=TOKEN_EXPIRE_HOURS):
            logger.error(f"Token已过期: {token[:10]}...")
            # 标记token为已过期
            token_record.expired = True
            db.commit()
            return None
            
        # 更新最后活跃时间
        token_record.last_active = datetime.utcnow()
        db.commit()
        
        return token_record.account_id
        
    except Exception as e:
        logger.error(f"验证token时发生异常: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return None

def create_token(db: Session, account_id: int, device_name: str, device_id: str) -> str:
    """
    创建用户令牌并保存到数据库
    """
    try:
        # 检查设备数量限制
        active_tokens = db.query(UserToken).filter(
            UserToken.account_id == account_id,
            UserToken.expired == False
        ).all()
        
        # 如果已达到最大设备数，使最早的token过期
        if len(active_tokens) >= 3:  # 最大允许3个设备同时在线
            oldest_token = min(active_tokens, key=lambda x: x.last_active)
            oldest_token.expired = True
            db.commit()
        
        # 检查是否存在相同设备的token
        existing_token = db.query(UserToken).filter(
            UserToken.account_id == account_id,
            UserToken.device_id == device_id,
            UserToken.expired == False
        ).first()
        
        if existing_token:
            existing_token.expired = True
            db.commit()
        
        # 创建JWT令牌
        token = create_access_token({"sub": str(account_id)})
        if not token:
            return None
        
        # 保存令牌记录
        token_record = UserToken(
            account_id=account_id,
            token=token,
            device_name=device_name,
            device_id=device_id,
            expired=False,
            last_active=datetime.utcnow()
        )
        db.add(token_record)
        db.commit()
        
        return token
        
    except Exception as e:
        logger.error(f"创建用户令牌时发生异常: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        db.rollback()
        return None

def get_current_user(
    token: str = Header(..., description="认证token"),
    device_name: str = Header(..., description="设备名称"),
    device_id: str = Header(..., description="设备ID"),
    service_code: str = Header(..., description="服务代码：web-网页端，game-游戏端"),
    db: Session = Depends(get_db)
) -> Account:
    """
    获取当前用户
    """
    try:
        # 验证设备信息
        if not device_id or not device_name:
            return response(
                code=ResponseCode.INVALID_DEVICE_DATA,
                message="INVALID_DEVICE_DATA"
            )
        
        # 验证token是否存在且未过期
        token_record = db.query(UserToken).filter(
            UserToken.token == token,
            UserToken.device_name == device_name,
            UserToken.device_id == device_id,
            UserToken.expired == False
        ).first()
        
        if not token_record:
            return response(
                code=ResponseCode.DEVICE_NOT_MATCH,
                message="DEVICE_NOT_MATCH"
            )
            
        # 验证JWT
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            account_id = int(payload.get("sub"))  # 确保转换为整数
            if account_id is None:
                return response(
                    code=ResponseCode.TOKEN_INVALID,
                    message="TOKEN_INVALID"
                )
        except jwt.ExpiredSignatureError:
            # 令牌过期，标记为已过期
            token_record.expired = True
            db.commit()
            return response(
                code=ResponseCode.TOKEN_EXPIRED,
                message="TOKEN_EXPIRED"
            )
        except jwt.JWTError:
            return response(
                code=ResponseCode.TOKEN_INVALID,
                message="TOKEN_INVALID"
            )
            
        # 获取用户
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return response(
                code=ResponseCode.ACCOUNT_NOT_FOUND,
                message="ACCOUNT_NOT_FOUND"
            )
            
        # 检查账号状态
        if account.is_deleted:
            return response(
                code=ResponseCode.ACCOUNT_DISABLED,
                message="ACCOUNT_DELETED"
            )
            
        if account.status == 2:  # 已封禁
            return response(
                code=ResponseCode.ACCOUNT_DISABLED,
                message="ACCOUNT_BANNED"
            )
            
        if account.status == 0:  # 未激活
            return response(
                code=ResponseCode.ACCOUNT_DISABLED,
                message="ACCOUNT_NOT_ACTIVATED"
            )
            
        # 更新最后活跃时间
        token_record.last_active = datetime.utcnow()
        db.commit()
        
        return account  # 确保返回 Account 对象
        
    except Exception as e:
        logger.error(f"获取当前用户时发生异常: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return response(
            code=ResponseCode.SYSTEM_ERROR,
            message="SYSTEM_ERROR"
        )

def invalidate_token(db: Session, token: str) -> bool:
    """
    使令牌失效
    """
    try:
        token_record = db.query(UserToken).filter(
            UserToken.token == token,
            UserToken.expired == False
        ).first()
        
        if token_record:
            token_record.expired = True
            db.commit()
            return True
            
        return False
        
    except Exception as e:
        logger.error(f"使令牌失效时发生异常: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        db.rollback()
        return False 