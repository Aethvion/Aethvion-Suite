// ============================================================
// Agent Workspaces Mode — mode-agents.js
// Provides workspace + thread management and agent task submission
// with the same polling pattern as threads.js pollTaskStatus.
// ============================================================

// ── Configure marked (same as mode-chat.js) ──────────────────
if (typeof marked !== 'undefined') {
    marked.setOptions({
        gfm: true,
        breaks: true,
        headerIds: false,
        mangle: false,
        sanitize: false
    });
}

// ── State ─────────────────────────────────────────────────────
let _agentsWorkspaces = [];
let _agentsCurrentWorkspace = null;  // workspace object
let _agentsCurrentThread = null;     // thread metadata object (no messages)
let _agentsPollTimer = null;
let _agentsCurrentTaskId = null;
let _agentsIsPolling = false;

// ── DOM helpers ───────────────────────────────────────────────
const _agEl = (id) => document.getElementById(id);

function _agentsRenderMarkdown(text) {
    if (!text) return '';
    if (typeof marked !== 'undefined') {
        try { return marked.parse(text); } catch (e) { /* fall through */ }
    }
    // Basic fallback: escape HTML and wrap code blocks
    return text
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br>');
}

// ── Workspace list ────────────────────────────────────────────
async function agentsLoadWorkspaces() {
    try {
        const resp = await fetch('/api/agents/workspaces');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        _agentsWorkspaces = data.workspaces || [];
        _agentsPopulateWorkspaceSelect();
    } catch (e) {
        console.error('[Agents] Failed to load workspaces:', e);
    }
}

function _agentsPopulateWorkspaceSelect() {
    const sel = _agEl('agents-workspace-select');
    if (!sel) return;
    const prev = sel.value;
    sel.innerHTML = '<option value="">— select workspace —</option>';
    for (const ws of _agentsWorkspaces) {
        const opt = document.createElement('option');
        opt.value = ws.id;
        opt.textContent = ws.name;
        sel.appendChild(opt);
    }
    // Restore selection if still valid
    if (prev && _agentsWorkspaces.find(w => w.id === prev)) {
        sel.value = prev;
    }
    _agentsOnWorkspaceSelectChange();
}

async function _agentsOnWorkspaceSelectChange() {
    const sel = _agEl('agents-workspace-select');
    if (!sel) return;
    const wsId = sel.value;
    const ws = _agentsWorkspaces.find(w => w.id === wsId) || null;
    _agentsCurrentWorkspace = ws;
    _agentsCurrentThread = null;

    // Update path display
    const pathEl = _agEl('agents-workspace-path-display');
    if (pathEl) pathEl.textContent = ws ? ws.path : '';

    const inputPath = _agEl('agents-input-path');
    const inputCtx = _agEl('agents-input-context');
    if (inputPath && inputCtx) {
        if (ws) {
            inputPath.textContent = ws.path;
            inputCtx.style.display = 'flex';
        } else {
            inputCtx.style.display = 'none';
        }
    }

    // Show/hide edit/delete buttons for workspace
    const editBtn = _agEl('agents-edit-workspace-btn');
    const delBtn = _agEl('agents-delete-workspace-btn');
    if (editBtn) editBtn.style.display = ws ? '' : 'none';
    if (delBtn) delBtn.style.display = ws ? '' : 'none';

    // Enable/disable thread controls
    const threadSel = _agEl('agents-thread-select');
    const newThreadBtn = _agEl('agents-new-thread-btn');
    if (threadSel) threadSel.disabled = !ws;
    if (newThreadBtn) newThreadBtn.disabled = !ws;

    if (ws) {
        await agentsLoadThreads(ws.id);
    } else {
        _agentsClearThreadSelect();
        _agentsShowEmptyState('No workspace selected', 'Add or select a workspace to start working with agents');
    }

    _agentsUpdateSubmitState();
}

// ── Thread list ───────────────────────────────────────────────
async function agentsLoadThreads(workspaceId) {
    try {
        const resp = await fetch(`/api/agents/workspaces/${workspaceId}/threads`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        _agentsPopulateThreadSelect(data.threads || []);
    } catch (e) {
        console.error('[Agents] Failed to load threads:', e);
    }
}

function _agentsPopulateThreadSelect(threads) {
    const sel = _agEl('agents-thread-select');
    if (!sel) return;
    const prev = sel.value;
    sel.innerHTML = '<option value="">— select thread —</option>';
    for (const t of threads) {
        const opt = document.createElement('option');
        opt.value = t.id;
        const msgCount = t.message_count > 0 ? ` (${t.message_count})` : '';
        opt.textContent = t.name + msgCount;
        sel.appendChild(opt);
    }
    if (prev && threads.find(t => t.id === prev)) {
        sel.value = prev;
        // Restore thread object
        const t = threads.find(t => t.id === prev);
        if (t) _agentsCurrentThread = t;
    }
    _agentsOnThreadSelectChange();
}

function _agentsClearThreadSelect() {
    const sel = _agEl('agents-thread-select');
    if (sel) {
        sel.innerHTML = '<option value="">Select workspace first</option>';
        sel.disabled = true;
    }
    const editBtn = _agEl('agents-rename-thread-btn');
    const delBtn = _agEl('agents-delete-thread-btn');
    if (editBtn) editBtn.style.display = 'none';
    if (delBtn) delBtn.style.display = 'none';
}

async function _agentsOnThreadSelectChange() {
    const sel = _agEl('agents-thread-select');
    if (!sel || !_agentsCurrentWorkspace) return;
    const threadId = sel.value;

    const editBtn = _agEl('agents-rename-thread-btn');
    const delBtn = _agEl('agents-delete-thread-btn');

    if (!threadId) {
        _agentsCurrentThread = null;
        if (editBtn) editBtn.style.display = 'none';
        if (delBtn) delBtn.style.display = 'none';
        _agentsShowEmptyState('No thread selected', 'Create or select a thread to start working');
        _agentsUpdateSubmitState();
        return;
    }

    if (editBtn) editBtn.style.display = '';
    if (delBtn) delBtn.style.display = '';

    // Load thread messages
    await agentsLoadThreadMessages(_agentsCurrentWorkspace.id, threadId);
    _agentsUpdateSubmitState();
}

async function agentsLoadThreadMessages(workspaceId, threadId) {
    try {
        const resp = await fetch(`/api/agents/workspaces/${workspaceId}/threads/${threadId}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const thread = await resp.json();
        _agentsCurrentThread = {
            id: thread.id,
            workspace_id: thread.workspace_id,
            name: thread.name,
            created_at: thread.created_at,
            last_active: thread.last_active,
            message_count: (thread.messages || []).length,
        };
        _agentsRenderMessages(thread.messages || []);
    } catch (e) {
        console.error('[Agents] Failed to load thread messages:', e);
    }
}

// ── Message rendering ─────────────────────────────────────────
function _agentsRenderMessages(messages) {
    const container = _agEl('agents-messages');
    if (!container) return;

    // Remove empty state
    const emptyState = container.querySelector('.agents-empty-state');
    if (emptyState) emptyState.remove();

    // Clear existing messages (except typing indicator)
    const existing = container.querySelectorAll('.agents-message');
    existing.forEach(el => el.remove());

    if (messages.length === 0) {
        _agentsShowEmptyState('Empty thread', 'Submit a task to get started');
        return;
    }

    for (const msg of messages) {
        _agentsAppendMessage(msg, false);
    }
    container.scrollTop = container.scrollHeight;
}

function _agentsAppendMessage(msg, scroll = true) {
    const container = _agEl('agents-messages');
    if (!container) return;

    // Remove empty state if present
    const emptyState = container.querySelector('.agents-empty-state');
    if (emptyState) emptyState.remove();

    const role = msg.role || 'assistant';
    const wrapper = document.createElement('div');
    wrapper.className = `agents-message agents-message--${role}`;

    const bubble = document.createElement('div');
    bubble.className = 'agents-bubble';

    if (role === 'user') {
        bubble.textContent = msg.content || '';
    } else if (role === 'error') {
        bubble.textContent = msg.content || 'An error occurred.';
    } else {
        bubble.innerHTML = _agentsRenderMarkdown(msg.content || '');
        // Syntax highlight if available
        if (typeof hljs !== 'undefined') {
            bubble.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
        }
    }

    wrapper.appendChild(bubble);

    // Actions taken pills
    if (role === 'assistant' && msg.actions && msg.actions.length > 0) {
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'agents-actions-taken';
        for (const action of msg.actions) {
            const pill = document.createElement('span');
            pill.className = 'agents-action-pill';
            pill.textContent = action;
            actionsDiv.appendChild(pill);
        }
        wrapper.appendChild(actionsDiv);
    }

    // Model badge + timestamp
    const meta = document.createElement('div');
    meta.className = 'agents-bubble-meta';
    const ts = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
    const modelStr = msg.model ? ` · ${msg.model}` : '';
    meta.textContent = ts + modelStr;
    wrapper.appendChild(meta);

    container.appendChild(wrapper);

    if (scroll) container.scrollTop = container.scrollHeight;
}

function _agentsShowEmptyState(title, sub) {
    const container = _agEl('agents-messages');
    if (!container) return;
    // Remove existing messages
    container.querySelectorAll('.agents-message').forEach(el => el.remove());
    // Remove existing empty state
    container.querySelectorAll('.agents-empty-state').forEach(el => el.remove());
    const div = document.createElement('div');
    div.className = 'agents-empty-state';
    div.id = 'agents-empty-state';
    div.innerHTML = `
        <div class="agents-empty-icon">🤖</div>
        <div class="agents-empty-title">${title}</div>
        <div class="agents-empty-sub">${sub}</div>
    `;
    container.appendChild(div);
}

// ── Typing indicator ──────────────────────────────────────────
function _agentsShowTyping() {
    _agentsHideTyping();
    const container = _agEl('agents-messages');
    if (!container) return;
    const indicator = document.createElement('div');
    indicator.id = 'agents-typing-indicator';
    indicator.className = 'agents-typing-indicator';
    indicator.innerHTML = `
        <div class="agents-typing-dots">
            <span></span><span></span><span></span>
        </div>
        <span style="font-size:0.8rem; color:var(--text-secondary);">Working</span>
        <span class="agents-typing-elapsed" id="agents-typing-elapsed"></span>
    `;
    container.appendChild(indicator);
    container.scrollTop = container.scrollHeight;
}

function _agentsHideTyping() {
    const el = _agEl('agents-typing-indicator');
    if (el) el.remove();
}

// ── Submit state ──────────────────────────────────────────────
function _agentsUpdateSubmitState() {
    const btn = _agEl('agents-submit-btn');
    const textarea = _agEl('agents-task-input');
    const enabled = !!(_agentsCurrentWorkspace && _agentsCurrentThread && !_agentsIsPolling);
    if (btn) btn.disabled = !enabled;
    if (textarea) textarea.disabled = !enabled;
    if (textarea && enabled) textarea.placeholder = 'Describe a task for the agent...';
    if (textarea && !enabled && !_agentsCurrentWorkspace) textarea.placeholder = 'Select a workspace first...';
    if (textarea && !enabled && _agentsCurrentWorkspace && !_agentsCurrentThread) textarea.placeholder = 'Select or create a thread first...';
    if (textarea && !enabled && _agentsIsPolling) textarea.placeholder = 'Waiting for agent response...';
}

// ── Task submission & polling ─────────────────────────────────
async function agentsSubmitTask() {
    if (_agentsIsPolling) return;
    if (!_agentsCurrentWorkspace || !_agentsCurrentThread) return;

    const textarea = _agEl('agents-task-input');
    const prompt = textarea ? textarea.value.trim() : '';
    if (!prompt) return;

    const modelSel = _agEl('agents-model-select');
    const modelId = modelSel ? modelSel.value : 'auto';

    // Append user message locally
    _agentsAppendMessage({ role: 'user', content: prompt, timestamp: new Date().toISOString() });
    if (textarea) textarea.value = '';

    _agentsIsPolling = true;
    _agentsUpdateSubmitState();
    _agentsShowTyping();

    try {
        const resp = await fetch('/api/tasks/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompt,
                thread_id: `agents-${_agentsCurrentWorkspace.id}-${_agentsCurrentThread.id}`,
                model_id: modelId,
                mode: 'auto',
                workspace_id: _agentsCurrentWorkspace.id,
                agent_thread_id: _agentsCurrentThread.id,
            })
        });

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        _agentsCurrentTaskId = data.task_id;
        _agentsPollTask(data.task_id);
    } catch (e) {
        _agentsHideTyping();
        _agentsAppendMessage({ role: 'error', content: `Failed to submit task: ${e.message}`, timestamp: new Date().toISOString() });
        _agentsIsPolling = false;
        _agentsUpdateSubmitState();
    }
}

function _agentsPollTask(taskId) {
    const startTime = Date.now();
    let attempts = 0;
    let consecutiveErrors = 0;
    const MAX_WAIT_MS = 300_000; // 5 minutes

    const intervalFor = (n) => Math.min(1000 * Math.pow(1.3, Math.min(n, 8)), 8000);

    // Elapsed timer for typing indicator
    const elapsedInterval = setInterval(() => {
        const el = _agEl('agents-typing-elapsed');
        if (el) {
            const secs = Math.round((Date.now() - startTime) / 1000);
            el.textContent = ` · ${secs}s`;
        }
    }, 1000);

    const finish = () => {
        clearInterval(elapsedInterval);
        _agentsHideTyping();
        _agentsIsPolling = false;
        _agentsCurrentTaskId = null;
        _agentsUpdateSubmitState();
    };

    const poll = async () => {
        if (Date.now() - startTime > MAX_WAIT_MS) {
            _agentsAppendMessage({ role: 'error', content: 'Task timed out after 5 minutes.', timestamp: new Date().toISOString() });
            finish();
            return;
        }

        try {
            const resp = await fetch(`/api/tasks/status/${taskId}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            consecutiveErrors = 0;

            if (data.status === 'completed') {
                const result = data.result || {};
                _agentsAppendMessage({
                    role: 'assistant',
                    content: result.response || '',
                    timestamp: new Date().toISOString(),
                    actions: result.actions_taken || [],
                    model: result.model_id || '',
                });
                finish();
                // Refresh thread metadata (message count updated by backend)
                if (_agentsCurrentWorkspace && _agentsCurrentThread) {
                    agentsLoadThreads(_agentsCurrentWorkspace.id);
                }
                return;
            } else if (data.status === 'failed') {
                _agentsAppendMessage({ role: 'error', content: `Task failed: ${data.error || 'Unknown error'}`, timestamp: new Date().toISOString() });
                finish();
                return;
            }

            attempts++;
            _agentsPollTimer = setTimeout(poll, intervalFor(attempts));
        } catch (err) {
            consecutiveErrors++;
            console.error(`[Agents] Poll error (attempt ${attempts}, ${consecutiveErrors} consecutive):`, err);

            if (consecutiveErrors >= 5) {
                _agentsAppendMessage({ role: 'error', content: `Lost connection while waiting for response (${err.message}).`, timestamp: new Date().toISOString() });
                finish();
                return;
            }
            _agentsPollTimer = setTimeout(poll, intervalFor(attempts + consecutiveErrors * 2));
        }
    };

    poll();
}

// ── Add Workspace modal ───────────────────────────────────────
function agentsShowAddWorkspaceModal(editMode = false) {
    const overlay = _agEl('agents-add-ws-overlay');
    const title = _agEl('agents-modal-title');
    const pathInput = _agEl('agents-ws-path-input');
    const nameInput = _agEl('agents-ws-name-input');
    const confirmBtn = _agEl('agents-modal-confirm');

    if (!overlay) return;

    if (editMode && _agentsCurrentWorkspace) {
        if (title) title.textContent = 'Edit Workspace';
        if (pathInput) pathInput.value = _agentsCurrentWorkspace.path || '';
        if (nameInput) nameInput.value = _agentsCurrentWorkspace.name || '';
        if (confirmBtn) confirmBtn.textContent = 'Save Changes';
        overlay.dataset.editMode = 'true';
    } else {
        if (title) title.textContent = 'Add Workspace';
        if (pathInput) pathInput.value = '';
        if (nameInput) nameInput.value = '';
        if (confirmBtn) confirmBtn.textContent = 'Add Workspace';
        overlay.dataset.editMode = 'false';
    }

    overlay.style.display = 'flex';
    setTimeout(() => { if (pathInput) pathInput.focus(); }, 60);
}

function agentsHideAddWorkspaceModal() {
    const overlay = _agEl('agents-add-ws-overlay');
    if (overlay) overlay.style.display = 'none';
}

async function agentsConfirmWorkspaceModal() {
    const overlay = _agEl('agents-add-ws-overlay');
    const pathInput = _agEl('agents-ws-path-input');
    const nameInput = _agEl('agents-ws-name-input');

    const path = pathInput ? pathInput.value.trim() : '';
    const name = nameInput ? nameInput.value.trim() : '';

    if (!path) {
        if (pathInput) pathInput.focus();
        return;
    }

    const editMode = overlay && overlay.dataset.editMode === 'true';

    try {
        if (editMode && _agentsCurrentWorkspace) {
            const resp = await fetch(`/api/agents/workspaces/${_agentsCurrentWorkspace.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path, name: name || undefined })
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            agentsHideAddWorkspaceModal();
            await agentsLoadWorkspaces();
            // Re-select the same workspace
            const sel = _agEl('agents-workspace-select');
            if (sel && _agentsCurrentWorkspace) {
                sel.value = _agentsCurrentWorkspace.id;
                await _agentsOnWorkspaceSelectChange();
            }
        } else {
            const resp = await fetch('/api/agents/workspaces', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path, name: name || undefined })
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const ws = await resp.json();
            agentsHideAddWorkspaceModal();
            await agentsLoadWorkspaces();
            // Auto-select the new workspace
            const sel = _agEl('agents-workspace-select');
            if (sel) {
                sel.value = ws.id;
                await _agentsOnWorkspaceSelectChange();
            }
        }
    } catch (e) {
        console.error('[Agents] Failed to save workspace:', e);
        if (typeof showToast === 'function') showToast(`Failed: ${e.message}`, 'error');
    }
}

async function agentsDeleteWorkspace() {
    if (!_agentsCurrentWorkspace) return;
    const name = _agentsCurrentWorkspace.name;
    if (typeof showConfirmModal === 'function') {
        showConfirmModal(
            `Delete workspace "${name}"?`,
            'All threads and history for this workspace will be permanently deleted.',
            async () => {
                await _agentsDoDeleteWorkspace();
            },
            'danger'
        );
    } else if (confirm(`Delete workspace "${name}"? This will delete all threads.`)) {
        await _agentsDoDeleteWorkspace();
    }
}

async function _agentsDoDeleteWorkspace() {
    try {
        const resp = await fetch(`/api/agents/workspaces/${_agentsCurrentWorkspace.id}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        _agentsCurrentWorkspace = null;
        _agentsCurrentThread = null;
        await agentsLoadWorkspaces();
    } catch (e) {
        console.error('[Agents] Failed to delete workspace:', e);
        if (typeof showToast === 'function') showToast(`Failed: ${e.message}`, 'error');
    }
}

// ── Thread actions ────────────────────────────────────────────
async function agentsCreateThread() {
    if (!_agentsCurrentWorkspace) return;
    try {
        const resp = await fetch(`/api/agents/workspaces/${_agentsCurrentWorkspace.id}/threads`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const thread = await resp.json();
        await agentsLoadThreads(_agentsCurrentWorkspace.id);
        // Auto-select the new thread
        const sel = _agEl('agents-thread-select');
        if (sel) {
            sel.value = thread.id;
            await _agentsOnThreadSelectChange();
        }
    } catch (e) {
        console.error('[Agents] Failed to create thread:', e);
        if (typeof showToast === 'function') showToast(`Failed: ${e.message}`, 'error');
    }
}

async function agentsRenameThread() {
    if (!_agentsCurrentWorkspace || !_agentsCurrentThread) return;
    const newName = prompt('Enter new thread name:', _agentsCurrentThread.name || '');
    if (!newName || !newName.trim()) return;
    try {
        const resp = await fetch(`/api/agents/workspaces/${_agentsCurrentWorkspace.id}/threads/${_agentsCurrentThread.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName.trim() })
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        _agentsCurrentThread.name = newName.trim();
        await agentsLoadThreads(_agentsCurrentWorkspace.id);
        // Re-select
        const sel = _agEl('agents-thread-select');
        if (sel) {
            sel.value = _agentsCurrentThread.id;
        }
    } catch (e) {
        console.error('[Agents] Failed to rename thread:', e);
        if (typeof showToast === 'function') showToast(`Failed: ${e.message}`, 'error');
    }
}

async function agentsDeleteThread() {
    if (!_agentsCurrentWorkspace || !_agentsCurrentThread) return;
    const name = _agentsCurrentThread.name;
    if (typeof showConfirmModal === 'function') {
        showConfirmModal(
            `Delete thread "${name}"?`,
            'All messages in this thread will be permanently deleted.',
            async () => { await _agentsDoDeleteThread(); },
            'danger'
        );
    } else if (confirm(`Delete thread "${name}"?`)) {
        await _agentsDoDeleteThread();
    }
}

async function _agentsDoDeleteThread() {
    try {
        const resp = await fetch(`/api/agents/workspaces/${_agentsCurrentWorkspace.id}/threads/${_agentsCurrentThread.id}`, {
            method: 'DELETE'
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        _agentsCurrentThread = null;
        await agentsLoadThreads(_agentsCurrentWorkspace.id);
        _agentsShowEmptyState('Thread deleted', 'Select or create a thread to continue');
        _agentsUpdateSubmitState();
    } catch (e) {
        console.error('[Agents] Failed to delete thread:', e);
        if (typeof showToast === 'function') showToast(`Failed: ${e.message}`, 'error');
    }
}

// ── Model selector ────────────────────────────────────────────
async function agentsLoadModels() {
    try {
        const resp = await fetch('/api/registry/models/chat');
        if (!resp.ok) return;
        const data = await resp.json();
        const models = data.models || data || [];
        const sel = _agEl('agents-model-select');
        if (!sel || !models.length) return;
        sel.innerHTML = '<option value="auto">Auto</option>';
        for (const m of models) {
            const opt = document.createElement('option');
            opt.value = m.id || m.model_id || m.name;
            opt.textContent = m.display_name || m.name || opt.value;
            sel.appendChild(opt);
        }
    } catch (e) {
        console.error('[Agents] Failed to load models:', e);
    }
}

// ── Event wiring (called once after DOM is ready) ─────────────
function agentsInitEventHandlers() {
    // Workspace select change
    const wsSel = _agEl('agents-workspace-select');
    if (wsSel) wsSel.addEventListener('change', _agentsOnWorkspaceSelectChange);

    // Thread select change
    const tSel = _agEl('agents-thread-select');
    if (tSel) tSel.addEventListener('change', _agentsOnThreadSelectChange);

    // Add workspace button
    const addWsBtn = _agEl('agents-add-workspace-btn');
    if (addWsBtn) addWsBtn.addEventListener('click', () => agentsShowAddWorkspaceModal(false));

    // Edit workspace button
    const editWsBtn = _agEl('agents-edit-workspace-btn');
    if (editWsBtn) editWsBtn.addEventListener('click', () => agentsShowAddWorkspaceModal(true));

    // Delete workspace button
    const delWsBtn = _agEl('agents-delete-workspace-btn');
    if (delWsBtn) delWsBtn.addEventListener('click', agentsDeleteWorkspace);

    // New thread button
    const newTBtn = _agEl('agents-new-thread-btn');
    if (newTBtn) newTBtn.addEventListener('click', agentsCreateThread);

    // Rename thread button
    const renameTBtn = _agEl('agents-rename-thread-btn');
    if (renameTBtn) renameTBtn.addEventListener('click', agentsRenameThread);

    // Delete thread button
    const delTBtn = _agEl('agents-delete-thread-btn');
    if (delTBtn) delTBtn.addEventListener('click', agentsDeleteThread);

    // Modal close / cancel
    const modalClose = _agEl('agents-modal-close');
    if (modalClose) modalClose.addEventListener('click', agentsHideAddWorkspaceModal);

    const modalCancel = _agEl('agents-modal-cancel');
    if (modalCancel) modalCancel.addEventListener('click', agentsHideAddWorkspaceModal);

    // Modal confirm
    const modalConfirm = _agEl('agents-modal-confirm');
    if (modalConfirm) modalConfirm.addEventListener('click', agentsConfirmWorkspaceModal);

    // Modal overlay click to close
    const overlay = _agEl('agents-add-ws-overlay');
    if (overlay) {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) agentsHideAddWorkspaceModal();
        });
    }

    // Modal Enter key
    const wsPathInput = _agEl('agents-ws-path-input');
    const wsNameInput = _agEl('agents-ws-name-input');
    [wsPathInput, wsNameInput].forEach(inp => {
        if (inp) inp.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') agentsConfirmWorkspaceModal();
            if (e.key === 'Escape') agentsHideAddWorkspaceModal();
        });
    });

    // Submit button
    const submitBtn = _agEl('agents-submit-btn');
    if (submitBtn) submitBtn.addEventListener('click', agentsSubmitTask);

    // Textarea Enter to submit (Shift+Enter for newline)
    const taskInput = _agEl('agents-task-input');
    if (taskInput) {
        taskInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                agentsSubmitTask();
            }
        });
        // Auto-resize textarea
        taskInput.addEventListener('input', () => {
            taskInput.style.height = 'auto';
            taskInput.style.height = Math.min(taskInput.scrollHeight, 200) + 'px';
        });
    }
}

// ── Panel activation hook ─────────────────────────────────────
// Called by the tab switcher when the Agents panel becomes active.
function onAgentsPanelActivated() {
    agentsLoadWorkspaces();
    agentsLoadModels();
}

// ── Init ──────────────────────────────────────────────────────
(function agentsInit() {
    // Wait for DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _agentsBootstrap);
    } else {
        _agentsBootstrap();
    }

    function _agentsBootstrap() {
        agentsInitEventHandlers();
        _agentsShowEmptyState('No workspace selected', 'Add or select a workspace to start working with agents');
        _agentsUpdateSubmitState();

        // Hook into the main tab switcher event dispatched by core.js switchMainTab
        document.addEventListener('tabChanged', (e) => {
            if (e.detail && e.detail.tab === 'agents') {
                onAgentsPanelActivated();
            }
        });

        // Also support the registerTabInit API from core.js if available
        if (typeof registerTabInit === 'function') {
            registerTabInit('agents', onAgentsPanelActivated);
        }
    }
})();
