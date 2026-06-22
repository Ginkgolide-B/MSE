"""
SQLAlchemy ORM 模型定义
映射数据库中的所有表
"""
from sqlalchemy import (
    Column, Integer, String, ForeignKey, Text, DateTime, CheckConstraint, JSON, UniqueConstraint, Float
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    card_name = Column(String(100), nullable=False)
    card_type = Column(String(20), nullable=False)  # 'ammo' | 'decision'
    decision_cost = Column(Integer, nullable=False)
    attack_bonus = Column(Integer, default=0)
    effect_description = Column(String(500), default="")
    effect_data = Column(JSON, nullable=True)  # 特殊效果参数 {"attack_min":3, "attack_max":11, ...}
    exclusive_vehicle = Column(String(50), nullable=True)  # NULL = 通用
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("card_type IN ('ammo', 'decision')", name="ck_card_type"),
        CheckConstraint("decision_cost >= 0", name="ck_decision_cost"),
    )


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player1_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    player2_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    current_turn_player_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String(20), default="waiting")  # waiting | active | finished
    winner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    turn_number = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('waiting', 'active', 'finished')", name="ck_game_status"),
    )

    player1 = relationship("User", foreign_keys=[player1_id])
    player2 = relationship("User", foreign_keys=[player2_id])


class GameState(Base):
    __tablename__ = "game_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    vehicle_type = Column(String(50), nullable=False)
    max_health = Column(Integer, default=100, nullable=False)
    current_health = Column(Integer, default=100, nullable=False)
    defense = Column(Integer, default=0, nullable=False)
    max_decision = Column(Integer, default=100, nullable=False)
    current_decision = Column(Integer, default=100, nullable=False)
    hand_cards = Column(JSON, default=list)      # 决策牌手牌
    deck_cards = Column(JSON, default=list)      # 决策牌牌库
    ammo_inventory = Column(JSON, default=dict)   # 弹药库存 {card_id: quantity}
    attack_buff = Column(Integer, default=0)
    damage_reduction = Column(Integer, default=0)
    ignore_defense = Column(Integer, default=0)   # 1=本回合无视对方防御
    defense_buff = Column(Integer, default=0)    # 临时防御加成（反应装甲）
    module_damage_multiplier = Column(Float, default=1.0)  # 模块损坏概率倍率（热成像）
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

# === 模块损坏状态 ===
    main_gun_status = Column(Integer, default=0)      # 0=正常 1=主炮损毁 2=主炮轻微损坏
    main_gun_timer = Column(Integer, default=0)        # 剩余回合数
    turret_drive_status = Column(Integer, default=0)   # 0=正常 1=方向机损坏
    turret_drive_timer = Column(Integer, default=0)     # 剩余回合数
    engine_status = Column(Integer, default=0)          # 0=正常 1=发动机轻微损毁 2=发动机完全损毁
    engine_timer = Column(Integer, default=0)           # 剩余回合数
    engine_saved_max_decision = Column(Integer, default=0)  # 发动机损坏前的决策上限（用于恢复）
    __table_args__ = (
        UniqueConstraint("game_id", "player_id", name="uq_game_player"),
    )


class GameLog(Base):
    __tablename__ = "game_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action_type = Column(String(50), nullable=False)  # play_card | end_turn | game_over
    card_id = Column(Integer, ForeignKey("cards.id"), nullable=True)
    description = Column(String(500), default="")
    created_at = Column(DateTime, server_default=func.now())