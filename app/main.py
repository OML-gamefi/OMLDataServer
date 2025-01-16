from fastapi import FastAPI, Depends, Path, Query, HTTPException, Header, Request, APIRouter, Form
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List, Union
import logging
import json
import traceback
from datetime import datetime, timedelta
import importlib
import inspect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from enum import Enum
from app.utils.static_data import static_data
from app.utils.response import response, ResponseCode
import jwt
from app.auth.token import SECRET_KEY, ALGORITHM
from app.auth.server import server_router  # 添加这行

# 导入配置
logger = logging.getLogger(__name__)
logger.info("Loading settings...")
from app.config import settings
logger.info(f"Settings loaded - DB_HOST: {settings.DB_HOST}")

# 导入数据库
logger.info("Initializing database...")
from app.database import SessionLocal, engine, Base
logger.info("Database initialized")

# 导入模型和工具
from app.models import *
from app.models import CHARACTER_RELATED_MODELS, __all__ as model_all, SoftDeleteMixin, format_character_data
from app.utils.password import verify_password
import sqlalchemy.exc
from app.admin.routes import admin_router
from app.utils.ai_service import ai_service, ChatRequest, ChatResponse
from app.crud.base import CRUDRegister
from app.auth.token import create_token, verify_token, invalidate_token
from pydantic import BaseModel

# 修改日志配置
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 创建FastAPI应用
app = FastAPI(
    title="游戏后端API",
    description="游戏服务器后端API文档",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 添加请求日志中间件
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 记录请求开始
        logger.debug("=" * 50)
        logger.debug("收到新的请求:")
        logger.debug(f"请求方法: {request.method}")
        logger.debug(f"请求URL: {request.url}")
        logger.debug(f"请求头: {dict(request.headers)}")
        
        # 取请求体
        body = await request.body()
        if body:
            try:
                logger.debug(f"请求体: {body.decode()}")
            except:
                logger.debug(f"请求体: {body}")
        
        # 获取查询参数
        query_params = dict(request.query_params)
        if query_params:
            logger.debug(f"查询参数: {query_params}")
            
        # 记录客户端信息
        client_host = request.client.host if request.client else "unknown"
        logger.debug(f"客户端IP: {client_host}")
        
        try:
            # 继续处理请求
            response = await call_next(request)
            
            # 记录响应状态
            logger.debug(f"响应状态码: {response.status_code}")
            return response
            
        except Exception as e:
            # 记录异常
            logger.error(f"请求处理过程中发生异常: {str(e)}")
            logger.error(f"异常堆栈: {traceback.format_exc()}")
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            )
        finally:
            logger.debug("请求处理完成")
            logger.debug("=" * 50)

# 添加中间件
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# 创建路由
crud_router = APIRouter(prefix="/api/crud", tags=["数据操作"])
auth_router = APIRouter(prefix="/api/auth", tags=["认证相关"])
user_router = APIRouter(prefix="/api/user", tags=["用户相关"])
character_router = APIRouter(prefix="/api/character", tags=["角色相关"])
admin_router = APIRouter(prefix="/api/admin", tags=["管理相关"])

# 依赖项
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 动态注册所有模型
for model_name in model_all:
    model = globals().get(model_name)
    if (inspect.isclass(model) and 
        issubclass(model, Base) and 
        model != Base and 
        model != SoftDeleteMixin):  # 排除基类
        # 注册到 CRUD
        CRUDRegister.register(model)
        # 创建表
        model.metadata.create_all(bind=engine)
        logger.debug(f"已注册并创建表: {model_name}")

# 添加登录请求模型
class LoginRequest(BaseModel):
    username: str
    password: str
    device_name: str
    device_id: str

class LogoutRequest(BaseModel):
    token: str
    device_name: str
    device_id: str

class UserRequest(BaseModel):
    token: str
    device_name: str
    device_id: str

# 位置ID映射
class LocationID:
    CHANGAN = 1001     # 长安
    AOLAIGUO = 1002    # 傲来国
    TIANGONG = 1003    # 天宫
    LINGSHAN = 1004    # 灵山
    DIFU = 1005        # 地府
    HUOYANSHAN = 1006  # 火焰山

# 种族初始属性配置
RACE_INITIAL_STATS = {
    Race.HUMAN: {
        "max_hp": 100,
        "max_mp": 0,
        "physical_attack": 10,
        "magic_attack": 0,
        "physical_defense": 10,
        "magic_defense": 0
    },
    Race.IMMORTAL: {
        "max_hp": 120,
        "max_mp": 100,
        "physical_attack": 5,
        "magic_attack": 10,
        "physical_defense": 0,
        "magic_defense": 5
    },
    Race.GHOST: {
        "max_hp": 80,
        "max_mp": 150,
        "physical_attack": 0,
        "magic_attack": 15,
        "physical_defense": 10,
        "magic_defense": 0
    },
    Race.MONSTER: {
        "max_hp": 150,
        "max_mp": 0,
        "physical_attack": 10,
        "magic_attack": 5,
        "physical_defense": 5,
        "magic_defense": 5
    }
}

# 势力好感度配置
RACE_FAVOR = {
    Race.HUMAN: {
        LocationID.CHANGAN: 20,
        LocationID.AOLAIGUO: 20
    },
    Race.IMMORTAL: {
        LocationID.TIANGONG: 20,
        LocationID.LINGSHAN: 20
    },
    Race.GHOST: {
        LocationID.DIFU: 20
    },
    Race.MONSTER: {
        LocationID.HUOYANSHAN: 20
    }
}

# 创建角色请求模型
class CreateCharacterRequest(BaseModel):
    name: str
    race: Race
    location_id: int

# CRUD路由
@crud_router.post("/{model_name}")
async def create_item(
    request: Request,
    model_name: str,
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    try:
        body = await request.body()
        logger.debug(f"创建{model_name}请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"Body: {body.decode()}")
        
        crud = CRUDRegister.get(model_name)
        if not crud:
            logger.error(f"模型不存在: {model_name}")
            raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
        
        result = crud.create(db=db, data=data)
        logger.debug(f"创建{model_name}成功: {result}")
        return result
    except HTTPException:
        raise
    except sqlalchemy.exc.IntegrityError as e:
        error_msg = str(e.orig)
        if "Duplicate entry" in error_msg:
            field = error_msg.split("key '")[1].split("'")[0].split('.')[-1]
            value = error_msg.split("'")[1]
            detail = f"字段 {field} 的值 '{value}' 已存在"
        else:
            detail = "数据完整性错误"
        logger.error(f"创建{model_name}失败: {error_msg}")
        raise HTTPException(status_code=400, detail=detail)
    except Exception as e:
        logger.error(f"创建{model_name}失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail=f"创建失败: {str(e)}"
        )

@crud_router.get("/{model_name}/{item_id}")
async def read_item(
    request: Request,
    model_name: str,
    item_id: int,
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"读取{model_name}请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"查询参数: model_name={model_name}, item_id={item_id}")
        
        crud = CRUDRegister.get(model_name)
        if not crud:
            logger.error(f"模型不存在: {model_name}")
            raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
        
        item = crud.get(db=db, id=item_id)
        if not item:
            logger.error(f"项目不存在: {model_name} id={item_id}")
            raise HTTPException(status_code=404, detail="Item not found")
        
        logger.debug(f"读取{model_name}成功: {item}")
        return item
    except Exception as e:
        logger.error(f"读取{model_name}失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise

@crud_router.get("/{model_name}")
async def read_items(
    request: Request,
    model_name: str,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"批量读取{model_name}请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"查询参数: model_name={model_name}, skip={skip}, limit={limit}")
        
        crud = CRUDRegister.get(model_name)
        if not crud:
            logger.error(f"模型不存在: {model_name}")
            raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
        
        items = crud.get_multi(db=db, skip=skip, limit=limit)
        logger.debug(f"批量读取{model_name}成功: 获取到{len(items)}条记录")
        return items
    except Exception as e:
        logger.error(f"批量读取{model_name}失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise

@crud_router.put("/{model_name}/{item_id}")
async def update_item(
    request: Request,
    model_name: str,
    item_id: int,
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    try:
        body = await request.body()
        logger.debug(f"更新{model_name}请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"Body: {body.decode()}")
        
        crud = CRUDRegister.get(model_name)
        if not crud:
            logger.error(f"模型不存在: {model_name}")
            raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
        
        item = crud.update(db=db, id=item_id, data=data)
        if not item:
            logger.error(f"项目不存在: {model_name} id={item_id}")
            raise HTTPException(status_code=404, detail="Item not found")
        
        logger.debug(f"更新{model_name}成功: {item}")
        return item
    except HTTPException:
        raise
    except sqlalchemy.exc.IntegrityError as e:
        error_msg = str(e.orig)
        if "Duplicate entry" in error_msg:
            field = error_msg.split("key '")[1].split("'")[0].split('.')[-1]
            value = error_msg.split("'")[1]
            detail = f"字段 {field} 的值 '{value}' 已存在"
        else:
            detail = "数据完整性错误"
        logger.error(f"更新{model_name}失败: {error_msg}")
        raise HTTPException(status_code=400, detail=detail)
    except Exception as e:
        logger.error(f"更新{model_name}失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail=f"更新失败: {str(e)}"
        )

@crud_router.delete("/{model_name}/{item_id}")
async def delete_item(
    request: Request,
    model_name: str,
    item_id: int,
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"删除{model_name}请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"参数: model_name={model_name}, item_id={item_id}")
        
        crud = CRUDRegister.get(model_name)
        if not crud:
            logger.error(f"模型不存在: {model_name}")
            raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
        
        item = crud.remove(db=db, id=item_id)
        if not item:
            logger.error(f"项目不存在: {model_name} id={item_id}")
            raise HTTPException(status_code=404, detail="Item not found")
        
        logger.debug(f"删除{model_name}成功: id={item_id}")
        return {"status": "success", "message": f"Item {item_id} deleted"}
    except HTTPException:
        raise
    except sqlalchemy.exc.IntegrityError as e:
        error_msg = str(e.orig)
        detail = "数据完整性错误，可能存在关联数据"
        logger.error(f"删除{model_name}失败: {error_msg}")
        raise HTTPException(status_code=400, detail=detail)
    except Exception as e:
        logger.error(f"删除{model_name}失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail=f"删除失败: {str(e)}"
        )

# 认证路由
@auth_router.post("/login",
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
        token = create_token(db, account.id, login_data.device_name, login_data.device_id)
        if not token:
            return response(
                code=ResponseCode.LOGIN_FAILED,
                message="TOKEN_CREATE_FAILED"
            )
            
        logger.debug(f"创建token成功: {token[:10]}...")
        
        # 更新最后登录时间
        account.last_login_at = datetime.now()
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

@auth_router.post("/logout",
    summary="用户登出",
    description="""
    用户登出接口，使当前设备的token失效。
    
    权限要求：
    - 需要有效的Token
    
    请求参数：
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
    
    可能的错误码：
    - 1004: Token无效
    - 1006: 设备不匹配
    - 1008: 登出失败
    
    请求示例：
    ```json
    {
        "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
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
    logout_data: LogoutRequest,
    db: Session = Depends(get_db)
):
    try:
        body = await request.body()
        logger.debug(f"登出请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"Body: {body.decode()}")
        
        # 验证设备信息
        if not logout_data.device_id or not logout_data.device_name:
            return response(
                code=ResponseCode.INVALID_DEVICE_DATA,
                message="INVALID_DEVICE_DATA"
            )
            
        # 验证token和设备是否匹配
        token_record = db.query(UserToken).filter(
            UserToken.token == logout_data.token,
            UserToken.device_id == logout_data.device_id,
            UserToken.device_name == logout_data.device_name,
            UserToken.expired == 0
        ).first()
        
        if not token_record:
            return response(
                code=ResponseCode.DEVICE_NOT_MATCH,
                message="DEVICE_NOT_MATCH"
            )
        
        # 使token失效
        if invalidate_token(db, logout_data.token):
            logger.debug(f"登出成功: token={logout_data.token[:10]}...")
            return response(data={
                "status": "success",
                "message": "Logged out successfully"
            })
        
        logger.error(f"登出失败，无效token: {logout_data.token[:10]}...")
        return response(
            code=ResponseCode.TOKEN_INVALID,
            message="TOKEN_INVALID"
        )
        
    except Exception as e:
        logger.error(f"登出过程发生异常: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return response(
            code=ResponseCode.LOGOUT_FAILED,
            message="LOGOUT_FAILED"
        )

# 创建公共请求头模型
class CommonHeaders:
    def __init__(
        self,
        token: str = Header(..., description="认证token"),
        device_name: str = Header(..., description="设备名称"),
        device_id: str = Header(..., description="设备ID"),
        service_code: str = Header(..., description="服务代码：web-网页端，game-游戏端")
    ):
        self.token = token
        self.device_name = device_name
        self.device_id = device_id
        self.service_code = service_code

# 认证依赖
async def get_current_user(
    request: Request,
    commons: CommonHeaders = Depends(),
    db: Session = Depends(get_db)
) -> Account:
    try:
        logger.debug(f"验证用户请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"Service Code: {commons.service_code}")
        
        # 验证设备信息
        if not commons.device_id or not commons.device_name:
            raise HTTPException(
                status_code=400,
                detail=response(
                    code=ResponseCode.INVALID_DEVICE_DATA,
                    message="INVALID_DEVICE_DATA"
                )
            )
        
        # 验证token是否存在且未过期
        token_record = db.query(UserToken).filter(
            UserToken.token == commons.token,
            UserToken.device_name == commons.device_name,
            UserToken.device_id == commons.device_id,
            UserToken.expired == False
        ).first()
        
        if not token_record:
            raise HTTPException(
                status_code=401,
                detail=response(
                    code=ResponseCode.DEVICE_NOT_MATCH,
                    message="DEVICE_NOT_MATCH"
                )
            )
            
        # 验证JWT
        try:
            payload = jwt.decode(commons.token, SECRET_KEY, algorithms=[ALGORITHM])
            account_id = int(payload.get("sub"))  # 确保转换为整数
            if account_id is None:
                raise HTTPException(
                    status_code=401,
                    detail=response(
                        code=ResponseCode.TOKEN_INVALID,
                        message="TOKEN_INVALID"
                    )
                )
        except jwt.ExpiredSignatureError:
            # 令牌过期，标记为已过期
            token_record.expired = True
            db.commit()
            raise HTTPException(
                status_code=401,
                detail=response(
                    code=ResponseCode.TOKEN_EXPIRED,
                    message="TOKEN_EXPIRED"
                )
            )
        except jwt.PyJWTError:  # 修改这里，使用 PyJWTError 替代 JWTError
            raise HTTPException(
                status_code=401,
                detail=response(
                    code=ResponseCode.TOKEN_INVALID,
                    message="TOKEN_INVALID"
                )
            )
            
        # 获取用户
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise HTTPException(
                status_code=404,
                detail=response(
                    code=ResponseCode.ACCOUNT_NOT_FOUND,
                    message="ACCOUNT_NOT_FOUND"
                )
            )
            
        # 检查账号状态
        if account.is_deleted:
            raise HTTPException(
                status_code=403,
                detail=response(
                    code=ResponseCode.ACCOUNT_DISABLED,
                    message="ACCOUNT_DELETED"
                )
            )
            
        if account.status == 2:  # 已封禁
            raise HTTPException(
                status_code=403,
                detail=response(
                    code=ResponseCode.ACCOUNT_DISABLED,
                    message="ACCOUNT_BANNED"
                )
            )
            
        if account.status == 0:  # 未激活
            raise HTTPException(
                status_code=403,
                detail=response(
                    code=ResponseCode.ACCOUNT_DISABLED,
                    message="ACCOUNT_NOT_ACTIVATED"
                )
            )
            
        # 更新最后活跃时间
        token_record.last_active = datetime.utcnow()
        db.commit()
        
        logger.debug(f"获取账号成功: {account.username} (ID: {account.id})")
        return account
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取当前用户时发生异常: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=response(
                code=ResponseCode.SYSTEM_ERROR,
                message="SYSTEM_ERROR"
            )
        )

# 添加 datetime 序列化处理函数
def datetime_handler(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f'Object of type {type(obj)} is not JSON serializable')

# 用户路由
@user_router.get("/me",
    summary="获取当前用户信息",
    description="""
    获取当前登录用户的详细信息，包括账号信息和当前角色信息。
    
    权限要求：
    - 需要有效的Token
    
    返回数据：
    - id: 用户ID
      - 类型：integer
      - 说明：用户的唯一标识符
      
    - username: 用户名
      - 类型：string
      - 说明：用户的登录名
      
    - wallet_address: 钱包地址
      - 类型：string
      - 说明：用户绑定的钱包地址
      - 可能为null
      
    - status: 账号状态
      - 类型：integer
      - 说明：0-未激活，1-正常，2-已封禁
      
    - email: 邮箱
      - 类型：string
      - 说明：用户的邮箱地址
      - 可能为null
      
    - role: 用户角色
      - 类型：string
      - 说明：user-普通用户，admin-管理员
      
    - avatar_url: 头像URL
      - 类型：string
      - 说明：用户头像的URL地址
      - 可能为null
      
    - oml_coin: OML币数量
      - 类型：integer
      - 说明：用户拥有的OML币数量
      
    - user_setting: 用户设置
      - 类型：string
      - 说明：用户的个性化设置
      - 可能为null
      
    - character: 当前角色信息
      - 类型：object
      - 说明：用户当前的游戏角色信息
      - 可能为null
    
    可能的错误码：
    - 401: Token无效
    - 404: 用户不存在
    
    成功返回示例：
    ```json
    {
        "code": 200,
        "message": "SUCCESS",
        "data": {
            "id": 1001,
            "username": "test_user",
            "wallet_address": "0x123...",
            "status": 1,
            "email": "test@example.com",
            "role": "user",
            "avatar_url": "https://...",
            "oml_coin": 100,
            "user_setting": "{...}",
            "character": {
                "id": 1,
                "name": "角色名",
                "race": 1,
                "level": 1,
                ...
            }
        }
    }
    ```
    
    错误返回示例：
    ```json
    {
        "code": 401,
        "message": "TOKEN_INVALID",
        "data": null
    }
    ```
    
    注意事项：
    1. character字段可能为null（用户未创建角色时）
    2. 某些字段可能为null（用户未设置时）
    3. 返回的角色信息为当前未删除的角色
    """
)
async def read_me(
    request: Request,
    commons: CommonHeaders = Depends(),
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"获取用户信息请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        
        # 获取当前未删除的角色
        current_character = db.query(Character).filter(
            Character.account_id == current_user.id,
            Character.is_deleted == 0
        ).first()
        
        if not current_character:
            return response(
                code=ResponseCode.CHARACTER_NOT_FOUND,
                message="CHARACTER_NOT_FOUND"
            )
        
        response_data = {
            "id": current_user.id,
            "username": current_user.username,
            "wallet_address": current_user.wallet_address,
            "status": current_user.status,
            "email": current_user.email,
            "role": current_user.role.value if current_user.role else None,
            "avatar_url": current_user.avatar_url,
            "created_at": current_user.created_at,
            "oml_coin": current_user.oml_coin,
            "user_setting": current_user.user_setting,
            "character": format_character_data(current_character)
        }
        
        logger.debug(f"获取用户信息成功: {json.dumps(response_data, ensure_ascii=False, default=datetime_handler)}")
        return response(data=response_data)
        
    except Exception as e:
        logger.error(f"获取用户信息失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return response(
            code=ResponseCode.SYSTEM_ERROR,
            message="SYSTEM_ERROR"
        )

@user_router.get("/characters",
    summary="获取用户角色列表",
    description="""
    获取当前用户的所有游戏角色列表。
    
    权限要求：
    - 需要有效的Token
    
    返回数据：
    角色列表，每个角色包含以下信息：
    - id: 角色ID
      - 类型：integer
      - 说明：角色的唯一标识符
      
    - name: 角色名称
      - 类型：string
      - 说明：角色的名称
      
    - race: 种族
      - 类型：integer
      - 说明：1-人族，2-妖族，3-鬼族，4-仙族
      
    - level: 等级
      - 类型：integer
      - 说明：角色当前等级
      
    - exp: 经验值
      - 类型：integer
      - 说明：当前经验值
      
    - max_exp: 升级所需经验
      - 类型：integer
      - 说明：升到下一级所需的经验值
      
    - sect_name: 宗门名称
      - 类型：string
      - 说明：所属宗门名称
      - 可能为null
      
    - current_location: 当前位置
      - 类型：string
      - 说明：角色当前所在位置
    
    可能的错误码：
    - 401: Token无效
    - 404: 用户不存在
    
    成功返回示例：
    ```json
    {
        "code": 200,
        "message": "SUCCESS",
        "data": [
            {
                "id": 1,
                "name": "角色1",
                "race": 1,
                "level": 10,
                "exp": 1000,
                "max_exp": 2000,
                "sect_name": "青云门",
                "current_location": "青云山",
                "max_hp": 1000,
                "current_hp": 1000,
                "max_mp": 500,
                "current_mp": 500,
                "physical_attack": 100,
                "magic_attack": 80,
                "physical_defense": 50,
                "magic_defense": 40,
                "speed": 10,
                "critical_rate": 0.05,
                "critical_damage": 1.5,
                "hit_rate": 0.95,
                "dodge_rate": 0.05,
                "morality": 0,
                "max_stamina": 100,
                "current_stamina": 100,
                "copper_coins": 1000,
                "created_at": "2024-01-01T00:00:00",
                "last_login": "2024-01-02T00:00:00",
                "last_logout": "2024-01-02T01:00:00"
            }
        ]
    }
    ```
    
    错误返回示例：
    ```json
    {
        "code": 401,
        "message": "TOKEN_INVALID",
        "data": null
    }
    ```
    
    注意事项：
    1. 只返回未删除的角色
    2. 目前系统限制每个账号只能创建一个角色
    3. 返回的列表可能为空（未创建角色时）
    """
)
async def read_user_characters(
    request: Request,
    commons: CommonHeaders = Depends(),
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"获取用户角色列表请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        
        # 只获取当前未删除的角色
        character = db.query(Character).filter(
            Character.account_id == current_user.id,
            Character.is_deleted == 0
        ).first()
        
        if not character:
            return response(
                code=ResponseCode.CHARACTER_NOT_FOUND,
                message="CHARACTER_NOT_FOUND"
            )
            
        char_list = [format_character_data(character)] if character else []
            
        logger.debug(f"角色列表: {json.dumps(char_list, ensure_ascii=False)}")
        return response(data=char_list)
        
    except Exception as e:
        logger.error(f"获取用户角色列表失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return response(
            code=ResponseCode.SYSTEM_ERROR,
            message="SYSTEM_ERROR"
        )

@user_router.get("/devices",
    summary="获取用户设备列表",
    description="""
    获取当前用户的所有活跃设备列表。
    
    权限要求：
    - 需要有效的Token
    
    返回数据：
    设备列表，每个设备包含以下信息：
    - device_name: 设备名称
      - 类型：string
      - 说明：设备的显示名称，如"iPhone 12"、"Chrome浏览器"等
      
    - device_id: 设备ID
      - 类型：string
      - 说明：设备的唯一标识符
      
    - last_active: 最后活跃时间
      - 类型：string (ISO 8601格式的日期时间)
      - 说明：设备最后一次活跃的时间
      
    - created_at: 首次登录时间
      - 类型：string (ISO 8601格式的日期时间)
      - 说明：设备首次登录的时间
    
    可能的错误码：
    - 401: Token无效
    - 404: 用户不存在
    - 1012: 设备不存在
    
    成功返回示例：
    ```json
    {
        "code": 200,
        "message": "SUCCESS",
        "data": [
            {
                "device_name": "Chrome Browser",
                "device_id": "browser-uuid-123",
                "last_active": "2024-01-02T10:30:00",
                "created_at": "2024-01-01T00:00:00"
            },
            {
                "device_name": "iPhone 12",
                "device_id": "iphone-uuid-456",
                "last_active": "2024-01-02T09:15:00",
                "created_at": "2024-01-01T12:00:00"
            }
        ]
    }
    ```
    
    错误返回示例：
    ```json
    {
        "code": 1012,
        "message": "DEVICE_NOT_FOUND",
        "data": null
    }
    ```
    
    注意事项：
    1. 只返回未过期的设备token
    2. last_active时间会在每次请求时更新
    3. 设备列表可能为空（未登录任何设备时）
    """
)
async def read_user_devices(
    request: Request,
    commons: CommonHeaders = Depends(),
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"获取用户设备列表请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        
        active_tokens = db.query(UserToken).filter(
            UserToken.account_id == current_user.id,
            UserToken.expired == 0
        ).all()
        
        if not active_tokens:
            return response(
                code=ResponseCode.DEVICE_NOT_FOUND,
                message="DEVICE_NOT_FOUND"
            )
        
        logger.debug(f"获取到 {len(active_tokens)} 个活跃设备")
        
        response_data = [
            {
                "device_name": token.device_name,
                "device_id": token.device_id,
                "last_active": token.last_active,
                "created_at": token.created_at
            }
            for token in active_tokens
        ]
        
        logger.debug(f"设备列表: {json.dumps(response_data, ensure_ascii=False, default=datetime_handler)}")
        return response(data=response_data)
        
    except Exception as e:
        logger.error(f"获取用户设备列表失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return response(
            code=ResponseCode.SYSTEM_ERROR,
            message="SYSTEM_ERROR"
        )

# 角色路由
@character_router.post("/create",
    summary="创建角色",
    description="""
    为当前用户创建一个新的游戏角色。
    
    权限要求：
    - 需要有效的Token
    - 账号未创建过角色
    
    请求参数：
    - name: 角色名称
      - 类型：string
      - 必填：是
      - 长度：2-20个字符
      - 说明：角色的显示名称，必须唯一
      
    - race: 种族
      - 类型：integer
      - 必填：是
      - 取值：
        - 1: 人族
        - 2: 妖族
        - 3: 鬼族
        - 4: 仙族
      
    - location_id: 出生地点ID
      - 类型：integer
      - 必填：是
      - 取值：
        - 1001: 长安
        - 1002: 傲来国
        - 1003: 天宫
        - 1004: 灵山
        - 1005: 地府
        - 1006: 火焰山
    
    可能的错误码：
    - 400: 参数错误
    - 401: Token无效
    - 404: 用户不存在
    - 2003: 角色数量达到上限
    - 2004: 角色名已存在
    
    请求示例：
    ```json
    {
        "name": "测试角色",
        "race": 1,
        "location_id": 1001
    }
    ```
    
    成功返回示例：
    ```json
    {
        "code": 200,
        "message": "SUCCESS",
        "data": {
            "message": "角色创建成功",
            "character_id": 1001,
            "name": "测试角色",
            "race": 1,
            "location": 1001
        }
    }
    ```
    
    错误返回示例：
    ```json
    {
        "code": 2004,
        "message": "CHARACTER_NAME_EXISTS",
        "data": null
    }
    ```
    
    注意事项：
    1. 每个账号只能创建一个角色
    2. 角色名必须唯一
    3. 不同种族有不同的初始属性
    4. 不同种族有不同的出生地点限制
    5. 创建角色时会自动创建相关的初始数据（装备栏、好感度等）
    """
)
async def create_character(
    request: Request,
    data: CreateCharacterRequest,
    commons: CommonHeaders = Depends(),
    db: Session = Depends(get_db)
):
    try:
        # 验证用户身份
        account = await get_current_user(request, commons, db)
        
        # 检查是否已有未删除的角色
        existing_character = db.query(Character).filter(
            Character.account_id == account.id,
            Character.is_deleted == 0
        ).first()
        
        if existing_character:
            return response(
                code=ResponseCode.CHARACTER_MAX_LIMIT,
                message="CHARACTER_MAX_LIMIT"
            )
        
        # 检查角色名是否已存在
        name_exists = db.query(Character).filter(
            Character.name == data.name,
            Character.is_deleted == 0
        ).first()
        if name_exists:
            return response(
                code=ResponseCode.CHARACTER_NAME_EXISTS,
                message="CHARACTER_NAME_EXISTS"
            )
            
        # 验证种族是否有效
        if data.race not in Race:
            return response(
                code=ResponseCode.INVALID_RACE,
                message="INVALID_RACE"
            )
            
        # 验证出生地点是否有效
        valid_locations = [
            LocationID.CHANGAN,
            LocationID.AOLAIGUO,
            LocationID.TIANGONG,
            LocationID.LINGSHAN,
            LocationID.DIFU,
            LocationID.HUOYANSHAN
        ]
        if data.location_id not in valid_locations:
            return response(
                code=ResponseCode.INVALID_LOCATION,
                message="INVALID_LOCATION"
            )
        
        # 获取种族初始属性
        try:
            initial_stats = RACE_INITIAL_STATS[data.race]
        except KeyError:
            return response(
                code=ResponseCode.INVALID_RACE,
                message="RACE_STATS_NOT_FOUND"
            )
        
        # 创建角色
        character = Character(
            account_id=account.id,
            name=data.name,
            race=data.race,
            current_location=data.location_id,
            # 设置初始属性
            max_hp=initial_stats["max_hp"],
            current_hp=initial_stats["max_hp"],
            max_mp=initial_stats["max_mp"],
            current_mp=initial_stats["max_mp"],
            physical_attack=initial_stats["physical_attack"],
            magic_attack=initial_stats["magic_attack"],
            physical_defense=initial_stats["physical_defense"],
            magic_defense=initial_stats["magic_defense"],
            # 设置其他默认值
            level=1,
            exp=0,
            max_exp=100,
            copper_coins=0,
            created_at=datetime.utcnow(),
            last_login=datetime.utcnow(),
            is_deleted=0
        )
        
        db.add(character)
        db.flush()  # 获取character.id
        
        # 创建初始好感度记录
        if data.race in RACE_FAVOR:
            for location_id, favor_value in RACE_FAVOR[data.race].items():
                favor_record = FavorRecord(
                    character_id=character.id,
                    target_type=FavorTargetType.FACTION,
                    target_id=location_id,
                    favor_value=favor_value,
                    level=1,
                    current_exp=0,
                    daily_interaction_count=0,
                    last_reset_time=datetime.utcnow(),
                    created_at=datetime.utcnow()
                )
                db.add(favor_record)
        
        # 创建装备栏
        equipment = CharacterEquipment(
            character_id=character.id
        )
        db.add(equipment)
        
        db.commit()
        
        return response(data={
            "message": "角色创建成功",
            "character_id": character.id,
            "name": character.name,
            "race": character.race.value,
            "location": character.current_location
        })
        
    except Exception as e:
        logger.error(f"创建角色失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        db.rollback()
        return response(
            code=ResponseCode.SYSTEM_ERROR,
            message="SYSTEM_ERROR"
        )

# 添加玩家数据查询路由
class TableRequest(BaseModel):
    table_name: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "table_name": "Character"
            }
        }

@character_router.post("/query_character_data",
    summary="查询角色相关数据",
    description="""
    查询当前角色的相关数据表信息。
    
    权限要求：
    - 需要有效的Token
    - 需要有效的角色
    
    请求参数：
    - table_name: 表名
      - 类型：string
      - 必填：是
      - 取值：
        - Character: 角色基础信息
        - Inventory: 背包物品
        - CharacterEquipment: 装备信息
        - CharacterQuest: 任务信息
        - FavorRecord: 好感度记录
        - Mail: 邮件信息
    
    可能的错误码：
    - 400: 参数错误
    - 401: Token无效
    - 404: 角色不存在
    - 2001: 角色不存在
    - 2002: 角色已删除
    
    请求示例：
    ```json
    {
        "table_name": "Character"
    }
    ```
    
    成功返回示例：
    ```json
    {
        "code": 200,
        "message": "SUCCESS",
        "data": {
            "table": "Character",
            "character_id": 1001,
            "total": 1,
            "data": [
                {
                    "id": 1001,
                    "name": "测试角色",
                    "race": 1,
                    "level": 10,
                    ...
                }
            ]
        }
    }
    ```
    
    错误返回示例：
    ```json
    {
        "code": 2001,
        "message": "CHARACTER_NOT_FOUND",
        "data": null
    }
    ```
    
    注意事项：
    1. 只能查询与当前角色相关的数据
    2. 不同表返回的字段结构不同
    3. 只返回未删除的记录
    4. 某些表可能返回空列表（如未接任务时的任务列表）
    """
)
async def query_character_data(
    request: Request,
    data: TableRequest,
    commons: CommonHeaders = Depends(),
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"查询玩家数据请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"请求表名: {data.table_name}")
        
        # 获取当前角色
        character = db.query(Character).filter(
            Character.account_id == current_user.id,
            Character.is_deleted == 0
        ).first()
        
        if not character:
            return response(
                code=ResponseCode.CHARACTER_NOT_FOUND,
                message="CHARACTER_NOT_FOUND"
            )
            
        # 获取对应的模型类
        if data.table_name not in CHARACTER_RELATED_MODELS:
            return response(
                code=ResponseCode.PARAM_ERROR,
                message="INVALID_TABLE_NAME"
            )
            
        model_class = CHARACTER_RELATED_MODELS[data.table_name]
        
        # 查询数据
        if data.table_name == 'Character':
            # Character表特殊处理
            results = [character]
        else:
            # 其他表通过character_id关联查询
            query = db.query(model_class).filter(
                model_class.character_id == character.id,
                model_class.is_deleted == 0
            )
            
            # 特殊处理：如果是装备表，只返回一条记录
            if data.table_name == "CharacterEquipment":
                results = query.first()
                if results:
                    results = [results]
                else:
                    results = []
            else:
                results = query.all()
            
        # 处理结果
        response_data = []
        for item in results:
            item_dict = {}
            for column in item.__table__.columns:
                value = getattr(item, column.name)
                # 处理特殊类型
                if isinstance(value, datetime):
                    value = value.isoformat()
                elif isinstance(value, Enum):
                    value = value.value
                item_dict[column.name] = value
            response_data.append(item_dict)
            
        logger.debug(f"查询到 {len(response_data)} 条记录")
        return response(data={
            "table": data.table_name,
            "character_id": character.id,
            "total": len(response_data),
            "data": response_data
        })
        
    except Exception as e:
        logger.error(f"查询玩家数据失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return response(
            code=ResponseCode.SYSTEM_ERROR,
            message="SYSTEM_ERROR"
        )

# 添加AI路由
@app.post("/api/chat", response_model=ChatResponse, tags=["AI对话"])
async def chat(request: ChatRequest):
    """
    AI对话接口
    
    - **messages**: 对话消息列表，包含role和content
    - **temperature**: 温度参数，控制响应的随机性（可选，默认0.7）
    - **max_tokens**: 最大token数（可选）
    """
    return await ai_service.chat_completion(request)

# 添加装备操作请求模型
class EquipmentOperationType(str, Enum):
    EQUIP = "equip"      # 穿上装备
    UNEQUIP = "unequip"  # 脱下装备

class EquipmentSlotType(int, Enum):
    WEAPON = 1    # 武器
    HAT = 2       # 帽子
    CLOTH = 3     # 衣服
    ORNAMENT = 4  # 饰品
    PENDANT = 5   # 挂坠
    SHOES = 6     # 鞋子

class EquipmentOperationRequest(BaseModel):
    slot_type: EquipmentSlotType
    item_id: Optional[int] = None  # 穿装备时需要，脱装备时可以为空
    operation: EquipmentOperationType

@character_router.post("/equipment/operate")
async def operate_equipment(
    request: Request,
    data: EquipmentOperationRequest,
    commons: CommonHeaders = Depends(),
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"装备操作请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"操作数据: {data.dict()}")
        
        # 获取当前角色
        character = db.query(Character).filter(
            Character.account_id == current_user.id,
            Character.is_deleted == 0
        ).first()
        
        if not character:
            return response(
                code=ResponseCode.CHARACTER_NOT_FOUND,
                message="CHARACTER_NOT_FOUND"
            )
            
        # 获取角色装备信息
        equipment = db.query(CharacterEquipment).filter(
            CharacterEquipment.character_id == character.id
        ).first()
        
        if not equipment:
            return response(
                code=ResponseCode.CHARACTER_NOT_FOUND,
                message="EQUIPMENT_NOT_FOUND"
            )
            
        # 槽位ID映射
        slot_map = {
            EquipmentSlotType.WEAPON: "weapon_id",
            EquipmentSlotType.HAT: "hat_id",
            EquipmentSlotType.CLOTH: "cloth_id",
            EquipmentSlotType.ORNAMENT: "ornament_id",
            EquipmentSlotType.PENDANT: "pendant_id",
            EquipmentSlotType.SHOES: "shoes_id"
        }
        
        if data.slot_type not in slot_map:
            return response(
                code=ResponseCode.INVALID_ITEM_DATA,
                message="INVALID_SLOT_TYPE"
            )
        
        slot_field = slot_map[data.slot_type]
        
        if data.operation == EquipmentOperationType.EQUIP:
            if not data.item_id:
                return response(
                    code=ResponseCode.INVALID_ITEM_DATA,
                    message="ITEM_ID_REQUIRED"
                )
                
            # 获取物品静态数据
            item_static_data = static_data.get_item_data(data.item_id)
            if not item_static_data:
                return response(
                    code=ResponseCode.ITEM_NOT_FOUND,
                    message="ITEM_CONFIG_NOT_FOUND"
                )
                
            # 检查物品类型是否匹配槽位
            if item_static_data["type"] != data.slot_type.value:
                return response(
                    code=ResponseCode.INVALID_ITEM_DATA,
                    message="ITEM_TYPE_NOT_MATCH"
                )
                
            # 检查物品是否存在且属于该角色
            item = db.query(Inventory).filter(
                Inventory.item_id == data.item_id,
                Inventory.character_id == character.id,
                Inventory.is_deleted == 0
            ).first()
            
            if not item:
                return response(
                    code=ResponseCode.ITEM_NOT_FOUND,
                    message="ITEM_NOT_FOUND"
                )
                
            # 检查物品是否已经装备
            if item.equipped == 1:
                return response(
                    code=ResponseCode.ITEM_EQUIPPED,
                    message="ITEM_ALREADY_EQUIPPED"
                )
                
            # 如果该槽位已有装备，先卸下
            current_equipped = getattr(equipment, slot_field)
            if current_equipped:
                # 获取当前装备的物品并更新状态
                current_item = db.query(Inventory).filter(
                    Inventory.id == current_equipped,
                    Inventory.is_deleted == 0
                ).first()
                if current_item:
                    current_item.equipped = 0
                
            # 装备新物品
            setattr(equipment, slot_field, item.id)  # 使用inventory表的id
            item.equipped = 1  # 标记为已装备
            
        else:  # UNEQUIP
            # 获取当前装备的物品ID
            current_equipped = getattr(equipment, slot_field)
            if not current_equipped:
                return response(
                    code=ResponseCode.ITEM_NOT_EQUIPPED,
                    message="NO_ITEM_EQUIPPED"
                )
                
            # 获取当前装备的物品并更新状态
            current_item = db.query(Inventory).filter(
                Inventory.id == current_equipped,
                Inventory.is_deleted == 0
            ).first()
            if current_item:
                current_item.equipped = 0
                
            # 卸下装备
            setattr(equipment, slot_field, None)
            
        db.commit()
        
        # 返回更新后的装备信息
        equipped_items = {}
        for slot_type, field_name in slot_map.items():
            inventory_id = getattr(equipment, field_name)
            if inventory_id:
                inventory_item = db.query(Inventory).filter(
                    Inventory.id == inventory_id,
                    Inventory.is_deleted == 0
                ).first()
                if inventory_item:
                    static_info = static_data.get_item_data(inventory_item.item_id)
                    if not static_info:
                        return response(
                            code=ResponseCode.INVALID_ITEM_DATA,
                            message="ITEM_CONFIG_MISSING"
                        )
                    equipped_items[slot_type.value] = {
                        "inventory_id": inventory_id,
                        "item_id": inventory_item.item_id,
                        "name": static_info.get("name"),
                        "quality": static_info.get("quality"),
                        "attr": static_info.get("attr"),
                        "strengthen_level": inventory_item.strengthen_level,
                        "durability": inventory_item.durability
                    }
        
        return response(data={
            "status": "success",
            "message": f"装备{data.operation.value}成功",
            "operation": data.operation.value,
            "slot_type": data.slot_type.value,
            "item_id": data.item_id,
            "equipped_items": equipped_items
        })
        
    except Exception as e:
        logger.error(f"装备操作失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return response(
            code=ResponseCode.SYSTEM_ERROR,
            message="SYSTEM_ERROR"
        )

# 添加物品请求模型
class ItemEntry(BaseModel):
    item_id: int
    quantity: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "item_id": 1001,
                "quantity": 1
            }
        }

class ItemAddRequest(BaseModel):
    items: List[ItemEntry]
    
    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {"item_id": 1001, "quantity": 1},
                    {"item_id": 1002, "quantity": 5}
                ]
            }
        }

@character_router.post("/inventory/add",
    summary="添加物品到背包",
    description="""
    向角色背包中添加一个或多个物品。
    
    权限要求：
    - 需要有效的Token
    - 需要有效的角色
    
    请求参数：
    - items: 物品列表
      - 类型：array
      - 必填：是
      - 每个物品包含：
        - item_id: 物品ID
          - 类型：integer
          - 必填：是
          - 说明：物品的配置ID
        - quantity: 数量
          - 类型：integer
          - 必填：是
          - 说明：添加的数量
          - 范围：1-9999
    
    可能的错误码：
    - 400: 参数错误
    - 401: Token无效
    - 2001: 角色不存在
    - 3001: 物品不存在
    - 3007: 物品数据无效
    
    请求示例：
    ```json
    {
        "items": [
            {
                "item_id": 1001,
                "quantity": 1
            },
            {
                "item_id": 1002,
                "quantity": 5
            }
        ]
    }
    ```
    
    成功返回示例：
    ```json
    {
        "code": 200,
        "message": "SUCCESS",
        "data": {
            "status": "success",
            "message": "物品添加成功",
            "character_id": 1001,
            "added_items": [
                {
                    "item_id": 1001,
                    "name": "青铜剑",
                    "quantity": 1,
                    "total_quantity": 1,
                    "quality": 1,
                    "type": 1
                },
                {
                    "item_id": 1002,
                    "name": "回血药水",
                    "quantity": 5,
                    "total_quantity": 10,
                    "quality": 1,
                    "type": 8
                }
            ]
        }
    }
    ```
    
    错误返回示例：
    ```json
    {
        "code": 3001,
        "message": "ITEM_NOT_FOUND",
        "data": null
    }
    ```
    
    注意事项：
    1. 如果物品已存在，会增加数量
    2. 新物品的初始属性：
       - 强化等级：0
       - 耐久度：100
       - 绑定状态：0（未绑定）
       - 额外属性：空
    3. 每个物品的数量必须大于0且不超过9999
    4. 返回的total_quantity是添加后的总数量
    """
)
async def add_items_to_inventory(
    request: Request,
    data: ItemAddRequest,
    commons: CommonHeaders = Depends(),
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"添加物品请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"操作数据: {data.dict()}")
        
        # 获取当前角色
        character = db.query(Character).filter(
            Character.account_id == current_user.id,
            Character.is_deleted == 0
        ).first()
        
        if not character:
            return response(
                code=ResponseCode.CHARACTER_NOT_FOUND,
                message="CHARACTER_NOT_FOUND"
            )
            
        added_items = []
        for item_data in data.items:
            # 验证数量是否合法
            if not 0 < item_data.quantity <= 9999:
                return response(
                    code=ResponseCode.INVALID_ITEM_DATA,
                    message="INVALID_ITEM_QUANTITY"
                )
            
            # 验证物品是否存在于配置中
            item_config = static_data.get_item_data(item_data.item_id)
            if not item_config:
                return response(
                    code=ResponseCode.ITEM_NOT_FOUND,
                    message=f"ITEM_NOT_FOUND: {item_data.item_id}"
                )
                
            # 查找是否已有该物品
            existing_item = db.query(Inventory).filter(
                Inventory.character_id == character.id,
                Inventory.item_id == item_data.item_id,
                Inventory.is_deleted == 0
            ).first()
            
            if existing_item:
                # 如果物品已存在，增加数量
                existing_item.quantity += item_data.quantity
                added_items.append({
                    "item_id": item_data.item_id,
                    "name": item_config["name"],
                    "quantity": item_data.quantity,
                    "total_quantity": existing_item.quantity,
                    "quality": item_config.get("quality", 0),
                    "type": item_config.get("type", 0)
                })
            else:
                # 创建新物品记录
                new_item = Inventory(
                    character_id=character.id,
                    item_id=item_data.item_id,
                    quantity=item_data.quantity,
                    strengthen_level=0,  # 新物品强化等级为0
                    durability=100,  # 新物品耐久度为100
                    bind_status=0,  # 新物品未绑定
                    extra_attributes={},  # 新物品无额外属性
                    bag_type=1  # 默认背包类型为1（普通背包）
                )
                db.add(new_item)
                added_items.append({
                    "item_id": item_data.item_id,
                    "name": item_config["name"],
                    "quantity": item_data.quantity,
                    "total_quantity": item_data.quantity,
                    "quality": item_config.get("quality", 0),
                    "type": item_config.get("type", 0)
                })
                
        db.commit()
        
        return response(data={
            "status": "success",
            "message": "物品添加成功",
            "character_id": character.id,
            "added_items": added_items
        })
        
    except Exception as e:
        logger.error(f"添加物品失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return response(
            code=ResponseCode.SYSTEM_ERROR,
            message="SYSTEM_ERROR"
        )

# 软删除请求模型
class SoftDeleteRequest(BaseModel):
    table_name: str
    record_id: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "table_name": "inventory",
                "record_id": 1
            }
        }

# 管理员软删除接口
@admin_router.post("/record/delete")
async def admin_soft_delete(
    request: Request,
    data: SoftDeleteRequest,
    commons: CommonHeaders = Depends(),
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    管理员软删除记录接口（需要管理员权限）
    
    可以删除任意表的记录，会记录删除时间和删除者
    """
    try:
        logger.debug(f"管理员删除请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"操作数据: {data.dict()}")
        
        # 验证管理员权限
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="需要管理员权限")
            
        # 获取对应的模型类
        if data.table_name not in model_all:
            raise HTTPException(status_code=400, detail=f"表名 {data.table_name} 不存在")
            
        model_class = globals()[data.table_name]
        if not issubclass(model_class, SoftDeleteMixin):
            raise HTTPException(status_code=400, detail=f"表 {data.table_name} 不支持软删除")
            
        # 查找记录
        record = db.query(model_class).filter(
            model_class.id == data.record_id,
            model_class.is_deleted == 0
        ).first()
        
        if not record:
            raise HTTPException(status_code=404, detail=f"未找到ID为 {data.record_id} 的记录或记录已删除")
            
        # 执行软删除
        record.is_deleted = 1
        record.deleted_at = datetime.utcnow()
        record.deleted_by = current_user.id
        
        db.commit()
        
        return {
            "status": "success",
            "message": "记录删除成功",
            "table": data.table_name,
            "record_id": data.record_id,
            "deleted_at": record.deleted_at,
            "deleted_by": record.deleted_by
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除记录失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="系统错误，请稍后重试")

# 用户软删除接口
@character_router.post("/record/delete")
async def user_soft_delete(
    request: Request,
    data: SoftDeleteRequest,
    commons: CommonHeaders = Depends(),
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    用户软删除记录接口
    
    只能删除与当前用户相关的记录，会记录删除时间和删除者
    """
    try:
        logger.debug(f"用户删除请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"操作数据: {data.dict()}")
        
        # 获取当前角色
        character = db.query(Character).filter(
            Character.account_id == current_user.id,
            Character.is_deleted == 0
        ).first()
        
        if not character:
            raise HTTPException(status_code=404, detail="未找到角色信息")
            
        # 验证表名是否在允许的列表中
        if data.table_name not in CHARACTER_RELATED_MODELS:
            raise HTTPException(status_code=400, detail=f"不允许删除 {data.table_name} 表的记录")
            
        model_class = globals()[data.table_name]
        if not issubclass(model_class, SoftDeleteMixin):
            raise HTTPException(status_code=400, detail=f"表 {data.table_name} 不支持软删除")
            
        # 首先检查记录是否存在
        record = db.query(model_class).filter(
            model_class.id == data.record_id,
            model_class.is_deleted == 0
        ).first()
        
        if not record:
            raise HTTPException(status_code=404, detail=f"记录不存在或已被删除")
            
        # 然后检查是否有权限删除
        if hasattr(model_class, 'character_id'):
            if record.character_id != character.id:
                raise HTTPException(status_code=403, detail="无权删除此记录")
        else:
            raise HTTPException(status_code=400, detail=f"表 {data.table_name} 不支持用户删除")
            
        # 执行软删除
        record.is_deleted = 1
        record.deleted_at = datetime.utcnow()
        record.deleted_by = current_user.id
        
        db.commit()
        
        return {
            "status": "success",
            "message": "记录删除成功",
            "table": data.table_name,
            "record_id": data.record_id,
            "deleted_at": record.deleted_at,
            "deleted_by": record.deleted_by
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除记录失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="系统错误，请稍后重试")

# 物品操作请求模型
class ItemOperationRequest(BaseModel):
    operation: ItemOperationType
    id: int
    quantity: Optional[int] = 1  # 使用时的数量，默认为1
    
    class Config:
        json_schema_extra = {
            "example": {
                "operation": ItemOperationType.EQUIP,
                "id": 1
            }
        }

@character_router.post("/item/operate",
    summary="物品操作",
    description="""
    对物品进行操作，包括装备、卸下、使用和丢弃。
    
    权限要求：
    - 需要有效的Token
    - 需要有效的角色
    
    请求参数：
    - operation: 操作类型
      - 类型：integer
      - 必填：是
      - 取值：
        - 0: 装备(EQUIP)
        - 1: 卸下(UNEQUIP)
        - 2: 使用(USE)
        - 3: 丢弃(DISCARD)
      
    - id: 物品ID
      - 类型：integer
      - 必填：是
      - 说明：背包中的物品ID（inventory表的id）
      
    - quantity: 使用数量
      - 类型：integer
      - 必填：否
      - 默认值：1
      - 说明：使用物品时的数量
      - 范围：1-9999
    
    可能的错误码：
    - 400: 参数错误
    - 401: Token无效
    - 2001: 角色不存在
    - 3001: 物品不存在
    - 3002: 物品数量不足
    - 3003: 物品已装备
    - 3004: 物品未装备
    - 3005: 物品不可使用
    - 3006: 物品绑定状态不符
    - 3007: 物品数据无效
    
    请求示例：
    1. 装备物品
    ```json
    {
        "operation": 0,
        "id": 1001
    }
    ```
    
    2. 使用物品
    ```json
    {
        "operation": 2,
        "id": 1001,
        "quantity": 5
    }
    ```
    
    成功返回示例：
    ```json
    {
        "code": 200,
        "message": "SUCCESS",
        "data": {
            "status": "success",
            "message": "物品操作成功",
            "operation": 0,
            "item_id": 1001,
            "character": {
                "current_hp": 1000,
                "max_hp": 1000,
                "current_mp": 500,
                "max_mp": 500,
                "physical_attack": 100,
                "magic_attack": 80,
                "physical_defense": 50,
                "magic_defense": 40
            }
        }
    }
    ```
    
    错误返回示例：
    ```json
    {
        "code": 3005,
        "message": "ITEM_NOT_USABLE",
        "data": null
    }
    ```
    
    注意事项：
    1. 装备操作：
       - 只能装备未装备的物品
       - 物品类型必须与装备槽位匹配
       - 装备后会更新角色属性
    2. 使用操作：
       - 只能使用消耗品（药品、食物等）
       - 使用后会更新物品数量
       - 数量为0时会自动删除物品
    3. 丢弃操作：
       - 已装备的物品不能丢弃
       - 丢弃后物品不可恢复
    """
)
async def operate_item(
    request: Request,
    data: ItemOperationRequest,
    commons: CommonHeaders = Depends(),
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"物品操作请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"操作数据: {data.dict()}")
        
        # 获取当前角色
        character = db.query(Character).filter(
            Character.account_id == current_user.id,
            Character.is_deleted == 0
        ).first()
        
        if not character:
            return response(
                code=ResponseCode.CHARACTER_NOT_FOUND,
                message="CHARACTER_NOT_FOUND"
            )
            
        # 获取物品信息
        inventory_item = db.query(Inventory).filter(
            Inventory.id == data.id,
            Inventory.character_id == character.id,
            Inventory.is_deleted == 0
        ).first()
        
        if not inventory_item:
            return response(
                code=ResponseCode.ITEM_NOT_FOUND,
                message="ITEM_NOT_FOUND"
            )
            
        # 获取物品静态数据
        item_static_data = static_data.get_item_data(inventory_item.item_id)
        if not item_static_data:
            return response(
                code=ResponseCode.INVALID_ITEM_DATA,
                message="ITEM_CONFIG_NOT_FOUND"
            )
            
        # 根据操作类型处理
        if data.operation in [ItemOperationType.EQUIP, ItemOperationType.UNEQUIP]:
            # 获取角色装备信息
            equipment = db.query(CharacterEquipment).filter(
                CharacterEquipment.character_id == character.id
            ).first()
            
            if not equipment:
                return response(
                    code=ResponseCode.CHARACTER_NOT_FOUND,
                    message="EQUIPMENT_NOT_FOUND"
                )
                
            await _operate_equipment(db, character, inventory_item, item_static_data, 
                                  data.operation, equipment)
                
        elif data.operation == ItemOperationType.USE:
            # 检查物品是否可以使用
            if item_static_data.get("use", 0) != 1:
                return response(
                    code=ResponseCode.ITEM_NOT_USABLE,
                    message="ITEM_NOT_USABLE"
                )
                
            # 检查物品类型
            item_type = ItemType(item_static_data["type"])
            if item_type not in [ItemType.POTION, ItemType.FOOD]:
                return response(
                    code=ResponseCode.ITEM_NOT_USABLE,
                    message="ITEM_TYPE_NOT_CONSUMABLE"
                )
                
            # 检查数量是否足够
            if inventory_item.quantity < data.quantity:
                return response(
                    code=ResponseCode.ITEM_NOT_ENOUGH,
                    message="ITEM_NOT_ENOUGH"
                )
                
            # 应用物品效果
            if "attr" in item_static_data:
                for attr_str in item_static_data["attr"].split(","):
                    attr_type, value = map(int, attr_str.split("+"))
                    if attr_type == ItemAttributeType.CURRENT_HP.value:
                        character.current_hp = min(character.current_hp + value * data.quantity, character.max_hp)
                    elif attr_type == ItemAttributeType.CURRENT_MP.value:
                        character.current_mp = min(character.current_mp + value * data.quantity, character.max_mp)
                    elif attr_type == ItemAttributeType.MAX_HP.value:
                        character.max_hp += value * data.quantity
                    elif attr_type == ItemAttributeType.MAX_MP.value:
                        character.max_mp += value * data.quantity
            
            # 减少物品数量
            inventory_item.quantity -= data.quantity
            
            # 如果数量为0，删除物品
            if inventory_item.quantity <= 0:
                await _soft_delete_record(db, character.id, current_user.id, 
                                       "Inventory", inventory_item.id)
            
        else:  # DISCARD
            # 如果物品已装备，不能丢弃
            if inventory_item.equipped == 1:
                return response(
                    code=ResponseCode.ITEM_EQUIPPED,
                    message="ITEM_ALREADY_EQUIPPED"
                )
                
            await _soft_delete_record(db, character.id, current_user.id, 
                                    "Inventory", inventory_item.id)
            
        db.commit()
        
        # 返回更新后的角色状态和物品信息
        response_data = {
            "status": "success",
            "message": f"物品{data.operation.name}成功",
            "character": {
                "current_hp": character.current_hp,
                "max_hp": character.max_hp,
                "current_mp": character.current_mp,
                "max_mp": character.max_mp,
                "physical_attack": character.physical_attack,
                "magic_attack": character.magic_attack,
                "physical_defense": character.physical_defense,
                "magic_defense": character.magic_defense
            }
        }
        
        # 如果是装备操作，返回装备信息
        if data.operation in [ItemOperationType.EQUIP, ItemOperationType.UNEQUIP]:
            equipped_items = {}
            slot_map = {
                ItemType.WEAPON: "weapon_id",
                ItemType.HAT: "hat_id",
                ItemType.CLOTH: "cloth_id",
                ItemType.ORNAMENT: "ornament_id",
                ItemType.PENDANT: "pendant_id",
                ItemType.SHOES: "shoes_id"
            }
            
            for item_type, field_name in slot_map.items():
                inventory_id = getattr(equipment, field_name)
                if inventory_id:
                    inventory_item = db.query(Inventory).filter(
                        Inventory.id == inventory_id,
                        Inventory.is_deleted == 0
                    ).first()
                    if inventory_item:
                        static_info = static_data.get_item_data(inventory_item.item_id)
                        equipped_items[item_type.value] = {
                            "inventory_id": inventory_id,
                            "item_id": inventory_item.item_id,
                            "name": static_info.get("name"),
                            "quality": static_info.get("quality"),
                            "attr": static_info.get("attr"),
                            "strengthen_level": inventory_item.strengthen_level,
                            "durability": inventory_item.durability
                        }
            
            response_data["equipped_items"] = equipped_items
        
        return response(data=response_data)
        
    except Exception as e:
        logger.error(f"物品操作失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return response(
            code=ResponseCode.SYSTEM_ERROR,
            message="SYSTEM_ERROR"
        )

# 内部软删除方法
async def _soft_delete_record(
    db: Session,
    character_id: int,
    user_id: int,
    table_name: str,
    record_id: int
) -> Dict[str, Any]:
    """
    内部软删除方法
    """
    if table_name not in CHARACTER_RELATED_MODELS:
        return response(
            code=ResponseCode.PARAM_ERROR,
            message="INVALID_TABLE_NAME"
        )
        
    model_class = globals()[table_name]
    if not issubclass(model_class, SoftDeleteMixin):
        return response(
            code=ResponseCode.PARAM_ERROR,
            message="TABLE_NOT_SUPPORT_SOFT_DELETE"
        )
        
    # 首先检查记录是否存在
    record = db.query(model_class).filter(
        model_class.id == record_id,
        model_class.is_deleted == 0
    ).first()
    
    if not record:
        return response(
            code=ResponseCode.NOT_FOUND,
            message="RECORD_NOT_FOUND"
        )
        
    # 然后检查是否有权限删除
    if hasattr(model_class, 'character_id'):
        if record.character_id != character_id:
            return response(
                code=ResponseCode.FORBIDDEN,
                message="NO_PERMISSION"
            )
    else:
        return response(
            code=ResponseCode.PARAM_ERROR,
            message="TABLE_NOT_SUPPORT_USER_DELETE"
        )
        
    # 执行软删除
    record.is_deleted = 1
    record.deleted_at = datetime.utcnow()
    record.deleted_by = user_id
    
    return {
        "status": "success",
        "message": "记录删除成功",
        "table": table_name,
        "record_id": record_id,
        "deleted_at": record.deleted_at,
        "deleted_by": record.deleted_by
    }

# 内部装备操作方法
async def _operate_equipment(
    db: Session,
    character: Character,
    inventory_item: Inventory,
    item_static_data: Dict[str, Any],
    operation: ItemOperationType,
    equipment: CharacterEquipment
) -> None:
    """
    内部装备操作方法
    """
    # 检查物品是否可以装备
    if item_static_data.get("use", 0) != 1:
        return response(
            code=ResponseCode.ITEM_NOT_USABLE,
            message="ITEM_NOT_EQUIPPABLE"
        )
        
    # 检查物品类型
    item_type = ItemType(item_static_data["type"])
    if item_type not in [ItemType.WEAPON, ItemType.HAT, ItemType.CLOTH, 
                       ItemType.ORNAMENT, ItemType.PENDANT, ItemType.SHOES]:
        return response(
            code=ResponseCode.ITEM_NOT_USABLE,
            message="ITEM_TYPE_NOT_EQUIPMENT"
        )
        
    # 槽位映射
    slot_map = {
        ItemType.WEAPON: "weapon_id",
        ItemType.HAT: "hat_id",
        ItemType.CLOTH: "cloth_id",
        ItemType.ORNAMENT: "ornament_id",
        ItemType.PENDANT: "pendant_id",
        ItemType.SHOES: "shoes_id"
    }
    
    slot_field = slot_map[item_type]
    
    if operation == ItemOperationType.EQUIP:
        # 检查是否已装备
        if inventory_item.equipped == 1:
            return response(
                code=ResponseCode.ITEM_EQUIPPED,
                message="ITEM_ALREADY_EQUIPPED"
            )
            
        # 如果该槽位已有装备，先卸下
        current_equipped = getattr(equipment, slot_field)
        if current_equipped:
            current_item = db.query(Inventory).filter(
                Inventory.id == current_equipped,
                Inventory.is_deleted == 0
            ).first()
            if current_item:
                current_item.equipped = 0
                
        # 装备新物品
        setattr(equipment, slot_field, inventory_item.id)
        inventory_item.equipped = 1
        
        # 应用装备属性
        if "attr" in item_static_data:
            for attr_str in item_static_data["attr"].split(","):
                attr_type, value = map(int, attr_str.split("+"))
                if attr_type == ItemAttributeType.PHYSICAL_ATTACK.value:
                    character.physical_attack += value
                elif attr_type == ItemAttributeType.MAGIC_ATTACK.value:
                    character.magic_attack += value
                elif attr_type == ItemAttributeType.PHYSICAL_DEFENSE.value:
                    character.physical_defense += value
                elif attr_type == ItemAttributeType.MAGIC_DEFENSE.value:
                    character.magic_defense += value
                    
    else:  # UNEQUIP
        # 检查物品是否已装备
        if inventory_item.equipped != 1:
            return response(
                code=ResponseCode.ITEM_NOT_EQUIPPED,
                message="ITEM_NOT_EQUIPPED"
            )
            
        # 移除装备属性
        if "attr" in item_static_data:
            for attr_str in item_static_data["attr"].split(","):
                attr_type, value = map(int, attr_str.split("+"))
                if attr_type == ItemAttributeType.PHYSICAL_ATTACK.value:
                    character.physical_attack -= value
                elif attr_type == ItemAttributeType.MAGIC_ATTACK.value:
                    character.magic_attack -= value
                elif attr_type == ItemAttributeType.PHYSICAL_DEFENSE.value:
                    character.physical_defense -= value
                elif attr_type == ItemAttributeType.MAGIC_DEFENSE.value:
                    character.magic_defense -= value
        
        # 卸下装备
        setattr(equipment, slot_field, None)
        inventory_item.equipped = 0

# 邮件操作类型枚举
class MailOperationType(str, Enum):
    CLAIM = "claim"    # 领取附件
    DELETE = "delete"  # 删除邮件

# 发送者类型枚举
class SenderType(str, Enum):
    SYSTEM = "system"  # 系统
    CHARACTER = "character"  # 角色
    # NPC = "npc"  # NPC (暂时屏蔽)
    CUSTOM = "custom"  # 自定义

# 邮件发送请求模型
class MailSendRequest(BaseModel):
    title: str
    content: str
    character_ids: Union[str, List[int]]  # 接收者角色ID列表或"all"
    sender_type: SenderType  # 发送者类型
    sender_id: Optional[Union[str, int]] = None  # 发送者ID（可选，system类型时不需要）
    attachments: Optional[List[Dict[str, Any]]] = None  # 附件列表 [{item_id: xx, quantity: xx}, ...]
    expire_days: Optional[int] = 7  # 过期天数，默认7天
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "测试邮件",
                "content": "这是一封测试邮件",
                "character_ids": "all",  # 或 [1, 2]
                "sender_type": "system",  # system类型时不需要sender_id
                "attachments": [
                    {"item_id": 1001, "quantity": 1},
                    {"item_id": 2001, "quantity": 5}
                ],
                "expire_days": 7
            }
        }

# 邮件操作请求模型
class MailOperationRequest(BaseModel):
    operation: MailOperationType
    mail_id: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "operation": MailOperationType.CLAIM,
                "mail_id": 1
            }
        }

@character_router.post("/mail/send", 
    summary="发送邮件",
    description="""
    发送邮件给指定角色或所有角色，可以包含附件。
    
    权限要求：
    - 需要有效的用户Token
    - 需要有效的角色信息
    
    请求参数：
    - title: 邮件标题
      - 类型：string
      - 必填：是
      - 长度：1-50个字符
      
    - content: 邮件内容
      - 类型：string
      - 必填：是
      - 长度：1-1000个字符
      
    - character_ids: 接收者角色ID列表或"all"
      - 类型：array[integer] 或 string
      - 必填：是
      - 说明：当为"all"时发送给所有角色，当为数组时发送给指定角色
      
    - sender_type: 发送者类型
      - 类型：string
      - 必填：是
      - 取值：
        - system: 系统发送（此类型时不需要sender_id，默认为"系统"）
        - character: 角色发送（sender_id必须为有效的角色ID）
        - custom: 自定义发送者（sender_id为任意字符串）
      
    - sender_id: 发送者ID
      - 类型：integer 或 string
      - 必填：否（system类型时不需要）
      - 说明：根据sender_type不同有不同要求
      
    - attachments: 附件列表
      - 类型：array[object]
      - 必填：否
      - 格式：[{item_id: 物品ID, quantity: 数量}, ...]
      - 说明：每个附件需要指定物品ID和数量
      
    - expire_days: 过期天数
      - 类型：integer
      - 必填：否
      - 默认值：7
      - 说明：邮件的有效期天数
    
    可能的错误码：
    - 400: 参数错误
    - 401: Token无效
    - 404: 角色不存在
    - 3001: 物品不存在
    - 4006: 邮件发送失败
    
    请求示例：
    1. 系统发送给所有角色
    ```json
    {
        "title": "系统公告",
        "content": "这是一封系统公告",
        "character_ids": "all",
        "sender_type": "system",
        "attachments": [
            {"item_id": 1001, "quantity": 1}
        ]
    }
    ```
    
    2. 角色发送给指定角色
    ```json
    {
        "title": "个人邮件",
        "content": "这是一封个人邮件",
        "character_ids": [1, 2],
        "sender_type": "character",
        "sender_id": 1001,
        "attachments": [
            {"item_id": 2001, "quantity": 5}
        ]
    }
    ```
    
    3. 自定义发送者
    ```json
    {
        "title": "活动奖励",
        "content": "这是活动奖励",
        "character_ids": "all",
        "sender_type": "custom",
        "sender_id": "中秋节活动",
        "attachments": [
            {"item_id": 1001, "quantity": 1}
        ]
    }
    ```
    
    成功返回示例：
    ```json
    {
        "code": 200,
        "message": "SUCCESS",
        "data": {
            "recipients_count": 2,
            "mail_ids": [1001, 1002]
        }
    }
    ```
    
    错误返回示例：
    ```json
    {
        "code": 3001,
        "message": "ITEM_NOT_FOUND",
        "data": null
    }
    ```
    
    注意事项：
    1. 发送给所有角色时，只会发送给未删除的角色
    2. 附件中的物品必须是有效的物品ID
    3. 物品数量必须大于0
    4. 邮件发送后不能撤回
    5. 邮件会在过期时间后自动删除
    """
)
async def send_mail(
    request: Request,
    data: MailSendRequest,
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"发送邮件请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"操作数据: {data.dict()}")
        
        # 获取发送者名称
        if data.sender_type == SenderType.SYSTEM:
            sender_name = "系统"
            sender_id = 0
        elif data.sender_type == SenderType.CHARACTER:
            if not isinstance(data.sender_id, int):
                return response(code=ResponseCode.PARAM_ERROR, 
                              message="INVALID_SENDER_ID_TYPE")
            # 验证角色是否存在
            sender = db.query(Character).filter(
                Character.id == data.sender_id,
                Character.is_deleted == 0
            ).first()
            if not sender:
                return response(code=ResponseCode.CHARACTER_NOT_FOUND, 
                              message="CHARACTER_NOT_FOUND")
            sender_name = sender.name
            sender_id = data.sender_id
        else:  # CUSTOM
            if not data.sender_id:
                return response(code=ResponseCode.PARAM_ERROR, 
                              message="MISSING_SENDER_ID")
            sender_name = str(data.sender_id)
            sender_id = 0
            
        # 获取接收者列表
        if data.character_ids == "all":
            # 发送给所有未删除的角色
            recipients = db.query(Character).filter(
                Character.is_deleted == 0
            ).all()
        else:
            # 发送给指定角色
            recipients = db.query(Character).filter(
                Character.id.in_(data.character_ids),
                Character.is_deleted == 0
            ).all()
        
        if not recipients:
            return response(code=ResponseCode.CHARACTER_NOT_FOUND, 
                          message="NO_VALID_RECIPIENTS")
            
        # 如果有附件，验证物品是否存在
        if data.attachments:
            for attachment in data.attachments:
                item_data = static_data.get_item_data(attachment["item_id"])
                if not item_data:
                    return response(code=ResponseCode.ITEM_NOT_FOUND, 
                                  message=f"ITEM_NOT_FOUND: {attachment['item_id']}")
                if attachment["quantity"] <= 0:
                    return response(code=ResponseCode.PARAM_ERROR, 
                                  message="INVALID_ITEM_QUANTITY")
        
        # 创建邮件
        mail_ids = []
        for recipient in recipients:
            mail = Mail(
                character_id=recipient.id,
                sender_id=sender_id,
                sender_name=sender_name,
                title=data.title,
                content=data.content,
                mail_type=MailType.SYSTEM if data.sender_type == SenderType.SYSTEM else MailType.PERSONAL,
                has_attachment=bool(data.attachments),
                attachments=data.attachments,
                status=MailStatus.UNREAD,
                expire_time=datetime.utcnow() + timedelta(days=data.expire_days)
            )
            db.add(mail)
            db.flush()  # 获取自增ID
            mail_ids.append(mail.id)
        
        db.commit()
        
        return response(data={
            "recipients_count": len(recipients),
            "mail_ids": mail_ids
        })
        
    except Exception as e:
        logger.error(f"发送邮件失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return response(code=ResponseCode.MAIL_SEND_FAILED, 
                      message="MAIL_SEND_FAILED")

@character_router.post("/mail/operate",
    summary="邮件操作",
    description="""
    对邮件进行操作，包括领取附件和删除邮件。
    
    权限要求：
    - 需要有效的用户Token
    - 需要有效的角色信息
    
    请求参数：
    - operation: 操作类型
      - 类型：string
      - 必填：是
      - 取值：
        - claim: 领取附件
        - delete: 删除邮件
      
    - mail_id: 邮件ID
      - 类型：integer
      - 必填：是
      - 说明：要操作的邮件ID
    
    可能的错误码：
    - 400: 参数错误
    - 401: Token无效
    - 404: 邮件不存在
    - 4002: 邮件已过期
    - 4003: 邮件无附件
    - 4004: 附件已领取
    - 4005: 邮件已删除
    - 4007: 邮件未领取不能删除
    
    请求示例：
    1. 领取附件
    ```json
    {
        "operation": "claim",
        "mail_id": 1001
    }
    ```
    
    2. 删除邮件
    ```json
    {
        "operation": "delete",
        "mail_id": 1001
    }
    ```
    
    成功返回示例：
    ```json
    {
        "code": 200,
        "message": "SUCCESS",
        "data": {
            "operation": "claim",
            "items": [
                {
                    "item_id": 1001,
                    "quantity": 1
                }
            ]
        }
    }
    ```
    
    错误返回示例：
    ```json
    {
        "code": 4007,
        "message": "UNCLAIMED_MAIL_CANNOT_DELETE",
        "data": null
    }
    ```
    
    注意事项：
    1. 领取附件后邮件状态会变更为已领取
    2. 删除邮件后不能恢复
    3. 已过期的邮件不能进行任何操作
    4. 领取附件时会自动添加到角色背包
    5. 有附件的邮件必须先领取附件才能删除
    """
)
async def operate_mail(
    request: Request,
    data: MailOperationRequest,
    commons: CommonHeaders = Depends(),
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"邮件操作请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"操作数据: {data.dict()}")
        
        # 获取当前角色
        character = db.query(Character).filter(
            Character.account_id == current_user.id,
            Character.is_deleted == 0
        ).first()
        
        if not character:
            return response(code=ResponseCode.CHARACTER_NOT_FOUND, 
                          message="CHARACTER_NOT_FOUND")
            
        # 获取邮件信息
        mail = db.query(Mail).filter(
            Mail.id == data.mail_id,
            Mail.character_id == character.id,
            Mail.is_deleted == 0
        ).first()
        
        if not mail:
            return response(code=ResponseCode.MAIL_NOT_FOUND, 
                          message="MAIL_NOT_FOUND")
            
        # 检查邮件是否已过期
        if mail.expire_time and mail.expire_time < datetime.utcnow():
            return response(code=ResponseCode.MAIL_EXPIRED, 
                          message="MAIL_EXPIRED")
            
        if data.operation == MailOperationType.CLAIM:
            # 检查是否有附件
            if not mail.has_attachment:
                return response(code=ResponseCode.MAIL_NO_ATTACHMENT, 
                              message="MAIL_NO_ATTACHMENT")
                
            # 检查是否已领取
            if mail.status == MailStatus.CLAIMED:
                return response(code=ResponseCode.MAIL_CLAIMED, 
                              message="MAIL_CLAIMED")
                
            # 领取附件
            claimed_items = []
            if mail.attachments:
                for attachment in mail.attachments:
                    # 验证物品是否存在
                    item_data = static_data.get_item_data(attachment["item_id"])
                    if not item_data:
                        return response(code=ResponseCode.ITEM_NOT_FOUND, 
                                      message=f"ITEM_NOT_FOUND: {attachment['item_id']}")
                        
                    # 查找是否已有该物品
                    existing_item = db.query(Inventory).filter(
                        Inventory.character_id == character.id,
                        Inventory.item_id == attachment["item_id"],
                        Inventory.is_deleted == 0
                    ).first()
                    
                    if existing_item:
                        # 如果物品已存在，增加数量
                        existing_item.quantity += attachment["quantity"]
                    else:
                        # 创建新物品记录
                        new_item = Inventory(
                            character_id=character.id,
                            item_id=attachment["item_id"],
                            quantity=attachment["quantity"],
                            strengthen_level=0,
                            durability=100,
                            bind_status=0,
                            extra_attributes={},
                            bag_type=1
                        )
                        db.add(new_item)
                    
                    claimed_items.append({
                        "item_id": attachment["item_id"],
                        "quantity": attachment["quantity"]
                    })
                        
            # 更新邮件状态
            mail.status = MailStatus.CLAIMED
            mail.claim_time = datetime.utcnow()
            
            db.commit()
            
            return response(data={
                "operation": data.operation,
                "items": claimed_items
            })
            
        else:  # DELETE
            # 检查是否有未领取的附件
            if mail.has_attachment and mail.status != MailStatus.CLAIMED:
                return response(code=ResponseCode.PARAM_ERROR,
                              message="UNCLAIMED_MAIL_CANNOT_DELETE")
            
            # 执行软删除
            await _soft_delete_record(db, character.id, current_user.id, "Mail", mail.id)
            
            return response(data={
                "operation": data.operation
            })
        
    except Exception as e:
        logger.error(f"邮件操作失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        return response(code=ResponseCode.SYSTEM_ERROR, 
                      message="SYSTEM_ERROR")

# 注册路由
app.include_router(crud_router)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(character_router)
app.include_router(admin_router)
app.include_router(server_router, tags=["服务器相关"])  # 修改这行，移除prefix

# 注册静态文件
app.mount("/static", StaticFiles(directory="app/admin/static"), name="static")