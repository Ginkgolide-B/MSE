"""
Pydantic Schema 定义 - API 请求/响应模型
"""
from pydantic import BaseModel
from typing import Optional, List


# ---------- 认证 ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user_id: int
    username: str
    token: str


class UserInfo(BaseModel):
    id: int
    username: str


# ---------- 卡牌 ----------
class CardInfo(BaseModel):
    id: int
    card_name: str
    card_type: str
    decision_cost: int
    attack_bonus: int
    effect_description: str
    effect_data: Optional[dict] = None
    exclusive_vehicle: Optional[str] = None


# ---------- 游戏 ----------
class CreateGameRequest(BaseModel):
    player1_id: int
    player1_vehicle: str  # M1_Abrams | T90M
    player1_ammo: Optional[dict] = None  # {card_id: quantity}


class JoinGameRequest(BaseModel):
    game_id: int
    player2_id: int
    player2_vehicle: str
    player2_ammo: Optional[dict] = None  # {card_id: quantity}


class PlayCardRequest(BaseModel):
    game_id: int
    player_id: int
    card_id: int


class GameStateInfo(BaseModel):
    game_id: int
    turn_number: int
    current_turn_player_id: int
    status: str
    winner_id: Optional[int] = None

    player1: Optional[dict] = None
    player2: Optional[dict] = None
    logs: List[dict] = []


class PlayerStateInfo(BaseModel):
    player_id: int
    username: str
    vehicle_type: str
    current_health: int
    max_health: int
    defense: int
    current_decision: int
    max_decision: int
    hand_cards: List[CardInfo]
    ammo_inventory: Optional[List[dict]] = None
    attack_buff: int
    damage_reduction: int
    modules: Optional[dict] = None  # 模块损坏状态


class ActionResponse(BaseModel):
    success: bool
    message: str
    game_state: Optional[GameStateInfo] = None


# ---------- MCP ----------
class MCPRequest(BaseModel):
    game_id: int
    player_id: int
    context: Optional[dict] = None


class MCPResponse(BaseModel):
    recommended_card_id: Optional[int] = None
    recommended_card_name: Optional[str] = None
    reason: str
    confidence: float