from fastapi import FastAPI, Depends, Path, Query, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from app.database import SessionLocal, engine, Base
import app.models as models  # 直接导入整个模块
from app.crud.base import CRUDRegister
from app.auth.token import create_token, verify_token, invalidate_token
from app.config import settings
from pydantic import BaseModel
import logging
import json
import traceback
from datetime import datetime
import importlib
import inspect
from app.models import Account, UserToken  # 只导入常用的模型
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.admin.routes import admin_router

# 修改日志配置
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

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

app = FastAPI()

# 添加请求日志中间件
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 记录请求开始
        logger.debug("=" * 50)
        logger.debug("收到新的请求:")
        logger.debug(f"请求方法: {request.method}")
        logger.debug(f"请求URL: {request.url}")
        logger.debug(f"请求头: {dict(request.headers)}")
        
        # 获取请求体
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

# 在所有路由之前添加中间件
app.add_middleware(RequestLoggingMiddleware)

# CORS中间件需要放在请求日志中间件之后
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# 动态注册所有模型
for attr_name in dir(models):
    attr = getattr(models, attr_name)
    # 检查是否是 SQLAlchemy 模型类
    if (inspect.isclass(attr) and 
        issubclass(attr, Base) and 
        attr != Base and 
        attr != models.SoftDeleteMixin):  # 排除基类
        # 注册到 CRUD
        CRUDRegister.register(attr)
        # 创建表
        attr.metadata.create_all(bind=engine)
        logger.debug(f"已注册并创建表: {attr_name}")

# 依赖项
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 通用CRUD API
@app.post("/api/{model_name}")
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
    except Exception as e:
        logger.error(f"创建{model_name}失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise

@app.get("/api/{model_name}/{item_id}")
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

@app.get("/api/{model_name}")
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

@app.put("/api/{model_name}/{item_id}")
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
    except Exception as e:
        logger.error(f"更新{model_name}失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise

@app.delete("/api/{model_name}/{item_id}")
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
    except Exception as e:
        logger.error(f"删除{model_name}失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise

#认证相关API
@app.post("/auth/login")
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
        
        # 验证用户名密码
        account = db.query(Account).filter(Account.username == login_data.username).first()
        if not account:
            logger.error(f"用户不存在: {login_data.username}")
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        if account.password != login_data.password:
            logger.error(f"密码错误: username={login_data.username}")
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        logger.debug(f"用户验证成功: {account.username} (ID: {account.id})")
        
        # 创建token
        token = create_token(db, account.id, login_data.device_name, login_data.device_id)
        logger.debug(f"创建token成: {token[:10]}...")
        
        response_data = {
            "token": token,
            "account_id": account.id,
            "username": login_data.username
        }
        logger.debug(f"登录成功，返回数据: {json.dumps(response_data, ensure_ascii=False)}")
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"登录过程发生异常: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/auth/logout")
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

# 认证依赖
async def get_current_user(
    request: Request,
    token: str = Header(..., description="认证token"),
    device_name: str = Header(..., description="设备名称"),
    device_id: str = Header(..., description="设备ID"),
    db: Session = Depends(get_db)
) -> Account:
    try:
        logger.debug(f"验证用户请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        
        # 验证token
        account_id = verify_token(db, token)
        if not account_id:
            logger.error(f"无效或过期的token: {token[:10]}...")
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        logger.debug(f"Token验证成功: account_id={account_id}")
        
        # 验证设备
        token_record = db.query(UserToken).filter(
            UserToken.token == token,
            UserToken.device_id == device_id,
            UserToken.device_name == device_name,
            UserToken.expired == 0
        ).first()
        
        if not token_record:
            logger.error(f"设备验证失败: device_name={device_name}, device_id={device_id}")
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

# 修改/api/me路由
@app.get("/user/me")
async def read_me(
    request: Request,
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"获取用户信息请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        
        response_data = {
            "id": current_user.id,
            "username": current_user.username,
            "wallet_address": current_user.wallet_address,
            "status": current_user.status,
            "email": current_user.email,
            "role": current_user.role.value,
            "avatar_url": current_user.avatar_url,
            "created_at": current_user.created_at,
            "characters": [
                {
                    "id": char.id,
                    "name": char.name,
                    "level": char.level,
                    "exp": char.exp,
                    "hp": char.hp,
                    "max_hp": char.max_hp,
                    "mp": char.mp,
                    "max_mp": char.max_mp,
                    "attack": char.attack,
                    "defense": char.defense,
                    "speed": char.speed,
                    "gold": char.gold,
                    "diamond": char.diamond,
                    "vip_level": char.vip_level,
                    "last_login": char.last_login,
                    "create_time": char.create_time
                }
                for char in current_user.characters
            ]
        }
        logger.debug(f"获取用户信息成功: {json.dumps(response_data, ensure_ascii=False, default=datetime_handler)}")
        return response_data
    except Exception as e:
        logger.error(f"获取用户信息失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise

# 修改为GET方法，使用header参数
@app.get("/user/characters")
async def read_user_characters(
    request: Request,
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"获取用户角色列表请求 - 完整信息:")
        logger.debug(f"URL: {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        
        characters = current_user.characters
        logger.debug(f"获取到 {len(characters)} 个角色")
        
        char_list = [{
            'id': char.id,
            'name': char.name,
            'level': char.level
        } for char in characters]
        logger.debug(f"角色列表: {json.dumps(char_list, ensure_ascii=False)}")
        
        return characters
    except Exception as e:
        logger.error(f"获取用户角色列表失败: {str(e)}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise

# 修改为GET方法，使用header参数
@app.get("/user/devices")
async def read_user_devices(
    request: Request,
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

# 注册静态文件
app.mount("/static", StaticFiles(directory="app/admin/static"), name="static")

# 注册管理后台路由
app.include_router(admin_router)