from datetime import datetime, timedelta
import jwt
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Account, UserToken
import logging

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
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=2)  # 默认2小时
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_token(db: Session, account_id: int, device_name: str, device_id: str) -> str:
    """
    创建用户令牌并保存到数据库
    """
    # 创建JWT令牌
    token = create_access_token({"sub": str(account_id)})
    
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
    credentials_exception = HTTPException(
        status_code=401,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # 验证token是否存在且未过期
        token_record = db.query(UserToken).filter(
            UserToken.token == token,
            UserToken.device_name == device_name,
            UserToken.device_id == device_id,
            UserToken.expired == False
        ).first()
        
        if not token_record:
            raise credentials_exception
            
        # 验证JWT
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        account_id = payload.get("sub")
        if account_id is None:
            raise credentials_exception
            
        # 获取用户
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise credentials_exception
            
        # 检查账号状态
        if account.is_deleted:
            raise HTTPException(status_code=403, detail="账号已被删除")
            
        if account.status == 2:  # 已封禁
            raise HTTPException(status_code=403, detail="账号已被封禁，如有疑问请联系我们")
            
        if account.status == 0:  # 未激活
            raise HTTPException(status_code=403, detail="账号未激活，请先激活账号")
            
        # 更新最后活跃时间
        token_record.last_active = datetime.utcnow()
        db.commit()
        
        return account
        
    except jwt.ExpiredSignatureError:
        # 令牌过期，标记为已过期
        if token_record:
            token_record.expired = True
            db.commit()
        raise HTTPException(status_code=401, detail="认证令牌已过期")
    except jwt.JWTError:
        raise credentials_exception
    except Exception as e:
        logger.error(f"验证用户时发生错误: {str(e)}")
        raise HTTPException(status_code=500, detail="系统错误，请稍后重试")

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
        logger.error(f"使令牌失效时发生错误: {str(e)}")
        return False 