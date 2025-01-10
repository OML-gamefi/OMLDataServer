from datetime import datetime, timedelta
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

def create_access_token(data: dict, expires_delta: timedelta = None):
    """
    创建访问令牌
    :param data: 要编码的数据
    :param expires_delta: 过期时间增量
    :return: 编码后的JWT令牌
    """
    try:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(hours=2)  # 默认2小时
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception as e:
        logger.error(f"创建访问令牌时发生异常: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return None

def create_token(db: Session, account_id: int, device_name: str, device_id: str) -> str:
    """
    创建用户令牌并保存到数据库
    """
    try:
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
            account_id = payload.get("sub")
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
        
        return account
        
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