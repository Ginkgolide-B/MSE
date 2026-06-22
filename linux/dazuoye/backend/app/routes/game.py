"""
游戏路由 - 创建/加入/进行游戏
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Game, GameState, Card, User
from app.schemas import (
    CreateGameRequest, JoinGameRequest, PlayCardRequest,
    ActionResponse, GameStateInfo,
)
from app.game_engine import (
    initialize_game_state, validate_play_card, execute_play_card,
    check_game_over, end_turn, get_game_state_info,
    VEHICLE_CONFIGS,
)
from app.mcp_server import execute_ai_turn

router = APIRouter(prefix="/api/game", tags=["游戏"])


def _parse_ammo(raw: dict | None) -> dict | None:
    """将前端传来的字符串键字典转为整数键"""
    if not raw:
        return None
    return {int(k): v for k, v in raw.items()}


@router.post("/create")
async def create_game(req: CreateGameRequest, db: AsyncSession = Depends(get_db)):
    """创建新对局（本地热座模式，Player1 先手）"""
    if req.player1_vehicle not in VEHICLE_CONFIGS:
        raise HTTPException(status_code=400, detail="无效的载具类型")

    user_query = await db.execute(select(User).where(User.id == req.player1_id))
    if not user_query.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="玩家不存在")

    game = Game(
        player1_id=req.player1_id,
        status="waiting",
    )
    db.add(game)
    await db.flush()

    ammo = _parse_ammo(req.player1_ammo)
    await initialize_game_state(db, game, req.player1_id, req.player1_vehicle, ammo)

    return {
        "game_id": game.id,
        "status": "waiting",
        "message": "游戏已创建，等待玩家2加入",
    }


@router.post("/join")
async def join_game(req: JoinGameRequest, db: AsyncSession = Depends(get_db)):
    """加入对局（Player2 加入）"""
    if req.player2_vehicle not in VEHICLE_CONFIGS:
        raise HTTPException(status_code=400, detail="无效的载具类型")

    game_query = await db.execute(select(Game).where(Game.id == req.game_id))
    game = game_query.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="对局不存在")
    if game.status != "waiting":
        raise HTTPException(status_code=400, detail="对局已开始或已结束")
    if game.player1_id == req.player2_id:
        raise HTTPException(status_code=400, detail="不能和自己对战")

    user_query = await db.execute(select(User).where(User.id == req.player2_id))
    if not user_query.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="玩家不存在")

    game.player2_id = req.player2_id
    game.current_turn_player_id = game.player1_id
    game.status = "active"
    game.turn_number = 1
    await db.flush()

    ammo = _parse_ammo(req.player2_ammo)
    await initialize_game_state(db, game, req.player2_id, req.player2_vehicle, ammo)

    return {
        "game_id": game.id,
        "status": "active",
        "message": "已加入对局，游戏开始！Player1 先手",
    }


@router.post("/play")
async def play_card(req: PlayCardRequest, db: AsyncSession = Depends(get_db)):
    """出牌动作"""
    game_query = await db.execute(select(Game).where(Game.id == req.game_id))
    game = game_query.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="对局不存在")
    if game.status != "active":
        raise HTTPException(status_code=400, detail="对局未激活或已结束")

    card_query = await db.execute(select(Card).where(Card.id == req.card_id))
    card = card_query.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="卡牌不存在")

    state_query = await db.execute(
        select(GameState).where(
            GameState.game_id == req.game_id,
            GameState.player_id == req.player_id,
        )
    )
    state = state_query.scalar_one_or_none()
    if not state:
        raise HTTPException(status_code=404, detail="玩家状态不存在")

    valid, msg = await validate_play_card(db, game, state, req.card_id)
    if not valid:
        raise HTTPException(status_code=400, detail=msg)

    opponent_id = (
        game.player2_id if game.player1_id == req.player_id else game.player1_id
    )
    opp_query = await db.execute(
        select(GameState).where(
            GameState.game_id == req.game_id,
            GameState.player_id == opponent_id,
        )
    )
    opp_state = opp_query.scalar_one()

    desc = await execute_play_card(db, game, state, opp_state, card)

    game_over = await check_game_over(db, game, state, opp_state)

    game_state = await get_game_state_info(db, game, req.player_id)
    if game_over:
        return ActionResponse(
            success=True,
            message=f"{desc} 游戏结束！",
            game_state=game_state,
        )

    return ActionResponse(
        success=True,
        message=desc,
        game_state=game_state,
    )


@router.post("/end-turn")
async def end_turn_route(
    game_id: int, player_id: int,
    db: AsyncSession = Depends(get_db),
):
    """结束当前回合"""
    game_query = await db.execute(select(Game).where(Game.id == game_id))
    game = game_query.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="对局不存在")
    if game.status != "active":
        raise HTTPException(status_code=400, detail="对局已结束")
    if game.current_turn_player_id != player_id:
        raise HTTPException(status_code=400, detail="不是你的回合")

    state_query = await db.execute(
        select(GameState).where(
            GameState.game_id == game_id,
            GameState.player_id == player_id,
        )
    )
    state = state_query.scalar_one()

    await end_turn(db, game, state)

    game_state = await get_game_state_info(db, game, player_id)
    return ActionResponse(
        success=True,
        message="回合结束",
        game_state=game_state,
    )


@router.get("/state/{game_id}/{player_id}")
async def get_state(game_id: int, player_id: int, db: AsyncSession = Depends(get_db)):
    """获取当前游戏状态"""
    game_query = await db.execute(select(Game).where(Game.id == game_id))
    game = game_query.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="对局不存在")

    game_state = await get_game_state_info(db, game, player_id)
    return game_state


@router.get("/vehicles")
async def list_vehicles():
    """列出可用载具"""
    vehicles = []
    for key, config in VEHICLE_CONFIGS.items():
        vehicles.append({
            "id": key,
            "name": config["name"],
            "max_health": config["max_health"],
            "defense": config["defense"],
            "max_decision": config["max_decision"],
            "min_ammo": config["min_ammo"],
            "max_ammo": config["max_ammo"],
            "description": config["description"],
        })
    return vehicles


@router.get("/ammo-cards/{vehicle_type}")
async def list_ammo_cards(vehicle_type: str, db: AsyncSession = Depends(get_db)):
    """列出某载具可用的弹药牌"""
    if vehicle_type not in VEHICLE_CONFIGS:
        raise HTTPException(status_code=400, detail="无效的载具类型")

    card_query = await db.execute(
        select(Card).where(
            Card.card_type == "ammo",
            (Card.exclusive_vehicle.is_(None)) | (Card.exclusive_vehicle == vehicle_type),
        )
    )
    cards = card_query.scalars().all()
    return [
        {
            "id": c.id,
            "card_name": c.card_name,
            "decision_cost": c.decision_cost,
            "attack_bonus": c.attack_bonus,
            "effect_description": c.effect_description,
            "effect_data": c.effect_data,
            "exclusive_vehicle": c.exclusive_vehicle,
        }
        for c in cards
    ]


@router.get("/list")
async def list_games(db: AsyncSession = Depends(get_db)):
    """列出所有游戏（用于调试）"""
    result = await db.execute(select(Game).order_by(Game.created_at.desc()).limit(10))
    games = result.scalars().all()
    return [
        {
            "id": g.id,
            "player1_id": g.player1_id,
            "player2_id": g.player2_id,
            "status": g.status,
            "winner_id": g.winner_id,
            "turn_number": g.turn_number,
            "created_at": str(g.created_at),
        }
        for g in games
    ]


# =============================================================
# AI 对战接口
# =============================================================

AI_BOT_USER_ID = 3


@router.post("/create-ai")
async def create_ai_game(
    player_id: int,
    player_vehicle: str,
    ai_vehicle: str = "T90M",
    player_ammo: dict | None = Body(None),
    db: AsyncSession = Depends(get_db),
):
    """创建与 AI 的对局（支持弹药选择）"""
    if player_vehicle not in VEHICLE_CONFIGS:
        raise HTTPException(status_code=400, detail="无效的载具类型")
    if ai_vehicle not in VEHICLE_CONFIGS:
        raise HTTPException(status_code=400, detail="无效的 AI 载具类型")

    user_query = await db.execute(select(User).where(User.id == player_id))
    if not user_query.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="玩家不存在")

    bot_query = await db.execute(select(User).where(User.id == AI_BOT_USER_ID))
    if not bot_query.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="AI Bot 不存在")

    game = Game(
        player1_id=player_id,
        player2_id=AI_BOT_USER_ID,
        current_turn_player_id=player_id,
        status="active",
        turn_number=1,
    )
    db.add(game)
    await db.flush()

    ammo = _parse_ammo(player_ammo)
    await initialize_game_state(db, game, player_id, player_vehicle, ammo)
    await initialize_game_state(db, game, AI_BOT_USER_ID, ai_vehicle)

    return {
        "game_id": game.id,
        "status": "active",
        "message": f"AI 对战已开始！你使用 {VEHICLE_CONFIGS[player_vehicle]['name']}，AI 使用 {VEHICLE_CONFIGS[ai_vehicle]['name']}",
    }


@router.post("/ai-move")
async def ai_make_move(
    game_id: int,
    db: AsyncSession = Depends(get_db),
):
    """AI 执行一整个回合"""
    game_query = await db.execute(select(Game).where(Game.id == game_id))
    game = game_query.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="对局不存在")
    if game.status != "active":
        raise HTTPException(status_code=400, detail="对局已结束")
    if game.current_turn_player_id != AI_BOT_USER_ID:
        raise HTTPException(status_code=400, detail="当前不是 AI 的回合")

    result = await execute_ai_turn(db, game_id, AI_BOT_USER_ID)

    game_state = await get_game_state_info(db, game, game.player1_id)

    return {
        "success": True,
        "actions": result["actions"],
        "game_state": game_state,
    }