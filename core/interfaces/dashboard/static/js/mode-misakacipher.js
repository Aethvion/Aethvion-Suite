/**
 * Misaka Cipher Companion - Persistence & History v1
 */

let misakaChatHistory = [];
let misakaMaxHistory = 6;
let misakaTypingSpeed = 20;
let isMisakaTyping = false;
let historyOffsetDays = 0;
const HISTORY_LIMIT_DAYS = 3;
let hasInitializedMisaka = false;
let currentMisakaMood = 'calm';

async function initializeMisakaCipher() {
    // Always deliver any queued proactive message when switching to this tab
    deliverQueuedProactiveMessage();

    if (hasInitializedMisaka) {
        console.log("Misaka Cipher already active, skipping initialization.");
        return;
    }
    console.log("Initializing Misaka Cipher Companion...");

    const chatMessages = document.getElementById('misaka-chat-messages');
    const chatInput = document.getElementById('misaka-chat-input');
    const sendBtn = document.getElementById('send-misaka-msg');

    if (!chatMessages || !chatInput || !sendBtn) return;

    // 1. Add "Load More" button at the top if it doesn't exist
    if (!document.getElementById('misaka-load-more-btn')) {
        const loadMoreBtn = document.createElement('button');
        loadMoreBtn.id = 'misaka-load-more-btn';
        loadMoreBtn.className = 'load-more-btn';
        loadMoreBtn.textContent = "Load Previous Conversations";
        loadMoreBtn.style.display = 'none';
        loadMoreBtn.onclick = () => loadMoreHistory();
        chatMessages.prepend(loadMoreBtn);
    }

    // 1b. Add mood badge to companion layout
    const layout = document.querySelector('.companion-layout');
    if (layout && !document.getElementById('misaka-mood-badge')) {
        const badge = document.createElement('div');
        badge.id = 'misaka-mood-badge';
        badge.className = 'mood-badge';
        const avatarView = layout.querySelector('.companion-avatar-view');
        if (avatarView) avatarView.style.position = 'relative';
        if (avatarView) avatarView.appendChild(badge);
        else layout.appendChild(badge);
    }
    // Apply default mood
    updateMisakaMood('calm');

    // 2. Clear current messages (except load more) for fresh init
    const blocks = chatMessages.querySelectorAll('.history-day-block');
    blocks.forEach(b => b.remove());

    // 3. Load expressions
    await loadExpressions();

    // 4. Load Memory
    await refreshMisakaMemory();

    // 5. Load Recent History (Last 3 days)
    historyOffsetDays = 0;
    // Update local context limit from prefs
    misakaMaxHistory = typeof prefs !== 'undefined' ? prefs.get('misakacipher.context_limit', 6) : 6;

    await loadHistory(0, 3, true);

    hasInitializedMisaka = true;

    // 6. Listen for changes from settings page
    window.addEventListener('misakaSettingsUpdated', (e) => {
        if (e.detail && e.detail.context_limit) misakaMaxHistory = e.detail.context_limit;
        if (e.detail && e.detail.typing_speed !== undefined) misakaTypingSpeed = e.detail.typing_speed;
    });

    // 7. Cache typing speed from prefs
    try {
        const prefsRes2 = await fetch('/api/preferences');
        if (prefsRes2.ok) {
            const prefsData2 = await prefsRes2.json();
            if (prefsData2.misakacipher && prefsData2.misakacipher.typing_speed !== undefined) {
                misakaTypingSpeed = prefsData2.misakacipher.typing_speed;
            }
        }
    } catch (e) { }

    // 7. Start proactive scheduler (runs once, sets up timers)
    startProactiveScheduler();

    // Event Listeners
    sendBtn.onclick = () => sendMisakaMessage();
    chatInput.onkeydown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMisakaMessage();
        }
    };
}

async function loadHistory(offset = 0, limit = 3, isInitial = false) {
    try {
        const response = await fetch(`/api/misakacipher/history?offset_days=${offset}&limit_days=${limit}`);
        const data = await response.json();

        const chatMessages = document.getElementById('misaka-chat-messages');
        const loadMoreBtn = document.getElementById('misaka-load-more-btn');

        if (loadMoreBtn) {
            loadMoreBtn.style.display = data.has_more ? 'block' : 'none';
        }

        if (data.history && data.history.length > 0) {
            const oldHeight = chatMessages.scrollHeight;

            // data.history is [newestDay, ..., oldestDay]
            // We want to render them such that the OLDEST day is at the TOP of the loaded batch
            // but the batch itself is PREPENDED to the current view.

            // To maintain order, we iterate backwards and prepend
            for (let i = data.history.length - 1; i >= 0; i--) {
                const day = data.history[i];
                renderDayHistory(day, isInitial);
            }

            // Sync Context Window: If initial load, take newest messages for LLM context
            if (isInitial && data.history.length > 0) {
                const mostRecentDay = data.history[0]; // newest is first
                if (mostRecentDay && mostRecentDay.messages) {
                    misakaChatHistory = mostRecentDay.messages.slice(-misakaMaxHistory).map(m => ({
                        role: m.role,
                        content: m.content
                    }));
                }
            }

            if (!isInitial) {
                chatMessages.scrollTop = chatMessages.scrollHeight - oldHeight;
            } else {
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }

            historyOffsetDays += data.history.length;
        }
    } catch (e) {
        console.error("Error loading chat history:", e);
    }
}

async function loadMoreHistory() {
    await loadHistory(historyOffsetDays, HISTORY_LIMIT_DAYS, false);
}

function renderDayHistory(day, isInitial) {
    const chatMessages = document.getElementById('misaka-chat-messages');
    const loadMoreBtn = document.getElementById('misaka-load-more-btn');

    const dayBlock = document.createElement('div');
    dayBlock.className = 'history-day-block';

    const separator = document.createElement('div');
    separator.className = 'date-separator';
    separator.innerHTML = `<span>${formatDate(day.date)}</span>`;
    dayBlock.appendChild(separator);

    day.messages.forEach(msg => {
        // Handle [msg_break] in history by creating multiple bubbles
        const parts = msg.content.split(/\[msg_break\]/i);
        parts.forEach(part => {
            if (part.trim()) {
                const msgDiv = createMessageElement(msg.role, part.trim());
                dayBlock.appendChild(msgDiv);
            }
        });
    });

    if (isInitial) {
        chatMessages.appendChild(dayBlock);
    } else {
        // Prepend after load more button
        if (loadMoreBtn && loadMoreBtn.nextSibling) {
            chatMessages.insertBefore(dayBlock, loadMoreBtn.nextSibling);
        } else {
            chatMessages.prepend(dayBlock);
        }
    }
}

function createMessageElement(role, text) {
    const div = document.createElement('div');
    div.className = `chat-message ${role}`;

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    if (role === 'assistant') {
        const cleanText = text.replace(/<memory_update>[\s\S]*?<\/memory_update>/gi, '')
            .replace(/\[Emotion:\s*\w+\]/gi, '')
            .replace(/\[tool:[\w_]+[^\]]*\]/gi, '')
            .replace(/\[msg_break\]/gi, '')
            .trim();
        bubble.innerHTML = renderMarkdown(cleanText);
    } else {
        bubble.textContent = text;
    }

    div.appendChild(bubble);
    return div;
}

function formatDate(dateStr) {
    const date = new Date(dateStr);
    const now = new Date();
    const yest = new Date();
    yest.setDate(now.getDate() - 1);

    if (date.toDateString() === now.toDateString()) return "Today";
    if (date.toDateString() === yest.toDateString()) return "Yesterday";

    return date.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
}

async function loadExpressions() {
    try {
        const response = await fetch('/api/misakacipher/expressions');
        const expressions = await response.json();
    } catch (e) {
        console.error("Error loading expressions:", e);
    }
}

async function refreshMisakaMemory() {
    try {
        const response = await fetch('/api/misakacipher/memory');
        const data = await response.json();

        const baseViewer = document.getElementById('misaka-base-info-viewer');
        const dynamicViewer = document.getElementById('misaka-dynamic-memory-viewer');

        if (baseViewer) baseViewer.textContent = JSON.stringify(data.base_info, null, 4);
        if (dynamicViewer) dynamicViewer.textContent = JSON.stringify(data.memory, null, 4);
    } catch (e) {
        console.error("Error refreshing Misaka memory:", e);
    }
}

async function sendMisakaMessage() {
    if (isMisakaTyping) return;

    const chatInput = document.getElementById('misaka-chat-input');
    const text = chatInput.value.trim();
    if (!text) return;

    addAssistantMessageStatic('user', text);
    chatInput.value = '';

    const payload = {
        message: text,
        history: misakaChatHistory
    };

    const statusLine = document.getElementById('misaka-status-line');
    if (statusLine) statusLine.textContent = "Processing neural paths...";

    try {
        const response = await fetch('/api/misakacipher/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "API Error");
        }

        const data = await response.json();

        misakaChatHistory.push({ role: 'user', content: text });
        misakaChatHistory.push({ role: 'assistant', content: data.response });

        if (misakaChatHistory.length > misakaMaxHistory) {
            misakaChatHistory = misakaChatHistory.slice(-misakaMaxHistory);
        }

        // Apply mood environment
        if (data.mood) updateMisakaMood(data.mood);

        // Deliver messages — supports multi-message via data.responses
        const parts = (data.responses && data.responses.length > 0) ? data.responses : [data.response];
        for (let i = 0; i < parts.length; i++) {
            if (i > 0) await new Promise(r => setTimeout(r, 700));
            await addAssistantMessageTyped(parts[i]);
        }

        if (data.memory_updated || data.synthesis_ran) {
            await refreshMisakaMemory();
            if (data.synthesis_ran) {
                if (statusLine) statusLine.textContent = "Memory synthesis complete. Neural patterns updated.";
            } else {
                if (statusLine) statusLine.textContent = "Memory synchronized.";
            }
            setTimeout(() => { if (statusLine) statusLine.textContent = "Neural core engaged."; }, 4000);
        } else {
            if (statusLine) statusLine.textContent = "Neural core engaged.";
        }

    } catch (e) {
        console.error("Chat Error:", e);
        addAssistantMessageStatic('assistant', "I encountered a neural desync. Please try again.");
    }
}

function addAssistantMessageStatic(role, text) {
    const container = document.getElementById('misaka-chat-messages');
    if (!container) return;

    const div = createMessageElement(role, text);
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function renderMarkdown(text) {
    if (typeof marked !== 'undefined') {
        if (typeof marked.parse === 'function') return marked.parse(text);
        if (typeof marked === 'function') return marked(text);
    }
    return text.replace(/\n/g, '<br>');
}

async function addAssistantMessageTyped(fullText) {
    const container = document.getElementById('misaka-chat-messages');
    if (!container) return;

    isMisakaTyping = true;

    const div = document.createElement('div');
    div.className = 'chat-message assistant';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble typing-glow';
    div.appendChild(bubble);
    container.appendChild(div);

    let remainingText = fullText
        .replace(/<memory_update>[\s\S]*?<\/memory_update>/gi, '')
        .replace(/\[tool:[\w_]+[^\]]*\]/gi, '')
        .replace(/\[msg_break\]/gi, '')
        .trim();

    let triggers = [];
    const emotionRegex = /\[Emotion:\s*(\w+)\]/gi;
    let match;
    let cleanText = "";
    let lastIndex = 0;

    while ((match = emotionRegex.exec(remainingText)) !== null) {
        cleanText += remainingText.substring(lastIndex, match.index);
        triggers.push({ pos: cleanText.length, emotion: match[1].toLowerCase() });
        lastIndex = emotionRegex.lastIndex;
    }
    cleanText += remainingText.substring(lastIndex);

    let speed = 20;
    try {
        const res = await fetch('/api/preferences');
        if (res.ok) {
            const prefs = await res.json();
            if (prefs.misakacipher && prefs.misakacipher.typing_speed !== undefined) {
                speed = prefs.misakacipher.typing_speed;
            }
        }
    } catch (e) { }

    const delay = Math.max(5, 100 - speed);

    if (speed >= 98) {
        if (triggers.length > 0) updateMisakaExpression(triggers[triggers.length - 1].emotion);
        bubble.innerHTML = renderMarkdown(cleanText);
        container.scrollTop = container.scrollHeight;
        isMisakaTyping = false;
        return;
    }

    let currentVisibleText = "";
    const characters = Array.from(cleanText);
    let triggerIdx = 0;

    for (let i = 0; i < characters.length; i++) {
        while (triggerIdx < triggers.length && triggers[triggerIdx].pos <= i) {
            updateMisakaExpression(triggers[triggerIdx].emotion);
            triggerIdx++;
        }
        currentVisibleText += characters[i];
        bubble.innerHTML = renderMarkdown(currentVisibleText);
        container.scrollTop = container.scrollHeight;
        await new Promise(r => setTimeout(r, delay));
    }

    while (triggerIdx < triggers.length) {
        updateMisakaExpression(triggers[triggerIdx].emotion);
        triggerIdx++;
    }

    bubble.innerHTML = renderMarkdown(cleanText);
    bubble.classList.remove('typing-glow');
    container.scrollTop = container.scrollHeight;
    isMisakaTyping = false;
}

function updateMisakaExpression(expression) {
    const img = document.getElementById('misaka-expression-img');
    if (!img) return;
    const path = `/static/misakacipher/expressions/misakacipher_${expression}.png`;
    const tempImg = new Image();
    tempImg.onload = () => { img.src = path; };
    tempImg.onerror = () => { img.src = "/static/misakacipher/expressions/misakacipher_default.png"; };
    tempImg.src = path;
}

function updateMisakaMood(mood) {
    if (mood === currentMisakaMood) return;
    currentMisakaMood = mood;

    const layout = document.querySelector('.companion-layout');
    if (!layout) return;

    layout.classList.remove('mood-calm', 'mood-happy', 'mood-intense', 'mood-reflective', 'mood-danger', 'mood-mystery');
    layout.classList.add(`mood-${mood}`);

    const badge = document.getElementById('misaka-mood-badge');
    if (badge) {
        const moodLabels = {
            calm: '◈ Calm',
            happy: '✦ Happy',
            intense: '⚡ Intense',
            reflective: '◌ Reflective',
            danger: '⚠ Alert',
            mystery: '✧ Mystery'
        };
        badge.textContent = moodLabels[mood] || mood;
        badge.classList.add('visible');
        clearTimeout(badge._hideTimer);
        badge._hideTimer = setTimeout(() => badge.classList.remove('visible'), 5000);
    }
}

// ===== PROACTIVE MESSAGING SYSTEM =====
let _proactiveSessionTimer = null;
let _queuedProactiveMessage = null; // { response, mood } — pending delivery when user opens Misaka tab

function _randomBetween(min, max) {
    return Math.random() * (max - min) + min;
}

async function _getHoursSinceLastMessage() {
    try {
        const res = await fetch('/api/misakacipher/history?offset_days=0&limit_days=1');
        if (!res.ok) return null;
        const data = await res.json();
        if (!data.history || !data.history[0] || !data.history[0].messages) return null;
        const msgs = data.history[0].messages;
        let lastTs = null;
        for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].timestamp) { lastTs = msgs[i].timestamp; break; }
        }
        if (!lastTs) return null;
        const last = new Date(lastTs.replace(' ', 'T'));
        const now = new Date();
        return (now - last) / (1000 * 3600);
    } catch { return null; }
}

async function startProactiveScheduler() {
    // Read prefs
    const res = await fetch('/api/preferences');
    if (!res.ok) return;
    const p = await res.json();
    const mc = p.misakacipher || {};

    const enabled = mc.proactive_enabled !== false;
    const startupHours = mc.startup_trigger_hours ?? 4;
    const startupChance = mc.startup_chance ?? 75;
    const delayMin = mc.startup_delay_min ?? 10;
    const delayMax = mc.startup_delay_max ?? 45;
    const intervalMin = mc.session_interval_min ?? 45;
    const intervalMax = mc.session_interval_max ?? 90;
    const sessionChance = mc.session_chance ?? 60;

    if (!enabled) return;

    // --- Startup check ---
    const hoursSince = await _getHoursSinceLastMessage();
    if (hoursSince !== null && hoursSince >= startupHours) {
        if (Math.random() * 100 < startupChance) {
            const delay = _randomBetween(delayMin, delayMax) * 1000;
            setTimeout(() => triggerProactiveMessage('startup', hoursSince), delay);
        }
    }

    // --- Session check-in loop ---
    function scheduleNextSession() {
        const interval = _randomBetween(intervalMin, intervalMax) * 60000;
        _proactiveSessionTimer = setTimeout(async () => {
            if (Math.random() * 100 < sessionChance) {
                await triggerProactiveMessage('session', 0);
            }
            scheduleNextSession();
        }, interval);
    }
    scheduleNextSession();
}

async function triggerProactiveMessage(trigger, hoursSince) {
    try {
        const res = await fetch('/api/misakacipher/initiate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trigger, hours_since_last: hoursSince })
        });
        if (!res.ok) return;
        const data = await res.json();

        // Check if Misaka tab is active
        const misakaPanel = document.getElementById('misaka-companion-panel');
        const isMisakaVisible = misakaPanel && !misakaPanel.classList.contains('hidden') &&
            misakaPanel.offsetParent !== null;

        if (isMisakaVisible) {
            // Deliver directly
            if (data.mood) updateMisakaMood(data.mood);
            await addAssistantMessageTyped(data.response);
            misakaChatHistory.push({ role: 'assistant', content: data.response });
            if (misakaChatHistory.length > misakaMaxHistory) {
                misakaChatHistory = misakaChatHistory.slice(-misakaMaxHistory);
            }
        } else {
            // Queue and show popup
            _queuedProactiveMessage = data;
            const prefRes = await fetch('/api/preferences');
            const prefs = await prefRes.json();
            const popupEnabled = (prefs.misakacipher || {}).proactive_popup !== false;
            if (popupEnabled) showMisakaPopup(data.response);
        }
    } catch (e) {
        console.warn('Proactive message failed:', e);
    }
}

function showMisakaPopup(text) {
    // Remove any existing popup
    const existing = document.getElementById('misaka-proactive-popup');
    if (existing) existing.remove();

    const popup = document.createElement('div');
    popup.id = 'misaka-proactive-popup';
    popup.className = 'misaka-proactive-popup';

    // Clean display text (strip emotion and mood tags)
    const cleanText = text.replace(/\[Emotion:\s*\w+\]/gi, '').replace(/\[Mood:\s*\w+\]/gi, '').trim();
    const preview = cleanText.length > 120 ? cleanText.slice(0, 117) + '…' : cleanText;

    const avatarSrc = document.getElementById('misaka-expression-img')?.src
        || '/static/misakacipher/expressions/misakacipher_default.png';

    popup.innerHTML = `
        <img class="popup-avatar" src="${avatarSrc}" alt="Misaka">
        <div class="popup-body">
            <div class="popup-name">Misaka Cipher</div>
            <div class="popup-text">${preview}</div>
        </div>
        <button class="popup-dismiss" title="Dismiss">✕</button>
        <div class="popup-progress"></div>
    `;

    // Click popup → navigate to Misaka tab
    const navigateToMisaka = () => {
        dismissMisakaPopup();
        if (typeof switchMainTab === 'function') switchMainTab('misaka-cipher');
    };
    popup.querySelector('.popup-body').addEventListener('click', navigateToMisaka);
    popup.querySelector('.popup-avatar').addEventListener('click', navigateToMisaka);

    // Dismiss button
    popup.querySelector('.popup-dismiss').addEventListener('click', (e) => {
        e.stopPropagation();
        dismissMisakaPopup();
    });

    document.body.appendChild(popup);
    // Animate in
    requestAnimationFrame(() => requestAnimationFrame(() => popup.classList.add('show')));

    // Auto-dismiss after 12s
    popup._dismissTimer = setTimeout(() => dismissMisakaPopup(), 12000);
}

function dismissMisakaPopup() {
    const popup = document.getElementById('misaka-proactive-popup');
    if (!popup) return;
    clearTimeout(popup._dismissTimer);
    popup.classList.remove('show');
    setTimeout(() => popup.remove(), 500);
}

// Deliver queued message when user returns to Misaka tab
function deliverQueuedProactiveMessage() {
    if (!_queuedProactiveMessage) return;
    const data = _queuedProactiveMessage;
    _queuedProactiveMessage = null;
    dismissMisakaPopup();

    setTimeout(async () => {
        if (data.mood) updateMisakaMood(data.mood);
        await addAssistantMessageTyped(data.response);
        misakaChatHistory.push({ role: 'assistant', content: data.response });
        if (misakaChatHistory.length > misakaMaxHistory) {
            misakaChatHistory = misakaChatHistory.slice(-misakaMaxHistory);
        }
    }, 800);
}

window.initializeMisakaCipher = initializeMisakaCipher;
window.deliverQueuedProactiveMessage = deliverQueuedProactiveMessage;
