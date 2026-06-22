-- =============================================================
-- 战争雷霆主题卡牌对战游戏 - 数据库初始化脚本
-- PostgreSQL DDL + 初始种子数据
-- =============================================================

-- 启用 UUID 扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================
-- 1. 用户表
-- =============================================================
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(50) UNIQUE NOT NULL,
    password_hash   VARCHAR(256) NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================
-- 2. 卡牌表（炮弹牌 & 决策牌共用）
-- =============================================================
CREATE TABLE IF NOT EXISTS cards (
    id                  SERIAL PRIMARY KEY,
    card_name           VARCHAR(100) NOT NULL,
    card_type           VARCHAR(20) NOT NULL CHECK (card_type IN ('ammo', 'decision')),
    decision_cost       INTEGER NOT NULL CHECK (decision_cost >= 0),
    attack_bonus        INTEGER DEFAULT 0,        -- 攻击力加成（炮弹牌）/ 0 表示决策牌
    effect_description  VARCHAR(500) DEFAULT '',   -- 效果描述
    effect_data         JSONB DEFAULT NULL,        -- 特殊效果参数（如攻击范围、模块概率倍率等）
    exclusive_vehicle   VARCHAR(50) DEFAULT NULL,  -- 专属载具（NULL 表示通用）
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (card_name, exclusive_vehicle)         -- 防止重复插入
);

-- =============================================================
-- 3. 游戏房间表
-- =============================================================
CREATE TABLE IF NOT EXISTS games (
    id                      SERIAL PRIMARY KEY,
    player1_id              INTEGER NOT NULL REFERENCES users(id),
    player2_id              INTEGER DEFAULT NULL REFERENCES users(id),
    current_turn_player_id  INTEGER DEFAULT NULL REFERENCES users(id),
    status                  VARCHAR(20) DEFAULT 'waiting' CHECK (status IN ('waiting', 'active', 'finished')),
    winner_id               INTEGER DEFAULT NULL REFERENCES users(id),
    turn_number             INTEGER DEFAULT 0,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at             TIMESTAMP DEFAULT NULL
);

-- =============================================================
-- 4. 游戏状态表（每个玩家一个状态行）
-- =============================================================
CREATE TABLE IF NOT EXISTS game_states (
    id              SERIAL PRIMARY KEY,
    game_id         INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    player_id       INTEGER NOT NULL REFERENCES users(id),
    vehicle_type    VARCHAR(50) NOT NULL,           -- 'M1_Abrams' 或 'T90M'
    -- 载具基础属性
    max_health      INTEGER NOT NULL DEFAULT 100,
    current_health  INTEGER NOT NULL DEFAULT 100,
    defense         INTEGER NOT NULL DEFAULT 0,
    max_decision    INTEGER NOT NULL DEFAULT 100,   -- 决策值上限
    current_decision INTEGER NOT NULL DEFAULT 100,  -- 当前决策值
    -- 手牌（存为 JSON 数组，元素为 card_id）
    hand_cards      JSONB DEFAULT '[]'::jsonb,
    -- 牌库（存为 JSON 数组，元素为 card_id；决策牌牌库）
    deck_cards      JSONB DEFAULT '[]'::jsonb,
    -- 弹药库存（存为 JSON 对象，{card_id: quantity}）
    ammo_inventory  JSONB DEFAULT '{}'::jsonb,
    -- 临时状态
    attack_buff     INTEGER DEFAULT 0,              -- 本回合攻击力加成（如热成像效果）
    damage_reduction INTEGER DEFAULT 0,             -- 本回合减伤效果（如烟雾弹）
    ignore_defense  INTEGER DEFAULT 0,              -- 1=本回合无视对方防御
    defense_buff    INTEGER DEFAULT 0,              -- 临时防御加成（反应装甲效果）
    module_damage_multiplier DOUBLE PRECISION DEFAULT 1.0,  -- 模块损坏概率倍率（热成像效果）
    -- 模块损坏状态
    main_gun_status     INTEGER DEFAULT 0,          -- 0=正常 1=主炮完全损毁 2=主炮轻微损坏
    main_gun_timer      INTEGER DEFAULT 0,          -- 主炮损坏剩余回合数
    turret_drive_status INTEGER DEFAULT 0,          -- 0=正常 1=方向机损坏
    turret_drive_timer  INTEGER DEFAULT 0,          -- 方向机损坏剩余回合数
    engine_status       INTEGER DEFAULT 0,          -- 0=正常 1=发动机轻微损毁 2=发动机完全损毁
    engine_timer        INTEGER DEFAULT 0,          -- 发动机损坏剩余回合数
    engine_saved_max_decision INTEGER DEFAULT 0,   -- 发动机损坏前的决策上限（用于恢复）
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (game_id, player_id)
);

-- =============================================================
-- 5. 对局日志表
-- =============================================================
CREATE TABLE IF NOT EXISTS game_logs (
    id              SERIAL PRIMARY KEY,
    game_id         INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    player_id       INTEGER NOT NULL REFERENCES users(id),
    action_type     VARCHAR(50) NOT NULL,           -- 'play_card', 'end_turn', 'game_over'
    card_id         INTEGER DEFAULT NULL REFERENCES cards(id),
    description     VARCHAR(500) DEFAULT '',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================
-- 6. 索引
-- =============================================================
CREATE INDEX idx_games_status ON games(status);
CREATE INDEX idx_games_player1 ON games(player1_id);
CREATE INDEX idx_games_player2 ON games(player2_id);
CREATE INDEX idx_game_states_game ON game_states(game_id);
CREATE INDEX idx_game_logs_game ON game_logs(game_id);

-- =============================================================
-- =============================================================
-- 种子数据：示例用户（测试用）
-- =============================================================
-- 密码都是 "test123"，使用简单哈希便于测试
INSERT INTO users (username, password_hash) VALUES
    ('Player1', 'pbkdf2:sha256:600000$test_salt_1$dummy_hash_placeholder'),
    ('Player2', 'pbkdf2:sha256:600000$test_salt_2$dummy_hash_placeholder'),
    ('AI_Bot',  'pbkdf2:sha256:600000$test_salt_3$dummy_hash_placeholder')
ON CONFLICT (username) DO NOTHING;

-- =============================================================
-- 种子数据：炮弹牌
-- =============================================================
-- effect_data 说明：
--   {"attack_min": N, "attack_max": M}       → 攻击力在 N~M 间随机取值
--   {"module_damage_multiplier": X}           → 模块损坏概率乘以 X
--   {"two_hit": true, "first_attack_min": A, "first_attack_max": B,
--     "first_module_multiplier": C, "second_attack": D} → 两次伤害
INSERT INTO cards (card_name, card_type, decision_cost, attack_bonus, effect_description, effect_data, exclusive_vehicle) VALUES
    -- M1 Abrams 专属炮弹
    ('M829A2 穿甲弹',     'ammo', 4,  13, 'M1 Abrams 专属 APFSDS 穿甲弹，高穿透力', NULL, 'M1_Abrams'),
    ('M830A1 多用途高爆弹', 'ammo', 4,  3,  'M1 Abrams 专用高爆弹，造成伤害时模块损坏概率+100%', '{"module_damage_multiplier": 2.0}', 'M1_Abrams'),
    ('M908 高爆弹',        'ammo', 3,  0,  'M1 Abrams 专用高爆弹，攻击力 3-11 随机', '{"attack_min": 3, "attack_max": 11}', 'M1_Abrams'),

    -- T-90M 专属炮弹
    ('3BM60 穿甲弹',      'ammo', 6,  10, 'T-90M 专属 APFSDS 穿甲弹，高攻击力', NULL, 'T90M'),
    ('3OF26 高爆弹',      'ammo', 5,  0,  'T-90M 专用高爆弹，攻击力 3-11 随机', '{"attack_min": 3, "attack_max": 11}', 'T90M'),
    ('9M119M 炮射导弹',   'ammo', 8,  0,  'T-90M 专用炮射导弹，两次伤害：第一次2-7随机（模块概率-50%），第二次固定11', '{"two_hit": true, "first_attack_min": 2, "first_attack_max": 7, "first_module_multiplier": 0.5, "second_attack": 11}', 'T90M'),

    -- 勒克莱尔 专属炮弹
    ('OFL 120 F1穿甲弹',  'ammo', 4,  11, '勒克莱尔专属 APFSDS 穿甲弹，高穿透力', NULL, 'Leclerc'),
    ('F1高爆弹',          'ammo', 4,  0,  '勒克莱尔专用高爆弹，攻击力2-8随机，模块损坏概率+100%', '{"attack_min": 2, "attack_max": 8, "module_damage_multiplier": 2.0}', 'Leclerc'),
    ('OCC 120 G1破甲弹',  'ammo', 4,  0,  '勒克莱尔专用破甲弹，攻击力5-11随机，模块损坏概率+40%', '{"attack_min": 5, "attack_max": 11, "module_damage_multiplier": 1.4}', 'Leclerc')
ON CONFLICT DO NOTHING;

-- =============================================================
-- 种子数据：决策牌（类似锦囊牌）
-- =============================================================
INSERT INTO cards (card_name, card_type, decision_cost, attack_bonus, effect_description, effect_data, exclusive_vehicle) VALUES
    ('烟雾弹',   'decision', 2, 0, '70%概率使敌方该回合内的攻击无法造成伤害', NULL, NULL),
    ('热成像',   'decision', 2, 0, '该回合内对敌方造成伤害时模块损坏概率变为150%', NULL, NULL),
    ('紧急维修', 'decision', 2, 0, '恢复5点生命值，移除全部模块损坏状态', NULL, NULL),
    ('反应装甲', 'decision', 3, 0, '下一回合提升5点防御值', NULL, NULL)
ON CONFLICT DO NOTHING;