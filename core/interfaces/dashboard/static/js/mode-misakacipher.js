/**
 * Aethvion Suite - Misaka Cipher Companion - Persistence & History
 */

// Global State
let misakaChatHistory = [];
let misakaMaxHistory = 20;
let misakaTypingSpeed = 75;
let isMisakaTyping = false;
let historyOffsetDays = 0;
const HISTORY_LIMIT_DAYS = 3;
let hasInitializedMisaka = false;
let currentMisakaMood = 'calm';

// Initialize from prefs if available, else default to 75
if (typeof window.prefs !== 'undefined') {
    misakaTypingSpeed = window.prefs.get('misakacipher.typing_speed', 75);
}

let _proactiveSessionTimer = null;
let _typingTimeout = null; // Timer to resume proactive check-ins after typing stops
let _misakaAttachedFile = null;
let currentToolBubble = null; // Added for tool status display

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
    // Apply default or restored mood/expression
    const lastMood = localStorage.getItem('misaka_last_mood') || 'calm';
    updateMisakaMood(lastMood);

    const lastExpr = localStorage.getItem('misaka_last_expression') || 'default';
    updateMisakaExpression(lastExpr);

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

    // Restore voice output pref
    const voiceWasEnabled = window.prefs ? prefs.get('misakacipher.voice_enabled', false) : false;
    if (voiceWasEnabled) {
        _misakaVoiceEnabled = true;
        const btn = document.getElementById('misaka-voice-toggle');
        const opts = document.getElementById('misaka-voice-options');
        if (btn) { btn.querySelector('i').className = 'fas fa-volume-up'; btn.classList.add('voice-active'); }
        if (opts) opts.style.display = 'flex';
        loadMisakaTTSModels();
    }

    hasInitializedMisaka = true;

    // 6. Listen for changes from settings page
    window.addEventListener('misakaSettingsUpdated', (e) => {
        console.log('[Misaka] Settings update received:', e.detail);
        if (e.detail && e.detail.context_limit) misakaMaxHistory = e.detail.context_limit;
        if (e.detail && e.detail.typing_speed !== undefined) {
            misakaTypingSpeed = parseInt(e.detail.typing_speed, 10);
            console.log('[Misaka] Typing speed updated to:', misakaTypingSpeed);
        }

        // Restart proactive scheduler if proactive settings might have changed
        if (e.detail && e.detail.proactive_change) {
            startProactiveScheduler();
        }

        // Toggle character / particle sphere
        if (e.detail && e.detail.hide_character !== undefined) {
            applyCharacterMode(e.detail.hide_character);
        }
    });

    // 7. Cache typing speed from prefs
    if (window.prefs) {
        misakaTypingSpeed = window.prefs.get('misakacipher.typing_speed', 20);
        console.log('[Misaka] Initial typing speed from prefs:', misakaTypingSpeed);
    }

    // 8. Apply character / sphere mode from saved pref
    const hideChar = window.prefs ? window.prefs.get('misakacipher.hide_character', false) : false;
    applyCharacterMode(hideChar);

    // 9. Wire settings gear button → Settings › Misaka Cipher subtab
    const settingsBtn = document.getElementById('misaka-settings-btn');
    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => {
            if (typeof ensureTabAndSubTab === 'function') {
                ensureTabAndSubTab('settings', 'misakacipher');
            }
        });
    }

    // 1. Setup Input interactions
    if (chatInput && sendBtn) {
        sendBtn.onclick = sendMisakaMessage;
        chatInput.onkeydown = (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMisakaMessage();
            }
        };
        // Reset/Pause proactive timer when typing
        chatInput.addEventListener('input', () => {
            if (chatInput.value.trim().length > 0) {
                pauseProactiveForTyping();
            }
        });
    }

    // 2. Wire attach button
    const attachBtn = document.getElementById('misaka-attach-btn');
    const fileInput = document.getElementById('misaka-file-input');
    if (attachBtn && fileInput) {
        attachBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', handleMisakaFileSelected);
    }

    // 7. Start proactive scheduler (runs once, sets up timers)
    startProactiveScheduler();
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

                    // Restore last state (mood and expression)
                    // We look backwards through the most recent day for the last assistant message
                    for (let j = mostRecentDay.messages.length - 1; j >= 0; j--) {
                        const m = mostRecentDay.messages[j];
                        if (m.role === 'assistant') {
                            if (m.mood) updateMisakaMood(m.mood);

                            // Try to extract expression either from saved field or content tag
                            let exp = m.expression;
                            if (!exp) {
                                const expMatch = m.content.match(/\[Emotion:\s*(\w+)\]/i);
                                if (expMatch) exp = expMatch[1].toLowerCase();
                            }
                            if (exp) updateMisakaExpression(exp);

                            break; // Only need the latest one
                        }
                    }
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
        parts.forEach((part, index) => {
            if (part.trim()) {
                const isLastPart = index === parts.length - 1;
                const atts = isLastPart ? msg.attachments : null;
                const msgDiv = createMessageElement(
                    msg.role, 
                    part.trim(), 
                    isLastPart ? msg.timestamp : null, 
                    atts,
                    msg.platform // Pass platform for Discord badges
                );
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

function createMessageElement(role, text, timestamp = null, attachments = null, platform = 'dashboard') {
    const div = document.createElement('div');
    const isDiscord = platform === 'discord' || platform === 'Discord';
    div.className = `chat-message ${role}${isDiscord ? ' from-discord' : ''}`;

    if (isDiscord) {
        const badge = document.createElement('div');
        badge.className = 'discord-badge';
        badge.innerHTML = `<i class="fab fa-discord"></i> Discord`;
        div.appendChild(badge);
    }

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    const textContainer = document.createElement('div');
    if (role === 'assistant') {
        const cleanText = text.replace(/<memory_update>[\s\S]*?<\/memory_update>/gi, '')
            .replace(/\[Emotion:\s*[^\]]+\]/gi, '')   // multi-word: "warm smile", "happy closedeyes" etc
            .replace(/\[Mood:\s*[^\]]+\]/gi, '')
            .replace(/\[tool:[\s\S]*?\](?=(?:\s*\[tool:)|(?:\s*$)|(?:\s*\[msg_break\]))/gi, '')
            .replace(/\[msg_break\]/gi, '')
            .trim();
        textContainer.innerHTML = renderMarkdown(cleanText);
    } else {
        textContainer.textContent = text;
    }
    bubble.appendChild(textContainer);

    if (attachments && attachments.length > 0) {
        const attachContainer = document.createElement('div');
        attachContainer.className = 'message-attachments';
        attachContainer.style.marginTop = '8px';
        attachContainer.style.display = 'flex';
        attachContainer.style.flexWrap = 'wrap';
        attachContainer.style.gap = '8px';

        attachments.forEach(att => {
            if (att.is_image && att.url) {
                const img = document.createElement('img');
                img.src = att.url;
                img.className = 'chat-attached-image';
                img.style.maxWidth = '100%';
                img.style.maxHeight = '250px';
                img.style.borderRadius = '8px';
                img.style.objectFit = 'contain';
                attachContainer.appendChild(img);
            } else if (att.filename) {
                const pill = document.createElement('div');
                pill.className = 'chat-attached-file-pill';
                pill.textContent = `📄 ${att.filename}`;
                pill.style.fontSize = '0.85em';
                pill.style.padding = '4px 8px';
                pill.style.background = 'rgba(255,255,255,0.1)';
                pill.style.borderRadius = '4px';
                attachContainer.appendChild(pill);
            }
        });
        bubble.appendChild(attachContainer);
    }

    div.appendChild(bubble);

    if (timestamp) {
        const tsDiv = document.createElement('div');
        tsDiv.className = 'message-timestamp';

        // Format: "YYYY-MM-DD HH:MM:SS" -> "HH:MM"
        try {
            const timePart = timestamp.split(' ')[1] || timestamp;
            const bluePrint = timePart.split(':');
            if (bluePrint.length >= 2) {
                tsDiv.textContent = `${bluePrint[0]}:${bluePrint[1]}`;
            } else {
                tsDiv.textContent = timestamp;
            }
        } catch (e) {
            tsDiv.textContent = timestamp;
        }

        div.appendChild(tsDiv);
    }

    return div;
}

/**
 * Appends media attachments to an existing message element.
 */
function appendAttachmentsToMessage(messageDiv, attachments) {
    if (!attachments || attachments.length === 0) return;

    const bubble = messageDiv.querySelector('.message-bubble');
    if (!bubble) return;

    let attachContainer = bubble.querySelector('.message-attachments');
    if (!attachContainer) {
        attachContainer = document.createElement('div');
        attachContainer.className = 'message-attachments';
        attachContainer.style.marginTop = '8px';
        attachContainer.style.display = 'flex';
        attachContainer.style.flexWrap = 'wrap';
        attachContainer.style.gap = '8px';
        bubble.appendChild(attachContainer);
    }

    attachments.forEach(att => {
        // Avoid duplicates
        const existingImg = Array.from(attachContainer.querySelectorAll('img')).find(i => i.src.includes(att.url));
        if (att.url && existingImg) return;

        if (att.is_image && att.url) {
            const img = document.createElement('img');
            img.src = att.url;
            img.className = 'chat-attached-image';
            img.style.maxWidth = '100%';
            img.style.maxHeight = '250px';
            img.style.borderRadius = '8px';
            img.style.objectFit = 'contain';
            img.onload = () => {
                const container = document.getElementById('misaka-chat-messages');
                if (container) container.scrollTop = container.scrollHeight;
            };
            attachContainer.appendChild(img);
        } else if (att.filename) {
            const pill = document.createElement('div');
            pill.className = 'chat-attached-file-pill';
            pill.textContent = `📄 ${att.filename}`;
            pill.style.fontSize = '0.85em';
            pill.style.padding = '4px 8px';
            pill.style.background = 'rgba(255,255,255,0.1)';
            pill.style.borderRadius = '4px';
            attachContainer.appendChild(pill);
        }
    });
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
    if (!text && !_misakaAttachedFile) return;

    const now = new Date();
    const ts = now.getFullYear() + "-" +
        String(now.getMonth() + 1).padStart(2, '0') + "-" +
        String(now.getDate()).padStart(2, '0') + " " +
        String(now.getHours()).padStart(2, '0') + ":" +
        String(now.getMinutes()).padStart(2, '0') + ":" +
        String(now.getSeconds()).padStart(2, '0');

    // Reset/Resume proportional to last activity
    startProactiveScheduler();

    // Upload file if attached
    let attachedFiles = null;
    const attachedFileName = _misakaAttachedFile ? _misakaAttachedFile.name : null;
    if (_misakaAttachedFile) {
        try {
            const formData = new FormData();
            formData.append('file', _misakaAttachedFile.file, _misakaAttachedFile.name);
            const uploadRes = await fetch('/api/misakacipher/upload-context', {
                method: 'POST',
                body: formData
            });
            if (uploadRes.ok) {
                const uploadData = await uploadRes.json();
                attachedFiles = [uploadData];
            } else {
                console.warn('File upload failed:', await uploadRes.text());
            }
        } catch (uploadErr) {
            console.error('File upload error:', uploadErr);
        }
        clearMisakaAttachment();
    }

    const displayText = text || `[Attached: ${attachedFileName}]`;
    addAssistantMessageStatic('user', displayText, ts, attachedFiles);
    chatInput.value = '';

    const payload = {
        message: text || `Please review the attached file: ${attachedFileName || 'file'}`,
        history: misakaChatHistory,
        ...(attachedFiles ? { attached_files: attachedFiles } : {})
    };

    let currentStreamingBubble = null;
    let untypedText = ""; // Text received but not yet revealed in bubbles
    let currentContentForHistory = ""; // Correct content including ALL turns

    // Activate particle sphere while AI responds
    if (window.ParticleSphere) ParticleSphere.setActive(true);
    // Show dots indicator immediately — don't wait for first server chunk
    addAssistantToolStatus();

    try {
        const statusLine = document.getElementById('misaka-status-line');
        if (statusLine) statusLine.textContent = "Processing...";

        const response = await fetch('/api/misakacipher/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "API Error");
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
                try {
                    const data = JSON.parse(line);

                    if (data.type === 'message') {
                        removeAssistantToolStatus(); // hide dots as soon as text starts
                        if (statusLine && statusLine.textContent === "Processing...")
                            statusLine.textContent = "Composing reply...";
                        untypedText += data.content;

                        // Process the untyped buffer for breaks and packets
                        while (true) {
                            const breakIdx = untypedText.toLowerCase().indexOf('[msg_break]');
                            if (breakIdx !== -1) {
                                // 1. Found a full break. Deliver everything before it.
                                const before = untypedText.substring(0, breakIdx);
                                if (before.length > 0) {
                                    if (!currentStreamingBubble) currentStreamingBubble = createStreamingBubble();
                                    await appendToStreamingBubble(currentStreamingBubble, before);
                                    currentContentForHistory += before;
                                }

                                // 2. Finalize bubble
                                if (currentStreamingBubble) {
                                    currentStreamingBubble.classList.remove('typing-glow');
                                    // Add timestamp if desired later
                                    currentStreamingBubble = null;
                                }

                                // 3. Advance buffer past the break
                                currentContentForHistory += "[msg_break]";
                                untypedText = untypedText.substring(breakIdx + '[msg_break]'.length);
                            } else {
                                // 4. No full break. Deliver "safe" text that isn't a partial [msg_break]
                                const partial = "[msg_break]";
                                let safeLen = untypedText.length;
                                for (let l = 1; l < partial.length; l++) {
                                    if (untypedText.toLowerCase().endsWith(partial.substring(0, l))) {
                                        safeLen = untypedText.length - l;
                                        break;
                                    }
                                }

                                if (safeLen > 0) {
                                    const part = untypedText.substring(0, safeLen);
                                    if (!currentStreamingBubble) currentStreamingBubble = createStreamingBubble();
                                    await appendToStreamingBubble(currentStreamingBubble, part);
                                    currentContentForHistory += part;
                                    untypedText = untypedText.substring(safeLen);
                                }
                                break; // Wait for next packet
                            }
                        }
                    }
                    else if (data.type === 'tool_start') {
                        addAssistantToolStatus(); // dots only, already showing
                        if (statusLine) statusLine.textContent = data.content || "Processing...";
                    }
                    else if (data.type === 'done') {
                        removeAssistantToolStatus();
                        if (window.ParticleSphere) ParticleSphere.setActive(false);

                        if (currentStreamingBubble) {
                            currentStreamingBubble.classList.remove('typing-glow');
                            const finishNow = new Date();
                            const finishTs = String(finishNow.getHours()).padStart(2, '0') + ":" + String(finishNow.getMinutes()).padStart(2, '0');
                            const tsDiv = document.createElement('div');
                            tsDiv.className = 'message-timestamp';
                            tsDiv.textContent = finishTs;
                            currentStreamingBubble.parentElement.appendChild(tsDiv);
                        }

                        const _fullReply = currentContentForHistory + untypedText;
                        misakaChatHistory.push({
                            role: 'assistant',
                            content: _fullReply
                        });

                        speakMisakaResponse(_fullReply);

                        if (data.mood) updateMisakaMood(data.mood);
                        if (data.expression) updateMisakaExpression(data.expression);

                        if (data.attachments && data.attachments.length > 0) {
                            const container = document.getElementById('misaka-chat-messages');
                            const assistantMsgs = container.querySelectorAll('.chat-message.assistant');
                            const lastAssistantMsg = assistantMsgs[assistantMsgs.length - 1];
                            if (lastAssistantMsg) {
                                appendAttachmentsToMessage(lastAssistantMsg, data.attachments);
                                setTimeout(() => { container.scrollTop = container.scrollHeight; }, 100);
                            }
                        }

                        const idleStatus = data.expression
                            ? _misakaPrettifyExpression(data.expression)
                            : "Neural core engaged.";

                        if (data.memory_updated || data.synthesis_ran) {
                            await refreshMisakaMemory();
                            if (statusLine) statusLine.textContent = "Memory synchronized.";
                            setTimeout(() => { if (statusLine) statusLine.textContent = idleStatus; }, 4000);
                        } else {
                            if (statusLine) statusLine.textContent = idleStatus;
                        }
                    }
                    else if (data.type === 'error') {
                        throw new Error(data.content);
                    }
                } catch (e) {
                    console.error("Error parsing NDJSON line:", e, line);
                }
            }
        }

        if (misakaChatHistory.length > misakaMaxHistory) {
            misakaChatHistory = misakaChatHistory.slice(-misakaMaxHistory);
        }

    } catch (err) {
        console.error("Misaka send error:", err);
        addAssistantMessageStatic('misaka', `I encountered a neural synchronization error: ${err.message}`, ts);
        if (statusLine) statusLine.textContent = "Neural error — check console.";
        setTimeout(() => { if (statusLine) statusLine.textContent = "Neural core engaged."; }, 5000);
        if (window.ParticleSphere) ParticleSphere.setActive(false);
    }
}

function addAssistantMessageStatic(role, text, timestamp = null, attachments = null) {
    const container = document.getElementById('misaka-chat-messages');
    if (!container) return;

    const div = createMessageElement(role, text, timestamp, attachments);
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

function cleanStreamingDisplay(rawText) {
    // Remove expression/mood/break tags (complete + partial at string end)
    // [^\]]+ matches multi-word emotions like "warm smile", "happy closedeyes"
    let clean = rawText
        .replace(/\[Emotion:[^\]]*\]/gi, '')
        .replace(/\[Mood:[^\]]*\]/gi, '')
        .replace(/\[msg_break\]/gi, '')
        // Strip partial tag still being typed at end of string
        .replace(/\[(Emotion|Mood|msg_break)[^\]]*$/i, '');

    // Strip complete bare JSON memory blobs (model forgot <memory_update> wrapper)
    const memKeys = /"(?:user_info|recent_observations|base_info|synthesis_notes)"/;
    clean = clean.replace(/\n?\{[^{]*"(?:user_info|recent_observations|base_info|synthesis_notes)"[\s\S]*?\}/g, '');

    // Strip partial JSON fragments like `,  "user_info":...` that haven't closed yet
    clean = clean.replace(/,?\s*"(?:user_info|recent_observations|base_info|synthesis_notes)"[\s\S]*/g, '');

    // Strip trailing partial JSON blob still being typed (starts with \n{ )
    const trailingJson = clean.match(/\n(\{[^{]*)$/);
    if (trailingJson && memKeys.test(trailingJson[1])) {
        clean = clean.slice(0, clean.length - trailingJson[0].length);
    }

    return clean.trim();
}

function addAssistantToolStatus() {
    const container = document.getElementById('misaka-chat-messages');
    if (!container) return;
    if (currentToolBubble) return; // already showing

    const div = document.createElement('div');
    div.className = 'chat-message assistant tool-indicator';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble misaka-busy-bubble';

    const dots = document.createElement('div');
    dots.className = 'misaka-dots';
    dots.innerHTML = '<span></span><span></span><span></span>';

    bubble.appendChild(dots);
    div.appendChild(bubble);
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;

    currentToolBubble = div;
}

function removeAssistantToolStatus() {
    if (currentToolBubble) {
        currentToolBubble.remove();
        currentToolBubble = null;
    }
}

function createStreamingBubble() {
    const container = document.getElementById('misaka-chat-messages');
    if (!container) return null;

    const div = document.createElement('div');
    div.className = 'chat-message assistant';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble typing-glow';
    bubble.setAttribute('data-raw', '');

    // Aligned with createMessageElement: plain div inside bubble
    const textContainer = document.createElement('div');
    bubble.appendChild(textContainer);

    div.appendChild(bubble);
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;

    return bubble;
}

async function appendToStreamingBubble(bubble, newChunk) {
    const container = document.getElementById('misaka-chat-messages');
    const textContainer = bubble.querySelector('div'); // Get the internal div
    if (!textContainer) return;

    let raw = bubble.getAttribute('data-raw') || "";
    const chars = Array.from(newChunk);

    for (const char of chars) {
        raw += char;
        bubble.setAttribute('data-raw', raw);

        // Immediate Expression/Mood trigger
        if (raw.endsWith(']')) {
            const emotionMatch = raw.match(/\[Emotion:\s*([^\]]+)\]$/i);
            if (emotionMatch) {
                const emo = emotionMatch[1].trim().toLowerCase();
                updateMisakaExpression(emo);
                const sl = document.getElementById('misaka-status-line');
                if (sl) sl.textContent = _misakaPrettifyExpression(emo);
            }
            const moodMatch = raw.match(/\[Mood:\s*([^\]]+)\]$/i);
            if (moodMatch) updateMisakaMood(moodMatch[1].trim().toLowerCase());
        }

        // Display current state cleaned: removed msg_break replacement here, sendMisakaMessage handles it
        let display = cleanStreamingDisplay(raw);

        textContainer.innerHTML = renderMarkdown(display);

        // Highlight code only if needed
        if (typeof hljs !== 'undefined' && display.includes('```')) {
            textContainer.querySelectorAll('pre code').forEach((block) => {
                if (!block.classList.contains('hljs')) hljs.highlightElement(block);
            });
        }

        container.scrollTop = container.scrollHeight;

        // Steady typing pulse using calibrated speed
        let delayMs = 100 - misakaTypingSpeed;
        if (delayMs > 0) {
            // Minimal catch-up only for extreme backlogs (>200 chars)
            const factor = chars.length > 200 ? 0.2 : 1.0;
            await new Promise(r => setTimeout(r, delayMs * factor));
        }
    }
}

function full_content_accumulator(text) {
    return text.replace(/\[Emotion:\s*\w+\]/gi, '')
        .replace(/\[Mood:\s*\w+\]/gi, '')
        .trim();
}

async function addAssistantMessageTyped(fullText, attachments = null) {
    // This is now used mainly for static history loads or fallback
    const bubble = createStreamingBubble();
    if (bubble) {
        await appendToStreamingBubble(bubble, fullText);
        bubble.classList.remove('typing-glow');

        // Add timestamp
        const now = new Date();
        const ts = String(now.getHours()).padStart(2, '0') + ":" + String(now.getMinutes()).padStart(2, '0');
        const tsDiv = document.createElement('div');
        tsDiv.className = 'message-timestamp';
        tsDiv.textContent = ts;
        bubble.parentElement.appendChild(tsDiv);

        if (attachments) appendAttachmentsToMessage(bubble.parentElement, attachments);
    }
}

function _misakaPrettifyExpression(expr) {
    // Resolve aliases first (same map as updateMisakaExpression)
    const aliases = {
        'smile': 'happy_closedeyes_widesmile',
        'smiling': 'happy_closedeyes_widesmile',
        'happy': 'happy_closedeyes_widesmile',
        'grin': 'happy_closedeyes_smilewithteeth',
        'blush': 'blushing',
        'cry': 'crying',
        'sad': 'crying',
        'sleep': 'sleeping',
        'surprise': 'surprised',
        'shock': 'surprised',
        'think': 'thinking',
        'hm': 'thinking',
        'pouting': 'pout',
        'mad': 'angry'
    };
    const resolved = aliases[expr.toLowerCase()] || expr.toLowerCase();
    const labels = {
        'default':                          'Neural core engaged.',
        'thinking':                         'Deep in thought...',
        'happy_closedeyes_widesmile':       'Feeling cheerful.',
        'happy_closedeyes_smilewithteeth':  'In a great mood!',
        'blushing':                         'Feeling a little flustered.',
        'wink':                             'Being playful.',
        'surprised':                        'Caught off guard!',
        'pout':                             'A bit sulky.',
        'angry':                            'Feeling frustrated.',
        'crying':                           'Feeling sad.',
        'bored':                            'A little bored.',
        'exhausted':                        'Running low on energy.',
        'sleeping':                         'Resting...',
        'error':                            'Something went wrong.'
    };
    return labels[resolved] || `Feeling ${resolved.replace(/_/g, ' ')}.`;
}

function updateMisakaExpression(expression) {
    const img = document.getElementById('misaka-expression-img');
    if (!img) return;

    // Expression aliasing
    const aliases = {
        'smile': 'happy_closedeyes_widesmile',
        'smiling': 'happy_closedeyes_widesmile',
        'happy': 'happy_closedeyes_widesmile',
        'grin': 'happy_closedeyes_smilewithteeth',
        'blush': 'blushing',
        'cry': 'crying',
        'sad': 'crying',
        'sleep': 'sleeping',
        'surprise': 'surprised',
        'shock': 'surprised',
        'think': 'thinking',
        'hm': 'thinking',
        'pouting': 'pout',
        'mad': 'angry'
    };
    const finalExpression = aliases[expression.toLowerCase()] || expression;

    const path = `/static/misakacipher/expressions/misakacipher_${finalExpression}.png`;
    const tempImg = new Image();
    tempImg.onload = () => { img.src = path; };
    tempImg.onerror = () => { img.src = "/static/misakacipher/expressions/misakacipher_default.png"; };
    tempImg.src = path;

    // Persistence
    localStorage.setItem('misaka_last_expression', expression);
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

    // Persistence
    localStorage.setItem('misaka_last_mood', mood);

    // Sync particle sphere colour to current mood
    if (window.ParticleSphere) {
        const moodColors = {
            calm:       [0,   217, 255],
            happy:      [255, 185,   0],
            intense:    [160,  60, 255],
            reflective: [0,   180, 150],
            danger:     [255,  60,  30],
            mystery:    [220,  60, 120]
        };
        const [r, g, b] = moodColors[mood] || moodColors.calm;
        ParticleSphere.setColor(r, g, b);
    }
}

/**
 * Toggle between character image and particle sphere.
 * @param {boolean} hideCharacter — true = show sphere, false = show image
 */
function applyCharacterMode(hideCharacter) {
    const avatarContainer = document.querySelector('.avatar-container');
    const sphereCanvas    = document.getElementById('misaka-particle-sphere');
    if (!avatarContainer || !sphereCanvas) return;

    if (hideCharacter) {
        avatarContainer.classList.add('sphere-mode');
        // Initialise sphere on first activation
        if (window.ParticleSphere) {
            ParticleSphere.setVisible(true);
            if (!sphereCanvas._sphereInited) {
                ParticleSphere.init(sphereCanvas);
                sphereCanvas._sphereInited = true;
            }
        }
    } else {
        avatarContainer.classList.remove('sphere-mode');
        if (window.ParticleSphere) ParticleSphere.setVisible(false);
    }
}

// ===== PROACTIVE MESSAGING SYSTEM =====
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
    // Prevent multiple timers from running
    if (_proactiveSessionTimer) {
        clearTimeout(_proactiveSessionTimer);
        _proactiveSessionTimer = null;
    }

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

    if (!enabled) {
        console.log('[Misaka] Proactive scheduler disabled.');
        return;
    }

    // --- Startup check ---
    const hoursSince = await _getHoursSinceLastMessage();
    if (hoursSince !== null && hoursSince >= startupHours) {
        if (Math.random() * 100 < startupChance) {
            const delay = _randomBetween(delayMin, delayMax) * 1000;
            console.log(`[Misaka] Startup message scheduled in ${(_randomBetween(delayMin, delayMax)).toFixed(2)} seconds (Hours since: ${hoursSince.toFixed(2)})`);
            setTimeout(() => triggerProactiveMessage('startup', hoursSince), delay);
        }
    }

    // --- Session check-in loop ---
    function scheduleNextSession() {
        const intervalMinVal = Math.max(1, intervalMin);
        const intervalMaxVal = Math.max(intervalMinVal, intervalMax);
        const interval = _randomBetween(intervalMinVal, intervalMaxVal) * 60000;

        console.log(`[Misaka] Proactive session scheduled in ${(interval / 60000).toFixed(2)} minutes.`);

        _proactiveSessionTimer = setTimeout(async () => {
            if (Math.random() * 100 < sessionChance) {
                await triggerProactiveMessage('session', 0);
            }
            scheduleNextSession();
        }, interval);
    }
    scheduleNextSession();
}

/**
 * Temporarily pauses the proactive scheduler while the user is typing.
 * Restarts the scheduler after a period of inactivity if the user doesn't send a message.
 */
function pauseProactiveForTyping() {
    if (_proactiveSessionTimer) {
        console.log('[Misaka] User is typing... pausing proactive scheduler.');
        clearTimeout(_proactiveSessionTimer);
        _proactiveSessionTimer = null;
    }

    if (_typingTimeout) clearTimeout(_typingTimeout);

    // If they stop typing for 45 seconds without sending, resume the scheduler
    _typingTimeout = setTimeout(() => {
        console.log('[Misaka] Typing idle detected, resuming scheduler.');
        startProactiveScheduler();
    }, 45000);
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
        const misakaPanel = document.getElementById('misaka-cipher-panel');
        const isMisakaVisible = misakaPanel && misakaPanel.classList.contains('active') &&
            misakaPanel.offsetParent !== null;

        if (isMisakaVisible) {
            // Deliver directly
            if (data.mood) updateMisakaMood(data.mood);
            await addAssistantMessageTyped(data.response, data.attachments);
            misakaChatHistory.push({ role: 'assistant', content: data.response, attachments: data.attachments });
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
        await addAssistantMessageTyped(data.response, data.attachments);
        misakaChatHistory.push({ role: 'assistant', content: data.response, attachments: data.attachments });
        if (misakaChatHistory.length > misakaMaxHistory) {
            misakaChatHistory = misakaChatHistory.slice(-misakaMaxHistory);
        }
    }, 800);
}

// ===== FILE ATTACHMENT =====

_misakaAttachedFile = null; // { name, file }

async function handleMisakaFileSelected(e) {
    const file = e.target.files[0];
    if (!file) return;

    _misakaAttachedFile = { name: file.name, file };

    const pill = document.getElementById('misaka-attach-pill');
    const pillName = document.getElementById('misaka-attach-name');
    if (pill && pillName) {
        pillName.textContent = file.name;
        pill.style.display = 'flex';
    }

    // Reset input so same file can be reselected
    e.target.value = '';
}

function clearMisakaAttachment() {
    _misakaAttachedFile = null;
    const pill = document.getElementById('misaka-attach-pill');
    if (pill) pill.style.display = 'none';
}

window.clearMisakaAttachment = clearMisakaAttachment;

// ── Voice Output ──────────────────────────────────────────────────────────────

let _misakaVoiceEnabled = false;
let _misakaAudio = null;

function toggleMisakaVoice() {
    _misakaVoiceEnabled = !_misakaVoiceEnabled;
    const btn = document.getElementById('misaka-voice-toggle');
    const opts = document.getElementById('misaka-voice-options');
    if (btn) {
        btn.querySelector('i').className = _misakaVoiceEnabled ? 'fas fa-volume-up' : 'fas fa-volume-mute';
        btn.classList.toggle('voice-active', _misakaVoiceEnabled);
    }
    if (opts) opts.style.display = _misakaVoiceEnabled ? 'flex' : 'none';
    if (_misakaVoiceEnabled) loadMisakaTTSModels();
    if (window.prefs) prefs.set('misakacipher.voice_enabled', _misakaVoiceEnabled);
}

async function loadMisakaTTSModels() {
    const sel = document.getElementById('misaka-voice-model');
    if (!sel) return;
    try {
        const res = await fetch('/api/audio/local/models/tts-for-dropdown');
        const data = await res.json();
        const providers = data.providers || [];

        const savedModel = window.prefs ? prefs.get('misakacipher.voice_model', '') : '';
        const current = sel.value;

        // Rebuild — keep the placeholder <option value="">
        while (sel.options.length > 1) sel.remove(1);

        providers.forEach(prov => {
            const group = document.createElement('optgroup');
            group.label = prov.name;
            prov.models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m.id;
                const loadedHint = m.loaded ? '' : ' (not loaded)';
                opt.textContent = (m.name || m.id) + loadedHint;
                opt.disabled = !m.loaded;
                group.appendChild(opt);
            });
            sel.appendChild(group);
        });

        // Restore saved / current selection (only enabled options)
        const restore = savedModel || current;
        const match = [...sel.options].find(o => o.value === restore && !o.disabled);
        if (match) {
            sel.value = match.value;
        } else {
            // Auto-select the first loaded model
            const first = [...sel.options].find(o => o.value && !o.disabled);
            if (first) sel.value = first.value;
        }

        if (sel.value) loadMisakaVoiceOptions();
    } catch (e) {
        console.warn('[Misaka Voice] Failed to load TTS models:', e);
    }
}

async function loadMisakaVoiceOptions() {
    const modelSel = document.getElementById('misaka-voice-model');
    const voiceSel = document.getElementById('misaka-voice-id');
    if (!modelSel || !voiceSel) return;
    const modelId = modelSel.value;
    if (!modelId) return;
    if (window.prefs) prefs.set('misakacipher.voice_model', modelId);
    try {
        const res = await fetch(`/api/audio/local/voices/${modelId}`);
        const data = await res.json();
        const voices = data.voices || [];
        while (voiceSel.options.length > 1) voiceSel.remove(1);
        voices.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.id;
            opt.textContent = v.name || v.id;
            voiceSel.appendChild(opt);
        });
        const savedVoice = window.prefs ? prefs.get('misakacipher.voice_id', '') : '';
        if (savedVoice && [...voiceSel.options].some(o => o.value === savedVoice)) {
            voiceSel.value = savedVoice;
        }
    } catch (e) {
        console.warn('[Misaka Voice] Failed to load voices:', e);
    }
}

function _cleanForSpeech(text) {
    // Strip memory JSON blobs
    text = text.replace(/\n?\{[^{]*"(?:user_info|recent_observations|base_info|synthesis_notes)"[\s\S]*?\}/g, '');
    return text
        .replace(/\[Emotion:.*?\]/gi, '')
        .replace(/\[Mood:.*?\]/gi, '')
        .replace(/\[msg_break\]/gi, '')
        .replace(/```[\s\S]*?```/g, ' ')
        .replace(/`[^`]+`/g, '')
        .replace(/\*\*(.*?)\*\*/g, '$1')
        .replace(/\*(.*?)\*/g, '$1')
        .replace(/#{1,6}\s*/g, '')
        .replace(/\n+/g, ' ')
        .trim();
}

async function speakMisakaResponse(rawText) {
    if (!_misakaVoiceEnabled) return;
    const modelSel = document.getElementById('misaka-voice-model');
    const voiceSel = document.getElementById('misaka-voice-id');
    if (!modelSel || !modelSel.value) return;

    // Stop any currently playing audio
    if (_misakaAudio) { _misakaAudio.pause(); _misakaAudio = null; }

    // Save voice choice to prefs
    if (window.prefs && voiceSel && voiceSel.value) prefs.set('misakacipher.voice_id', voiceSel.value);

    // Split by [msg_break] and speak each segment in order
    const segments = rawText
        .split(/\[msg_break\]/gi)
        .map(s => _cleanForSpeech(s))
        .filter(s => s.length > 2);  // skip near-empty segments

    for (const text of segments) {
        if (!_misakaVoiceEnabled) break;
        try {
            const res = await fetch('/api/audio/local/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text,
                    model_id: modelSel.value,
                    voice_id: voiceSel ? voiceSel.value || null : null,
                    language: 'en',
                    device: 'cuda',
                }),
            });
            const data = await res.json();
            if (!data.success || !data.audio) continue;
            await new Promise(resolve => {
                _misakaAudio = new Audio(data.audio);
                _misakaAudio.onended = resolve;
                _misakaAudio.onerror = resolve;
                _misakaAudio.play();
            });
            _misakaAudio = null;
        } catch (e) {
            console.warn('[Misaka Voice] TTS generation failed:', e);
        }
    }
}

window.toggleMisakaVoice = toggleMisakaVoice;
window.loadMisakaTTSModels = loadMisakaTTSModels;
window.loadMisakaVoiceOptions = loadMisakaVoiceOptions;
window.speakMisakaResponse = speakMisakaResponse;

window.initializeMisakaCipher = initializeMisakaCipher;
window.refreshMisakaMemory = refreshMisakaMemory;
window.deliverQueuedProactiveMessage = deliverQueuedProactiveMessage;
