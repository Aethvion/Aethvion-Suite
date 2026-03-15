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

function renderAIConvChips() {
    const container = document.getElementById('aiconv-model-chips');
    if (!container) return;

    container.innerHTML = aiconvSelectedModels.map((model, index) => `
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
        </div>
    `).join('');

    container.querySelectorAll('.aiconv-personality-input').forEach(ta => {
        ta.addEventListener('input', (e) => {
            const idx = e.target.dataset.index;
            if (aiconvSelectedModels[idx]) {
                aiconvSelectedModels[idx].personality = e.target.value;
            }
        });
    });
}

function removeAIConvModel(index) {
    if (aiconvState.isRunning && !aiconvState.isPaused) return;
    aiconvSelectedModels.splice(index, 1);
    renderAIConvChips();
}

async function startAIConv() {
    if (aiconvSelectedModels.length < 2) {
        showToast('Please select at least 2 models.', 'warn');
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
        baseSystem += `- ${m.name} [Model: ${m.id}]`;
        if (m.personality) baseSystem += `\n  Role/Personality: ${m.personality}`;
        baseSystem += "\n";
    }
    baseSystem += "\nPlease keep your responses concise, engaging, and stay in character.";

    // Reset State
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

    const messagesContainer = document.getElementById('aiconv-messages');
    messagesContainer.innerHTML = `
        <div class="message system-message">
            <div class="message-content">
                <strong>System:</strong> Starting conversation on topic: "${escapeHtml(topic)}"
            </div>
        </div>
    `;

    updateAIConvUI();

    // Start Loop
    runAIConvLoop();
}

function togglePauseAIConv() {
    aiconvState.isPaused = !aiconvState.isPaused;
    const pauseBtn = document.getElementById('aiconv-pause-btn');
    if (aiconvState.isPaused) {
        pauseBtn.innerHTML = '<i class="fas fa-play"></i> Resume';
    } else {
        pauseBtn.innerHTML = '<i class="fas fa-pause"></i> Pause';
        runAIConvLoop();
    }
}

function stopAIConv() {
    aiconvState.isRunning = false;
    aiconvState.isPaused = false;

    document.getElementById('aiconv-start-btn').disabled = false;
    document.getElementById('aiconv-pause-btn').disabled = true;
    document.getElementById('aiconv-stop-btn').disabled = true;
    document.getElementById('aiconv-topic').disabled = false;

    const messagesContainer = document.getElementById('aiconv-messages');
    messagesContainer.insertAdjacentHTML('beforeend', `
        <div class="message system-message">
            <div class="message-content">
                <strong>System:</strong> Conversation stopped.
            </div>
        </div>
    `);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

async function runAIConvLoop() {
    const totalTarget = aiconvState.maxTurnsPerModel * aiconvSelectedModels.length;

    while (aiconvState.isRunning && !aiconvState.isPaused && aiconvState.totalTurnsCompleted < totalTarget) {
        const currentModel = aiconvSelectedModels[aiconvState.currentTurnIndex];

        // Show loading marker
        const messagesContainer = document.getElementById('aiconv-messages');
        const loadingId = `aiconv-loading-${Date.now()}`;
        messagesContainer.insertAdjacentHTML('beforeend', `
            <div class="message ai-message" id="${loadingId}" style="border-left: 4px solid ${currentModel.color};">
                <div class="message-header">
                    <span class="message-role" style="color: ${currentModel.color};">🎭 ${currentModel.name} <span style="font-size:0.8em; opacity:0.7;">(${currentModel.id})</span></span>
                </div>
                <div class="message-content">
                    <div class="typing-indicator">
                        <span></span><span></span><span></span>
                    </div>
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

            // Hit backend
            const res = await fetch('/api/arena/aiconv/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model_id: currentModel.id,
                    messages: turnMessages
                })
            });

            const data = await res.json();

            // Remove loading msg
            const loadingEl = document.getElementById(loadingId);
            if (loadingEl) loadingEl.remove();

            if (!res.ok || !aiconvState.isRunning) {
                if (aiconvState.isRunning) {
                    console.error("AI Conv Error:", data.detail || 'Unknown error');
                    stopAIConv();
                }
                break;
            }

            // Append to history
            const responseText = data.response;
            aiconvState.messageHistory.push({
                role: 'assistant',
                name: currentModel.id.replace(/[^a-zA-Z0-9_-]/g, '').substring(0, 64),
                content: responseText
            });

            // Update Tokens & Cost
            if (data.usage) {
                const inTokens = data.usage.prompt_tokens || data.usage.prompt_token_count || 0;
                const outTokens = data.usage.completion_tokens || data.usage.candidates_token_count || 0;

                aiconvState.estInTokens += inTokens;
                aiconvState.estOutTokens += outTokens;

                let inCost = 0;
                let outCost = 0;
                if (typeof arenaAvailableModels !== 'undefined') {
                    const modelInfo = arenaAvailableModels.find(m => m.id === currentModel.id);
                    if (modelInfo) {
                        inCost = (inTokens / 1000000) * (modelInfo.input_cost_per_1m_tokens || 0);
                        outCost = (outTokens / 1000000) * (modelInfo.output_cost_per_1m_tokens || 0);
                    }
                }
                aiconvState.estCost += (inCost + outCost);
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

            // Small delay between turns for readability
            if (aiconvState.totalTurnsCompleted < totalTarget) {
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

    if (aiconvState.totalTurnsCompleted >= totalTarget && aiconvState.isRunning) {
        stopAIConv();
        const messagesContainer = document.getElementById('aiconv-messages');
        messagesContainer.insertAdjacentHTML('beforeend', `
            <div class="message system-message">
                <div class="message-content">
                    <strong>System:</strong> Conversation completed successfully!
                </div>
            </div>
        `);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
}

function updateAIConvUI() {
    const totalTarget = aiconvState.maxTurnsPerModel * aiconvSelectedModels.length;

    // Live Tracker Detailed Stats
    const inTokensEl = document.getElementById('aiconv-in-tokens');
    const outTokensEl = document.getElementById('aiconv-out-tokens');
    const liveTokensEl = document.getElementById('aiconv-live-tokens');
    const liveCostEl = document.getElementById('aiconv-live-cost');
    const progressEl = document.getElementById('aiconv-progress');

    if (inTokensEl) inTokensEl.textContent = formatNumber(aiconvState.estInTokens || 0);
    if (outTokensEl) outTokensEl.textContent = formatNumber(aiconvState.estOutTokens || 0);
    if (liveTokensEl) liveTokensEl.textContent = formatNumber((aiconvState.estInTokens || 0) + (aiconvState.estOutTokens || 0));
    if (liveCostEl) liveCostEl.textContent = formatCost(aiconvState.estCost || 0);
    if (progressEl) progressEl.textContent = `${aiconvState.totalTurnsCompleted}/${totalTarget}`;
}

// ===== Global Event Delegation for Dynamic Dropdowns =====
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

            const hue = Math.floor(Math.random() * 360);
            const color = `hsl(${hue}, 70%, 65%)`;

            aiconvSelectedModels.push({
                id: modelId,
                name: pickedName,
                color: color,
                personality: ''
            });

            if (typeof renderAIConvChips === 'function') renderAIConvChips();
        }
        e.target.value = '';
    }
});

// Global Click Delegation for Dynamic Buttons
document.addEventListener('click', (e) => {
    if (e.target && e.target.id === 'aiconv-start-btn') {
        if (typeof startAIConv === 'function') startAIConv();
    }
    if (e.target && e.target.id === 'aiconv-pause-btn') {
        if (typeof togglePauseAIConv === 'function') togglePauseAIConv();
    }
    if (e.target && e.target.id === 'aiconv-stop-btn') {
        if (typeof stopAIConv === 'function') stopAIConv();
    }
});
