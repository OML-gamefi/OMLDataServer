from sqlalchemy import create_engine, text
from app.config import settings
import logging

# 配置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 数据库URL
DATABASE_URL = f"mysql+pymysql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"

def clean_database():
    try:
        # 创建数据库引擎
        engine = create_engine(DATABASE_URL)
        
        # 获取所有表名
        with engine.connect() as connection:
            # 禁用外键检查
            connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            
            # 获取所有表名
            result = connection.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result]
            
            # 删除所有表
            for table in tables:
                logger.info(f"正在删除表: {table}")
                connection.execute(text(f"DROP TABLE IF EXISTS {table}"))
            
            # 启用外键检查
            connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
            
            connection.commit()
            
        logger.info("所有表已成功删除")
        
    except Exception as e:
        logger.error(f"删除表时发生错误: {str(e)}")
        raise

if __name__ == "__main__":
    logger.info("开始清理数据库...")
    clean_database()
    logger.info("数据库清理完成") 