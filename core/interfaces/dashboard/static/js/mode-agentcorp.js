/* ═══════════════════════════════════════════════════════════════
   Agent Corp — frontend module
   Handles corp selection, worker dashboard, task board, live feed
═══════════════════════════════════════════════════════════════ */

// ── Global state ─────────────────────────────────────────────────────────────

let _corpList         = [];
let _corpCurrent      = null;   // full config object
let _corpModelsLoaded = false;  // models fetched once per session
let _corpTasks        = [];
let _corpWorkerStats  = {};     // worker_id → stats dict
let _corpSSE          = null;   // EventSource for live feed
let _corpIsRunning    = false;
let _corpIsStopping   = false;
let _corpFeedItems    = [];     // accumulated feed events (cap at 200)
const CORP_FEED_MAX   = 200;

// Worker color lookup (populated from config): worker_id → color hex
let _corpWorkerColors = {};
let _corpWorkerNames  = {};     // worker_id → name

// ── Initialisation ────────────────────────────────────────────────────────────

function onCorpPanelActivated() {
    corpLoadCorps();
    corpLoadModels();
}

async function corpLoadCorps() {
    try {
        const res = await fetch('/api/corp/list');
        _corpList = await res.json();
        corpPopulateSelect();
    } catch (e) {
        console.error('[AgentCorp] Failed to load corps:', e);
    }
}

function corpPopulateSelect() {
    const sel = document.getElementById('corp-select');
    if (!sel) return;

    const prev = sel.value || localStorage.getItem('corp_last_id');
    sel.innerHTML = '<option value="">— Select a Corp —</option>';
    for (const corp of _corpList) {
        const opt = document.createElement('option');
        opt.value = corp.id;
        opt.textContent = corp.name;
        sel.appendChild(opt);
    }

    // Restore selection
    if (prev && _corpList.some(c => c.id === prev)) {
        sel.value = prev;
        corpOnSelect(prev);
    } else if (_corpList.length === 1) {
        sel.value = _corpList[0].id;
        corpOnSelect(_corpList[0].id);
    } else {
        corpShowEmpty();
    }
}

async function corpOnSelect(corpId) {
    if (!corpId) { corpShowEmpty(); return; }
    localStorage.setItem('corp_last_id', corpId);

    try {
        _corpCurrent = await (await fetch(`/api/corp/${corpId}`)).json();
    } catch (e) {
        console.error('[AgentCorp] Failed to load corp:', e);
        return;
    }

    // Build colour/name lookup maps
    _corpWorkerColors = {};
    _corpWorkerNames  = {};
    for (const w of (_corpCurrent.workers || [])) {
        _corpWorkerColors[w.id] = w.color || '#7c3aed';
        _corpWorkerNames[w.id]  = w.name;
    }

    // Load tasks
    await corpRefreshTasks();

    // Load persisted worker stats from disk (populates cards before any SSE arrives)
    await corpRestoreStats(corpId);

    // Render workers panel (uses _corpWorkerStats populated above)
    corpRenderWorkers();

    // Show controls
    document.getElementById('corp-add-worker-btn').style.display = '';
    document.getElementById('corp-add-task-btn').style.display   = '';

    // Show workspace bar and populate it
    const wsBar = document.getElementById('corp-workspace-bar');
    const wsInput = document.getElementById('corp-workspace-input');
    if (wsBar) wsBar.style.display = 'flex';
    if (wsInput) wsInput.value = _corpCurrent.workspace_path || '';

    // Show goal bar and populate it
    const goalBar   = document.getElementById('corp-goal-bar');
    const goalInput = document.getElementById('corp-goal-input');
    if (goalBar) goalBar.style.display = 'flex';
    if (goalInput) goalInput.value = _corpCurrent.goal || '';

    // Show chat button when a corp is selected
    const chatBtn = document.getElementById('corp-chat-btn');
    if (chatBtn) chatBtn.style.display = '';

    // Determine running state
    _corpIsRunning = !!_corpCurrent.is_running;
    corpUpdateRunButtons();

    // Replay persisted feed events into the panel
    await corpRestoreFeed(corpId);

    // Subscribe to SSE for live updates going forward
    corpConnectSSE(corpId);
}

// ── Model loading ─────────────────────────────────────────────────────────────

async function corpLoadModels() {
    if (_corpModelsLoaded) return;
    try {
        const res = await fetch('/api/registry/models/chat');
        if (!res.ok) return;
        const data = await res.json();

        const sel = document.getElementById('corp-wmodal-model');
        if (!sel) return;

        // Use the same generateCategorizedModelOptions helper as other tabs
        if (typeof generateCategorizedModelOptions === 'function') {
            sel.innerHTML = generateCategorizedModelOptions(data, 'chat');
        } else {
            // Fallback: plain list
            sel.innerHTML = (data.models || []).map(m =>
                `<option value="${m.id}">${m.name || m.id}</option>`
            ).join('');
        }

        // Restore last-used worker model
        const saved = localStorage.getItem('corp_worker_model');
        if (saved) {
            const opt = sel.querySelector(`option[value="${CSS.escape(saved)}"]`);
            if (opt) sel.value = saved;
        }

        _corpModelsLoaded = true;
    } catch (e) {
        console.error('[AgentCorp] Failed to load models:', e);
    }
}

function corpShowEmpty() {
    document.getElementById('corp-workers-panel').innerHTML =
        '<div class="corp-empty-state"><i class="fas fa-users" style="font-size:2rem;opacity:.3"></i>' +
        '<div>No corp selected</div><div style="font-size:.72rem">Create or select a corp above</div></div>';
    document.getElementById('corp-taskboard').innerHTML =
        '<div class="corp-empty-state"><i class="fas fa-clipboard-list" style="font-size:2rem;opacity:.3"></i>' +
        '<div>No corp selected</div></div>';
    document.getElementById('corp-add-worker-btn').style.display = 'none';
    document.getElementById('corp-add-task-btn').style.display   = 'none';
    document.getElementById('corp-start-btn').style.display      = 'none';
    document.getElementById('corp-stop-btn').style.display       = 'none';
    const chatBtn = document.getElementById('corp-chat-btn');
    if (chatBtn) chatBtn.style.display = 'none';
    const chatPopup = document.getElementById('corp-chat-popup');
    if (chatPopup) chatPopup.style.display = 'none';
    const wsBar = document.getElementById('corp-workspace-bar');
    if (wsBar) wsBar.style.display = 'none';
    const goalBar = document.getElementById('corp-goal-bar');
    if (goalBar) goalBar.style.display = 'none';
}

// ── SSE ───────────────────────────────────────────────────────────────────────

function corpConnectSSE(corpId) {
    if (_corpSSE) { _corpSSE.close(); _corpSSE = null; }

    _corpSSE = new EventSource(`/api/corp/${corpId}/events`);

    _corpSSE.onmessage = (e) => {
        let data;
        try { data = JSON.parse(e.data); } catch { return; }

        switch (data.type) {
            case 'ping': break;

            case 'worker_thought':
                _corpUpdateWorkerThought(data.worker_id, data.thought);
                _corpAddFeedItem('thought', data);
                break;

            case 'worker_action':
                _corpAddFeedItem('action', data);
                break;

            case 'worker_message':
                _corpAddFeedItem('message', data);
                _corpAddChatMessage('worker', data.worker_name, data.content, data.color);
                break;

            case 'user_message':
                _corpAddFeedItem('message', {
                    worker_name: 'You',
                    color: '#3b82f6',
                    to: 'All',
                    content: data.content,
                });
                _corpAddChatMessage('user', 'You', data.content);
                break;

            case 'worker_stats':
                _corpWorkerStats[data.worker_id] = data.stats;
                _corpUpdateWorkerCard(data.worker_id, data.stats);
                break;

            case 'worker_status':
                _corpUpdateWorkerStatus(data.worker_id, data.status);
                break;

            case 'task_update':
                corpRefreshTasks();   // reload task board
                _corpAddFeedItem('task-update', data);
                break;

            case 'corp_status':
                _corpIsRunning = (data.status === 'running');
                _corpIsStopping = (data.status === 'stopping');
                corpUpdateRunButtons();
                _corpAddFeedItem('corp-event', {
                    worker_name: 'System',
                    color: '#6b7280',
                    thought: `Corp ${data.status}.`,
                });
                break;

            case 'stream_end':
                _corpSSE.close();
                _corpSSE = null;
                break;
        }
    };

    _corpSSE.onerror = () => {
        // Will auto-retry — EventSource behaviour
    };
}

// ── Restore persisted state on load ──────────────────────────────────────────

async function corpRestoreStats(corpId) {
    try {
        const data = await (await fetch(`/api/corp/${corpId}/stats`)).json();
        for (const [wid, stats] of Object.entries(data)) {
            _corpWorkerStats[wid] = stats;
        }
    } catch (e) {
        console.error('[AgentCorp] Failed to restore stats:', e);
    }
}

async function corpRestoreFeed(corpId) {
    try {
        const events = await (await fetch(`/api/corp/${corpId}/feed?last_n=200`)).json();
        if (!events || events.length === 0) return;

        // Clear current feed display (keep header)
        _corpFeedItems = [];
        const feed = document.getElementById('corp-feed');
        if (feed) {
            const items = feed.querySelectorAll('.corp-feed-item');
            items.forEach(i => i.remove());
        }

        // Replay events — map SSE types to feed types
        for (const ev of events) {
            const t = ev.type;
            if (t === 'worker_thought')  _corpAddFeedItem('thought',     ev);
            else if (t === 'worker_action')   _corpAddFeedItem('action',      ev);
            else if (t === 'worker_message') {
                _corpAddFeedItem('message', ev);
                _corpAddChatMessage('worker', ev.worker_name, ev.content, ev.color);
            }
            else if (t === 'task_update')     _corpAddFeedItem('task-update', ev);
            else if (t === 'corp_status')     _corpAddFeedItem('corp-event',  ev);
            else if (t === 'user_message')    _corpAddChatMessage('user', 'You', ev.content);
        }
    } catch (e) {
        console.error('[AgentCorp] Failed to restore feed:', e);
    }
}

// ── Worker panel rendering ────────────────────────────────────────────────────

function corpRenderWorkers() {
    const panel = document.getElementById('corp-workers-panel');
    if (!panel) return;
    panel.innerHTML = '';

    if (!_corpCurrent || !_corpCurrent.workers || _corpCurrent.workers.length === 0) {
        panel.innerHTML =
            '<div class="corp-empty-state"><i class="fas fa-user-plus" style="font-size:1.5rem;opacity:.3"></i>' +
            '<div>No workers yet</div><div style="font-size:.72rem">Add a worker to get started</div></div>';
        return;
    }

    // Header
    const hdr = document.createElement('div');
    hdr.className = 'corp-workers-header';
    hdr.innerHTML = `<span class="corp-workers-header-title">Workers (${_corpCurrent.workers.length})</span>`;
    panel.appendChild(hdr);

    for (const worker of _corpCurrent.workers) {
        panel.appendChild(_corpBuildWorkerCard(worker));
    }
}

function _corpBuildWorkerCard(worker) {
    const stats  = _corpWorkerStats[worker.id] || {};
    const status = stats.status || 'idle';
    const initials = worker.name.split(' ').map(p => p[0]).join('').toUpperCase().slice(0, 2);

    const card = document.createElement('div');
    card.className = `corp-worker-card ${status}`;
    card.id = `corp-worker-card-${worker.id}`;

    const autoLabel = worker.can_create_tasks
        ? `<span class="corp-worker-autoplan active" title="Auto-planning enabled — click to disable"
                onclick="corpToggleAutoplan('${worker.id}', false)">⚡ auto-plan</span>`
        : `<span class="corp-worker-autoplan" title="Auto-planning disabled — click to enable"
                onclick="corpToggleAutoplan('${worker.id}', true)">⚡ auto-plan</span>`;

    card.innerHTML = `
        <div class="corp-worker-header">
            <div class="corp-worker-avatar" style="background:${worker.color || '#7c3aed'}">${initials}</div>
            <div class="corp-worker-info">
                <div class="corp-worker-name">${_esc(worker.name)}</div>
                <div class="corp-worker-role">${_esc(worker.role)}</div>
            </div>
            <div style="display:flex;flex-direction:column;align-items:flex-end;gap:.25rem">
                <div style="display:flex;align-items:center;gap:4px">
                    <div class="corp-worker-badge ${status}" id="corp-badge-${worker.id}">${status}</div>
                    <button class="corp-worker-pause-btn" onclick="corpTogglePauseWorker('${_esc(worker.id)}')"
                        title="${worker.paused ? 'Resume worker' : 'Pause worker'}">
                        <i class="fas fa-${worker.paused ? 'play' : 'pause'}"></i>
                    </button>
                </div>
                ${autoLabel}
            </div>
        </div>
        <div class="corp-worker-thought" id="corp-thought-${worker.id}">${_esc(stats.current_thought || 'Waiting…')}</div>
        <div class="corp-worker-stats">
            <div class="corp-worker-stat">
                <span class="corp-worker-stat-label">Tokens</span>
                <span class="corp-worker-stat-value" id="corp-stat-tok-${worker.id}">${_fmtNum((stats.tokens_in||0)+(stats.tokens_out||0))}</span>
            </div>
            <div class="corp-worker-stat">
                <span class="corp-worker-stat-label">Cost</span>
                <span class="corp-worker-stat-value" id="corp-stat-cost-${worker.id}">$${(stats.cost_usd||0).toFixed(4)}</span>
            </div>
            <div class="corp-worker-stat">
                <span class="corp-worker-stat-label">Files</span>
                <span class="corp-worker-stat-value" id="corp-stat-files-${worker.id}">${(stats.files_created||0)+(stats.files_updated||0)}</span>
            </div>
            <div class="corp-worker-stat">
                <span class="corp-worker-stat-label">t/s</span>
                <span class="corp-worker-stat-value" id="corp-stat-tps-${worker.id}">${stats.tokens_per_second||0}</span>
            </div>
            <div class="corp-worker-stat">
                <span class="corp-worker-stat-label">Done</span>
                <span class="corp-worker-stat-value" id="corp-stat-done-${worker.id}">${stats.tasks_completed||0}</span>
            </div>
            <div class="corp-worker-stat">
                <span class="corp-worker-stat-label">Model</span>
                <span class="corp-worker-stat-value" style="font-size:.62rem">${_shortModel(worker.model)}</span>
            </div>
        </div>`;

    return card;
}

function _corpUpdateWorkerCard(workerId, stats) {
    const t  = el => document.getElementById(el);
    const set = (id, val) => { const e = t(id); if (e) e.textContent = val; };

    set(`corp-stat-tok-${workerId}`,  _fmtNum((stats.tokens_in||0)+(stats.tokens_out||0)));
    set(`corp-stat-cost-${workerId}`, `$${(stats.cost_usd||0).toFixed(4)}`);
    set(`corp-stat-files-${workerId}`,String((stats.files_created||0)+(stats.files_updated||0)));
    set(`corp-stat-tps-${workerId}`,  String(stats.tokens_per_second||0));
    set(`corp-stat-done-${workerId}`, String(stats.tasks_completed||0));

    _corpUpdateWorkerStatus(workerId, stats.status || 'idle');
    if (stats.current_thought) {
        _corpUpdateWorkerThought(workerId, stats.current_thought);
    }
}

function _corpUpdateWorkerThought(workerId, thought) {
    const el = document.getElementById(`corp-thought-${workerId}`);
    if (el) el.textContent = thought;
}

function _corpUpdateWorkerStatus(workerId, status) {
    const card  = document.getElementById(`corp-worker-card-${workerId}`);
    const badge = document.getElementById(`corp-badge-${workerId}`);
    if (card) {
        card.classList.remove('idle', 'running', 'stopped');
        card.classList.add(status);
    }
    if (badge) {
        badge.className = `corp-worker-badge ${status}`;
        badge.textContent = status;
    }
}

// ── Task board ────────────────────────────────────────────────────────────────

async function corpRefreshTasks() {
    if (!_corpCurrent) return;
    try {
        _corpTasks = await (await fetch(`/api/corp/${_corpCurrent.id}/tasks`)).json();
    } catch { return; }
    corpRenderTaskBoard();
}

function corpRenderTaskBoard() {
    const board = document.getElementById('corp-taskboard');
    if (!board) return;
    board.innerHTML = '';

    // Header row
    const hdr = document.createElement('div');
    hdr.className = 'corp-taskboard-header';
    hdr.innerHTML = `<span class="corp-taskboard-title">Task Board</span>`;
    board.appendChild(hdr);

    // Kanban columns
    const kanban = document.createElement('div');
    kanban.className = 'corp-kanban';

    const cols = [
        { key: 'pending',     label: 'Pending' },
        { key: 'in_progress', label: 'In Progress' },
        { key: 'done',        label: 'Done' },
    ];

    for (const col of cols) {
        const tasks = _corpTasks.filter(t => t.status === col.key ||
            (col.key === 'done' && t.status === 'failed'));
        kanban.appendChild(_corpBuildKanbanCol(col, tasks));
    }

    board.appendChild(kanban);
}

function _corpBuildKanbanCol(col, tasks) {
    const div = document.createElement('div');
    div.className = `corp-kanban-col ${col.key}`;

    div.innerHTML = `
        <div class="corp-kanban-col-header">
            <span class="corp-kanban-col-title">${col.label}</span>
            <span class="corp-kanban-col-count">${tasks.length}</span>
        </div>
        <div class="corp-kanban-cards" id="corp-col-${col.key}"></div>`;

    const cardsDiv = div.querySelector('.corp-kanban-cards');

    if (tasks.length === 0) {
        cardsDiv.innerHTML = '<div class="corp-kanban-empty">No tasks</div>';
    } else {
        for (const task of tasks) {
            cardsDiv.appendChild(_corpBuildTaskCard(task));
        }
    }

    return div;
}

function _corpBuildTaskCard(task) {
    const card = document.createElement('div');
    card.className = `corp-task-card ${task.status}`;

    // Find worker color
    let workerDot = '';
    const wid = task.worker_id;
    if (wid && _corpWorkerColors[wid]) {
        workerDot = `<span class="corp-task-worker-dot" style="background:${_corpWorkerColors[wid]}"></span>`;
    }

    const assignedName = _corpResolveAssigned(task.assigned_to);

    let resultHtml = '';
    if (task.result_summary) {
        resultHtml = `<div class="corp-task-result" title="${_esc(task.result_summary)}">${_esc(task.result_summary.slice(0,80))}…</div>`;
    }

    card.innerHTML = `
        <div class="corp-task-id">${_esc(task.task_id)}</div>
        <div class="corp-task-title">${_esc(task.title)}</div>
        <div class="corp-task-meta">
            <span class="corp-task-priority ${task.priority}">${task.priority}</span>
            <span class="corp-task-assigned">${workerDot}${_esc(assignedName)}</span>
        </div>
        ${resultHtml}`;

    if (task.status === 'pending' || task.status === 'in_progress') {
        const rejectBtn = document.createElement('button');
        rejectBtn.className = 'corp-task-reject-btn';
        rejectBtn.title = 'Reject this task';
        rejectBtn.innerHTML = '✕';
        rejectBtn.onclick = (e) => { e.stopPropagation(); corpRejectTask(task.task_id); };
        card.querySelector('.corp-task-id').after(rejectBtn);
    }

    // Show description tooltip on hover + open detail modal on click
    if (task.description) {
        card.title = task.description.length > 120
            ? task.description.slice(0, 120) + '…'
            : task.description;
    }
    card.style.cursor = 'pointer';
    card.addEventListener('click', () => corpOpenTaskDetail(task));

    return card;
}

function _corpResolveAssigned(assigned_to) {
    if (!assigned_to || assigned_to === 'any') return 'Any';
    // Check if it's a worker_id
    if (_corpWorkerNames[assigned_to]) return _corpWorkerNames[assigned_to];
    return assigned_to;
}

// ── Live feed ─────────────────────────────────────────────────────────────────

function _corpAddFeedItem(type, data) {
    const feed = document.getElementById('corp-feed');
    if (!feed) return;

    // Cap feed size
    _corpFeedItems.push({ type, data });
    if (_corpFeedItems.length > CORP_FEED_MAX) {
        _corpFeedItems.shift();
        const first = feed.querySelector('.corp-feed-item');
        if (first) first.remove();
    }

    const item = _corpBuildFeedItem(type, data);
    feed.appendChild(item);
    feed.scrollTop = feed.scrollHeight;
}

function _corpBuildFeedItem(type, data) {
    const div = document.createElement('div');
    div.className = `corp-feed-item ${type}`;

    const color    = data.color || '#7c3aed';
    const name     = data.worker_name || 'System';
    const initials = name.split(' ').map(p => p[0]).join('').toUpperCase().slice(0,2);

    let icon = '';
    let bodyHtml = '';

    if (type === 'thought') {
        icon = `<div class="corp-feed-avatar" style="background:${color}">${initials}</div>`;
        bodyHtml = `<div class="corp-feed-body">
            <div class="corp-feed-who" style="color:${color}">${_esc(name)}</div>
            <div class="corp-feed-text">${_esc(data.thought || '')}</div>
        </div>`;

    } else if (type === 'action') {
        const actionIcons = {
            write_file: '📄', read_file: '📖', delete_file: '🗑️',
            search_web: '🔍', fetch_url: '🌐', run_command: '⚡',
            list_dir:   '📁', post_to_log: '💬', create_task: '📋',
        };
        const aIcon = actionIcons[data.action] || '⚙️';
        icon = `<div class="corp-feed-avatar" style="background:${color}">${initials}</div>`;
        const pathOrQuery = data.path || '';
        bodyHtml = `<div class="corp-feed-body">
            <div class="corp-feed-who" style="color:${color}">${_esc(name)} ${aIcon} ${_esc(data.action || '')}</div>
            <div class="corp-feed-text">${_esc(pathOrQuery.slice(0,80))}${pathOrQuery.length>80?'…':''}</div>
        </div>`;

    } else if (type === 'message') {
        icon = `<div class="corp-feed-avatar" style="background:${color}">${initials}</div>`;
        bodyHtml = `<div class="corp-feed-body">
            <div class="corp-feed-who" style="color:${color}">${_esc(name)} → ${_esc(data.to || 'All')}</div>
            <div class="corp-feed-text">${_esc((data.content || '').slice(0,200))}</div>
        </div>`;

    } else if (type === 'task-update') {
        const statusIcons = { pending:'🕐', in_progress:'▶️', done:'✅', failed:'❌' };
        const sIcon = statusIcons[data.status] || '📋';
        icon = `<div class="corp-feed-icon">${sIcon}</div>`;
        bodyHtml = `<div class="corp-feed-body">
            <div class="corp-feed-who">${_esc(data.task_id || '')} — ${_esc(data.status || '')}</div>
            <div class="corp-feed-text">${_esc((data.title || '').slice(0,80))}</div>
        </div>`;

    } else {
        // corp-event / misc
        icon = `<div class="corp-feed-icon">🏢</div>`;
        bodyHtml = `<div class="corp-feed-body">
            <div class="corp-feed-text">${_esc(data.thought || data.content || JSON.stringify(data))}</div>
        </div>`;
    }

    div.innerHTML = icon + bodyHtml;
    return div;
}

// ── Corp start / stop ─────────────────────────────────────────────────────────

async function corpStartCorp() {
    if (!_corpCurrent) return;
    try {
        await fetch(`/api/corp/${_corpCurrent.id}/start`, { method: 'POST' });
        _corpIsRunning = true;
        corpUpdateRunButtons();
        _corpFeedClear();  // Clear display — history is preserved on disk
        // Don't wipe stats: workers load from disk and add to cumulative totals
        corpRenderWorkers();
    } catch (e) {
        console.error('[AgentCorp] Start failed:', e);
    }
}

async function corpStopCorp() {
    if (!_corpCurrent) return;
    try {
        await fetch(`/api/corp/${_corpCurrent.id}/stop`, { method: 'POST' });
        _corpIsRunning = false;
        corpUpdateRunButtons();
    } catch (e) {
        console.error('[AgentCorp] Stop failed:', e);
    }
}

function corpUpdateRunButtons() {
    const startBtn = document.getElementById('corp-start-btn');
    const stopBtn  = document.getElementById('corp-stop-btn');
    const dot      = document.getElementById('corp-status-dot');

    if (!_corpCurrent) {
        if (startBtn) startBtn.style.display = 'none';
        if (stopBtn)  stopBtn.style.display  = 'none';
        return;
    }
    if (startBtn) startBtn.style.display = (_corpIsRunning || _corpIsStopping) ? 'none' : '';
    if (stopBtn)  stopBtn.style.display  = (_corpIsRunning || _corpIsStopping) ? '' : 'none';
    if (stopBtn)  stopBtn.textContent    = _corpIsStopping ? 'Stopping…' : '■ Stop';
    if (dot) {
        dot.classList.toggle('running',  _corpIsRunning && !_corpIsStopping);
        dot.classList.toggle('stopping', _corpIsStopping);
    }
}

function _corpFeedClear() {
    _corpFeedItems = [];
    const feed = document.getElementById('corp-feed');
    if (!feed) return;
    // Keep the header, remove items
    const items = feed.querySelectorAll('.corp-feed-item');
    items.forEach(i => i.remove());
}

// ── Create corp modal ─────────────────────────────────────────────────────────

function corpShowCreateModal() {
    const m = document.getElementById('corp-create-modal');
    if (m) {
        document.getElementById('corp-modal-name').value = '';
        document.getElementById('corp-modal-desc').value = '';
        document.getElementById('corp-modal-goal').value = '';
        m.style.display = 'flex';
        setTimeout(() => document.getElementById('corp-modal-name').focus(), 50);
    }
}

async function corpSubmitCreate() {
    const name = (document.getElementById('corp-modal-name').value || '').trim();
    const desc = (document.getElementById('corp-modal-desc').value || '').trim();
    const goal = (document.getElementById('corp-modal-goal').value || '').trim();
    if (!name) { alert('Corp name is required.'); return; }

    try {
        const corp = await (await fetch('/api/corp/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description: desc, goal }),
        })).json();

        document.getElementById('corp-create-modal').style.display = 'none';
        await corpLoadCorps();
        const sel = document.getElementById('corp-select');
        if (sel) { sel.value = corp.id; corpOnSelect(corp.id); }
    } catch (e) {
        console.error('[AgentCorp] Create failed:', e);
    }
}

// ── Add worker modal ──────────────────────────────────────────────────────────

function corpShowAddWorkerModal() {
    if (!_corpCurrent) return;
    const m = document.getElementById('corp-worker-modal');
    if (!m) return;

    document.getElementById('corp-wmodal-name').value        = '';
    document.getElementById('corp-wmodal-role').value        = '';
    document.getElementById('corp-wmodal-personality').value = '';
    const canPlanChk = document.getElementById('corp-wmodal-can-plan');
    if (canPlanChk) canPlanChk.checked = false;
    document.getElementById('corp-wmodal-color').value       = _randomColor();

    // Ensure models are loaded, then restore last-used selection
    corpLoadModels().then(() => {
        const sel   = document.getElementById('corp-wmodal-model');
        const saved = localStorage.getItem('corp_worker_model');
        if (sel && saved) {
            const opt = sel.querySelector(`option[value="${CSS.escape(saved)}"]`);
            if (opt) sel.value = saved;
        }
    });

    m.style.display = 'flex';
    setTimeout(() => document.getElementById('corp-wmodal-name').focus(), 50);
}

async function corpSubmitAddWorker() {
    const name           = (document.getElementById('corp-wmodal-name').value || '').trim();
    const role           = (document.getElementById('corp-wmodal-role').value || '').trim();
    const model          = document.getElementById('corp-wmodal-model').value || 'claude-sonnet-4-5';
    const personality    = (document.getElementById('corp-wmodal-personality').value || '').trim();
    const color          = document.getElementById('corp-wmodal-color').value || '#7c3aed';
    const canPlanChk     = document.getElementById('corp-wmodal-can-plan');
    const can_create_tasks = canPlanChk ? canPlanChk.checked : false;

    if (!name || !role) { alert('Name and role are required.'); return; }

    // Remember last-used model
    if (model) localStorage.setItem('corp_worker_model', model);

    try {
        await fetch(`/api/corp/${_corpCurrent.id}/workers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, role, model, personality, color, can_create_tasks }),
        });
        document.getElementById('corp-worker-modal').style.display = 'none';
        // Refresh corp config and re-render
        _corpCurrent = await (await fetch(`/api/corp/${_corpCurrent.id}`)).json();
        for (const w of (_corpCurrent.workers || [])) {
            _corpWorkerColors[w.id] = w.color || '#7c3aed';
            _corpWorkerNames[w.id]  = w.name;
        }
        corpRenderWorkers();
    } catch (e) {
        console.error('[AgentCorp] Add worker failed:', e);
    }
}

// ── Add task modal ────────────────────────────────────────────────────────────

function corpShowAddTaskModal() {
    if (!_corpCurrent) return;
    const m = document.getElementById('corp-task-modal');
    if (!m) return;

    document.getElementById('corp-tmodal-title').value    = '';
    document.getElementById('corp-tmodal-desc').value     = '';
    document.getElementById('corp-tmodal-priority').value = 'medium';

    // Populate assigned-to dropdown
    const sel = document.getElementById('corp-tmodal-assign');
    sel.innerHTML = '<option value="any">Any worker</option>';
    for (const w of (_corpCurrent.workers || [])) {
        const opt = document.createElement('option');
        opt.value = w.name;
        opt.textContent = w.name;
        sel.appendChild(opt);
    }

    m.style.display = 'flex';
    setTimeout(() => document.getElementById('corp-tmodal-title').focus(), 50);
}

async function corpSubmitAddTask() {
    const title       = (document.getElementById('corp-tmodal-title').value || '').trim();
    const description = (document.getElementById('corp-tmodal-desc').value || '').trim();
    const assigned_to = document.getElementById('corp-tmodal-assign').value || 'any';
    const priority    = document.getElementById('corp-tmodal-priority').value || 'medium';

    if (!title || !description) { alert('Title and description are required.'); return; }

    try {
        await fetch(`/api/corp/${_corpCurrent.id}/tasks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, description, assigned_to, priority }),
        });
        document.getElementById('corp-task-modal').style.display = 'none';
        await corpRefreshTasks();
    } catch (e) {
        console.error('[AgentCorp] Add task failed:', e);
    }
}

// ── Workspace ─────────────────────────────────────────────────────────────────

async function corpBrowseWorkspace() {
    const browseBtn = document.getElementById('corp-workspace-browse-btn');
    const input     = document.getElementById('corp-workspace-input');
    if (!browseBtn || !input) return;

    const prev = browseBtn.innerHTML;
    browseBtn.disabled = true;
    browseBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

    try {
        const currentPath = input.value.trim();
        const url = '/api/agents/browse/native' +
            (currentPath ? `?initial=${encodeURIComponent(currentPath)}` : '');
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        if (!data.cancelled && data.path) {
            input.value = data.path;
        }
    } catch (e) {
        console.error('[AgentCorp] Browse error:', e);
        if (typeof showToast === 'function') showToast('Could not open folder picker', 'error');
    } finally {
        browseBtn.disabled = false;
        browseBtn.innerHTML = prev;
    }
}

async function corpToggleAutoplan(workerId, enable) {
    if (!_corpCurrent) return;
    try {
        await fetch(`/api/corp/${_corpCurrent.id}/workers/${workerId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ can_create_tasks: enable }),
        });
        // Update local config and re-render the worker card
        for (const w of (_corpCurrent.workers || [])) {
            if (w.id === workerId) { w.can_create_tasks = enable; break; }
        }
        const card = document.getElementById(`corp-worker-card-${workerId}`);
        if (card) {
            // Find the worker and rebuild just the card
            const worker = (_corpCurrent.workers || []).find(w => w.id === workerId);
            if (worker) {
                const newCard = _corpBuildWorkerCard(worker);
                card.replaceWith(newCard);
            }
        }
        if (typeof showToast === 'function') {
            showToast(enable ? 'Auto-planning enabled' : 'Auto-planning disabled', 'success');
        }
    } catch (e) {
        console.error('[AgentCorp] Toggle auto-plan failed:', e);
    }
}

async function corpSaveGoal() {
    if (!_corpCurrent) return;
    const input = document.getElementById('corp-goal-input');
    const goal  = (input ? input.value : '').trim();

    try {
        const updated = await (await fetch(`/api/corp/${_corpCurrent.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ goal }),
        })).json();

        _corpCurrent.goal = updated.goal ?? goal;

        if (typeof showToast === 'function') {
            showToast(goal ? 'Company goal saved' : 'Goal cleared', 'success');
        }
    } catch (e) {
        console.error('[AgentCorp] Save goal failed:', e);
        if (typeof showToast === 'function') showToast('Failed to save goal', 'error');
    }
}

async function corpSaveWorkspacePath() {
    if (!_corpCurrent) return;
    const input = document.getElementById('corp-workspace-input');
    const path  = (input ? input.value : '').trim();

    try {
        const updated = await (await fetch(`/api/corp/${_corpCurrent.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: path }),
        })).json();

        _corpCurrent.workspace_path = updated.workspace_path || path;

        if (typeof showToast === 'function') {
            showToast(path ? `Workspace set to: ${path}` : 'Using default corp folder', 'success');
        }
    } catch (e) {
        console.error('[AgentCorp] Save workspace failed:', e);
        if (typeof showToast === 'function') showToast('Failed to save workspace path', 'error');
    }
}

// ── Event handler wiring ──────────────────────────────────────────────────────

// ── Agent Corp panel init (deferred until partial is injected) ────────────────
let _corpInitDone = false;

function _initCorpPanel() {
    const sel = document.getElementById('corp-select');
    if (!sel || _corpInitDone) return;
    _corpInitDone = true;

    sel.addEventListener('change', () => corpOnSelect(sel.value));

    const createBtn    = document.getElementById('corp-create-btn');
    const addWorkerBtn = document.getElementById('corp-add-worker-btn');
    const addTaskBtn   = document.getElementById('corp-add-task-btn');
    const startBtn     = document.getElementById('corp-start-btn');
    const stopBtn      = document.getElementById('corp-stop-btn');

    if (createBtn)    createBtn.addEventListener('click', corpShowCreateModal);
    if (addWorkerBtn) addWorkerBtn.addEventListener('click', corpShowAddWorkerModal);
    if (addTaskBtn)   addTaskBtn.addEventListener('click', corpShowAddTaskModal);
    if (startBtn)     startBtn.addEventListener('click', corpStartCorp);
    if (stopBtn)      stopBtn.addEventListener('click', corpStopCorp);

    const chatBtn2 = document.getElementById('corp-chat-btn');
    if (chatBtn2) chatBtn2.addEventListener('click', corpToggleChat);

    const createSubmit = document.getElementById('corp-create-submit');
    if (createSubmit) createSubmit.addEventListener('click', corpSubmitCreate);
    const createCancel = document.getElementById('corp-create-cancel');
    if (createCancel) createCancel.addEventListener('click', () => {
        document.getElementById('corp-create-modal').style.display = 'none';
    });

    const workerSubmit = document.getElementById('corp-worker-submit');
    if (workerSubmit) workerSubmit.addEventListener('click', corpSubmitAddWorker);
    const workerCancel = document.getElementById('corp-worker-cancel');
    if (workerCancel) workerCancel.addEventListener('click', () => {
        document.getElementById('corp-worker-modal').style.display = 'none';
    });

    const taskSubmit = document.getElementById('corp-task-submit');
    if (taskSubmit) taskSubmit.addEventListener('click', corpSubmitAddTask);
    const taskCancel = document.getElementById('corp-task-cancel');
    if (taskCancel) taskCancel.addEventListener('click', () => {
        document.getElementById('corp-task-modal').style.display = 'none';
    });

    const wsBrowse = document.getElementById('corp-workspace-browse-btn');
    const wsSave   = document.getElementById('corp-workspace-save-btn');
    const wsInput  = document.getElementById('corp-workspace-input');
    if (wsBrowse) wsBrowse.addEventListener('click', corpBrowseWorkspace);
    if (wsSave)   wsSave.addEventListener('click', corpSaveWorkspacePath);
    if (wsInput)  wsInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') corpSaveWorkspacePath();
    });

    const goalSave  = document.getElementById('corp-goal-save-btn');
    const goalInput = document.getElementById('corp-goal-input');
    if (goalSave)  goalSave.addEventListener('click', corpSaveGoal);
    if (goalInput) goalInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') corpSaveGoal();
    });

    ['corp-create-modal', 'corp-worker-modal', 'corp-task-modal'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('click', (e) => {
            if (e.target === el) el.style.display = 'none';
        });
    });

    ['corp-modal-name', 'corp-wmodal-name'].forEach(id => {
        const inp = document.getElementById(id);
        if (inp) inp.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                if (id === 'corp-modal-name') corpSubmitCreate();
                else corpSubmitAddWorker();
            }
        });
    });

}

document.addEventListener('DOMContentLoaded', _initCorpPanel);

document.addEventListener('panelLoaded', function (e) {
    if (e.detail.panelId === 'agent-corp-panel') {
        _corpInitDone = false;
        _initCorpPanel();
    }
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function _esc(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function _fmtNum(n) {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1000)      return (n / 1000).toFixed(1) + 'K';
    return String(n);
}

function _shortModel(model) {
    if (!model) return '—';
    if (model.includes('opus'))   return 'Opus';
    if (model.includes('sonnet')) return 'Sonnet';
    if (model.includes('haiku'))  return 'Haiku';
    return model.split('-').slice(-1)[0] || model;
}

function _randomColor() {
    const palette = [
        '#7c3aed', '#2563eb', '#059669', '#d97706',
        '#dc2626', '#db2777', '#0891b2', '#65a30d',
    ];
    return palette[Math.floor(Math.random() * palette.length)];
}

// ── Worker pause/resume ────────────────────────────────────────────────────────

async function corpTogglePauseWorker(workerId) {
    if (!_corpCurrent) return;
    const worker = (_corpCurrent.workers || []).find(w => w.id === workerId);
    if (!worker) return;
    const action = worker.paused ? 'resume' : 'pause';
    try {
        await fetch(`/api/corp/${_corpCurrent.id}/workers/${workerId}/${action}`, { method: 'POST' });
        // Optimistically update local state and re-render card
        worker.paused = !worker.paused;
        const card = document.getElementById(`corp-worker-card-${workerId}`);
        if (card) {
            const newCard = _corpBuildWorkerCard(worker);
            card.replaceWith(newCard);
        }
    } catch (e) {
        console.error('[AgentCorp] Pause/resume failed:', e);
    }
}

// ── Task reject ────────────────────────────────────────────────────────────────

function corpOpenTaskDetail(task) {
    const modal = document.getElementById('corp-task-detail-modal');
    if (!modal) return;

    document.getElementById('corp-detail-title').textContent = task.title;

    const statusEl = document.getElementById('corp-detail-status');
    statusEl.textContent = task.status.replace('_', ' ');
    statusEl.className = `corp-detail-status-badge ${task.status}`;

    const assignedName = _corpResolveAssigned(task.assigned_to);
    const createdAt = task.created_at ? new Date(task.created_at).toLocaleString() : '—';
    const workerName = task.worker_id ? (_corpWorkerNames[task.worker_id] || task.worker_id) : '—';
    document.getElementById('corp-detail-meta').innerHTML =
        `<span class="corp-detail-meta-item"><b>Priority:</b> <span class="corp-task-priority ${task.priority}">${task.priority}</span></span>` +
        `<span class="corp-detail-meta-item"><b>Assigned to:</b> ${_esc(assignedName)}</span>` +
        `<span class="corp-detail-meta-item"><b>Created:</b> ${_esc(createdAt)}</span>` +
        (task.worker_id ? `<span class="corp-detail-meta-item"><b>Worker:</b> ${_esc(workerName)}</span>` : '');

    document.getElementById('corp-detail-description').textContent = task.description || '(no description)';

    const resultWrap = document.getElementById('corp-detail-result-wrap');
    if (task.result_summary) {
        document.getElementById('corp-detail-result').textContent = task.result_summary;
        resultWrap.style.display = '';
    } else {
        resultWrap.style.display = 'none';
    }

    modal.style.display = 'flex';
}

function corpCloseTaskDetail() {
    const modal = document.getElementById('corp-task-detail-modal');
    if (modal) modal.style.display = 'none';
}

async function corpRejectTask(taskId) {
    if (!_corpCurrent) return;
    if (!confirm(`Reject task ${taskId}? This cannot be undone.`)) return;
    try {
        await fetch(`/api/corp/${_corpCurrent.id}/tasks/${taskId}/reject`, { method: 'POST' });
        await corpRefreshTasks();
    } catch (e) {
        console.error('[AgentCorp] Reject task failed:', e);
    }
}

// ── Company chat ───────────────────────────────────────────────────────────────

function corpToggleChat() {
    const popup = document.getElementById('corp-chat-popup');
    if (!popup) return;
    popup.style.display = popup.style.display === 'none' ? 'flex' : 'none';
}

async function corpSendChatMessage() {
    if (!_corpCurrent) return;
    const input = document.getElementById('corp-chat-input');
    const msg   = (input ? input.value : '').trim();
    if (!msg) return;
    try {
        await fetch(`/api/corp/${_corpCurrent.id}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg }),
        });
        if (input) input.value = '';
    } catch (e) {
        console.error('[AgentCorp] Send message failed:', e);
    }
}

function _corpAddChatMessage(side, name, content, color) {
    const container = document.getElementById('corp-chat-messages');
    if (!container) return;
    // Remove empty state placeholder
    const empty = container.querySelector('.corp-chat-empty');
    if (empty) empty.remove();

    const div = document.createElement('div');
    div.className = `corp-chat-msg ${side}`;

    if (side === 'worker' && name) {
        const who = document.createElement('div');
        who.className = 'corp-chat-msg-who';
        who.style.color = color || '#7c3aed';
        who.textContent = name;
        div.appendChild(who);
    }
    const text = document.createElement('div');
    text.textContent = content || '';
    div.appendChild(text);

    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}
