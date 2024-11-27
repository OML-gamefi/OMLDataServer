from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # 数据库配置
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    
    # API服务配置
    API_HOST: str
    API_PORT: int
    
    # CORS配置
    CORS_ORIGINS: str  # 直接使用与.env文件相同的变量名

    @property
    def cors_origins_list(self) -> List[str]:
        if not self.CORS_ORIGINS:
            return [
                "http://localhost:7456",
                "http://localhost:8080",
                "http://127.0.0.1:7456",
                "http://127.0.0.1:8080",
                "http://18.136.199.150:8021",
                "*"
            ]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False
    }

settings = Settings() 