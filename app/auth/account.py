from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
import logging
import traceback

from app.database import get_db
from app.models import Account, UserRole, UserToken, Character
from app.utils.response import response, ResponseCode
from app.utils.password import hash_password, verify_password
from app.auth.token import create_token, invalidate_token, create_access_token, get_current_user
from app.utils.common import CommonHeaders

logger = logging.getLogger(__name__)

# 创建路由
account_router = APIRouter(
    prefix="/api/auth",
    tags=["认证相关"]
)

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "test_user",
                "password": "password123",
                "email": "test@example.com"
            }
        }

class LoginRequest(BaseModel):
    username: str
    password: str
    device_name: str
    device_id: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "test_user",
                "password": "password123",
                "device_name": "Chrome Browser",
                "device_id": "browser-uuid-123"
            }
        }

class LogoutRequest(BaseModel):
    token: str
    device_name: str
    device_id: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                "device_name": "Chrome Browser",
                "device_id": "browser-uuid-123"
            }
        }

# 修改密码请求模型
class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "old_password": "old_password123",
                "new_password": "new_password123"
            }
        }

@account_router.post("/register",
    summary="用户注册",
    description="""
    用户注册接口，创建新账号。
    
    权限要求：
    - 无需Token
    
    请求参数：
    - username: 用户名
      - 类型：string
      - 必填：是
      - 长度：1-50个字符
      - 说明：用户的登录名，必须唯一
      
    - password: 密码
      - 类型：string
      - 必填：是
      - 长度：6-20个字符
      - 说明：用户的登录密码
      
    - email: 邮箱
      - 类型：string
      - 必填：否
      - 格式：有效的邮箱地址
      - 说明：用户的邮箱地址，如果提供则必须唯一
    
    可能的错误码：
    - 400: 参数错误
    - 1009: 账号已存在
    - 1010: 邮箱已存在
    
    请求示例：
    ```json
    {
        "username": "test_user",
        "password": "password123",
        "email": "test@example.com"
    }
    ```
    
    成功返回示例：
    ```json
    {
        "code": 200,
        "message": "SUCCESS",
        "data": {
            "account_id": 1001,
            "username": "test_user",
            "email": "test@example.com"
        }
    }
    ```
    
    错误返回示例：
    ```json
    {
        "code": 1009,
        "message": "ACCOUNT_EXISTS",
        "data": null
    }
    ```
    
    注意事项：
    1. 用户名必须唯一
    2. 如果提供邮箱，则邮箱必须唯一
    3. 密码会进行加密存储
    4. 注册成功后需要单独调用登录接口获取token
    """
)
async def register(
    request: Request,
    register_data: RegisterRequest,
    db: Session = Depends(get_db)
):
    """用户注册"""
    try:
        # 检查用户名是否已存在
        if db.query(Account).filter(Account.username == register_data.username).first():
            raise HTTPException(
                status_code=400,
                detail=response(
                    code=ResponseCode.ACCOUNT_EXISTS,
                    message="ACCOUNT_EXISTS"
                )
            )
        
        # 如果提供了邮箱，检查邮箱是否已存在
        if register_data.email:
            if db.query(Account).filter(Account.email == register_data.email).first():
                raise HTTPException(
                    status_code=400,
                    detail=response(
                        code=ResponseCode.EMAIL_EXISTS,
                        message="EMAIL_EXISTS"
                    )
                )
        
        # 创建新账号
        new_account = Account(
            username=register_data.username,
            password=hash_password(register_data.password),  # 使用密码加密函数
            email=register_data.email,
            status=1,  # 1: 正常
            role=UserRole.USER,  # 默认为普通用户
            created_at=datetime.utcnow()
        )
        
        db.add(new_account)
        db.commit()
        db.refresh(new_account)
        
        # 返回成功响应
        return response(
            code=ResponseCode.SUCCESS,
            message="SUCCESS",
            data={
                "account_id": new_account.id,
                "username": new_account.username,
                "email": new_account.email
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"注册账号时发生异常: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=response(
                code=ResponseCode.SYSTEM_ERROR,
                message="SYSTEM_ERROR"
            )
        )

@account_router.post("/login",
    summary="用户登录",
    description="""
    用户登录接口，支持账号密码登录。
    
    权限要求：
    - 无需Token
    
    请求参数：
    - username: 用户名
      - 类型：string
      - 必填：是
      - 长度：1-50个字符
      
    - password: 密码
      - 类型：string
      - 必填：是
      - 长度：6-20个字符
      
    - device_name: 设备名称
      - 类型：string
      - 必填：是
      - 说明：用于标识登录设备，如"iPhone 12"、"Chrome浏览器"等
      
    - device_id: 设备ID
      - 类型：string
      - 必填：是
      - 说明：设备的唯一标识符
    
    可能的错误码：
    - 1001: 账号不存在
    - 1002: 账号已禁用
    - 1003: 密码错误
    - 1007: 登录失败（其他原因）
    
    请求示例：
    ```json
    {
        "username": "test_user",
        "password": "password123",
        "device_name": "Chrome Browser",
        "device_id": "browser-uuid-123"
    }
    ```
    
    成功返回示例：
    ```json
    {
        "code": 200,
        "message": "SUCCESS",
        "data": {
            "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
            "account_id": 1001,
            "username": "test_user",
            "has_character": true
        }
    }
    ```
    
    错误返回示例：
    ```json
    {
        "code": 1003,
        "message": "PASSWORD_ERROR",
        "data": null
    }
    ```
    
    注意事项：
    1. 同一账号可以在多个设备上登录
    2. 每次登录都会生成新的token
    3. token有效期为7天
    4. 返回的has_character字段表示该账号是否已创建游戏角色
    """
)
async def login(
    request: Request,
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    try:
        # 记录完整的请求信息
        body = await request.body()
        logger.debug(f"收到登录请求 - 完整请求信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"Body: {body.decode()}")
        logger.debug(f"处理后的请求数据: {login_data.dict()}")
        
        # 验证设备信息
        if not login_data.device_id or not login_data.device_name:
            return response(
                code=ResponseCode.INVALID_DEVICE_DATA,
                message="INVALID_DEVICE_DATA"
            )
        
        # 查找用户账号
        account = db.query(Account).filter(Account.username == login_data.username).first()
        if not account:
            logger.error(f"用户不存在: {login_data.username}")
            return response(
                code=ResponseCode.ACCOUNT_NOT_FOUND,
                message="ACCOUNT_NOT_FOUND"
            )
            
        # 检查账号状态
        if account.is_deleted:
            logger.error(f"已删除的账号尝试登录: {login_data.username}")
            return response(
                code=ResponseCode.ACCOUNT_DISABLED,
                message="ACCOUNT_DELETED"
            )
            
        if account.status == 2:  # 已封禁
            logger.error(f"被封禁的账号尝试登录: {login_data.username}")
            return response(
                code=ResponseCode.ACCOUNT_DISABLED,
                message="ACCOUNT_BANNED"
            )
            
        # 验证密码
        if not verify_password(login_data.password, account.password):
            logger.error(f"密码错误: username={login_data.username}")
            return response(
                code=ResponseCode.PASSWORD_ERROR,
                message="PASSWORD_ERROR"
            )
            
        logger.debug(f"用户验证成功: {account.username} (ID: {account.id})")
        
        # 检查是否有游戏角色
        has_character = db.query(Character).filter(
            Character.account_id == account.id,
            Character.is_deleted == 0
        ).first() is not None
        logger.debug(f"用户角色检查: has_character={has_character}")
        
        # 创建token
        token = create_access_token({"sub": str(account.id)})
        if not token:
            return response(
                code=ResponseCode.LOGIN_FAILED,
                message="TOKEN_CREATE_FAILED"
            )
            
        # 保存token记录
        token_record = UserToken(
            account_id=account.id,
            token=token,
            device_name=login_data.device_name,
            device_id=login_data.device_id,
            expired=False,
            created_at=datetime.utcnow(),
            last_active=datetime.utcnow()
        )
        db.add(token_record)
            
        logger.debug(f"创建token成功: {token[:10]}...")
        
        # 更新最后登录时间
        account.last_login_at = datetime.utcnow()
        db.commit()
        
        return response(data={
            "token": token,
            "account_id": account.id,
            "username": account.username,
            "has_character": has_character
        })
        
    except Exception as e:
        logger.error(f"登录过程发生异常: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return response(
            code=ResponseCode.LOGIN_FAILED,
            message="LOGIN_FAILED"
        )

@account_router.post("/logout",
    summary="用户登出",
    description="""
    用户登出接口，使当前设备的token失效。
    
    权限要求：
    - 需要有效的Token
    
    请求头：
    - token: 当前会话的token
      - 类型：string
      - 必填：是
      
    - device_name: 设备名称
      - 类型：string
      - 必填：是
      - 说明：登录时使用的设备名称
      
    - device_id: 设备ID
      - 类型：string
      - 必填：是
      - 说明：登录时使用的设备ID
      
    - service_code: 服务代码
      - 类型：string
      - 必填：是
      - 说明：web-网页端，game-游戏端
    
    可能的错误码：
    - 1004: Token无效
    - 1006: 设备不匹配
    - 1008: 登出失败
    
    成功返回示例：
    ```json
    {
        "code": 200,
        "message": "SUCCESS",
        "data": {
            "status": "success",
            "message": "Logged out successfully"
        }
    }
    ```
    
    错误返回示例：
    ```json
    {
        "code": 1004,
        "message": "TOKEN_INVALID",
        "data": null
    }
    ```
    
    注意事项：
    1. 登出后token将立即失效
    2. 只会使当前设备的token失效，不影响其他设备的登录状态
    3. 重复登出无害，会返回成功
    """
)
async def logout(
    request: Request,
    commons: CommonHeaders = Depends(),
    db: Session = Depends(get_db)
):
    try:
        body = await request.body()
        logger.debug(f"登出请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"Body: {body.decode()}")
        
        # 验证设备信息
        if not commons.device_id or not commons.device_name:
            return response(
                code=ResponseCode.INVALID_DEVICE_DATA,
                message="INVALID_DEVICE_DATA"
            )
            
        # 验证token和设备是否匹配
        token_record = db.query(UserToken).filter(
            UserToken.token == commons.token,
            UserToken.device_id == commons.device_id,
            UserToken.device_name == commons.device_name,
            UserToken.expired == False
        ).first()
        
        if not token_record:
            return response(
                code=ResponseCode.DEVICE_NOT_MATCH,
                message="DEVICE_NOT_MATCH"
            )
        
        # 使token失效
        token_record.expired = True
        db.commit()
        
        logger.debug(f"登出成功: token={commons.token[:10]}...")
        return response(data={
            "status": "success",
            "message": "Logged out successfully"
        })
        
    except Exception as e:
        logger.error(f"登出过程发生异常: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return response(
            code=ResponseCode.LOGOUT_FAILED,
            message="LOGOUT_FAILED"
        )

@account_router.post("/change-password",
    summary="修改密码",
    description="""
    修改当前用户的登录密码。
    
    权限要求：
    - 需要有效的Token
    
    请求参数：
    - old_password: 旧密码
      - 类型：string
      - 必填：是
      - 长度：6-20个字符
      - 说明：用户当前的登录密码
      
    - new_password: 新密码
      - 类型：string
      - 必填：是
      - 长度：6-20个字符
      - 说明：用户要设置的新密码
    
    可能的错误码：
    - 400: 参数错误
    - 401: Token无效
    - 1003: 旧密码错误
    - 1007: 修改失败
    
    请求示例：
    ```json
    {
        "old_password": "old_password123",
        "new_password": "new_password123"
    }
    ```
    
    成功返回示例：
    ```json
    {
        "code": 200,
        "message": "SUCCESS",
        "data": {
            "message": "密码修改成功"
        }
    }
    ```
    
    错误返回示例：
    ```json
    {
        "code": 1003,
        "message": "PASSWORD_ERROR",
        "data": null
    }
    ```
    
    注意事项：
    1. 新密码不能与旧密码相同
    2. 修改密码后，当前token仍然有效
    3. 其他设备的登录状态不受影响
    """
)
async def change_password(
    request: Request,
    data: ChangePasswordRequest,
    commons: CommonHeaders = Depends(),
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"修改密码请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        
        # 验证旧密码
        if not verify_password(data.old_password, current_user.password):
            logger.error(f"旧密码错误: account_id={current_user.id}")
            return response(
                code=ResponseCode.PASSWORD_ERROR,
                message="OLD_PASSWORD_ERROR"
            )
            
        # 检查新密码是否与旧密码相同
        if data.old_password == data.new_password:
            return response(
                code=ResponseCode.PARAM_ERROR,
                message="NEW_PASSWORD_SAME_AS_OLD"
            )
            
        # 更新密码
        current_user.password = hash_password(data.new_password)
        current_user.updated_at = datetime.utcnow()
        
        db.commit()
        
        logger.debug(f"密码修改成功: account_id={current_user.id}")
        return response(data={
            "message": "密码修改成功"
        })
        
    except Exception as e:
        logger.error(f"修改密码失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return response(
            code=ResponseCode.SYSTEM_ERROR,
            message="SYSTEM_ERROR"
        ) 