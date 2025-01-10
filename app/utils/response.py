from enum import Enum
from typing import Any, Dict, Union, Optional

# 统一错误码
class ResponseCode(int, Enum):
    SUCCESS = 200  # 成功
    PARAM_ERROR = 400  # 参数错误
    UNAUTHORIZED = 401  # 未授权
    FORBIDDEN = 403  # 禁止访问
    NOT_FOUND = 404  # 资源未找在
    CONFLICT = 409  # 资源冲突
    SYSTEM_ERROR = 500  # 系统错误
    
    # 账号相关错误码 (1000-1999)
    ACCOUNT_NOT_FOUND = 1001  # 账号不存在
    ACCOUNT_DISABLED = 1002  # 账号已禁用
    PASSWORD_ERROR = 1003  # 密码错误
    TOKEN_INVALID = 1004  # Token无效
    TOKEN_EXPIRED = 1005  # Token已过期
    DEVICE_NOT_MATCH = 1006  # 设备不匹配
    LOGIN_FAILED = 1007  # 登录失败
    LOGOUT_FAILED = 1008  # 登出失败
    ACCOUNT_EXISTS = 1009  # 账号已存在
    EMAIL_EXISTS = 1010  # 邮箱已存在
    WALLET_EXISTS = 1011  # 钱包地址已存在
    DEVICE_NOT_FOUND = 1012  # 设备不存在
    INVALID_DEVICE_DATA = 1013  # 设备信息无效
    
    # 角色相关错误码 (2000-2999)
    CHARACTER_NOT_FOUND = 2001  # 角色不存在
    CHARACTER_DELETED = 2002  # 角色已删除
    CHARACTER_MAX_LIMIT = 2003  # 角色数量达到上限
    CHARACTER_NAME_EXISTS = 2004  # 角色名已存在
    CHARACTER_LEVEL_LIMIT = 2005  # 角色等级不足
    INVALID_RACE = 2006         # 无效的种族
    INVALID_LOCATION = 2007     # 无效的位置
    
    # 物品相关错误码 (3000-3999)
    ITEM_NOT_FOUND = 3001     # 物品不存在
    ITEM_NOT_ENOUGH = 3002    # 物品数量不足
    ITEM_EQUIPPED = 3003      # 物品已装备
    ITEM_NOT_EQUIPPED = 3004  # 物品未装备
    ITEM_NOT_USABLE = 3005   # 物品不可使用
    ITEM_BIND_STATUS = 3006  # 物品绑定状态不符
    INVALID_ITEM_DATA = 3007 # 物品数据无效
    
    # 邮件相关错误码 (4000-4999)
    MAIL_NOT_FOUND = 4001  # 邮件不存在
    MAIL_EXPIRED = 4002  # 邮件已过期
    MAIL_NO_ATTACHMENT = 4003  # 邮件无附件
    MAIL_CLAIMED = 4004  # 附件已领取
    MAIL_DELETED = 4005  # 邮件已删除
    MAIL_SEND_FAILED = 4006  # 邮件发送失败

# 统一返回方法
def response(*, code: Union[int, ResponseCode] = ResponseCode.SUCCESS, 
            message: str = "SUCCESS",
            data: Any = None) -> Dict[str, Any]:
    """
    统一返回方法
    
    参数：
        code: 错误码，默认为200（成功）
        message: 错误信息，默认为"SUCCESS"
        data: 返回数据，默认为None
    
    返回统一格式的响应数据
    """
    return {
        "code": code if isinstance(code, int) else code.value,
        "message": message.upper() if message else "SUCCESS",
        "data": data
    } 