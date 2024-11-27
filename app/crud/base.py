from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.ext.declarative import DeclarativeMeta

ModelType = TypeVar("ModelType", bound=DeclarativeMeta)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)

class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, db: Session, id: Any) -> Optional[ModelType]:
        return db.query(self.model).filter(self.model.id == id).first()

    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[ModelType]:
        return db.query(self.model).offset(skip).limit(limit).all()

    def create(self, db: Session, *, data: Dict[str, Any]) -> ModelType:
        db_obj = self.model(**data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, *, id: Any, data: Dict[str, Any]) -> Optional[ModelType]:
        db_obj = self.get(db, id)
        if db_obj:
            for field, value in data.items():
                if hasattr(db_obj, field):
                    setattr(db_obj, field, value)
            db.add(db_obj)
            db.commit()
            db.refresh(db_obj)
        return db_obj

    def remove(self, db: Session, *, id: int) -> Optional[ModelType]:
        obj = self.get(db, id)
        if obj:
            db.delete(obj)
            db.commit()
        return obj

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