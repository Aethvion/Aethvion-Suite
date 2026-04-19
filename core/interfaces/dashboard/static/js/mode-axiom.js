/**
 * Aethvion Suite - Axiom Companion
 * CSS-based avatar — expressions controlled via class switching
 */

// ── Global State ──────────────────────────────────────────────────────────────
let axiomChatHistory = [];
let axiomMaxHistory = 20;
let axiomTypingSpeed = 20;  // fallback; overridden by global companions speed
let isAxiomTyping = false;
let axiomHistoryOffsetDays = 0;
const AXIOM_HISTORY_LIMIT_DAYS = 3;
let hasInitializedAxiom = false;
let currentAxiomMood = 'precise';
let currentAxiomExpression = 'neutral';

function _axiomLoadTypingSpeed() {
    if (typeof window.prefs !== 'undefined') {
        axiomTypingSpeed = window.prefs.get('companions.global.typing_speed', 20);
    }
}
_axiomLoadTypingSpeed();

// Update speed when global companion setting changes
window.addEventListener('companionSettingsUpdated', (e) => {
    if (e.detail && e.detail.typing_speed !== undefined) {
        axiomTypingSpeed = parseInt(e.detail.typing_speed, 10);
    }
});

// ── Expression map ────────────────────────────────────────────────────────────
// Maps LLM emotion tag values → CSS class suffixes on #axiom-avatar

const AXIOM_EXPRESSION_MAP = {
    // direct
    'neutral':    'neutral',
    'analyzing':  'analyzing',
    'processing': 'processing',
    'skeptical':  'skeptical',
    'focused':    'focused',
    'error':      'error',
    'curious':    'curious',
    'calculating':'calculating',
    'alert':      'alert',
    // aliases
    'thinking':   'analyzing',
    'analyse':    'analyzing',
    'analyze':    'analyzing',
    'think':      'analyzing',
    'process':    'processing',
    'loading':    'processing',
    'doubt':      'skeptical',
    'suspicious': 'skeptical',
    'focus':      'focused',
    'deep':       'focused',
    'warning':    'alert',
    'danger':     'alert',
    'confused':   'skeptical',
    'happy':      'curious',
    'default':    'neutral',
};

// ── Mood label map ────────────────────────────────────────────────────────────

const AXIOM_MOOD_LABELS = {
    precise:    '◈ Precise',
    analytical: '∿ Analytical',
    processing: '⟳ Processing',
    critical:   '⚡ Critical',
    deep_focus: '◎ Deep Focus',
    warning:    '⚠ Warning',
};

// ── Initializer ───────────────────────────────────────────────────────────────

async function initializeAxiom() {
    if (hasInitializedAxiom) {
        console.log('[Axiom] Already initialized.');
        return;
    }
    console.log('[Axiom] Initializing...');

    const chatMessages = document.getElementById('axiom-chat-messages');
    const chatInput    = document.getElementById('axiom-chat-input');
    const sendBtn      = document.getElementById('send-axiom-msg');

    if (!chatMessages || !chatInput || !sendBtn) {
        console.warn('[Axiom] Required DOM elements not found.');
        return;
    }

    // Load-more button
    if (!document.getElementById('axiom-load-more-btn')) {
        const loadMoreBtn = document.createElement('button');
        loadMoreBtn.id = 'axiom-load-more-btn';
        loadMoreBtn.className = 'load-more-btn';
        loadMoreBtn.textContent = 'Load Previous Conversations';
        loadMoreBtn.style.display = 'none';
        loadMoreBtn.onclick = () => axiomLoadMoreHistory();
        chatMessages.prepend(loadMoreBtn);
    }

    // Restore last state
    const lastMood = localStorage.getItem('axiom_last_mood') || 'precise';
    updateAxiomMood(lastMood);
    const lastExpr = localStorage.getItem('axiom_last_expression') || 'neutral';
    updateAxiomExpression(lastExpr);

    // Clear stale messages
    chatMessages.querySelectorAll('.history-day-block').forEach(b => b.remove());

    // Load history
    axiomHistoryOffsetDays = 0;
    axiomMaxHistory = typeof prefs !== 'undefined' ? prefs.get('axiom.context_limit', 6) : 6;
    await axiomLoadHistory(0, AXIOM_HISTORY_LIMIT_DAYS, true);

    // Wire up send button and Enter key
    sendBtn.addEventListener('click', sendAxiomMessage);
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendAxiomMessage();
        }
    });

    // Auto-resize textarea
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    });

    // Wire settings button → Companions settings subtab
    const axiomSettingsBtn = document.getElementById('axiom-settings-btn');
    if (axiomSettingsBtn) {
        axiomSettingsBtn.addEventListener('click', () => {
            if (typeof ensureTabAndSubTab === 'function') {
                ensureTabAndSubTab('settings', 'companions');
            }
        });
    }

    hasInitializedAxiom = true;
    console.log('[Axiom] Initialization complete.');
}

// ── Expression update ─────────────────────────────────────────────────────────

function updateAxiomExpression(expression) {
    const avatar = document.getElementById('axiom-avatar');
    if (!avatar) return;

    const key = (expression || 'neutral').toLowerCase().trim();
    const cssClass = AXIOM_EXPRESSION_MAP[key] || 'neutral';

    // Remove all existing expression classes
    const classes = Array.from(avatar.classList);
    classes.filter(c => c.startsWith('axiom-expr-')).forEach(c => avatar.classList.remove(c));

    avatar.classList.add(`axiom-expr-${cssClass}`);
    currentAxiomExpression = cssClass;

    // Update status line with a formatted label
    const statusLine = document.getElementById('axiom-status-line');
    if (statusLine) {
        const labels = {
            neutral:    'Ready.',
            analyzing:  'Analyzing data...',
            processing: 'Processing...',
            skeptical:  'I need more information to be precise.',
            focused:    'Deep focus active.',
            error:      'Something went wrong.',
            curious:    'Investigation in progress...',
            calculating:'Calculating...',
            alert:      'Attention required.',
        };
        statusLine.textContent = labels[cssClass] || 'Ready.';
    }

    localStorage.setItem('axiom_last_expression', key);
}

// ── Mood update ───────────────────────────────────────────────────────────────

function updateAxiomMood(mood) {
    if (mood === currentAxiomMood) return;
    currentAxiomMood = mood;

    const layout = document.querySelector('.axiom-layout');
    if (!layout) return;

    const moods = ['mood-precise', 'mood-analytical', 'mood-processing', 'mood-critical', 'mood-deep_focus', 'mood-warning'];
    moods.forEach(m => layout.classList.remove(m));
    layout.classList.add(`mood-${mood}`);

    const badge = document.getElementById('axiom-mood-badge');
    if (badge) {
        badge.textContent = AXIOM_MOOD_LABELS[mood] || mood;
        badge.classList.add('visible');
        clearTimeout(badge._hideTimer);
        badge._hideTimer = setTimeout(() => badge.classList.remove('visible'), 4000);
    }

    localStorage.setItem('axiom_last_mood', mood);
}

// ── History loading ───────────────────────────────────────────────────────────

async function axiomLoadHistory(offsetDays, limitDays, isInitial) {
    try {
        const res = await fetch(`/api/companions/axiom/history?offset_days=${offsetDays}&limit_days=${limitDays}`);
        if (!res.ok) return;
        const data = await res.json();

        const chatMessages = document.getElementById('axiom-chat-messages');
        const loadMoreBtn  = document.getElementById('axiom-load-more-btn');
        const oldHeight    = chatMessages.scrollHeight;

        if (data.has_more && loadMoreBtn) {
            loadMoreBtn.style.display = 'block';
        } else if (loadMoreBtn) {
            loadMoreBtn.style.display = 'none';
        }

        if (data.history && data.history.length > 0) {
            data.history.reverse().forEach(day => axiomRenderDayHistory(day, isInitial));

            // Rebuild in-memory context from most recent day
            const mostRecentDay = data.history[0];
            if (mostRecentDay && mostRecentDay.messages) {
                axiomChatHistory = mostRecentDay.messages.map(m => ({
                    role: m.role,
                    content: m.content
                }));

                for (let j = mostRecentDay.messages.length - 1; j >= 0; j--) {
                    const m = mostRecentDay.messages[j];
                    if (m.role === 'assistant') {
                        if (m.mood) updateAxiomMood(m.mood);
                        let exp = m.expression;
                        if (!exp) {
                            const match = m.content.match(/\[Emotion:\s*(\w+)\]/i);
                            if (match) exp = match[1].toLowerCase();
                        }
                        if (exp) updateAxiomExpression(exp);
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

        axiomHistoryOffsetDays += data.history ? data.history.length : 0;
    } catch (e) {
        console.error('[Axiom] Error loading history:', e);
    }
}

async function axiomLoadMoreHistory() {
    await axiomLoadHistory(axiomHistoryOffsetDays, AXIOM_HISTORY_LIMIT_DAYS, false);
}

function axiomRenderDayHistory(day, isInitial) {
    const chatMessages = document.getElementById('axiom-chat-messages');
    const loadMoreBtn  = document.getElementById('axiom-load-more-btn');

    const dayBlock  = document.createElement('div');
    dayBlock.className = 'history-day-block';

    const separator = document.createElement('div');
    separator.className = 'date-separator';
    separator.innerHTML = `<span>${axiomFormatDate(day.date)}</span>`;
    dayBlock.appendChild(separator);

    day.messages.forEach(msg => {
        const parts = msg.content.split(/\[msg_break\]/i);
        parts.forEach((part, idx) => {
            if (part.trim()) {
                const isLast = idx === parts.length - 1;
                const msgDiv = axiomCreateMessageElement(
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

function axiomCreateMessageElement(role, text, timestamp = null) {
    const div = document.createElement('div');
    div.className = `chat-message ${role}`;

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    const cleanedText = axiomCleanDisplayText(text);
    bubble.innerHTML = axiomFormatText(cleanedText);
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

function axiomCleanDisplayText(text) {
    return text
        .replace(/\[Emotion:\s*\w+\]?/gi, '')
        .replace(/\[Mood:\s*\w+\]?/gi, '')
        .replace(/\[msg_break\]/gi, '')
        .trim();
}

function axiomFormatText(text) {
    // Escape HTML then render basic markdown-like formatting
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

function axiomFormatDate(dateStr) {
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
    } catch (e) {
        return dateStr;
    }
}

// ── Streaming bubble helpers ──────────────────────────────────────────────────

function axiomCreateStreamingBubble() {
    const chatMessages = document.getElementById('axiom-chat-messages');
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

async function axiomAppendToStreamingBubble(bubble, text) {
    const cleanedText = axiomCleanDisplayText(text);
    if (!cleanedText) return;

    // Detect and update expression inline
    const expMatch = text.match(/\[Emotion:\s*(\w+)\]/i);
    if (expMatch) updateAxiomExpression(expMatch[1]);

    // Character-by-character typing effect
    for (const char of cleanedText) {
        bubble.innerHTML += char === '\n' ? '<br>' : char;
        document.getElementById('axiom-chat-messages').scrollTop =
            document.getElementById('axiom-chat-messages').scrollHeight;
        await new Promise(r => setTimeout(r, axiomTypingSpeed));
    }
}

function axiomAddToolStatus() {
    const chatMessages = document.getElementById('axiom-chat-messages');
    if (document.getElementById('axiom-tool-status')) return;

    const div = document.createElement('div');
    div.id = 'axiom-tool-status';
    div.className = 'chat-message assistant';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble tool-status-bubble';
    bubble.innerHTML = `<span class="typing-dots"><span></span><span></span><span></span></span>`;
    div.appendChild(bubble);
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function axiomRemoveToolStatus() {
    const el = document.getElementById('axiom-tool-status');
    if (el) el.remove();
}

function axiomAddStaticMessage(role, text, timestamp = null) {
    const chatMessages = document.getElementById('axiom-chat-messages');
    const msgDiv = axiomCreateMessageElement(role, text, timestamp);
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ── Send message ──────────────────────────────────────────────────────────────

async function sendAxiomMessage() {
    if (isAxiomTyping) return;

    const chatInput = document.getElementById('axiom-chat-input');
    const text = chatInput.value.trim();
    if (!text) return;

    const now = new Date();
    const ts = now.getFullYear() + "-" +
        String(now.getMonth() + 1).padStart(2, '0') + "-" +
        String(now.getDate()).padStart(2, '0') + " " +
        String(now.getHours()).padStart(2, '0') + ":" +
        String(now.getMinutes()).padStart(2, '0') + ":" +
        String(now.getSeconds()).padStart(2, '0');

    axiomAddStaticMessage('user', text, ts);
    chatInput.value = '';
    chatInput.style.height = 'auto';

    const payload = {
        message: text,
        history: axiomChatHistory
    };

    let currentStreamingBubble = null;
    let untypedText = "";
    let currentContentForHistory = "";

    axiomAddToolStatus();
    isAxiomTyping = true;

    const statusLine = document.getElementById('axiom-status-line');

    try {
        if (statusLine) statusLine.textContent = 'Processing query...';

        const response = await fetch('/api/companions/axiom/chat', {
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
                    console.error('[Axiom] NDJSON parse error:', e, line);
                    continue;
                }

                    if (data.type === 'message') {
                        axiomRemoveToolStatus();
                        if (statusLine && statusLine.textContent === 'Processing query...')
                            statusLine.textContent = 'Composing response...';

                        untypedText += data.content;

                        while (true) {
                            const breakIdx = untypedText.toLowerCase().indexOf('[msg_break]');
                            if (breakIdx !== -1) {
                                const before = untypedText.substring(0, breakIdx);
                                if (before.length > 0) {
                                    if (!currentStreamingBubble) currentStreamingBubble = axiomCreateStreamingBubble();
                                    await axiomAppendToStreamingBubble(currentStreamingBubble, before);
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
                                    if (!currentStreamingBubble) currentStreamingBubble = axiomCreateStreamingBubble();
                                    await axiomAppendToStreamingBubble(currentStreamingBubble, part);
                                    currentContentForHistory += part;
                                    untypedText = untypedText.substring(safeLen);
                                }
                                break;
                            }
                        }
                    }
                    else if (data.type === 'tool_start') {
                        axiomAddToolStatus();
                        if (statusLine) statusLine.textContent = data.content || 'Processing...';
                    }
                    else if (data.type === 'done') {
                        axiomRemoveToolStatus();

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

                        // Flush remaining untyped text
                        if (untypedText.trim()) {
                            if (!currentStreamingBubble) currentStreamingBubble = axiomCreateStreamingBubble();
                            await axiomAppendToStreamingBubble(currentStreamingBubble, untypedText);
                            currentContentForHistory += untypedText;
                            untypedText = '';
                        }

                        const fullReply = currentContentForHistory;
                        axiomChatHistory.push({ role: 'assistant', content: fullReply });

                        if (data.mood) updateAxiomMood(data.mood);
                        if (data.expression) updateAxiomExpression(data.expression);

                        const idleLabels = {
                            neutral:    'Ready.',
                            analyzing:  'Analysis complete.',
                            processing: 'Done.',
                            focused:    'Focus released.',
                            curious:    'Investigation concluded.',
                            calculating:'Calculation complete.',
                            alert:      'Ready.',
                        };
                        if (statusLine) {
                            statusLine.textContent = idleLabels[currentAxiomExpression] || 'Ready.';
                        }
                    }
                    else if (data.type === 'error') {
                        throw new Error(data.content);
                    }
            }
        }

        if (axiomChatHistory.length > axiomMaxHistory) {
            axiomChatHistory = axiomChatHistory.slice(-axiomMaxHistory);
        }

    } catch (err) {
        console.error('[Axiom] Send error:', err);
        axiomRemoveToolStatus();
        axiomAddStaticMessage('assistant', `An error occurred. Please try again.`, ts);
        if (statusLine) {
            statusLine.textContent = "Something went wrong. Please try again.";
            setTimeout(() => { if (statusLine) statusLine.textContent = "Ready."; }, 5000);
        }
    } finally {
        isAxiomTyping = false;
    }
}

// ── Memory refresh ────────────────────────────────────────────────────────────

async function refreshAxiomMemory() {
    try {
        const res = await fetch('/api/companions/axiom/memory');
        if (!res.ok) return;
        const data = await res.json();
        
        const baseViewer = document.getElementById('axiom-base-info-viewer');
        const dynamicViewer = document.getElementById('axiom-dynamic-memory-viewer');
        
        if (baseViewer) baseViewer.textContent = JSON.stringify(data.base_info, null, 4);
        if (dynamicViewer) dynamicViewer.textContent = JSON.stringify(data.memory, null, 4);
    } catch (e) {
        console.warn('[Axiom] Could not load memory:', e);
    }
}

window.toggleAxiomMemoryMode = function() {
    const chatMsgs = document.getElementById('axiom-chat-messages');
    const memoryView = document.getElementById('axiom-memory-view');
    const toggleBtn = document.getElementById('axiom-memory-toggle');
    const inputArea = document.querySelector('.axiom-layout .chat-input-area');

    if (!memoryView) return;

    if (memoryView.style.display === 'none') {
        chatMsgs.style.display = 'none';
        if (inputArea) inputArea.style.display = 'none';
        memoryView.style.display = 'flex';
        toggleBtn.classList.add('voice-active');
        toggleBtn.title = "Back to Chat";
        refreshAxiomMemory();
    } else {
        chatMsgs.style.display = 'flex';
        if (inputArea) inputArea.style.display = 'flex';
        memoryView.style.display = 'none';
        toggleBtn.classList.remove('voice-active');
        toggleBtn.title = "View Axiom's Memory";
    }
};

// ── Exports ───────────────────────────────────────────────────────────────────

window.initializeAxiom = initializeAxiom;
window.refreshAxiomMemory = refreshAxiomMemory;
window.updateAxiomExpression = updateAxiomExpression;
window.updateAxiomMood = updateAxiomMood;
window.sendAxiomMessage = sendAxiomMessage;
