// Schedule Mode — mode-schedule.js
// Recurring AI task setup via conversational AI + cron scheduler.
// Separate from chat: own API, own data store (data/scheduled_tasks/).

if (typeof marked !== 'undefined') {
    marked.setOptions({ gfm: true, breaks: true, headerIds: false, mangle: false, sanitize: false });
}

// ── State ─────────────────────────────────────────────────────
let _schedTasks        = [];          // list metadata (no thread/runs)
let _schedCurrentId    = null;        // selected task id
let _schedCurrentTask  = null;        // full task object (metadata only, thread loaded separately)
let _schedIsSending    = false;
let _schedModels       = {};          // model_id → cost info

// ── DOM helpers ───────────────────────────────────────────────
const _sEl  = (id) => document.getElementById(id);
const _sQ   = (sel, parent = document) => parent.querySelector(sel);

function _schedMd(text) {
    if (!text) return '';
    if (typeof marked !== 'undefined') {
        try { return marked.parse(text); } catch (_) {}
    }
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
               .replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\n/g, '<br>');
}

function _schedGetDisplayTz() {
    return localStorage.getItem('display_timezone') || 'UTC';
}

function _schedFmtTime(iso, opts = {}) {
    // opts.future: if true, render as "in Xm" style; if false, "Xm ago" style.
    // opts.absolute: always render absolute datetime.
    if (!iso) return '';
    try {
        // Ensure the string is treated as UTC. Strings ending in 'Z' are fine;
        // strings without timezone info get 'Z' appended so JS parses as UTC.
        const normalized = /[Zz]$|[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + 'Z';
        const d = new Date(normalized);
        if (isNaN(d.getTime())) return iso;

        const now = new Date();
        const diffMs = d - now;           // positive = future, negative = past
        const absDiffMs = Math.abs(diffMs);
        const tz = _schedGetDisplayTz();

        // Relative label for very recent / near-future
        if (absDiffMs < 60000) return 'just now';
        if (absDiffMs < 3600000) {
            const mins = Math.round(absDiffMs / 60000);
            return diffMs > 0 ? `in ${mins}m` : `${mins}m ago`;
        }
        if (absDiffMs < 86400000) {
            const hrs = Math.round(absDiffMs / 3600000);
            return diffMs > 0 ? `in ${hrs}h` : `${hrs}h ago`;
        }

        // Absolute display in the user's chosen timezone
        const fmt = new Intl.DateTimeFormat(undefined, {
            timeZone: tz,
            month: 'short', day: 'numeric',
            hour: '2-digit', minute: '2-digit',
        });
        const label = fmt.format(d);
        if (absDiffMs < 7 * 86400000) {
            // Also show weekday for near dates
            const dayFmt = new Intl.DateTimeFormat(undefined, { timeZone: tz, weekday: 'short' });
            return `${dayFmt.format(d)}, ${label}`;
        }
        return label;
    } catch (_) { return iso; }
}

// ── Load task list ────────────────────────────────────────────
async function scheduleLoadTasks() {
    try {
        const resp = await fetch('/api/schedule/tasks');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        _schedTasks = data.tasks || [];
        _schedRenderTaskList();
    } catch (e) {
        console.error('[Schedule] Failed to load tasks:', e);
    }
}

function _schedRenderTaskList() {
    const list  = _sEl('sched-task-list');
    const empty = _sEl('sched-empty-list');
    if (!list) return;

    // Remove old task items (keep the empty-list element)
    Array.from(list.children).forEach(el => {
        if (el.id !== 'sched-empty-list') el.remove();
    });

    if (_schedTasks.length === 0) {
        if (empty) empty.style.display = '';
        return;
    }
    if (empty) empty.style.display = 'none';

    _schedTasks.forEach(task => {
        const item = document.createElement('div');
        item.className = 'sched-task-item' + (task.id === _schedCurrentId ? ' active' : '');
        item.dataset.taskId = task.id;

        const dotClass = { active: 'dot-active', paused: 'dot-paused', draft: 'dot-draft' }[task.status] || 'dot-draft';
        const schedLine = task.cron_human || (task.cron ? task.cron : 'Not scheduled');
        const lastRun   = task.last_run_at ? `Last: ${_schedFmtTime(task.last_run_at)}` : '';

        item.innerHTML = `
            <div class="sched-task-item-inner">
                <span class="sched-task-dot ${dotClass}"></span>
                <div class="sched-task-item-text">
                    <span class="sched-task-item-name">${_escHtml(task.name || 'Untitled')}</span>
                    <span class="sched-task-item-meta">${_escHtml(schedLine)}</span>
                    ${lastRun ? `<span class="sched-task-item-last">${_escHtml(lastRun)}</span>` : ''}
                </div>
            </div>`;
        item.addEventListener('click', () => scheduleSelectTask(task.id));
        list.appendChild(item);
    });
}

function _escHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Select / load a task ──────────────────────────────────────
async function scheduleSelectTask(taskId) {
    _schedCurrentId = taskId;
    _schedRenderTaskList();   // update active highlight

    // Show task view — guard against partial not yet loaded
    const _noTask   = _sEl('sched-no-task');
    const _taskView = _sEl('sched-task-view');
    if (!_noTask || !_taskView) return;  // panel not in DOM yet
    _noTask.style.display   = 'none';
    _taskView.style.display = '';

    try {
        const resp = await fetch(`/api/schedule/tasks/${taskId}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const task = await resp.json();
        _schedCurrentTask = task;
        _schedUpdateInfoCard(task);
        _schedRenderThread(task.thread || []);
        _schedRenderRuns(task.runs || []);
        // Persist selection
        localStorage.setItem('schedule_task_id', taskId);
    } catch (e) {
        console.error('[Schedule] Failed to load task:', e);
    }
}

// ── Info card ─────────────────────────────────────────────────
function _schedUpdateInfoCard(task) {
    const name      = _sEl('sched-info-name');
    const badge     = _sEl('sched-status-badge');
    const dot       = _sEl('sched-status-dot');
    const cronHuman = _sEl('sched-cron-human');
    const nextWrap  = _sEl('sched-next-run-wrap');
    const nextRun   = _sEl('sched-next-run');
    const lastWrap  = _sEl('sched-last-run-wrap');
    const lastRun   = _sEl('sched-last-run');
    const pauseBtn  = _sEl('sched-pause-btn');
    const pauseLbl  = _sEl('sched-pause-label');
    const queueInp  = _sEl('sched-queue-max');

    if (name)      name.textContent      = task.name || 'Untitled';
    if (badge) {
        badge.textContent = task.status || 'draft';
        badge.className   = `sched-status-badge sched-status-${task.status || 'draft'}`;
    }
    if (dot) {
        dot.className = `sched-status-dot ${{ active: 'dot-active', paused: 'dot-paused', draft: 'dot-draft' }[task.status] || 'dot-draft'}`;
    }
    if (cronHuman) cronHuman.textContent = task.cron_human || (task.cron ? `cron: ${task.cron}` : 'Not scheduled yet');

    const tzWrap    = _sEl('sched-tz-wrap');
    const tzDisplay = _sEl('sched-tz-display');
    if (tzWrap && tzDisplay) {
        const tz = task.timezone || 'UTC';
        if (task.cron && tz !== 'UTC') {
            tzDisplay.textContent  = tz;
            tzWrap.style.display   = '';
        } else {
            tzWrap.style.display   = 'none';
        }
    }

    if (nextWrap && nextRun) {
        if (task.next_run_at && task.status === 'active') {
            nextRun.textContent  = _schedFmtTime(task.next_run_at);
            nextWrap.style.display = '';
        } else {
            nextWrap.style.display = 'none';
        }
    }
    if (lastWrap && lastRun) {
        if (task.last_run_at) {
            lastRun.textContent  = _schedFmtTime(task.last_run_at);
            lastWrap.style.display = '';
        } else {
            lastWrap.style.display = 'none';
        }
    }

    if (pauseBtn && pauseLbl) {
        const isPaused = task.status === 'paused';
        pauseLbl.textContent    = isPaused ? 'Resume' : 'Pause';
        pauseBtn.querySelector('i').className = isPaused ? 'fas fa-play' : 'fas fa-pause';
        pauseBtn.disabled       = task.status === 'draft';
        pauseBtn.title          = isPaused ? 'Resume this schedule' : 'Pause this schedule';
    }

    if (queueInp) queueInp.value = task.queue_max ?? 1;

    // Sync model select to THIS task's saved model (per-task)
    const modelSel = _sEl('sched-model-select');
    if (modelSel) {
        const wanted = task.model_id || 'auto';
        if (modelSel.querySelector(`option[value="${CSS.escape(wanted)}"]`)) {
            modelSel.value = wanted;
        } else {
            modelSel.value = 'auto';
        }
    }

    // Update sidebar item too
    const sideItem = document.querySelector(`.sched-task-item[data-task-id="${task.id}"]`);
    if (sideItem) {
        const metaEl = sideItem.querySelector('.sched-task-item-meta');
        if (metaEl) metaEl.textContent = task.cron_human || task.cron || 'Not scheduled';
        const nameEl = sideItem.querySelector('.sched-task-item-name');
        if (nameEl) nameEl.textContent = task.name || 'Untitled';
    }
}

// ── Render conversation thread ────────────────────────────────
function _schedRenderThread(thread) {
    const msgs = _sEl('sched-messages');
    if (!msgs) return;
    msgs.innerHTML = '';

    if (thread.length === 0) {
        msgs.innerHTML = `
            <div class="sched-intro">
                <div class="sched-intro-icon">🗓️</div>
                <div class="sched-intro-title">Set up your schedule</div>
                <div class="sched-intro-sub">
                    Describe what you want to automate and how often.<br>
                    The AI will help you configure the schedule and the prompt it will run.
                </div>
                <div class="sched-intro-examples">
                    <span class="sched-example-chip" data-msg="I want to check up on my workout routine every Monday at 9 AM">💪 Weekly workout check</span>
                    <span class="sched-example-chip" data-msg="Send me a daily motivational quote every morning at 8 AM">🌅 Daily motivation</span>
                    <span class="sched-example-chip" data-msg="Give me a brief market summary every weekday at 9 AM">📈 Weekday market brief</span>
                    <span class="sched-example-chip" data-msg="Remind me to drink water every 2 hours during the day">💧 Hydration reminder</span>
                </div>
            </div>`;
        // wire up chips
        msgs.querySelectorAll('.sched-example-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                const inp = _sEl('sched-input');
                if (inp) { inp.value = chip.dataset.msg; inp.focus(); }
            });
        });
        return;
    }

    thread.forEach(msg => _schedAppendMessage(msg, false));
    msgs.scrollTop = msgs.scrollHeight;
}

function _schedRenderRuns(runs) {
    // Append completed runs as special cards at the bottom of the messages area
    const msgs = _sEl('sched-messages');
    if (!msgs || !runs || runs.length === 0) return;

    const completed = runs.filter(r => r.status !== 'running' && r.status !== 'queued').slice(-5);
    if (completed.length === 0) return;

    const divider = document.createElement('div');
    divider.className = 'sched-runs-divider';
    divider.innerHTML = `<span>Recent Runs</span>`;
    msgs.appendChild(divider);

    completed.forEach(run => {
        const card = document.createElement('div');
        card.className = `sched-run-card sched-run-${run.status}`;
        const ts  = _schedFmtTime(run.completed_at || run.triggered_at);
        const ico = { success: '✅', failed: '❌', skipped: '⏭️' }[run.status] || '•';
        const tag = run.manual ? ' (manual)' : '';
        card.innerHTML = `
            <div class="sched-run-header">
                <span>${ico} ${run.status}${tag}</span>
                <span class="sched-run-ts">${ts}</span>
            </div>
            ${run.result ? `<div class="sched-run-result">${_schedMd(run.result)}</div>` : ''}`;
        msgs.appendChild(card);
    });
    msgs.scrollTop = msgs.scrollHeight;
}

function _schedAppendMessage(msg, scroll = true) {
    const msgs = _sEl('sched-messages');
    if (!msgs) return;

    // Remove intro if present
    const intro = msgs.querySelector('.sched-intro');
    if (intro) intro.remove();

    const el = document.createElement('div');
    el.className = `sched-msg sched-msg-${msg.role}`;

    const ts = msg.ts ? _schedFmtTime(msg.ts) : '';
    if (msg.role === 'user') {
        el.innerHTML = `
            <div class="sched-msg-bubble sched-msg-user-bubble">
                <div class="sched-msg-text">${_escHtml(msg.content)}</div>
                ${ts ? `<div class="sched-msg-ts">${ts}</div>` : ''}
            </div>`;
    } else {
        el.innerHTML = `
            <div class="sched-msg-bubble sched-msg-ai-bubble">
                <div class="sched-msg-text">${_schedMd(msg.content)}</div>
                ${ts ? `<div class="sched-msg-ts">${ts}</div>` : ''}
            </div>`;
    }

    msgs.appendChild(el);
    if (scroll) msgs.scrollTop = msgs.scrollHeight;
}

// ── Send message ──────────────────────────────────────────────
async function scheduleSendMessage() {
    if (_schedIsSending || !_schedCurrentId) return;
    const inp  = _sEl('sched-input');
    const text = inp?.value.trim();
    if (!text) return;

    inp.value = '';
    inp.style.height = '';
    _schedIsSending = true;
    _sEl('sched-send-btn').disabled = true;

    // Optimistically add user message (toISOString() always returns UTC with 'Z')
    _schedAppendMessage({ role: 'user', content: text, ts: new Date().toISOString() });

    // Show typing
    const typing = _sEl('sched-typing');
    if (typing) typing.style.display = 'flex';

    try {
        const modelSel = _sEl('sched-model-select');
        const modelId  = modelSel?.value || 'auto';

        const resp = await fetch(`/api/schedule/tasks/${_schedCurrentId}/chat`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ message: text, model_id: modelId === 'auto' ? null : modelId }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        if (typing) typing.style.display = 'none';
        _schedAppendMessage({ role: 'assistant', content: data.reply, ts: new Date().toISOString() });  // toISOString = UTC+Z

        // Update info card if schedule changed
        if (data.task) {
            _schedCurrentTask = { ...(_schedCurrentTask || {}), ...data.task };
            _schedUpdateInfoCard(_schedCurrentTask);
            // Refresh sidebar item
            const idx = _schedTasks.findIndex(t => t.id === _schedCurrentId);
            if (idx >= 0) _schedTasks[idx] = { ..._schedTasks[idx], ...data.task };
            _schedRenderTaskList();
        }
    } catch (e) {
        if (typing) typing.style.display = 'none';
        _schedAppendMessage({ role: 'assistant', content: `Error: ${e.message}`, ts: new Date().toISOString() });
        console.error('[Schedule] Send failed:', e);
    } finally {
        _schedIsSending = false;
        _sEl('sched-send-btn').disabled = false;
        inp?.focus();
    }
}

// ── Create new task ───────────────────────────────────────────
async function scheduleNewTask() {
    try {
        const modelSel = _sEl('sched-model-select');
        const modelId  = modelSel?.value;
        const resp = await fetch('/api/schedule/tasks', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ model_id: modelId && modelId !== 'auto' ? modelId : null }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const task = await resp.json();
        _schedTasks.unshift({ ...task });
        _schedRenderTaskList();
        await scheduleSelectTask(task.id);
    } catch (e) {
        console.error('[Schedule] Create task failed:', e);
    }
}

// ── Run now ───────────────────────────────────────────────────
async function scheduleRunNow() {
    if (!_schedCurrentId) return;
    const btn = _sEl('sched-run-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Running…'; }
    try {
        const resp = await fetch(`/api/schedule/tasks/${_schedCurrentId}/run`, { method: 'POST' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const run = await resp.json();
        // Show feedback in chat
        const statusMsg = run.error
            ? `Could not start run: ${run.error}`
            : `Run started (id: ${run.id?.slice(0, 8)}…) — result will appear here when complete.`;
        _schedAppendMessage({ role: 'assistant', content: `*[Manual run triggered]* ${statusMsg}`, ts: new Date().toISOString() });
        // Poll once after 3 seconds to refresh run result
        setTimeout(() => _schedRefreshRuns(), 3000);
    } catch (e) {
        console.error('[Schedule] Run now failed:', e);
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-play"></i> Run Now'; }
    }
}

async function _schedRefreshRuns() {
    if (!_schedCurrentId) return;
    try {
        const resp = await fetch(`/api/schedule/tasks/${_schedCurrentId}`);
        if (!resp.ok) return;
        const task = await resp.json();
        _schedCurrentTask = task;
        _schedUpdateInfoCard(task);
        // Re-render runs section
        const msgs = _sEl('sched-messages');
        if (msgs) {
            const existing = msgs.querySelector('.sched-runs-divider');
            if (existing) {
                // Remove old runs section
                let el = existing;
                while (el) { const next = el.nextSibling; el.remove(); el = next; }
            }
            _schedRenderRuns(task.runs || []);
        }
    } catch (_) {}
}

// ── Pause / Resume ────────────────────────────────────────────
async function scheduleTogglePause() {
    if (!_schedCurrentId || !_schedCurrentTask) return;
    const isPaused = _schedCurrentTask.status === 'paused';
    const endpoint = isPaused ? 'resume' : 'pause';
    try {
        const resp = await fetch(`/api/schedule/tasks/${_schedCurrentId}/${endpoint}`, { method: 'POST' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        _schedCurrentTask.status = data.status;
        _schedUpdateInfoCard(_schedCurrentTask);
        const idx = _schedTasks.findIndex(t => t.id === _schedCurrentId);
        if (idx >= 0) { _schedTasks[idx].status = data.status; _schedRenderTaskList(); }
    } catch (e) {
        console.error('[Schedule] Toggle pause failed:', e);
    }
}

// ── Delete task ───────────────────────────────────────────────
async function scheduleDeleteTask() {
    if (!_schedCurrentId) return;
    const name = _schedCurrentTask?.name || 'this schedule';
    if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
    try {
        const resp = await fetch(`/api/schedule/tasks/${_schedCurrentId}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        _schedTasks = _schedTasks.filter(t => t.id !== _schedCurrentId);
        _schedCurrentId   = null;
        _schedCurrentTask = null;
        _schedRenderTaskList();
        _sEl('sched-no-task').style.display  = '';
        _sEl('sched-task-view').style.display = 'none';
        localStorage.removeItem('schedule_task_id');
    } catch (e) {
        console.error('[Schedule] Delete failed:', e);
    }
}

// ── Save queue setting ────────────────────────────────────────
async function scheduleSaveQueueMax() {
    if (!_schedCurrentId) return;
    const inp = _sEl('sched-queue-max');
    const val = parseInt(inp?.value ?? '1', 10);
    if (isNaN(val) || val < 0) return;
    try {
        const resp = await fetch(`/api/schedule/tasks/${_schedCurrentId}`, {
            method:  'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ queue_max: val }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        if (_schedCurrentTask) _schedCurrentTask.queue_max = val;
    } catch (e) {
        console.error('[Schedule] Save queue max failed:', e);
    }
}

// ── Model population ──────────────────────────────────────────
async function _schedLoadModels() {
    try {
        const resp = await fetch('/api/registry/models/chat');
        if (!resp.ok) return;
        const data = await resp.json();

        const sel = _sEl('sched-model-select');
        if (!sel) return;

        // Use the same grouped/categorized dropdown as Agents and other tabs
        if (typeof generateCategorizedModelOptions === 'function') {
            sel.innerHTML = generateCategorizedModelOptions(data, 'chat');
        } else {
            // Fallback: flat list
            sel.innerHTML = '<option value="auto">Auto</option>';
            for (const m of data.models || []) {
                const opt = document.createElement('option');
                opt.value = m.id; opt.textContent = m.name || m.id;
                sel.appendChild(opt);
            }
        }

        // Restore saved selection
        const saved = localStorage.getItem('schedule_model_id');
        if (saved) {
            const opt = sel.querySelector(`option[value="${CSS.escape(saved)}"]`);
            if (opt) sel.value = saved;
        }
    } catch (e) {
        console.error('[Schedule] Failed to load models:', e);
    }
}

// ── Overview (Knowledge tab) ──────────────────────────────────
async function scheduleLoadOverview() {
    try {
        const resp = await fetch('/api/schedule/tasks');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data  = await resp.json();
        const tasks = data.tasks || [];
        const tbody = _sEl('sched-ov-tbody');
        const empty = _sEl('sched-ov-empty');
        const table = _sEl('sched-ov-table');
        if (!tbody) return;

        tbody.innerHTML = '';
        if (tasks.length === 0) {
            if (empty) empty.style.display = '';
            if (table) table.style.display = 'none';
            return;
        }
        if (empty) empty.style.display = 'none';
        if (table) table.style.display = '';

        tasks.forEach(task => {
            const statusDot = { active: 'dot-active', paused: 'dot-paused', draft: 'dot-draft' }[task.status] || 'dot-draft';
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><span class="sched-task-dot ${statusDot}" style="display:inline-block"></span> ${_escHtml(task.status || 'draft')}</td>
                <td>${_escHtml(task.name || 'Untitled')}</td>
                <td>${_escHtml(task.cron_human || task.cron || '—')}</td>
                <td>${task.next_run_at && task.status === 'active' ? _schedFmtTime(task.next_run_at) : '—'}</td>
                <td>${task.last_run_at ? _schedFmtTime(task.last_run_at) : '—'}</td>
                <td>${task.queue_max === 0 ? 'Unlimited' : task.queue_max ?? 1}</td>
                <td>
                    <button class="sched-ov-go-btn" title="Open in Schedule tab" data-id="${task.id}">
                        <i class="fas fa-external-link-alt"></i> Open
                    </button>
                </td>`;
            tbody.appendChild(tr);
        });

        // Wire go buttons — switch to schedule tab and select task
        tbody.querySelectorAll('.sched-ov-go-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = btn.dataset.id;
                // Switch to schedule panel
                const schedTab = document.querySelector('[data-maintab="schedule"]');
                if (schedTab) schedTab.click();
                // Give the tab a moment to activate, then select
                setTimeout(() => scheduleSelectTask(id), 100);
            });
        });
    } catch (e) {
        console.error('[Schedule] Overview load failed:', e);
    }
}

// ── Init & event wiring ───────────────────────────────────────
function scheduleInit() {
    // Buttons
    const newBtn       = _sEl('sched-new-btn');
    const noTaskNewBtn = _sEl('sched-no-task-new-btn');
    const sendBtn      = _sEl('sched-send-btn');
    const runBtn       = _sEl('sched-run-btn');
    const pauseBtn     = _sEl('sched-pause-btn');
    const deleteBtn    = _sEl('sched-delete-btn');
    const queueSaveBtn = _sEl('sched-queue-save-btn');
    const ovRefreshBtn = _sEl('sched-ov-refresh-btn');
    const inp          = _sEl('sched-input');

    if (newBtn)       newBtn.addEventListener('click', scheduleNewTask);
    if (noTaskNewBtn) noTaskNewBtn.addEventListener('click', scheduleNewTask);
    if (sendBtn)      sendBtn.addEventListener('click', scheduleSendMessage);
    if (runBtn)       runBtn.addEventListener('click', scheduleRunNow);
    if (pauseBtn)     pauseBtn.addEventListener('click', scheduleTogglePause);
    if (deleteBtn)    deleteBtn.addEventListener('click', scheduleDeleteTask);
    if (queueSaveBtn) queueSaveBtn.addEventListener('click', scheduleSaveQueueMax);
    if (ovRefreshBtn) ovRefreshBtn.addEventListener('click', scheduleLoadOverview);

    // Enter to send (Shift+Enter = newline)
    if (inp) {
        inp.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                scheduleSendMessage();
            }
        });
        inp.addEventListener('input', () => {
            inp.style.height = 'auto';
            inp.style.height = Math.min(inp.scrollHeight, 160) + 'px';
        });
    }

    // Per-task model: save to the task (PATCH) when changed
    const modelSel = _sEl('sched-model-select');
    if (modelSel) {
        modelSel.addEventListener('change', async () => {
            const val = modelSel.value;
            // Always store last used as fallback for new tasks
            localStorage.setItem('schedule_model_id', val);
            if (_schedCurrentId) {
                try {
                    await fetch(`/api/schedule/tasks/${_schedCurrentId}`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ model_id: val === 'auto' ? null : val }),
                    });
                    if (_schedCurrentTask) _schedCurrentTask.model_id = val === 'auto' ? null : val;
                } catch (e) {
                    console.error('[Schedule] Failed to save model to task:', e);
                }
            }
        });
    }

    _schedLoadModels();
    scheduleLoadTasks().then(() => {
        // Restore last selected task
        const last = localStorage.getItem('schedule_task_id');
        if (last && _schedTasks.find(t => t.id === last)) {
            scheduleSelectTask(last);
        }
    });
}

// ── Panel activation hook (called by main tab switcher) ───────
window._scheduleOnActivate = function () {
    scheduleLoadTasks();
};
window._scheduleOverviewOnActivate = function () {
    scheduleLoadOverview();
};

// ── Bootstrap ─────────────────────────────────────────────────
// Wire up panel-agnostic listeners immediately (sidebar buttons are always in the DOM).
// scheduleInit() itself (which queries panel elements) is deferred until the partial loads.
document.addEventListener('DOMContentLoaded', () => {
    // Hook into existing tab switching logic (sidebar buttons exist in shell)
    document.addEventListener('click', e => {
        const tab = e.target.closest('[data-maintab]');
        if (!tab) return;
        const mt = tab.dataset.maintab;
        if (mt === 'schedule')       setTimeout(window._scheduleOnActivate, 50);
        if (mt === 'sched-overview') setTimeout(window._scheduleOverviewOnActivate, 50);
    });

    // Handle deep-linking from notifications
    window.addEventListener('notif-navigate', e => {
        const { tab, context } = e.detail;
        if (tab === 'schedule' && context) {
            if (typeof window._scheduleOnActivate === 'function') window._scheduleOnActivate();
            if (typeof scheduleSelectTask === 'function') {
                setTimeout(() => scheduleSelectTask(context), 150);
            }
        }
    });

    // If the schedule panel is already in the DOM (pre-loaded), init now
    if (document.getElementById('sched-messages')) {
        scheduleInit();
    }
});

// Deferred init: run scheduleInit() once the schedule partial is injected
document.addEventListener('panelLoaded', function (e) {
    if (e.detail.panelId === 'schedule-panel') scheduleInit();
});
