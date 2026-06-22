/**
 * 主游戏应用逻辑
 * 管理：大厅 → 弹药选择 → 游戏 → 结束 全流程
 * 支持：热座双人对战 + AI 对战
 */
const App = {
    // ---------- 状态 ----------
    users: [],
    vehicles: [],
    ammoCards: [],        // 当前载具可用弹药牌
    ammoSelection: {},    // {cardId: quantity}
    player1: null,
    player2: null,
    p1Vehicle: null,
    p2Vehicle: null,
    gameId: null,
    gameState: null,
    currentPlayerId: null,
    pollTimer: null,
    isMyTurn: false,
    gameOver: false,
    isAiMode: false,
    aiThinking: false,
    aiBotUserId: 3,

    // ---------- 初始化 ----------
    async init() {
        await this.loadUsers();
        await this.loadVehicles();
        this.setupEventListeners();
    },

    async loadUsers() {
        try {
            this.users = await Api.getUsers();
            const s1 = document.getElementById('player1-select');
            const s2 = document.getElementById('player2-select');
            s1.innerHTML = '';
            s2.innerHTML = '';
            this.users.forEach(u => {
                s1.innerHTML += `<option value="${u.id}">${u.username}</option>`;
                s2.innerHTML += `<option value="${u.id}">${u.username}</option>`;
            });
        } catch (e) {
            console.error('加载用户失败:', e);
            document.getElementById('login-error').textContent = '加载用户失败：' + e.message;
            document.getElementById('login-error').style.color = '#e74c3c';
        }
    },

    async loadVehicles() {
        try {
            this.vehicles = await Api.getVehicles();
            const container = document.getElementById('vehicle-list');
            container.innerHTML = '';
            this.vehicles.forEach((v, i) => {
                const card = document.createElement('div');
                card.className = `vehicle-card ${i === 0 ? 'selected' : ''}`;
                card.dataset.vehicleId = v.id;
                card.innerHTML = `
                    <h4>${v.name}</h4>
                    <div class="stat-row"><span>血量</span><span>${v.max_health}</span></div>
                    <div class="stat-row"><span>防御</span><span>${v.defense}</span></div>
                    <div class="stat-row"><span>决策上限</span><span>${v.max_decision}</span></div>
                    <div class="stat-row"><span>载弹量</span><span>${v.min_ammo}-${v.max_ammo}</span></div>
                    <div style="font-size:0.75rem;color:#888;margin-top:6px;">${v.description}</div>
                `;
                card.addEventListener('click', () => this.selectVehicle(card, v));
                container.appendChild(card);
            });
            this.p1Vehicle = this.vehicles[0].id;
            this.p2Vehicle = this.vehicles.length > 1 ? this.vehicles[1].id : this.vehicles[0].id;
            await this.loadAmmoCards(this.p1Vehicle);
        } catch (e) {
            console.error('加载载具失败:', e);
            const list = document.getElementById('vehicle-list');
            if (list) list.innerHTML =
                `<div class="error-msg">加载载具失败：${e.message}。请检查后端是否正常运行。</div>`;
        }
    },

    async selectVehicle(card, vehicle) {
        document.querySelectorAll('.vehicle-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
        this.p1Vehicle = vehicle.id;
        this.p2Vehicle = this.vehicles.find(v => v.id !== this.p1Vehicle)?.id || this.vehicles[0].id;
        await this.loadAmmoCards(this.p1Vehicle);
    },

    // ---------- 弹药选择 ----------
    async loadAmmoCards(vehicleType) {
        try {
            this.ammoCards = await Api.getAmmoCards(vehicleType);
            this.ammoSelection = {};
            this.ammoCards.forEach(c => { this.ammoSelection[c.id] = 0; });
            this.renderAmmoSelectors();
        } catch (e) {
            console.error('加载弹药牌失败:', e);
            const panel = document.getElementById('ammo-select-panel');
            if (panel) {
                panel.style.display = 'block';
                const list = document.getElementById('ammo-select-list');
                if (list) list.innerHTML =
                    `<div class="error-msg">加载弹药牌失败：${e.message}。请检查后端是否正常运行。</div>`;
                const warning = document.getElementById('ammo-warning');
                if (warning) warning.textContent = '弹药数据加载失败，无法配置弹药';
            }
        }
    },

    renderAmmoSelectors() {
        const panel = document.getElementById('ammo-select-panel');
        if (!panel) { console.warn('ammo-select-panel 元素未找到，跳过渲染'); return; }
        const list = document.getElementById('ammo-select-list');
        const vehicle = this.vehicles.find(v => v.id === this.p1Vehicle);

        if (!vehicle || this.ammoCards.length === 0) {
            panel.style.display = 'none';
            return;
        }
        panel.style.display = 'block';

        document.getElementById('ammo-min').textContent = vehicle.min_ammo;
        document.getElementById('ammo-max').textContent = vehicle.max_ammo;

        list.innerHTML = '';
        this.ammoCards.forEach(c => {
            const row = document.createElement('div');
            row.className = 'ammo-select-row';
            const exclusive = c.exclusive_vehicle ? ' [专属]' : ' [通用]';
            const atkDisplay = App.formatAttack(c);
            row.innerHTML = `
                <div class="ammo-select-info">
                    <span class="ammo-select-name">${c.card_name}${exclusive}</span>
                    <span class="ammo-select-stat">攻击 ${atkDisplay} | 消耗 ${c.decision_cost}</span>
                </div>
                <div class="ammo-select-slider">
                    <input type="range" min="0" max="${vehicle.max_ammo}" value="${this.ammoSelection[c.id] || 0}"
                           data-card-id="${c.id}" class="ammo-slider">
                    <span class="ammo-qty" id="ammo-qty-${c.id}">${this.ammoSelection[c.id] || 0}</span>
                </div>
            `;
            list.appendChild(row);
        });

        // 绑定滑块事件
        list.querySelectorAll('.ammo-slider').forEach(slider => {
            slider.addEventListener('input', () => this.onAmmoSliderChange(slider));
        });

        this.updateAmmoTotal();
    },

    onAmmoSliderChange(slider) {
        const cardId = parseInt(slider.dataset.cardId);
        const val = parseInt(slider.value);
        this.ammoSelection[cardId] = val;
        document.getElementById(`ammo-qty-${cardId}`).textContent = val;
        this.updateAmmoTotal();
    },

    updateAmmoTotal() {
        const total = Object.values(this.ammoSelection).reduce((a, b) => a + b, 0);
        document.getElementById('ammo-total').textContent = total;

        const vehicle = this.vehicles.find(v => v.id === this.p1Vehicle);
        const warning = document.getElementById('ammo-warning');
        if (vehicle) {
            if (total < vehicle.min_ammo) {
                warning.textContent = `至少需要 ${vehicle.min_ammo} 发弹药`;
            } else if (total > vehicle.max_ammo) {
                warning.textContent = `最多 ${vehicle.max_ammo} 发弹药`;
            } else {
                warning.textContent = '';
            }
        }
    },

    getAmmoPayload() {
        const payload = {};
        for (const [k, v] of Object.entries(this.ammoSelection)) {
            if (v > 0) payload[k] = v;
        }
        return Object.keys(payload).length > 0 ? payload : null;
    },

    validateAmmo() {
        const vehicle = this.vehicles.find(v => v.id === this.p1Vehicle);
        if (!vehicle) return false;
        const total = Object.values(this.ammoSelection).reduce((a, b) => a + b, 0);
        return total >= vehicle.min_ammo && total <= vehicle.max_ammo;
    },

    // ---------- 事件绑定 ----------
    setupEventListeners() {
        document.getElementById('login-btn').addEventListener('click', () => this.handleLogin());
        document.getElementById('create-game-btn').addEventListener('click', () => this.handleCreateGame());
        document.getElementById('create-ai-btn').addEventListener('click', () => this.handleCreateGameAI());
        document.getElementById('end-turn-btn').addEventListener('click', () => this.handleEndTurn());
        document.getElementById('mcp-advice-btn').addEventListener('click', () => this.handleMcpAdvice());
        document.getElementById('restart-btn').addEventListener('click', () => this.handleRestart());
    },

    // ---------- 登录 ----------
    async handleLogin() {
        const p1Select = document.getElementById('player1-select');
        const pw1 = document.getElementById('password1').value;
        const errEl = document.getElementById('login-error');

        try {
            const r1 = await Api.login(p1Select.options[p1Select.selectedIndex].text, pw1);
            this.player1 = r1;
            errEl.textContent = `已登录：${r1.username}`;
            errEl.style.color = '#2ecc71';
            document.getElementById('create-game-btn').disabled = false;
            document.getElementById('create-ai-btn').disabled = false;
        } catch (e) {
            errEl.textContent = e.message;
        }
    },

    // ---------- 创建玩家对局 ----------
    async handleCreateGame() {
        if (!this.player1) return;
        if (!this.validateAmmo()) {
            document.getElementById('game-info').textContent = '请先配置弹药（数量需在载弹量范围内）';
            return;
        }

        const p2Select = document.getElementById('player2-select');
        const pw2 = document.getElementById('password2').value;
        const infoEl = document.getElementById('game-info');

        try {
            const r2 = await Api.login(p2Select.options[p2Select.selectedIndex].text, pw2);
            this.player2 = r2;
        } catch (e) {
            infoEl.textContent = '请先登录玩家 2: ' + e.message;
            return;
        }

        const ammoP1 = this.getAmmoPayload();
        // 玩家2：同载具则用同样弹药，不同载具则用默认（避免专属弹药冲突）
        const ammoP2 = (this.p2Vehicle === this.p1Vehicle) ? ammoP1 : null;

        try {
            const createRes = await Api.createGame(this.player1.user_id, this.p1Vehicle, ammoP1);
            infoEl.textContent = `对局已创建 (ID: ${createRes.game_id})，正在加入...`;

            const joinRes = await Api.joinGame(createRes.game_id, this.player2.user_id, this.p2Vehicle, ammoP2);
            infoEl.textContent = `对局已开始！(ID: ${createRes.game_id})`;

            this.isAiMode = false;
            this.gameId = createRes.game_id;
            this.startGame();
        } catch (e) {
            infoEl.textContent = e.message;
        }
    },

    // ---------- 创建 AI 对局 ----------
    async handleCreateGameAI() {
        if (!this.player1) {
            document.getElementById('game-info').textContent = '请先登录！';
            return;
        }
        if (!this.validateAmmo()) {
            document.getElementById('game-info').textContent = '请先配置弹药（数量需在载弹量范围内）';
            return;
        }

        this.p2Vehicle = this.vehicles.find(v => v.id !== this.p1Vehicle)?.id || this.vehicles[0].id;
        const ammoP1 = this.getAmmoPayload();

        const infoEl = document.getElementById('game-info');
        try {
            const res = await Api.startAiGame(this.player1.user_id, this.p1Vehicle, this.p2Vehicle, ammoP1);
            infoEl.textContent = `AI 对战已开始！(ID: ${res.game_id})`;

            this.isAiMode = true;
            this.player2 = { user_id: this.aiBotUserId, username: 'AI Bot' };
            this.gameId = res.game_id;
            this.startGame();
        } catch (e) {
            infoEl.textContent = e.message;
        }
    },

    // ---------- 开始游戏 ----------
    async startGame() {
        document.getElementById('lobby-screen').classList.remove('active');
        document.getElementById('game-screen').classList.add('active');

        this.gameOver = false;
        this.currentPlayerId = this.player1.user_id;
        this.isMyTurn = true;

        await this.refreshState();
        this.startPolling();
    },

    // ---------- 状态轮询 ----------
    startPolling() {
        this.stopPolling();
        this.pollTimer = setInterval(() => this.pollState(), 2000);
    },

    stopPolling() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
    },

    async pollState() {
        if (this.gameOver) return;
        try {
            const state = await Api.getGameState(this.gameId, this.currentPlayerId);
            this.gameState = state;
            this.renderState(state);

            if (this.isAiMode && !this.gameOver && !this.aiThinking) {
                const isAiTurn = state.current_turn_player_id === this.aiBotUserId;
                if (isAiTurn) {
                    await this.triggerAiTurn();
                }
            }
        } catch (e) {
            console.error('轮询状态失败:', e);
        }
    },

    async refreshState() {
        try {
            const state = await Api.getGameState(this.gameId, this.currentPlayerId);
            this.gameState = state;
            this.renderState(state);
        } catch (e) {
            console.error('刷新状态失败:', e);
        }
    },

    // ---------- AI 回合 ----------
    async triggerAiTurn() {
        this.aiThinking = true;
        this.isMyTurn = false;
        this.updateTurnIndicator();
        this.showToast('AI 正在思考...');

        try {
            const res = await Api.triggerAiMove(this.gameId);
            this.aiThinking = false;
            await this.refreshState();

            if (res.game_state && res.game_state.status === 'finished') {
                this.handleGameOver(res.game_state);
            }
        } catch (e) {
            this.aiThinking = false;
            console.error('AI 回合失败:', e);
            await this.refreshState();
        }
    },

    // ---------- 渲染 ----------
    renderState(state) {
        this.gameState = state;
        const me = state.player1;
        const opponent = state.player2;

        // 对方信息
        document.getElementById('opponent-name').textContent = opponent.username;
        document.getElementById('opponent-vehicle').textContent = this.getVehicleName(opponent.vehicle_type);
        this.updateBar('opponent-hp', opponent.current_health, opponent.max_health);
        document.getElementById('opponent-hp-text').textContent = `${opponent.current_health}/${opponent.max_health}`;
        document.getElementById('opponent-defense').textContent = opponent.defense;
        this.updateBar('opponent-decision', opponent.current_decision, opponent.max_decision);
        document.getElementById('opponent-decision-text').textContent = `${opponent.current_decision}/${opponent.max_decision}`;

        // 己方信息
        document.getElementById('player-name').textContent = me.username;
        document.getElementById('player-vehicle').textContent = this.getVehicleName(me.vehicle_type);
        this.updateBar('player-hp', me.current_health, me.max_health);
        document.getElementById('player-hp-text').textContent = `${me.current_health}/${me.max_health}`;
        document.getElementById('player-defense').textContent = me.defense;
        this.updateBar('player-decision', me.current_decision, me.max_decision);
        document.getElementById('player-decision-text').textContent = `${me.current_decision}/${me.max_decision}`;

        // 回合指示
        this.isMyTurn = (state.current_turn_player_id === this.currentPlayerId);
        this.updateTurnIndicator();

        // 按钮
        const canAct = this.isMyTurn && !this.gameOver && !this.aiThinking;
        document.getElementById('end-turn-btn').disabled = !canAct;
        document.getElementById('mcp-advice-btn').disabled = !canAct;

        // Buff / 模块 / 弹药 / 手牌 / 日志
        this.renderBuffs(me);
        this.renderModuleStatus(document.getElementById('opponent-area'), opponent);
        this.renderModuleStatus(document.getElementById('player-area'), me);
        this.renderAmmoInventory(me.ammo_inventory, me.current_decision);
        this.renderHandCards(me.hand_cards, me.current_decision);
        this.renderLogs(state.logs);

        if (state.status === 'finished') {
            this.handleGameOver(state);
        }
    },

    updateTurnIndicator() {
        const turnEl = document.getElementById('turn-indicator');
        if (this.aiThinking) {
            turnEl.textContent = 'AI 思考中...';
            turnEl.className = 'turn-indicator inactive';
        } else if (this.isMyTurn) {
            turnEl.textContent = '你的回合';
            turnEl.className = 'turn-indicator active';
        } else {
            turnEl.textContent = this.isAiMode ? '等待 AI 行动...' : '等待对手...';
            turnEl.className = 'turn-indicator inactive';
        }
    },

    updateBar(prefix, current, max) {
        const pct = max > 0 ? Math.max(0, (current / max) * 100) : 0;
        document.getElementById(`${prefix}-fill`).style.width = `${pct}%`;
    },

    getVehicleName(type) {
        const v = this.vehicles.find(v => v.id === type);
        return v ? v.name : type;
    },

    renderBuffs(me) {
        const bar = document.getElementById('buff-bar');
        bar.innerHTML = '';
        if (me.attack_buff > 0) {
            bar.innerHTML += `<span class="buff-tag">攻击加成 +${me.attack_buff}</span>`;
        }
        if (me.damage_reduction > 0) {
            bar.innerHTML += `<span class="buff-tag">烟雾防护</span>`;
        }
    },

    renderModuleStatus(container, player) {
        const oldStatus = container.querySelector('.module-status');
        if (oldStatus) oldStatus.remove();

        if (!player.modules) return;
        const m = player.modules;
        const parts = [];
        if (m.main_gun.status === 1) parts.push(`主炮损毁(${m.main_gun.timer}回合)`);
        else if (m.main_gun.status === 2) parts.push(`主炮不稳(${m.main_gun.timer}回合)`);
        if (m.turret_drive.status === 1) parts.push(`方向机损坏(${m.turret_drive.timer}回合)`);
        if (m.engine.status === 1) parts.push(`发动机轻微损毁(${m.engine.timer}回合)`);
        else if (m.engine.status === 2) parts.push(`发动机完全损毁(${m.engine.timer}回合)`);

        if (parts.length > 0) {
            const div = document.createElement('div');
            div.className = 'module-status';
            div.style.cssText = 'margin-top:6px;display:flex;gap:6px;flex-wrap:wrap;';
            parts.forEach(p => {
                div.innerHTML += `<span class="buff-tag" style="background:rgba(231,76,60,0.15);border-color:#e74c3c;color:#e74c3c;">${p}</span>`;
            });
            container.appendChild(div);
        }
    },

    // ---------- 弹药库存渲染 ----------
    renderAmmoInventory(ammoItems, currentDecision) {
        const container = document.getElementById('ammo-cards');
        container.innerHTML = '';

        if (!ammoItems || ammoItems.length === 0) {
            container.innerHTML = '<div style="color:#888;padding:8px;">弹药已耗尽</div>';
            return;
        }

        ammoItems.forEach(item => {
            const canPlay = this.isMyTurn && !this.gameOver && !this.aiThinking && currentDecision >= item.decision_cost && item.quantity > 0;
            const atkDisplay = App.formatAttack(item);
            const el = document.createElement('div');
            el.className = `ammo-card ${canPlay ? '' : 'disabled'}`;
            el.dataset.cardId = item.id;

            el.innerHTML = `
                <div class="ammo-card-name">${item.card_name}</div>
                <div class="ammo-card-stats">
                    <span>攻击 ${atkDisplay}</span>
                    <span>消耗 ${item.decision_cost}</span>
                    <span class="ammo-card-qty">x${item.quantity}</span>
                </div>
            `;

            if (canPlay) {
                el.addEventListener('click', () => this.handlePlayCard(item.id));
            }

            container.appendChild(el);
        });
    },

    renderHandCards(cards, currentDecision) {
        const container = document.getElementById('hand-cards');
        container.innerHTML = '';

        if (!cards || cards.length === 0) {
            container.innerHTML = '<div style="color:#888;padding:20px;">决策牌为空</div>';
            return;
        }

        cards.forEach(card => {
            const canPlay = this.isMyTurn && !this.gameOver && !this.aiThinking && currentDecision >= card.decision_cost;
            const el = document.createElement('div');
            el.className = `game-card decision ${canPlay ? '' : 'disabled'}`;
            el.dataset.cardId = card.id;

            el.innerHTML = `
                <div class="card-type-badge">决策</div>
                <div class="card-name">${card.card_name}</div>
                <div class="card-cost">决策值: ${card.decision_cost}</div>
                <div class="card-desc">${card.effect_description || ''}</div>
            `;

            if (canPlay) {
                el.addEventListener('click', () => this.handlePlayCard(card.id));
            }

            container.appendChild(el);
        });
    },

    renderLogs(logs) {
        const container = document.getElementById('log-entries');
        container.innerHTML = '';
        if (!logs || logs.length === 0) {
            container.innerHTML = '<div class="log-entry">等待对战开始...</div>';
            return;
        }
        logs.forEach(log => {
            const isSelf = log.player_id === this.currentPlayerId;
            const isAi = this.isAiMode && log.player_id === this.aiBotUserId;
            const el = document.createElement('div');
            el.className = `log-entry ${isSelf ? 'self' : 'opponent'}`;
            const prefix = isSelf ? '你' : (isAi ? 'AI' : '对手');
            el.textContent = `${prefix}: ${log.description}`;
            container.appendChild(el);
        });
        document.getElementById('battle-log').scrollTop = container.scrollHeight;
    },

    // ---------- 操作处理 ----------
    async handlePlayCard(cardId) {
        if (!this.isMyTurn || this.gameOver || this.aiThinking) return;
        try {
            const res = await Api.playCard(this.gameId, this.currentPlayerId, cardId);
            this.showToast(res.message);
            await this.refreshState();
        } catch (e) {
            this.showToast('' + e.message, true);
        }
    },

    async handleEndTurn() {
        if (!this.isMyTurn || this.gameOver || this.aiThinking) return;
        try {
            const res = await Api.endTurn(this.gameId, this.currentPlayerId);
            this.showToast('回合结束');
            this.isMyTurn = false;
            await this.refreshState();

            if (this.isAiMode && !this.gameOver) {
                setTimeout(() => this.triggerAiTurn(), 500);
            }
        } catch (e) {
            this.showToast('' + e.message, true);
        }
    },

    async handleMcpAdvice() {
        if (this.gameOver || this.aiThinking) return;
        try {
            const advice = await Api.getMcpAdvice(this.gameId, this.currentPlayerId);
            const msg = `AI 建议: ${advice.recommended_card_name || '结束回合'} - ${advice.reason} (置信度: ${Math.round(advice.confidence * 100)}%)`;
            this.showToast(msg);
        } catch (e) {
            this.showToast('' + e.message, true);
        }
    },

    handleGameOver(state) {
        this.gameOver = true;
        this.stopPolling();

        const winnerName = state.winner_id === this.currentPlayerId ? '你' : (this.isAiMode ? 'AI' : '对手');
        const isWin = state.winner_id === this.currentPlayerId;

        const banner = document.createElement('div');
        banner.className = 'game-over-banner';
        banner.id = 'game-over-banner';
        banner.innerHTML = `
            <h1>${isWin ? '胜利！' : '战败'}</h1>
            <p>${winnerName} 获得了这场对决的胜利！</p>
            <button class="btn btn-primary" onclick="App.handleRestart()">重新开始</button>
        `;
        document.body.appendChild(banner);
        document.getElementById('restart-btn').style.display = 'inline-block';
    },

    handleRestart() {
        this.stopPolling();
        this.gameOver = false;
        this.gameId = null;
        this.gameState = null;
        this.isAiMode = false;
        this.aiThinking = false;

        const banner = document.getElementById('game-over-banner');
        if (banner) banner.remove();

        document.getElementById('restart-btn').style.display = 'none';
        document.getElementById('game-screen').classList.remove('active');
        document.getElementById('lobby-screen').classList.add('active');

        document.getElementById('game-info').textContent = '';
        document.getElementById('create-game-btn').disabled = false;
        document.getElementById('create-ai-btn').disabled = false;
    },

    // ---------- 工具 ----------
    formatAttack(card) {
        const ed = card.effect_data;
        if (ed) {
            if (ed.two_hit) {
                return `${ed.first_attack_min}-${ed.first_attack_max} + ${ed.second_attack}`;
            }
            if (ed.attack_min !== undefined && ed.attack_max !== undefined) {
                return `${ed.attack_min}-${ed.attack_max}`;
            }
        }
        return card.attack_bonus;
    },

    showToast(msg, isError = false) {
        const toast = document.getElementById('toast');
        toast.textContent = msg;
        toast.style.borderColor = isError ? '#e74c3c' : '#d4a843';
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 3500);
    },
};

// ---------- 启动 ----------
document.addEventListener('DOMContentLoaded', () => App.init());