// Agent Workspaces Mode — mode-agents.js
// Provides workspace + thread management and agent task submission
// with the same polling pattern as threads.js pollTaskStatus.

// Configure marked (same as mode-chat.js)
if (typeof marked !== 'undefined') {
    marked.setOptions({
        gfm: true,
        breaks: true,
        headerIds: false,
        mangle: false,
        sanitize: false
    });
}

// State
let _agentsWorkspaces = [];
let _agentsCurrentWorkspace = null;  // workspace object
let _agentsCurrentThread = null;     // thread metadata object (no messages)
let _agentsModelCosts = {};          // model_id → {input, output} per 1M tokens
let _agentsPollTimer = null;
let _agentsCurrentTaskId = null;
let _agentsIsPolling = false;
let _agentsAttachedFiles = [];       // [{filename, path, is_image, mime_type, content, size, _previewUrl}]
let _agentsCurrentReplayTimestamp = null;

// DOM helpers
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

// Workspace list
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

    // Reset file tree and editor on workspace change
    const rootEl = document.getElementById('agents-file-tree-root');
    if (rootEl) {
        if (ws) {
            _agLoadWorkspaceTree();
        } else {
            rootEl.innerHTML = '<div class="agents-tree-empty">Select workspace first</div>';
        }
    }
    
    _agCurrentOpenFile = null;
    _agOriginalFileContent = null;
    const viewerEmpty  = document.getElementById('agents-viewer-empty');
    const editorWrap   = document.getElementById('agents-code-editor-wrap');
    const mdPreview    = document.getElementById('agents-md-preview');
    const mdToggle     = document.getElementById('agents-md-toggle');
    const activeTitle  = document.getElementById('agents-active-file-title');
    const activePath   = document.getElementById('agents-active-file-path');
    const saveBtn      = document.getElementById('agents-file-save-btn');

    if (activeTitle) activeTitle.textContent = 'No file open';
    if (activePath) activePath.textContent = '';
    if (saveBtn) saveBtn.style.display = 'none';
    if (mdToggle) mdToggle.style.display = 'none';
    if (mdPreview) mdPreview.style.display = 'none';
    if (editorWrap) editorWrap.style.display = 'none';
    if (viewerEmpty) viewerEmpty.style.display = 'flex';
    
    // Clear search results
    const sInput = document.getElementById('agents-search-input');
    const sList = document.getElementById('agents-search-results-list');
    const sInfo = document.getElementById('agents-search-info');
    if (sInput) sInput.value = '';
    if (sList) sList.innerHTML = '';
    if (sInfo) sInfo.textContent = 'Enter search query above';

    _agentsUpdateSubmitState();
}

// Thread list
async function agentsLoadThreads(workspaceId) {
    try {
        const resp = await fetch(`/api/agents/workspaces/${workspaceId}/threads`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        let threads = data.threads || [];

        // Auto-create a default thread when the workspace has none yet
        let autoCreatedThread = null;
        if (threads.length === 0) {
            try {
                const createResp = await fetch(`/api/agents/workspaces/${workspaceId}/threads`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: 'Thread 1' }),
                });
                if (createResp.ok) {
                    autoCreatedThread = await createResp.json();
                    threads = [autoCreatedThread];
                }
            } catch (createErr) {
                console.warn('[Agents] Auto-create default thread failed:', createErr);
            }
        }

        _agentsPopulateThreadSelect(threads);

        // Auto-switch to the newly created thread so the workspace is immediately usable
        if (autoCreatedThread) {
            const sel = _agEl('agents-thread-select');
            if (sel) {
                sel.value = autoCreatedThread.id;
                await _agentsOnThreadSelectChange();
            }
        }
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

    // Check for interrupted checkpoint — show resume banner if found
    _agentsCheckCheckpoint(_agentsCurrentWorkspace.id, threadId);
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

// Thread token totals from history
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

// Message rendering
function _agentsRenderMessages(messages) {
    const container = _agEl('agents-messages');
    if (!container) return;

    // Reset the replay-dedup flag so switching threads can't carry stale state
    _agLastMsgWasAgentSteps = false;
    // Clear any dangling stream card from a previous run
    if (_agStreamCard) { _agStreamCard.remove(); _agStreamCard = null; }
    _agLiveTokenText = '';

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
        _agentsAppendMessage(msg, false, true); // scroll=false, isHistory=true
    }
    container.scrollTop = container.scrollHeight;
}

// Tracks whether the previous message was agent_steps — if so the `assistant`
// message that immediately follows is the same summary already shown in the
// done card, so we skip it to avoid a duplicate.
let _agLastMsgWasAgentSteps = false;

function _agentsAppendMessage(msg, scroll = true, isHistory = false) {
    const container = _agEl('agents-messages');
    if (!container) return;

    // Agent step history — replay through the dashboard renderer
    if (msg.role === 'agent_steps') {
        _agLastMsgWasAgentSteps = true;
        _agentsCurrentReplayTimestamp = msg.timestamp || null;
        for (const event of (msg.events || [])) {
            renderAgentStep(event, true); // isReplay = true
        }
        _agentsCurrentReplayTimestamp = null;
        if (scroll) container.scrollTop = container.scrollHeight;
        return;
    }

    // The `assistant` message stored after an agent run is already represented by
    // either: the agent_response (respond action) events replayed from agent_steps,
    // or the stream-static cards rebuilt from llm_token events. Skip it when either exists.
    if (msg.role === 'assistant' && _agLastMsgWasAgentSteps) {
        _agLastMsgWasAgentSteps = false;
        const rs = _agentsRenderState;
        const hasStream = rs && rs.activity
            ? rs.activity.querySelector('.agent-stream-static') !== null : false;
        if ((rs && rs.hadRespond) || hasStream) return;
        // Nothing visible yet → show the stored message as fallback
    }

    // Reset flag for any other role (user, error, etc.)
    if (msg.role !== 'assistant') _agLastMsgWasAgentSteps = false;

    const emptyState = container.querySelector('.agents-empty-state');
    if (emptyState) emptyState.remove();

    const role = msg.role || 'assistant';
    const wrapper = document.createElement('div');
    wrapper.className = `agents-message agents-message--${role}`;
    if (isHistory) wrapper.classList.add('instant-msg');

    if (role === 'user') {
        const bubble = document.createElement('div');
        bubble.className = 'agents-bubble';
        bubble.textContent = msg.content || '';
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
            bubble.appendChild(chips);
        }
        wrapper.appendChild(bubble);
    } else if (role === 'error') {
        const bubble = document.createElement('div');
        bubble.className = 'agents-bubble';
        bubble.textContent = msg.content || 'An error occurred.';
        wrapper.appendChild(bubble);
    } else {
        // Assistant message — chat bubble
        const bubble = document.createElement('div');
        bubble.className = 'agents-bubble';
        bubble.innerHTML = _agentsRenderMarkdown(msg.content || '');
        if (typeof hljs !== 'undefined') {
            bubble.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
        }
        wrapper.appendChild(bubble);

        const ts = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
        const modelStr = msg.model ? ` · ${msg.model}` : '';
        if (ts || modelStr) {
            const meta = document.createElement('div');
            meta.className = 'agents-bubble-meta';
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
    // Remove existing messages, runs, and typing indicators
    container.querySelectorAll('.agents-message, .agent-run, .agent-typing-indicator').forEach(el => el.remove());
    // Remove existing empty state
    container.querySelectorAll('.agents-empty-state').forEach(el => el.remove());
    const div = document.createElement('div');
    div.className = 'agents-empty-state';
    div.id = 'agents-empty-state';
    div.innerHTML = `
        <div class="agents-empty-title">${title}</div>
        <div class="agents-empty-sub">${sub}</div>
    `;
    container.appendChild(div);
}

// Typing indicator
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

// Submit state
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

// Auto-rename thread after first task
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

// Task submission & polling
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

    // Hide resume banner when user starts a fresh task
    const resumeBanner = _agEl('agents-resume-banner');
    if (resumeBanner) resumeBanner.style.display = 'none';
    _agentsCheckpointState = null;

    // Read optional token budget
    const budgetInput = _agEl('agents-budget-input');
    const budgetVal = budgetInput && budgetInput.value ? parseInt(budgetInput.value, 10) : null;
    const tokenBudget = (budgetVal && budgetVal >= 1000) ? budgetVal : null;

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
                token_budget: tokenBudget,
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
                            _agAutoRenameThread(_agentsCurrentWorkspace.id, _agentsCurrentThread.id, newName).then(() => {
                                agentsLoadThreads(_agentsCurrentWorkspace.id);
                            });
                        } else {
                            agentsLoadThreads(_agentsCurrentWorkspace.id);
                        }
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

// Agent step rendering
function _htmlEscape(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Per-run view state (reset on each new task start)
let _agentsRenderState = null;

// Thread-level thought counter — persists across tasks, resets on thread switch
let _agentsThoughtTotal = 0;

// Reset panels to empty state
function _agResetDashboard() {
    if (_agentsRenderState && _agentsRenderState.timerInterval) {
        clearInterval(_agentsRenderState.timerInterval);
    }
    _agentsRenderState = null;
    _agentsThoughtTotal = 0;

    // Left panel
    const leftEmpty   = _agEl('agents-dash-left-empty');
    const dashContent = _agEl('agents-dash-content');
    if (leftEmpty)   leftEmpty.style.display   = 'flex';
    if (dashContent) dashContent.style.display = 'none';

    // Right panel
    const rightEmpty   = _agEl('agents-dash-right-empty');
    const rightContent = _agEl('agents-dash-right-content');
    const actLog       = _agEl('agents-activity-log');
    const planSection  = _agEl('agents-plan-section');
    const planList     = _agEl('agents-plan-compact-list');
    if (rightEmpty)   rightEmpty.style.display   = 'flex';
    if (rightContent) rightContent.style.display = 'none';
    if (actLog)       actLog.innerHTML           = '';
    if (planSection)  planSection.style.display  = 'none';
    if (planList)     planList.innerHTML          = '';
}

// Bootstrap a new run
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
    // Left panel: show stats
    const leftEmpty    = _agEl('agents-dash-left-empty');
    const dashContent  = _agEl('agents-dash-content');
    const statsSection = _agEl('agents-stats-section');
    if (leftEmpty)    leftEmpty.style.display    = 'none';
    if (dashContent)  dashContent.style.display  = 'flex';
    if (statsSection) statsSection.style.display = 'block';

    // Right panel: plan starts hidden (shown on first set_plan), plan list cleared
    const planSection = _agEl('agents-plan-section');
    const planList    = _agEl('agents-plan-compact-list');
    if (planSection) planSection.style.display = 'none';
    if (planList)    planList.innerHTML         = '';

    // Right panel: show content area, add task separator if multiple tasks
    const rightEmpty   = _agEl('agents-dash-right-empty');
    const rightContent = _agEl('agents-dash-right-content');
    if (rightEmpty)   rightEmpty.style.display   = 'none';
    if (rightContent) rightContent.style.display = 'flex';

    const actLog = _agEl('agents-activity-log');
    if (actLog && actLog.children.length > 0 && !isReplay) {
        const sep = document.createElement('div');
        sep.style.cssText = 'height:1px;background:rgba(255,255,255,0.06);margin:0.35rem 0.5rem;';
        actLog.appendChild(sep);
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
        hadRespond: false, // true if agent used the respond action this run
        _planChatCard: null, // inline plan card shown in main chat
    };
    return _agentsRenderState;
}

// Timeline (vertical, renders into left panel)
// Activity Log (right panel)
// Adds a compact timestamped row. If `detail` is provided the row is
// expandable — click it to reveal the full thought text.
function _agActivityLogAdd(icon, label, variant = '', event = null, detail = null) {
    const actLog = _agEl('agents-activity-log');
    if (!actLog) return;

    let timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
    const rawTime = event && (event.timestamp || event.time);
    if (rawTime) {
        try {
            const d = new Date(rawTime);
            if (!isNaN(d.getTime()))
                timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
        } catch(e) {}
    }

    const wrap = document.createElement('div');

    const entry = document.createElement('div');
    entry.className = 'agent-alog-entry' + (variant ? ` agent-alog-entry--${variant}` : '')
                    + (detail ? ' agent-alog-entry--expandable' : '');

    const timeEl  = document.createElement('span');
    timeEl.className = 'agent-alog-time';
    timeEl.textContent = timeStr;

    const iconEl  = document.createElement('span');
    iconEl.className = 'agent-alog-icon';
    iconEl.textContent = icon;

    const labelEl = document.createElement('span');
    labelEl.className = 'agent-alog-label';
    labelEl.textContent = label;

    entry.appendChild(timeEl);
    entry.appendChild(iconEl);
    entry.appendChild(labelEl);

    if (detail) {
        const chev = document.createElement('span');
        chev.className = 'agent-alog-chevron';
        chev.textContent = '▾';
        entry.appendChild(chev);

        const detailEl = document.createElement('div');
        detailEl.className = 'agent-alog-detail';
        detailEl.innerHTML = _agentsRenderMarkdown(detail);

        let open = false;
        entry.addEventListener('click', () => {
            open = !open;
            detailEl.classList.toggle('agent-alog-detail--open', open);
            chev.textContent = open ? '▴' : '▾';
            if (open) actLog.scrollTop = actLog.scrollHeight;
        });

        wrap.appendChild(entry);
        wrap.appendChild(detailEl);
    } else {
        wrap.appendChild(entry);
    }

    actLog.appendChild(wrap);
    actLog.scrollTop = actLog.scrollHeight;
}

// Legacy shim — keep callers working without changes
function _agPhaseAdd(id, icon, label, event = null) {
    _agActivityLogAdd(icon, label, 'active', event);
}

function _agRenderTimeline() { /* no-op */ }

// Live LLM token streaming
let _agLiveTokenText = '';   // accumulated raw LLM output for the current iteration
let _agStreamCard    = null; // live streaming card in main chat (converts to static on finalize)

// State for the live command streaming card (run_command_line events)
let _agCmdStreamCard = null;
let _agCmdStreamLines = [];

/**
 * Called for every `llm_token` SSE event.
 * Streams the pre-ACTION text (the model's actual narrative/answer) live into the chat.
 * The backend emits all tokens including both the reasoning text and ACTION: JSON.
 * We show only the part before the first ACTION: line — that IS the answer for Q&A tasks.
 */
function _agHandleLLMToken(event) {
    _agLiveTokenText += event.token || '';

    // Show text before the first ACTION: line (the model's answer/narration)
    const actionIdx = _agLiveTokenText.indexOf('ACTION:');
    const display   = (actionIdx !== -1
        ? _agLiveTokenText.slice(0, actionIdx)
        : _agLiveTokenText
    ).trimStart().trimEnd();

    if (!display) return;

    const s = _agentsRenderState;
    if (!s) return;

    if (!_agStreamCard) {
        _agStreamCard = document.createElement('div');
        _agStreamCard.className = 'agent-stream-preview';
        const ti = s.activity.querySelector('.agent-typing-indicator');
        if (ti) s.activity.insertBefore(_agStreamCard, ti);
        else s.activity.appendChild(_agStreamCard);
    }
    _agStreamCard.textContent = display;

    const container = _agEl('agents-messages');
    if (container) container.scrollTop = container.scrollHeight;
}

/**
 * Finalize the streaming card: convert it to a stable static element.
 * Keep the text visible — it IS the agent's response for the current iteration.
 * Called between LLM iterations (before tool execution) and at task end.
 */
function _agFinalizeLiveToken() {
    if (_agStreamCard) {
        const text = _agStreamCard.textContent.trim();
        if (text) {
            _agStreamCard.classList.remove('agent-stream-preview');
            _agStreamCard.classList.add('agent-stream-static');
        } else {
            _agStreamCard.remove();
        }
        _agStreamCard = null;
    }
    _agLiveTokenText = '';
}

/**
 * Called for each `run_command_line` SSE event — streams shell output into
 * a compact card in the main activity area.
 */
function _agHandleCmdLine(event) {
    // Command streaming goes into the right panel activity log
    const actLog = _agEl('agents-activity-log');
    if (!actLog) return;

    if (!_agCmdStreamCard) {
        _agCmdStreamLines = [];
        _agCmdStreamCard = document.createElement('div');
        _agCmdStreamCard.className = 'agent-cmd-stream-inline';
        actLog.appendChild(_agCmdStreamCard);
    }

    const line = event.line || '';
    _agCmdStreamLines.push(line);
    _agCmdStreamCard.textContent = _agCmdStreamLines.slice(-30).join('\n');
    actLog.scrollTop = actLog.scrollHeight;
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

/** Append an activity item into the main chat, before the typing indicator. */
function _agActLogAppend(item) {
    const s = _agentsRenderState;
    if (s && s.activity) {
        const ti = s.activity.querySelector('.agent-typing-indicator');
        if (ti) s.activity.insertBefore(item, ti);
        else s.activity.appendChild(item);
    }
    const container = _agEl('agents-messages');
    if (container) container.scrollTop = container.scrollHeight;
}

function _agHandleThinking(event) {
    const s = _agentsRenderState;
    if (!s) return;
    _agFinalizeLiveToken(); // close streaming card before adding formatted thought

    const title  = event.title || 'Thinking';
    const opMatch = title.match(/\(([^)]+)\)/);
    const op = opMatch ? opMatch[1].trim() : '';

    // Update plan state (set_plan / mark_done)
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

    // Activity log — only add compact entries for plan operations.
    // General thinking content is already shown via the persistent streaming card,
    // so we skip adding a redundant second entry.
    if (op === 'set_plan') {
        const count = s.planItems.length;
        _agActivityLogAdd('📋', `Plan set · ${count} steps`, '', event);
    } else if (op === 'mark_done') {
        _agActivityLogAdd('✓', `Step done`, 'active', event);
    } else if (title.includes('blocked') || title.includes('failed')) {
        _agActivityLogAdd('⚠', title, 'fail', event);
    }
    // Other thinking events: the streaming card handles the content — no log entry needed.
}

function _agAddInlineThought(title, detail, s) {
    if (!s) s = _agentsRenderState;
    if (!s) return;

    const PREVIEW_LEN = 500;
    const truncated = detail.length > PREVIEW_LEN;
    const preview   = truncated ? detail.slice(0, PREVIEW_LEN) + '…' : detail;

    const card = document.createElement('div');
    card.className = 'agent-thought-inline';
    if (s.isReplay) card.classList.add('instant-msg');

    const hdr = document.createElement('div');
    hdr.className = 'agent-thought-inline-header';
    hdr.textContent = `🧠 ${title}`;
    card.appendChild(hdr);

    const body = document.createElement('div');
    body.className = 'agent-thought-inline-body';
    body.innerHTML = _agentsRenderMarkdown(preview);
    card.appendChild(body);

    if (truncated) {
        let expanded = false;
        const toggle = document.createElement('button');
        toggle.className = 'agent-thought-inline-toggle';
        toggle.textContent = '▾ Show more';
        toggle.addEventListener('click', () => {
            expanded = !expanded;
            body.innerHTML = _agentsRenderMarkdown(expanded ? detail : preview);
            toggle.textContent = expanded ? '▴ Show less' : '▾ Show more';
        });
        card.appendChild(toggle);
    }

    s.activity.appendChild(card);
    const container = _agEl('agents-messages');
    if (container) container.scrollTop = container.scrollHeight;

    // Legacy compat — was used to count thoughts
    _agentsThoughtTotal++;
}

// Legacy shim — now adds to the right panel activity log
function _agAddThoughtCard(title, detail) {
    _agActivityLogAdd('🧠', title, '', null, detail || null);
}

function _agRenderPlanItems() {
    const s = _agentsRenderState;
    if (!s) return;
    // Right panel (hidden) — kept for compat
    const planSection = _agEl('agents-plan-section');
    const planList    = _agEl('agents-plan-compact-list');
    const badge       = _agEl('agents-plan-badge');
    if (planSection) planSection.style.display = 'block';
    if (planList) {
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
    // Also render inline plan card in main chat
    _agRenderInlinePlan(s);
}

function _agRenderInlinePlan(s) {
    if (!s || !s.planItems.length) return;

    let card = s._planChatCard;
    if (!card) {
        card = document.createElement('div');
        card.className = 'agent-plan-inline';
        s._planChatCard = card;
        // Insert before typing indicator
        const ti = s.activity.querySelector('.agent-typing-indicator');
        if (ti) s.activity.insertBefore(card, ti);
        else s.activity.appendChild(card);
    }

    const doneCount  = s.planItems.filter(i => i.done).length;
    const totalCount = s.planItems.length;
    const allDone    = doneCount === totalCount;

    card.innerHTML = '';
    const hdr = document.createElement('div');
    hdr.className = 'agent-plan-inline-header';
    hdr.textContent = allDone
        ? `✓ ${totalCount} steps done`
        : `${doneCount}/${totalCount} steps`;
    card.appendChild(hdr);

    s.planItems.forEach(item => {
        const row = document.createElement('div');
        row.className = 'agent-plan-inline-row' + (item.done ? ' done' : '');
        row.textContent = (item.done ? '✓ ' : '○ ') + item.text;
        card.appendChild(row);
    });

    const container = _agEl('agents-messages');
    if (container) container.scrollTop = container.scrollHeight;
}

// Stats helpers
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

// Observation (image / context acknowledgement)
function _agHandleObserve(event) {
    const s = _agentsRenderState;
    if (!s) return;

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

// File activity rows
function _agFormatBytes(b) {
    if (b < 1024)        return `${b} B`;
    if (b < 1048576)     return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1048576).toFixed(1)} MB`;
}

// Delete file activity row
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
    _agActLogAppend(item);
}

function _agHandleWriteFile(event) {
    const s = _agentsRenderState;
    if (!s) return;
    s.fileCount++;
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
        // Inline diff view
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
        _agActLogAppend(item);
    }

    // Real-time update for currently open file in editor
    if (_agCurrentOpenFile === path) {
        _agOpenFile(path, filename);
    }
    // Refresh tree elements (to mark modification glows)
    const fileTreeRoot = document.getElementById('agents-file-tree-root');
    if (fileTreeRoot && fileTreeRoot.innerHTML !== '' && !fileTreeRoot.querySelector('.agents-tree-empty')) {
        _agLoadWorkspaceTree();
    }
}

// Command activity rows
function _agHandleCommand(event) {
    const s = _agentsRenderState;
    if (!s) return;

    const result  = event.result || '';
    const failed  = result.trimStart().startsWith('(exit ');

    // When a command fails, keep the live streaming card in the Thoughts panel as a
    // persistent error card so the output is never "silently removed".  For success,
    // discard the streaming card as usual (the activity row is sufficient).
    if (failed && _agCmdStreamCard) {
        _agCmdStreamCard.classList.remove('agent-thought-streaming');
        _agCmdStreamCard.classList.add('agent-thought-cmd-fail');
        const tag = _agCmdStreamCard.querySelector('.agent-thought-streaming-tag');
        if (tag) {
            tag.classList.remove('agent-thought-streaming-tag');
            tag.innerHTML = '<span style="color:#f87171;margin-right:4px;">✗</span>Command failed';
        }
        // Detach from the live-card tracker so _agFinalizeCmdStream won't remove it.
        _agCmdStreamCard = null;
        _agCmdStreamLines = [];
    } else {
        _agFinalizeCmdStream();  // close any streaming preview card in Thoughts
    }

    s.cmdCount++;
    if (failed) s.cmdFail++; else s.cmdSuccess++;
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
    _agActLogAppend(item);
}

// Read / list (compact dimmed, deduplicated)
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
    _agActLogAppend(item);
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
    _agActLogAppend(item);
}

// Web search
function _agHandleSearch(event) {
    const s = _agentsRenderState;
    if (!s) return;
    const query  = event.query || event.title || '';
    s.searchCount = (s.searchCount || 0) + 1;
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
    _agActLogAppend(item);
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

// URL fetch
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
    _agActLogAppend(item);
}

// Glob / move_file / create_directory
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
    _agActLogAppend(item);
}

function _agHandleMoveFile(event) {
    const s = _agentsRenderState;
    if (!s) return;
    s.fileCount++;
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
    _agActLogAppend(item);
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
    _agActLogAppend(item);
}

// Blueprint scan
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
    _agActLogAppend(item);
}

// Codebase search
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

    _agActLogAppend(item);
}

// Restore file (undo)

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
    _agActLogAppend(item);
}

// Completion
function _agFinishRender(event, isReplay = false) {
    const s = _agentsRenderState;
    if (!s) return;
    if (s.timerInterval) clearInterval(s.timerInterval);

    const isOk   = event.type === 'done';
    const detail = (event.detail || '').trim();

    // Update activity log with final entry
    _agActivityLogAdd(isOk ? '✅' : '❌', isOk ? 'Done' : 'Error', isOk ? 'done' : 'error', event);
    if (isOk) { s.planItems.forEach(i => { i.done = true; }); _agRenderPlanItems(); }

    // Remove the inner typing indicator
    const ti = s.activity.querySelector('.agent-typing-indicator');
    if (ti) ti.remove();

    // Command fail warning (inline in activity, not as a separate card)
    if (s.cmdFail > 0) {
        const warn = document.createElement('div');
        warn.className = 'agent-inline-warn agent-inline-warn--stall';
        warn.style.margin = '0.3rem 0';
        warn.innerHTML = `<span class="agent-inline-warn-icon">⚠</span><div class="agent-inline-warn-body"><strong>${s.cmdFail} command${s.cmdFail !== 1 ? 's' : ''} failed</strong>Scroll up to see the errors.</div>`;
        s.activity.appendChild(warn);
    }

    // Show done.detail as the final message when no other content is visible.
    // done.detail now contains the pre-action thinking text (the real answer) — backend fix.
    // Skip when: agent used respond (that IS the answer), or stream-static already shows it.
    if (!isReplay) {
        _agentsHideTyping();
        const hasStream = s.activity.querySelector('.agent-stream-static') !== null;
        if (!s.hadRespond && !hasStream) {
            const content = detail || (!isOk ? event.title || 'Task failed.' : '');
            if (content) {
                _agentsAppendMessage({
                    role:      isOk ? 'assistant' : 'error',
                    content:   content,
                    timestamp: new Date().toISOString(),
                }, true);
            }
        }
    }
}

// Main entry point (called for every SSE event)
function renderAgentStep(event, isReplay = false) {
    const container = _agEl('agents-messages');
    if (!container) return;
    const emptyState = _agEl('agents-empty-state');
    if (emptyState) emptyState.style.display = 'none';

    if (event.type === 'stream_end') return;

    if (event.type === 'start') {
        _agentsHideTyping();
        _agInitRender(isReplay);
        _agPhaseAdd('start', '🚀', 'Started', event);
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
        _agentsHideTyping();
        _agFinalizeLiveToken();  // finalize any open LLM streaming card (updates in place)
        _agFinalizeCmdStream();  // close any open command streaming card
        _agFinishRender(event, isReplay);
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
        case 'stall_warning':
            _agRenderInlineWarn('stall', '⚠️',
                event.title || 'Agent may be stuck',
                event.detail || `No plan progress in ${event.iterations_since_progress || '?'} steps.`
            );
            break;
        case 'budget_warning':
            _agRenderInlineWarn('budget-warn', '🟡',
                event.title || 'Approaching token budget',
                event.detail || ''
            );
            break;
        case 'budget_exceeded':
            _agRenderInlineWarn('budget-exceeded', '🛑',
                event.title || 'Token budget reached',
                event.detail || ''
            );
            // Treat as done — close stream cleanly
            _agentsIsPolling = false;
            _agentsCurrentTaskId = null;
            _agentsUpdateSubmitState();
            break;
        case 'project_memory_item':
            _pmHandleAgentSave(event);
            break;
        case 'patch_failed':
            _agHandlePatchFailed(event);
            break;
        case 'agent_response':
            if (_agentsRenderState) _agentsRenderState.hadRespond = true;
            _agHandleAgentResponse(event);
            break;
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

// Add Workspace modal
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

// Folder browser
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

// Thread actions
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

// Model selector
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

// File attachment helpers
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

// Event wiring (called once after DOM is ready)
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

    // Resume banner buttons
    const resumeBtn    = _agEl('agents-resume-btn');
    const dismissBtn   = _agEl('agents-resume-dismiss-btn');
    if (resumeBtn)  resumeBtn.addEventListener('click', _agentsResumeTask);
    if (dismissBtn) dismissBtn.addEventListener('click', () => {
        const banner = _agEl('agents-resume-banner');
        if (banner) banner.style.display = 'none';
        _agentsCheckpointState = null;
    });

    // Project memory panel buttons
    const pmAddBtn    = _agEl('agents-pm-add-btn');
    const pmSaveBtn   = _agEl('agents-pm-save-btn');
    const pmCancelBtn = _agEl('agents-pm-cancel-btn');
    if (pmAddBtn) pmAddBtn.addEventListener('click', () => {
        const form = _agEl('agents-pm-form');
        if (form) {
            form.dataset.editId = '';
            form.style.display = form.style.display === 'none' ? '' : 'none';
            const inp = _agEl('agents-pm-text-inp');
            if (inp && form.style.display !== 'none') inp.focus();
        }
    });
    if (pmSaveBtn)   pmSaveBtn.addEventListener('click', _pmSaveForm);
    if (pmCancelBtn) pmCancelBtn.addEventListener('click', () => {
        const form = _agEl('agents-pm-form');
        if (form) { form.style.display = 'none'; form.dataset.editId = ''; }
        const inp = _agEl('agents-pm-text-inp');
        if (inp) inp.value = '';
    });
    // Ctrl+Enter in textarea submits the form
    const pmTextInp = _agEl('agents-pm-text-inp');
    if (pmTextInp) pmTextInp.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && e.ctrlKey) { e.preventDefault(); _pmSaveForm(); }
    });

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

    // Workspace IDE tabs switching click listener
    const tabBtns = document.querySelectorAll('.agents-main-tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            const panels = document.querySelectorAll('.agents-tab-content-panel');
            panels.forEach(p => p.classList.remove('active'));
            
            const targetPanel = document.getElementById(`agents-${targetTab}-tab-panel`);
            if (targetPanel) targetPanel.classList.add('active');
            
            if (targetTab === 'files') {
                _agLoadWorkspaceTree();
            } else if (targetTab === 'memory') {
                _pmLoad();
            }
        });
    });

    // Refresh explorer tree button
    const treeRefreshBtn = document.getElementById('agents-tree-refresh-btn');
    if (treeRefreshBtn) {
        treeRefreshBtn.addEventListener('click', () => {
            _agLoadWorkspaceTree();
        });
    }

    // Save manual edits button
    const fileSaveBtn = document.getElementById('agents-file-save-btn');
    if (fileSaveBtn) {
        fileSaveBtn.addEventListener('click', _agSaveCurrentFile);
    }

    // Markdown preview toggle
    const mdToggleBtn = document.getElementById('agents-md-toggle');
    if (mdToggleBtn) {
        mdToggleBtn.addEventListener('click', _agToggleMarkdownPreview);
    }

    // Workspace search button
    const searchBtn = document.getElementById('agents-search-btn');
    if (searchBtn) {
        searchBtn.addEventListener('click', _agSearchWorkspace);
    }

    // Search enter key trigger
    const searchInput = document.getElementById('agents-search-input');
    if (searchInput) {
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                _agSearchWorkspace();
            }
        });
    }
}

// Project Memory

const _PM_CAT_META = {
    rule:      { icon: '🔴', label: 'Rule'      },
    context:   { icon: '🔵', label: 'Context'   },
    design:    { icon: '🟣', label: 'Design'    },
    note:      { icon: '🟡', label: 'Note'      },
    checklist: { icon: '📋', label: 'Checklist' },
};

async function _pmLoad() {
    const ws = _agentsCurrentWorkspace;
    if (!ws) return;
    try {
        const resp = await fetch(`/api/agents/workspaces/${ws.id}/memory`);
        if (!resp.ok) return;
        const { items } = await resp.json();
        _pmRender(items);
    } catch (e) { console.debug('[PM] load failed:', e); }
}

function _pmRender(items) {
    const panel   = _agEl('agents-project-memory');
    const empty   = _agEl('agents-pm-empty');
    const list    = _agEl('agents-pm-list');
    if (!panel || !list) return;

    panel.style.display = _agentsCurrentWorkspace ? '' : 'none';
    list.innerHTML = '';

    if (!items || items.length === 0) {
        if (empty) empty.style.display = '';
        return;
    }
    if (empty) empty.style.display = 'none';

    // Sort: rules first, then context, design, note, checklist
    const ORDER = ['rule', 'context', 'design', 'note', 'checklist'];
    items = [...items].sort((a, b) =>
        ORDER.indexOf(a.category) - ORDER.indexOf(b.category)
    );

    for (const item of items) {
        list.appendChild(_pmBuildItemEl(item));
    }
}

function _pmBuildItemEl(item) {
    const cat  = item.category || 'note';
    const meta = _PM_CAT_META[cat] || { icon: '📝', label: cat };

    const el = document.createElement('div');
    el.className = 'agents-pm-item';
    el.dataset.id  = item.id;
    el.dataset.cat = cat;

    const top = document.createElement('div');
    top.className = 'agents-pm-item-top';

    const badge = document.createElement('span');
    badge.className = `agents-pm-badge agents-pm-badge--${cat}`;
    badge.textContent = meta.label;

    const text = document.createElement('span');
    text.className = 'agents-pm-text';

    if (cat === 'checklist') {
        text.textContent = item.title || 'Checklist';
    } else {
        text.textContent = item.text || '';
    }

    const actions = document.createElement('div');
    actions.className = 'agents-pm-actions';

    const editBtn = document.createElement('button');
    editBtn.className = 'agents-pm-action-btn';
    editBtn.title = 'Edit';
    editBtn.textContent = '✏';
    editBtn.addEventListener('click', (e) => { e.stopPropagation(); _pmEditItem(item); });

    const delBtn = document.createElement('button');
    delBtn.className = 'agents-pm-action-btn agents-pm-action-btn--del';
    delBtn.title = 'Delete';
    delBtn.textContent = '×';
    delBtn.addEventListener('click', (e) => { e.stopPropagation(); _pmDeleteItem(item.id); });

    actions.appendChild(editBtn);
    actions.appendChild(delBtn);
    top.appendChild(badge);
    top.appendChild(text);
    top.appendChild(actions);
    el.appendChild(top);

    // Checklist rows
    if (cat === 'checklist' && Array.isArray(item.items)) {
        const cl = document.createElement('div');
        cl.className = 'agents-pm-checklist';
        for (const ci of item.items) {
            cl.appendChild(_pmBuildChecklistRow(item.id, ci));
        }
        el.appendChild(cl);
    }

    return el;
}

function _pmBuildChecklistRow(checklistId, ci) {
    const row = document.createElement('label');
    row.className = 'agents-pm-cl-row' + (ci.done ? ' agents-pm-cl-row--done' : '');
    row.dataset.ciId = ci.id;

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = !!ci.done;
    cb.addEventListener('change', async () => {
        const done = cb.checked;
        row.className = 'agents-pm-cl-row' + (done ? ' agents-pm-cl-row--done' : '');
        try {
            await fetch(`/api/agents/workspaces/${_agentsCurrentWorkspace.id}/memory/${checklistId}/items/${ci.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ done }),
            });
        } catch (e) { console.debug('[PM] checklist update failed:', e); }
    });

    const span = document.createElement('span');
    span.className = 'agents-pm-cl-text';
    span.textContent = ci.text;

    row.appendChild(cb);
    row.appendChild(span);
    return row;
}

async function _pmDeleteItem(itemId) {
    if (!_agentsCurrentWorkspace) return;
    try {
        await fetch(`/api/agents/workspaces/${_agentsCurrentWorkspace.id}/memory/${itemId}`, { method: 'DELETE' });
        _pmLoad();
    } catch (e) { console.debug('[PM] delete failed:', e); }
}

function _pmEditItem(item) {
    // Simple inline edit — repopulate form with existing values and update on save
    const form    = _agEl('agents-pm-form');
    const catSel  = _agEl('agents-pm-cat-sel');
    const textInp = _agEl('agents-pm-text-inp');
    if (!form || !catSel || !textInp) return;

    catSel.value  = item.category;
    textInp.value = item.category === 'checklist' ? (item.title || '') : (item.text || '');
    form.dataset.editId = item.id;
    form.style.display = '';
    textInp.focus();
}

async function _pmSaveForm() {
    const ws = _agentsCurrentWorkspace;
    if (!ws) return;
    const form    = _agEl('agents-pm-form');
    const catSel  = _agEl('agents-pm-cat-sel');
    const textInp = _agEl('agents-pm-text-inp');
    if (!form || !catSel || !textInp) return;

    const cat  = catSel.value;
    const text = textInp.value.trim();
    if (!text) return;

    const editId = form.dataset.editId;

    try {
        if (editId) {
            // Update existing
            const body = cat === 'checklist' ? { title: text } : { text, category: cat };
            await fetch(`/api/agents/workspaces/${ws.id}/memory/${editId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
        } else {
            // Add new
            const body = { category: cat, source: 'user' };
            if (cat === 'checklist') {
                body.title = text;
                body.items = [];   // empty checklist — user adds rows later
            } else {
                body.text = text;
            }
            await fetch(`/api/agents/workspaces/${ws.id}/memory`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
        }
    } catch (e) { console.debug('[PM] save failed:', e); }

    form.dataset.editId = '';
    form.style.display = 'none';
    textInp.value = '';
    _pmLoad();
}

function _pmHandleAgentSave(event) {
    // Called when SSE delivers a project_memory_item event from the agent.
    // Add a compact entry to the activity log.
    _agActivityLogAdd('💾', `Saved · [${event.label || event.category}] ${(event.text || '').slice(0, 40)}`);

    // If the Memory tab is currently active, refresh it to show the new item
    const memTab = _agEl('agents-memory-tab-panel');
    if (memTab && memTab.classList.contains('active')) {
        _pmLoad();
    }
}

// Checkpoint / Resume
let _agentsCheckpointState = null;  // last fetched state from /state endpoint

async function _agentsCheckCheckpoint(workspaceId, threadId) {
    const banner = _agEl('agents-resume-banner');
    if (banner) banner.style.display = 'none';
    _agentsCheckpointState = null;

    if (!workspaceId || !threadId) return;
    try {
        const resp = await fetch(`/api/agents/workspaces/${workspaceId}/threads/${threadId}/state`);
        if (!resp.ok) return;
        const state = await resp.json();
        if (!state.is_interrupted) return;

        _agentsCheckpointState = state;
        const done  = state.plan_done  || 0;
        const total = state.plan_total || 0;

        // Format when it was last saved
        let whenStr = '';
        if (state.last_saved) {
            const diff = Math.round((Date.now() - new Date(state.last_saved).getTime()) / 1000);
            if (diff < 60)       whenStr = `${diff}s ago`;
            else if (diff < 3600) whenStr = `${Math.round(diff/60)}m ago`;
            else                  whenStr = `${Math.round(diff/3600)}h ago`;
        }

        const titleEl = _agEl('agents-resume-title');
        const subEl   = _agEl('agents-resume-sub');
        if (titleEl) titleEl.textContent = `Task interrupted — ${done}/${total} steps done`;
        if (subEl) {
            const firstIncomplete = (state.plan || []).find(s => !s.done);
            subEl.textContent = (whenStr ? `${whenStr} · ` : '') +
                (firstIncomplete ? `Next: ${firstIncomplete.text}` : '');
        }
        if (banner) banner.style.display = 'flex';
    } catch (e) {
        console.debug('[Agents] checkpoint check failed:', e);
    }
}

async function _agentsResumeTask() {
    if (!_agentsCheckpointState || !_agentsCurrentWorkspace || !_agentsCurrentThread) return;
    const banner = _agEl('agents-resume-banner');
    if (banner) banner.style.display = 'none';

    // Reconstruct the original task from the plan steps for context
    const steps = (_agentsCheckpointState.plan || []).map(s => s.text).join(', ');
    const prompt = `Resume the previous task from where it was interrupted. Plan steps: ${steps}`;

    // Show as a user message in chat
    _agentsAppendMessage({ role: 'user', content: '⏩ Resuming from checkpoint…', timestamp: new Date().toISOString() });

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
                workspace_id: _agentsCurrentWorkspace.id,
                agent_thread_id: _agentsCurrentThread.id,
                resume: true,
            }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        _agentsCurrentTaskId = data.task_id;

        const evtSource = new EventSource(`/api/tasks/${data.task_id}/events`);
        _agentsPollTimer = evtSource;
        evtSource.onmessage = (e) => {
            try {
                const event = JSON.parse(e.data);
                if (event.type === 'stream_end') {
                    evtSource.close();
                    _agentsPollTimer = null;
                    _agentsIsPolling = false;
                    _agentsCurrentTaskId = null;
                    _agentsCheckpointState = null;
                    _agentsUpdateSubmitState();
                    return;
                }
                renderAgentStep(event);
            } catch (err) { console.error('[Agents] SSE parse error (resume):', err); }
        };
        evtSource.onerror = () => {
            evtSource.close();
            _agentsPollTimer = null;
            _agentsIsPolling = false;
            _agentsCurrentTaskId = null;
            _agentsUpdateSubmitState();
        };
    } catch (e) {
        _agentsHideTyping();
        _agentsIsPolling = false;
        _agentsUpdateSubmitState();
        _agentsAppendMessage({ role: 'error', content: `Failed to resume: ${e.message}`, timestamp: new Date().toISOString() });
    }
}

// Inline warning card (stall / budget)
function _agRenderInlineWarn(cls, icon, title, detail) {
    const container = _agEl('agents-messages');
    if (!container) return;
    const card = document.createElement('div');
    card.className = `agent-inline-warn agent-inline-warn--${cls}`;
    card.innerHTML = `<span class="agent-inline-warn-icon">${icon}</span>
        <div class="agent-inline-warn-body">
            <strong>${_htmlEscape(title)}</strong>
            ${_htmlEscape(detail)}
        </div>`;
    container.appendChild(card);
    container.scrollTop = container.scrollHeight;
}

// Patch failure card in main activity
function _agHandlePatchFailed(event) {
    const s = _agentsRenderState;
    if (!s) return;
    const path = event.path || '';

    const card = document.createElement('div');
    card.className = 'agent-patch-fail-card';
    card.innerHTML = `<span class="agent-patch-fail-icon">⚠</span>
        <div class="agent-patch-fail-body">
            <strong>Patch failed · ${_htmlEscape(path)}</strong>
            Content mismatch — agent re-reading file and retrying.
        </div>`;
    _agActLogAppend(card);
}

// Agent respond action — visible message in main chat
function _agHandleAgentResponse(event) {
    const content = event.content || '';
    if (!content) return;
    // The current stream card contains partial ACTION: JSON — replace it with the clean message
    if (_agStreamCard) { _agStreamCard.remove(); _agStreamCard = null; }
    _agentsHideTyping();
    _agentsAppendMessage({
        role:      'assistant',
        content,
        timestamp: new Date().toISOString(),
    }, true);
}

// Workspace IDE Tree & Editor Helpers
let _agCurrentOpenFile = null;

async function _agLoadWorkspaceTree() {
    const rootEl = document.getElementById('agents-file-tree-root');
    if (!rootEl) return;
    
    if (!_agentsCurrentWorkspace || !_agentsCurrentWorkspace.path) {
        rootEl.innerHTML = '<div class="agents-tree-empty">Select workspace first</div>';
        return;
    }
    
    const wsRoot = _agentsCurrentWorkspace.path;
    _agFetchAndRenderFolder(wsRoot, rootEl);
}

async function _agFetchAndRenderFolder(dirPath, container) {
    // If root container, show loading. If child folder, append spinner temporarily
    const isRoot = container.id === 'agents-file-tree-root';
    if (isRoot) {
        container.innerHTML = '<div class="agents-tree-loading"><i class="fas fa-spinner fa-spin"></i> Loading tree...</div>';
    }
    
    try {
        const resp = await fetch(`/api/agents/workspace/tree?path=${encodeURIComponent(dirPath)}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        
        container.innerHTML = '';
        if (!data.entries || data.entries.length === 0) {
            container.innerHTML = '<div class="agents-tree-empty-folder">Empty folder</div>';
            return;
        }
        
        data.entries.forEach(entry => {
            const node = document.createElement('div');
            node.className = `agents-tree-node ${entry.is_dir ? 'directory collapsed' : 'file'}`;
            node.setAttribute('data-path', entry.path);
            
            const isModified = _agentsRenderState && _agentsRenderState.fileCards && _agentsRenderState.fileCards[entry.path];
            const hasIndicator = isModified ? '<span class="agents-tree-file-indicator modified" title="Modified by Agent"></span>' : '';
            
            // Icon mapping
            let iconClass = entry.is_dir ? 'fas fa-folder' : 'far fa-file-code';
            if (!entry.is_dir) {
                if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(entry.ext)) iconClass = 'far fa-file-image';
                else if (['json', 'yaml', 'yml', 'toml'].includes(entry.ext)) iconClass = 'far fa-file-alt';
                else if (['md', 'txt'].includes(entry.ext)) iconClass = 'far fa-file-lines';
            }
            
            node.innerHTML = `
                <div class="agents-tree-row">
                    <i class="fas fa-chevron-right agents-tree-arrow" style="${entry.is_dir ? '' : 'visibility:hidden'}"></i>
                    <i class="${iconClass} agents-tree-icon"></i>
                    <span class="agents-tree-label">${_htmlEscape(entry.name)}</span>
                    ${hasIndicator}
                </div>
                ${entry.is_dir ? '<div class="agents-tree-children"></div>' : ''}
            `;
            
            const row = node.querySelector('.agents-tree-row');
            row.addEventListener('click', (e) => {
                e.stopPropagation();
                if (entry.is_dir) {
                    const children = node.querySelector('.agents-tree-children');
                    const arrow = node.querySelector('.agents-tree-arrow');
                    const folderIcon = node.querySelector('.agents-tree-icon');
                    
                    if (node.classList.contains('collapsed')) {
                        node.classList.remove('collapsed');
                        node.classList.add('expanded');
                        arrow.className = 'fas fa-chevron-down agents-tree-arrow';
                        folderIcon.className = 'fas fa-folder-open agents-tree-icon';
                        if (children.children.length === 0) {
                            _agFetchAndRenderFolder(entry.path, children);
                        }
                    } else {
                        node.classList.remove('expanded');
                        node.classList.add('collapsed');
                        arrow.className = 'fas fa-chevron-right agents-tree-arrow';
                        folderIcon.className = 'fas fa-folder agents-tree-icon';
                    }
                } else {
                    // File selection
                    document.querySelectorAll('.agents-tree-row').forEach(r => r.classList.remove('active'));
                    row.classList.add('active');
                    _agOpenFile(entry.path, entry.name);
                }
            });
            
            container.appendChild(node);
        });
    } catch (e) {
        console.error(e);
        container.innerHTML = `<div class="agents-tree-error">Failed to load: ${e.message || e}</div>`;
    }
}

function _agDetectLanguage(filePath) {
    const ext = filePath.split('.').pop().toLowerCase();
    const map = {
        'js': 'javascript',
        'jsx': 'javascript',
        'ts': 'typescript',
        'tsx': 'typescript',
        'py': 'python',
        'html': 'xml',
        'htm': 'xml',
        'css': 'css',
        'json': 'json',
        'md': 'markdown',
        'sh': 'bash',
        'bash': 'bash',
        'yml': 'yaml',
        'yaml': 'yaml',
        'sql': 'sql',
        'ini': 'ini',
        'toml': 'toml',
        'xml': 'xml',
    };
    return map[ext] || 'plaintext';
}

// Track whether the markdown preview is currently active
let _agMdPreviewActive = false;
// Track original file content to detect dirty state
let _agOriginalFileContent = null;

function _agToggleMarkdownPreview() {
    const mdPreview   = document.getElementById('agents-md-preview');
    const editorWrap  = document.getElementById('agents-code-editor-wrap');
    const mdToggleBtn = document.getElementById('agents-md-toggle');
    if (!mdPreview || !editorWrap) return;

    _agMdPreviewActive = !_agMdPreviewActive;

    if (_agMdPreviewActive) {
        // Render markdown from current textarea content
        const codeEditor = document.getElementById('agents-code-editor');
        const content = codeEditor ? codeEditor.value : '';
        mdPreview.innerHTML = (typeof marked !== 'undefined')
            ? marked.parse(content)
            : `<pre>${_htmlEscape(content)}</pre>`;
        // Apply hljs to code blocks inside markdown
        if (typeof hljs !== 'undefined') {
            mdPreview.querySelectorAll('pre code').forEach(b => {
                b.removeAttribute('data-highlighted');
                hljs.highlightElement(b);
            });
        }
        mdPreview.style.display = 'block';
        editorWrap.style.display = 'none';
        if (mdToggleBtn) {
            mdToggleBtn.textContent = 'Source';
            mdToggleBtn.classList.remove('active');
        }
    } else {
        mdPreview.style.display = 'none';
        editorWrap.style.display = 'flex';
        if (mdToggleBtn) {
            mdToggleBtn.textContent = 'Markdown';
            mdToggleBtn.classList.add('active');
        }
    }
}

async function _agOpenFile(filePath, filename) {
    // Preserve open state reference
    const oldFile = _agCurrentOpenFile;
    _agCurrentOpenFile = filePath;
    // Reset dirty tracking
    _agOriginalFileContent = null;
    _agMdPreviewActive = false;
    
    const viewerEmpty  = document.getElementById('agents-viewer-empty');
    const editorWrap   = document.getElementById('agents-code-editor-wrap');
    const mdPreview    = document.getElementById('agents-md-preview');
    const codeEditor   = document.getElementById('agents-code-editor');
    const codeBlock    = document.getElementById('agents-code-block');
    const activeTitle  = document.getElementById('agents-active-file-title');
    const activePath   = document.getElementById('agents-active-file-path');
    const saveBtn      = document.getElementById('agents-file-save-btn');
    const mdToggle     = document.getElementById('agents-md-toggle');
    const mdToggleBtn  = mdToggle; // same element — button IS the toggle
    
    if (!activeTitle) return;
    
    activeTitle.textContent = filename || filePath.split(/[\\/]/).pop() || filePath;
    if (activePath) activePath.textContent = filePath;
    
    // Hide everything while loading
    if (viewerEmpty) viewerEmpty.style.display = 'none';
    if (saveBtn) saveBtn.style.display = 'none';
    if (mdToggle) mdToggle.style.display = 'none';
    if (mdPreview) mdPreview.style.display = 'none';
    if (editorWrap) {
        editorWrap.style.display = 'flex';
        if (codeEditor) {
            codeEditor.value = 'Loading…';
            codeEditor.disabled = true;
        }
        if (codeBlock) codeBlock.textContent = 'Loading…';
    }
    
    try {
        const resp = await fetch(`/api/agents/workspace/file-content?path=${encodeURIComponent(filePath)}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        const content = data.content || '';
        
        // Determine if this is a markdown file
        const isMd = filePath.toLowerCase().endsWith('.md');
        const lang = _agDetectLanguage(filePath);
        
        // Populate the highlighted pre
        if (codeBlock) {
            codeBlock.textContent = content;
            codeBlock.className = '';
            codeBlock.classList.add(`language-${lang}`);
            if (typeof hljs !== 'undefined') {
                codeBlock.removeAttribute('data-highlighted');
                hljs.highlightElement(codeBlock);
            }
        }
        
        // Populate the textarea
        if (codeEditor) {
            codeEditor.value = content;
            codeEditor.disabled = !!(data.too_large || data.binary);
            // Sync scroll between textarea and highlight pre
            _agSyncEditorScroll();
        }
        
        // Store baseline for dirty detection
        _agOriginalFileContent = content;
        
        // Show MD toggle only for markdown files
        if (isMd && mdToggle) {
            mdToggle.style.display = 'inline-flex';
            // Reset MD toggle to "Preview" state (show editor by default)
            _agMdPreviewActive = false;
            if (mdToggleBtn) {
                mdToggleBtn.textContent = 'Markdown';
                mdToggleBtn.classList.add('active');
            }
        }
        
        // Show editor (not md preview)
        if (editorWrap) editorWrap.style.display = 'flex';
        if (mdPreview) mdPreview.style.display = 'none';
        
        // Bind input handler for dirty tracking + live highlight sync
        if (codeEditor && !codeEditor.disabled) {
            // Remove previous listeners by replacing with clone
            const fresh = codeEditor.cloneNode(true);
            codeEditor.parentNode.replaceChild(fresh, codeEditor);
            fresh.value = content;
            fresh.addEventListener('input', _agOnEditorInput);
            fresh.addEventListener('scroll', _agOnEditorScroll);
            fresh.addEventListener('keydown', _agEditorKeydown);
        }

    } catch (e) {
        console.error(e);
        if (editorWrap) editorWrap.style.display = 'flex';
        if (codeBlock) codeBlock.textContent = `Error loading file: ${e.message || e}`;
        const ed = document.getElementById('agents-code-editor');
        if (ed) {
            ed.value = `Error loading file: ${e.message || e}`;
            ed.disabled = true;
        }
    }
}

// Editor helpers

function _agOnEditorInput() {
    // Update highlight layer
    const codeEditor = document.getElementById('agents-code-editor');
    const codeBlock  = document.getElementById('agents-code-block');
    const saveBtn    = document.getElementById('agents-file-save-btn');
    if (!codeEditor || !codeBlock) return;

    const content = codeEditor.value;

    // Re-highlight
    codeBlock.textContent = content;
    if (typeof hljs !== 'undefined') {
        codeBlock.removeAttribute('data-highlighted');
        hljs.highlightElement(codeBlock);
    }

    // Smart save: only show when content has changed
    if (saveBtn) {
        const isDirty = content !== _agOriginalFileContent;
        saveBtn.style.display = isDirty ? 'inline-flex' : 'none';
    }
}

function _agOnEditorScroll() {
    _agSyncEditorScroll();
}

function _agSyncEditorScroll() {
    const codeEditor  = document.getElementById('agents-code-editor');
    const codePre     = document.getElementById('agents-code-pre');
    if (!codeEditor || !codePre) return;
    codePre.scrollTop  = codeEditor.scrollTop;
    codePre.scrollLeft = codeEditor.scrollLeft;
}

function _agEditorKeydown(e) {
    // Tab key inserts spaces instead of blurring
    if (e.key === 'Tab') {
        e.preventDefault();
        const ta = e.currentTarget;
        const start = ta.selectionStart;
        const end   = ta.selectionEnd;
        ta.value = ta.value.substring(0, start) + '    ' + ta.value.substring(end);
        ta.selectionStart = ta.selectionEnd = start + 4;
        // Trigger input event to sync highlight
        ta.dispatchEvent(new Event('input'));
    }
}

async function _agSaveCurrentFile() {
    if (!_agCurrentOpenFile) return;
    
    const codeEditor = document.getElementById('agents-code-editor');
    const saveBtn = document.getElementById('agents-file-save-btn');
    if (!codeEditor || codeEditor.disabled || !saveBtn) return;
    
    const originalHTML = saveBtn.innerHTML;
    saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
    saveBtn.disabled = true;
    
    try {
        const resp = await fetch('/api/agents/workspace/file-save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                path: _agCurrentOpenFile,
                content: codeEditor.value
            })
        });
        
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        
        // Update baseline — file is no longer dirty
        _agOriginalFileContent = codeEditor.value;
        
        saveBtn.innerHTML = '<i class="fas fa-check"></i> Saved!';
        saveBtn.style.borderColor = '#10b981';
        setTimeout(() => {
            saveBtn.style.display = 'none'; // hide because content matches baseline
            saveBtn.innerHTML = originalHTML;
            saveBtn.style.borderColor = '';
            saveBtn.disabled = false;
        }, 1200);
        
        // Update syntax-highlighted code block content
        const codeBlock = document.getElementById('agents-code-block');
        if (codeBlock) {
            codeBlock.textContent = codeEditor.value;
            if (typeof hljs !== 'undefined') {
                codeBlock.removeAttribute('data-highlighted');
                hljs.highlightElement(codeBlock);
            }
        }
        
        // Refresh explorer highlights
        _agLoadWorkspaceTree();
    } catch (e) {
        console.error(e);
        saveBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error';
        saveBtn.style.borderColor = '#ef4444';
        setTimeout(() => {
            saveBtn.innerHTML = originalHTML;
            saveBtn.style.borderColor = '';
            saveBtn.disabled = false;
        }, 3000);
    }
}

async function _agSearchWorkspace() {
    const input = document.getElementById('agents-search-input');
    const list = document.getElementById('agents-search-results-list');
    const info = document.getElementById('agents-search-info');
    
    if (!input || !list || !info) return;
    const query = input.value.trim();
    if (!query) {
        info.textContent = 'Please enter a search query';
        list.innerHTML = '';
        return;
    }
    
    if (query.length < 2) {
        info.textContent = 'Query must be at least 2 characters';
        list.innerHTML = '';
        return;
    }
    
    if (!_agentsCurrentWorkspace || !_agentsCurrentWorkspace.path) {
        info.textContent = 'Select workspace first';
        list.innerHTML = '';
        return;
    }
    
    info.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Searching codebase...';
    list.innerHTML = '';
    
    try {
        const wsPath = _agentsCurrentWorkspace.path;
        const resp = await fetch(`/api/agents/workspace/search?path=${encodeURIComponent(wsPath)}&query=${encodeURIComponent(query)}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        
        if (!data.results || data.results.length === 0) {
            info.textContent = `No matches found for "${query}"`;
            return;
        }
        
        info.textContent = `Found ${data.results.length} files matching "${query}":`;
        
        data.results.forEach(res => {
            const card = document.createElement('div');
            card.className = 'agent-search-result-card';
            
            let matchesHtml = '';
            res.matches.forEach(m => {
                matchesHtml += `
                    <div class="agent-search-match-line" data-line="${m.line_number}">
                        <span class="match-line-num">Line ${m.line_number}:</span>
                        <code class="match-line-content">${_htmlEscape(m.content)}</code>
                    </div>`;
            });
            
            card.innerHTML = `
                <div class="agent-search-result-header">
                    <span class="search-result-file"><i class="far fa-file-code"></i> ${res.rel_path}</span>
                </div>
                <div class="agent-search-result-matches">
                    ${matchesHtml}
                </div>
            `;
            
            card.querySelector('.agent-search-result-header').addEventListener('click', () => {
                const filesTabBtn = document.getElementById('agents-tab-files-btn');
                if (filesTabBtn) {
                    filesTabBtn.click();
                    _agOpenFile(res.path, res.filename);
                }
            });
            
            card.querySelectorAll('.agent-search-match-line').forEach(lineEl => {
                lineEl.addEventListener('click', () => {
                    const filesTabBtn = document.getElementById('agents-tab-files-btn');
                    if (filesTabBtn) {
                        filesTabBtn.click();
                        _agOpenFile(res.path, res.filename);
                    }
                });
            });
            
            list.appendChild(card);
        });
    } catch (e) {
        console.error(e);
        info.textContent = `Search failed: ${e.message || e}`;
    }
}

// Panel activation hook
// Called by the tab switcher when the Agents panel becomes active.
function onAgentsPanelActivated() {
    agentsLoadWorkspaces();
    agentsLoadModels();
}

// Init
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
