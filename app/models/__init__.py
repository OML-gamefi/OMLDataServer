from sqlalchemy import Column, Integer, String, ForeignKey, Float, DateTime, Enum, JSON, Text
from sqlalchemy.orm import relationship
from app.database import Base
import datetime
import enum
import sqlalchemy

# 添加用户角色枚举
class UserRole(enum.Enum):
    USER = "user"
    ADMIN = "admin"

# 添加软删除 Mixin
class SoftDeleteMixin:
    is_deleted = Column(Integer, default=0, nullable=False)  # 软删除标记：0-正常 1-已删除
    deleted_at = Column(DateTime, nullable=True)  # 删除时间
    deleted_by = Column(Integer, nullable=True)  # 删除操作者ID
    created_by = Column(Integer, nullable=True)  # 创建者ID
    updated_by = Column(Integer, nullable=True)  # 更新者ID
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.datetime.utcnow)  # 更新时间

class Account(SoftDeleteMixin, Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True) #id，从1000开始递增
    username = Column(String(50), unique=True, index=True, nullable=False) #用户名
    password = Column(String(100), nullable=False) #密码
    
    # 新增字段
    wallet_address = Column(String(100), unique=True, nullable=True)  # 钱包地址
    status = Column(Integer, default=0, nullable=False)  # 0: 未激活, 1: 正常, 2: 已封禁
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)  # 创建时间
    email = Column(String(100), unique=True, nullable=True)  # 邮箱地址
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)  # 用户角色
    avatar_url = Column(String(255), nullable=True)  # 头像URL
    oml_coin = Column(Integer, default=0, nullable=False)  # oml币
    user_setting = Column(String(255), nullable=True)  # 用户设计

    # 关系字段
    characters = relationship("Character", back_populates="account")
    tokens = relationship("UserToken", back_populates="account")
    
    __table_args__ = {
        'mysql_auto_increment': '1000'
    }
    
class UserToken(SoftDeleteMixin, Base):
    __tablename__ = "user_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    token = Column(String(255), unique=True, index=True, nullable=False)
    device_name = Column(String(100), nullable=False)  # 设备名称
    device_id = Column(String(100), nullable=False)    # 设备唯一标识
    last_active = Column(DateTime, default=datetime.datetime.utcnow)  # 最后活跃时间
    created_at = Column(DateTime, default=datetime.datetime.utcnow)   # 创建时间
    expired = Column(Integer, default=0)  # 是否已过期: 0-有效 1-过期
    
    # 关联到Account
    account = relationship("Account", back_populates="tokens")

# 种族枚举
class Race(enum.Enum):
    HUMAN = 1      # 人
    MONSTER = 2    # 妖
    GHOST = 3      # 鬼
    IMMORTAL = 4   # 仙

# 道具类型枚举
class ItemType(enum.Enum):
    EQUIPMENT = "装备"
    CONSUMABLE = "消耗品"
    MATERIAL = "材料"
    QUEST = "任务物品"
    OTHER = "其他"

# 道具绑定状态枚举
class BindType(enum.Enum):
    NONE = "不绑定"
    PICKUP = "拾取绑定"
    EQUIP = "装备绑定"
    ACCOUNT = "账号绑定"

# 装备位置枚举
class EquipmentSlot(enum.Enum):
    WEAPON = "武器"
    OFFHAND = "副手"
    HEAD = "头部"
    NECK = "项链"
    SHOULDER = "肩部"
    CHEST = "胸甲"
    WAIST = "腰带"
    LEGS = "腿部"
    FEET = "靴子"
    WRIST = "护腕"
    HANDS = "手套"
    FINGER1 = "戒指1"
    FINGER2 = "戒指2"
    TRINKET1 = "饰品1"
    TRINKET2 = "饰品2"
    BACK = "披风"

# 装备表（记录角色当前装备）
class CharacterEquipment(SoftDeleteMixin, Base):
    __tablename__ = "character_equipment"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False, unique=True)
    
    # 各个部位装备的背包物品ID（关联到inventory表的id）
    weapon_id = Column(Integer, nullable=True)        # 武器
    armor_id = Column(Integer, nullable=True)         # 护甲
    helmet_id = Column(Integer, nullable=True)        # 头部
    necklace_id = Column(Integer, nullable=True)      # 项链
    ring_1_id = Column(Integer, nullable=True)        # 戒指1
    ring_2_id = Column(Integer, nullable=True)        # 戒指2
    bracelet_1_id = Column(Integer, nullable=True)    # 手镯1
    bracelet_2_id = Column(Integer, nullable=True)    # 手镯2
    belt_id = Column(Integer, nullable=True)          # 腰带
    shoes_id = Column(Integer, nullable=True)         # 鞋子
    
    # 更新时间
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # 关系
    character = relationship("Character", back_populates="equipment")

    __table_args__ = (
        # 添加外键约束
        sqlalchemy.ForeignKeyConstraint(
            ['weapon_id'], ['inventory.id'],
            ondelete='SET NULL'
        ),
        sqlalchemy.ForeignKeyConstraint(
            ['armor_id'], ['inventory.id'],
            ondelete='SET NULL'
        ),
        sqlalchemy.ForeignKeyConstraint(
            ['helmet_id'], ['inventory.id'],
            ondelete='SET NULL'
        ),
        sqlalchemy.ForeignKeyConstraint(
            ['necklace_id'], ['inventory.id'],
            ondelete='SET NULL'
        ),
        sqlalchemy.ForeignKeyConstraint(
            ['ring_1_id'], ['inventory.id'],
            ondelete='SET NULL'
        ),
        sqlalchemy.ForeignKeyConstraint(
            ['ring_2_id'], ['inventory.id'],
            ondelete='SET NULL'
        ),
        sqlalchemy.ForeignKeyConstraint(
            ['bracelet_1_id'], ['inventory.id'],
            ondelete='SET NULL'
        ),
        sqlalchemy.ForeignKeyConstraint(
            ['bracelet_2_id'], ['inventory.id'],
            ondelete='SET NULL'
        ),
        sqlalchemy.ForeignKeyConstraint(
            ['belt_id'], ['inventory.id'],
            ondelete='SET NULL'
        ),
        sqlalchemy.ForeignKeyConstraint(
            ['shoes_id'], ['inventory.id'],
            ondelete='SET NULL'
        ),
        {
            'mysql_engine': 'InnoDB',
            'mysql_charset': 'utf8mb4',
            'mysql_collate': 'utf8mb4_unicode_ci'
        }
    )

# 角色表
class Character(SoftDeleteMixin, Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    sect_id = Column(Integer, nullable=True)  # 所属宗门ID
    race = Column(Enum(Race), nullable=False)  # 种族
    
    # 基础信息
    name = Column(String(50), unique=True, index=True, nullable=False)  # 角色名称
    current_location = Column(String(100), nullable=False, default="新手村")  # 当前位置
    
    # 基础属性
    max_hp = Column(Integer, default=100, nullable=False)  # 最大生命值
    current_hp = Column(Integer, default=100, nullable=False)  # 当前生命值
    max_mp = Column(Integer, default=100, nullable=False)  # 最大法力值
    current_mp = Column(Integer, default=100, nullable=False)  # 当前法力值
    
    # 战斗属性
    physical_attack = Column(Integer, default=10, nullable=False)  # 物理攻击
    magic_attack = Column(Integer, default=10, nullable=False)  # 魔法攻击
    physical_defense = Column(Integer, default=10, nullable=False)  # 物理防御
    magic_defense = Column(Integer, default=10, nullable=False)  # 魔法防御
    
    # 其他属性
    morality = Column(Integer, default=0, nullable=False)  # 善恶值
    max_stamina = Column(Integer, default=100, nullable=False)  # 体力上限
    current_stamina = Column(Integer, default=100, nullable=False)  # 当前体力
    copper_coins = Column(Integer, default=0, nullable=False)  # 铜钱（游戏币）
    
    # 时间相关
    created_at = Column(DateTime, default=datetime.datetime.utcnow)  # 创建时间
    last_login = Column(DateTime)  # 最后登录时间
    last_logout = Column(DateTime)  # 最后登出时间
    
    # 添加基础属性
    level = Column(Integer, default=1, nullable=False)  # 等级
    exp = Column(Integer, default=0, nullable=False)    # 经验值
    max_exp = Column(Integer, default=100, nullable=False)  # 当前等级最大经验值
    
    # 添加战斗相关属性
    speed = Column(Integer, default=10, nullable=False)  # 速度
    critical_rate = Column(Float, default=0.05, nullable=False)  # 暴击率
    critical_damage = Column(Float, default=1.5, nullable=False)  # 暴击伤害
    hit_rate = Column(Float, default=0.95, nullable=False)  # 命中率
    dodge_rate = Column(Float, default=0.05, nullable=False)  # 闪避率
    
    # 关系
    account = relationship("Account", back_populates="characters")
    inventory_items = relationship("Inventory", back_populates="character")
    equipment = relationship("CharacterEquipment", uselist=False, back_populates="character")
    mails = relationship("Mail", back_populates="receiver")
    quests = relationship("CharacterQuest", back_populates="character")
    favor_records = relationship("FavorRecord", back_populates="character")
    
    __table_args__ = {
        'mysql_engine': 'InnoDB',
        'mysql_charset': 'utf8mb4',
        'mysql_collate': 'utf8mb4_unicode_ci'
    }


# 背包表
class Inventory(SoftDeleteMixin, Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False, index=True)
    
    # 道具基本信息
    item_id = Column(Integer, nullable=False, index=True)  # 道具ID
    item_type = Column(Enum(ItemType), nullable=False)     # 道具类型
    quantity = Column(Integer, default=1, nullable=False)   # 数量
    
    # 背包相关
    slot = Column(Integer, nullable=False)                 # 背包格子位置
    bag_type = Column(Integer, default=0, nullable=False)  # 背包类型：0-主背包 1-材料包 2-任务包
    
    # 绑定相关
    bind_type = Column(Enum(BindType), default=BindType.NONE)  # 绑定类型
    bound_to = Column(Integer, nullable=True)                  # 绑定角色ID
    
    # 时效相关
    expire_time = Column(DateTime, nullable=True)          # 过期时间
    created_at = Column(DateTime, default=datetime.datetime.utcnow)  # 获得时间
    
    # 其他属性
    attributes = Column(JSON, nullable=True)               # 额外属性（如：强化等级、宝石槽等）
    durability = Column(Integer, nullable=True)            # 耐久度（装备特有）
    
    # 关系
    character = relationship("Character", back_populates="inventory_items")

    __table_args__ = (
        # 确保同一角色在同一背包类型中不会有重复的格子位置
        sqlalchemy.UniqueConstraint('character_id', 'bag_type', 'slot'),
        {
            'mysql_engine': 'InnoDB',
            'mysql_charset': 'utf8mb4',
            'mysql_collate': 'utf8mb4_unicode_ci'
        }
    )

# 邮件类型枚举
class MailType(enum.Enum):
    SYSTEM = 1      # 系统邮件
    PERSONAL = 2    # 个人邮件
    TRADE = 3       # 交易邮件
    GUILD = 4       # 公会邮件

# 邮件状态枚举
class MailStatus(enum.Enum):
    UNREAD = 0      # 未读
    READ = 1        # 已读
    CLAIMED = 2     # 已领取
    EXPIRED = 3     # 已过期
    DELETED = 4     # 已删除

# 邮件表
class Mail(SoftDeleteMixin, Base):
    __tablename__ = "mails"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 收发信息
    receiver_id = Column(Integer, ForeignKey("characters.id"), nullable=False, index=True)  # 接收者角色ID
    sender_id = Column(Integer, nullable=False)  # 发送者ID（0表示系统）
    sender_name = Column(String(50), nullable=False)  # 发送者名称
    
    # 邮件内容
    title = Column(String(100), nullable=False)  # 标题
    content = Column(Text, nullable=False)  # 内容
    mail_type = Column(Enum(MailType), nullable=False)  # 邮件类型
    
    # 附件信息
    has_attachment = Column(Integer, default=0)  # 是否有附件
    attachments = Column(JSON)  # 附件内容 [{item_id: xx, quantity: xx, bind_type: xx}, ...]
    
    # 状态信息
    status = Column(Enum(MailStatus), default=MailStatus.UNREAD)  # 邮件状态
    
    # 时间信息
    send_time = Column(DateTime, default=datetime.datetime.utcnow)  # 发送时间
    read_time = Column(DateTime, nullable=True)  # 阅读时间
    claim_time = Column(DateTime, nullable=True)  # 领取时间
    expire_time = Column(
        DateTime, 
        default=lambda: datetime.datetime.utcnow() + datetime.timedelta(days=7),
        nullable=False
    )  # 过期时间（7天后过期）
    
    # 关系
    receiver = relationship("Character", back_populates="mails")

    __table_args__ = {
        'mysql_engine': 'InnoDB',
        'mysql_charset': 'utf8mb4',
        'mysql_collate': 'utf8mb4_unicode_ci'
    }

# 任务状态枚举
class QuestStatus(enum.Enum):
    NOT_STARTED = 0    # 未开始
    IN_PROGRESS = 1    # 进行中
    COMPLETED = 2      # 已完成
    FAILED = 3         # 失败
    ABANDONED = 4      # 已放弃

# 任务类型枚举
class QuestType(enum.Enum):
    MAIN = 1          # 主线任务
    BRANCH = 2        # 支线任务
    DAILY = 3         # 日常任务
    WEEKLY = 4        # 周常任务
    EVENT = 5         # 活动任务
    HIDDEN = 6        # 隐藏任务
    ACHIEVEMENT = 7   # 成就任务

# 任务表
class CharacterQuest(SoftDeleteMixin, Base):
    __tablename__ = "character_quests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False, index=True)
    quest_id = Column(Integer, nullable=False)  # 任务模板ID
    quest_type = Column(Enum(QuestType), nullable=False)  # 任务类型
    status = Column(Enum(QuestStatus), default=QuestStatus.NOT_STARTED)  # 任务状态
    
    # 任务进度
    progress = Column(JSON)  # 任务进度，JSON格式存储 {target_id: count, ...}
    current_step = Column(Integer, default=1)  # 当前步骤
    
    # 时间信息
    accept_time = Column(DateTime, default=datetime.datetime.utcnow)  # 接取时间
    complete_time = Column(DateTime, nullable=True)  # 完成时间
    expire_time = Column(DateTime, nullable=True)  # 过期时间（用于限时任务）
    
    # 关系
    character = relationship("Character", back_populates="quests")

    __table_args__ = (
        # 确保同一角色不会重复接取同一任务
        sqlalchemy.UniqueConstraint('character_id', 'quest_id'),
        {
            'mysql_engine': 'InnoDB',
            'mysql_charset': 'utf8mb4',
            'mysql_collate': 'utf8mb4_unicode_ci'
        }
    )

# 好感度目标类型枚举
class FavorTargetType(enum.Enum):
    NPC = 1           # NPC
    FACTION = 2       # 势力
    SECT = 3          # 宗门
    GUILD = 4         # 公会

# 好感度表
class FavorRecord(SoftDeleteMixin, Base):
    __tablename__ = "favor_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False, index=True)
    target_type = Column(Enum(FavorTargetType), nullable=False)  # 目标类型
    target_id = Column(Integer, nullable=False)  # 目标ID
    
    # 好感度相关
    favor_value = Column(Integer, default=0)  # 好感度值
    intimacy = Column(Integer, default=0)  # 亲密度
    contribution = Column(Integer, default=0)  # 贡献度
    
    # 称号和权限
    title = Column(String(50), nullable=True)  # 称号
    special_permissions = Column(JSON, nullable=True)  # 特殊权限 {permission_id: expire_time, ...}
    
    # 等级相关
    level = Column(Integer, default=1)  # 关系等级
    current_exp = Column(Integer, default=0)  # 当前经验值
    
    # 互动记录
    daily_interaction_count = Column(Integer, default=0)  # 每日互动次数
    last_interaction_time = Column(DateTime, nullable=True)  # 最后互动时间
    last_reset_time = Column(DateTime, default=datetime.datetime.utcnow)  # 上次重置时间
    
    # 时间信息
    created_at = Column(DateTime, default=datetime.datetime.utcnow)  # 记录创建时间
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)  # 更新时间
    
    # 关系
    character = relationship("Character", back_populates="favor_records")

    __table_args__ = (
        # 确保每个角色对每个目标只有一条记录
        sqlalchemy.UniqueConstraint('character_id', 'target_type', 'target_id'),
        {
            'mysql_engine': 'InnoDB',
            'mysql_charset': 'utf8mb4',
            'mysql_collate': 'utf8mb4_unicode_ci'
        }
    )

# 道具品质枚举
class ItemQuality(enum.Enum):
    NORMAL = "普通"
    MAGIC = "魔法"
    RARE = "稀有"
    EPIC = "史诗"
    LEGENDARY = "传说"
    ARTIFACT = "神器"

# 道具模板表
class ItemTemplate(SoftDeleteMixin, Base):
    __tablename__ = "item_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)  # 道具名称
    description = Column(Text, nullable=True)  # 道具描述
    icon = Column(String(255), nullable=True)  # 图标路径
    
    # 基本属性
    type = Column(Enum(ItemType), nullable=False)  # 道具类型
    quality = Column(Enum(ItemQuality), nullable=False)  # 道具品质
    level = Column(Integer, default=1)  # 道具等级
    
    # 堆叠和绑定
    max_stack = Column(Integer, default=1)  # 最大堆叠数量
    bind_type = Column(Enum(BindType), default=BindType.NONE)  # 绑定类型
    
    # 装备专属属性（只有type为EQUIPMENT时才有效）
    equipment_slot = Column(Enum(EquipmentSlot), nullable=True)  # 装备位置
    physical_attack = Column(Integer, default=0, nullable=True)  # 物理攻击
    magic_attack = Column(Integer, default=0, nullable=True)  # 魔法攻击
    physical_defense = Column(Integer, default=0, nullable=True)  # 物理防御
    magic_defense = Column(Integer, default=0, nullable=True)  # 魔法防御
    hp_bonus = Column(Integer, default=0, nullable=True)  # 生命值加成
    mp_bonus = Column(Integer, default=0, nullable=True)  # 法力值加成
    
    # 使用相关
    usable = Column(Integer, default=0)  # 是否可使用
    use_script = Column(String(255), nullable=True)  # 使用脚本
    cooldown = Column(Integer, default=0)  # 使用冷却时间（秒）
    
    # 交易相关
    tradeable = Column(Integer, default=1)  # 是否可交易
    sellable = Column(Integer, default=1)  # 是否可出售
    buy_price = Column(Integer, default=0)  # 购买价格
    sell_price = Column(Integer, default=0)  # 出售价格
    
    # 其他属性
    extra_attributes = Column(JSON, nullable=True)  # 额外属性
    
    __table_args__ = (
        # 添加检查约束：如果type是EQUIPMENT，则equipment_slot不能为空
        sqlalchemy.CheckConstraint(
            "(type != 'EQUIPMENT') OR (type = 'EQUIPMENT' AND equipment_slot IS NOT NULL)",
            name='check_equipment_slot'
        ),
        {
            'mysql_engine': 'InnoDB',
            'mysql_charset': 'utf8mb4',
            'mysql_collate': 'utf8mb4_unicode_ci'
        }
    )

# 确保导出这两个类
__all__ = [
    # 基础模型
    'Account',
    'UserToken',
    'Character',
    'CharacterEquipment',
    'Inventory',
    'Mail',
    'CharacterQuest',
    'FavorRecord',
    'ItemTemplate',
    
    # 枚举类型
    'UserRole',
    'Race',
    'ItemType',
    'BindType',
    'EquipmentSlot',
    'MailType',
    'MailStatus',
    'QuestStatus',
    'QuestType',
    'FavorTargetType',
    'ItemQuality'
]