/**
 * Aethvion Suite - Lyra Companion
 * CSS-based avatar — expressions controlled via class switching
 */

// ── Global State ──────────────────────────────────────────────────────────────
let lyraChatHistory = [];
let lyraMaxHistory = 20;
let lyraTypingSpeed = 20;  // fallback; overridden by global companions speed
let isLyraTyping = false;
let lyraHistoryOffsetDays = 0;
const LYRA_HISTORY_LIMIT_DAYS = 3;
let hasInitializedLyra = false;
let currentLyraMood = 'warm';
let currentLyraExpression = 'joyful';

function _lyraLoadTypingSpeed() {
    if (typeof window.prefs !== 'undefined') {
        lyraTypingSpeed = window.prefs.get('companions.global.typing_speed', 20);
    }
}
_lyraLoadTypingSpeed();

// Update speed when global companion setting changes
window.addEventListener('companionSettingsUpdated', (e) => {
    if (e.detail && e.detail.typing_speed !== undefined) {
        lyraTypingSpeed = parseInt(e.detail.typing_speed, 10);
    }
});

// ── Expression map ────────────────────────────────────────────────────────────

const LYRA_EXPRESSION_MAP = {
    // direct
    'joyful':      'joyful',
    'inspired':    'inspired',
    'dreamy':      'dreamy',
    'creative':    'creative',
    'cheerful':    'cheerful',
    'melancholic': 'melancholic',
    'excited':     'excited',
    'peaceful':    'peaceful',
    'surprised':   'surprised',
    'thinking':    'thinking',
    'blushing':    'blushing',
    'wink':        'wink',
    // aliases
    'happy':       'joyful',
    'joy':         'joyful',
    'glad':        'cheerful',
    'bright':      'cheerful',
    'inspire':     'inspired',
    'dream':       'dreamy',
    'drift':       'dreamy',
    'create':      'creative',
    'creating':    'creative',
    'sad':         'melancholic',
    'melancholy':  'melancholic',
    'blue':        'melancholic',
    'wistful':     'melancholic',
    'excited':     'excited',
    'thrill':      'excited',
    'calm':        'peaceful',
    'still':       'peaceful',
    'peace':       'peaceful',
    'surprise':    'surprised',
    'shock':       'surprised',
    'think':       'thinking',
    'wonder':      'thinking',
    'hm':          'thinking',
    'blush':       'blushing',
    'shy':         'blushing',
    'playful':     'wink',
    'default':     'joyful',
};

// ── Mood label map ────────────────────────────────────────────────────────────

const LYRA_MOOD_LABELS = {
    ethereal:    '✦ Ethereal',
    warm:        '♡ Warm',
    melancholic: '◌ Melancholic',
    inspired:    '✧ Inspired',
    playful:     '♪ Playful',
    serene:      '◈ Serene',
};

// ── Status messages per expression ───────────────────────────────────────────

const LYRA_STATUS_BY_EXPRESSION = {
    joyful:      "I'm here — what shall we discover today?",
    inspired:    "Something just arrived — follow this thread with me...",
    dreamy:      "There's a thought forming... slowly...",
    creative:    "Ideas are connecting. Hold on — this is interesting.",
    cheerful:    "A good moment to be in.",
    melancholic: "Some things are worth sitting with for a while.",
    excited:     "Oh — oh this is something. I can't stop now.",
    peaceful:    "It's quiet here. That's a good thing.",
    surprised:   "Oh! I didn't expect that.",
    thinking:    "Somewhere between the question and the answer...",
    blushing:    "That was — thank you.",
    wink:        "I have a feeling about this.",
};

// ── Initializer ───────────────────────────────────────────────────────────────

async function initializeLyra() {
    if (hasInitializedLyra) {
        console.log('[Lyra] Already initialized.');
        return;
    }
    console.log('[Lyra] Initializing...');

    const chatMessages = document.getElementById('lyra-chat-messages');
    const chatInput    = document.getElementById('lyra-chat-input');
    const sendBtn      = document.getElementById('send-lyra-msg');

    if (!chatMessages || !chatInput || !sendBtn) {
        console.warn('[Lyra] Required DOM elements not found.');
        return;
    }

    // Load-more button
    if (!document.getElementById('lyra-load-more-btn')) {
        const loadMoreBtn = document.createElement('button');
        loadMoreBtn.id = 'lyra-load-more-btn';
        loadMoreBtn.className = 'load-more-btn';
        loadMoreBtn.textContent = 'Load Previous Conversations';
        loadMoreBtn.style.display = 'none';
        loadMoreBtn.onclick = () => lyraLoadMoreHistory();
        chatMessages.prepend(loadMoreBtn);
    }

    // Restore last state
    const lastMood = localStorage.getItem('lyra_last_mood') || 'warm';
    updateLyraMood(lastMood);
    const lastExpr = localStorage.getItem('lyra_last_expression') || 'joyful';
    updateLyraExpression(lastExpr);

    // Clear stale messages
    chatMessages.querySelectorAll('.history-day-block').forEach(b => b.remove());

    // Load history
    lyraHistoryOffsetDays = 0;
    lyraMaxHistory = typeof prefs !== 'undefined' ? prefs.get('lyra.context_limit', 6) : 6;
    await lyraLoadHistory(0, LYRA_HISTORY_LIMIT_DAYS, true);

    // Wire up send button and Enter key
    sendBtn.addEventListener('click', sendLyraMessage);
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendLyraMessage();
        }
    });

    // Auto-resize textarea
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    });

    // Wire settings button → Companions settings subtab
    const lyraSettingsBtn = document.getElementById('lyra-settings-btn');
    if (lyraSettingsBtn) {
        lyraSettingsBtn.addEventListener('click', () => {
            if (typeof ensureTabAndSubTab === 'function') {
                ensureTabAndSubTab('settings', 'companions');
            }
        });
    }

    hasInitializedLyra = true;
    console.log('[Lyra] Initialization complete.');
}

// ── Expression update ─────────────────────────────────────────────────────────

function updateLyraExpression(expression) {
    const avatar = document.getElementById('lyra-avatar');
    if (!avatar) return;

    const key = (expression || 'joyful').toLowerCase().trim();
    const cssClass = LYRA_EXPRESSION_MAP[key] || 'joyful';

    // Remove all existing expression classes
    const classes = Array.from(avatar.classList);
    classes.filter(c => c.startsWith('lyra-expr-')).forEach(c => avatar.classList.remove(c));

    avatar.classList.add(`lyra-expr-${cssClass}`);
    currentLyraExpression = cssClass;

    // Update status line
    const statusLine = document.getElementById('lyra-status-line');
    if (statusLine) {
        statusLine.textContent = LYRA_STATUS_BY_EXPRESSION[cssClass] ||
            "Listening — what's on your mind?";
    }

    localStorage.setItem('lyra_last_expression', key);
}

// ── Mood update ───────────────────────────────────────────────────────────────

function updateLyraMood(mood) {
    if (mood === currentLyraMood) return;
    currentLyraMood = mood;

    const layout = document.querySelector('.lyra-layout');
    if (!layout) return;

    const moods = ['mood-ethereal', 'mood-warm', 'mood-melancholic', 'mood-inspired', 'mood-playful', 'mood-serene'];
    moods.forEach(m => layout.classList.remove(m));
    layout.classList.add(`mood-${mood}`);

    const badge = document.getElementById('lyra-mood-badge');
    if (badge) {
        badge.textContent = LYRA_MOOD_LABELS[mood] || mood;
        badge.classList.add('visible');
        clearTimeout(badge._hideTimer);
        badge._hideTimer = setTimeout(() => badge.classList.remove('visible'), 5000);
    }

    localStorage.setItem('lyra_last_mood', mood);
}

// ── History loading ───────────────────────────────────────────────────────────

async function lyraLoadHistory(offsetDays, limitDays, isInitial) {
    try {
        const res = await fetch(`/api/lyra/history?offset_days=${offsetDays}&limit_days=${limitDays}`);
        if (!res.ok) return;
        const data = await res.json();

        const chatMessages = document.getElementById('lyra-chat-messages');
        const loadMoreBtn  = document.getElementById('lyra-load-more-btn');
        const oldHeight    = chatMessages.scrollHeight;

        if (data.has_more && loadMoreBtn) {
            loadMoreBtn.style.display = 'block';
        } else if (loadMoreBtn) {
            loadMoreBtn.style.display = 'none';
        }

        if (data.history && data.history.length > 0) {
            data.history.reverse().forEach(day => lyraRenderDayHistory(day, isInitial));

            const mostRecentDay = data.history[0];
            if (mostRecentDay && mostRecentDay.messages) {
                lyraChatHistory = mostRecentDay.messages.map(m => ({
                    role: m.role,
                    content: m.content
                }));

                for (let j = mostRecentDay.messages.length - 1; j >= 0; j--) {
                    const m = mostRecentDay.messages[j];
                    if (m.role === 'assistant') {
                        if (m.mood) updateLyraMood(m.mood);
                        let exp = m.expression;
                        if (!exp) {
                            const match = m.content.match(/\[Emotion:\s*(\w+)\]/i);
                            if (match) exp = match[1].toLowerCase();
                        }
                        if (exp) updateLyraExpression(exp);
                        break;
                    }
                }
            }
        }

        if (!isInitial) {
            chatMessages.scrollTop = chatMessages.scrollHeight - oldHeight;
        } else {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        lyraHistoryOffsetDays += data.history ? data.history.length : 0;
    } catch (e) {
        console.error('[Lyra] Error loading history:', e);
    }
}

async function lyraLoadMoreHistory() {
    await lyraLoadHistory(lyraHistoryOffsetDays, LYRA_HISTORY_LIMIT_DAYS, false);
}

function lyraRenderDayHistory(day, isInitial) {
    const chatMessages = document.getElementById('lyra-chat-messages');
    const loadMoreBtn  = document.getElementById('lyra-load-more-btn');

    const dayBlock = document.createElement('div');
    dayBlock.className = 'history-day-block';

    const separator = document.createElement('div');
    separator.className = 'date-separator';
    separator.innerHTML = `<span>${lyraFormatDate(day.date)}</span>`;
    dayBlock.appendChild(separator);

    day.messages.forEach(msg => {
        const parts = msg.content.split(/\[msg_break\]/i);
        parts.forEach((part, idx) => {
            if (part.trim()) {
                const isLast = idx === parts.length - 1;
                const msgDiv = lyraCreateMessageElement(
                    msg.role,
                    part.trim(),
                    isLast ? msg.timestamp : null
                );
                dayBlock.appendChild(msgDiv);
            }
        });
    });

    if (isInitial) {
        chatMessages.appendChild(dayBlock);
    } else {
        if (loadMoreBtn && loadMoreBtn.nextSibling) {
            chatMessages.insertBefore(dayBlock, loadMoreBtn.nextSibling);
        } else {
            chatMessages.prepend(dayBlock);
        }
    }
}

function lyraCreateMessageElement(role, text, timestamp = null) {
    const div = document.createElement('div');
    div.className = `chat-message ${role}`;

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    const cleanedText = lyraCleanDisplayText(text);
    bubble.innerHTML = lyraFormatText(cleanedText);
    div.appendChild(bubble);

    if (timestamp) {
        const ts = document.createElement('div');
        ts.className = 'message-timestamp';
        try {
            const d = new Date(timestamp);
            ts.textContent = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
        } catch (e) {
            ts.textContent = timestamp;
        }
        div.appendChild(ts);
    }

    return div;
}

// ── Text helpers ──────────────────────────────────────────────────────────────

function lyraCleanDisplayText(text) {
    return text
        .replace(/\[Emotion:\s*\w+\]?/gi, '')
        .replace(/\[Mood:\s*\w+\]?/gi, '')
        .replace(/\[msg_break\]/gi, '')
        .trim();
}

function lyraFormatText(text) {
    let safe = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    safe = safe
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br>');
    return safe;
}

function lyraFormatDate(dateStr) {
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
    } catch (e) {
        return dateStr;
    }
}

// ── Streaming bubble helpers ──────────────────────────────────────────────────

function lyraCreateStreamingBubble() {
    const chatMessages = document.getElementById('lyra-chat-messages');
    const div = document.createElement('div');
    div.className = 'chat-message assistant';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble typing-glow';
    bubble.innerHTML = '';
    div.appendChild(bubble);
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return bubble;
}

async function lyraAppendToStreamingBubble(bubble, text) {
    const cleanedText = lyraCleanDisplayText(text);
    if (!cleanedText) return;

    // Detect and update expression inline
    const expMatch = text.match(/\[Emotion:\s*(\w+)\]/i);
    if (expMatch) updateLyraExpression(expMatch[1]);

    for (const char of cleanedText) {
        bubble.innerHTML += char === '\n' ? '<br>' : char;
        document.getElementById('lyra-chat-messages').scrollTop =
            document.getElementById('lyra-chat-messages').scrollHeight;
        await new Promise(r => setTimeout(r, lyraTypingSpeed));
    }
}

function lyraAddToolStatus() {
    const chatMessages = document.getElementById('lyra-chat-messages');
    if (document.getElementById('lyra-tool-status')) return;

    const div = document.createElement('div');
    div.id = 'lyra-tool-status';
    div.className = 'chat-message assistant';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble tool-status-bubble';
    bubble.innerHTML = `<span class="typing-dots"><span></span><span></span><span></span></span>`;
    div.appendChild(bubble);
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function lyraRemoveToolStatus() {
    const el = document.getElementById('lyra-tool-status');
    if (el) el.remove();
}

function lyraAddStaticMessage(role, text, timestamp = null) {
    const chatMessages = document.getElementById('lyra-chat-messages');
    const msgDiv = lyraCreateMessageElement(role, text, timestamp);
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ── Send message ──────────────────────────────────────────────────────────────

async function sendLyraMessage() {
    if (isLyraTyping) return;

    const chatInput = document.getElementById('lyra-chat-input');
    const text = chatInput.value.trim();
    if (!text) return;

    const now = new Date();
    const ts = now.getFullYear() + "-" +
        String(now.getMonth() + 1).padStart(2, '0') + "-" +
        String(now.getDate()).padStart(2, '0') + " " +
        String(now.getHours()).padStart(2, '0') + ":" +
        String(now.getMinutes()).padStart(2, '0') + ":" +
        String(now.getSeconds()).padStart(2, '0');

    lyraAddStaticMessage('user', text, ts);
    chatInput.value = '';
    chatInput.style.height = 'auto';

    const payload = {
        message: text,
        history: lyraChatHistory
    };

    let currentStreamingBubble = null;
    let untypedText = "";
    let currentContentForHistory = "";

    lyraAddToolStatus();
    isLyraTyping = true;

    const statusLine = document.getElementById('lyra-status-line');

    try {
        if (statusLine) statusLine.textContent = 'Something is forming...';

        const response = await fetch('/api/lyra/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'API Error');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.trim()) continue;
                let data;
                try {
                    data = JSON.parse(line);
                } catch (e) {
                    console.error('[Lyra] NDJSON parse error:', e, line);
                    continue;
                }

                    if (data.type === 'message') {
                        lyraRemoveToolStatus();
                        if (statusLine && statusLine.textContent === 'Something is forming...')
                            statusLine.textContent = 'Lyra is speaking...';

                        untypedText += data.content;

                        while (true) {
                            const breakIdx = untypedText.toLowerCase().indexOf('[msg_break]');
                            if (breakIdx !== -1) {
                                const before = untypedText.substring(0, breakIdx);
                                if (before.length > 0) {
                                    if (!currentStreamingBubble) currentStreamingBubble = lyraCreateStreamingBubble();
                                    await lyraAppendToStreamingBubble(currentStreamingBubble, before);
                                    currentContentForHistory += before;
                                }
                                if (currentStreamingBubble) {
                                    currentStreamingBubble.classList.remove('typing-glow');
                                    currentStreamingBubble = null;
                                }
                                currentContentForHistory += '[msg_break]';
                                untypedText = untypedText.substring(breakIdx + '[msg_break]'.length);
                            } else {
                                const partial = '[msg_break]';
                                let safeLen = untypedText.length;
                                for (let l = 1; l < partial.length; l++) {
                                    if (untypedText.toLowerCase().endsWith(partial.substring(0, l))) {
                                        safeLen = untypedText.length - l;
                                        break;
                                    }
                                }
                                if (safeLen > 0) {
                                    const part = untypedText.substring(0, safeLen);
                                    if (!currentStreamingBubble) currentStreamingBubble = lyraCreateStreamingBubble();
                                    await lyraAppendToStreamingBubble(currentStreamingBubble, part);
                                    currentContentForHistory += part;
                                    untypedText = untypedText.substring(safeLen);
                                }
                                break;
                            }
                        }
                    }
                    else if (data.type === 'tool_start') {
                        lyraAddToolStatus();
                        if (statusLine) statusLine.textContent = data.content || 'A thought is arriving...';
                    }
                    else if (data.type === 'done') {
                        lyraRemoveToolStatus();

                        if (currentStreamingBubble) {
                            currentStreamingBubble.classList.remove('typing-glow');
                            const finishNow = new Date();
                            const finishTs = String(finishNow.getHours()).padStart(2, '0') + ':' +
                                String(finishNow.getMinutes()).padStart(2, '0');
                            const tsDiv = document.createElement('div');
                            tsDiv.className = 'message-timestamp';
                            tsDiv.textContent = finishTs;
                            currentStreamingBubble.parentElement.appendChild(tsDiv);
                        }

                        // Flush remaining
                        if (untypedText.trim()) {
                            if (!currentStreamingBubble) currentStreamingBubble = lyraCreateStreamingBubble();
                            await lyraAppendToStreamingBubble(currentStreamingBubble, untypedText);
                            currentContentForHistory += untypedText;
                            untypedText = '';
                        }

                        const fullReply = currentContentForHistory;
                        lyraChatHistory.push({ role: 'assistant', content: fullReply });

                        if (data.mood) updateLyraMood(data.mood);
                        if (data.expression) updateLyraExpression(data.expression);

                        if (statusLine) {
                            statusLine.textContent = LYRA_STATUS_BY_EXPRESSION[currentLyraExpression] ||
                                'Listening...';
                        }
                    }
                    else if (data.type === 'error') {
                        throw new Error(data.content);
                    }
            }
        }

        if (lyraChatHistory.length > lyraMaxHistory) {
            lyraChatHistory = lyraChatHistory.slice(-lyraMaxHistory);
        }

    } catch (err) {
        console.error('[Lyra] Send error:', err);
        lyraRemoveToolStatus();
        lyraAddStaticMessage('assistant',
            `[Emotion: melancholic] Something went quiet... ${err.message}`, ts);
        if (statusLine) statusLine.textContent = 'A silence fell.';
    } finally {
        isLyraTyping = false;
    }
}

// ── Memory refresh ────────────────────────────────────────────────────────────

async function refreshLyraMemory() {
    try {
        const res = await fetch('/api/lyra/memory');
        if (!res.ok) return;
        const data = await res.json();
        console.log('[Lyra] Memory loaded:', Object.keys(data));
    } catch (e) {
        console.warn('[Lyra] Could not load memory:', e);
    }
}

// ── Exports ───────────────────────────────────────────────────────────────────

window.initializeLyra = initializeLyra;
window.refreshLyraMemory = refreshLyraMemory;
window.updateLyraExpression = updateLyraExpression;
window.updateLyraMood = updateLyraMood;
window.sendLyraMessage = sendLyraMessage;
