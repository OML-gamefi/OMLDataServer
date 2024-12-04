from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.ext.declarative import DeclarativeMeta
from app.database import Base
from app.utils.password import hash_password
import logging

ModelType = TypeVar("ModelType", bound=DeclarativeMeta)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)

logger = logging.getLogger(__name__)

class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, db: Session, id: Any) -> Optional[ModelType]:
        return db.query(self.model).filter(self.model.id == id).first()

    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[ModelType]:
        return db.query(self.model).offset(skip).limit(limit).all()

    def create(self, db: Session, *, data: Dict[str, Any]) -> ModelType:
        try:
            # 如果是Account模型且包含password字段，进行密码加密
            if self.model.__name__ == 'Account' and 'password' in data:
                data['password'] = hash_password(data['password'])
                logger.debug(f"已对用户密码进行加密: username={data.get('username')}")

            db_obj = self.model(**data)
            db.add(db_obj)
            db.commit()
            db.refresh(db_obj)
            return db_obj
        except Exception as e:
            logger.error(f"创建{self.model.__name__}失败: {str(e)}")
            db.rollback()
            raise

    def update(self, db: Session, *, id: Any, data: Dict[str, Any]) -> Optional[ModelType]:
        try:
            db_obj = db.query(self.model).filter(self.model.id == id).first()
            if not db_obj:
                return None

            # 如果是Account模型且要更新password字段，进行密码加密
            if self.model.__name__ == 'Account' and 'password' in data:
                data['password'] = hash_password(data['password'])
                logger.debug(f"已对用户新密码进行加密: id={id}")

            for key, value in data.items():
                setattr(db_obj, key, value)
            
            db.commit()
            db.refresh(db_obj)
            return db_obj
        except Exception as e:
            logger.error(f"更新{self.model.__name__}失败: {str(e)}")
            db.rollback()
            raise

    def remove(self, db: Session, *, id: int) -> Optional[ModelType]:
        try:
            db_obj = db.query(self.model).filter(self.model.id == id).first()
            if not db_obj:
                return None
            
            db.delete(db_obj)
            db.commit()
            return db_obj
        except Exception as e:
            logger.error(f"删除{self.model.__name__}失败: {str(e)}")
            db.rollback()
            raise

class CRUDRegister:
    _instances: Dict[str, CRUDBase] = {}

    @classmethod
    def register(cls, model_class: Type[ModelType]) -> CRUDBase:
        """注册模型类到CRUD实例"""
        if model_class.__name__ not in cls._instances:
            cls._instances[model_class.__name__] = CRUDBase(model_class)
        return cls._instances[model_class.__name__]

    @classmethod
    def get(cls, model_name: str) -> Optional[CRUDBase]:
        """获取CRUD实例"""
        return cls._instances.get(model_name)

    @classmethod
    def get_all_models(cls) -> List[str]:
        """获取所有已注册的模型名称"""
        return list(cls._instances.keys())

# 确保导出这些类
__all__ = ['CRUDBase', 'CRUDRegister'] 