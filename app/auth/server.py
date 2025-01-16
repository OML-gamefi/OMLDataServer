import json
import os
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException
from app.utils.response import response, ResponseCode

# 创建路由
server_router = APIRouter(prefix="/api/auth")

def load_server_config() -> Dict:
    """
    加载服务器配置文件
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, 'server_config.json')
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=response(
                code=ResponseCode.SYSTEM_ERROR,
                message="无法加载服务器配置"
            )
        )

@server_router.get("/servers",
    summary="获取服务器列表",
    description="""
    获取游戏服务器列表信息。
    
    权限要求：
    - 无需Token
    
    返回数据：
    - servers: 服务器列表
      - id: 服务器ID
      - name: 服务器名称
      - description: 服务器描述
      - ip: 服务器IP
      - port: 服务器端口
      - status: 服务器状态
        - 0: 关闭 - 服务器不可访问
        - 1: 正常 - 服务器运行正常
        - 2: 爆满 - 服务器人数接近上限
        - 3: 维护 - 服务器正在维护
      - is_new: 是否新服
      - is_recommend: 是否推荐
      - maintenance: 是否维护中
      - server_load: 服务器负载（0-100）
      - created_at: 创建时间
      - region: 服务器地区
      - max_players: 最大玩家数
      - current_players: 当前玩家数
    
    可能的错误码：
    - 500: 系统错误
    
    成功返回示例：
    ```json
    {
        "code": 200,
        "message": "SUCCESS",
        "data": [
            {
                "id": 1,
                "name": "测试服务器",
                "description": "用于测试的服务器",
                "ip": "127.0.0.1",
                "port": 3235,
                "status": 1,
                "is_new": true,
                "is_recommend": true,
                "maintenance": false,
                "server_load": 0,
                "created_at": "2024-01-01T00:00:00",
                "region": "中国",
                "max_players": 1000,
                "current_players": 0
            }
        ]
    }
    ```
    
    错误返回示例：
    ```json
    {
        "code": 500,
        "message": "SYSTEM_ERROR",
        "data": null
    }
    ```
    
    注意事项：
    1. 推荐优先选择 is_recommend 为 true 的服务器
    2. 新服会有 is_new 标记
    3. 维护中的服务器不可登录
    4. 服务器负载超过80%时，状态会自动变为"爆满"
    """
)
async def get_servers():
    """获取服务器列表"""
    try:
        config = load_server_config()
        return response(
            code=ResponseCode.SUCCESS,
            message="SUCCESS",
            data=config["servers"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=response(
                code=ResponseCode.SYSTEM_ERROR,
                message="获取服务器列表失败"
            )
        ) 