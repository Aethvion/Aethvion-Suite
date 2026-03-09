/**
 * Misaka Cipher Personal Assistant logic
 */

document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('misaka-assistant-container');
    const avatar = document.getElementById('misaka-avatar');
    const imgBubble = document.getElementById('misaka-img');
    const imgDialog = document.getElementById('misaka-img-dialog');
    const chatWindow = document.getElementById('misaka-chat-window');
    const closeBtn = document.getElementById('misaka-close-btn');
    const messagesArea = document.getElementById('misaka-messages');
    const input = document.getElementById('misaka-input');
    const sendBtn = document.getElementById('misaka-send-btn');

    const IMG_DEFAULT = '/static/misakacipher/expressions/misakacipher_default.png';
    const IMG_WINK = '/static/misakacipher/expressions/misakacipher_wink.png';

    // State
    let isAssistantEnabled = false;
    let typingSpeed = 20; // Default typing speed
    let contextHistoryLimit = 5; // Default pairs
    let messageHistory = [];
    let currentEmotion = 'default';

    // Load initial settings
    async function loadAssistantSettings() {
        try {
            const res = await fetch('/api/preferences');
            if (res.ok) {
                const data = await res.json();
                if (data.assistant) {
                    isAssistantEnabled = data.assistant.enabled !== undefined ? data.assistant.enabled : true;
                    typingSpeed = data.assistant.typing_speed !== undefined ? data.assistant.typing_speed : 20;
                    contextHistoryLimit = data.assistant.context_limit !== undefined ? data.assistant.context_limit : 5;

                    if (data.assistant.position) {
                        let pos = data.assistant.position;
                        // Clamp initial position to current window size in case it changed
                        pos = clampBounds(pos.left, pos.top);

                        container.style.bottom = 'auto';
                        container.style.right = 'auto';
                        container.style.left = pos.left + 'px';
                        container.style.top = pos.top + 'px';
                    }
                } else {
                    isAssistantEnabled = true; // default
                }
            } else {
                isAssistantEnabled = true;
            }
        } catch (e) {
            console.error("Failed to load assistant preferences", e);
            isAssistantEnabled = true;
        }

        if (isAssistantEnabled) {
            container.classList.remove('hidden');
        } else {
            container.classList.add('hidden');
        }
    }

    // Draggable Logic
    let isDragging = false;
    let dragStartX, dragStartY;
    let initialLeft, initialTop;
    let dragThreshold = 5;
    let totalMoved = 0;

    function clampBounds(left, top) {
        const bubbleSize = 80;
        const margin = 10;
        const maxX = window.innerWidth - bubbleSize - margin;
        const maxY = window.innerHeight - bubbleSize - margin;

        return {
            left: Math.max(margin, Math.min(left, maxX)),
            top: Math.max(margin, Math.min(top, maxY))
        };
    }

    avatar.addEventListener('pointerdown', (e) => {
        isDragging = false;
        totalMoved = 0;
        dragStartX = e.clientX;
        dragStartY = e.clientY;

        const rect = container.getBoundingClientRect();
        initialLeft = rect.left;
        initialTop = rect.top;

        avatar.setPointerCapture(e.pointerId);
    });

    avatar.addEventListener('pointermove', (e) => {
        if (e.buttons === 0) return;

        const dx = e.clientX - dragStartX;
        const dy = e.clientY - dragStartY;
        totalMoved += Math.sqrt(dx * dx + dy * dy);

        if (!isDragging && totalMoved > dragThreshold) {
            isDragging = true;
        }

        if (isDragging) {
            const pos = clampBounds(initialLeft + dx, initialTop + dy);
            container.style.bottom = 'auto';
            container.style.right = 'auto';
            container.style.left = pos.left + 'px';
            container.style.top = pos.top + 'px';
        }
    });

    avatar.addEventListener('pointerup', async (e) => {
        avatar.releasePointerCapture(e.pointerId);

        if (isDragging) {
            const rect = container.getBoundingClientRect();
            const position = {
                left: Math.round(rect.left),
                top: Math.round(rect.top)
            };

            try {
                await fetch('/api/preferences/assistant.position', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: 'assistant.position', value: position })
                });
            } catch (err) {
                console.error("Failed to save assistant position:", err);
            }

            setTimeout(() => { isDragging = false; }, 10);
        }
    });

    // Toggle Chat Window
    avatar.addEventListener('click', (e) => {
        if (isDragging) return;

        // Smart Position Check
        const rect = container.getBoundingClientRect();
        const windowWidth = 650;
        const windowHeight = 250;
        const bubbleSize = 80;
        let pivotX = 'left';
        let pivotY = 'top';

        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;

        // Horizontal logic - Check fit
        const canFitRight = (rect.left + windowWidth <= viewportWidth);
        const canFitLeft = (rect.right - windowWidth >= 0);

        if (canFitRight) {
            // Space on right - anchor left edge of window to left edge of bubble
            chatWindow.style.left = `0px`;
            pivotX = 'left';
        } else if (canFitLeft) {
            // Space on left - anchor right edge of window to right edge of bubble
            chatWindow.style.left = `-${windowWidth - bubbleSize}px`;
            pivotX = 'right';
        } else {
            // Narrow screen logic - simpler fallback
            if (rect.left > (viewportWidth / 2)) {
                chatWindow.style.left = `-${windowWidth - bubbleSize}px`;
                pivotX = 'right';
            } else {
                chatWindow.style.left = `0px`;
                pivotX = 'left';
            }
        }

        // Vertical logic - Check fit (Vertical margin is simpler as windowHeight is small)
        if (rect.top > windowHeight) {
            // Space on top - anchor bottom edge of window to bottom edge of bubble
            chatWindow.style.top = `-${windowHeight - bubbleSize}px`;
            pivotY = 'bottom';
        } else {
            // Space on bottom - anchor top edge of window to top edge of bubble
            chatWindow.style.top = '0px';
            pivotY = 'top';
        }

        chatWindow.style.transformOrigin = `${pivotY} ${pivotX}`;

        chatWindow.classList.remove('collapsed');
        avatar.classList.add('hidden');
        input.focus();
        scrollToBottom();
    });

    closeBtn.addEventListener('click', () => {
        chatWindow.classList.add('collapsed');
        avatar.classList.remove('hidden');
    });

    // Set Emotion Image
    function setEmotion(emotion) {
        currentEmotion = emotion;
        const url = `/static/misakacipher/expressions/misakacipher_${emotion}.png`;
        if (imgBubble) imgBubble.src = url;
        if (imgDialog) imgDialog.src = url;
    }

    // Winking Animation
    function triggerWink(duration = 1000) {
        if (imgBubble) imgBubble.src = IMG_WINK;
        if (imgDialog) imgDialog.src = IMG_WINK;
        setTimeout(() => {
            setEmotion(currentEmotion); // Restore current emotion instead of default
        }, duration);
    }

    // Scroll to bottom
    function scrollToBottom() {
        messagesArea.scrollTop = messagesArea.scrollHeight;
    }

    // Add message to UI
    function appendMessage(role, content, asMarkdown = false) {
        const div = document.createElement('div');
        div.className = `misaka-d-message ${role}`;

        if (asMarkdown && typeof marked !== 'undefined') {
            div.innerHTML = marked.parse(content);
        } else {
            div.textContent = content;
        }

        // Target specifically code blocks to highlight them if highlight.js exists
        if (asMarkdown && typeof hljs !== 'undefined') {
            div.querySelectorAll('pre code').forEach((block) => {
                hljs.highlightElement(block);
            });
        }

        messagesArea.appendChild(div);
        scrollToBottom();
    }

    // Add typing effect message
    function typeMessage(role, content, asMarkdown = false, finalEmotion = 'default') {
        const div = document.createElement('div');
        div.className = `misaka-d-message ${role}`;
        messagesArea.appendChild(div);
        scrollToBottom();

        // Apply target emotion immediately so it shows before typing begins
        setEmotion(finalEmotion);

        let delayMs = 100 - typingSpeed;
        if (delayMs <= 0) {
            if (asMarkdown && typeof marked !== 'undefined') {
                div.innerHTML = marked.parse(content);
            } else {
                div.textContent = content;
            }
            if (asMarkdown && typeof hljs !== 'undefined') {
                div.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
            }
            if (finalEmotion === 'default' || finalEmotion.startsWith('happy') || finalEmotion === 'wink') {
                triggerWink(1500);
            }
            scrollToBottom();
            return Promise.resolve();
        }

        // Typing animation state
        const isNegative = ['angry', 'crying', 'pout', 'error', 'exhausted'].includes(finalEmotion);
        let talkingFaces = ['default', 'happy_closedeyes_smilewithteeth', 'happy_closedeyes_widesmile', 'thinking', 'wink'];

        if (!isNegative && finalEmotion !== 'default') {
            talkingFaces = [finalEmotion, finalEmotion, finalEmotion, 'happy_closedeyes_smilewithteeth', 'happy_closedeyes_widesmile'];
        }

        // Pre-render the HTML if needed
        let sourceContainer = document.createElement('div');
        if (asMarkdown && typeof marked !== 'undefined') {
            sourceContainer.innerHTML = marked.parse(content);
        } else {
            sourceContainer.textContent = content;
        }

        // Calculate expression change logic
        const totalChars = sourceContainer.textContent.length;
        const numChanges = totalChars < 50 ? 2 : totalChars < 200 ? 3 : totalChars < 500 ? 4 : 6;
        const expressionInterval = Math.max(10, Math.floor(totalChars / numChanges));
        let processedChars = 0;

        // Recursive reveal function
        async function revealNodes(source, target) {
            for (const node of Array.from(source.childNodes)) {
                if (node.nodeType === Node.TEXT_NODE) {
                    const text = node.textContent;
                    const textNode = document.createTextNode('');
                    target.appendChild(textNode);

                    for (let i = 0; i < text.length; i++) {
                        textNode.textContent += text[i];
                        processedChars++;

                        // Scroll and expressions
                        scrollToBottom();
                        if (processedChars % expressionInterval === 0 && processedChars < totalChars - 5) {
                            if (!isNegative) {
                                let randomFace = talkingFaces[Math.floor(Math.random() * talkingFaces.length)];
                                while (randomFace === currentEmotion && talkingFaces.length > 1) {
                                    randomFace = talkingFaces[Math.floor(Math.random() * talkingFaces.length)];
                                }
                                setEmotion(randomFace);
                            } else {
                                setEmotion(processedChars % (expressionInterval * 2) === 0 ? 'pout' : finalEmotion);
                            }
                        }

                        // Wait for typing delay
                        if (delayMs > 0) {
                            await new Promise(r => setTimeout(r, delayMs));
                        }
                    }
                } else if (node.nodeType === Node.ELEMENT_NODE) {
                    const clone = node.cloneNode(false); // shallow clone
                    target.appendChild(clone);
                    await revealNodes(node, clone);
                }
            }
        }

        return new Promise(async (resolve) => {
            await revealNodes(sourceContainer, div);

            // Cleanup / Finale
            setEmotion(finalEmotion);
            if (asMarkdown && typeof hljs !== 'undefined') {
                div.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
            }

            if (!isNegative && (finalEmotion === 'default' || finalEmotion.startsWith('happy') || finalEmotion === 'wink')) {
                triggerWink(1500);
            }

            scrollToBottom();
            resolve();
        });
    }

    // Add typing indicator
    function showTyping() {
        const div = document.createElement('div');
        div.id = 'misaka-typing-indicator';
        div.className = 'misaka-typing';
        div.innerHTML = `
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        `;
        messagesArea.appendChild(div);
        scrollToBottom();
    }

    function removeTyping() {
        const indicator = document.getElementById('misaka-typing-indicator');
        if (indicator) {
            indicator.remove();
        }
    }

    // Handle sending message
    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        input.value = '';
        input.disabled = true;
        sendBtn.disabled = true;

        // User message
        appendMessage('user', text);
        messageHistory.push({ role: 'user', content: text });

        // Keep history reasonably short to save tokens (e.g. 5 pairs = 10 messages)
        const maxMessages = contextHistoryLimit * 2;
        if (messageHistory.length > maxMessages) {
            messageHistory = messageHistory.slice(-maxMessages);
        }

        showTyping();

        // Gather current UI context
        let activeTabId = 'unknown';
        let activeTabName = 'Unknown Tab';
        const activePanel = document.querySelector('.main-tab-panel:not([style*="display: none"])');
        if (activePanel) {
            activeTabId = activePanel.id;
            const navBtn = document.querySelector(`.nav-btn.active`);
            if (navBtn) {
                activeTabName = navBtn.textContent.trim();
            }
        }

        try {
            const res = await fetch('/api/assistant/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    messages: messageHistory,
                    ui_context: {
                        active_tab_id: activeTabId,
                        active_tab_name: activeTabName
                    }
                })
            });

            removeTyping();

            if (res.ok) {
                const data = await res.json();
                let responseText = data.response;

                // Parse emotion tag: [Emotion: <emotion>]
                let targetEmotion = 'default';
                // Globally replace ALL emotion tags so they don't leak into the typed response
                const emotionRegex = /\[Emotion:\s*([a-zA-Z0-9_]+)\]/ig;
                let match;
                while ((match = emotionRegex.exec(responseText)) !== null) {
                    targetEmotion = match[1].toLowerCase(); // capture the very last emotion tag specified
                }
                // Strip all emotion tags out
                responseText = responseText.replace(/\[Emotion:\s*[a-zA-Z0-9_]+\]/ig, '').trim();

                // Parse dashboard tab switch: [SwitchTab: tab_id]
                const switchTabRegex = /\[SwitchTab:\s*([a-zA-Z0-9_-]+)\]/ig;
                let switchMatch;
                let switchTarget = null;
                while ((switchMatch = switchTabRegex.exec(responseText)) !== null) {
                    switchTarget = switchMatch[1].toLowerCase();
                }

                // Parse dashboard sub-tab switch: [SwitchSubTab: subtab_id]
                const switchSubTabRegex = /\[SwitchSubTab:\s*([a-zA-Z0-9_-]+)\]/ig;
                let subMatch;
                let switchSubTarget = null;
                while ((subMatch = switchSubTabRegex.exec(responseText)) !== null) {
                    switchSubTarget = subMatch[1].toLowerCase();
                }

                // Strip all Switch tags from display text
                responseText = responseText.replace(/\[SwitchTab:\s*[a-zA-Z0-9_-]+\]/ig, '').trim();
                responseText = responseText.replace(/\[SwitchSubTab:\s*[a-zA-Z0-9_-]+\]/ig, '').trim();

                messageHistory.push({ role: 'assistant', content: responseText }); // Save cleaned text
                await typeMessage('misaka', responseText, true, targetEmotion);

                // Execute tab switch AFTER message display
                if (switchSubTarget) {
                    // Mapping sub-tabs to their parent main tabs
                    const settingsSubTabs = ['assistant', 'system', 'env', 'providers', 'profiles'];
                    if (settingsSubTabs.includes(switchSubTarget)) {
                        if (typeof ensureTabAndSubTab === 'function') {
                            ensureTabAndSubTab('settings', switchSubTarget);
                        }
                    }
                } else if (switchTarget) {
                    if (typeof switchDashboardTab === 'function') {
                        switchDashboardTab(switchTarget);
                    }
                }
            } else {
                const err = await res.json();
                appendMessage('system', `Error: ${err.detail || 'Failed to connect.'}`);
                setEmotion('error');
                // Don't save failed attempts to context
                messageHistory.pop();
            }

        } catch (error) {
            console.error("Assistant chat error:", error);
            removeTyping();
            appendMessage('system', 'Connection error. Is the server running?');
            setEmotion('error');
            messageHistory.pop();
        }

        input.disabled = false;
        sendBtn.disabled = false;
        input.focus();
    }

    // Event Listeners for Input
    sendBtn.addEventListener('click', sendMessage);
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });

    // Listen for custom events to toggle visibility from settings
    window.addEventListener('assistantSettingsUpdated', (e) => {
        if (e.detail) {
            if (e.detail.enabled !== undefined) {
                isAssistantEnabled = e.detail.enabled;
                if (isAssistantEnabled) {
                    container.classList.remove('hidden');
                    triggerWink();
                } else {
                    container.classList.add('hidden');
                    chatWindow.classList.add('collapsed');
                    avatar.classList.remove('hidden');
                }
            }
            if (e.detail.typing_speed !== undefined) {
                typingSpeed = e.detail.typing_speed;
            }
            if (e.detail.context_limit !== undefined) {
                contextHistoryLimit = e.detail.context_limit;
            }
        }
    });

    // Initialize after system is ready (splash screen finished)
    let initialized = false;
    const init = () => {
        if (initialized) return;
        initialized = true;
        loadAssistantSettings();
    };

    window.addEventListener('systemReady', init);

    // Fallback: Initialize after 5 seconds if systemReady event is not received
    // (Useful for dev/debug or if splash screen is disabled)
    setTimeout(init, 5000);
});

/**
 * Navigate the dashboard to a specific tab by its ID.
 * Calls the global switchMainTab from core.js.
 */
function switchDashboardTab(tabId) {
    if (typeof switchMainTab === 'function') {
        switchMainTab(tabId);
    } else {
        console.warn(`[Assistant] switchMainTab not available, cannot switch to: ${tabId}`);
    }
}
