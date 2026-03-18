// Misaka Cipher - AI Conversations Mode
// Handles the multi-agent AI Conversation loop and generation UI

let aiconvSelectedModels = [];
let aiconvAvailableNames = ['Alice', 'Bob', 'Charlie', 'Dave', 'Eve', 'Frank', 'Grace', 'Heidi', 'Ivan', 'Judy', 'Mallory', 'Olivia', 'Peggy', 'Sybil', 'Trent', 'Victor', 'Walter'];
let aiconvUsedNames = [];

let aiconvState = {
    isRunning: false,
    isPaused: false,
    currentTurnIndex: 0,
    totalTurnsCompleted: 0,
    maxTurnsPerModel: 5,
    messageHistory: [],
    estInTokens: 0,
    estOutTokens: 0,
    estCost: 0
};

// ─── Participant Chip Rendering ───────────────────────────────────────────────

function renderAIConvChips() {
    const container = document.getElementById('aiconv-model-chips');
    if (!container) return;

    container.innerHTML = aiconvSelectedModels.map((model, index) => {
        if (model.isHuman) {
            return `
                <div class="aiconv-identity-card" style="border: 1px solid ${model.color}; padding: 0.5rem; margin-bottom: 0.5rem; border-radius: 6px; background: var(--bg-tertiary); border-left: 4px solid ${model.color};">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 0.5rem;">
                        <div style="display:flex; align-items:center; gap: 0.5rem;">
                            <span class="chip-number" style="background:${model.color}; color:#000; padding:2px 6px; border-radius:12px; font-weight:bold; font-size:0.75rem;">${index + 1}</span>
                            <strong style="color:${model.color}; font-size: 0.9rem;">👤 ${model.name}</strong>
                            <span style="font-size: 0.75rem; color: var(--text-secondary);">(You)</span>
                        </div>
                        <span class="chip-remove" style="cursor:pointer; font-size: 1.2rem; color:var(--text-secondary);" onclick="removeAIConvModel(${index})">&times;</span>
                    </div>
                    <input
                        type="text"
                        class="term-input aiconv-human-name-input"
                        data-index="${index}"
                        placeholder="Your display name"
                        value="${escapeHtml(model.name)}"
                        style="width:100%; font-size:0.8rem;"
                    >
                </div>`;
        }

        return `
            <div class="aiconv-identity-card" style="border: 1px solid ${model.color}; padding: 0.5rem; margin-bottom: 0.5rem; border-radius: 6px; background: var(--bg-tertiary); border-left: 4px solid ${model.color};">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 0.5rem;">
                    <div style="display:flex; align-items:center; gap: 0.5rem;">
                        <span class="chip-number" style="background:${model.color}; color:#000; padding:2px 6px; border-radius:12px; font-weight:bold; font-size:0.75rem;">${index + 1}</span>
                        <strong style="color:${model.color}; font-size: 0.9rem;">${model.name}</strong>
                        <span style="font-size: 0.75rem; color: var(--text-secondary);">(${model.id})</span>
                    </div>
                    <span class="chip-remove" style="cursor:pointer; font-size: 1.2rem; color:var(--text-secondary);" onclick="removeAIConvModel(${index})">&times;</span>
                </div>
                <textarea
                    class="term-input aiconv-personality-input"
                    data-index="${index}"
                    placeholder="Optional: Define ${model.name}'s personality or role here..."
                    style="width:100%; min-height:40px; resize:vertical; font-size:0.8rem;"
                >${model.personality}</textarea>
            </div>`;
    }).join('');

    // Wire up personality inputs
    container.querySelectorAll('.aiconv-personality-input').forEach(ta => {
        ta.addEventListener('input', (e) => {
            const idx = parseInt(e.target.dataset.index);
            if (aiconvSelectedModels[idx]) aiconvSelectedModels[idx].personality = e.target.value;
        });
    });

    // Wire up human name inputs
    container.querySelectorAll('.aiconv-human-name-input').forEach(inp => {
        inp.addEventListener('input', (e) => {
            const idx = parseInt(e.target.dataset.index);
            if (aiconvSelectedModels[idx]) aiconvSelectedModels[idx].name = e.target.value.trim() || 'You';
        });
    });
}

function removeAIConvModel(index) {
    if (aiconvState.isRunning && !aiconvState.isPaused) return;
    aiconvSelectedModels.splice(index, 1);
    renderAIConvChips();
}

function addHumanParticipant() {
    if (aiconvSelectedModels.some(m => m.isHuman)) {
        showToast('You are already in the conversation.', 'warn');
        return;
    }
    aiconvSelectedModels.push({
        id: 'human',
        name: 'You',
        color: 'hsl(200, 70%, 65%)',
        personality: '',
        isHuman: true
    });
    renderAIConvChips();
    showToast('Added yourself to the conversation! It\'s your turn when the round reaches you.', 'info');
}

// ─── Start / Stop / Pause ────────────────────────────────────────────────────

async function startAIConv() {
    if (aiconvSelectedModels.length < 2) {
        showToast('Please select at least 2 participants.', 'warn');
        return;
    }

    const aiParticipants = aiconvSelectedModels.filter(m => !m.isHuman);
    if (aiParticipants.length < 1) {
        showToast('Please add at least 1 AI model.', 'warn');
        return;
    }

    const topicInput = document.getElementById('aiconv-topic');
    const msgCountInput = document.getElementById('aiconv-msg-count');
    const topic = topicInput ? topicInput.value.trim() : '';
    const maxMsgs = msgCountInput ? parseInt(msgCountInput.value) || 5 : 5;

    if (!topic) {
        showToast('Please enter a topic or initial prompt.', 'warn');
        return;
    }

    let baseSystem = `The topic of this conversation is: ${topic}.\n\nParticipants:\n`;
    for (const m of aiconvSelectedModels) {
        if (m.isHuman) {
            baseSystem += `- ${m.name} [Human participant — will chime in occasionally]\n`;
        } else {
            baseSystem += `- ${m.name} [Model: ${m.id}]`;
            if (m.personality) baseSystem += `\n  Role/Personality: ${m.personality}`;
            baseSystem += "\n";
        }
    }
    baseSystem += "\nPlease keep your responses concise, engaging, and stay in character.";

    // Reset state
    aiconvState.isRunning = true;
    aiconvState.isPaused = false;
    aiconvState.currentTurnIndex = 0;
    aiconvState.totalTurnsCompleted = 0;
    aiconvState.maxTurnsPerModel = maxMsgs;
    aiconvState.messageHistory = [{ role: 'system', content: baseSystem }];
    aiconvState.estInTokens = 0;
    aiconvState.estOutTokens = 0;
    aiconvState.estCost = 0;

    // Update UI
    document.getElementById('aiconv-start-btn').disabled = true;
    document.getElementById('aiconv-pause-btn').disabled = false;
    document.getElementById('aiconv-stop-btn').disabled = false;
    document.getElementById('aiconv-pause-btn').innerHTML = '<i class="fas fa-pause"></i> Pause';
    document.getElementById('aiconv-topic').disabled = true;

    // Remove any old continue button
    const oldContinue = document.getElementById('aiconv-continue-btn');
    if (oldContinue) oldContinue.remove();

    const messagesContainer = document.getElementById('aiconv-messages');
    messagesContainer.innerHTML = `
        <div class="message system-message">
            <div class="message-content">
                <strong>System:</strong> Starting conversation on topic: "${escapeHtml(topic)}"
            </div>
        </div>
    `;

    updateAIConvUI();
    runAIConvLoop();
}

function togglePauseAIConv() {
    aiconvState.isPaused = !aiconvState.isPaused;
    const pauseBtn = document.getElementById('aiconv-pause-btn');
    if (aiconvState.isPaused) {
        pauseBtn.innerHTML = '<i class="fas fa-play"></i> Resume';
        showPauseInjectBar();
    } else {
        pauseBtn.innerHTML = '<i class="fas fa-pause"></i> Pause';
        hidePauseInjectBar();
        runAIConvLoop();
    }
}

function stopAIConv(completed = false) {
    aiconvState.isRunning = false;
    aiconvState.isPaused = false;
    hidePauseInjectBar();
    saveCurrentAIConv(); // save on stop/complete

    document.getElementById('aiconv-start-btn').disabled = false;
    document.getElementById('aiconv-pause-btn').disabled = true;
    document.getElementById('aiconv-stop-btn').disabled = true;
    document.getElementById('aiconv-topic').disabled = false;

    const messagesContainer = document.getElementById('aiconv-messages');

    if (completed) {
        messagesContainer.insertAdjacentHTML('beforeend', `
            <div class="message system-message">
                <div class="message-content">
                    <strong>System:</strong> Conversation completed!
                    <button id="aiconv-continue-btn" class="action-btn secondary" style="margin-left:1rem; padding:0.25rem 0.75rem; font-size:0.8rem;">
                        <i class="fas fa-plus"></i> Continue Conversation
                    </button>
                </div>
            </div>
        `);
    } else {
        messagesContainer.insertAdjacentHTML('beforeend', `
            <div class="message system-message">
                <div class="message-content">
                    <strong>System:</strong> Conversation stopped.
                    <button id="aiconv-continue-btn" class="action-btn secondary" style="margin-left:1rem; padding:0.25rem 0.75rem; font-size:0.8rem;">
                        <i class="fas fa-play"></i> Continue from here
                    </button>
                </div>
            </div>
        `);
    }
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function continueAIConv() {
    if (aiconvSelectedModels.length < 1) {
        showToast('No participants to continue with.', 'warn');
        return;
    }

    const msgCountInput = document.getElementById('aiconv-msg-count');
    const extraRounds = msgCountInput ? parseInt(msgCountInput.value) || 5 : 5;
    aiconvState.maxTurnsPerModel += extraRounds;
    aiconvState.isRunning = true;
    aiconvState.isPaused = false;

    document.getElementById('aiconv-start-btn').disabled = true;
    document.getElementById('aiconv-pause-btn').disabled = false;
    document.getElementById('aiconv-stop-btn').disabled = false;
    document.getElementById('aiconv-pause-btn').innerHTML = '<i class="fas fa-pause"></i> Pause';

    const continueBtn = document.getElementById('aiconv-continue-btn');
    if (continueBtn) continueBtn.closest('.message').remove();

    const messagesContainer = document.getElementById('aiconv-messages');
    messagesContainer.insertAdjacentHTML('beforeend', `
        <div class="message system-message">
            <div class="message-content">
                <strong>System:</strong> Continuing conversation for ${extraRounds} more rounds per participant…
            </div>
        </div>
    `);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    runAIConvLoop();
}

// ─── Pause Inject Bar ────────────────────────────────────────────────────────

function showPauseInjectBar() {
    if (document.getElementById('aiconv-inject-bar')) return;
    const chatArea = document.querySelector('.aiconv-chat-area');
    if (!chatArea) return;

    chatArea.insertAdjacentHTML('beforeend', `
        <div id="aiconv-inject-bar" style="padding:0.5rem 0.75rem; border-top: 1px solid var(--primary); background: var(--bg-tertiary); display:flex; gap:0.5rem; align-items:center;">
            <i class="fas fa-comment-dots" style="color:var(--primary); flex-shrink:0;"></i>
            <input id="aiconv-inject-input" class="term-input" style="flex:1; padding:0.35rem 0.6rem; font-size:0.85rem;" placeholder="Inject a comment into the conversation (Enter to send)…">
            <button id="aiconv-inject-send" class="action-btn primary" style="padding:0.35rem 0.75rem; font-size:0.8rem; flex-shrink:0;">
                <i class="fas fa-paper-plane"></i> Send
            </button>
        </div>
    `);

    const input = document.getElementById('aiconv-inject-input');
    const sendBtn = document.getElementById('aiconv-inject-send');

    const doInject = () => {
        const msg = input ? input.value.trim() : '';
        if (!msg) return;

        aiconvState.messageHistory.push({ role: 'user', content: `[Narrator/Observer]: ${msg}` });

        const messagesContainer = document.getElementById('aiconv-messages');
        messagesContainer.insertAdjacentHTML('beforeend', `
            <div class="message" style="border-left: 4px solid var(--primary); background: rgba(99,102,241,0.06); padding:0.6rem 1rem; margin:0.3rem 0;">
                <div class="message-header" style="margin-bottom:0.3rem;">
                    <span style="color: var(--primary); font-weight: bold; font-size:0.9rem;">💬 You (injected)</span>
                </div>
                <div class="message-content">${escapeHtml(msg)}</div>
            </div>
        `);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        input.value = '';
        showToast('Message injected — will be seen when conversation resumes.', 'success', 1800);
    };

    if (sendBtn) sendBtn.addEventListener('click', doInject);
    if (input) input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doInject(); } });
    if (input) setTimeout(() => input.focus(), 50);
}

function hidePauseInjectBar() {
    const bar = document.getElementById('aiconv-inject-bar');
    if (bar) bar.remove();
}

// ─── Human Turn Prompt ───────────────────────────────────────────────────────

function waitForHumanInput(participant) {
    return new Promise((resolve) => {
        const messagesContainer = document.getElementById('aiconv-messages');
        const promptId = `human-turn-${Date.now()}`;

        messagesContainer.insertAdjacentHTML('beforeend', `
            <div id="${promptId}" style="border-left: 4px solid ${participant.color}; background: rgba(0,180,255,0.05); padding:0.75rem 1rem; margin:0.3rem 0; border-radius:0 6px 6px 0;">
                <div style="color: ${participant.color}; font-weight: bold; font-size:0.95rem; margin-bottom:0.5rem;">
                    👤 ${escapeHtml(participant.name)} — It's your turn!
                    <span style="font-size:0.75rem; color:var(--text-secondary); font-weight:normal; margin-left:0.5rem;">Press Ctrl+Enter to send</span>
                </div>
                <textarea id="${promptId}-input" class="term-input" style="width:100%; min-height:64px; resize:vertical; font-size:0.85rem; box-sizing:border-box;" placeholder="Type your message… or skip this turn"></textarea>
                <div style="display:flex; gap:0.5rem; margin-top:0.5rem;">
                    <button id="${promptId}-send" class="action-btn primary" style="flex:1;">
                        <i class="fas fa-paper-plane"></i> Send
                    </button>
                    <button id="${promptId}-skip" class="action-btn secondary" style="flex:0 0 auto; padding:0.4rem 1rem;">
                        <i class="fas fa-forward"></i> Skip turn
                    </button>
                </div>
            </div>
        `);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        const inputEl = document.getElementById(`${promptId}-input`);
        const sendBtn = document.getElementById(`${promptId}-send`);
        const skipBtn = document.getElementById(`${promptId}-skip`);

        if (inputEl) setTimeout(() => inputEl.focus(), 50);

        const cleanup = () => { const el = document.getElementById(promptId); if (el) el.remove(); };

        const doSend = () => {
            const msg = inputEl ? inputEl.value.trim() : '';
            if (!msg) { if (inputEl) inputEl.focus(); return; }
            cleanup();
            resolve({ action: 'send', message: msg });
        };

        if (sendBtn) sendBtn.addEventListener('click', doSend);
        if (skipBtn) skipBtn.addEventListener('click', () => { cleanup(); resolve({ action: 'skip' }); });
        if (inputEl) inputEl.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); doSend(); } });
    });
}

// ─── Main Loop ───────────────────────────────────────────────────────────────

async function runAIConvLoop() {
    const totalTarget = () => aiconvState.maxTurnsPerModel * aiconvSelectedModels.length;

    while (aiconvState.isRunning && !aiconvState.isPaused && aiconvState.totalTurnsCompleted < totalTarget()) {
        const currentModel = aiconvSelectedModels[aiconvState.currentTurnIndex];
        const messagesContainer = document.getElementById('aiconv-messages');

        // ── Human turn ──
        if (currentModel.isHuman) {
            const result = await waitForHumanInput(currentModel);
            if (!aiconvState.isRunning) break;

            if (result.action === 'send') {
                messagesContainer.insertAdjacentHTML('beforeend', `
                    <div class="message" style="border-left: 4px solid ${currentModel.color}; background: rgba(0,180,255,0.06); padding:0.6rem 1rem; margin:0.3rem 0;">
                        <div class="message-header" style="margin-bottom:0.3rem;">
                            <span style="color: ${currentModel.color}; font-weight: bold; font-size:1rem;">👤 ${escapeHtml(currentModel.name)}</span>
                        </div>
                        <div class="message-content">${escapeHtml(result.message)}</div>
                    </div>
                `);
                messagesContainer.scrollTop = messagesContainer.scrollHeight;

                aiconvState.messageHistory.push({
                    role: 'user',
                    content: `${currentModel.name}: ${result.message}`
                });
            }
            // skip: no message, just advance

            aiconvState.totalTurnsCompleted++;
            aiconvState.currentTurnIndex = (aiconvState.currentTurnIndex + 1) % aiconvSelectedModels.length;
            updateAIConvUI();
            continue;
        }

        // ── AI turn ──
        const loadingId = `aiconv-loading-${Date.now()}`;
        messagesContainer.insertAdjacentHTML('beforeend', `
            <div class="message ai-message" id="${loadingId}" style="border-left: 4px solid ${currentModel.color};">
                <div class="message-header">
                    <span class="message-role" style="color: ${currentModel.color};">🎭 ${currentModel.name} <span style="font-size:0.8em; opacity:0.7;">(${currentModel.id})</span></span>
                </div>
                <div class="message-content">
                    <div class="typing-indicator"><span></span><span></span><span></span></div>
                </div>
            </div>
        `);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        try {
            const turnMessages = [...aiconvState.messageHistory];
            turnMessages.push({
                role: 'system',
                content: `You are now speaking as ${currentModel.name}. Reply exclusively as ${currentModel.name}. Do not break character. Do not include your name at the start of your message.`
            });

            const res = await fetch('/api/arena/aiconv/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model_id: currentModel.id, messages: turnMessages })
            });

            const data = await res.json();
            const loadingEl = document.getElementById(loadingId);
            if (loadingEl) loadingEl.remove();

            if (!res.ok || !aiconvState.isRunning) {
                if (aiconvState.isRunning) { console.error('AI Conv Error:', data.detail || 'Unknown error'); stopAIConv(); }
                break;
            }

            const responseText = data.response;
            aiconvState.messageHistory.push({
                role: 'assistant',
                name: currentModel.id.replace(/[^a-zA-Z0-9_-]/g, '').substring(0, 64),
                _displayName: currentModel.name,
                _color: currentModel.color,
                content: responseText
            });

            // Token / cost tracking
            if (data.usage) {
                const inTokens = data.usage.prompt_tokens || data.usage.prompt_token_count || 0;
                const outTokens = data.usage.completion_tokens || data.usage.candidates_token_count || 0;
                aiconvState.estInTokens += inTokens;
                aiconvState.estOutTokens += outTokens;

                if (typeof arenaAvailableModels !== 'undefined') {
                    const modelInfo = arenaAvailableModels.find(m => m.id === currentModel.id);
                    if (modelInfo) {
                        aiconvState.estCost += (inTokens / 1e6) * (modelInfo.input_cost_per_1m_tokens || 0)
                            + (outTokens / 1e6) * (modelInfo.output_cost_per_1m_tokens || 0);
                    }
                }
            }

            const htmlContent = (typeof marked !== 'undefined' && marked.parse) ? marked.parse(responseText) : escapeHtml(responseText);

            messagesContainer.insertAdjacentHTML('beforeend', `
                <div class="message ai-message" style="border-left: 4px solid ${currentModel.color}; background: var(--bg-tertiary);">
                    <div class="message-header">
                        <span class="message-role" style="color: ${currentModel.color}; font-weight: bold; font-size: 1.05rem;">🎭 ${currentModel.name}</span>
                        <span style="font-size: 0.75rem; color: var(--text-secondary); margin-left: 0.5rem;">(${currentModel.id})</span>
                    </div>
                    <div class="message-content markdown-body" style="padding-top: 0.5rem;">${htmlContent}</div>
                </div>
            `);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;

            aiconvState.totalTurnsCompleted++;
            aiconvState.currentTurnIndex = (aiconvState.currentTurnIndex + 1) % aiconvSelectedModels.length;
            updateAIConvUI();
            saveCurrentAIConv(); // auto-save after each AI turn

            if (aiconvState.totalTurnsCompleted < totalTarget()) {
                await new Promise(r => setTimeout(r, 1000));
            }

        } catch (err) {
            console.error('Turn execution failed:', err);
            const loadingEl = document.getElementById(loadingId);
            if (loadingEl) loadingEl.remove();
            stopAIConv();
            break;
        }
    }

    if (aiconvState.totalTurnsCompleted >= totalTarget() && aiconvState.isRunning) {
        stopAIConv(true);
    }
}

// ─── Conversation History ────────────────────────────────────────────────────

let aiconvCurrentId = null; // ID of the currently active (saved) conversation

async function loadAIConvHistory() {
    const list = document.getElementById('aiconv-conv-list');
    const empty = document.getElementById('aiconv-conv-empty');
    if (!list) return;

    try {
        const res = await fetch('/api/arena/aiconv/conversations');
        const data = await res.json();
        const convs = data.conversations || [];

        if (!convs.length) {
            list.innerHTML = '<div id="aiconv-conv-empty" style="font-size:0.8rem; color:var(--text-secondary); text-align:center; padding:0.5rem 0;">No saved conversations yet.</div>';
            return;
        }

        list.innerHTML = convs.map(c => `
            <div class="aiconv-hist-item ${c.id === aiconvCurrentId ? 'active' : ''}" data-id="${c.id}" title="${escapeHtml(c.topic || c.name)}">
                <div class="aiconv-hist-name" ondblclick="startAIConvRename('${c.id}', this)">${escapeHtml(c.name)}</div>
                <div class="aiconv-hist-meta">${c.message_count} msgs · ${c.participant_count} participants</div>
                <button class="aiconv-hist-delete" onclick="deleteAIConvConversation('${c.id}', event)" title="Delete">×</button>
            </div>
        `).join('');

        // Click to load
        list.querySelectorAll('.aiconv-hist-item').forEach(el => {
            el.addEventListener('click', (e) => {
                if (e.target.classList.contains('aiconv-hist-delete')) return;
                if (e.target.classList.contains('aiconv-hist-name') && e.detail === 2) return; // dblclick handled separately
                loadAIConvConversation(el.dataset.id);
            });
        });
    } catch (e) {
        console.error('Failed to load AI Conv history:', e);
    }
}

async function saveCurrentAIConv() {
    if (!aiconvState.messageHistory.length) return;

    const topicMatch = (aiconvState.messageHistory[0]?.content || '').match(/topic of this conversation is:\s*"?(.+?)(?:"|\.|\n)/i);
    const topic = topicMatch ? topicMatch[1].trim() : 'AI Conversation';
    const name = topic.length > 55 ? topic.slice(0, 52) + '…' : topic;

    const payload = {
        id:             aiconvCurrentId || undefined,
        name,
        topic,
        participants:   aiconvSelectedModels.map(m => ({
            name:    m.name, color: m.color, isHuman: m.isHuman || false,
            model:   m.isHuman ? null : m.id, personality: m.personality || null
        })),
        messageHistory: aiconvState.messageHistory,
        stats: {
            inTokens: aiconvState.estInTokens,
            outTokens: aiconvState.estOutTokens,
            cost: aiconvState.estCost
        }
    };

    try {
        const res  = await fetch('/api/arena/aiconv/conversations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!aiconvCurrentId) {
            aiconvCurrentId = data.id;
        }
        loadAIConvHistory(); // refresh list
    } catch (e) {
        console.error('Failed to save conversation:', e);
    }
}

async function loadAIConvConversation(id) {
    if (aiconvState.isRunning) {
        showToast('Stop the current conversation before loading another.', 'warn');
        return;
    }

    try {
        const res  = await fetch(`/api/arena/aiconv/conversations/${id}`);
        if (!res.ok) { showToast('Conversation not found.', 'error'); return; }
        const data = await res.json();

        // Restore state
        aiconvCurrentId             = data.id;
        aiconvState.messageHistory  = data.messageHistory || [];
        aiconvState.estInTokens     = data.stats?.inTokens  || 0;
        aiconvState.estOutTokens    = data.stats?.outTokens || 0;
        aiconvState.estCost         = data.stats?.cost      || 0;
        aiconvState.totalTurnsCompleted = aiconvState.messageHistory.filter(m => m.role !== 'system').length;
        aiconvState.maxTurnsPerModel    = parseInt(document.getElementById('aiconv-msg-count')?.value) || 5;
        aiconvState.currentTurnIndex    = aiconvState.totalTurnsCompleted % Math.max(1, (data.participants || []).length);

        // Restore participants
        aiconvSelectedModels = (data.participants || []).map(p => ({
            id:          p.model || 'human',
            name:        p.name,
            color:       p.color,
            personality: p.personality || '',
            isHuman:     p.isHuman || false
        }));
        renderAIConvChips();

        // Set topic input
        const topicEl = document.getElementById('aiconv-topic');
        if (topicEl) topicEl.value = data.topic || '';

        // Render messages
        _renderLoadedMessages(data.messageHistory, data.participants || []);

        // Show Continue button
        document.getElementById('aiconv-start-btn').disabled = false;
        document.getElementById('aiconv-pause-btn').disabled = true;
        document.getElementById('aiconv-stop-btn').disabled = true;

        const messagesContainer = document.getElementById('aiconv-messages');
        messagesContainer.insertAdjacentHTML('beforeend', `
            <div class="message system-message">
                <div class="message-content">
                    <strong>System:</strong> Conversation loaded — ${aiconvState.totalTurnsCompleted} messages restored.
                    <button id="aiconv-continue-btn" class="action-btn secondary" style="margin-left:1rem; padding:0.25rem 0.75rem; font-size:0.8rem;">
                        <i class="fas fa-play"></i> Continue
                    </button>
                </div>
            </div>
        `);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        updateAIConvUI();
        loadAIConvHistory(); // highlight active
        showToast(`Loaded: ${data.name}`, 'success', 1800);

    } catch (e) {
        console.error('Failed to load conversation:', e);
        showToast('Failed to load conversation.', 'error');
    }
}

async function deleteAIConvConversation(id, event) {
    event.stopPropagation();
    if (!confirm('Delete this conversation?')) return;
    try {
        await fetch(`/api/arena/aiconv/conversations/${id}`, { method: 'DELETE' });
        if (aiconvCurrentId === id) aiconvCurrentId = null;
        loadAIConvHistory();
        showToast('Conversation deleted.', 'success', 1500);
    } catch (e) {
        showToast('Failed to delete.', 'error');
    }
}

function startAIConvRename(id, nameEl) {
    const currentName = nameEl.textContent;
    const input = document.createElement('input');
    input.type  = 'text';
    input.value = currentName;
    input.className = 'term-input';
    input.style.cssText = 'width:100%; font-size:0.82rem; padding:0.15rem 0.4rem;';

    nameEl.replaceWith(input);
    input.focus();
    input.select();

    const commit = async () => {
        const newName = input.value.trim() || currentName;
        try {
            await fetch(`/api/arena/aiconv/conversations/${id}/name`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName })
            });
        } catch (e) { /* silent */ }
        loadAIConvHistory();
    };

    input.addEventListener('blur',    commit);
    input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); input.blur(); } if (e.key === 'Escape') { input.value = currentName; input.blur(); } });
}

function _renderLoadedMessages(history, participants) {
    const container = document.getElementById('aiconv-messages');
    if (!container) return;
    container.innerHTML = '';

    const partByName = {};
    for (const p of participants) partByName[p.name] = p;

    for (let i = 0; i < history.length; i++) {
        const msg = history[i];

        if (msg.role === 'system' && i === 0) {
            const topicMatch = msg.content.match(/topic of this conversation is:\s*"?(.+?)(?:"|\.|\n)/i);
            if (topicMatch) {
                container.insertAdjacentHTML('beforeend', `
                    <div class="message system-message">
                        <div class="message-content"><strong>System:</strong> Starting conversation on topic: "${escapeHtml(topicMatch[1].trim())}"</div>
                    </div>`);
            }
            continue;
        }
        if (msg.role === 'system') continue;

        if (msg.role === 'assistant') {
            const name    = msg._displayName || 'AI';
            const color   = msg._color || 'hsl(260,70%,65%)';
            const modelId = msg.name || '';
            const html    = (typeof marked !== 'undefined' && marked.parse) ? marked.parse(msg.content) : escapeHtml(msg.content);
            container.insertAdjacentHTML('beforeend', `
                <div class="message ai-message" style="border-left:4px solid ${color}; background:var(--bg-tertiary);">
                    <div class="message-header">
                        <span style="color:${color}; font-weight:bold; font-size:1.05rem;">🎭 ${escapeHtml(name)}</span>
                        ${modelId ? `<span style="font-size:0.75rem; color:var(--text-secondary); margin-left:0.5rem;">(${escapeHtml(modelId)})</span>` : ''}
                    </div>
                    <div class="message-content markdown-body" style="padding-top:0.5rem;">${html}</div>
                </div>`);
        } else if (msg.role === 'user') {
            const human = participants.find(p => p.isHuman && msg.content.startsWith(p.name + ':'));
            if (human) {
                const content = msg.content.slice(human.name.length + 1).trim();
                container.insertAdjacentHTML('beforeend', `
                    <div class="message" style="border-left:4px solid ${human.color}; background:rgba(0,180,255,0.06); padding:0.6rem 1rem; margin:0.3rem 0;">
                        <div class="message-header" style="margin-bottom:0.3rem;">
                            <span style="color:${human.color}; font-weight:bold;">👤 ${escapeHtml(human.name)}</span>
                        </div>
                        <div class="message-content">${escapeHtml(content)}</div>
                    </div>`);
            } else {
                const narratorMatch = msg.content.match(/^\[Narrator\/Observer\]:\s*(.*)/s);
                const content = narratorMatch ? narratorMatch[1] : msg.content;
                container.insertAdjacentHTML('beforeend', `
                    <div class="message" style="border-left:4px solid var(--primary); background:rgba(99,102,241,0.06); padding:0.6rem 1rem; margin:0.3rem 0;">
                        <div class="message-header" style="margin-bottom:0.3rem;">
                            <span style="color:var(--primary); font-weight:bold; font-size:0.9rem;">💬 You (injected)</span>
                        </div>
                        <div class="message-content">${escapeHtml(content)}</div>
                    </div>`);
            }
        }
    }
    container.scrollTop = container.scrollHeight;
}

function newAIConvConversation() {
    if (aiconvState.isRunning) { showToast('Stop the current conversation first.', 'warn'); return; }
    aiconvCurrentId = null;
    aiconvState.messageHistory  = [];
    aiconvState.totalTurnsCompleted = 0;
    aiconvState.estInTokens  = 0;
    aiconvState.estOutTokens = 0;
    aiconvState.estCost      = 0;

    const container = document.getElementById('aiconv-messages');
    if (container) container.innerHTML = `
        <div class="arena-placeholder" id="aiconv-placeholder">
            <span class="tab-icon" style="font-size:3rem;">🎭</span>
            <p>Select models, configure the topic, and start the conversation!</p>
        </div>`;

    const continueBtn = document.getElementById('aiconv-continue-btn');
    if (continueBtn) continueBtn.closest('.message')?.remove();

    document.getElementById('aiconv-topic').disabled = false;
    document.getElementById('aiconv-start-btn').disabled = false;
    updateAIConvUI();
    loadAIConvHistory();
}

// ─── Share / Export ──────────────────────────────────────────────────────────

async function _compressToBase64url(obj) {
    const json = JSON.stringify(obj);
    const bytes = new TextEncoder().encode(json);
    const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream('deflate-raw'));
    const buf = await new Response(stream).arrayBuffer();
    const u8 = new Uint8Array(buf);
    let bin = '';
    for (let i = 0; i < u8.length; i++) bin += String.fromCharCode(u8[i]);
    return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

async function shareAIConv() {
    if (!aiconvState.messageHistory.length) { showToast('Nothing to share yet.', 'warn'); return; }

    // Collect only the visible messages (skip the system prompt at index 0)
    const messages = [];
    const topicMatch = (aiconvState.messageHistory[0]?.content || '').match(/topic of this conversation is:\s*"?(.+?)(?:"|\.|\n)/i);
    const topic = topicMatch ? topicMatch[1].trim() : 'AI Conversation';

    // Rebuild rendered message list from history
    // We re-derive speaker info from aiconvSelectedModels
    // Index by both raw id AND the sanitized version used when storing msg.name
    const modelMap = {};
    for (const m of aiconvSelectedModels) {
        modelMap[m.id] = m;
        const sanitized = m.id.replace(/[^a-zA-Z0-9_-]/g, '').substring(0, 64);
        modelMap[sanitized] = m;
    }

    for (let i = 1; i < aiconvState.messageHistory.length; i++) {
        const msg = aiconvState.messageHistory[i];
        if (msg.role === 'system') continue; // skip per-turn system injections

        // Find matching participant by name prefix in content (human injections)
        let sender = null;
        let content = msg.content;

        if (msg.role === 'user') {
            // Could be human participant or injected comment
            const humanParticipant = aiconvSelectedModels.find(m => m.isHuman && content.startsWith(m.name + ':'));
            if (humanParticipant) {
                sender = humanParticipant;
                content = content.slice(humanParticipant.name.length + 1).trim();
            } else {
                // Injected narrator comment
                const narratorMatch = content.match(/^\[Narrator\/Observer\]:\s*(.*)/s);
                if (narratorMatch) {
                    sender = { name: 'You', color: 'hsl(200,70%,65%)', isHuman: true };
                    content = narratorMatch[1];
                } else {
                    sender = { name: 'You', color: 'hsl(200,70%,65%)', isHuman: true };
                }
            }
        } else {
            // AI assistant — prefer the display name stored directly on the entry
            if (msg._displayName) {
                sender = {
                    name: msg._displayName,
                    color: msg._color || 'hsl(260,70%,65%)',
                    id: msg.name || '',
                    isHuman: false
                };
            } else {
                // Legacy fallback: look up by sanitized model id
                const modelId = msg.name ? msg.name : null;
                sender = modelId ? modelMap[modelId] : null;
                if (!sender) sender = { name: 'AI', color: 'hsl(260,70%,65%)', id: '' };
            }
        }

        messages.push({
            name: sender.name,
            color: sender.color,
            content: content,
            isHuman: sender.isHuman || false,
            model: sender.isHuman ? null : (sender.id || null)
        });
    }

    if (!messages.length) { showToast('No messages to share yet.', 'warn'); return; }

    const payload = {
        v: 1,
        title: topic,
        topic: topic,
        created: new Date().toISOString(),
        participants: aiconvSelectedModels.map(m => ({
            name:        m.name,
            color:       m.color,
            isHuman:     m.isHuman || false,
            model:       m.isHuman ? null : m.id,
            personality: m.personality && m.personality.trim() ? m.personality.trim() : null
        })),
        stats: {
            inTokens: aiconvState.estInTokens,
            outTokens: aiconvState.estOutTokens,
            cost: aiconvState.estCost
        },
        messages
    };

    try {
        const encoded = await _compressToBase64url(payload);
        const url = `https://aethvion.com/c#${encoded}`;

        await navigator.clipboard.writeText(url);
        showToast('Share link copied to clipboard!', 'success');

        // Also show it in a small modal for convenience
        _showShareModal(url);
    } catch (err) {
        console.error('Share failed:', err);
        showToast('Failed to generate share link.', 'error');
    }
}

function _showShareModal(url) {
    const existing = document.getElementById('aiconv-share-modal');
    if (existing) existing.remove();

    document.body.insertAdjacentHTML('beforeend', `
        <div id="aiconv-share-modal" style="
            position:fixed; inset:0; background:rgba(0,0,0,0.65); z-index:9999;
            display:flex; align-items:center; justify-content:center; padding:1rem;">
            <div style="
                background:var(--bg-secondary); border:1px solid var(--border);
                border-radius:12px; padding:1.5rem; max-width:560px; width:100%;
                box-shadow:0 8px 40px rgba(0,0,0,0.5);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
                    <h3 style="margin:0; color:var(--primary); font-size:1rem;">
                        <i class="fas fa-share-nodes"></i> Share Conversation
                    </h3>
                    <span id="aiconv-share-modal-close" style="cursor:pointer; font-size:1.4rem; color:var(--text-secondary);">&times;</span>
                </div>
                <p style="font-size:0.82rem; color:var(--text-secondary); margin:0 0 0.75rem 0;">
                    This link contains the full conversation — no backend, no login required. Anyone with the link can view it.
                </p>
                <div style="display:flex; gap:0.5rem;">
                    <input id="aiconv-share-url-input" type="text" readonly value="${url}"
                        style="flex:1; font-size:0.75rem; padding:0.45rem 0.6rem; background:var(--bg-tertiary); border:1px solid var(--border); border-radius:6px; color:var(--text-primary); word-break:break-all;"
                        onclick="this.select()">
                    <button id="aiconv-share-copy-btn" class="action-btn primary" style="flex-shrink:0; padding:0.4rem 0.75rem; font-size:0.8rem;">
                        <i class="fas fa-copy"></i> Copy
                    </button>
                </div>
            </div>
        </div>
    `);

    document.getElementById('aiconv-share-modal-close').addEventListener('click', () => {
        document.getElementById('aiconv-share-modal')?.remove();
    });
    document.getElementById('aiconv-share-copy-btn').addEventListener('click', async () => {
        await navigator.clipboard.writeText(url);
        showToast('Copied!', 'success', 1200);
    });
    document.getElementById('aiconv-share-modal').addEventListener('click', e => {
        if (e.target.id === 'aiconv-share-modal') document.getElementById('aiconv-share-modal').remove();
    });
}

// ─── Stats UI ────────────────────────────────────────────────────────────────

function updateAIConvUI() {
    const totalTarget = aiconvState.maxTurnsPerModel * aiconvSelectedModels.length;

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('aiconv-in-tokens', formatNumber(aiconvState.estInTokens || 0));
    set('aiconv-out-tokens', formatNumber(aiconvState.estOutTokens || 0));
    set('aiconv-live-tokens', formatNumber((aiconvState.estInTokens || 0) + (aiconvState.estOutTokens || 0)));
    set('aiconv-live-cost', formatCost(aiconvState.estCost || 0));
    set('aiconv-progress', `${aiconvState.totalTurnsCompleted}/${totalTarget}`);

    // Show share button once there are messages
    const shareBtn = document.getElementById('aiconv-share-btn');
    if (shareBtn) shareBtn.style.display = aiconvState.totalTurnsCompleted > 0 ? '' : 'none';
}

// ─── Global Event Delegation ──────────────────────────────────────────────────

document.addEventListener('change', (e) => {
    // Arena Model Selector
    if (e.target && e.target.id === 'arena-model-add') {
        const modelId = e.target.value;
        if (modelId && typeof arenaSelectedModels !== 'undefined' && !arenaSelectedModels.includes(modelId)) {
            arenaSelectedModels.push(modelId);
            if (typeof renderArenaChips === 'function') renderArenaChips();
        }
        e.target.value = '';
    }

    // AI Conversations Model Selector
    if (e.target && e.target.id === 'aiconv-model-add') {
        const modelId = e.target.value;
        if (modelId && typeof aiconvSelectedModels !== 'undefined') {
            if (aiconvAvailableNames.length === 0) {
                aiconvAvailableNames = [...aiconvUsedNames];
                aiconvUsedNames = [];
            }
            const randIdx = Math.floor(Math.random() * aiconvAvailableNames.length);
            const pickedName = aiconvAvailableNames.splice(randIdx, 1)[0];
            aiconvUsedNames.push(pickedName);

            aiconvSelectedModels.push({
                id: modelId,
                name: pickedName,
                color: `hsl(${Math.floor(Math.random() * 360)}, 70%, 65%)`,
                personality: ''
            });

            if (typeof renderAIConvChips === 'function') renderAIConvChips();
        }
        e.target.value = '';
    }
});

document.addEventListener('click', (e) => {
    if (e.target && e.target.id === 'aiconv-start-btn') { if (typeof startAIConv === 'function') startAIConv(); }

    if (e.target && e.target.id === 'aiconv-pause-btn') { if (typeof togglePauseAIConv === 'function') togglePauseAIConv(); }

    if (e.target && e.target.id === 'aiconv-stop-btn') { if (typeof stopAIConv === 'function') stopAIConv(); }

    if (e.target && e.target.id === 'aiconv-add-self-btn') { if (typeof addHumanParticipant === 'function') addHumanParticipant(); }

    // Continue button is inserted dynamically — match by id
    if (e.target && e.target.id === 'aiconv-continue-btn') { if (typeof continueAIConv === 'function') continueAIConv(); }

    if (e.target && e.target.id === 'aiconv-share-btn')    { if (typeof shareAIConv           === 'function') shareAIConv(); }
    if (e.target && e.target.id === 'aiconv-new-conv-btn') { if (typeof newAIConvConversation  === 'function') newAIConvConversation(); }
});

// Load history when the AI Conversations tab is first activated
document.addEventListener('DOMContentLoaded', () => {
    // Delay slightly so the tab system has initialised
    setTimeout(loadAIConvHistory, 300);
});

// Also reload when the tab is switched to (for fresh lists)
document.addEventListener('click', (e) => {
    if (e.target && e.target.dataset && e.target.dataset.tab === 'aiconv') {
        loadAIConvHistory();
    }
}, true);
