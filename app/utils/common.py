from fastapi import Header

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