from fastapi import FastAPI, Depends, Path, Query, HTTPException, Header, Request, APIRouter, Form
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
import logging
import json
import traceback
from datetime import datetime
import importlib
import inspect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from enum import Enum
import app.models as models_module
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
logger = logging.getLogger(__name__)

# 导入配置
logger.info("Loading settings...")
from app.config import settings
logger.info(f"Settings loaded - DB_HOST: {settings.DB_HOST}")

# 导入数据库
logger.info("Initializing database...")
from app.database import SessionLocal, engine, Base
logger.info("Database initialized")

from app.models import (
    Account, UserToken, Character, CharacterEquipment, 
    Race, FavorRecord, FavorTargetType
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
        
        # ��取请求体
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

# 创建路由器
crud_router = APIRouter(prefix="/api", tags=["CRUD操作"])
auth_router = APIRouter(prefix="/auth", tags=["认证"])
user_router = APIRouter(prefix="/user", tags=["用户"])
character_router = APIRouter(prefix="/character", tags=["角色"])

# 依赖项
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 动态注册所有模型
for attr_name in dir(models_module):
    attr = getattr(models_module, attr_name)
    # 检查是否是 SQLAlchemy 模型类
    if (inspect.isclass(attr) and 
        issubclass(attr, Base) and 
        attr != Base and 
        attr != models_module.SoftDeleteMixin):  # 排除基类
        # 注册到 CRUD
        CRUDRegister.register(attr)
        # 创建表
        attr.metadata.create_all(bind=engine)
        logger.debug(f"已注册并创建表: {attr_name}")

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
@auth_router.post("/login")
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
        
        # 查找用户账号
        account = db.query(Account).filter(Account.username == login_data.username).first()
        if not account:
            logger.error(f"用户不存在: {login_data.username}")
            raise HTTPException(status_code=401, detail="用户名或密码错误")
            
        # 检查账号状态
        if account.is_deleted:
            logger.error(f"已删除的账号尝试登录: {login_data.username}")
            raise HTTPException(status_code=403, detail="账号已被删除")
            
        if account.status == 2:  # 已封禁
            logger.error(f"被封禁的账号尝试登录: {login_data.username}")
            raise HTTPException(
                status_code=403, 
                detail="账号已被封禁，如有疑问请联系我们"
            )
            
        # if account.status == 0:  # 未激活
        #     logger.error(f"未激活的账号尝试登录: {login_data.username}")
        #     raise HTTPException(status_code=403, detail="账号未激活，请先激活账号")
            
        # 验证密码
        if not verify_password(login_data.password, account.password):
            logger.error(f"密码错误: username={login_data.username}")
            raise HTTPException(status_code=401, detail="用户名或密码错误")
            
        logger.debug(f"用户验证成功: {account.username} (ID: {account.id})")
        
        # 检查是否有游戏角色
        has_character = db.query(Character).filter(
            Character.account_id == account.id,
            Character.is_deleted == 0
        ).first() is not None
        logger.debug(f"用户角色检查: has_character={has_character}")
        
        # 创建token
        token = create_token(db, account.id, login_data.device_name, login_data.device_id)
        logger.debug(f"创建token成功: {token[:10]}...")
        
        # 更新最后登录时间
        account.last_login_at = datetime.now()
        db.commit()
        
        response_data = {
            "token": token,
            "account_id": account.id,
            "username": account.username,
            "has_character": has_character
        }
        logger.debug(f"登录成功，返回数据: {response_data}")
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"登录过程发生异常: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="系统错误，请稍后重试")

@auth_router.post("/logout")
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
        
        if invalidate_token(db, logout_data.token):
            logger.debug(f"登出成功: token={logout_data.token[:10]}...")
            return {"status": "success", "message": "Logged out successfully"}
        
        logger.error(f"登出失败，无效token: {logout_data.token[:10]}...")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"登出过程发生异常: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise

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
        logger.debug(f"验证用户请求 - ��整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"Service Code: {commons.service_code}")
        
        # 验证token
        account_id = verify_token(db, commons.token)
        if not account_id:
            logger.error(f"无效或过期的token: {commons.token[:10]}...")
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        logger.debug(f"Token验证成功: account_id={account_id}")
        
        # 验证设备
        token_record = db.query(UserToken).filter(
            UserToken.token == commons.token,
            UserToken.device_id == commons.device_id,
            UserToken.device_name == commons.device_name,
            UserToken.expired == 0
        ).first()
        
        if not token_record:
            logger.error(f"设备验证失败: device_name={commons.device_name}, device_id={commons.device_id}")
            raise HTTPException(status_code=401, detail="Invalid device or device name")
        
        logger.debug(f"设备验证成功: {token_record.device_name} ({token_record.device_id})")
        
        # 获取账号信息
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            logger.error(f"账号不存在: account_id={account_id}")
            raise HTTPException(status_code=404, detail="Account not found")
        
        logger.debug(f"获取账号成功: {account.username} (ID: {account.id})")
        return account
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"用户验证过程发生异常: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal server error")

# 添加 datetime 序列化处理函数
def datetime_handler(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f'Object of type {type(obj)} is not JSON serializable')

# 用户路由
@user_router.get("/me")
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
            "character": None if not current_character else {
                "id": current_character.id,
                "name": current_character.name,
                "race": current_character.race.value,
                "sect_name": current_character.sect_name,
                "current_location": current_character.current_location,
                "level": current_character.level,
                "exp": current_character.exp,
                "max_exp": current_character.max_exp,
                # 基础属性
                "max_hp": current_character.max_hp,
                "current_hp": current_character.current_hp,
                "max_mp": current_character.max_mp,
                "current_mp": current_character.current_mp,
                # 战斗属性
                "physical_attack": current_character.physical_attack,
                "magic_attack": current_character.magic_attack,
                "physical_defense": current_character.physical_defense,
                "magic_defense": current_character.magic_defense,
                # 其他属性
                "speed": current_character.speed,
                "critical_rate": current_character.critical_rate,
                "critical_damage": current_character.critical_damage,
                "hit_rate": current_character.hit_rate,
                "dodge_rate": current_character.dodge_rate,
                "morality": current_character.morality,
                "max_stamina": current_character.max_stamina,
                "current_stamina": current_character.current_stamina,
                "copper_coins": current_character.copper_coins,
                # 时间信息
                "created_at": current_character.created_at,
                "last_login": current_character.last_login,
                "last_logout": current_character.last_logout
            }
        }
        logger.debug(f"获取用户信息成功: {json.dumps(response_data, ensure_ascii=False, default=datetime_handler)}")
        return response_data
    except Exception as e:
        logger.error(f"获取用户信息失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise

@user_router.get("/characters")
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
        
        if character:
            char_list = [{
                'id': character.id,
                'name': character.name,
                'level': character.level
            }]
        else:
            char_list = []
            
        logger.debug(f"角色列表: {json.dumps(char_list, ensure_ascii=False)}")
        return char_list
    except Exception as e:
        logger.error(f"获取用户角色列表失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise

# 修改为GET方法，使用header参数
@user_router.get("/devices")
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
        return response_data
    except Exception as e:
        logger.error(f"获取用户设备列表失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise

# 角色路由
@character_router.post("/create")
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
            raise HTTPException(
                status_code=400,
                detail="已有角色"
            )
        
        # 检查角色名是否已存在
        name_exists = db.query(Character).filter(
            Character.name == data.name,
            Character.is_deleted == 0
        ).first()
        if name_exists:
            raise HTTPException(status_code=400, detail="角色名已存在")
        
        # 获取种族初始属性
        initial_stats = RACE_INITIAL_STATS[data.race]
        
        # 创建角色
        character = Character(
            account_id=account.id,
            name=data.name,
            race=data.race,
            current_location=data.location_id,  # 直接使用location_id
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
            is_deleted=0  # 确保设置为未删除
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
        
        return {
            "message": "角色创建成功",
            "character_id": character.id,
            "name": character.name,
            "race": character.race.value,
            "location": character.current_location
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建角色失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        db.rollback()
        raise HTTPException(status_code=500, detail="系统错误，请稍后重试")

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

# 注册路由
app.include_router(crud_router)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(character_router)
app.include_router(admin_router)

# 注册静态文件
app.mount("/static", StaticFiles(directory="app/admin/static"), name="static")