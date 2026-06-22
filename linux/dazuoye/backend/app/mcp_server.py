"""
MCP (Model Context Protocol) 服务器 + AI 对手引擎

两个功能：
1. get_decision_recommendation() - 单步决策推荐（给前端"AI 建议"按钮用）
2. execute_ai_turn() - 完整 AI 回合执行（自动出牌 + 结束回合）

AI 策略规则引擎：
- 若血量 < 30%，优先使用"紧急维修"
- 若还没开热成像，优先开启
- 使用烟雾弹减伤（对手有高攻击炮弹可用时）
- 优先使用最高攻击力的可用炮弹
- 决策值快满时优先使用"战术突击"
- 其余决策牌按需使用
- 无法行动或攻击完后结束回合
"""
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import GameState, Card, Game, GameLog
from app.game_engine import VEHICLE_CONFIGS, validate_play_card, execute_play_card, check_game_over, end_turn


async def get_decision_recommendation(
    db: AsyncSession,
    game_id: int,
    player_id: int,
) -> dict:
    """
    根据当前游戏状态推荐最优决策（单步，供前端调用）。
    返回一张推荐的卡牌，或建议结束回合。
    """
    state, hand_cards, affordable = await _get_playable_state(db, game_id, player_id)
    if state is None:
        return {"recommended_card_id": None, "recommended_card_name": None, "reason": "无法获取游戏状态", "confidence": 0.0}

    if not affordable:
        return {"recommended_card_id": None, "recommended_card_name": None, "reason": "决策值不足或手牌为空，建议结束回合", "confidence": 0.8}

    # 策略 1：血量低时推荐维修
    health_ratio = state.current_health / state.max_health
    if health_ratio < 0.3:
        repair = next((c for c in affordable if c.card_name == "紧急维修"), None)
        if repair:
            return {"recommended_card_id": repair.id, "recommended_card_name": repair.card_name,
                    "reason": f"血量仅剩 {state.current_health}/{state.max_health}，建议紧急维修", "confidence": 0.9}

    # 策略 2：先使用热成像（模块倍率还没开的话）
    thermal = next((c for c in affordable if c.card_name == "热成像" and (state.module_damage_multiplier or 1.0) <= 1.0), None)
    if thermal:
        return {"recommended_card_id": thermal.id, "recommended_card_name": thermal.card_name,
                "reason": "建议先使用热成像增加模块损坏概率", "confidence": 0.75}

    # 策略 3：推荐消耗最低的炮弹
    ammo_cards = [c for c in affordable if c.card_type == "ammo"]
    if ammo_cards:
        cheapest = min(ammo_cards, key=lambda c: c.decision_cost)
        ed = cheapest.effect_data or {}
        if ed.get("two_hit"):
            atk_str = f"{ed.get('first_attack_min',0)}-{ed.get('first_attack_max',0)}+{ed.get('second_attack',0)}"
        elif "attack_min" in ed:
            atk_str = f"{ed['attack_min']}-{ed['attack_max']}"
        else:
            atk_str = str(cheapest.attack_bonus)
        return {"recommended_card_id": cheapest.id, "recommended_card_name": cheapest.card_name,
                "reason": f"推荐使用 {cheapest.card_name}（消耗 {cheapest.decision_cost}，攻击 {atk_str}）", "confidence": 0.7}

    # 策略 4：推荐消耗最低的决策牌
    cheapest = min(affordable, key=lambda c: c.decision_cost)
    return {"recommended_card_id": cheapest.id, "recommended_card_name": cheapest.card_name,
            "reason": f"推荐使用 {cheapest.card_name}（消耗 {cheapest.decision_cost}）", "confidence": 0.6}


# =============================================================
# AI 完整回合执行（自动打多张牌 + 结束回合）
# =============================================================

async def execute_ai_turn(db: AsyncSession, game_id: int, ai_player_id: int) -> dict:
    """
    AI 执行一整个回合：
    1. 反复决策 → 出牌 → 直到无法行动
    2. 结束回合
    3. 返回执行的动作列表
    """
    actions = []

    # 最多尝试 10 次出牌防止死循环
    for _ in range(10):
        # 检查游戏是否已结束
        game = await db.get(Game, game_id)
        if not game or game.status != "active":
            break
        if game.current_turn_player_id != ai_player_id:
            break

        # 获取 AI 的可玩手牌
        state, hand_cards, affordable = await _get_playable_state(db, game_id, ai_player_id)
        if state is None:
            break

        # 选取最佳卡牌
        best_card = await _ai_select_card(state, affordable, hand_cards)
        if best_card is None:
            # 没有合适的牌了，准备结束回合
            break

        # 验证并出牌
        game = await db.get(Game, game_id)
        valid, msg = await validate_play_card(db, game, state, best_card.id)
        if not valid:
            continue

        # 获取对手状态
        opponent_id = game.player2_id if game.player1_id == ai_player_id else game.player1_id
        opp_state_query = await db.execute(
            select(GameState).where(GameState.game_id == game_id, GameState.player_id == opponent_id)
        )
        opp_state = opp_state_query.scalar_one()

        # 执行出牌
        desc = await execute_play_card(db, game, state, opp_state, best_card)
        actions.append({"card_name": best_card.card_name, "description": desc})

        # 检查游戏是否结束
        game_over = await check_game_over(db, game, state, opp_state)
        if game_over:
            actions.append({"card_name": None, "description": "游戏结束！"})
            break

    # 结束回合
    game = await db.get(Game, game_id)
    if game and game.status == "active" and game.current_turn_player_id == ai_player_id:
        state_query = await db.execute(
            select(GameState).where(GameState.game_id == game_id, GameState.player_id == ai_player_id)
        )
        state = state_query.scalar_one()
        await end_turn(db, game, state)
        actions.append({"card_name": None, "description": "AI 结束回合"})

    return {"actions": actions}


async def _get_playable_state(db, game_id, player_id):
    """获取玩家状态和可用的手牌列表（含弹药库存）"""
    state_query = await db.execute(
        select(GameState).where(GameState.game_id == game_id, GameState.player_id == player_id)
    )
    state = state_query.scalar_one_or_none()
    if not state:
        return None, [], []

    # 决策牌手牌
    hand_ids = list(state.hand_cards)
    all_card_ids = set(hand_ids)

    # 弹药库存中的卡牌ID
    ammo = dict(state.ammo_inventory) if state.ammo_inventory else {}
    for aid in ammo.keys():
        all_card_ids.add(int(aid))

    if not all_card_ids:
        return state, [], []

    cards_query = await db.execute(select(Card).where(Card.id.in_(list(all_card_ids))))
    all_cards = list(cards_query.scalars().all())

    hand_cards = [c for c in all_cards if c.id in hand_ids]
    # 弹药卡也加入可选列表
    ammo_cards = [c for c in all_cards if c.card_type == "ammo"]

    affordable = [c for c in hand_cards + ammo_cards if c.decision_cost <= state.current_decision]
    return state, hand_cards + ammo_cards, affordable


async def _ai_select_card(state: GameState, affordable: List[Card], hand_cards: List[Card]) -> Optional[Card]:
    """
    AI 选牌策略：
    1. 有模块损坏 → 紧急维修
    2. 模块倍率为1.0 → 热成像
    3. 防御buff为0 → 反应装甲
    4. 最高攻击炮弹
    5. 烟雾弹防御
    6. 最低消耗牌
    """
    if not affordable:
        return None

    affordable_map = {c.card_name: c for c in affordable}

    # 1. 有模块损坏时优先维修
    has_module_damage = (
        state.main_gun_status != 0 or
        state.turret_drive_status != 0 or
        state.engine_status != 0
    )
    if has_module_damage and "紧急维修" in affordable_map:
        return affordable_map["紧急维修"]

    # 2. 血量低急救
    health_ratio = state.current_health / state.max_health
    if health_ratio < 0.4 and "紧急维修" in affordable_map:
        return affordable_map["紧急维修"]

    # 3. 热成像（模块倍率还没开的话）
    if (state.module_damage_multiplier or 1.0) <= 1.0 and "热成像" in affordable_map:
        return affordable_map["热成像"]

    # 4. 反应装甲（防御buff还没开的话）
    if (state.defense_buff or 0) == 0 and "反应装甲" in affordable_map:
        return affordable_map["反应装甲"]

    # 5. 优先使用炮弹攻击
    ammo_cards = [c for c in affordable if c.card_type == "ammo"]
    if ammo_cards:
        def _avg_attack(c):
            ed = c.effect_data or {}
            if ed.get("two_hit"):
                avg1 = (ed.get("first_attack_min", 0) + ed.get("first_attack_max", 0)) / 2
                return avg1 + ed.get("second_attack", 0)
            if "attack_min" in ed and "attack_max" in ed:
                return (ed["attack_min"] + ed["attack_max"]) / 2
            return c.attack_bonus
        sorted_ammo = sorted(ammo_cards, key=lambda c: -_avg_attack(c))
        return sorted_ammo[0]

    # 6. 烟雾弹防御
    if state.damage_reduction == 0 and "烟雾弹" in affordable_map:
        return affordable_map["烟雾弹"]

    # 7. 选最低消耗的
    return min(affordable, key=lambda c: c.decision_cost)