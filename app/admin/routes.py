from fastapi import APIRouter, Request, Response, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import (
    Account, UserRole, ItemTemplate, ItemType, 
    ItemQuality, BindType, EquipmentSlot, UserToken, Character, Mail, MailType
)
from typing import Optional
import jwt
from datetime import datetime, timedelta
import random
import string
from sqlalchemy import func

# 创建路由
admin_router = APIRouter(prefix="/admin")

# 设置模板
templates = Jinja2Templates(directory="app/admin/templates")

# JWT 配置
SECRET_KEY = "your-secret-key"  # 应该从配置文件读取
ALGORITHM = "HS256"

# 验证管理员
async def get_current_admin(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[Account]:
    token = request.cookies.get("admin_token")
    if not token:
        return None
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        account = db.query(Account).filter(Account.id == payload["sub"]).first()
        if not account or account.role != UserRole.ADMIN:
            return None
        return account
    except:
        return None

# 登录页面
@admin_router.get("/", response_class=HTMLResponse)
@admin_router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    admin: Account = Depends(get_current_admin)
):
    if admin:
        return RedirectResponse(url="/admin/dashboard")
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )

# 登录处理
@admin_router.post("/login")
async def login(
    request: Request,
    db: Session = Depends(get_db)
):
    form = await request.form()
    username = form.get("username")
    password = form.get("password")
    
    account = db.query(Account).filter(Account.username == username).first()
    if not account or account.password != password or account.role != UserRole.ADMIN:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "messages": [{"type": "danger", "text": "用户名或密码错误"}]
            }
        )
    
    # 创建 JWT token
    token = jwt.encode(
        {
            "sub": str(account.id),
            "exp": datetime.utcnow() + timedelta(days=1)
        },
        SECRET_KEY,
        algorithm=ALGORITHM
    )
    
    response = RedirectResponse(url="/admin/dashboard", status_code=303)
    response.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        max_age=86400  # 1天
    )
    return response

# 仪表盘
@admin_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    admin: Account = Depends(get_current_admin)
):
    if not admin:
        return RedirectResponse(url="/admin/login")
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": admin}
    )

# 登出
@admin_router.get("/logout")
async def logout():
    response = RedirectResponse(url="/admin/login")
    response.delete_cookie("admin_token")
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
@admin_router.get("/items/create", response_class=HTMLResponse)
async def create_item_page(
    request: Request,
    admin: Account = Depends(get_current_admin)
):
    if not admin:
        return RedirectResponse(url="/admin/login")
    
    return templates.TemplateResponse(
        "items/edit.html",
        {
            "request": request,
            "user": admin,
            "item": None,
            "item_types": list(ItemType),
            "item_qualities": list(ItemQuality),
            "bind_types": list(BindType),
            "equipment_slots": list(EquipmentSlot)
        }
    )

# 编辑道具页面
@admin_router.get("/items/{item_id}/edit", response_class=HTMLResponse)
async def edit_item_page(
    request: Request,
    item_id: int,
    admin: Account = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if not admin:
        return RedirectResponse(url="/admin/login")
    
    item = db.query(ItemTemplate).filter(ItemTemplate.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    return templates.TemplateResponse(
        "items/edit.html",
        {
            "request": request,
            "user": admin,
            "item": item,
            "item_types": list(ItemType),
            "item_qualities": list(ItemQuality),
            "bind_types": list(BindType),
            "equipment_slots": list(EquipmentSlot)
        }
    )

# 创建道具API
@admin_router.post("/items")
async def create_item(
    request: Request,
    admin: Account = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if not admin:
        raise HTTPException(status_code=401)
    
    data = await request.json()
    item = ItemTemplate(**data)
    db.add(item)
    db.commit()
    db.refresh(item)
    
    return {"id": item.id}

# 更新道具API
@admin_router.put("/items/{item_id}")
async def update_item(
    item_id: int,
    request: Request,
    admin: Account = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if not admin:
        raise HTTPException(status_code=401)
    
    item = db.query(ItemTemplate).filter(ItemTemplate.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    data = await request.json()
    for key, value in data.items():
        setattr(item, key, value)
    
    db.commit()
    return {"status": "success"}

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
    user.password = new_password  # 实际应用中应该加密
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
            sender_name="系统管理员",
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
        return RedirectResponse(url="/admin/login")
    
    # 计算基础统计数据
    total_users = db.query(Account).count()
    new_users_today = db.query(Account).filter(
        Account.created_at >= datetime.utcnow().date()
    ).count()
    
    online_users = db.query(UserToken).filter(
        UserToken.expired == 0,
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