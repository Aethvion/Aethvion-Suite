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
let _agentsModelCosts = {};          // model_id → {input, output} per 1M tokens
let _agentsPollTimer = null;
let _agentsCurrentTaskId = null;
let _agentsIsPolling = false;
let _agentsAttachedFiles = [];       // [{filename, path, is_image, mime_type, content, size, _previewUrl}]

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
    // Prefer in-page value, fall back to localStorage
    const prev = sel.value || localStorage.getItem('agents_workspace_id') || '';
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

    // Persist selection
    if (ws) localStorage.setItem('agents_workspace_id', ws.id);
    else localStorage.removeItem('agents_workspace_id');

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
    // Prefer in-page value, fall back to localStorage (scoped to current workspace)
    const wsId = _agentsCurrentWorkspace ? _agentsCurrentWorkspace.id : '';
    const savedKey = `agents_thread_id_${wsId}`;
    const prev = sel.value || localStorage.getItem(savedKey) || '';
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
        localStorage.removeItem(`agents_thread_id_${_agentsCurrentWorkspace.id}`);
        if (editBtn) editBtn.style.display = 'none';
        if (delBtn) delBtn.style.display = 'none';
        _agentsShowEmptyState('No thread selected', 'Create or select a thread to start working');
        _agentsUpdateSubmitState();
        return;
    }

    // Persist thread selection scoped to this workspace
    localStorage.setItem(`agents_thread_id_${_agentsCurrentWorkspace.id}`, threadId);

    if (editBtn) editBtn.style.display = '';
    if (delBtn) delBtn.style.display = '';

    // Load thread messages
    await agentsLoadThreadMessages(_agentsCurrentWorkspace.id, threadId);
    _agentsUpdateSubmitState();

    // Show existing thread token totals in stats panel
    _agUpdateThreadStats();
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

// ── Thread token totals from history ──────────────────────────
function _agCalcThreadTotalsFromMessages(messages) {
    let totalIn = 0, totalOut = 0;
    for (const msg of messages) {
        if (msg.role === 'agent_steps') {
            for (const ev of (msg.events || [])) {
                if (ev.type === 'usage') {
                    totalIn  += ev.input_tokens  || 0;
                    totalOut += ev.output_tokens || 0;
                }
            }
        }
    }
    return { in: totalIn, out: totalOut };
}

// ── Message rendering ─────────────────────────────────────────
function _agentsRenderMessages(messages) {
    const container = _agEl('agents-messages');
    if (!container) return;

    // Reset the replay-dedup flag so switching threads can't carry stale state
    _agLastMsgWasAgentSteps = false;

    // Reset dashboard left panel and stop any running timer
    _agResetDashboard();

    const emptyState = container.querySelector('.agents-empty-state');
    if (emptyState) emptyState.remove();

    container.querySelectorAll('.agents-message, .agent-run, .agent-typing-indicator').forEach(el => el.remove());

    if (messages.length === 0) {
        _agentsShowEmptyState('Empty thread', 'Submit a task to get started');
        return;
    }

    // Pre-calculate accurate thread totals from full history (prevents
    // localStorage from growing on each refresh due to replay accumulation)
    const threadId = _agentsCurrentThread?.id;
    if (threadId) {
        const totals = _agCalcThreadTotalsFromMessages(messages);
        localStorage.setItem(`agents_thread_stats_${threadId}`, JSON.stringify(totals));
    }

    for (const msg of messages) {
        _agentsAppendMessage(msg, false);
    }
    container.scrollTop = container.scrollHeight;
}

// Tracks whether the previous message was agent_steps — if so the `assistant`
// message that immediately follows is the same summary already shown in the
// done card, so we skip it to avoid a duplicate.
let _agLastMsgWasAgentSteps = false;

function _agentsAppendMessage(msg, scroll = true) {
    const container = _agEl('agents-messages');
    if (!container) return;

    // Agent step history — replay through the dashboard renderer
    if (msg.role === 'agent_steps') {
        _agLastMsgWasAgentSteps = true;
        for (const event of (msg.events || [])) {
            renderAgentStep(event, true); // isReplay = true
        }
        if (scroll) container.scrollTop = container.scrollHeight;
        return;
    }

    // The `assistant` message saved after an agent run is the same text already
    // displayed by the done card from agent_steps replay — skip it.
    if (msg.role === 'assistant' && _agLastMsgWasAgentSteps) {
        _agLastMsgWasAgentSteps = false;
        return;
    }

    // Reset flag for any other role (user, error, etc.)
    if (msg.role !== 'assistant') _agLastMsgWasAgentSteps = false;

    const emptyState = container.querySelector('.agents-empty-state');
    if (emptyState) emptyState.remove();

    const role = msg.role || 'assistant';
    const wrapper = document.createElement('div');
    wrapper.className = `agents-message agents-message--${role}`;

    if (role === 'user') {
        // Task prompt header — compact, dashboard style
        const header = document.createElement('div');
        header.className = 'agents-task-header';
        header.innerHTML = `
            <span class="agents-task-label">Task</span>
            <span class="agents-task-text">${_htmlEscape(msg.content || '')}</span>`;
        // Show attached file thumbnails/chips if present
        const attachments = msg.attachments || [];
        if (attachments.length > 0) {
            const chips = document.createElement('div');
            chips.className = 'agents-task-attachments';
            attachments.forEach(file => {
                const chip = document.createElement('div');
                chip.className = 'agents-task-attach-chip';
                if (file.is_image && file._previewUrl) {
                    chip.innerHTML = `<img src="${file._previewUrl}" class="agents-attach-thumb" alt="${_htmlEscape(file.filename)}">`;
                } else if (file.is_image) {
                    chip.innerHTML = `<i class="fas fa-image"></i><span>${_htmlEscape(file.filename)}</span>`;
                } else {
                    chip.innerHTML = `<i class="fas fa-file-alt"></i><span>${_htmlEscape(file.filename)}</span>`;
                }
                chips.appendChild(chip);
            });
            header.appendChild(chips);
        }
        wrapper.appendChild(header);
    } else if (role === 'error') {
        wrapper.innerHTML = `<div class="agents-response-error">${_htmlEscape(msg.content || 'An error occurred.')}</div>`;
    } else {
        // Assistant final response — clean reading area
        const body = document.createElement('div');
        body.className = 'agents-response-body';
        body.innerHTML = _agentsRenderMarkdown(msg.content || '');
        if (typeof hljs !== 'undefined') {
            body.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
        }
        wrapper.appendChild(body);

        const ts = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
        const modelStr = msg.model ? ` · ${msg.model}` : '';
        if (ts || modelStr) {
            const meta = document.createElement('div');
            meta.className = 'agents-response-meta';
            meta.textContent = ts + modelStr;
            wrapper.appendChild(meta);
        }
    }

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
    const btn       = _agEl('agents-submit-btn');
    const stopBtn   = _agEl('agents-stop-btn');
    const attachBtn = _agEl('agents-attach-btn');
    const textarea  = _agEl('agents-task-input');
    const enabled   = !!(_agentsCurrentWorkspace && _agentsCurrentThread && !_agentsIsPolling);
    if (btn)       btn.disabled       = !enabled;
    if (attachBtn) attachBtn.disabled = !enabled;
    if (textarea) textarea.disabled = !enabled;
    // Show Stop button only while agent is running; hide Submit
    if (stopBtn) stopBtn.style.display = _agentsIsPolling ? '' : 'none';
    if (btn)     btn.style.display     = _agentsIsPolling ? 'none' : '';
    if (textarea && enabled) textarea.placeholder = 'Describe a task for the agent...';
    if (textarea && !enabled && !_agentsCurrentWorkspace) textarea.placeholder = 'Select a workspace first...';
    if (textarea && !enabled && _agentsCurrentWorkspace && !_agentsCurrentThread) textarea.placeholder = 'Select or create a thread first...';
    if (textarea && !enabled && _agentsIsPolling) textarea.placeholder = 'Waiting for agent response...';
}

async function agentsStopTask() {
    if (!_agentsCurrentTaskId) return;
    const taskId = _agentsCurrentTaskId;
    try {
        await fetch(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
    } catch (_) { /* ignore network errors — runner will check flag next iteration */ }
    // Close the SSE stream immediately from the client side too
    if (_agentsPollTimer && _agentsPollTimer.close) {
        _agentsPollTimer.close();
        _agentsPollTimer = null;
    }
    _agentsIsPolling = false;
    _agentsCurrentTaskId = null;
    _agentsUpdateSubmitState();
}

// ── Auto-rename thread after first task ──────────────────────
async function _agAutoRenameThread(wsId, threadId, name) {
    try {
        const res = await fetch(`/api/agents/workspaces/${wsId}/threads/${threadId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
        });
        if (res.ok && _agentsCurrentThread && _agentsCurrentThread.id === threadId) {
            _agentsCurrentThread.name = name;
        }
    } catch (e) {
        console.debug('[Agents] Auto-rename failed:', e);
    }
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

    // Snapshot and clear attached files before appending the message
    const filesSnapshot = _agentsAttachedFiles.slice();
    _agentsAttachedFiles = [];
    _agentsRenderAttachStrip();

    // Append user message locally (show file thumbnails inline)
    _agentsAppendMessage({
        role: 'user',
        content: prompt,
        timestamp: new Date().toISOString(),
        attachments: filesSnapshot,
    });
    if (textarea) textarea.value = '';

    _agentsIsPolling = true;
    _agentsUpdateSubmitState();
    _agentsShowTyping();

    // Strip preview URL before sending to backend
    const filesForApi = filesSnapshot.map(({ _previewUrl, ...rest }) => rest);

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
                attached_files: filesForApi.length ? filesForApi : undefined,
            })
        });

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        _agentsCurrentTaskId = data.task_id;

        // Start SSE stream instead of polling
        const evtSource = new EventSource(`/api/tasks/${data.task_id}/events`);
        _agentsPollTimer = evtSource;  // store reference for cancel

        evtSource.onmessage = (e) => {
            try {
                const event = JSON.parse(e.data);
                if (event.type === 'stream_end') {
                    evtSource.close();
                    _agentsPollTimer = null;
                    _agentsIsPolling = false;
                    _agentsCurrentTaskId = null;
                    _agentsUpdateSubmitState();
                    // Auto-rename thread from task prompt if it still has the default date name
                    if (_agentsCurrentWorkspace && _agentsCurrentThread) {
                        const curName = _agentsCurrentThread.name || '';
                        if (/^[A-Z][a-z]+ \d{1,2}, \d{4}( #\d+)?$/.test(curName)) {
                            const slug = prompt.replace(/\s+/g, ' ').trim();
                            const newName = slug.length > 52 ? slug.slice(0, 52) + '…' : slug;
                            _agAutoRenameThread(_agentsCurrentWorkspace.id, _agentsCurrentThread.id, newName);
                        }
                        agentsLoadThreads(_agentsCurrentWorkspace.id);
                    }
                    return;
                }
                renderAgentStep(event);
            } catch (err) {
                console.error('[Agents] SSE parse error:', err);
            }
        };

        evtSource.onerror = () => {
            evtSource.close();
            _agentsPollTimer = null;
            _agentsIsPolling = false;
            _agentsCurrentTaskId = null;
            _agentsUpdateSubmitState();
            renderAgentStep({ type: 'error', title: 'Connection error', detail: 'Lost connection to agent stream' });
        };
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
                // The SSE `done` event already rendered the agent-done-card summary —
                // do NOT call _agentsAppendMessage here or the summary appears twice.
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

// ── Agent step rendering ──────────────────────────────────────
function _htmlEscape(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Per-run view state (reset on each new task start)
let _agentsRenderState = null;

// Thread-level thought counter — persists across tasks, resets on thread switch
let _agentsThoughtTotal = 0;

// ── Reset left panel to empty state (also clears thoughts on thread switch) ──
function _agResetDashboard() {
    if (_agentsRenderState && _agentsRenderState.timerInterval) {
        clearInterval(_agentsRenderState.timerInterval);
    }
    _agentsRenderState = null;
    const leftEmpty   = _agEl('agents-dash-left-empty');
    const dashContent = _agEl('agents-dash-content');
    if (leftEmpty)   leftEmpty.style.display   = 'flex';
    if (dashContent) dashContent.style.display = 'none';

    // Full reset of the thoughts panel — called on thread switch / full re-render
    _agentsThoughtTotal = 0;
    const thoughtsList = _agEl('agents-thoughts-list');
    const rightEmpty   = _agEl('agents-dash-right-empty');
    const badge        = _agEl('agents-thought-badge');
    if (thoughtsList) { thoughtsList.innerHTML = ''; thoughtsList.style.display = 'none'; }
    if (rightEmpty)   rightEmpty.style.display = 'flex';
    if (badge)        { badge.textContent = ''; badge.style.display = 'none'; }
}

// ── Bootstrap a new run ───────────────────────────────────────
function _agInitRender(isReplay = false) {
    const container = _agEl('agents-messages');
    if (!container) return null;

    // Activity block in the main messages area
    const run = document.createElement('div');
    run.className = 'agent-run';

    const activity = document.createElement('div');
    activity.className = 'agent-activity';
    run.appendChild(activity);
    container.appendChild(run);

    // Activate left panel
    const leftEmpty   = _agEl('agents-dash-left-empty');
    const dashContent = _agEl('agents-dash-content');
    const vtl         = _agEl('agents-vert-timeline');
    const planSection = _agEl('agents-plan-section');
    const statsSection= _agEl('agents-stats-section');
    const planList    = _agEl('agents-plan-compact-list');
    if (leftEmpty)    leftEmpty.style.display    = 'none';
    if (dashContent)  dashContent.style.display  = 'flex';
    if (planSection)  planSection.style.display  = 'none';
    if (statsSection) statsSection.style.display = 'block';
    if (planList)     planList.innerHTML          = '';
    if (vtl)          vtl.innerHTML               = '';

    // Right panel (chain of thought) — add a task divider if thoughts already exist,
    // otherwise just ensure the list is visible. Never clear between tasks in same thread.
    const rightEmpty  = _agEl('agents-dash-right-empty');
    const thoughtsList= _agEl('agents-thoughts-list');
    if (thoughtsList && thoughtsList.children.length > 0 && !isReplay) {
        // Insert a task-separator so you can visually tell where each task starts
        const divider = document.createElement('div');
        divider.className = 'agent-thought-divider';
        divider.textContent = '▸ new task';
        thoughtsList.appendChild(divider);
        thoughtsList.scrollTop = thoughtsList.scrollHeight;
    }

    // Elapsed-time timer
    const startTime = Date.now();
    const timerInterval = setInterval(() => {
        const secs = Math.floor((Date.now() - startTime) / 1000);
        const el = _agEl('agents-stat-time');
        if (el) el.textContent =
            String(Math.floor(secs / 60)).padStart(2, '0') + ':' +
            String(secs % 60).padStart(2, '0');
    }, 1000);

    _agentsRenderState = {
        run, activity,
        phases: [],
        planItems: [],
        fileCards: {},   // path → { row, expand, sizeEl, contentEl, writeCount, readCount }
        readCards: {},   // path → { item, row, countEl, count } — dedup read rows
        fileCount: 0,
        cmdCount: 0,
        cmdSuccess: 0,
        cmdFail: 0,
        searchCount: 0,
        tokensIn: 0,
        tokensOut: 0,
        tpsValues: [],   // tok_per_sec per API call — averaged for display
        startTime,
        timerInterval,
        isReplay,        // true when replaying history (skip localStorage writes)
        thoughtCount: 0, // number of thought cards added to right panel
    };
    return _agentsRenderState;
}

// ── Timeline (vertical, renders into left panel) ──────────────
function _agPhaseAdd(id, icon, label) {
    const s = _agentsRenderState;
    if (!s) return;
    const existing = s.phases.find(p => p.id === id);
    if (existing) {
        existing.label = label;
        _agRenderTimeline();
        return;
    }
    s.phases.forEach(p => { if (p.status === 'active') p.status = 'done'; });
    s.phases.push({ id, icon, label, status: 'active' });
    _agRenderTimeline();
}

function _agRenderTimeline() {
    const s = _agentsRenderState;
    if (!s) return;
    const vtl = _agEl('agents-vert-timeline');
    if (!vtl) return;
    vtl.innerHTML = '';
    s.phases.forEach((ph, i) => {
        const item = document.createElement('div');
        item.className = `agent-vtl-item agent-vtl--${ph.status}`;
        item.innerHTML = `
            <div class="agent-vtl-track">
                <span class="agent-vtl-dot"></span>
                ${i < s.phases.length - 1 ? '<span class="agent-vtl-line"></span>' : ''}
            </div>
            <div class="agent-vtl-label">
                <span class="agent-vtl-icon">${ph.icon}</span>
                <span>${ph.label}</span>
            </div>`;
        vtl.appendChild(item);
    });
}

// ── Plan (left panel checklist) ───────────────────────────────
// ── Live LLM token streaming ──────────────────────────────────
// State for the live streaming thought card
let _agLiveTokenCard = null;
let _agLiveTokenText = '';

// State for the live command streaming card (run_command_line events)
let _agCmdStreamCard = null;
let _agCmdStreamLines = [];

/**
 * Append a raw token to the live streaming card in the Thoughts panel.
 * Called for every `llm_token` SSE event while the LLM is generating.
 */
function _agHandleLLMToken(event) {
    const thoughtsList = _agEl('agents-thoughts-list');
    const rightEmpty   = _agEl('agents-dash-right-empty');
    if (!thoughtsList) return;

    // Make the thoughts panel visible
    if (rightEmpty) rightEmpty.style.display = 'none';
    thoughtsList.style.display = 'flex';

    // Create the live card on first token of this LLM call
    if (!_agLiveTokenCard) {
        _agLiveTokenText = '';
        _agLiveTokenCard = document.createElement('div');
        _agLiveTokenCard.className = 'agent-thought-msg agent-thought-streaming';

        const tag = document.createElement('span');
        tag.className = 'agent-thought-tag agent-thought-streaming-tag';
        tag.innerHTML = '<i class="fas fa-circle-notch fa-spin" style="font-size:0.62rem;margin-right:4px;"></i>Thinking…';
        _agLiveTokenCard.appendChild(tag);

        const body = document.createElement('div');
        body.className = 'agent-thought-body agent-thought-live-body';
        _agLiveTokenCard.appendChild(body);

        thoughtsList.appendChild(_agLiveTokenCard);
    }

    _agLiveTokenText += event.token || '';

    const body = _agLiveTokenCard.querySelector('.agent-thought-live-body');
    if (body) {
        // Strip ACTION: lines — they're noise in a "thinking" view
        const display = _agLiveTokenText.split('\nACTION:')[0].trimStart();
        // Show the last 1200 chars so the card doesn't grow unbounded
        body.textContent = display.length > 1200 ? '…' + display.slice(-1200) : display;
    }

    thoughtsList.scrollTop = thoughtsList.scrollHeight;
}

/**
 * Remove the live streaming card.  Called when:
 * - a `thinking` event arrives (full response processed — card replaced by formatted thought)
 * - a `usage` event arrives (end of LLM call)
 * - a `done` or `error` event arrives
 */
function _agFinalizeLiveToken() {
    if (_agLiveTokenCard) {
        _agLiveTokenCard.remove();
        _agLiveTokenCard = null;
        _agLiveTokenText = '';
    }
}

/**
 * Called for each `run_command_line` SSE event — streams shell output into
 * a live card in the Thoughts panel while the command is still running.
 */
function _agHandleCmdLine(event) {
    const thoughtsList = _agEl('agents-thoughts-list');
    const rightEmpty   = _agEl('agents-dash-right-empty');
    if (!thoughtsList) return;

    if (rightEmpty) rightEmpty.style.display = 'none';
    thoughtsList.style.display = 'flex';

    if (!_agCmdStreamCard) {
        _agCmdStreamLines = [];
        _agCmdStreamCard = document.createElement('div');
        _agCmdStreamCard.className = 'agent-thought-msg agent-thought-streaming';

        const tag = document.createElement('span');
        tag.className = 'agent-thought-tag agent-thought-streaming-tag';
        tag.innerHTML = '<i class="fas fa-terminal" style="font-size:0.62rem;margin-right:4px;"></i>Running…';
        _agCmdStreamCard.appendChild(tag);

        const body = document.createElement('div');
        body.className = 'agent-thought-body agent-thought-live-body';
        _agCmdStreamCard.appendChild(body);

        thoughtsList.appendChild(_agCmdStreamCard);
    }

    const line = event.line || '';
    _agCmdStreamLines.push(line);

    const body = _agCmdStreamCard.querySelector('.agent-thought-live-body');
    if (body) {
        // Show last 40 lines to keep the card compact
        const display = _agCmdStreamLines.slice(-40).join('\n');
        body.textContent = display;
        body.scrollTop = body.scrollHeight;
    }
}

/**
 * Remove the live command streaming card once the final run_command event arrives.
 */
function _agFinalizeCmdStream() {
    if (_agCmdStreamCard) {
        _agCmdStreamCard.remove();
        _agCmdStreamCard = null;
        _agCmdStreamLines = [];
    }
}

function _agHandleThinking(event) {
    const s = _agentsRenderState;
    if (!s) return;
    _agFinalizeLiveToken(); // close streaming card before adding formatted thought
    _agPhaseAdd('planning', '🧠', 'Planning');

    const opMatch = (event.title || '').match(/\(([^)]+)\)/);
    const op = opMatch ? opMatch[1].trim() : '';

    if (op === 'set_plan') {
        const lines = (event.detail || '').split('\n').map(l => l.trim()).filter(Boolean);
        s.planItems = lines.map((line, i) => ({
            id: i,
            text: line.replace(/^[-*•\d.]+\s*/, '').trim() || line,
            done: false,
        }));
        _agRenderPlanItems();
    } else if (op === 'mark_done') {
        const hint = (event.detail || '').toLowerCase().trim();
        let marked = false;
        for (const item of s.planItems) {
            if (!item.done) {
                if (!hint || hint.includes(item.text.toLowerCase().slice(0, 30))) {
                    item.done = true; marked = true; break;
                }
            }
        }
        if (!marked) { const next = s.planItems.find(p => !p.done); if (next) next.done = true; }
        _agRenderPlanItems();
    }

    // Push general thinking text (non-plan ops) to right chain-of-thought panel
    const detail = (event.detail || '').trim();
    if (detail && op !== 'set_plan' && op !== 'mark_done' && op !== 'add_note') {
        _agAddThoughtCard(event.title || 'Thinking', detail);
    }
}

function _agAddThoughtCard(title, detail) {
    const s = _agentsRenderState;
    if (!s) return;

    const thoughtsList = _agEl('agents-thoughts-list');
    const rightEmpty   = _agEl('agents-dash-right-empty');
    const badge        = _agEl('agents-thought-badge');
    if (!thoughtsList) return;

    // Show the list, hide empty state
    if (rightEmpty) rightEmpty.style.display = 'none';
    thoughtsList.style.display = 'flex';

    _agentsThoughtTotal++;
    if (s) s.thoughtCount = _agentsThoughtTotal; // keep render state in sync
    if (badge) { badge.style.display = 'inline'; badge.textContent = _agentsThoughtTotal; }

    const msg = document.createElement('div');
    msg.className = 'agent-thought-msg';

    // Label chip (source tag: "Thinking", "🔍 Found…", etc.)
    const tag = document.createElement('span');
    tag.className = 'agent-thought-tag';
    tag.textContent = `#${_agentsThoughtTotal} ${title}`;
    msg.appendChild(tag);

    // Body text rendered as markdown
    const body = document.createElement('div');
    body.className = 'agent-thought-body';
    body.innerHTML = _agentsRenderMarkdown(detail);
    msg.appendChild(body);

    thoughtsList.appendChild(msg);
    // Keep scroll pinned to bottom (Twitch-style)
    thoughtsList.scrollTop = thoughtsList.scrollHeight;
}

function _agRenderPlanItems() {
    const s = _agentsRenderState;
    if (!s) return;
    const planSection = _agEl('agents-plan-section');
    const planList    = _agEl('agents-plan-compact-list');
    const badge       = _agEl('agents-plan-badge');
    if (planSection) planSection.style.display = 'block';
    if (!planList) return;
    planList.innerHTML = '';
    const done  = s.planItems.filter(i => i.done).length;
    const total = s.planItems.length;
    if (badge) badge.textContent = `${done}/${total}`;
    s.planItems.forEach(item => {
        const row = document.createElement('div');
        row.className = 'agents-plan-ci' + (item.done ? ' agents-plan-ci--done' : '');
        row.title = item.text;
        row.textContent = (item.done ? '✅ ' : '⬜ ') + item.text;
        planList.appendChild(row);
    });
}

// ── Stats helpers ──────────────────────────────────────────────
function _agFmtNum(n) {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'k';
    return String(n);
}

function _agCalcCost(inTok, outTok) {
    const modelId = (_agEl('agents-model-select') || {}).value || '';
    const costs   = _agentsModelCosts[modelId];
    if (!costs || (inTok + outTok) === 0) return null;
    return (inTok / 1_000_000 * costs.input) + (outTok / 1_000_000 * costs.output);
}

function _agFmtCost(c) {
    if (c === null) return '—';
    if (c === 0)    return '$0.00';
    if (c < 0.001)  return '<$0.001';
    return '$' + c.toFixed(4);
}

function _agUpdateStats() {
    const s = _agentsRenderState;
    if (!s) return;

    // Files / cmds
    const filesEl   = _agEl('agents-stat-files');
    const cmdsEl    = _agEl('agents-stat-cmds');
    const cmdOkEl   = _agEl('agents-stat-cmd-ok');
    const cmdFailEl = _agEl('agents-stat-cmd-fail');
    if (filesEl)   filesEl.textContent   = `${s.fileCount} file${s.fileCount !== 1 ? 's' : ''}`;
    if (cmdsEl)    cmdsEl.textContent    = `${s.cmdCount} cmd${s.cmdCount !== 1 ? 's' : ''}`;
    if (cmdOkEl)   cmdOkEl.textContent   = s.cmdSuccess > 0 ? `${s.cmdSuccess} ok`   : '—';
    if (cmdFailEl) cmdFailEl.textContent = s.cmdFail    > 0 ? `${s.cmdFail} failed` : '—';

    // Tokens
    const totalTok = s.tokensIn + s.tokensOut;
    const inEl  = _agEl('agents-stat-in-tok');
    const outEl = _agEl('agents-stat-out-tok');
    const totEl = _agEl('agents-stat-total-tok');
    const costEl = _agEl('agents-stat-cost');
    const tpsEl  = _agEl('agents-stat-tps');

    if (inEl)  inEl.textContent  = s.tokensIn  > 0 ? `${_agFmtNum(s.tokensIn)} in`  : '—';
    if (outEl) outEl.textContent = s.tokensOut > 0 ? `${_agFmtNum(s.tokensOut)} out` : '—';
    if (totEl) totEl.textContent = totalTok    > 0 ? _agFmtNum(totalTok)             : '—';
    if (costEl) costEl.textContent = _agFmtCost(_agCalcCost(s.tokensIn, s.tokensOut));

    // tok/s: average of per-call values from the API (avoids wall-clock distortion
    // during history replay where all events process in near-zero elapsed time)
    if (tpsEl) {
        if (s.tpsValues && s.tpsValues.length > 0) {
            const avg = s.tpsValues.reduce((a, b) => a + b, 0) / s.tpsValues.length;
            tpsEl.textContent = `${Math.round(avg)} tok/s`;
        } else {
            tpsEl.textContent = '—';
        }
    }
}

function _agUpdateThreadStats() {
    const threadId = _agentsCurrentThread?.id;
    if (!threadId) return;
    const data = JSON.parse(localStorage.getItem(`agents_thread_stats_${threadId}`) || '{"in":0,"out":0}');
    const total = (data.in || 0) + (data.out || 0);
    const grp   = _agEl('agents-stats-thread-group');
    if (grp && total > 0) grp.style.display = 'block';
    const tokEl  = _agEl('agents-stat-thread-tok');
    const costEl = _agEl('agents-stat-thread-cost');
    if (tokEl)  tokEl.textContent  = total > 0 ? _agFmtNum(total) : '—';
    if (costEl) costEl.textContent = _agFmtCost(_agCalcCost(data.in || 0, data.out || 0));
}

function _agHandleUsage(event) {
    const s = _agentsRenderState;
    if (!s) return;
    s.tokensIn  = event.run_input  || 0;
    s.tokensOut = event.run_output || 0;

    // Collect tok/s from the API (already calculated correctly per call)
    if (event.tok_per_sec && event.tok_per_sec > 0) {
        s.tpsValues.push(event.tok_per_sec);
    }

    // Only accumulate thread totals during live streaming — not history replay.
    // During replay, thread totals are pre-calculated in _agentsRenderMessages
    // from the full history JSON to avoid doubling on every page refresh.
    if (!s.isReplay) {
        const threadId = _agentsCurrentThread?.id;
        if (threadId) {
            const key  = `agents_thread_stats_${threadId}`;
            const prev = JSON.parse(localStorage.getItem(key) || '{"in":0,"out":0}');
            const updated = {
                in:  (prev.in  || 0) + (event.input_tokens  || 0),
                out: (prev.out || 0) + (event.output_tokens || 0),
            };
            localStorage.setItem(key, JSON.stringify(updated));
            _agUpdateThreadStats();
        }
    }

    _agUpdateStats();
}

// ── Observation (image / context acknowledgement) ─────────────
function _agHandleObserve(event) {
    const s = _agentsRenderState;
    if (!s) return;
    _agPhaseAdd('observe', '👁️', 'Observation');

    const detail = event.detail || '';
    const item = document.createElement('div');
    item.className = 'agent-act-item';
    const row = document.createElement('div');
    row.className = 'agent-act-row agent-act--observe';
    row.innerHTML = `<span class="agent-act-icon">👁️</span><span class="agent-act-name">Observation</span>`;

    if (detail) {
        const chevron = document.createElement('span');
        chevron.className = 'agent-act-chevron';
        chevron.textContent = '▾';  // open by default
        row.appendChild(chevron);
        const expand = document.createElement('div');
        expand.className = 'agent-act-expand agent-act-observe-body';
        // Render as markdown so formatting is preserved
        const body = document.createElement('div');
        body.className = 'agent-act-observe-text';
        body.innerHTML = _agentsRenderMarkdown(detail);
        expand.appendChild(body);
        item.appendChild(row);
        item.appendChild(expand);
        row.addEventListener('click', () => {
            const open = expand.style.display !== 'none';
            expand.style.display = open ? 'none' : 'block';
            chevron.textContent = open ? '▸' : '▾';
        });
    } else {
        item.appendChild(row);
    }
    s.activity.appendChild(item);
}

// ── File activity rows ─────────────────────────────────────────
function _agFormatBytes(b) {
    if (b < 1024)        return `${b} B`;
    if (b < 1048576)     return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1048576).toFixed(1)} MB`;
}

// ── Delete file activity row ───────────────────────────────────
function _agHandleDeleteFile(event) {
    const s = _agentsRenderState;
    if (!s) return;
    const path     = event.path || (event.title || '').replace(/^Deleting\s+/, '').trim();
    const filename = path.replace(/\\/g, '/').split('/').pop() || path;
    const result   = event.result || '';

    // Remove from fileCards if it was tracked
    if (s.fileCards[path]) {
        const fc = s.fileCards[path];
        fc.row.closest('.agent-act-item')?.classList.add('agent-act--deleted');
        const nameEl = fc.row.querySelector('.agent-act-name');
        if (nameEl) nameEl.style.textDecoration = 'line-through';
        delete s.fileCards[path];
    }

    const item = document.createElement('div');
    item.className = 'agent-act-item';
    const row = document.createElement('div');
    row.className = 'agent-act-row agent-act--delete';
    row.innerHTML = `<span class="agent-act-icon">🗑️</span><span class="agent-act-name agent-act-name--del">${_htmlEscape(filename)}</span><span class="agent-act-path">${_htmlEscape(path)}</span>`;
    if (result && result.startsWith('Error')) {
        const err = document.createElement('span');
        err.className = 'agent-act-error-inline';
        err.textContent = result;
        row.appendChild(err);
    }
    item.appendChild(row);
    s.activity.appendChild(item);
}

function _agHandleWriteFile(event) {
    const s = _agentsRenderState;
    if (!s) return;
    s.fileCount++;
    _agPhaseAdd('files', '📄', `Files · ${s.fileCount}`);
    _agUpdateStats();

    const path      = event.path || (event.title || '').replace(/^Writing\s+/, '').trim();
    const filename  = path.replace(/\\/g, '/').split('/').pop() || path;
    const detail    = event.detail || '';
    const truncated = detail.length > 4000 ? detail.slice(0, 4000) + '\n…' : detail;
    const sizeStr   = event.bytes ? _agFormatBytes(event.bytes) : '';

    if (s.fileCards[path]) {
        const fc = s.fileCards[path];
        fc.writeCount++;
        if (fc.sizeEl)    fc.sizeEl.textContent    = sizeStr;
        if (fc.contentEl && detail) fc.contentEl.textContent = truncated;
        // Update verb to show modified count
        const verbEl = fc.row.querySelector('.agent-act-verb');
        if (verbEl) verbEl.textContent = `Modified ×${fc.writeCount}`;
        fc.row.classList.add('agent-act--flash');
        setTimeout(() => fc.row.classList.remove('agent-act--flash'), 600);
    } else {
        // If a read card exists for this path, remove it — the write card absorbs it
        if (s.readCards[path]) {
            s.readCards[path].item.remove();
            delete s.readCards[path];
        }

        const item    = document.createElement('div');
        item.className = 'agent-act-item';
        const row     = document.createElement('div');
        row.className = 'agent-act-row agent-act--file';

        row.innerHTML = `<span class="agent-act-icon">📄</span><span class="agent-act-name">${_htmlEscape(filename)}</span>`;

        const verbEl = document.createElement('span');
        verbEl.className = 'agent-act-verb agent-act-verb--write';
        verbEl.textContent = 'Writing';
        row.appendChild(verbEl);

        const pathSpan = document.createElement('span');
        pathSpan.className = 'agent-act-path';
        pathSpan.textContent = path;
        row.appendChild(pathSpan);

        const sizeEl  = document.createElement('span');
        sizeEl.className = 'agent-act-size';
        sizeEl.textContent = sizeStr;
        row.appendChild(sizeEl);

        // Undo button — only if a backup exists for this file
        if (event.has_backup) {
            const undoBtn = document.createElement('button');
            undoBtn.className = 'agent-act-undo-btn';
            undoBtn.title = 'Restore previous version';
            undoBtn.textContent = '↩';
            undoBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                _agRestoreFile(path, undoBtn);
            });
            row.appendChild(undoBtn);
        }

        const chevron = document.createElement('span');
        chevron.className = 'agent-act-chevron';
        chevron.textContent = '▸';
        row.appendChild(chevron);

        const expand = document.createElement('div');
        expand.className = 'agent-act-expand';
        expand.style.display = 'none';
        if (event.result) {
            const res = document.createElement('div');
            res.className = 'agent-act-result';
            res.textContent = event.result;
            expand.appendChild(res);
        }
        // ── Inline diff view ──────────────────────────────────────
        if (event.diff) {
            const diffWrap = document.createElement('div');
            diffWrap.className = 'agent-act-diff';
            event.diff.split('\n').forEach(line => {
                const span = document.createElement('div');
                span.className = 'ag-diff-line';
                if      (line.startsWith('+') && !line.startsWith('+++')) span.classList.add('ag-diff-add');
                else if (line.startsWith('-') && !line.startsWith('---')) span.classList.add('ag-diff-del');
                else if (line.startsWith('@@'))                           span.classList.add('ag-diff-hunk');
                else if (line.startsWith('---') || line.startsWith('+++')) span.classList.add('ag-diff-header');
                span.textContent = line;
                diffWrap.appendChild(span);
            });
            expand.appendChild(diffWrap);
        } else {
            // No diff (new file) — show raw content preview
            const contentEl = document.createElement('pre');
            contentEl.className = 'agent-act-content';
            contentEl.textContent = truncated;
            expand.appendChild(contentEl);
        }

        item.appendChild(row);
        item.appendChild(expand);
        row.addEventListener('click', () => {
            const open = expand.style.display !== 'none';
            expand.style.display = open ? 'none' : 'block';
            chevron.textContent = open ? '▸' : '▾';
        });

        s.fileCards[path] = { row, expand, sizeEl, writeCount: 1 };
        s.activity.appendChild(item);
    }
}

// ── Command activity rows ──────────────────────────────────────
function _agHandleCommand(event) {
    const s = _agentsRenderState;
    if (!s) return;
    _agFinalizeCmdStream();  // close any streaming preview card in Thoughts
    s.cmdCount++;
    const result  = event.result || '';
    const failed  = result.trimStart().startsWith('(exit ');
    if (failed) s.cmdFail++; else s.cmdSuccess++;
    _agPhaseAdd('commands', '⚡', `Commands · ${s.cmdCount}`);
    _agUpdateStats();

    const cmd     = (event.command || event.title || '').replace(/^\$\s*/, '');
    const detail  = event.detail || '';
    const hasBody = !!(result || detail);

    const item = document.createElement('div');
    item.className = 'agent-act-item';
    const row = document.createElement('div');
    row.className = `agent-act-row agent-act--cmd${failed ? ' agent-act--cmd-fail' : ''}`;
    row.innerHTML = `<span class="agent-act-icon">${failed ? '✗' : '⚡'}</span><span class="agent-act-name agent-act-name--mono">$ ${_htmlEscape(cmd)}</span>`;

    if (hasBody) {
        const chevron = document.createElement('span');
        chevron.className = 'agent-act-chevron';
        chevron.textContent = failed ? '▾' : '▸'; // auto-expand failures
        row.appendChild(chevron);
        const expand = document.createElement('div');
        expand.className = 'agent-act-expand';
        expand.style.display = failed ? 'block' : 'none'; // show failures immediately
        if (result) { const r = document.createElement('div'); r.className = `agent-act-result${failed ? ' agent-act-result--fail' : ''}`; r.textContent = result; expand.appendChild(r); }
        if (detail) { const pre = document.createElement('pre'); pre.className = 'agent-act-content'; pre.textContent = detail.length > 5000 ? detail.slice(0, 5000) + '\n…' : detail; expand.appendChild(pre); }
        item.appendChild(row);
        item.appendChild(expand);
        row.addEventListener('click', () => { const open = expand.style.display !== 'none'; expand.style.display = open ? 'none' : 'block'; chevron.textContent = open ? '▸' : '▾'; });
    } else {
        item.appendChild(row);
    }
    s.activity.appendChild(item);
}

// ── Read / list (compact dimmed, deduplicated) ─────────────────
function _agHandleReadFile(event) {
    const s = _agentsRenderState;
    if (!s) return;
    const path = event.path || event.title || '';
    const filename = path.replace(/\\/g, '/').split('/').pop() || path;

    // File already has a write card — add a small "also read ×N" badge to it
    if (s.fileCards[path]) {
        const fc = s.fileCards[path];
        let rcEl = fc.row.querySelector('.agent-act-rcount');
        if (!rcEl) {
            rcEl = document.createElement('span');
            rcEl.className = 'agent-act-rcount';
            const chevron = fc.row.querySelector('.agent-act-chevron');
            fc.row.insertBefore(rcEl, chevron || null);
        }
        fc.readCount = (fc.readCount || 0) + 1;
        rcEl.textContent = `📖 ×${fc.readCount}`;
        return;
    }

    // Same file read again — update existing read row's count badge
    if (s.readCards[path]) {
        const rc = s.readCards[path];
        rc.count++;
        rc.countEl.textContent = `×${rc.count}`;
        rc.countEl.style.display = '';
        rc.item.classList.add('agent-act--flash');
        setTimeout(() => rc.item.classList.remove('agent-act--flash'), 400);
        return;
    }

    // First read — create compact row with action verb
    const item = document.createElement('div');
    item.className = 'agent-act-item';
    const row = document.createElement('div');
    row.className = 'agent-act-row agent-act--read';

    row.innerHTML = `<span class="agent-act-icon">📖</span><span class="agent-act-name">${_htmlEscape(filename)}</span>`;

    const verbEl = document.createElement('span');
    verbEl.className = 'agent-act-verb agent-act-verb--read';
    verbEl.textContent = 'Reading';
    row.appendChild(verbEl);

    const countEl = document.createElement('span');
    countEl.className = 'agent-act-rcount';
    countEl.style.display = 'none';
    row.appendChild(countEl);

    const pathEl = document.createElement('span');
    pathEl.className = 'agent-act-path';
    pathEl.textContent = path;
    row.appendChild(pathEl);

    item.appendChild(row);
    s.activity.appendChild(item);
    s.readCards[path] = { item, row, countEl, count: 1 };
}

function _agHandleListDir(event) {
    const s = _agentsRenderState;
    if (!s) return;
    const path   = event.path || '.';
    const detail = event.result || '';
    const item   = document.createElement('div');
    item.className = 'agent-act-item';
    const row = document.createElement('div');
    row.className = 'agent-act-row agent-act--dir';
    row.innerHTML = `<span class="agent-act-icon">📂</span><span class="agent-act-name agent-act-name--mono">${_htmlEscape(path)}</span>`;
    if (detail) {
        const chevron = document.createElement('span');
        chevron.className = 'agent-act-chevron';
        chevron.textContent = '▸';
        row.appendChild(chevron);
        const expand = document.createElement('div');
        expand.className = 'agent-act-expand';
        expand.style.display = 'none';
        const pre = document.createElement('pre');
        pre.className = 'agent-act-content';
        pre.textContent = detail;
        expand.appendChild(pre);
        item.appendChild(row);
        item.appendChild(expand);
        row.addEventListener('click', () => { const open = expand.style.display !== 'none'; expand.style.display = open ? 'none' : 'block'; chevron.textContent = open ? '▸' : '▾'; });
    } else {
        item.appendChild(row);
    }
    s.activity.appendChild(item);
}

// ── Web search ─────────────────────────────────────────────────
function _agHandleSearch(event) {
    const s = _agentsRenderState;
    if (!s) return;
    const query  = event.query || event.title || '';
    s.searchCount = (s.searchCount || 0) + 1;
    _agPhaseAdd('search', '🔍', `Web · ${s.searchCount}`);
    const result = event.result || '';
    const item   = document.createElement('div');
    item.className = 'agent-act-item';
    const row = document.createElement('div');
    row.className = 'agent-act-row agent-act--search';
    row.innerHTML = `<span class="agent-act-icon">🔍</span><span class="agent-act-name">${_htmlEscape(query)}</span>`;
    if (result) {
        const chevron = document.createElement('span');
        chevron.className = 'agent-act-chevron';
        chevron.textContent = '▸';
        row.appendChild(chevron);
        const expand = document.createElement('div');
        expand.className = 'agent-act-expand';
        expand.style.display = 'none';
        // Render each result block as a mini card
        const blocks = result.split(/\n---\n/);
        blocks.forEach(block => {
            const lines = block.trim().split('\n');
            const title = lines[0]?.replace(/^\[|\]$/g, '') || '';
            const url   = lines[1] || '';
            const body  = lines.slice(2).join('\n').trim();
            const card = document.createElement('div');
            card.className = 'agent-search-result';
            card.innerHTML = `<div class="agent-search-title">${_htmlEscape(title)}</div>${url ? `<a class="agent-search-url" href="${_htmlEscape(url)}" target="_blank" rel="noopener">${_htmlEscape(url)}</a>` : ''}${body ? `<div class="agent-search-snippet">${_htmlEscape(body)}</div>` : ''}`;
            expand.appendChild(card);
        });
        item.appendChild(row);
        item.appendChild(expand);
        row.addEventListener('click', () => { const open = expand.style.display !== 'none'; expand.style.display = open ? 'none' : 'block'; chevron.textContent = open ? '▸' : '▾'; });

        // Push a condensed summary of findings to the thoughts panel
        _agSearchToThought(query, result, blocks);
    } else {
        item.appendChild(row);
    }
    s.activity.appendChild(item);
}

// Push search findings as a thought card so the right panel reflects what was found
function _agSearchToThought(query, rawResult, blocks) {
    if (!rawResult || rawResult === 'No results found.' || rawResult.startsWith('Search error')) return;
    // Build a compact markdown summary: query as heading + top result titles
    const topTitles = blocks
        .slice(0, 5)
        .map(b => b.trim().split('\n')[0]?.replace(/^\[|\]$/g, '').trim())
        .filter(Boolean);
    if (!topTitles.length) return;
    const md = `**Search:** ${query}\n\n**Top results:**\n${topTitles.map(t => `- ${t}`).join('\n')}`;
    _agAddThoughtCard(`🔍 Found ${topTitles.length} results`, md);
}

// ── URL fetch ──────────────────────────────────────────────────
function _agHandleFetch(event) {
    const s = _agentsRenderState;
    if (!s) return;
    const url    = event.url || event.title || '';
    const result = event.result || '';
    const item   = document.createElement('div');
    item.className = 'agent-act-item';
    const row = document.createElement('div');
    row.className = 'agent-act-row agent-act--fetch';
    const shortUrl = url.replace(/^https?:\/\//, '');
    row.innerHTML = `<span class="agent-act-icon">🌐</span><span class="agent-act-name agent-act-name--mono">${_htmlEscape(shortUrl)}</span>`;
    if (result) {
        const chevron = document.createElement('span');
        chevron.className = 'agent-act-chevron';
        chevron.textContent = '▸';
        row.appendChild(chevron);
        const expand = document.createElement('div');
        expand.className = 'agent-act-expand';
        expand.style.display = 'none';
        const pre = document.createElement('pre');
        pre.className = 'agent-act-content';
        pre.textContent = result.slice(0, 1500);
        expand.appendChild(pre);
        item.appendChild(row);
        item.appendChild(expand);
        row.addEventListener('click', () => { const open = expand.style.display !== 'none'; expand.style.display = open ? 'none' : 'block'; chevron.textContent = open ? '▸' : '▾'; });

        // Push a short fetch summary to the thoughts panel
        if (!result.startsWith('Fetch error') && !result.startsWith('HTTP 4') && !result.startsWith('HTTP 5')) {
            const snippet = result.replace(/^HTTP \d+\n/, '').slice(0, 300).trim();
            if (snippet) {
                _agAddThoughtCard(`🌐 Fetched ${shortUrl}`, `**URL:** ${url}\n\n\`\`\`\n${snippet}${result.length > 300 ? '\n…' : ''}\n\`\`\``);
            }
        }
    } else {
        item.appendChild(row);
    }
    s.activity.appendChild(item);
}

// ── Glob / move_file / create_directory ──────────────────────
function _agHandleGlob(event) {
    const s = _agentsRenderState;
    if (!s) return;
    const pattern = event.pattern || event.title || '';
    const result  = event.result  || '';

    const item = document.createElement('div');
    item.className = 'agent-act-item';
    const row = document.createElement('div');
    row.className = 'agent-act-row agent-act--search';
    row.innerHTML = `<span class="agent-act-icon">🔍</span><span class="agent-act-name agent-act-name--mono">${_htmlEscape(pattern)}</span>`;

    const verbEl = document.createElement('span');
    verbEl.className = 'agent-act-verb';
    verbEl.textContent = 'glob';
    row.appendChild(verbEl);

    if (result) {
        const count = result.split('\n').filter(Boolean).length;
        const badge = document.createElement('span');
        badge.className = 'agent-act-size';
        badge.textContent = `${count} file${count !== 1 ? 's' : ''}`;
        const chevron = document.createElement('span');
        chevron.className = 'agent-act-chevron';
        chevron.textContent = '▸';
        row.appendChild(badge);
        row.appendChild(chevron);
        const expand = document.createElement('div');
        expand.className = 'agent-act-expand';
        expand.style.display = 'none';
        const pre = document.createElement('pre');
        pre.className = 'agent-act-content';
        pre.textContent = result.length > 2000 ? result.slice(0, 2000) + '\n…' : result;
        expand.appendChild(pre);
        item.appendChild(row);
        item.appendChild(expand);
        row.addEventListener('click', () => {
            const open = expand.style.display !== 'none';
            expand.style.display = open ? 'none' : 'block';
            chevron.textContent = open ? '▸' : '▾';
        });
    } else {
        item.appendChild(row);
    }
    s.activity.appendChild(item);
}

function _agHandleMoveFile(event) {
    const s = _agentsRenderState;
    if (!s) return;
    s.fileCount++;
    _agPhaseAdd('files', '📄', `Files · ${s.fileCount}`);
    _agUpdateStats();

    const src = event.src || '';
    const dst = event.dst || '';
    const dstFilename = dst.replace(/\\/g, '/').split('/').pop() || dst;

    const item = document.createElement('div');
    item.className = 'agent-act-item';
    const row = document.createElement('div');
    row.className = 'agent-act-row agent-act--file';
    row.innerHTML = `<span class="agent-act-icon">📄</span><span class="agent-act-name">${_htmlEscape(dstFilename)}</span>`;

    const verbEl = document.createElement('span');
    verbEl.className = 'agent-act-verb agent-act-verb--write';
    verbEl.textContent = 'Moved';
    row.appendChild(verbEl);

    const pathSpan = document.createElement('span');
    pathSpan.className = 'agent-act-path';
    pathSpan.textContent = `${src} → ${dst}`;
    row.appendChild(pathSpan);

    if (event.result) {
        const res = document.createElement('span');
        res.className = 'agent-act-size';
        res.textContent = event.result.startsWith('Error') ? '✗' : '✓';
        row.appendChild(res);
    }
    item.appendChild(row);
    s.activity.appendChild(item);
}

function _agHandleCreateDir(event) {
    const s = _agentsRenderState;
    if (!s) return;
    const path = event.path || '';

    const item = document.createElement('div');
    item.className = 'agent-act-item';
    const row = document.createElement('div');
    row.className = 'agent-act-row agent-act--search';
    row.innerHTML = `<span class="agent-act-icon">📁</span><span class="agent-act-name">${_htmlEscape(path)}</span>`;
    const verbEl = document.createElement('span');
    verbEl.className = 'agent-act-verb';
    verbEl.textContent = 'mkdir';
    row.appendChild(verbEl);
    item.appendChild(row);
    s.activity.appendChild(item);
}

// ── Blueprint scan ────────────────────────────────────────────
function _agHandleBlueprint(event) {
    const s = _agentsRenderState;
    if (!s) return;
    const label = event.title || 'Blueprint scan';
    const result = event.result || '';

    const item = document.createElement('div');
    item.className = 'agent-act-item';
    const row = document.createElement('div');
    row.className = 'agent-act-row agent-act--read';
    row.innerHTML = `<span class="agent-act-icon">📐</span><span class="agent-act-name">${_htmlEscape(label)}</span>`;

    const verbEl = document.createElement('span');
    verbEl.className = 'agent-act-verb agent-act-verb--read';
    verbEl.textContent = 'Scanned';
    row.appendChild(verbEl);

    if (result) {
        const lineCount = result.split('\n').length;
        const countEl = document.createElement('span');
        countEl.className = 'agent-act-size';
        countEl.textContent = `${lineCount} entries`;
        row.appendChild(countEl);
    }

    item.appendChild(row);
    s.activity.appendChild(item);
}

// ── Codebase search ───────────────────────────────────────────
function _agHandleSearchCodebase(event) {
    const s = _agentsRenderState;
    if (!s) return;
    const query  = event.query  || '';
    const path   = event.path   || '';
    const result = event.result || '';

    const item = document.createElement('div');
    item.className = 'agent-act-item';
    const row = document.createElement('div');
    row.className = 'agent-act-row agent-act--read';
    row.innerHTML = `<span class="agent-act-icon">🔍</span><span class="agent-act-name agent-act-name--mono">${_htmlEscape(query)}</span>`;

    const verbEl = document.createElement('span');
    verbEl.className = 'agent-act-verb agent-act-verb--read';
    verbEl.textContent = path ? `in ${path.replace(/\\/g, '/').split('/').pop() || path}` : 'codebase';
    row.appendChild(verbEl);

    if (result && !result.startsWith('Error') && !result.startsWith('No match')) {
        const matchCount = (result.match(/^[^:]+:\d+:/gm) || []).length || result.split('\n').filter(Boolean).length;
        const chevron = document.createElement('span');
        chevron.className = 'agent-act-chevron';
        chevron.textContent = '▸';

        const countEl = document.createElement('span');
        countEl.className = 'agent-act-size';
        countEl.textContent = `${matchCount} match${matchCount !== 1 ? 'es' : ''}`;
        row.appendChild(countEl);
        row.appendChild(chevron);

        const expand = document.createElement('div');
        expand.className = 'agent-act-expand';
        expand.style.display = 'none';
        const pre = document.createElement('pre');
        pre.className = 'agent-act-content';
        pre.textContent = result.length > 3000 ? result.slice(0, 3000) + '\n…' : result;
        expand.appendChild(pre);

        item.appendChild(row);
        item.appendChild(expand);
        row.addEventListener('click', () => {
            const open = expand.style.display !== 'none';
            expand.style.display = open ? 'none' : 'block';
            chevron.textContent = open ? '▸' : '▾';
        });
    } else {
        item.appendChild(row);
    }

    s.activity.appendChild(item);
}

// ── Restore file (undo) ────────────────────────────────────────

/**
 * Called when the user clicks the ↩ undo button on a file card.
 * POSTs to the restore endpoint then flashes feedback on the button.
 */
async function _agRestoreFile(path, btnEl) {
    const wsId = _agentsCurrentWorkspace && _agentsCurrentWorkspace.id;
    if (!wsId) return;
    btnEl.disabled = true;
    btnEl.textContent = '…';
    try {
        const res = await fetch(`/api/agents/workspaces/${wsId}/restore`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path }),
        });
        if (res.ok) {
            btnEl.textContent = '✓';
            btnEl.style.color = 'var(--success, #22c55e)';
            setTimeout(() => { btnEl.textContent = '↩'; btnEl.style.color = ''; btnEl.disabled = false; }, 2000);
        } else {
            const err = await res.json().catch(() => ({ detail: 'Error' }));
            btnEl.textContent = '✗';
            btnEl.style.color = 'var(--error, #ef4444)';
            btnEl.title = err.detail || 'Restore failed';
            setTimeout(() => { btnEl.textContent = '↩'; btnEl.style.color = ''; btnEl.disabled = false; }, 3000);
        }
    } catch (e) {
        btnEl.textContent = '✗';
        setTimeout(() => { btnEl.textContent = '↩'; btnEl.disabled = false; }, 2000);
    }
}

/** Show a compact "Restored path" row in the activity panel. */
function _agHandleRestoreFile(event) {
    const s = _agentsRenderState;
    if (!s) return;
    const path = event.path || '';
    const filename = path.replace(/\\/g, '/').split('/').pop() || path;

    const item = document.createElement('div');
    item.className = 'agent-act-item';
    const row = document.createElement('div');
    row.className = 'agent-act-row agent-act--read';
    row.innerHTML = `<span class="agent-act-icon">↩</span><span class="agent-act-name">${_htmlEscape(filename)}</span>`;
    const verbEl = document.createElement('span');
    verbEl.className = 'agent-act-verb';
    verbEl.textContent = 'Restored';
    row.appendChild(verbEl);
    item.appendChild(row);
    s.activity.appendChild(item);
}

// ── Completion ─────────────────────────────────────────────────
function _agFinishRender(event) {
    const s = _agentsRenderState;
    if (!s) return;
    if (s.timerInterval) clearInterval(s.timerInterval);

    const isOk  = event.type === 'done';
    const label = event.title || (isOk ? 'Completed' : 'Error');
    const detail = (event.detail || '').trim();

    s.phases.forEach(p => { p.status = 'done'; });
    s.phases.push({ id: 'final', icon: isOk ? '✅' : '❌', label: isOk ? 'Done' : 'Error', status: isOk ? 'done' : 'error' });
    _agRenderTimeline();
    if (isOk) { s.planItems.forEach(i => { i.done = true; }); _agRenderPlanItems(); }

    // ── Summary card ──────────────────────────────────────────────
    const card = document.createElement('div');
    card.className = `agent-done-card ${isOk ? 'agent-done-card--ok' : 'agent-done-card--err'}`;

    const hdr = document.createElement('div');
    hdr.className = 'agent-done-card-header';
    hdr.innerHTML = `<span class="agent-done-card-icon">${isOk ? '✅' : '❌'}</span><span class="agent-done-card-label">${_htmlEscape(label)}</span>`;
    card.appendChild(hdr);

    if (detail) {
        const body = document.createElement('div');
        body.className = 'agent-done-card-body';
        body.innerHTML = _agentsRenderMarkdown(detail);
        card.appendChild(body);
    }

    s.activity.appendChild(card);
}

// ── Main entry point (called for every SSE event) ─────────────
function renderAgentStep(event, isReplay = false) {
    const container = _agEl('agents-messages');
    if (!container) return;
    const emptyState = _agEl('agents-empty-state');
    if (emptyState) emptyState.style.display = 'none';

    if (event.type === 'stream_end') return;

    if (event.type === 'start') {
        _agentsHideTyping();
        _agInitRender(isReplay);
        _agPhaseAdd('start', '🚀', 'Started');
        const s = _agentsRenderState;
        if (s) {
            const ti = document.createElement('div');
            ti.className = 'agent-typing-indicator';
            ti.innerHTML = '<span></span><span></span><span></span>';
            s.activity.appendChild(ti);
        }
        container.scrollTop = container.scrollHeight;
        return;
    }

    if (!_agentsRenderState) _agInitRender(isReplay);
    const s = _agentsRenderState;

    if (event.type === 'done' || event.type === 'error') {
        const ti = s.activity.querySelector('.agent-typing-indicator');
        if (ti) ti.remove();
        _agentsHideTyping();
        _agFinalizeLiveToken();  // close any open LLM streaming card
        _agFinalizeCmdStream();  // close any open command streaming card
        _agFinishRender(event);
        container.scrollTop = container.scrollHeight;
        return;
    }

    switch (event.type) {
        case 'llm_token':        _agHandleLLMToken(event);                            break;
        case 'run_command_line': _agHandleCmdLine(event);                             break;
        case 'thinking':         _agHandleThinking(event);                            break;
        case 'observe':          _agHandleObserve(event);                             break;
        case 'write_file':       _agHandleWriteFile(event);                           break;
        case 'delete_file':      _agHandleDeleteFile(event);                          break;
        case 'read_file':        _agHandleReadFile(event);                            break;
        case 'list_dir':         _agHandleListDir(event);                             break;
        case 'run_command':      _agHandleCommand(event);                             break;
        case 'search_web':       _agHandleSearch(event);                              break;
        case 'fetch_url':        _agHandleFetch(event);                               break;
        case 'glob':                  _agHandleGlob(event);                                break;
        case 'move_file':             _agHandleMoveFile(event);                            break;
        case 'create_directory':      _agHandleCreateDir(event);                           break;
        case 'restore_file':          _agHandleRestoreFile(event);                         break;
        case 'get_project_blueprint': _agHandleBlueprint(event);                           break;
        case 'search_codebase':       _agHandleSearchCodebase(event);                      break;
        case 'usage':                 _agFinalizeLiveToken(); _agHandleUsage(event);       break;
        default:
            // Unknown event type — log for diagnostics, don't crash
            if (event.type && event.type !== 'start' && event.type !== 'stream_end') {
                console.debug('[AgentUI] unhandled event type:', event.type, event);
            }
    }

    const ti = s.activity.querySelector('.agent-typing-indicator');
    if (ti) s.activity.appendChild(ti);
    container.scrollTop = container.scrollHeight;
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
    _agentsBrowserHide();
}

// ── Folder browser ────────────────────────────────────────────
let _agentsBrowserOpen = false;

async function _agentsBrowserNavigate(path) {
    const browser = _agEl('agents-folder-browser');
    const crumb = _agEl('agents-browser-crumb');
    const list = _agEl('agents-browser-list');
    if (!browser || !crumb || !list) return;

    try {
        list.innerHTML = '<div class="agents-browser-loading">Loading…</div>';
        const resp = await fetch(`/api/agents/browse?path=${encodeURIComponent(path || '')}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        // Render breadcrumb — split path into clickable segments
        const parts = data.path.replace(/\\/g, '/').split('/').filter(Boolean);
        let builtPath = data.path.startsWith('/') ? '/' : '';
        // Detect Windows drive root (e.g. C:)
        const isWindows = /^[A-Za-z]:/.test(data.path);
        crumb.innerHTML = '';

        if (isWindows) {
            // Windows: C:\foo\bar
            const winParts = data.path.replace(/\//g, '\\').split('\\').filter(Boolean);
            let accumulated = '';
            winParts.forEach((part, i) => {
                accumulated = i === 0 ? part + '\\' : accumulated + part + (i < winParts.length - 1 ? '\\' : '');
                const seg = document.createElement('span');
                seg.className = 'agents-crumb-seg';
                seg.textContent = i === 0 ? part : part;
                const acc = accumulated; // capture
                seg.onclick = () => _agentsBrowserNavigate(acc);
                crumb.appendChild(seg);
                if (i < winParts.length - 1) {
                    const sep = document.createElement('span');
                    sep.className = 'agents-crumb-sep';
                    sep.textContent = '\\';
                    crumb.appendChild(sep);
                }
            });
        } else {
            // Unix
            const rootSeg = document.createElement('span');
            rootSeg.className = 'agents-crumb-seg';
            rootSeg.textContent = '/';
            rootSeg.onclick = () => _agentsBrowserNavigate('/');
            crumb.appendChild(rootSeg);
            parts.forEach((part, i) => {
                builtPath += (builtPath.endsWith('/') ? '' : '/') + part;
                const seg = document.createElement('span');
                seg.className = 'agents-crumb-seg';
                seg.textContent = part;
                const acc = builtPath;
                seg.onclick = () => _agentsBrowserNavigate(acc);
                crumb.appendChild(seg);
                if (i < parts.length - 1) {
                    const sep = document.createElement('span');
                    sep.className = 'agents-crumb-sep';
                    sep.textContent = '/';
                    crumb.appendChild(sep);
                }
            });
        }

        // Render directory list
        list.innerHTML = '';

        // Up button
        if (data.parent) {
            const upBtn = document.createElement('div');
            upBtn.className = 'agents-browser-entry agents-browser-up';
            upBtn.innerHTML = '<i class="fas fa-level-up-alt"></i> ..';
            upBtn.onclick = () => _agentsBrowserNavigate(data.parent);
            list.appendChild(upBtn);
        }

        if (data.entries.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'agents-browser-empty';
            empty.textContent = 'No subdirectories';
            list.appendChild(empty);
        } else {
            data.entries.forEach(entry => {
                const row = document.createElement('div');
                row.className = 'agents-browser-entry';
                row.innerHTML = `<i class="fas fa-folder"></i> <span>${entry.name}</span>`;
                row.title = entry.path;
                // Single click → navigate into
                row.onclick = () => _agentsBrowserNavigate(entry.path);
                // Double-click or select button → pick this folder
                const pick = document.createElement('button');
                pick.className = 'agents-browser-pick';
                pick.title = 'Select this folder';
                pick.innerHTML = '<i class="fas fa-check"></i>';
                pick.onclick = (e) => {
                    e.stopPropagation();
                    _agentsBrowserSelect(entry.path, entry.name);
                };
                row.appendChild(pick);
                list.appendChild(row);
            });
        }

        // "Select current folder" button at bottom
        const selCurrent = document.createElement('button');
        selCurrent.className = 'agents-browser-select-current';
        selCurrent.innerHTML = `<i class="fas fa-check-circle"></i> Use this folder`;
        selCurrent.onclick = () => {
            const folderName = data.path.replace(/\\/g, '/').split('/').filter(Boolean).pop() || data.path;
            _agentsBrowserSelect(data.path, folderName);
        };
        list.appendChild(selCurrent);

    } catch (e) {
        console.error('[Agents] Browse error:', e);
        list.innerHTML = `<div class="agents-browser-empty">Error: ${e.message}</div>`;
    }
}

function _agentsBrowserSelect(path, name) {
    const pathInput = _agEl('agents-ws-path-input');
    const nameInput = _agEl('agents-ws-name-input');
    if (pathInput) pathInput.value = path;
    if (nameInput && !nameInput.value) nameInput.value = name;
    _agentsBrowserHide();
}

function _agentsBrowserHide() {
    const browser = _agEl('agents-folder-browser');
    if (browser) browser.style.display = 'none';
    _agentsBrowserOpen = false;
}

async function _agentsBrowserToggle() {
    const browser = _agEl('agents-folder-browser');
    if (!browser) return;
    if (_agentsBrowserOpen) {
        _agentsBrowserHide();
    } else {
        browser.style.display = 'block';
        _agentsBrowserOpen = true;
        // Start at current path input value, or home
        const pathInput = _agEl('agents-ws-path-input');
        const startPath = pathInput ? pathInput.value.trim() : '';
        await _agentsBrowserNavigate(startPath);
    }
}

async function _agentsNativeBrowse() {
    const browseBtn = _agEl('agents-browse-btn');
    const pathInput = _agEl('agents-ws-path-input');

    // Show a spinner while the user has the dialog open
    if (browseBtn) {
        browseBtn.disabled = true;
        browseBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    }

    try {
        const currentPath = pathInput ? pathInput.value.trim() : '';
        const url = '/api/agents/browse/native' + (currentPath ? `?initial=${encodeURIComponent(currentPath)}` : '');
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        if (!data.cancelled && data.path) {
            _agentsBrowserSelect(data.path, data.name || '');
        }
    } catch (e) {
        console.error('[Agents] Native browse error:', e);
        if (typeof showToast === 'function') showToast('Could not open folder picker', 'error');
    } finally {
        if (browseBtn) {
            browseBtn.disabled = false;
            browseBtn.innerHTML = '<i class="fas fa-folder-open"></i>';
        }
    }
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

        // Cache model costs for stats calculation
        _agentsModelCosts = {};
        for (const m of data.models || []) {
            _agentsModelCosts[m.id] = {
                input:  m.input_cost_per_1m_tokens  || 0,
                output: m.output_cost_per_1m_tokens || 0,
            };
        }

        const sel = _agEl('agents-model-select');
        if (!sel) return;

        // Use the same grouped dropdown as other tabs
        const opts = generateCategorizedModelOptions(data, 'chat');
        sel.innerHTML = opts;

        // Restore saved model
        const saved = localStorage.getItem('agents_model_id');
        if (saved) {
            const opt = sel.querySelector(`option[value="${CSS.escape(saved)}"]`);
            if (opt) sel.value = saved;
        }
    } catch (e) {
        console.error('[Agents] Failed to load models:', e);
    }
}

// ── File attachment helpers ────────────────────────────────────
function _agentsRenderAttachStrip() {
    const strip = _agEl('agents-attach-strip');
    if (!strip) return;
    if (_agentsAttachedFiles.length === 0) {
        strip.style.display = 'none';
        strip.innerHTML = '';
        return;
    }
    strip.style.display = 'flex';
    strip.innerHTML = '';
    _agentsAttachedFiles.forEach((file, idx) => {
        const chip = document.createElement('div');
        chip.className = 'agents-attach-chip';
        const thumb = file._previewUrl
            ? `<img src="${file._previewUrl}" class="agents-attach-thumb" alt="">`
            : `<i class="fas fa-file-alt agents-attach-file-icon"></i>`;
        chip.innerHTML = `
            ${thumb}
            <span class="agents-attach-chip-name">${_htmlEscape(file.filename)}</span>
            <button class="agents-attach-chip-remove" data-idx="${idx}" title="Remove">
                <i class="fas fa-times"></i>
            </button>`;
        chip.querySelector('.agents-attach-chip-remove').addEventListener('click', () => {
            if (file._previewUrl) URL.revokeObjectURL(file._previewUrl);
            _agentsAttachedFiles.splice(idx, 1);
            _agentsRenderAttachStrip();
        });
        strip.appendChild(chip);
    });
}

async function _agentsHandleFileSelect(files) {
    if (!files || files.length === 0) return;
    const attachBtn = _agEl('agents-attach-btn');
    if (attachBtn) {
        attachBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        attachBtn.disabled = true;
    }
    try {
        const wsId = _agentsCurrentWorkspace?.id;
        if (!wsId) {
            console.error('[Agents attach] No workspace selected');
            return;
        }
        for (const file of Array.from(files)) {
            const fd = new FormData();
            fd.append('file', file);
            const resp = await fetch(`/api/agents/upload?workspace_id=${encodeURIComponent(wsId)}`, { method: 'POST', body: fd });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                console.error('[Agents attach]', err.detail || `HTTP ${resp.status}`);
                continue;
            }
            const data = await resp.json();
            // Create local preview URL for images
            if (data.is_image) {
                data._previewUrl = URL.createObjectURL(file);
            }
            _agentsAttachedFiles.push(data);
        }
    } catch (e) {
        console.error('[Agents attach] Upload error:', e);
    } finally {
        if (attachBtn) {
            attachBtn.innerHTML = '<i class="fas fa-paperclip"></i>';
            attachBtn.disabled = !(_agentsCurrentWorkspace && _agentsCurrentThread && !_agentsIsPolling);
        }
    }
    _agentsRenderAttachStrip();
}

// ── Event wiring (called once after DOM is ready) ─────────────
function agentsInitEventHandlers() {
    // Workspace select change
    const wsSel = _agEl('agents-workspace-select');
    if (wsSel) wsSel.addEventListener('change', _agentsOnWorkspaceSelectChange);

    // Thread select change
    const tSel = _agEl('agents-thread-select');
    if (tSel) tSel.addEventListener('change', _agentsOnThreadSelectChange);

    // Model select change — persist selection
    const mSel = _agEl('agents-model-select');
    if (mSel) mSel.addEventListener('change', () => {
        localStorage.setItem('agents_model_id', mSel.value);
    });

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

    // Browse button → open native OS folder picker
    const browseBtn = _agEl('agents-browse-btn');
    if (browseBtn) browseBtn.addEventListener('click', _agentsNativeBrowse);

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

    // Attach button + hidden file input
    const attachBtn  = _agEl('agents-attach-btn');
    const fileInput  = _agEl('agents-file-input');
    if (attachBtn && fileInput) {
        attachBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', () => {
            _agentsHandleFileSelect(fileInput.files);
            fileInput.value = ''; // reset so same file can be re-added
        });
    }

    // Submit / Stop buttons
    const submitBtn = _agEl('agents-submit-btn');
    if (submitBtn) submitBtn.addEventListener('click', agentsSubmitTask);
    const stopBtn = _agEl('agents-stop-btn');
    if (stopBtn) stopBtn.addEventListener('click', agentsStopTask);

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
let _agentsEventsDone = false;

function _agentsBootstrapPanel() {
    if (_agentsEventsDone) return;
    const wsSelect = document.getElementById('agents-workspace-select');
    if (!wsSelect) return; // partial not loaded yet
    _agentsEventsDone = true;
    agentsInitEventHandlers();
    _agentsShowEmptyState('No workspace selected', 'Add or select a workspace to start working with agents');
    _agentsUpdateSubmitState();
}

(function agentsInit() {
    // Hook into the main tab switcher event dispatched by core.js switchMainTab
    document.addEventListener('tabChanged', (e) => {
        if (e.detail && e.detail.tab === 'agents') {
            onAgentsPanelActivated();
        }
    });

    // Wire event handlers once partial is injected, then load data
    document.addEventListener('panelLoaded', function (e) {
        if (e.detail.panelId === 'agents-panel') {
            _agentsBootstrapPanel();
            onAgentsPanelActivated();
        }
    });
})();
