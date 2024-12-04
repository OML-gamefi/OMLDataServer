from pydantic import BaseModel, Field
from typing import Optional
from app.models import ItemType, ItemQuality, BindType, EquipmentSlot

class ItemCreate(BaseModel):
    name: str = Field(..., description="道具名称")
    type: str = Field(..., description="道具类型")
    quality: str = Field(..., description="道具品质")
    level: int = Field(..., ge=1, description="道具等级")
    description: Optional[str] = Field(None, description="道具描述")
    max_stack: int = Field(1, ge=1, description="最大堆叠数量")
    bind_type: Optional[str] = Field(None, description="绑定类型")
    equipment_slot: Optional[str] = Field(None, description="装备槽位")
    physical_attack: int = Field(0, ge=0, description="物理攻击")
    magic_attack: int = Field(0, ge=0, description="魔法攻击")
    physical_defense: int = Field(0, ge=0, description="物理防御")
    magic_defense: int = Field(0, ge=0, description="魔法防御")
    hp_bonus: int = Field(0, ge=0, description="生命值加成")
    mp_bonus: int = Field(0, ge=0, description="魔法值加成")

    class Config:
        schema_extra = {
            "example": {
                "name": "新手木剑",
                "type": "EQUIPMENT",
                "quality": "NORMAL",
                "level": 1,
                "description": "新手常用的木制长剑",
                "max_stack": 1,
                "bind_type": "PICKUP",
                "equipment_slot": "WEAPON",
                "physical_attack": 5,
                "magic_attack": 0,
                "physical_defense": 0,
                "magic_defense": 0,
                "hp_bonus": 0,
                "mp_bonus": 0
            }
        } 