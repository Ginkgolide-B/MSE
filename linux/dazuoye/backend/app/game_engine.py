"""
游戏引擎 - 核心对战逻辑
包含：初始化、抽牌、出牌验证、伤害计算、回合切换
"""
import random
from typing import Tuple, Optional, Dict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Game, GameState, Card, GameLog, User

# =============================================================
# 载具配置表（硬编码，便于后续调整）
# =============================================================
VEHICLE_CONFIGS = {
    "M1_Abrams": {
        "name": "M1 Abrams",
        "max_health": 18,
        "defense": 6,
        "max_decision": 5,
        "min_ammo": 5,
        "max_ammo": 42,
        "description": "美国第三代主战坦克，火力与防护均衡",
    },
    "T90M": {
        "name": "T-90M",
        "max_health": 15,
        "defense": 9,
        "max_decision": 5,
        "min_ammo": 5,
        "max_ammo": 40,
        "description": "俄罗斯主战坦克，装甲厚重，火力凶猛",
    },
    "Leclerc": {
        "name": "勒克莱尔",
        "max_health": 13,
        "defense": 5,
        "max_decision": 6,
        "min_ammo": 5,
        "max_ammo": 40,
        "description": "法国主战坦克，高灵活性著称",
    },
}


async def initialize_game_state(
    db: AsyncSession,
    game: Game,
    player_id: int,
    vehicle_type: str,
    ammo_selection: Optional[Dict[int, int]] = None,
) -> GameState:
    """
    初始化一个玩家的游戏状态：
    - 设置载具属性
    - 弹药牌：根据玩家选择直接放入 ammo_inventory
    - 决策牌：从牌池随机抽取 3 张作为初始手牌（无数量限制）
    """
    config = VEHICLE_CONFIGS[vehicle_type]

    # 查询所有决策牌（通用，无专属）
    decision_query = select(Card).where(
        Card.card_type == "decision",
        (Card.exclusive_vehicle.is_(None)) | (Card.exclusive_vehicle == vehicle_type),
    )
    decision_result = await db.execute(decision_query)
    decision_cards = decision_result.scalars().all()
    decision_pool = [c.id for c in decision_cards]

    # 初始手牌：从牌池随机抽 3 张（可重复）
    hand_ids = random.choices(decision_pool, k=3) if decision_pool else []

    # 处理弹药选择
    ammo_inventory = {}
    if ammo_selection:
        total = sum(ammo_selection.values())
        if total < config["min_ammo"] or total > config["max_ammo"]:
            raise ValueError(
                f"载弹量必须在 {config['min_ammo']}-{config['max_ammo']} 之间，当前 {total}"
            )
        # 验证所有弹药牌是否合法（通用 + 该载具专属）
        ammo_ids = list(ammo_selection.keys())
        ammo_query = select(Card).where(
            Card.id.in_(ammo_ids),
            Card.card_type == "ammo",
            (Card.exclusive_vehicle.is_(None)) | (Card.exclusive_vehicle == vehicle_type),
        )
        ammo_result = await db.execute(ammo_query)
        valid_ammo = {c.id for c in ammo_result.scalars().all()}
        for aid in ammo_ids:
            if aid not in valid_ammo:
                raise ValueError(f"卡牌 {aid} 不适用于该载具")
        # 转为字符串键存储（JSON 兼容）
        ammo_inventory = {str(k): v for k, v in ammo_selection.items() if v > 0}
    else:
        # 无选择时默认分配：专属炮弹各5发，通用炮弹各5发
        all_ammo_query = select(Card).where(
            Card.card_type == "ammo",
            (Card.exclusive_vehicle.is_(None)) | (Card.exclusive_vehicle == vehicle_type),
        )
        all_ammo_result = await db.execute(all_ammo_query)
        all_ammo = all_ammo_result.scalars().all()
        for c in all_ammo:
            ammo_inventory[str(c.id)] = 5

    state = GameState(
        game_id=game.id,
        player_id=player_id,
        vehicle_type=vehicle_type,
        max_health=config["max_health"],
        current_health=config["max_health"],
        defense=config["defense"],
        max_decision=config["max_decision"],
        current_decision=config["max_decision"],
        hand_cards=hand_ids,
        deck_cards=[],      # 决策牌无数量限制，不再使用牌库
        ammo_inventory=ammo_inventory,
    )
    db.add(state)
    await db.flush()
    return state


async def draw_card(db: AsyncSession, state: GameState) -> Optional[int]:
    """
    从决策牌池随机抽取一张牌（无数量限制，可重复）。
    返回抽到的 card_id。
    """
    decision_query = select(Card).where(
        Card.card_type == "decision",
        (Card.exclusive_vehicle.is_(None)) | (Card.exclusive_vehicle == state.vehicle_type),
    )
    decision_result = await db.execute(decision_query)
    decision_cards = decision_result.scalars().all()
    pool = [c.id for c in decision_cards]
    if not pool:
        return None
    card_id = random.choice(pool)
    hand = list(state.hand_cards)
    hand.append(card_id)
    state.hand_cards = hand
    await db.flush()
    return card_id


async def reset_decision(state: GameState):
    """每回合开始：决策上限+1，然后重置决策值至上限"""
    state.max_decision += 1
    state.current_decision = state.max_decision
    # 重置临时 buff
    state.attack_buff = 0
    state.damage_reduction = 0
    state.ignore_defense = 0
    state.defense_buff = 0
    state.module_damage_multiplier = 1.0


async def validate_play_card(
    db: AsyncSession,
    game: Game,
    state: GameState,
    card_id: int,
) -> Tuple[bool, str]:
    """
    验证出牌合法性：
    1. 卡牌是否存在
    2. 是否为该玩家回合
    3. 决策牌→在手牌中 / 弹药牌→在弹药库存中
    4. 决策值是否足够
    5. 专属载具限制
    """
    card_query = await db.execute(select(Card).where(Card.id == card_id))
    card = card_query.scalar_one_or_none()
    if not card:
        return False, "卡牌不存在"

    if game.current_turn_player_id != state.player_id:
        return False, "不是你的回合"

    # 弹药牌：检查弹药库存
    if card.card_type == "ammo":
        ammo = dict(state.ammo_inventory) if state.ammo_inventory else {}
        if str(card_id) not in ammo or ammo[str(card_id)] <= 0:
            return False, "该弹药已耗尽"
    else:
        # 决策牌：检查手牌
        if card_id not in state.hand_cards:
            return False, "该卡牌不在手牌中"

    if state.current_decision < card.decision_cost:
        return False, f"决策值不足（需要 {card.decision_cost}，当前 {state.current_decision}）"

    if card.exclusive_vehicle and card.exclusive_vehicle != state.vehicle_type:
        return False, f"该卡牌为 {card.exclusive_vehicle} 专属"

    return True, "OK"


async def execute_play_card(
    db: AsyncSession,
    game: Game,
    state: GameState,
    opponent_state: GameState,
    card: Card,
) -> str:
    """执行出牌效果（含模块损坏机制）"""
    # 扣除决策值
    state.current_decision -= card.decision_cost

    # 移除卡牌：弹药牌扣库存，决策牌从手牌移除
    if card.card_type == "ammo":
        ammo = dict(state.ammo_inventory) if state.ammo_inventory else {}
        key = str(card.id)
        ammo[key] = ammo.get(key, 0) - 1
        if ammo[key] <= 0:
            del ammo[key]
        state.ammo_inventory = ammo
    else:
        hand = list(state.hand_cards)
        hand.remove(card.id)
        state.hand_cards = hand

    description = ""

    if card.card_type == "ammo":
        # ===== 先检查己方主炮和方向机状态 =====
        ammo_fail_reason = None

        if state.main_gun_status == 1:
            ammo_fail_reason = "主炮已损毁，炮弹无法发射！"
        elif state.main_gun_status == 2 and random.random() < 0.3:
            ammo_fail_reason = "主炮轻微损坏，发射失败！"

        if ammo_fail_reason:
            log = GameLog(game_id=game.id, player_id=state.player_id,
                          action_type="play_card", card_id=card.id, description=ammo_fail_reason)
            db.add(log)
            await db.flush()
            return ammo_fail_reason

        ed = card.effect_data or {}

        # 解析攻击力：有 attack_min/attack_max 时随机取值，否则用 attack_bonus
        if "attack_min" in ed and "attack_max" in ed:
            base_attack = random.randint(ed["attack_min"], ed["attack_max"])
        else:
            base_attack = card.attack_bonus

        buff = state.attack_buff

        # 模块损坏概率倍率
        module_multiplier = float(ed.get("module_damage_multiplier", 1.0))

        # 方向机损坏检查
        description = ""
        effective_attack = base_attack

        if state.turret_drive_status == 1:
            td_roll = random.random()
            if td_roll < 0.6:
                effective_attack = 0
                description += "【方向机损坏】攻击无效！"
            elif td_roll < 0.8:
                effective_attack = max(0, effective_attack // 2)
                description += "【方向机损坏】攻击减半！"

        # 防御 = 基础防御 + 临时防御加成（反应装甲等）
        defense = opponent_state.defense + (opponent_state.defense_buff or 0)
        if state.ignore_defense:
            defense = 0

        # 合并模块损坏概率倍率：热成像(1.5) × 弹药牌自身倍率
        effective_multiplier = module_multiplier * (state.module_damage_multiplier or 1.0)

        # ---- 核心：处理伤害 ----
        if ed.get("two_hit"):
            # === 两次伤害（9M119M 炮射导弹）===
            first_attack = random.randint(ed["first_attack_min"], ed["first_attack_max"])
            first_multiplier = float(ed.get("first_module_multiplier", 1.0))
            second_attack = ed["second_attack"]

            description += f"使用 {card.card_name}，"

            # 第一次伤害
            first_total = first_attack + buff
            if effective_attack == 0:
                first_total = 0
            # 烟雾弹：70% 概率免疫
            if opponent_state.damage_reduction > 0 and random.random() < 0.7:
                first_damage = 0
                description += "【烟雾弹】免疫第一次伤害！"
            elif first_total > defense:
                first_damage = first_total - defense
            else:
                first_damage = 0
            if first_damage > 0:
                opponent_state.current_health -= first_damage
                description += f"第一次造成 {first_damage} 点伤害"
                module_desc = await _apply_module_damage(opponent_state, first_multiplier * effective_multiplier)
                if module_desc:
                    description += "，" + module_desc
            else:
                description += "第一次未造成伤害"

            # 第二次伤害
            second_total = second_attack + buff
            if effective_attack == 0:
                second_total = 0
            if second_total > defense:
                second_damage = second_total - defense
            else:
                second_damage = 0
            if second_damage > 0:
                opponent_state.current_health -= second_damage
                description += f"；第二次造成 {second_damage} 点伤害"
                module_desc2 = await _apply_module_damage(opponent_state, 1.0 * effective_multiplier)
                if module_desc2:
                    description += "，" + module_desc2
            else:
                description += "；第二次未造成伤害"
            description += "！"
        else:
            # === 普通单次伤害 ===
            total_attack = base_attack + buff
            if effective_attack == 0:
                total_attack = 0

            # 烟雾弹：70% 概率免疫
            if opponent_state.damage_reduction > 0 and random.random() < 0.7:
                final_damage = 0
                description += "【烟雾弹】攻击被免疫！"
            elif total_attack > defense:
                final_damage = total_attack - defense
            else:
                final_damage = 0

            if final_damage > 0:
                opponent_state.current_health -= final_damage
                description += f"使用 {card.card_name}，造成 {final_damage} 点伤害！"
                # 模块损坏判定
                module_desc = await _apply_module_damage(opponent_state, effective_multiplier)
                if module_desc:
                    description += module_desc
            else:
                description += f"使用 {card.card_name}，未造成伤害！"

    elif card.card_type == "decision":
        if card.card_name == "烟雾弹":
            state.damage_reduction = 1
            description = "释放烟雾弹，敌方攻击有70%概率无法造成伤害！"
        elif card.card_name == "热成像":
            state.module_damage_multiplier = 1.5
            description = "启用热成像，本回合模块损坏概率变为150%！"
        elif card.card_name == "紧急维修":
            heal = 5
            state.current_health = min(state.max_health, state.current_health + heal)
            # 移除全部模块损坏状态
            state.main_gun_status = 0
            state.main_gun_timer = 0
            state.turret_drive_status = 0
            state.turret_drive_timer = 0
            if state.engine_saved_max_decision > 0:
                state.max_decision = state.engine_saved_max_decision
                state.engine_saved_max_decision = 0
            state.engine_status = 0
            state.engine_timer = 0
            description = f"紧急维修，恢复 {heal} 点生命值，移除全部模块损坏！"
        elif card.card_name == "反应装甲":
            state.defense_buff += 5
            description = "加装反应装甲，下一回合防御 +5！"
        else:
            description = f"使用决策牌：{card.card_name}"

    log = GameLog(
        game_id=game.id,
        player_id=state.player_id,
        action_type="play_card",
        card_id=card.id,
        description=description,
    )
    db.add(log)
    await db.flush()
    return description


async def check_game_over(
    db: AsyncSession,
    game: Game,
    state: GameState,
    opponent_state: GameState,
) -> bool:
    if state.current_health <= 0:
        game.status = "finished"
        game.winner_id = opponent_state.player_id
        game.finished_at = func.now()
        await _log_game_over(db, game, opponent_state.player_id)
        return True
    if opponent_state.current_health <= 0:
        game.status = "finished"
        game.winner_id = state.player_id
        game.finished_at = func.now()
        await _log_game_over(db, game, state.player_id)
        return True
    return False


async def _log_game_over(db: AsyncSession, game: Game, winner_id: int):
    log = GameLog(
        game_id=game.id,
        player_id=winner_id,
        action_type="game_over",
        description=f"玩家 {winner_id} 获胜！",
    )
    db.add(log)
    await db.flush()


async def end_turn(db: AsyncSession, game: Game, current_state: GameState):
    """结束当前回合：切换玩家 → 新回合玩家获得一张决策牌 → 新回合开始"""
    await _update_module_timers(current_state)

    next_player_id = (
        game.player2_id if game.current_turn_player_id == game.player1_id
        else game.player1_id
    )
    game.current_turn_player_id = next_player_id
    game.turn_number += 1

    # 获取下一位玩家状态
    next_state_query = await db.execute(
        select(GameState).where(
            GameState.game_id == game.id,
            GameState.player_id == next_player_id,
        )
    )
    next_state = next_state_query.scalar_one()

    # 每回合开始：给当前行动玩家发一张随机决策牌
    card = await draw_card(db, next_state)

    log = GameLog(
        game_id=game.id,
        player_id=next_player_id,
        action_type="end_turn",
        description=f"新回合开始，获得一张决策牌",
    )
    db.add(log)

    await reset_decision(next_state)

    await db.flush()


# =============================================================
# 模块损坏机制
# =============================================================

async def _apply_module_damage(victim_state: GameState, multiplier: float = 1.0) -> str:
    """应用模块损坏判定，multiplier 为概率倍率（默认 1.0）"""
    desc = ""

    # 1. 主炮损坏
    if victim_state.main_gun_status == 0:
        roll = random.random()
        if roll < 0.05 * multiplier:
            victim_state.main_gun_status = 1
            victim_state.main_gun_timer = 2
            desc += "【主炮损毁】对方主炮被击毁，2回合内无法使用炮弹！"
        elif roll < 0.20 * multiplier:
            victim_state.main_gun_status = 2
            victim_state.main_gun_timer = 2
            desc += "【主炮损坏】对方主炮轻微损坏，2回合内30%概率发射失败！"

    # 2. 方向机损坏
    if victim_state.turret_drive_status == 0:
        if victim_state.vehicle_type == "M1_Abrams":
            td_prob = 0.20 * multiplier
        elif victim_state.vehicle_type == "T90M":
            td_prob = 0.15 * multiplier
        else:
            td_prob = 0.15 * multiplier
        if random.random() < td_prob:
            victim_state.turret_drive_status = 1
            victim_state.turret_drive_timer = 2
            desc += "【方向机损坏】对方方向机损坏，2回合内炮塔旋转受阻！"

    # 3. 发动机损坏
    if victim_state.engine_status == 0:
        roll = random.random()
        if roll < 0.05 * multiplier:
            victim_state.engine_status = 2
            victim_state.engine_timer = 2
            victim_state.engine_saved_max_decision = victim_state.max_decision
            reduction = victim_state.max_decision * 60 // 100
            victim_state.max_decision -= reduction
            desc += "【发动机完全损毁】对方决策上限减少60%！"
        elif roll < 0.20 * multiplier:
            victim_state.engine_status = 1
            victim_state.engine_timer = 2
            victim_state.engine_saved_max_decision = victim_state.max_decision
            reduction = victim_state.max_decision * 30 // 100
            victim_state.max_decision -= reduction
            desc += "【发动机轻微损毁】对方决策上限减少30%！"

    return desc


async def _update_module_timers(state: GameState):
    if state.main_gun_timer > 0:
        state.main_gun_timer -= 1
        if state.main_gun_timer == 0:
            state.main_gun_status = 0

    if state.turret_drive_timer > 0:
        state.turret_drive_timer -= 1
        if state.turret_drive_timer == 0:
            state.turret_drive_status = 0

    if state.engine_timer > 0:
        state.engine_timer -= 1
        if state.engine_timer == 0:
            if state.engine_saved_max_decision > 0:
                state.max_decision = state.engine_saved_max_decision
                state.engine_saved_max_decision = 0
            state.engine_status = 0


async def get_game_state_info(
    db: AsyncSession, game: Game, player_id: int
) -> dict:
    my_state_query = await db.execute(
        select(GameState).where(
            GameState.game_id == game.id,
            GameState.player_id == player_id,
        )
    )
    my_state = my_state_query.scalar_one()

    opponent_id = (
        game.player2_id if game.player1_id == player_id else game.player1_id
    )
    opp_state_query = await db.execute(
        select(GameState).where(
            GameState.game_id == game.id,
            GameState.player_id == opponent_id,
        )
    )
    opp_state = opp_state_query.scalar_one()

    user_query = await db.execute(select(User).where(User.id == player_id))
    my_user = user_query.scalar_one()

    opp_user_query = await db.execute(select(User).where(User.id == opponent_id))
    opp_user = opp_user_query.scalar_one()

    # 决策手牌详细信息
    hand_card_ids = list(my_state.hand_cards)
    hand_cards_info = []
    if hand_card_ids:
        cards_query = await db.execute(
            select(Card).where(Card.id.in_(hand_card_ids))
        )
        cards_map = {c.id: c for c in cards_query.scalars().all()}
        for cid in hand_card_ids:
            if cid in cards_map:
                c = cards_map[cid]
                hand_cards_info.append({
                    "id": c.id,
                    "card_name": c.card_name,
                    "card_type": c.card_type,
                    "decision_cost": c.decision_cost,
                    "attack_bonus": c.attack_bonus,
                    "effect_description": c.effect_description,
                    "effect_data": c.effect_data,
                    "exclusive_vehicle": c.exclusive_vehicle,
                })

    # 弹药库存详细信息
    ammo_info = []
    ammo = dict(my_state.ammo_inventory) if my_state.ammo_inventory else {}
    if ammo:
        ammo_ids = [int(k) for k in ammo.keys()]
        ammo_cards_query = await db.execute(
            select(Card).where(Card.id.in_(ammo_ids))
        )
        ammo_cards_map = {c.id: c for c in ammo_cards_query.scalars().all()}
        for aid, qty in ammo.items():
            c = ammo_cards_map.get(int(aid))
            if c:
                ammo_info.append({
                    "id": c.id,
                    "card_name": c.card_name,
                    "card_type": c.card_type,
                    "decision_cost": c.decision_cost,
                    "attack_bonus": c.attack_bonus,
                    "effect_description": c.effect_description,
                    "effect_data": c.effect_data,
                    "exclusive_vehicle": c.exclusive_vehicle,
                    "quantity": qty,
                })

    # 对方弹药库存（仅显示种类，不显示数量）
    opp_ammo_info = []
    opp_ammo = dict(opp_state.ammo_inventory) if opp_state.ammo_inventory else {}
    if opp_ammo:
        opp_ammo_ids = [int(k) for k in opp_ammo.keys()]
        opp_ammo_cards_query = await db.execute(
            select(Card).where(Card.id.in_(opp_ammo_ids))
        )
        opp_ammo_cards_map = {c.id: c for c in opp_ammo_cards_query.scalars().all()}
        for aid, qty in opp_ammo.items():
            c = opp_ammo_cards_map.get(int(aid))
            if c:
                opp_ammo_info.append({
                    "id": c.id,
                    "card_name": c.card_name,
                    "card_type": c.card_type,
                    "decision_cost": c.decision_cost,
                    "attack_bonus": c.attack_bonus,
                    "effect_description": c.effect_description,
                    "effect_data": c.effect_data,
                    "exclusive_vehicle": c.exclusive_vehicle,
                    "quantity": 0,  # 不暴露对方弹药数量
                })

    # 日志
    logs_query = await db.execute(
        select(GameLog).where(GameLog.game_id == game.id).order_by(GameLog.created_at)
    )
    logs = [
        {
            "id": log.id,
            "player_id": log.player_id,
            "action_type": log.action_type,
            "description": log.description,
            "created_at": log.created_at.isoformat() if log.created_at else "",
        }
        for log in logs_query.scalars().all()
    ]

    return {
        "game_id": game.id,
        "turn_number": game.turn_number,
        "current_turn_player_id": game.current_turn_player_id,
        "status": game.status,
        "winner_id": game.winner_id,
        "player1": {
            "player_id": my_state.player_id,
            "username": my_user.username,
            "vehicle_type": my_state.vehicle_type,
            "current_health": my_state.current_health,
            "max_health": my_state.max_health,
            "defense": my_state.defense + (my_state.defense_buff or 0),
            "current_decision": my_state.current_decision,
            "max_decision": my_state.max_decision,
            "hand_cards": hand_cards_info,
            "ammo_inventory": ammo_info,
            "attack_buff": my_state.attack_buff,
            "damage_reduction": my_state.damage_reduction,
            "modules": {
                "main_gun": {"status": my_state.main_gun_status, "timer": my_state.main_gun_timer},
                "turret_drive": {"status": my_state.turret_drive_status, "timer": my_state.turret_drive_timer},
                "engine": {"status": my_state.engine_status, "timer": my_state.engine_timer},
            },
        },
        "player2": {
            "player_id": opp_state.player_id,
            "username": opp_user.username,
            "vehicle_type": opp_state.vehicle_type,
            "current_health": opp_state.current_health,
            "max_health": opp_state.max_health,
            "defense": opp_state.defense + (opp_state.defense_buff or 0),
            "current_decision": opp_state.current_decision,
            "max_decision": opp_state.max_decision,
            "hand_cards": [],
            "ammo_inventory": opp_ammo_info,
            "attack_buff": opp_state.attack_buff,
            "damage_reduction": opp_state.damage_reduction,
            "modules": {
                "main_gun": {"status": opp_state.main_gun_status, "timer": opp_state.main_gun_timer},
                "turret_drive": {"status": opp_state.turret_drive_status, "timer": opp_state.turret_drive_timer},
                "engine": {"status": opp_state.engine_status, "timer": opp_state.engine_timer},
            },
        },
        "logs": logs,
    }