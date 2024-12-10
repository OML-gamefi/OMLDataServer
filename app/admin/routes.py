from fastapi import APIRouter, Request, Response, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import (
    Account, UserRole, ItemTemplate, ItemType, 
    ItemQuality, BindType, EquipmentSlot, UserToken, Character, Mail, MailType
)
from typing import Optional
from datetime import datetime, timedelta
import logging
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import traceback
import random
import string
from app.schemas.items import ItemCreate
from app.utils.password import verify_password, hash_password
from app.utils.auth import create_access_token, SECRET_KEY, ALGORITHM
import jwt

logger = logging.getLogger(__name__)

# 创建路由
admin_router = APIRouter(
    prefix="/admin",
    tags=["管理端"],
    responses={404: {"description": "Not found"}},
)

# 设置模板
templates = Jinja2Templates(directory="app/admin/templates")

# 验证管理员
async def get_current_admin(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[Account]:
    token = request.cookies.get("admin_token")
    if not token:
        logger.debug("No admin_token cookie found")
        return None
    
    try:
        # 验证JWT
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        account_id = payload.get("sub")
        if not account_id:
            logger.debug("No sub claim in token")
            return None
            
        # 获取管理员账号
        admin = db.query(Account).filter(
            Account.id == account_id,
            Account.role == UserRole.ADMIN,
            Account.is_deleted == False
        ).first()
        
        if not admin:
            logger.debug(f"No admin found for account_id: {account_id}")
            return None
            
        if admin.status == 2:  # 已封禁
            logger.debug(f"Admin is banned: {admin.username} (ID: {admin.id})")
            return None
            
        logger.debug(f"Admin authenticated: {admin.username} (ID: {admin.id})")
        return admin
        
    except jwt.ExpiredSignatureError:
        logger.debug("Token expired")
        return None
    except jwt.JWTError as e:
        logger.debug(f"JWT validation error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error in get_current_admin: {str(e)}")
        return None

# 登录页面
@admin_router.get("/", response_class=HTMLResponse)
@admin_router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    admin: Account = Depends(get_current_admin)
):
    if admin:
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )

# 登录处理
@admin_router.post("/login")
async def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        # 查找管理员账号
        admin = db.query(Account).filter(Account.username == username).first()
        if not admin:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "用户名或密码错误"
                }
            )
            
        # 检查账号状态
        if admin.is_deleted:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "账号已被删除"
                }
            )
            
        if admin.status == 2:  # 已封禁
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "账号已被封禁，如有疑问请联系超级管理员"
                }
            )
            
        # 验证密码
        if not verify_password(password, admin.password):
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "用户名或密码错误"
                }
            )
            
        # 验证是否是管理员
        if admin.role != UserRole.ADMIN:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "该账号没有管理员权限"
                }
            )
            
        # 生成访问令牌，有效期2小时
        access_token = create_access_token(
            data={"sub": str(admin.id)},
            expires_delta=timedelta(hours=2)
        )
        logger.debug(f"Created access token for admin: {admin.username} (ID: {admin.id})")
        
        # 更新最后登录时��
        admin.last_login_at = datetime.now()
        db.commit()
        
        # 创建响应
        response = RedirectResponse(url="/admin/dashboard", status_code=303)
        response.set_cookie(
            key="admin_token",
            value=access_token,
            httponly=True,
            secure=False,  # 允许在 HTTP 中使用
            samesite="lax",  # 防止 CSRF 攻击
            max_age=7200,  # 2小时后过期
            path="/"
        )
        return response
        
    except Exception as e:
        logger.error(f"管理员登录失败: {str(e)}")
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "系统错误，请稍后重试"
            }
        )

# 仪表盘
@admin_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    admin: Account = Depends(get_current_admin)
):
    if not admin:
        logger.debug("No admin authenticated, redirecting to login")
        return RedirectResponse(url="/admin/login", status_code=303)
    logger.debug(f"Rendering dashboard for admin: {admin.username} (ID: {admin.id})")
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": admin}
    )

# 登出
@admin_router.get("/logout")
async def logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(
        key="admin_token",
        path="/"  # 添加path参数
    )
    return response

# 道具列表页面
@admin_router.get("/items", response_class=HTMLResponse)
async def items_list(
    request: Request,
    name: str = None,
    type: str = None,
    admin: Account = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if not admin:
        return RedirectResponse(url="/admin/login")
    
    # 构建查询
    query = db.query(ItemTemplate)
    if name:
        query = query.filter(ItemTemplate.name.like(f"%{name}%"))
    if type:
        query = query.filter(ItemTemplate.type == type)
    
    items = query.all()
    
    return templates.TemplateResponse(
        "items/list.html",
        {
            "request": request,
            "user": admin,
            "items": items,
            "item_types": list(ItemType),
            "item_qualities": list(ItemQuality)
        }
    )

# 新建道具页面
@admin_router.get("/items/new", response_class=HTMLResponse)
async def new_item(
    request: Request,
    admin: Account = Depends(get_current_admin)
):
    if not admin:
        return RedirectResponse(url="/admin/login")
        
    return templates.TemplateResponse("items/edit.html", {
        "request": request,
        "item": None,
        "item_types": list(ItemType),
        "item_qualities": list(ItemQuality),
        "bind_types": list(BindType),
        "equipment_slots": list(EquipmentSlot)
    })

# 编辑道具页面
@admin_router.get("/items/{item_id}/edit", response_class=HTMLResponse)
async def edit_item(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
    admin: Account = Depends(get_current_admin)
):
    if not admin:
        return RedirectResponse(url="/admin/login")
        
    item = db.query(ItemTemplate).filter(ItemTemplate.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="道具不存在")
        
    return templates.TemplateResponse("items/edit.html", {
        "request": request,
        "item": item,
        "item_types": list(ItemType),
        "item_qualities": list(ItemQuality),
        "bind_types": list(BindType),
        "equipment_slots": list(EquipmentSlot)
    })

# 创建道具API
@admin_router.post("/items")
async def create_item(
    item: ItemCreate,
    db: Session = Depends(get_db),
    admin: Account = Depends(get_current_admin)
):
    if not admin:
        raise HTTPException(status_code=401, detail="未授权的访问")
        
    try:
        # 将字符串枚举名称转换为枚举值
        item_dict = item.dict()
        
        # 转换道具类型
        if item_dict.get('type'):
            item_dict['type'] = ItemType[item_dict['type']]
            
        # 转换品质
        if item_dict.get('quality'):
            item_dict['quality'] = ItemQuality[item_dict['quality']]
            
        # 转换绑定类型
        if item_dict.get('bind_type'):
            item_dict['bind_type'] = BindType[item_dict['bind_type']]
            
        # 转换装备槽位
        if item_dict.get('equipment_slot'):
            item_dict['equipment_slot'] = EquipmentSlot[item_dict['equipment_slot']]
        
        # 创建道具模板
        db_item = ItemTemplate(**item_dict)
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        
        return {"status": "success", "message": "道具创建成功", "data": db_item}
        
    except KeyError as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"无效的枚举值: {str(e)}"
        )
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"数据库错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="数据库错误"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"创建道具时发生错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"创建道具失败: {str(e)}"
        )

# 更新道具API
@admin_router.put("/items/{item_id}")
async def update_item(
    item_id: int,
    item: ItemCreate,
    db: Session = Depends(get_db),
    admin: Account = Depends(get_current_admin)
):
    if not admin:
        raise HTTPException(status_code=401, detail="未授权的访问")
        
    try:
        # 查找要更新的道具
        db_item = db.query(ItemTemplate).filter(ItemTemplate.id == item_id).first()
        if not db_item:
            raise HTTPException(status_code=404, detail="道具不存在")
            
        # 将字符串枚举名称转换为枚举值
        item_dict = item.dict(exclude_unset=True)
        
        # 转换道具类型
        if item_dict.get('type'):
            item_dict['type'] = ItemType[item_dict['type']]
            
        # 转换品质
        if item_dict.get('quality'):
            item_dict['quality'] = ItemQuality[item_dict['quality']]
            
        # 转换绑定类型
        if item_dict.get('bind_type'):
            item_dict['bind_type'] = BindType[item_dict['bind_type']]
            
        # 转换装备槽位
        if item_dict.get('equipment_slot'):
            item_dict['equipment_slot'] = EquipmentSlot[item_dict['equipment_slot']]
            
        # 更新道具属性
        for key, value in item_dict.items():
            setattr(db_item, key, value)
            
        db.commit()
        db.refresh(db_item)
        
        return {"status": "success", "message": "道具更新成功", "data": db_item}
        
    except KeyError as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"无效的枚举值: {str(e)}"
        )
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"数据库错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="数据库错误"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"更新道具时发生错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"更新道具失败: {str(e)}"
        )

# 删除道具API
@admin_router.delete("/items/{item_id}")
async def delete_item(
    item_id: int,
    admin: Account = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if not admin:
        raise HTTPException(status_code=401)
    
    item = db.query(ItemTemplate).filter(ItemTemplate.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    db.delete(item)
    db.commit()
    return {"status": "success"}

# 用户管理相关路由
@admin_router.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request,
    username: str = None,
    role: str = None,
    status: int = None,
    admin: Account = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if not admin:
        return RedirectResponse(url="/admin/login")
    
    # 构建查询
    query = db.query(Account)
    if username:
        query = query.filter(Account.username.like(f"%{username}%"))
    if role:
        query = query.filter(Account.role == role)
    if status is not None:
        query = query.filter(Account.status == status)
    
    users = query.all()
    
    return templates.TemplateResponse(
        "users/list.html",
        {
            "request": request,
            "user": admin,
            "users": users,
            "user_roles": list(UserRole)
        }
    )

# 修改用户状态
@admin_router.post("/users/{user_id}/status")
async def change_user_status(
    user_id: int,
    admin: Account = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if not admin:
        raise HTTPException(status_code=401)
    
    user = db.query(Account).filter(Account.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 切换状态：正常 <-> 封禁
    user.status = 1 if user.status == 2 else 2
    db.commit()
    
    return {"status": "success"}

# 重置用户密码
@admin_router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    admin: Account = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if not admin:
        raise HTTPException(status_code=401)
    
    user = db.query(Account).filter(Account.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 生成新密码
    new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    user.password = hash_password(new_password)
    db.commit()
    
    return {"status": "success", "password": new_password}

# 邮件系统相关路由
@admin_router.get("/mails", response_class=HTMLResponse)
async def mail_page(
    request: Request,
    admin: Account = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if not admin:
        return RedirectResponse(url="/admin/login")
    
    # 获取道具列表供选择
    items = db.query(ItemTemplate).all()
    
    return templates.TemplateResponse(
        "mails/send.html",
        {
            "request": request,
            "user": admin,
            "items": items,
            "bind_types": list(BindType)
        }
    )

# 发送邮件
@admin_router.post("/mails/send")
async def send_mail(
    request: Request,
    admin: Account = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if not admin:
        raise HTTPException(status_code=401)
    
    data = await request.json()
    
    # 获取收件人列表
    if data['send_type'] == 'all':
        recipients = db.query(Account).filter(Account.status == 1).all()
    elif data['send_type'] == 'level':
        recipients = db.query(Account).join(Character).filter(
            Account.status == 1,
            Character.level.between(data['min_level'], data['max_level'])
        ).all()
    else:  # specific
        recipients = db.query(Account).filter(
            Account.status == 1,
            Account.id.in_(data['user_ids'])
        ).all()
    
    # 创建邮件
    for recipient in recipients:
        mail = Mail(
            receiver_id=recipient.id,
            sender_id=admin.id,
            sender_name="统管理员",
            title=data['title'],
            content=data['content'],
            mail_type=MailType.SYSTEM,
            has_attachment=bool(data['attachments']),
            attachments=data['attachments'],
            expire_time=datetime.utcnow() + timedelta(days=data['expire_days'])
        )
        db.add(mail)
    
    db.commit()
    return {"status": "success", "message": f"已发送给 {len(recipients)} 个用户"}

# 数据统计相关路由
@admin_router.get("/stats", response_class=HTMLResponse)
async def stats_dashboard(
    request: Request,
    admin: Account = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)
    
    # 计算基础统计数据
    total_users = db.query(Account).count()
    new_users_today = db.query(Account).filter(
        Account.created_at >= datetime.utcnow().date()
    ).count()
    
    online_users = db.query(UserToken).filter(
        UserToken.expired == False,
        UserToken.last_active >= datetime.utcnow() - timedelta(minutes=5)
    ).count()
    
    # 等级分布数据
    level_dist = db.query(
        Character.level,
        func.count(Character.id).label('count')
    ).group_by(Character.level).all()
    
    # 在线趋势数据（最近24小时）
    online_trend = []
    for hour in range(24):
        time_point = datetime.utcnow() - timedelta(hours=23-hour)
        count = db.query(UserToken).filter(
            UserToken.last_active >= time_point,
            UserToken.last_active < time_point + timedelta(hours=1)
        ).count()
        online_trend.append({
            'time': time_point.strftime('%H:00'),
            'count': count
        })
    
    stats = {
        'total_users': total_users,
        'new_users_today': new_users_today,
        'online_users': online_users,
        'level_dist': {
            'labels': [str(x[0]) for x in level_dist],
            'data': [x[1] for x in level_dist]
        },
        'online_trend': {
            'labels': [x['time'] for x in online_trend],
            'data': [x['count'] for x in online_trend]
        }
    }
    
    return templates.TemplateResponse(
        "stats/dashboard.html",
        {
            "request": request,
            "user": admin,
            "stats": stats
        }
    ) 