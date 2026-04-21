// Handles interactions with the Arena battle UI and leaderboard

let arenaSelectedModels = [];
let arenaAvailableModels = [];
let _arenaInitialized = false;

function switchChatArenaMode(mode) {
    // Update dropdown items
    document.querySelectorAll('.tab-dropdown-item').forEach(item => {
        item.classList.toggle('active', item.dataset.subtab === mode);
    });

    // Update dropdown button label
    const btn = document.querySelector('.main-tab-dropdown .main-tab');
    if (btn) {
        const icons = { chat: '💬', agent: '🤖', arena: '⚔️', aiconv: '🎭' };
        const labels = { chat: 'Chat', agent: 'Agent', arena: 'Arena', aiconv: 'AI Conv' };
        btn.innerHTML = `<span class="tab-icon">${icons[mode] || '💬'}</span>${labels[mode] || 'Chat'} <span class="dropdown-arrow">▾</span>`;
    }

    // Switch panel
    if (typeof switchMainTab === 'function') switchMainTab(mode);

    // Re-render thread list to filter by mode
    if (typeof renderThreadList === 'function') {
        renderThreadList();

        // Auto-select first visible thread if current is no longer visible
        if (mode === 'chat' || mode === 'agent') {
            const visibleThreads = document.querySelectorAll('.thread-item');
            const currentThreadId = window.currentThreadId;
            const currentVisible = document.querySelector(`.thread-item[data-thread-id="${currentThreadId}"]`);
            if (!currentVisible && visibleThreads.length > 0) {
                const firstId = visibleThreads[0].dataset.threadId;
                if (typeof switchThread === 'function') switchThread(firstId);
            } else if (visibleThreads.length === 0) {
                // No threads for this mode — clear chat
                window.currentThreadId = null;
                if (typeof toggleChatInput === 'function') toggleChatInput(false);
                const chatMessages = document.getElementById('chat-messages');
                if (chatMessages) chatMessages.innerHTML = '';
                const activeThreadTitle = document.getElementById('active-thread-title');
                if (activeThreadTitle) activeThreadTitle.textContent = 'No threads';
            }
        }
    }
}

function initializeArena() {
    if (_arenaInitialized) return;
    _arenaInitialized = true;

    // ── Battle ───────────────────────────────────────────────────────────────
    const sendBtn = document.getElementById('arena-send');
    if (sendBtn) sendBtn.addEventListener('click', sendArenaPrompt);

    const input = document.getElementById('arena-input');
    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendArenaPrompt(); }
        });
        input.addEventListener('input', function () {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
            if (this.value === '') this.style.height = '';
        });
    }

    // Battle model-add dropdown
    const battleAdd = document.getElementById('arena-model-add');
    if (battleAdd) {
        battleAdd.addEventListener('change', () => {
            const v = battleAdd.value;
            if (v && !arenaSelectedModels.includes(v)) {
                arenaSelectedModels.push(v);
                renderArenaChips();
            }
            battleAdd.value = '';
        });
    }

    // Battle evaluator — persist selection
    const battleEval = document.getElementById('arena-evaluator');
    if (battleEval) {
        battleEval.addEventListener('change', () => {
            localStorage.setItem('arena_battle_evaluator', battleEval.value);
        });
    }

    // Gauntlet evaluator — persist selection
    const gauntletEvalSel = document.getElementById('gauntlet-evaluator');
    if (gauntletEvalSel) {
        gauntletEvalSel.addEventListener('change', () => {
            localStorage.setItem('arena_gauntlet_evaluator', gauntletEvalSel.value);
        });
    }

    // Clear leaderboard
    const clearBtn = document.getElementById('arena-clear-leaderboard');
    if (clearBtn) clearBtn.addEventListener('click', clearArenaLeaderboard);

    // ── Mode switcher ─────────────────────────────────────────────────────────
    document.querySelectorAll('.arena-mode-btn').forEach(btn => {
        btn.addEventListener('click', () => setArenaMode(btn.dataset.mode));
    });

    // ── Leaderboard tabs ──────────────────────────────────────────────────────
    document.querySelectorAll('.lb-tab').forEach(btn => {
        btn.addEventListener('click', () => setLbTab(btn.dataset.tab));
    });

    // ── Gauntlet ──────────────────────────────────────────────────────────────
    const gauntletAdd = document.getElementById('gauntlet-model-add');
    if (gauntletAdd) {
        gauntletAdd.addEventListener('change', () => {
            const v = gauntletAdd.value;
            if (v && !gauntletSelectedModels.includes(v)) {
                gauntletSelectedModels.push(v);
                renderGauntletChips();
            }
            gauntletAdd.value = '';
        });
    }

    const presetSel = document.getElementById('gauntlet-preset');
    if (presetSel) presetSel.addEventListener('change', () => updateGauntletPresetPreview(presetSel.value));

    const startBtn = document.getElementById('gauntlet-start');
    if (startBtn) startBtn.addEventListener('click', startGauntlet);
}

async function loadArenaModels() {
    try {
        const res = await fetch('/api/registry/models/chat');
        if (!res.ok) return;
        const data = await res.json();

        arenaAvailableModels = data.models || [];
        const chatOptions = generateCategorizedModelOptions(data, 'chat');

        // Battle dropdowns
        const addSelect = document.getElementById('arena-model-add');
        if (addSelect) addSelect.innerHTML = '<option value="">+ Add Model...</option>' + chatOptions;

        const evalSelect = document.getElementById('arena-evaluator');
        if (evalSelect) evalSelect.innerHTML = '<option value="">No Evaluator</option>' + chatOptions;

        // AI Conv dropdown
        const aiconvSelect = document.getElementById('aiconv-model-add');
        if (aiconvSelect) aiconvSelect.innerHTML = '<option value="">+ Add Model...</option>' + chatOptions;

        // Gauntlet dropdowns
        const gauntletAdd = document.getElementById('gauntlet-model-add');
        if (gauntletAdd) gauntletAdd.innerHTML = '<option value="">+ Add Model...</option>' + chatOptions;

        const gauntletEval = document.getElementById('gauntlet-evaluator');
        if (gauntletEval) gauntletEval.innerHTML = '<option value="">Select evaluator...</option>' + chatOptions;

        // ── Restore saved evaluator selections ───────────────────────────────
        const savedBattleEval = localStorage.getItem('arena_battle_evaluator');
        if (savedBattleEval && evalSelect) {
            // Only restore if the option actually exists in the populated list
            if ([...evalSelect.options].some(o => o.value === savedBattleEval)) {
                evalSelect.value = savedBattleEval;
            }
        }

        const savedGauntletEval = localStorage.getItem('arena_gauntlet_evaluator');
        if (savedGauntletEval && gauntletEval) {
            if ([...gauntletEval.options].some(o => o.value === savedGauntletEval)) {
                gauntletEval.value = savedGauntletEval;
            }
        }

    } catch (err) {
        console.error('Failed to load arena models:', err);
    }
}


function renderArenaChips() {
    const container = document.getElementById('arena-model-chips');
    if (!container) return;

    container.innerHTML = arenaSelectedModels.map(id => `
        <span class="arena-chip">
            ${id}
            <span class="chip-remove" onclick="removeArenaModel('${id}')">&times;</span>
        </span>
    `).join('');
}

function removeArenaModel(modelId) {
    arenaSelectedModels = arenaSelectedModels.filter(id => id !== modelId);
    renderArenaChips();
}

async function sendArenaPrompt() {
    const input = document.getElementById('arena-input');
    const prompt = input ? input.value.trim() : '';

    if (!prompt) return;
    if (arenaSelectedModels.length < 2) {
        showToast('Please add at least 2 models to the arena.', 'warn');
        return;
    }

    input.value = '';
    input.style.height = '';

    const evalSelect = document.getElementById('arena-evaluator');
    const evaluatorModelId = evalSelect ? evalSelect.value : '';

    const responsesDiv = document.getElementById('arena-responses');

    // Clear previous results
    responsesDiv.innerHTML = '';

    // Show loading grid and prompt bar
    const loadingHtml = `
        <div class="arena-prompt-bar" style="margin-bottom: 1rem; border-radius: 8px;"><strong>Prompt:</strong> ${escapeHtml(prompt)}</div>
        <div class="arena-cards-grid" id="current-battle-cards">
            ${arenaSelectedModels.map(id => `
                <div class="arena-response-card">
                    <div class="card-header"><span class="card-model">${id}</span></div>
                    <div class="card-body"><div class="arena-loading"><div class="spinner"></div> Generating...</div></div>
                </div>
            `).join('')}
        </div>
    `;

    responsesDiv.insertAdjacentHTML('beforeend', loadingHtml);
    responsesDiv.scrollTop = responsesDiv.scrollHeight;

    let battleData = {
        responses: [],
        trace_id: null,
        leaderboard: null
    };

    try {
        const res = await fetch('/api/arena/battle_stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompt: prompt,
                model_ids: arenaSelectedModels,
                evaluator_model_id: null
            })
        });

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Battle failed to start');
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            let lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer

            for (let line of lines) {
                if (line.startsWith('data: ')) {
                    const dataStr = line.substring(6).trim();
                    if (!dataStr) continue;

                    try {
                        const eventData = JSON.parse(dataStr);

                        if (eventData.type === 'start') {
                            battleData.trace_id = eventData.trace_id;
                        }
                        else if (eventData.type === 'result') {
                            const result = eventData.data;
                            battleData.responses.push(result);
                            renderSingleBattleResponse(result, evaluatorModelId === '', arenaSelectedModels);
                        }
                        else if (eventData.type === 'complete') {
                            battleData.leaderboard = eventData.leaderboard;
                            if (battleData.leaderboard) {
                                renderArenaLeaderboard(battleData.leaderboard);
                            }
                            // Tag fastest successful response card
                            _tagFastestResponseCard(battleData.responses);
                        }
                    } catch (e) {
                        console.error("Error parsing stream event:", e, dataStr);
                    }
                }
            }
        }

    } catch (err) {
        console.error('Arena battle failed:', err);
        const cardsGrid = document.getElementById('current-battle-cards');
        if (cardsGrid) {
            cardsGrid.innerHTML += `<div class="arena-response-card" style="border-color: var(--error); grid-column: 1 / -1;">
                <div class="card-body" style="color: var(--error);">Battle failed: ${escapeHtml(err.message)}</div>
            </div>`;
        }
        return;
    }

    // Now proceed to evaluation if requested
    if (evaluatorModelId && battleData) {
        // Show evaluation loading
        const cardsGrid = document.getElementById('current-battle-cards');
        if (cardsGrid) {
            cardsGrid.insertAdjacentHTML('afterend', `<div id="eval-loading" class="arena-prompt-bar" style="margin-top: 1rem; border-radius: 8px; text-align: center;"><div class="spinner" style="display:inline-block; vertical-align:middle; margin-right: 8px;"></div> Evaluating responses with ${evaluatorModelId}...</div>`);
            responsesDiv.scrollTop = responsesDiv.scrollHeight;
        }

        try {
            const evalRes = await fetch('/api/arena/evaluate_battle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prompt: prompt,
                    responses: battleData.responses,
                    evaluator_model_id: evaluatorModelId,
                    trace_id: battleData.trace_id
                })
            });

            const evalData = await evalRes.json();

            if (!evalRes.ok) {
                throw new Error(evalData.detail || 'Evaluation failed');
            }

            const evalLoading = document.getElementById('eval-loading');
            if (evalLoading) evalLoading.remove();

            // Re-render responses with scores
            renderBattleResponses(evalData, false);

            if (evalData.leaderboard) {
                renderArenaLeaderboard(evalData.leaderboard);
            }

        } catch (err) {
            console.error('Evaluation failed:', err);
            const evalLoading = document.getElementById('eval-loading');
            if (evalLoading) evalLoading.innerHTML = `<span style="color: var(--error);">Evaluation failed: ${escapeHtml(err.message)}</span>`;
        }
    }
}

function renderSingleBattleResponse(r, needsManualEval, participantIds) {
    const cardsGrid = document.getElementById('current-battle-cards');
    if (!cardsGrid) return;

    // Find the specific card for this model
    const cards = Array.from(cardsGrid.querySelectorAll('.arena-response-card'));
    const targetCard = cards.find(c => c.querySelector('.card-model').textContent === r.model_id);

    if (!targetCard) return;

    const isWinner = false; // Initial stream doesn't have winners yet
    let scoreHtml = '';
    let badgeHtml = '';

    // Add manual winner button if no evaluator was used
    if (needsManualEval) {
        badgeHtml = `<button class="action-btn small action-winner-btn" 
                       onclick="declareArenaWinner('${r.model_id}', ${JSON.stringify(participantIds).replace(/"/g, '&quot;')}, this.closest('.arena-response-card'))">
                       🏆 Declare Winner
                     </button>`;
    }

    let timeHtml = '';
    if (r.time_ms) {
        timeHtml = `<span class="card-time" style="font-size: 0.75rem; color: var(--text-secondary); margin-left: 8px; font-family: 'Fira Code', monospace;">⏱️ ${(r.time_ms / 1000).toFixed(2)}s</span>`;
    }

    const htmlContent = (typeof marked !== 'undefined' && marked.parse)
        ? marked.parse(r.response)
        : escapeHtml(r.response);

    targetCard.innerHTML = `
        ${badgeHtml}
        <div class="card-header">
            <div>
                <span class="card-model">${r.model_id}</span>
                ${timeHtml}
            </div>
            ${scoreHtml}
        </div>
        <div class="card-body">${htmlContent}</div>
        <div class="card-provider">via ${r.provider}</div>
    `;
}

function renderBattleResponses(data, needsManualEval) {
    const cardsGrid = document.getElementById('current-battle-cards');
    if (!cardsGrid) return;

    const participantIds = data.responses.map(r => r.model_id);

    cardsGrid.innerHTML = data.responses.map(r => {
        const isWinner = r.model_id === data.winner_id;
        const scoreHtml = r.score !== null && r.score !== undefined
            ? `<span class="card-score">${r.score}/10</span>`
            : '';

        let badgeHtml = isWinner ? '<span class="card-badge">🏆 Winner</span>' : '';

        // Add manual winner button if no evaluator was used
        if (needsManualEval) {
            badgeHtml = `<button class="action-btn small action-winner-btn" 
                           onclick="declareArenaWinner('${r.model_id}', ${JSON.stringify(participantIds).replace(/"/g, '&quot;')}, this.closest('.arena-response-card'))">
                           🏆 Declare Winner
                         </button>`;
        }

        let timeHtml = '';
        if (r.time_ms) {
            timeHtml = `<span class="card-time" style="font-size: 0.75rem; color: var(--text-secondary); margin-left: 8px; font-family: 'Fira Code', monospace;">⏱️ ${(r.time_ms / 1000).toFixed(2)}s</span>`;
        }

        const htmlContent = (typeof marked !== 'undefined' && marked.parse)
            ? marked.parse(r.response)
            : escapeHtml(r.response);

        const reasoningHtml = r.reasoning ? `
            <details class="evaluator-reasoning">
                <summary>View Evaluator Reasoning</summary>
                <div class="reasoning-content">${escapeHtml(r.reasoning)}</div>
            </details>
        ` : '';

        return `
            <div class="arena-response-card ${isWinner ? 'winner' : ''}">
                ${badgeHtml}
                <div class="card-header">
                    <div>
                        <span class="card-model">${r.model_id}</span>
                        ${timeHtml}
                    </div>
                    ${scoreHtml}
                </div>
                <div class="card-body">${htmlContent}</div>
                ${reasoningHtml}
                <div class="card-provider">via ${r.provider}</div>
            </div>
        `;
    }).join('');
}

async function declareArenaWinner(winnerId, participantIds, cardElement) {
    try {
        const res = await fetch('/api/arena/declare_winner', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                winner_model_id: winnerId,
                participant_model_ids: participantIds
            })
        });

        if (!res.ok) throw new Error('Failed to declare winner');
        const data = await res.json();

        // Update UI
        if (data.leaderboard) {
            renderArenaLeaderboard(data.leaderboard);
        }

        // Highlight winner card
        const allCards = cardElement.parentElement.querySelectorAll('.arena-response-card');
        allCards.forEach(c => {
            c.classList.remove('winner');
            const btn = c.querySelector('.action-winner-btn');
            if (btn) btn.remove(); // Remove buttons after decision
        });

        cardElement.classList.add('winner');
        const badgeHtml = '<span class="card-badge">🏆 Winner</span>';
        cardElement.insertAdjacentHTML('afterbegin', badgeHtml);

    } catch (err) {
        console.error('Declare winner error:', err);
    }
}

async function loadArenaLeaderboard() {
    try {
        const res = await fetch('/api/arena/leaderboard');
        const data = await res.json();
        renderArenaLeaderboard(data.models || {});
    } catch (err) {
        console.error('Failed to load leaderboard:', err);
    }
}

function renderArenaLeaderboard(modelsData) {
    const container = document.getElementById('arena-leaderboard-cards');
    if (!container) return;

    const models = Object.entries(modelsData);
    if (!models.length) {
        container.innerHTML = '<div class="lb-empty">No battles yet</div>';
        return;
    }

    // Sort by wins desc, then win rate
    models.sort((a, b) => {
        if (b[1].wins !== a[1].wins) return b[1].wins - a[1].wins;
        const rateA = a[1].battles > 0 ? a[1].wins / a[1].battles : 0;
        const rateB = b[1].battles > 0 ? b[1].wins / b[1].battles : 0;
        return rateB - rateA;
    });

    // Compute speed ranking (lower avg time = better rank)
    const speedRanked = [...models]
        .filter(([, s]) => s.battles > 0 && s.total_time_ms > 0)
        .sort((a, b) => {
            const avgA = a[1].total_time_ms / a[1].battles;
            const avgB = b[1].total_time_ms / b[1].battles;
            return avgA - avgB;
        })
        .map(([id]) => id);

    const medals = ['🥇', '🥈', '🥉'];
    const rankColors = ['lb-rank-gold', 'lb-rank-silver', 'lb-rank-bronze'];

    container.innerHTML = models.map(([id, stats], i) => {
        const winRate = stats.battles > 0 ? ((stats.wins / stats.battles) * 100).toFixed(0) : 0;
        const failRate = stats.battles > 0 ? ((stats.failures || 0) / stats.battles * 100).toFixed(0) : 0;
        const avgTime = stats.battles > 0 && stats.total_time_ms > 0
            ? (stats.total_time_ms / stats.battles / 1000).toFixed(2)
            : null;
        const avgScore = stats.scores_count > 0
            ? (stats.scores_total / stats.scores_count).toFixed(1)
            : null;
        const speedRank = speedRanked.indexOf(id);

        const rankLabel = i < 3 ? medals[i] : `${i + 1}`;
        const rankClass = i < 3 ? rankColors[i] : '';

        const failClass = failRate >= 30 ? 'lb-badge-fail-high'
            : failRate >= 10 ? 'lb-badge-fail-mid'
            : 'lb-badge-fail-low';

        const speedBadge = speedRank === 0
            ? `<span class="lb-badge lb-badge-speed">⚡ Fastest</span>`
            : avgTime
            ? `<span class="lb-badge lb-badge-time">⏱ ${avgTime}s avg</span>`
            : '';

        const scoreBadge = avgScore
            ? `<span class="lb-badge lb-badge-score">★ ${avgScore}/10</span>`
            : '';

        const failBadge = `<span class="lb-badge ${failClass}">${failRate}% fail</span>`;

        // Short display name
        const shortName = id.length > 28 ? id.slice(0, 25) + '…' : id;

        return `
        <div class="lb-card ${rankClass}">
            <div class="lb-card-top">
                <span class="lb-rank-label">${rankLabel}</span>
                <span class="lb-model-name" title="${escapeHtml(id)}">${escapeHtml(shortName)}</span>
                <span class="lb-wins">${stats.wins}W / ${stats.battles}B</span>
            </div>
            <div class="lb-bar-row">
                <div class="lb-bar-track">
                    <div class="lb-bar-fill" style="width: ${winRate}%"></div>
                </div>
                <span class="lb-bar-pct">${winRate}%</span>
            </div>
            <div class="lb-badges-row">
                ${speedBadge}
                ${failBadge}
                ${scoreBadge}
            </div>
        </div>`;
    }).join('');
}

function _tagFastestResponseCard(responses) {
    const successful = responses.filter(r => r.success && r.time_ms);
    if (!successful.length) return;
    const fastest = successful.reduce((a, b) => a.time_ms < b.time_ms ? a : b);
    const cardsGrid = document.getElementById('current-battle-cards');
    if (!cardsGrid) return;
    const cards = Array.from(cardsGrid.querySelectorAll('.arena-response-card'));
    const targetCard = cards.find(c => {
        const modelEl = c.querySelector('.card-model');
        return modelEl && modelEl.textContent === fastest.model_id;
    });
    if (targetCard && !targetCard.querySelector('.card-badge-speed')) {
        const badge = document.createElement('span');
        badge.className = 'card-badge-speed';
        badge.textContent = '⚡ Fastest';
        targetCard.insertAdjacentElement('afterbegin', badge);
    }
}

async function clearArenaLeaderboard() {
    if (!confirm('Clear the entire arena leaderboard?')) return;

    try {
        await fetch('/api/arena/leaderboard', { method: 'DELETE' });
        const container = document.getElementById('arena-leaderboard-cards');
        if (container) container.innerHTML = '<div class="lb-empty">No battles yet</div>';
    } catch (err) {
        console.error('Failed to clear leaderboard:', err);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ══════════════════════════════════════════════════════════════════════════════
// GAUNTLET MODE
// ══════════════════════════════════════════════════════════════════════════════

let arenaMode = 'battle';
let arenaLbTab = 'battle';
let gauntletSelectedModels = [];
let gauntletPresets = {};
let gauntletRunning = false;

// Color palette for model polygons / score bars (matches radar chart)
const MODEL_COLORS = [
    '#00d9ff', '#ff00ff', '#00ff88', '#f59e0b',
    '#ef4444', '#a855f7', '#3b82f6', '#ec4899',
];

// ── Mode / tab switching ──────────────────────────────────────────────────────

function setArenaMode(mode) {
    arenaMode = mode;

    document.getElementById('battle-controls').style.display  = mode === 'battle'   ? '' : 'none';
    document.getElementById('gauntlet-controls').style.display = mode === 'gauntlet' ? '' : 'none';
    document.getElementById('battle-area').style.display       = mode === 'battle'   ? '' : 'none';
    document.getElementById('gauntlet-area').style.display     = mode === 'gauntlet' ? '' : 'none';

    document.querySelectorAll('.arena-mode-btn').forEach(btn =>
        btn.classList.toggle('active', btn.dataset.mode === mode)
    );

    setLbTab(mode === 'gauntlet' ? 'gauntlet' : 'battle');
}

function setLbTab(tab) {
    arenaLbTab = tab;
    document.getElementById('arena-leaderboard-cards').style.display = tab === 'battle'   ? '' : 'none';
    document.getElementById('gauntlet-leaderboard').style.display    = tab === 'gauntlet' ? '' : 'none';
    document.querySelectorAll('.lb-tab').forEach(btn =>
        btn.classList.toggle('active', btn.dataset.tab === tab)
    );
}

// ── Preset loading & preview ──────────────────────────────────────────────────

async function loadGauntletPresets() {
    try {
        const res = await fetch('/api/arena/gauntlet/presets');
        if (!res.ok) return;
        const data = await res.json();
        gauntletPresets = data.presets || {};

        const sel = document.getElementById('gauntlet-preset');
        if (!sel) return;
        sel.innerHTML = Object.entries(gauntletPresets).map(([id, p]) =>
            `<option value="${id}">${p.icon} ${escapeHtml(p.name)}</option>`
        ).join('');

        const firstId = Object.keys(gauntletPresets)[0];
        if (firstId) updateGauntletPresetPreview(firstId);
    } catch (err) {
        console.error('Failed to load gauntlet presets:', err);
    }
}

function updateGauntletPresetPreview(presetId) {
    const preset = gauntletPresets[presetId];
    const el = document.getElementById('gauntlet-preset-preview');
    if (!preset || !el) return;

    el.innerHTML = `
        <p class="gauntlet-preset-desc">${escapeHtml(preset.description)}</p>
        <ul class="gauntlet-cat-list">
            ${preset.categories.map(c => `
                <li>
                    <span>${escapeHtml(c.name)}</span>
                    <span class="gauntlet-cat-weight">×${c.weight}</span>
                </li>
            `).join('')}
        </ul>`;
}

// ── Gauntlet model chips ──────────────────────────────────────────────────────

function renderGauntletChips() {
    const el = document.getElementById('gauntlet-model-chips');
    if (!el) return;
    el.innerHTML = gauntletSelectedModels.map(id => `
        <span class="arena-chip">
            ${escapeHtml(id)}
            <span class="chip-remove" onclick="removeGauntletModel('${id}')">&times;</span>
        </span>`).join('');
}

function removeGauntletModel(modelId) {
    gauntletSelectedModels = gauntletSelectedModels.filter(id => id !== modelId);
    renderGauntletChips();
}

// ── Start gauntlet ────────────────────────────────────────────────────────────

async function startGauntlet() {
    if (gauntletRunning) return;

    const presetId  = (document.getElementById('gauntlet-preset')    || {}).value || '';
    const evalId    = (document.getElementById('gauntlet-evaluator')  || {}).value || '';

    if (!gauntletSelectedModels.length) { showToast('Add at least 1 model.', 'warn'); return; }
    if (!presetId)  { showToast('Select a preset.', 'warn'); return; }
    if (!evalId)    { showToast('An evaluator is required for Gauntlet mode.', 'warn'); return; }

    gauntletRunning = true;
    const startBtn = document.getElementById('gauntlet-start');
    if (startBtn) startBtn.disabled = true;

    const display = document.getElementById('gauntlet-display');
    if (display) display.innerHTML = '';

    try {
        const res = await fetch('/api/arena/gauntlet_stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model_ids: gauntletSelectedModels,
                preset_name: presetId,
                evaluator_model_id: evalId,
            }),
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Gauntlet failed to start');
        }

        const reader  = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        let currentCategories = [];

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const raw = line.substring(6).trim();
                if (!raw) continue;
                try {
                    const ev = JSON.parse(raw);
                    if (ev.type === 'gauntlet_start') {
                        currentCategories = ev.categories || [];
                        _gauntletInitDisplay(ev);
                    } else if (ev.type === 'category_start') {
                        _gauntletCategoryStart(ev);
                    } else if (ev.type === 'model_response') {
                        _gauntletModelResponse(ev);
                    } else if (ev.type === 'category_complete') {
                        _gauntletCategoryComplete(ev, gauntletSelectedModels);
                    } else if (ev.type === 'gauntlet_complete') {
                        _gauntletComplete(ev, currentCategories);
                        if (ev.leaderboard) renderGauntletLeaderboard(ev.leaderboard);
                    }
                } catch (e) {
                    console.error('Gauntlet parse error:', e, raw);
                }
            }
        }

    } catch (err) {
        console.error('Gauntlet failed:', err);
        const display = document.getElementById('gauntlet-display');
        if (display) display.innerHTML =
            `<div class="arena-prompt-bar" style="color:var(--error);">Gauntlet failed: ${escapeHtml(err.message)}</div>`;
    } finally {
        gauntletRunning = false;
        if (startBtn) startBtn.disabled = false;
    }
}

// ── Gauntlet SSE handlers ─────────────────────────────────────────────────────

function _gauntletInitDisplay(ev) {
    const display = document.getElementById('gauntlet-display');
    if (!display) return;

    const catRows = ev.categories.map(cat => `
        <div class="gauntlet-cat-card pending" id="gauntlet-cat-${cat.id}" data-cat-id="${cat.id}">
            <div class="gauntlet-cat-header">
                <span class="gauntlet-cat-status-icon">🔒</span>
                <span class="gauntlet-cat-name">${escapeHtml(cat.name)}</span>
                <span class="gauntlet-cat-status">Pending</span>
            </div>
        </div>`).join('');

    display.innerHTML = `
        <div class="gauntlet-run-header">
            <span class="gauntlet-preset-label">${escapeHtml(ev.preset.icon)} ${escapeHtml(ev.preset.name)}</span>
            <div class="gauntlet-progress-info">
                <div class="gauntlet-progress-track">
                    <div class="gauntlet-progress-fill" id="gauntlet-progress-fill" style="width:0%"></div>
                </div>
                <span class="gauntlet-progress-text" id="gauntlet-progress-text">0 / ${ev.categories.length}</span>
            </div>
        </div>
        <div class="gauntlet-categories-list" id="gauntlet-categories-list">${catRows}</div>
        <div class="gauntlet-results" id="gauntlet-results" style="display:none;"></div>`;
}

function _gauntletCategoryStart(ev) {
    const card = document.getElementById(`gauntlet-cat-${ev.category_id}`);
    if (!card) return;
    card.className = 'gauntlet-cat-card running';
    const icon   = card.querySelector('.gauntlet-cat-status-icon');
    const status = card.querySelector('.gauntlet-cat-status');
    if (icon)   icon.textContent   = '⏳';
    if (status) status.textContent = 'Generating…';
    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function _gauntletModelResponse(ev) {
    const card   = document.getElementById(`gauntlet-cat-${ev.category_id}`);
    const status = card && card.querySelector('.gauntlet-cat-status');
    if (status) status.textContent = 'Evaluating…';
}

function _gauntletCategoryComplete(ev, modelIds) {
    const card = document.getElementById(`gauntlet-cat-${ev.category_id}`);
    if (!card) return;

    const scores = ev.scores || {};
    let winner = null, best = -1;
    for (const [mid, s] of Object.entries(scores)) {
        if (s.score != null && s.score > best) { best = s.score; winner = mid; }
    }

    const scoresHtml = modelIds.map((mid, mi) => {
        const s     = scores[mid];
        const score = s ? s.score : null;
        const color = MODEL_COLORS[mi % MODEL_COLORS.length];
        const width = score != null ? (score / 10) * 100 : 0;
        const short = mid.length > 22 ? mid.slice(0, 19) + '…' : mid;
        const win   = mid === winner;
        return `
            <div class="cat-model-score-row">
                <span class="cat-model-name${win ? ' cat-winner-name' : ''}" title="${escapeHtml(mid)}">${escapeHtml(short)}</span>
                <div class="cat-score-bar-track">
                    <div class="cat-score-bar-fill" style="width:${width}%; background:${color};${win ? ' box-shadow:0 0 5px ' + color + ';' : ''}"></div>
                </div>
                <span class="cat-score-val">${score != null ? score + '/10' : '—'}</span>
            </div>`;
    }).join('');

    const winShort = winner ? (winner.length > 20 ? winner.slice(0,17) + '…' : winner) : null;
    card.className = 'gauntlet-cat-card complete';
    card.innerHTML = `
        <div class="gauntlet-cat-header">
            <span class="gauntlet-cat-status-icon">✅</span>
            <span class="gauntlet-cat-name">${escapeHtml(ev.category_name)}</span>
            <span class="gauntlet-cat-status">${winShort ? '🏆 ' + escapeHtml(winShort) : 'No winner'}</span>
        </div>
        <div class="gauntlet-cat-scores">${scoresHtml}</div>`;

    // Update progress bar
    const completed = ev.category_index + 1;
    const total     = ev.total_categories || document.querySelectorAll('[id^="gauntlet-cat-"]').length;
    const fill = document.getElementById('gauntlet-progress-fill');
    const text = document.getElementById('gauntlet-progress-text');
    if (fill) fill.style.width = `${(completed / total) * 100}%`;
    if (text) text.textContent = `${completed} / ${total}`;
}

function _gauntletComplete(ev, categories) {
    const resultsDiv = document.getElementById('gauntlet-results');
    if (!resultsDiv) return;

    const { results, ranked } = ev;
    const medals = ['🥇', '🥈', '🥉'];

    // Table header columns
    const catTh = categories.map(c => `<th>${escapeHtml(c.name)}</th>`).join('');

    // Table rows sorted by rank
    const tableRows = ranked.map((mid, rank) => {
        const r    = results[mid];
        const tds  = categories.map(c => {
            const s = r.category_scores[c.id];
            return `<td class="score-cell">${(s != null) ? s : '—'}</td>`;
        }).join('');
        const label = rank < 3 ? medals[rank] : (rank + 1);
        const short = mid.length > 24 ? mid.slice(0, 21) + '…' : mid;
        return `
            <tr class="${rank === 0 ? 'winner-row' : ''}">
                <td>${label}</td>
                <td title="${escapeHtml(mid)}" style="font-size:0.71rem;">${escapeHtml(short)}</td>
                <td class="composite-cell">${r.composite_score}</td>
                ${tds}
            </tr>`;
    }).join('');

    resultsDiv.style.display = '';
    resultsDiv.innerHTML = `
        <div class="gauntlet-results-header">🏁 Gauntlet Complete — ${escapeHtml(ev.winner_id || '')} wins</div>
        <div class="gauntlet-results-body">
            <div class="gauntlet-radar-container" id="gauntlet-radar-container"></div>
            <div class="gauntlet-scores-table-container">
                <table class="gauntlet-scores-table">
                    <thead><tr><th>#</th><th>Model</th><th>Score</th>${catTh}</tr></thead>
                    <tbody>${tableRows}</tbody>
                </table>
            </div>
        </div>`;

    // Build radar data
    const radarData = {};
    for (const [mid, r] of Object.entries(results)) {
        radarData[mid] = { category_scores: r.category_scores };
    }
    renderRadarChart('gauntlet-radar-container', categories, radarData, ranked);
    resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Radar chart (pure SVG) ────────────────────────────────────────────────────

function renderRadarChart(containerId, categories, modelsData, rankedIds) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const n = categories.length;
    if (n < 3) { container.innerHTML = '<p style="color:var(--text-secondary);font-size:0.8rem;padding:1rem;">Need ≥ 3 categories for radar chart.</p>'; return; }

    const size   = 280;
    const cx     = size / 2;
    const cy     = size / 2;
    const r      = 90;
    const labelR = r + 26;
    const modelIds = rankedIds || Object.keys(modelsData);

    const angle  = (i) => (i * 2 * Math.PI / n) - Math.PI / 2;
    const px     = (i, frac) => cx + frac * r * Math.cos(angle(i));
    const py     = (i, frac) => cy + frac * r * Math.sin(angle(i));

    // Grid rings at 20 % intervals
    const grid = [0.2, 0.4, 0.6, 0.8, 1.0].map(frac => {
        const pts = categories.map((_, i) => `${px(i, frac).toFixed(1)},${py(i, frac).toFixed(1)}`).join(' ');
        return `<polygon points="${pts}" fill="none" stroke="rgba(255,255,255,${frac === 1.0 ? 0.14 : 0.07})" stroke-width="1"/>`;
    }).join('');

    // Axis spokes
    const axes = categories.map((_, i) =>
        `<line x1="${cx}" y1="${cy}" x2="${px(i,1).toFixed(1)}" y2="${py(i,1).toFixed(1)}" stroke="rgba(255,255,255,0.11)" stroke-width="1"/>`
    ).join('');

    // Category labels
    const labels = categories.map((cat, i) => {
        const a   = angle(i);
        const lx  = cx + labelR * Math.cos(a);
        const ly  = cy + labelR * Math.sin(a);
        const cos = Math.cos(a);
        const anchor = cos > 0.15 ? 'start' : cos < -0.15 ? 'end' : 'middle';
        return `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="${anchor}" dominant-baseline="middle" fill="rgba(255,255,255,0.52)" font-size="10" font-family="system-ui,sans-serif">${escapeHtml(cat.name)}</text>`;
    }).join('');

    // Model polygons + dots
    const polygons = modelIds.map((mid, mi) => {
        const color  = MODEL_COLORS[mi % MODEL_COLORS.length];
        const scores = modelsData[mid]?.category_scores || {};
        const pts = categories.map((cat, i) => {
            const s = scores[cat.id];
            const f = s != null ? Math.max(0, Math.min(10, s)) / 10 : 0;
            return `${px(i, f).toFixed(1)},${py(i, f).toFixed(1)}`;
        }).join(' ');
        const dots = categories.map((cat, i) => {
            const s = scores[cat.id];
            const f = s != null ? Math.max(0, Math.min(10, s)) / 10 : 0;
            return f > 0 ? `<circle cx="${px(i,f).toFixed(1)}" cy="${py(i,f).toFixed(1)}" r="3" fill="${color}" stroke="var(--bg-secondary)" stroke-width="1.5"/>` : '';
        }).join('');
        return `<polygon points="${pts}" fill="${color}" fill-opacity="0.15" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>${dots}`;
    }).join('');

    const legend = modelIds.map((mid, mi) => {
        const color = MODEL_COLORS[mi % MODEL_COLORS.length];
        const short = mid.length > 24 ? mid.slice(0, 21) + '…' : mid;
        return `<div class="radar-legend-item">
                    <span class="radar-legend-dot" style="background:${color}"></span>
                    <span class="radar-legend-label" title="${escapeHtml(mid)}">${escapeHtml(short)}</span>
                </div>`;
    }).join('');

    container.innerHTML = `
        <svg viewBox="0 0 ${size} ${size}" class="gauntlet-radar-svg" style="overflow:visible;">
            ${grid}${axes}${polygons}${labels}
        </svg>
        <div class="radar-legend">${legend}</div>`;
}

// ── Gauntlet leaderboard ──────────────────────────────────────────────────────

function renderGauntletLeaderboard(gauntletData) {
    const container = document.getElementById('gauntlet-leaderboard');
    if (!container) return;

    const entries = Object.entries(gauntletData || {});
    if (!entries.length) { container.innerHTML = '<div class="lb-empty">No gauntlets yet</div>'; return; }

    entries.sort((a, b) => (b[1].best_composite || 0) - (a[1].best_composite || 0));
    const medals = ['🥇', '🥈', '🥉'];

    container.innerHTML = entries.map(([mid, data], rank) => {
        const short  = mid.length > 26 ? mid.slice(0, 23) + '…' : mid;
        const label  = rank < 3 ? medals[rank] : (rank + 1);
        const preset = (data.last_preset || '').replace(/_/g, ' ');
        return `
            <div class="gauntlet-lb-card">
                <div class="gauntlet-lb-top">
                    <span class="gauntlet-lb-rank">${label}</span>
                    <span class="gauntlet-lb-model" title="${escapeHtml(mid)}">${escapeHtml(short)}</span>
                    <span class="gauntlet-lb-composite">${(data.best_composite || 0).toFixed(2)}</span>
                </div>
                <div class="gauntlet-lb-meta">${data.runs || 0} run${data.runs !== 1 ? 's' : ''} · last ${(data.last_composite || 0).toFixed(2)} · ${escapeHtml(preset)}</div>
            </div>`;
    }).join('');
}

async function loadGauntletLeaderboard() {
    try {
        const res  = await fetch('/api/arena/leaderboard');
        const data = await res.json();
        if (data.gauntlet) renderGauntletLeaderboard(data.gauntlet);
    } catch (err) {
        console.error('Failed to load gauntlet leaderboard:', err);
    }
}

// ── Initialise when the arena partial is first injected ───────────────────────
// The partial loader fetches arena.html + mode-arena.js lazily on first visit.
// DOMContentLoaded fires before these load, so initializeArena() must be called
// here — exactly as every other lazy-loaded JS module does via panelLoaded.
document.addEventListener('panelLoaded', function (e) {
    if (e.detail.tabName === 'arena') {
        initializeArena();
        loadArenaModels();
        loadArenaLeaderboard();
        loadGauntletPresets();
        loadGauntletLeaderboard();
    }
});
