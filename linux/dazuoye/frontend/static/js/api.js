/**
 * API 客户端层 - 封装所有后端接口调用
 * 使用相对路径，由 nginx 代理到后端，避免 CORS 问题
 */
const API_BASE = '';

const Api = {
    /**
     * 登录
     */
    async login(username, password) {
        const res = await fetch(`${API_BASE}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: '登录失败' }));
            throw new Error(err.detail || '登录失败');
        }
        return res.json();
    },

    /**
     * 获取用户列表
     */
    async getUsers() {
        const res = await fetch(`${API_BASE}/api/auth/users`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: '获取用户列表失败' }));
            throw new Error(err.detail || '获取用户列表失败');
        }
        return res.json();
    },

    /**
     * 获取可用载具
     */
    async getVehicles() {
        const res = await fetch(`${API_BASE}/api/game/vehicles`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: '获取载具失败' }));
            throw new Error(err.detail || '获取载具失败');
        }
        return res.json();
    },

    /**
     * 获取某载具可用的弹药牌
     */
    async getAmmoCards(vehicleType) {
        const res = await fetch(`${API_BASE}/api/game/ammo-cards/${vehicleType}`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: '获取弹药牌失败' }));
            throw new Error(err.detail || '获取弹药牌失败');
        }
        return res.json();
    },

    /**
     * 创建对局
     */
    async createGame(player1Id, player1Vehicle, player1Ammo = null) {
        const body = { player1_id: player1Id, player1_vehicle: player1Vehicle };
        if (player1Ammo) body.player1_ammo = player1Ammo;
        const res = await fetch(`${API_BASE}/api/game/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: '创建对局失败' }));
            throw new Error(err.detail || '创建对局失败');
        }
        return res.json();
    },

    /**
     * 加入对局
     */
    async joinGame(gameId, player2Id, player2Vehicle, player2Ammo = null) {
        const body = { game_id: gameId, player2_id: player2Id, player2_vehicle: player2Vehicle };
        if (player2Ammo) body.player2_ammo = player2Ammo;
        const res = await fetch(`${API_BASE}/api/game/join`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: '加入对局失败' }));
            throw new Error(err.detail || '加入对局失败');
        }
        return res.json();
    },

    /**
     * 出牌
     */
    async playCard(gameId, playerId, cardId) {
        const res = await fetch(`${API_BASE}/api/game/play`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ game_id: gameId, player_id: playerId, card_id: cardId }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: '出牌失败' }));
            throw new Error(err.detail || '出牌失败');
        }
        return res.json();
    },

    /**
     * 结束回合
     */
    async endTurn(gameId, playerId) {
        const res = await fetch(`${API_BASE}/api/game/end-turn?game_id=${gameId}&player_id=${playerId}`, {
            method: 'POST',
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: '结束回合失败' }));
            throw new Error(err.detail || '结束回合失败');
        }
        return res.json();
    },

    /**
     * 获取游戏状态
     */
    async getGameState(gameId, playerId) {
        const res = await fetch(`${API_BASE}/api/game/state/${gameId}/${playerId}`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: '获取状态失败' }));
            throw new Error(err.detail || '获取状态失败');
        }
        return res.json();
    },

    /**
     * MCP 决策推荐
     */
    async getMcpAdvice(gameId, playerId) {
        const res = await fetch(`${API_BASE}/mcp/recommend`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ game_id: gameId, player_id: playerId }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: '获取建议失败' }));
            throw new Error(err.detail || '获取建议失败');
        }
        return res.json();
    },

    // =============================================================
    // AI 对战接口
    // =============================================================

    /**
     * 创建与 AI 的对局
     */
    async startAiGame(playerId, playerVehicle, aiVehicle = 'T90M', playerAmmo = null) {
        const url = `${API_BASE}/api/game/create-ai?player_id=${playerId}&player_vehicle=${playerVehicle}&ai_vehicle=${aiVehicle}`;
        const body = playerAmmo ? JSON.stringify(playerAmmo) : '{}';
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: body,
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: '创建 AI 对局失败' }));
            throw new Error(err.detail || '创建 AI 对局失败');
        }
        return res.json();
    },

    /**
     * 触发 AI 回合
     */
    async triggerAiMove(gameId) {
        const res = await fetch(
            `${API_BASE}/api/game/ai-move?game_id=${gameId}`,
            { method: 'POST' }
        );
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'AI 行动失败' }));
            throw new Error(err.detail || 'AI 行动失败');
        }
        return res.json();
    },
};