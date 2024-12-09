from sqlalchemy import create_engine, text
import logging
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SQLALCHEMY_DATABASE_URL, Base, engine
from app.models import Character, CharacterEquipment, FavorRecord, CharacterQuest, Inventory, Mail

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def reset_characters():
    """
    删除并重新创建角色相关的所有表
    """
    try:
        # 创建数据库引擎
        engine = create_engine(SQLALCHEMY_DATABASE_URL)
        
        # 创建连接
        with engine.connect() as connection:
            # 开始事务
            with connection.begin():
                logger.info("开始删除角色相关表...")
                
                # 按顺序删除表
                connection.execute(text("DROP TABLE IF EXISTS character_equipment"))
                connection.execute(text("DROP TABLE IF EXISTS favor_records"))
                connection.execute(text("DROP TABLE IF EXISTS character_quests"))
                connection.execute(text("DROP TABLE IF EXISTS inventory"))
                connection.execute(text("DROP TABLE IF EXISTS mails"))
                connection.execute(text("DROP TABLE IF EXISTS characters"))
                
                logger.info("表删除完成，开始重新创建表...")
                
                # 重新创建表
                Character.__table__.create(engine)
                CharacterEquipment.__table__.create(engine)
                FavorRecord.__table__.create(engine)
                CharacterQuest.__table__.create(engine)
                Inventory.__table__.create(engine)
                Mail.__table__.create(engine)
                
                logger.info("表重建完成！")
            
    except Exception as e:
        logger.error(f"重置过程中发生错误: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        reset_characters()
    except Exception as e:
        logger.error(f"重置失败: {str(e)}")
        sys.exit(1) 