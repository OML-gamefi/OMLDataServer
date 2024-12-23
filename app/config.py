from typing import List
from pydantic_settings import BaseSettings
import logging

# 配置日志
logger = logging.getLogger(__name__)

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
    CORS_ORIGINS: str
    
    # JWT配置
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7天
    
    # AI配置
    AI_API_KEY: str
    AI_BASE_URL: str
    AI_MODEL: str

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        case_sensitive = True

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

# 创建设置实例
settings = Settings()