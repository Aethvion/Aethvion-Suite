// ===== THREAD MANAGEMENT =====

window.currentThreadId = 'default';
window.threads = {};
let threadMessages = {};
let activeTasksByThread = {}; // taskId -> threadId
let isTypingIndicatorVisible = false; // Track typing state globally
let typingInterval = null;
let typingDotsCount = 1;

const typingMessages = [
    "working",
    "searching",
    "Coding",
    "Calculating",
    "Counting Sheep",
    "Decrypting reality",
    "Counting to infinity",
    "Asking rubber duck for advice",
    "Herding digital cats"
];

// Initialize thread management
// Initialize thread management
function initThreadManagement() {
    // Start with no selected thread
    currentThreadId = null;

    // Disable input initially
    toggleChatInput(false);

    // Load threads from API
    loadThreads();

    // Set up    // Listeners
    document.getElementById('new-thread-button').addEventListener('click', createNewThread);
    const headerNewBtn = document.getElementById('header-new-thread-btn');
    if (headerNewBtn) headerNewBtn.addEventListener('click', createNewThread);

    const activeThreadTitle = document.getElementById('active-thread-title');
    if (activeThreadTitle) {
        activeThreadTitle.addEventListener('dblclick', () => {
            if (!currentThreadId || currentThreadId === 'default') return;
            const thread = threads[currentThreadId];
            if (!thread) return;
            activeThreadTitle.contentEditable = 'true';
            activeThreadTitle.focus();
            const r = document.createRange();
            r.selectNodeContents(activeThreadTitle);
            window.getSelection().removeAllRanges();
            window.getSelection().addRange(r);
            const commit = () => {
                activeThreadTitle.contentEditable = 'false';
                const t = activeThreadTitle.textContent.trim();
                if (t && t !== thread.title) editThreadTitle(thread.id, t);
                else activeThreadTitle.textContent = thread.title;
            };
            activeThreadTitle.addEventListener('blur', commit, { once: true });
            activeThreadTitle.addEventListener('keydown', (ev) => {
                if (ev.key === 'Enter')  { ev.preventDefault(); activeThreadTitle.blur(); }
                if (ev.key === 'Escape') { activeThreadTitle.textContent = thread.title; activeThreadTitle.blur(); }
            });
        });
        activeThreadTitle.style.cursor = 'text';
        activeThreadTitle.title = 'Double-click to edit title';
    }

    // Global Settings Listeners
    ['global-ctx-mode', 'global-ctx-window'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('change', () => saveGlobalChatSettings());
    });

    // Load persisted global settings
    loadGlobalChatSettings();

    // Bind Send Button explicitly
    const sendButton = document.getElementById('send-button');
    if (sendButton) {
        const newBtn = sendButton.cloneNode(true);
        sendButton.parentNode.replaceChild(newBtn, sendButton);
        newBtn.addEventListener('click', sendMessage);
    }

    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        // Clone/replace is risky for input if it has other bindings, but for now we just add listener
        // Actually, let's just add the listener. The app.js one is commented out.
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }



    // Set up thread list click delegation
    document.getElementById('threads-list').addEventListener('click', (e) => {
        const threadItem = e.target.closest('.thread-item');
        if (threadItem) {
            const threadId = threadItem.dataset.threadId;
            switchThread(threadId);
        }
    });

    // Periodically refresh thread status
    setInterval(refreshThreadStatus, 3000);

    // Wire thread search
    initThreadSearch();
}

// Load threads from API
async function loadThreads() {
    try {
        const response = await fetch('/api/tasks/threads');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();

        if (!data || !Array.isArray(data.threads)) {
            console.warn('Invalid thread data received from server:', data);
            return;
        }

        // Merge with existing threads (don't overwrite local-only threads like 'default')
        data.threads.forEach(thread => {
            // Default mode if not set
            if (!thread.mode) thread.mode = 'auto';
            if (thread.is_pinned === undefined) thread.is_pinned = false;

            if (!threads[thread.id]) {
                threads[thread.id] = thread;
                threadMessages[thread.id] = []; // Initialize message storage
            } else {
                // Update existing thread data
                threads[thread.id].mode = thread.mode;
                threads[thread.id].is_pinned = thread.is_pinned;
            }
        });

        renderThreadList();

        // Auto-select first thread if none selected, or if currently on an agent thread
        const onAgentThread = currentThreadId && currentThreadId.startsWith('agents-');
        if (!currentThreadId || currentThreadId === 'default' || onAgentThread) {
            const threadKeys = Object.keys(threads).filter(id => !id.startsWith('agents-'));
            if (threadKeys.length > 0) {
                // Sort by pinned first, then by date desc
                const sorted = threadKeys.map(id => threads[id]).sort((a, b) => {
                    if (a.is_pinned && !b.is_pinned) return -1;
                    if (!a.is_pinned && b.is_pinned) return 1;
                    return new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at);
                });
                switchThread(sorted[0].id);
            }
        }

    } catch (error) {
        console.error('Failed to load threads:', error);
    }
}

// Create new thread
async function createNewThread() {
    // Determine Thread Count from localStorage for instant creation
    let threadCount = parseInt(localStorage.getItem('total_threads_created')) || 0;
    threadCount += 1;
    localStorage.setItem('total_threads_created', threadCount);

    const title = `Thread ${threadCount}`;
    const threadId = `thread-${Date.now()}`;

    // Create thread locally
    threads[threadId] = {
        id: threadId,
        title: title,
        task_ids: [],
        mode: 'chat_only', // Legacy field, we'll use global toggle now
        settings: {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        is_pinned: false
    };

    // Initialize message storage for new thread
    threadMessages[threadId] = [];

    // Create thread on backend immediately so Mode toggles work
    try {
        await fetch('/api/tasks/thread/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                thread_id: threadId,
                title: title,
                mode: 'chat_only'
            })
        });
    } catch (e) {
        console.error("Failed to create thread on backend:", e);
    }

    renderThreadList();
    switchThread(threadId);
}

// Switch to a different thread
function switchThread(threadId) {
    if (currentThreadId === threadId) return;

    currentThreadId = threadId;
    isSettingsPanelOpen = false; // Reset settings state for new thread

    // Enable input when thread is selected
    toggleChatInput(true);

    // Hide typing indicator when switching, it will be re-shown by loadThreadMessages if needed
    hideTypingIndicator();

    // Update active thread in UI INSTANTLY
    document.querySelectorAll('.thread-item').forEach(item => {
        const isActive = item.dataset.threadId === threadId;
        item.classList.toggle('active', isActive);
    });

    // Update chat header
    const thread = threads[threadId];
    if (thread) {
        document.getElementById('active-thread-title').textContent = thread.title;
    }

    // Load and render messages
    loadThreadMessages(threadId).then(() => {
        renderThreadMessages();
    });

    // Update terminal visibility
    if (typeof updateTerminalVisibility === 'function') {
        updateTerminalVisibility();
    }
}

function toggleChatInput(enabled) {
    const input = document.getElementById('chat-input');
    const button = document.getElementById('send-button');

    if (input) {
        input.disabled = !enabled;
        if (button) button.disabled = !enabled;

        if (!enabled) {
            input.placeholder = "Select a thread to start chatting...";
            input.value = '';
            input.style.height = ''; // Reset height
        } else {
            input.placeholder = "Ask me anything... (e.g., 'Analyze TSLA stock outlook')";
        }
    }
}

// Render messages for current thread
function renderThreadMessages() {
    const chatMessages = document.getElementById('chat-messages');
    chatMessages.innerHTML = '';

    // Get messages for current thread
    const messages = threadMessages[currentThreadId] || [];

    // Render each message
    let lastDate = null;
    messages.forEach(msg => {
        // Date Divider
        const timestamp = msg.timestamp || new Date().toISOString();
        const msgDateStr = new Date(timestamp).toDateString();
        if (msgDateStr !== lastDate) {
            const divider = document.createElement('div');
            divider.className = 'chat-date-divider';
            const displayDate = msgDateStr === new Date().toDateString() ? 'Today' : msgDateStr;
            divider.innerHTML = `<span>${displayDate}</span>`;
            chatMessages.appendChild(divider);
            lastDate = msgDateStr;
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${msg.role}-message`;
        if (msg.taskId) {
            messageDiv.dataset.taskId = msg.taskId;
        }
        messageDiv.innerHTML = msg.html;
        chatMessages.appendChild(messageDiv);
    });

    // Re-append typing indicator if visible and we are on the right thread
    if (isTypingIndicatorVisible) {
        showTypingIndicator(true); // Internal call to just append/show
    }

    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Add message to specific thread
function addMessageToThread(threadId, role, content, taskId = null, taskData = null, attachments = null, timestamp = null) {
    // Ensure thread message storage exists
    if (!threadMessages[threadId]) {
        threadMessages[threadId] = [];
    }

    if (!attachments && taskData && taskData.metadata && taskData.metadata.attached_files) {
        attachments = taskData.metadata.attached_files;
    }

    let messageContent = '';
    let attachmentsHtml = '';
    if (attachments && attachments.length > 0) {
        attachmentsHtml += '<div class="message-attachments" style="margin-top:8px; margin-bottom: 4px; display:flex; flex-wrap:wrap; gap:8px;">';
        attachments.forEach(att => {
            if (att.is_image && att.url) {
                attachmentsHtml += `<img src="${att.url}" class="chat-attached-image" style="max-width:100%; max-height:250px; border-radius:8px; object-fit:contain;">`;
            } else if (att.filename) {
                attachmentsHtml += `<div class="chat-attached-file-pill" style="font-size:0.85em; padding:4px 8px; background:rgba(255,255,255,0.1); border-radius:4px;">📄 ${att.filename}</div>`;
            }
        });
        attachmentsHtml += '</div>';
    }

    if (role === 'user') {
        messageContent = `<strong>You:</strong> <div style="display:inline-block; width:100%;">${content}</div>${attachmentsHtml}`;
    } else if (role === 'assistant') {
        let parsedContent = content;
        try {
            if (typeof marked !== 'undefined' && typeof marked.parse === 'function') {
                parsedContent = marked.parse(content);
            } else {
                console.warn("Marked library not loaded, using raw text");
            }
        } catch (e) {
            console.error("Markdown parsing failed:", e);
            parsedContent = content; // Fallback to raw text
        }

        // Build model label if available
        const actualModel = taskData?.metadata?.actual_model || taskData?.result?.model_id;
        const isAutoRouted = taskData?.metadata?.selected_model === 'auto';
        let modelLabel = '';
        if (actualModel) {
            const display = isAutoRouted ? `${actualModel}*` : actualModel;
            const title = isAutoRouted ? 'Auto-routed model (*)' : 'Selected model';
            modelLabel = `<span class="msg-model-label" title="${title}">${display}</span>`;
        }

        // Wrap in a div to ensure block styles work correctly after the strong tag
        messageContent = `${modelLabel} <strong>Chat:</strong> <div style="display:inline-block; width:100%;">${parsedContent}</div>`;


        // Add expandable task details only for complex tasks (tools used, agents spawned, or auto-routing happened)
        const _isComplexTask = taskData && (
            (taskData.result?.tools_forged  > 0) ||
            (taskData.result?.agents_spawned > 0) ||
            !!(taskData.result?.usage?.routing_reason  || taskData.metadata?.routing_reason)  ||
            !!(taskData.result?.usage?.routed_model    || taskData.metadata?.routed_model)
        );
        if (_isComplexTask) {
            const usage = taskData.result?.usage;
            let usageHtml = '';

            if (usage) {
                // Models breakdown
                let modelsList = '';
                if (usage.models_used) {
                    modelsList = Object.entries(usage.models_used).map(([m, data]) =>
                        `<div>${m} (${data.calls} calls)</div>`
                    ).join('');
                }

                usageHtml = `
                    <div style="margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px solid var(--border);">
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; font-size: 0.8rem;">
                            <div>
                                <strong>Models Used:</strong>
                                <div style="margin-top: 0.2rem; margin-bottom: 0.5rem; color: var(--text);">
                                    ${modelsList || 'None'}
                                </div>
                            </div>
                            <div>
                                <strong>Tokens:</strong>
                                <div style="color: var(--text);">Prompt: ${usage.total_prompt_tokens}</div>
                                <div style="color: var(--text);">Output: ${usage.total_completion_tokens}</div>
                                <div style="font-weight: 600; color: var(--text);">Total: ${usage.total_tokens}</div>
                            </div>
                        </div>
                        <div style="margin-top: 0.5rem; font-size: 0.8rem; border-top: 1px dashed var(--border); padding-top: 0.4rem;">
                            <strong>Estimated Cost:</strong>
                            <span style="float: right; font-family: 'Fira Code', monospace; color: var(--primary);">
                                $${usage.total_cost.toFixed(6)}
                            </span>
                            <div style="font-size: 0.75rem; color: var(--text-secondary);">
                                (In: $${usage.total_input_cost.toFixed(6)} | Out: $${usage.total_output_cost.toFixed(6)})
                            </div>
                        </div>
                    </div>
                `;
            }

            messageContent += `
                <div class="task-details" style="margin-top: 0.5rem; font-size: 0.85rem; color: var(--text-secondary);">
                    <details>
                        <summary style="cursor: pointer;">Task Details</summary>
                        <div style="margin-top: 0.5rem; padding: 0.5rem; background: var(--bg-primary); border-radius: 4px;">
                            <div style="display: flex; justify-content: space-between;">
                                <span><strong>ID:</strong> ${taskData.id}</span>
                                <span><strong>Time:</strong> ${taskData.result?.execution_time?.toFixed(2) || '0.00'}s</span>
                            </div>
                            <div style="margin-top: 0.3rem;"><strong>Worker:</strong> ${taskData.worker_id || 'N/A'}</div>
                            <div style="margin-top: 0.3rem;"><strong>Model:</strong> ${taskData.result?.model_id || taskData.metadata?.actual_model || 'N/A'}</div>
                            <div style="margin-top: 0.3rem;"><strong>Mode:</strong> ${taskData.metadata?.mode || 'N/A'}</div>
                            <div style="margin-top: 0.3rem;"><strong>Model Selection:</strong> ${taskData.metadata?.selected_model === 'auto' ? '⚡ Auto Routing' : (taskData.metadata?.selected_model || 'Default')}</div>
                            ${(taskData.result?.usage?.routing_model || taskData.metadata?.routing_model) ? `<div style="margin-top: 0.3rem;"><strong>Route Picker:</strong> ${taskData.result?.usage?.routing_model || taskData.metadata?.routing_model}</div>` : ''}
                            ${(taskData.result?.usage?.routed_model || taskData.metadata?.routed_model) ? `<div style="margin-top: 0.3rem;"><strong>Routed To:</strong> <span style="color: var(--primary);">${taskData.result?.usage?.routed_model || taskData.metadata?.routed_model}</span></div>` : ''}
                            ${(taskData.result?.usage?.routing_reason || taskData.metadata?.routing_reason) ? `<div style="margin-top: 0.5rem; padding: 0.4rem 0.6rem; background: rgba(0,212,255,0.06); border-left: 3px solid var(--primary); border-radius: 4px; font-style: italic; font-size: 0.78rem; color: var(--text-secondary);">🧠 ${taskData.result?.usage?.routing_reason || taskData.metadata?.routing_reason}</div>` : ''}
                            
                            <!-- Standard Actions Info -->
                            ${taskData.result?.actions_taken?.length > 0 ? `<div style="margin-top: 0.3rem;"><strong>Actions:</strong> ${taskData.result.actions_taken.join(', ')}</div>` : ''}
                            ${taskData.result?.tools_forged?.length > 0 ? `<div style="margin-top: 0.3rem;"><strong>Tools:</strong> ${taskData.result.tools_forged.join(', ')}</div>` : ''}
                            ${taskData.result?.agents_spawned?.length > 0 ? `<div style="margin-top: 0.3rem;"><strong>Agents:</strong> ${taskData.result.agents_spawned.join(', ')}</div>` : ''}
                            
                            <!-- Enhanced Usage Info -->
                            ${usageHtml}
                        </div>
                    </details>
                </div>
            `;
        }
    } else if (role === 'system') {
        messageContent = `<strong>System:</strong> ${content}`;
    } else if (role === 'error') {
        messageContent = `<strong>Error:</strong> ${content}`;
    }

    const html = `<div class="message-content">${messageContent}</div>`;

    // Store message in thread
    threadMessages[threadId].push({
        role: role,
        content: content,
        taskId: taskId,
        taskData: taskData,
        html: html,
        timestamp: timestamp || new Date().toISOString()
    });

    try {
        // If this is the current thread, render it
        if (threadId === currentThreadId) {
            renderThreadMessages();
        }
    } catch (e) {
        console.error("Error rendering messages:", e);
    }
}

// Load messages for a thread from server
async function loadThreadMessages(threadId) {
    try {
        const response = await fetch(`/api/tasks/thread/${threadId}`);

        // Handle 404 for local-only threads (expected and normal)
        if (response.status === 404) {
            // Silently return - local threads don't exist on backend
            return;
        }

        const data = await response.json();
        console.log(`Loaded messages for ${threadId}:`, data); // Debug logging

        // Clear existing messages for this thread
        threadMessages[threadId] = [];

        // Load tasks and their results
        if (data.tasks && data.tasks.length > 0) {
            // Sort by created_at asc for flow
            const sortedTasks = [...data.tasks].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
            
            sortedTasks.forEach(task => {
                const ts = task.created_at || task.updated_at;
                // Add user message
                addMessageToThread(threadId, 'user', task.prompt, task.id, null, null, ts);

                // Add assistant response if completed
                if (task.status === 'completed' && task.result) {
                    addMessageToThread(threadId, 'assistant', task.result.response, task.id, task, null, task.updated_at || ts);
                } else if (task.status === 'failed') {
                    addMessageToThread(threadId, 'error', `Task failed: ${task.error}`, task.id, null, null, task.updated_at || ts);
                }
            });
        }

        // Check if any tasks are still running/queued for this thread
        const hasActiveTasks = data.tasks.some(task => task.status === 'running' || task.status === 'queued');
        if (hasActiveTasks && threadId === currentThreadId) {
            showTypingIndicator();
            // Re-poll for any active tasks
            data.tasks.filter(task => task.status === 'running' || task.status === 'queued').forEach(task => {
                pollTaskStatus(task.id, threadId);
            });
        } else {
            hideTypingIndicator();
        }

    } catch (error) {
        console.error('Failed to load thread messages:', error);
    }
}

// ─── Relative time helper ─────────────────────────────────────────
function relativeTime(dateStr) {
    if (!dateStr) return '';
    const diff = Date.now() - new Date(dateStr).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1)  return 'just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    if (d < 7)  return `${d}d ago`;
    return new Date(dateStr).toLocaleDateString();
}

function getThreadGroupName(dateStr) {
    if (!dateStr) return 'Unknown';
    const target = new Date(dateStr);
    const now = new Date();
    const todayMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const targetTimestamp = new Date(target.getFullYear(), target.getMonth(), target.getDate()).getTime();
    const diffMs = todayMidnight - targetTimestamp;
    const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays <= 0) return 'Today';
    if (diffDays < 3) return 'Past 3 days';
    if (diffDays < 7) return 'Past week';
    if (diffDays < 30) return 'Past month';
    if (diffDays < 365) return 'Past year';
    return 'More than a year';
}

// ─── Thread search wiring (called once after DOM ready) ───────────
function initThreadSearch() {
    const input = document.getElementById('threads-search');
    if (!input || input.dataset.bound) return;
    input.dataset.bound = 'true';

    let debounceTimer = null;
    input.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            const q = input.value.trim().toLowerCase();
            let visibleTotal = 0;
            
            // First hide all headers
            const headers = document.querySelectorAll('.thread-group-header');
            headers.forEach(h => h.style.display = 'none');

            document.querySelectorAll('.thread-item').forEach(item => {
                const title   = (item.querySelector('.thread-title')?.textContent   || '').toLowerCase();
                const preview = (item.querySelector('.thread-preview')?.textContent || '').toLowerCase();
                const show    = !q || title.includes(q) || preview.includes(q);
                item.style.display = show ? '' : 'none';
                
                if (show) {
                    visibleTotal++;
                    // Find the preceding header and show it
                    let sibling = item.previousElementSibling;
                    while (sibling) {
                        if (sibling.classList.contains('thread-group-header')) {
                            sibling.style.display = '';
                            break;
                        }
                        sibling = sibling.previousElementSibling;
                    }
                }
            });

            // Show empty state if nothing matches
            let noResults = document.getElementById('threads-no-results');
            if (visibleTotal === 0 && q) {
                if (!noResults) {
                    noResults = document.createElement('div');
                    noResults.id = 'threads-no-results';
                    noResults.className = 'threads-empty-state';
                    noResults.innerHTML = '<i class="fas fa-search"></i><span>No threads match</span>';
                    document.getElementById('threads-list')?.appendChild(noResults);
                }
                noResults.style.display = 'flex';
            } else if (noResults) {
                noResults.style.display = 'none';
            }
        }, 150);
    });

    // Clear search when clicking outside or switching tabs
    window._clearThreadSearch = () => {
        input.value = '';
        input.dispatchEvent(new Event('input'));
    };
}

// Render thread list
function renderThreadList() {
    const threadsList = document.getElementById('threads-list');
    threadsList.innerHTML = '';
    const template = document.getElementById('thread-item-template');

    // Sort threads by pinned first, then by date desc
    const sortedThreads = Object.values(threads).sort((a, b) => {
        if (a.is_pinned && !b.is_pinned) return -1;
        if (!a.is_pinned && b.is_pinned) return 1;
        return new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at);
    });

    let lastGroupName = '';

    sortedThreads.forEach(thread => {
        // Grouping Dividers (only for non-pinned or first group of non-pinned)
        if (!thread.is_pinned) {
            const groupName = getThreadGroupName(thread.updated_at || thread.created_at);
            if (groupName !== lastGroupName) {
                const divider = document.createElement('div');
                divider.className = 'thread-group-header';
                divider.textContent = groupName;
                threadsList.appendChild(divider);
                lastGroupName = groupName;
            }
        } else {
             // For pinned threads, display only 'Pinned' header once
             if (lastGroupName !== 'Pinned') {
                const divider = document.createElement('div');
                divider.className = 'thread-group-header';
                divider.innerHTML = '<i class="fas fa-thumbtack"></i> Pinned';
                threadsList.appendChild(divider);
                lastGroupName = 'Pinned';
             }
        }

        // Clone template
        const clone = template.content.cloneNode(true);
        const threadItem = clone.querySelector('.thread-item');

        // Set ID and Active State
        threadItem.dataset.threadId = thread.id;
        if (thread.id === currentThreadId) threadItem.classList.add('active');

        // Populate Data
        const titleEl = clone.querySelector('.thread-title');
        titleEl.textContent = thread.title;
        titleEl.title = thread.title;   // tooltip for truncated text

        // Preview — last user message from in-memory store
        const msgs = threadMessages[thread.id] || [];
        const lastMsg = [...msgs].reverse().find(m => m.role === 'user' || m.role === 'assistant');
        const previewEl = clone.querySelector('.thread-preview');
        if (previewEl) {
            const previewText = lastMsg
                ? lastMsg.content.replace(/<[^>]+>/g, '').slice(0, 80)
                : 'No messages yet';
            previewEl.textContent = previewText;
            previewEl.title = previewText;   // tooltip for truncated preview
        }

        // Pin State Visuals
        if (thread.is_pinned) {
            threadItem.classList.add('pinned');
            const pinBtn = clone.querySelector('.pin-btn');
            if (pinBtn) pinBtn.classList.add('active');
        }

        // Pin Action
        const pinBtn = clone.querySelector('.pin-btn');
        if (pinBtn) {
            pinBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const newState = !thread.is_pinned;
                thread.is_pinned = newState;
                
                // Visual feedback immediate
                threadItem.classList.toggle('pinned', newState);
                pinBtn.classList.toggle('active', newState);
                
                // Re-sort and render list to reflect new positions
                renderThreadList();
                
                try {
                    await fetch(`/api/tasks/thread/${thread.id}/pin`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ is_pinned: newState })
                    });
                } catch (err) {
                    console.error("Failed to toggle pin state:", err);
                    showToast("Failed to pin thread.", "error");
                }
            });
        }

        // Edit Action — inline title rename
        const editBtn = clone.querySelector('.edit-btn');
        if (editBtn) {
            editBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const titleEl = threadItem.querySelector('.thread-title');
                if (!titleEl) return;
                titleEl.contentEditable = 'true';
                titleEl.focus();
                const range = document.createRange();
                range.selectNodeContents(titleEl);
                window.getSelection().removeAllRanges();
                window.getSelection().addRange(range);

                const commit = () => {
                    titleEl.contentEditable = 'false';
                    const newTitle = titleEl.textContent.trim();
                    if (newTitle && newTitle !== thread.title) {
                        editThreadTitle(thread.id, newTitle);
                        showToast('Thread renamed', 'success');
                    } else {
                        titleEl.textContent = thread.title; // revert
                    }
                };
                titleEl.addEventListener('blur',    commit, { once: true });
                titleEl.addEventListener('keydown', (ev) => {
                    if (ev.key === 'Enter')  { ev.preventDefault(); titleEl.blur(); }
                    if (ev.key === 'Escape') { titleEl.textContent = thread.title; titleEl.blur(); }
                });
            });
        }

        // Delete Action — custom confirm modal
        clone.querySelector('.delete-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            showConfirm(
                'Delete Thread',
                `Delete "${thread.title}" and all its messages? This cannot be undone.`,
                () => deleteThread(thread.id),
                { confirmLabel: 'Delete', icon: 'fa-trash' }
            );
        });

        threadsList.appendChild(clone);
    });
}

// Edit a thread's title manually
async function editThreadTitle(threadId, newTitle) {
    if (!threads[threadId]) return;

    // Optimistic UI update
    threads[threadId].title = newTitle;
    
    // Update Sidebar
    const uiThreadLink = document.querySelector(`.thread-item[data-thread-id="${threadId}"] .thread-title`);
    if (uiThreadLink) uiThreadLink.textContent = newTitle;

    // Update Header if it's the active thread
    if (currentThreadId === threadId) {
        document.getElementById('active-thread-title').textContent = newTitle;
    }

    try {
        await fetch(`/api/tasks/thread/${threadId}/title`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle })
        });
    } catch (error) {
        console.error('Failed to update thread title on server:', error);
    }
}


// Delete a thread — 5-second undo grace period before committing to server
function deleteThread(threadId) {
    const thread = threads[threadId];
    if (!thread) return;

    // Save data for potential undo
    const savedThread    = { ...thread };
    const savedMessages  = (threadMessages[threadId] || []).slice();

    // Optimistically hide DOM element
    const threadEl = document.querySelector(`.thread-item[data-thread-id="${threadId}"]`);
    if (threadEl) threadEl.style.display = 'none';

    // Remove from in-memory state right away
    delete threads[threadId];
    delete threadMessages[threadId];

    // If we deleted the active thread, switch to the next available one
    if (currentThreadId === threadId) {
        const sorted = Object.values(threads).sort((a, b) =>
            new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at)
        );
        switchThread(sorted.length > 0 ? sorted[0].id : 'default');
    }

    // Show undo toast — user has 5 s to cancel
    showToast(`"${savedThread.title}" deleted`, 'warn', 5000, {
        undoLabel: 'Undo',
        onUndo: () => {
            clearTimeout(deleteTimer);
            threads[threadId]        = savedThread;
            threadMessages[threadId] = savedMessages;
            if (threadEl) { threadEl.style.display = ''; }
            else           { renderThreadList(); }
            if (currentThreadId !== threadId) switchThread(threadId);
            showToast(`"${savedThread.title}" restored`, 'success');
        }
    });

    // Commit to server after grace period
    const deleteTimer = setTimeout(async () => {
        try {
            await fetch(`/api/tasks/thread/${threadId}`, { method: 'DELETE' });
            if (threadEl && threadEl.parentNode) threadEl.remove();
        } catch (error) {
            console.error('Failed to delete thread:', error);
            showToast('Failed to delete thread on server', 'error');
            // Revert state so nothing is lost
            threads[threadId]        = savedThread;
            threadMessages[threadId] = savedMessages;
            renderThreadList();
        }
    }, 5000);
}

function saveGlobalChatSettings() {
    const settings = {
        context_mode: document.getElementById('global-ctx-mode').value,
        context_window: parseInt(document.getElementById('global-ctx-window').value) || 5,
    };
    localStorage.setItem('global_chat_settings', JSON.stringify(settings));
}

function loadGlobalChatSettings() {
    try {
        const saved = localStorage.getItem('global_chat_settings');
        if (saved) {
            const settings = JSON.parse(saved);
            document.getElementById('global-ctx-mode').value = settings.context_mode || 'smart';
            document.getElementById('global-ctx-window').value = settings.context_window || 5;
        }
    } catch (e) {
        console.error("Failed to load global chat settings:", e);
    }
}

// Get thread status based on tasks
function getThreadStatus(thread) {
    if (!thread.task_ids || thread.task_ids.length === 0) {
        return 'idle';
    }

    // Check if any tasks are running
    // This will be updated by refreshThreadStatus
    return thread.status || 'idle';
}

// Refresh thread status
async function refreshThreadStatus() {
    try {
        const response = await fetch('/api/tasks/queue/status');
        const data = await response.json();

        // Update thread statuses based on task statuses
        Object.keys(threads).forEach(threadId => {
            const thread = threads[threadId];
            if (!thread.task_ids || thread.task_ids.length === 0) {
                thread.status = 'idle';
                return;
            }

            // Check if any tasks are running
            const hasRunning = thread.task_ids.some(taskId => {
                // This is a simplified check - in reality we'd query task status
                return false; // Will be implemented with proper task tracking
            });

            thread.status = hasRunning ? 'running' : 'completed';
        });

        renderThreadList();

    } catch (error) {
        console.error('Failed to refresh thread status:', error);
    }
}

// Draft persistence — save typed text so it survives accidental navigation / failed sends
const DRAFT_KEY = 'ae_chat_draft';
function saveDraft(text) { try { localStorage.setItem(DRAFT_KEY, text); } catch(e){} }
function loadDraft()     { try { return localStorage.getItem(DRAFT_KEY) || ''; } catch(e){ return ''; } }
function clearDraft()    { try { localStorage.removeItem(DRAFT_KEY); } catch(e){} }

// Restore draft on init
(function restoreDraftOnLoad() {
    document.addEventListener('DOMContentLoaded', () => {
        const input = document.getElementById('chat-input');
        if (input) {
            const d = loadDraft();
            if (d) input.value = d;
            input.addEventListener('input', () => saveDraft(input.value));
        }
    });
})();

// Send button loading state helpers
function setSendLoading(loading) {
    const btn = document.getElementById('send-button');
    const input = document.getElementById('chat-input');
    if (!btn) return;
    if (loading) {
        btn.disabled = true;
        btn.dataset.origHtml = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i>';
        if (input) input.disabled = true;
    } else {
        btn.disabled = false;
        if (btn.dataset.origHtml) btn.innerHTML = btn.dataset.origHtml;
        if (input) input.disabled = false;
    }
}

// Modified sendMessage to use task queue
async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();

    // Store which thread this message belongs to
    const messageThreadId = currentThreadId;

    let attachedFiles = null;
    let attachedFileName = window._mainChatAttachedFile ? window._mainChatAttachedFile.name : null;

    if (!message && !window._mainChatAttachedFile) return;

    // Lock UI immediately to prevent double-send
    setSendLoading(true);

    // Upload file if attached
    if (window._mainChatAttachedFile) {
        try {
            const formData = new FormData();
            formData.append('file', window._mainChatAttachedFile.file, window._mainChatAttachedFile.name);
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
        if (typeof window.clearMainChatAttachment === 'function') {
            window.clearMainChatAttachment();
        }
    }

    // Clear input ONLY after we've confirmed submission will proceed — draft cleared below
    input.value = '';
    input.style.height = '';

    const displayText = message || `[Attached: ${attachedFileName}]`;

    // Add user message to current thread
    addMessageToThread(messageThreadId, 'user', displayText, null, null, attachedFiles);

    // Auto-Title Logic: If the thread is named "Thread N" and this is the first user message, rename it.
    const currentThreadParams = threads[messageThreadId];
    if (currentThreadParams && /^Thread \d+$/.test(currentThreadParams.title)) {
        const userMessages = (threadMessages[messageThreadId] || []).filter(m => m.role === 'user');
        if (userMessages.length === 1) { // It's the first message!
            // First 40 chars
            let autoTitle = message || attachedFileName || "New Chat";
            autoTitle = autoTitle.trim().split('\n')[0]; // First line only
            if (autoTitle.length > 40) autoTitle = autoTitle.substring(0, 37) + '...';
            
            currentThreadParams.title = autoTitle;
            
            // Update UI Header and Sidebar immediately
            document.getElementById('active-thread-title').textContent = autoTitle;
            const uiThreadLink = document.querySelector(`.thread-item[data-thread-id="${messageThreadId}"] .thread-title`);
            if (uiThreadLink) uiThreadLink.textContent = autoTitle;

            // Sync with backend async
            fetch(`/api/tasks/thread/${messageThreadId}/title`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: autoTitle })
            }).catch(e => console.error("Failed to auto-title thread remotely:", e));
        }
    }

    // Get model selection
    const modelSelect = document.getElementById('model-select');
    const modelId = modelSelect ? modelSelect.value : null;

    try {
        // Submit task to queue
        const ctxMode = document.getElementById('global-ctx-mode').value;
        const ctxWin = parseInt(document.getElementById('global-ctx-window').value) || 5;

        const payload = {
            prompt: message || `Please review the attached file: ${attachedFileName || 'file'}`,
            thread_id: messageThreadId,
            thread_title: threads[messageThreadId]?.title,
            model_id: modelId || 'auto',
            mode: 'chat_only',
            settings: {
                context_mode: ctxMode,
                context_window: ctxWin
            }
        };

        if (attachedFiles) {
            payload.attached_files = attachedFiles;
        }

        const response = await fetch('/api/tasks/submit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        // Track which thread this task belongs to
        activeTasksByThread[data.task_id] = messageThreadId;

        // Draft successfully submitted — clear it
        clearDraft();

        // Unlock UI
        setSendLoading(false);

        // Show typing indicator instead of system message
        showTypingIndicator();

        // Start polling for task completion
        pollTaskStatus(data.task_id, messageThreadId);

    } catch (error) {
        console.error('Failed to submit task:', error);
        // Restore draft so user doesn't lose their message
        input.value = message;
        saveDraft(message);
        setSendLoading(false);
        addMessageToThread(messageThreadId, 'error', `Failed to submit: ${error.message} — your message was restored.`);
        showToast('Send failed. Your message has been restored in the input.', 'error');
    }
}

// Active task cancel registry
const _cancelledTasks = new Set();
function cancelTask(taskId) {
    _cancelledTasks.add(taskId);
    delete activeTasksByThread[taskId];
    hideTypingIndicator();
    showToast('Task cancelled.', 'info');
}
window.cancelTask = cancelTask;

// Poll task status until completion — with exponential backoff, elapsed timer, and cancel support
async function pollTaskStatus(taskId, threadId) {
    const startTime = Date.now();
    let attempts = 0;
    let consecutiveErrors = 0;
    let warned30s = false;
    const MAX_WAIT_MS = 300_000; // 5 minutes hard cap

    // Update the typing indicator's elapsed time display
    const updateElapsed = () => {
        const indicator = document.getElementById('chat-typing-indicator');
        if (!indicator) return;
        const elapsed = Math.round((Date.now() - startTime) / 1000);
        let elapsedEl = indicator.querySelector('.typing-elapsed');
        if (!elapsedEl) {
            elapsedEl = document.createElement('span');
            elapsedEl.className = 'typing-elapsed';
            const content = indicator.querySelector('.message-content');
            if (content) content.appendChild(elapsedEl);
        }
        elapsedEl.textContent = ` · ${elapsed}s`;

        // At 30s show cancel button once
        if (elapsed >= 30 && !warned30s) {
            warned30s = true;
            let cancelEl = indicator.querySelector('.typing-cancel-btn');
            if (!cancelEl) {
                cancelEl = document.createElement('button');
                cancelEl.className = 'typing-cancel-btn';
                cancelEl.textContent = 'Cancel';
                cancelEl.onclick = () => cancelTask(taskId);
                const content = indicator.querySelector('.message-content');
                if (content) content.appendChild(cancelEl);
            }
            showToast('Task is taking a while — you can cancel it.', 'warn', 5000);
        }
    };

    const elapsedInterval = setInterval(updateElapsed, 1000);

    const finish = () => {
        clearInterval(elapsedInterval);
        setSendLoading(false);
    };

    // Interval based on attempt count — gentle exponential backoff
    const intervalFor = (n) => Math.min(1000 * Math.pow(1.3, Math.min(n, 8)), 8000);

    const poll = async () => {
        if (_cancelledTasks.has(taskId)) { finish(); return; }
        if (Date.now() - startTime > MAX_WAIT_MS) {
            addMessageToThread(threadId, 'error', `Task timed out after 5 minutes.`);
            hideTypingIndicator();
            delete activeTasksByThread[taskId];
            finish();
            return;
        }

        try {
            const response = await fetch(`/api/tasks/status/${taskId}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            consecutiveErrors = 0;

            if (data.status === 'completed') {
                addMessageToThread(threadId, 'assistant', data.result.response, taskId, data);
                hideTypingIndicator();
                delete activeTasksByThread[taskId];
                finish();
                return;
            } else if (data.status === 'failed') {
                addMessageToThread(threadId, 'error', `Task failed: ${data.error}`, taskId);
                hideTypingIndicator();
                delete activeTasksByThread[taskId];
                finish();
                return;
            }

            attempts++;
            setTimeout(poll, intervalFor(attempts));

        } catch (error) {
            consecutiveErrors++;
            console.error(`Polling error (attempt ${attempts}, ${consecutiveErrors} consecutive):`, error);

            if (consecutiveErrors >= 5) {
                // 5 back-to-back failures — give up and tell the user
                addMessageToThread(threadId, 'error',
                    `Lost connection while waiting for response (${error.message}). The task may still be running — refresh to check.`);
                hideTypingIndicator();
                delete activeTasksByThread[taskId];
                showToast('Connection lost during polling. Task may still be processing.', 'error', 6000);
                finish();
                return;
            }
            // Otherwise retry with longer backoff
            setTimeout(poll, intervalFor(attempts + consecutiveErrors * 2));
        }
    };

    poll();
}


// Update existing message in a specific thread (for non-streaming status updates if still used)
function updateMessageInThread(threadId, taskId, content) {
    const messages = threadMessages[threadId] || [];
    const messageIndex = messages.findIndex(msg => msg.taskId === taskId);

    if (messageIndex !== -1) {
        messages[messageIndex].content = content;
        messages[messageIndex].html = `<div class="message-content"><strong>System:</strong> ${content}</div>`;

        // Re-render if this is the current thread
        if (threadId === currentThreadId) {
            renderThreadMessages();
        }
    }
}

// Typing Indicator Management
function showTypingIndicator(internal = false) {
    if (!internal) isTypingIndicatorVisible = true;
    
    let indicator = document.getElementById('chat-typing-indicator');
    const messages = document.getElementById('chat-messages');

    if (!messages) return;

    // If indicator was removed by innerHTML = '', recreate it or re-append it
    if (!indicator || indicator.parentElement !== messages) {
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.id = 'chat-typing-indicator';
            indicator.className = 'message ai-message typing-indicator';
            indicator.innerHTML = `
                <div class="message-content">
                    <span class="typing-text">Working...</span>
                </div>
            `;
        }
        messages.appendChild(indicator);
    }

    indicator.style.display = 'flex';
    
    // Start dynamic updates if not already running
    if (!typingInterval) {
        const textEl = indicator.querySelector('.typing-text');
        const randomMsg = typingMessages[Math.floor(Math.random() * typingMessages.length)];
        
        typingInterval = setInterval(() => {
            typingDotsCount = (typingDotsCount % 5) + 1;
            const dots = '.'.repeat(typingDotsCount);
            if (textEl) textEl.textContent = `${randomMsg}${dots}`;
        }, 400);
    }

    // Scroll to bottom
    setTimeout(() => {
        messages.scrollTop = messages.scrollHeight;
    }, 10);
}

function hideTypingIndicator() {
    isTypingIndicatorVisible = false;
    if (typingInterval) {
        clearInterval(typingInterval);
        typingInterval = null;
        typingDotsCount = 1;
    }
    const indicator = document.getElementById('chat-typing-indicator');
    if (indicator) indicator.style.display = 'none';
}

// Save thread settings (auto-save)
async function saveThreadSettings(threadId) {
    const threadItem = document.querySelector(`.thread-item[data-thread-id="${threadId}"]`);
    if (!threadItem) return;

    // Fixed: Read from select dropdown
    const contextSelect = threadItem.querySelector(`select[name="contextMode"]`);
    let contextMode = 'smart';
    if (contextSelect) {
        contextMode = contextSelect.value;
    }

    // Fallback for radio if select not found (backward compatibility if template mismatch)
    if (!contextSelect) {
        const radioGroup = threadItem.querySelectorAll(`input[name="contextMode-${threadId}"]`);
        for (const radio of radioGroup) {
            if (radio.checked) {
                contextMode = radio.value;
                break;
            }
        }
    }

    const windowInput = threadItem.querySelector('.context-window-input');
    const contextWindow = windowInput ? parseInt(windowInput.value) : 5;


    // Update local state
    if (threads[threadId]) {
        threads[threadId].settings = {
            context_mode: contextMode,
            context_window: contextWindow
        };
    }

    try {
        await fetch(`/api/tasks/thread/${threadId}/settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ settings: threads[threadId].settings })
        });
        // Silent success
    } catch (e) {
        console.error("Failed to save thread settings:", e);
    }
}
