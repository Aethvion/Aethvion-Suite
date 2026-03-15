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
    ['global-ctx-mode', 'global-ctx-window', 'global-agent-toggle'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', () => {
                saveGlobalChatSettings();
                if (id === 'global-agent-toggle') {
                    if (typeof updateChatLayout === 'function') updateChatLayout();
                }
            });
        }
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

            if (!threads[thread.id]) {
                threads[thread.id] = thread;
                threadMessages[thread.id] = []; // Initialize message storage
            } else {
                // Update existing thread data (e.g. mode)
                threads[thread.id].mode = thread.mode;
            }
        });

        renderThreadList();

        // Auto-select first thread if none selected
        if (!currentThreadId || currentThreadId === 'default') {
            const threadKeys = Object.keys(threads);
            if (threadKeys.length > 0) {
                // Sort by date desc
                const sorted = Object.values(threads).sort((a, b) =>
                    new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at)
                );
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
        updated_at: new Date().toISOString()
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
    messages.forEach(msg => {
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
function addMessageToThread(threadId, role, content, taskId = null, taskData = null, attachments = null) {
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


        // Add expandable task details if available
        if (taskData) {
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
        timestamp: new Date().toISOString()
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
            data.tasks.forEach(task => {
                // Add user message
                addMessageToThread(threadId, 'user', task.prompt, task.id);

                // Add assistant response if completed
                if (task.status === 'completed' && task.result) {
                    addMessageToThread(threadId, 'assistant', task.result.response, task.id, task);
                } else if (task.status === 'failed') {
                    addMessageToThread(threadId, 'error', `Task failed: ${task.error}`, task.id);
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

// ─── Thread search wiring (called once after DOM ready) ───────────
function initThreadSearch() {
    const input = document.getElementById('threads-search');
    if (!input || input.dataset.bound) return;
    input.dataset.bound = 'true';
    input.addEventListener('input', () => {
        const q = input.value.trim().toLowerCase();
        document.querySelectorAll('.thread-item').forEach(item => {
            const title = (item.querySelector('.thread-title')?.textContent || '').toLowerCase();
            const preview = (item.querySelector('.thread-preview')?.textContent || '').toLowerCase();
            item.style.display = (title.includes(q) || preview.includes(q)) ? '' : 'none';
        });
    });
}

// Render thread list
function renderThreadList() {
    const threadsList = document.getElementById('threads-list');
    threadsList.innerHTML = '';
    const template = document.getElementById('thread-item-template');

    // Sort threads by date desc
    const sortedThreads = Object.values(threads).sort((a, b) =>
        new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at)
    );

    sortedThreads.forEach(thread => {
        // Clone template
        const clone = template.content.cloneNode(true);
        const threadItem = clone.querySelector('.thread-item');

        // Set ID and Active State
        threadItem.dataset.threadId = thread.id;
        if (thread.id === currentThreadId) threadItem.classList.add('active');

        // Populate Data
        clone.querySelector('.thread-title').textContent = thread.title;

        // Preview — last user message from in-memory store
        const msgs = threadMessages[thread.id] || [];
        const lastMsg = [...msgs].reverse().find(m => m.role === 'user' || m.role === 'assistant');
        const previewEl = clone.querySelector('.thread-preview');
        if (previewEl) {
            previewEl.textContent = lastMsg
                ? lastMsg.content.replace(/<[^>]+>/g, '').slice(0, 60)
                : 'No messages yet';
        }

        // Relative date
        const date = relativeTime(thread.updated_at || thread.created_at);
        clone.querySelector('.thread-date').textContent = date;

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


// Delete a thread
async function deleteThread(threadId) {
    // Optimistic UI update
    const threadEl = document.querySelector(`.thread-item[data-thread-id="${threadId}"]`);
    if (threadEl) threadEl.remove();

    // If deleted current thread, switch to default
    if (currentThreadId === threadId) {
        switchThread('default');
    }

    delete threads[threadId];
    delete threadMessages[threadId];

    try {
        await fetch(`/api/tasks/thread/${threadId}`, { method: 'DELETE' });
    } catch (error) {
        console.error('Failed to delete thread:', error);
        showToast('Failed to delete thread on server', 'error');
        loadThreads(); // Revert on failure
    }
}

function saveGlobalChatSettings() {
    const settings = {
        context_mode: document.getElementById('global-ctx-mode').value,
        context_window: parseInt(document.getElementById('global-ctx-window').value) || 5,
        agents_enabled: document.getElementById('global-agent-toggle').checked
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
            document.getElementById('global-agent-toggle').checked = !!settings.agents_enabled;

            // Trigger layout update based on loaded setting
            if (typeof updateChatLayout === 'function') updateChatLayout();
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

// Modified sendMessage to use task queue
async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();

    // Store which thread this message belongs to
    const messageThreadId = currentThreadId;

    let attachedFiles = null;
    let attachedFileName = window._mainChatAttachedFile ? window._mainChatAttachedFile.name : null;

    if (!message && !window._mainChatAttachedFile) return;

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

    // Clear input
    input.value = '';

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
        const agentsEnabled = document.getElementById('global-agent-toggle').checked;

        const payload = {
            prompt: message || `Please review the attached file: ${attachedFileName || 'file'}`,
            thread_id: messageThreadId,
            thread_title: threads[messageThreadId]?.title,
            model_id: modelId || 'auto',
            mode: agentsEnabled ? 'auto' : 'chat_only',
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

        // Show typing indicator instead of system message
        showTypingIndicator();

        // Start polling for task completion
        pollTaskStatus(data.task_id, messageThreadId);

    } catch (error) {
        console.error('Failed to submit task:', error);
        addMessageToThread(messageThreadId, 'error', `Failed to submit task: ${error.message}`);
    }
}

// Poll task status until completion
async function pollTaskStatus(taskId, threadId, maxAttempts = 60) {
    let attempts = 0;

    const poll = async () => {
        try {
            const response = await fetch(`/api/tasks/status/${taskId}`);
            const data = await response.json(); // Renamed 'task' to 'data' for consistency with original diff

            if (data.status === 'completed') {
                // Task completed successfully
                addMessageToThread(threadId, 'assistant', data.result.response, taskId, data);
                hideTypingIndicator();
                delete activeTasksByThread[taskId];
                return;
            } else if (data.status === 'failed') {
                // Task failed
                addMessageToThread(threadId, 'error', `Task failed: ${data.error}`, taskId);
                hideTypingIndicator();
                delete activeTasksByThread[taskId];
                return;
            }

            attempts++;
            if (attempts < maxAttempts) {
                setTimeout(poll, 1000); // Poll every second
            } else {
                addMessageToThread(threadId, 'error', `Task ${taskId} timed out`);
                hideTypingIndicator();
                delete activeTasksByThread[taskId];
            }

        } catch (error) {
            console.error('Polling error:', error);
            hideTypingIndicator();
            delete activeTasksByThread[taskId]; // Ensure task is removed from active list even on polling error
            return;
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
