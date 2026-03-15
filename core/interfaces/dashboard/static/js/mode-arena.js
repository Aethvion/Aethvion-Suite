// Misaka Cipher - LLM Arena Mode
// Handles interactions with the Arena battle UI and leaderboard

let arenaSelectedModels = [];
let arenaAvailableModels = [];

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
    // Send button
    const sendBtn = document.getElementById('arena-send');
    if (sendBtn) {
        sendBtn.addEventListener('click', sendArenaPrompt);
    }

    // Input enter key
    const input = document.getElementById('arena-input');
    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendArenaPrompt();
            }
        });
        input.addEventListener('input', function () {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
            if (this.value === '') this.style.height = '';
        });
    }

    // Clear leaderboard
    const clearBtn = document.getElementById('arena-clear-leaderboard');
    if (clearBtn) {
        clearBtn.addEventListener('click', clearArenaLeaderboard);
    }
}

async function loadArenaModels() {
    try {
        const res = await fetch('/api/registry/models/chat');
        if (!res.ok) return;
        const data = await res.json();

        // Use shared utility from core.js
        const chatOptions = generateCategorizedModelOptions(data, 'chat');

        // Populate add-model dropdown
        const addSelect = document.getElementById('arena-model-add');
        if (addSelect) {
            addSelect.innerHTML = '<option value="">+ Add Model...</option>' + chatOptions;
        }

        // Pre-populate AI Conv dropdown
        const aiconvSelect = document.getElementById('aiconv-model-add');
        if (aiconvSelect) {
            aiconvSelect.innerHTML = '<option value="">+ Add Model...</option>' + chatOptions;
        }

        // Populate evaluator dropdown
        const evalSelect = document.getElementById('arena-evaluator');
        if (evalSelect) {
            evalSelect.innerHTML = '<option value="">No Evaluator</option>' + chatOptions;
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
    const tbody = document.getElementById('arena-leaderboard-body');
    if (!tbody) return;

    const models = Object.entries(modelsData);
    if (!models.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="placeholder-text">No battles yet</td></tr>';
        return;
    }

    // Sort by wins desc, then win rate
    models.sort((a, b) => {
        if (b[1].wins !== a[1].wins) return b[1].wins - a[1].wins;
        const rateA = a[1].battles > 0 ? a[1].wins / a[1].battles : 0;
        const rateB = b[1].battles > 0 ? b[1].wins / b[1].battles : 0;
        return rateB - rateA;
    });

    tbody.innerHTML = models.map(([id, stats], i) => {
        const winRate = stats.battles > 0 ? ((stats.wins / stats.battles) * 100).toFixed(0) : 0;
        const barWidth = Math.min(winRate, 100);
        return `<tr>
            <td style="font-weight:600; color: var(--primary);">${i + 1}</td>
            <td style="font-size:0.78rem; font-family:'Fira Code',monospace;">${id}</td>
            <td style="color: var(--success); font-weight:600;">${stats.wins}</td>
            <td>${stats.battles}</td>
            <td>${winRate}%<span class="win-rate-bar" style="width:${barWidth * 0.5}px;"></span></td>
        </tr>`;
    }).join('');
}

async function clearArenaLeaderboard() {
    if (!confirm('Clear the entire arena leaderboard?')) return;

    try {
        await fetch('/api/arena/leaderboard', { method: 'DELETE' });
        renderArenaLeaderboard({});
    } catch (err) {
        console.error('Failed to clear leaderboard:', err);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
