/**
 * Misaka Cipher Companion - Persistence & History v1
 */

let misakaChatHistory = [];
let misakaMaxHistory = 6;
let isMisakaTyping = false;
let historyOffsetDays = 0;
const HISTORY_LIMIT_DAYS = 3;
let hasInitializedMisaka = false;
let currentMisakaMood = 'calm';

async function initializeMisakaCipher() {
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
        if (e.detail && e.detail.context_limit) {
            misakaMaxHistory = e.detail.context_limit;
            console.log("Misaka context limit updated to:", misakaMaxHistory);
        }
    });

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
        const msgDiv = createMessageElement(msg.role, msg.content);
        dayBlock.appendChild(msgDiv);
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
            .replace(/\[Emotion:\s*\w+\]/gi, '').trim();
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

        await addAssistantMessageTyped(data.response);

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

    let remainingText = fullText.replace(/<memory_update>[\s\S]*?<\/memory_update>/gi, '').trim();

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

    // Remove all existing mood classes
    layout.classList.remove('mood-calm', 'mood-happy', 'mood-intense', 'mood-reflective', 'mood-danger', 'mood-mystery');

    // Apply new mood
    layout.classList.add(`mood-${mood}`);

    // Update badge
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

        // Hide badge after 5 seconds
        clearTimeout(badge._hideTimer);
        badge._hideTimer = setTimeout(() => badge.classList.remove('visible'), 5000);
    }
}

window.initializeMisakaCipher = initializeMisakaCipher;
