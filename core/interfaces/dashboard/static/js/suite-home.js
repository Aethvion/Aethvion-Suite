/**
 * suite-home.js — Home dashboard logic (Autonomous Life Command Center)
 *
 * Drives:
 *   - Assistant Hero & Omnibar (One-click instruction dispatch)
 *   - Live Dispatched Missions & Autonomous Agent Terminal
 *   - Proactive Life Context (Persistent memory integration)
 *   - Autonomous Schedules & Automations (Cron & Blueprint workflows)
 *   - Recent Conversations & Telemetry Deck
 */

(function () {
    'use strict';

    let _userName = 'Marcel';
    let _missions = [];
    const STORAGE_KEY = 'aethvion_missions_v1';
    let _activePollers = {};

    // ── Greeting ───────────────────────────────────────────────────────────

    function updateGreeting() {
        const hour = new Date().getHours();
        const title = document.getElementById('sh-greeting-title');
        if (title) {
            const timeGreeting =
                hour < 5  ? 'Good night' :
                hour < 12 ? 'Good morning' :
                hour < 17 ? 'Good afternoon' :
                            'Good evening';
            title.textContent = `${timeGreeting}, ${_userName}`;
        }

        const dateEl = document.getElementById('sh-greeting-date');
        if (dateEl) {
            dateEl.textContent = new Date().toLocaleDateString('en-US', {
                weekday: 'long', month: 'short', day: 'numeric', year: 'numeric',
            });
        }
    }

    // ── Dispatched Missions State & Persistence ────────────────────────────

    function loadMissions() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (raw) {
                _missions = JSON.parse(raw);
            }
        } catch (_) {
            _missions = [];
        }
    }

    function saveMissions() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(_missions.slice(0, 10)));
        } catch (_) {}
    }

    // ── Omnibar Dispatch ───────────────────────────────────────────────────

    function setupOmnibar() {
        const input = document.getElementById('sh-omnibar-input');
        const submitBtn = document.getElementById('sh-omnibar-submit');
        if (!input || input.dataset.wired) return;
        input.dataset.wired = 'true';

        function handleDispatch() {
            const text = input.value.trim();
            if (!text) return;
            input.value = '';

            // Dispatch as an autonomous mission on the dashboard!
            dispatchMission(text);
        }

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleDispatch();
            }
        });

        if (submitBtn) {
            submitBtn.addEventListener('click', (e) => {
                e.preventDefault();
                handleDispatch();
            });
        }

        const clearBtn = document.getElementById('sh-missions-clear-all');
        if (clearBtn && !clearBtn.dataset.wired) {
            clearBtn.dataset.wired = 'true';
            clearBtn.addEventListener('click', clearCompletedMissions);
        }
    }

    // ── Mission Runner (Background Execution on Dashboard) ─────────────────

    async function dispatchMission(prompt, existingMission = null) {
        const missionId = existingMission ? existingMission.id : ('m-' + Date.now());
        const threadId = existingMission ? existingMission.thread_id : ('dispatched-' + Date.now());

        const mission = existingMission || {
            id: missionId,
            taskId: null,
            thread_id: threadId,
            prompt: prompt,
            status: 'queued',
            started_at: Date.now(),
            ended_at: null,
            logs: [
                `[${new Date().toLocaleTimeString()}] [System] Mission initialized. Context: Project & Suite tools.`
            ],
            response: null,
            error: null
        };

        if (!existingMission) {
            _missions.unshift(mission);
            saveMissions();
            renderMissions();
        }

        try {
            const payload = {
                prompt: prompt,
                thread_id: threadId,
                thread_title: 'Dashboard Mission: ' + prompt.slice(0, 30),
                mode: 'auto',
                is_incognito: true,
                settings: {
                    internet_search: true
                }
            };

            const res = await fetch('/api/tasks/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to submit task`);
            const data = await res.json();
            mission.taskId = data.task_id;
            mission.status = 'running';
            mission.logs.push(`[${new Date().toLocaleTimeString()}] [Agent] Task queued with ID ${data.task_id}. Execution started.`);
            saveMissions();
            renderMissions();

            // Start live status poller
            startMissionPoller(mission);

        } catch (err) {
            console.error('[home] Mission dispatch error:', err);
            mission.status = 'failed';
            mission.error = err.message || 'Dispatch failed';
            mission.logs.push(`[${new Date().toLocaleTimeString()}] [Error] ${mission.error}`);
            saveMissions();
            renderMissions();
        }
    }

    function startMissionPoller(mission) {
        if (!mission.taskId) return;
        if (_activePollers[mission.id]) clearInterval(_activePollers[mission.id]);

        let elapsedSeconds = 0;

        _activePollers[mission.id] = setInterval(async () => {
            elapsedSeconds++;
            const timerEl = document.getElementById(`timer-${mission.id}`);
            if (timerEl && mission.status === 'running') {
                timerEl.textContent = `${elapsedSeconds}s`;
            }

            try {
                const res = await fetch(`/api/tasks/status/${mission.taskId}`);
                if (!res.ok) return;
                const task = await res.json();

                const status = (task.status || '').toLowerCase();

                if (status === 'completed') {
                    clearInterval(_activePollers[mission.id]);
                    delete _activePollers[mission.id];

                    mission.status = 'completed';
                    mission.ended_at = Date.now();
                    const duration = ((mission.ended_at - mission.started_at) / 1000).toFixed(1);
                    
                    const result = task.result || {};
                    mission.response = result.response || 'Task completed successfully.';
                    mission.logs.push(`[${new Date().toLocaleTimeString()}] [Completed] Mission finished in ${duration}s.`);
                    saveMissions();
                    renderMissions();

                } else if (status === 'failed' || status === 'error' || status === 'cancelled') {
                    clearInterval(_activePollers[mission.id]);
                    delete _activePollers[mission.id];

                    mission.status = status;
                    mission.ended_at = Date.now();
                    mission.error = task.error || (status === 'cancelled' ? 'Mission cancelled by user.' : 'Execution failed.');
                    mission.logs.push(`[${new Date().toLocaleTimeString()}] [${status.toUpperCase()}] ${mission.error}`);
                    saveMissions();
                    renderMissions();
                }

            } catch (err) {
                console.warn('[home] Error polling task:', err);
            }
        }, 1200);
    }

    async function cancelMission(missionId) {
        const mission = _missions.find(m => m.id === missionId);
        if (!mission) return;

        if (_activePollers[missionId]) {
            clearInterval(_activePollers[missionId]);
            delete _activePollers[missionId];
        }

        if (mission.taskId) {
            try {
                await fetch(`/api/tasks/${mission.taskId}/cancel`, { method: 'POST' });
            } catch (_) {}
        }

        mission.status = 'cancelled';
        mission.ended_at = Date.now();
        mission.logs.push(`[${new Date().toLocaleTimeString()}] [System] Mission stopped by user.`);
        saveMissions();
        renderMissions();
    }

    function dismissMission(missionId) {
        if (_activePollers[missionId]) {
            clearInterval(_activePollers[missionId]);
            delete _activePollers[missionId];
        }
        _missions = _missions.filter(m => m.id !== missionId);
        saveMissions();
        renderMissions();
    }

    function clearCompletedMissions() {
        _missions = _missions.filter(m => m.status === 'running');
        saveMissions();
        renderMissions();
    }

    function steerMission(missionId) {
        const inputEl = document.getElementById(`steer-input-${missionId}`);
        if (!inputEl) return;
        const text = inputEl.value.trim();
        if (!text) return;
        inputEl.value = '';

        const mission = _missions.find(m => m.id === missionId);
        if (!mission) return;

        mission.logs.push(`[${new Date().toLocaleTimeString()}] [User Follow-up] ${text}`);
        mission.status = 'running';
        mission.response = null;
        renderMissions();

        dispatchMission(text, mission);
    }

    // ── Render Missions Terminal UI ────────────────────────────────────────

    function renderMissions() {
        const wrapper = document.getElementById('sh-missions-wrapper');
        const list = document.getElementById('sh-missions-list');
        const countBadge = document.getElementById('sh-missions-count');
        if (!wrapper || !list) return;

        if (!_missions.length) {
            wrapper.style.display = 'none';
            return;
        }

        wrapper.style.display = 'flex';
        const activeCount = _missions.filter(m => m.status === 'running').length;
        if (countBadge) countBadge.textContent = String(_missions.length);

        list.innerHTML = '';

        _missions.forEach(m => {
            const card = document.createElement('div');
            card.className = `sh-mission-card sh-mission-${m.status}`;
            card.id = `mission-${m.id}`;

            let statusBadge = '';
            if (m.status === 'running') {
                statusBadge = `<span class="sh-m-badge badge-running"><i class="fas fa-circle-notch fa-spin"></i> RUNNING</span>`;
            } else if (m.status === 'completed') {
                statusBadge = `<span class="sh-m-badge badge-done"><i class="fas fa-check"></i> COMPLETED</span>`;
            } else if (m.status === 'cancelled') {
                statusBadge = `<span class="sh-m-badge badge-cancelled"><i class="fas fa-ban"></i> STOPPED</span>`;
            } else {
                statusBadge = `<span class="sh-m-badge badge-failed"><i class="fas fa-triangle-exclamation"></i> FAILED</span>`;
            }

            const elapsed = m.ended_at
                ? `${((m.ended_at - m.started_at) / 1000).toFixed(1)}s`
                : `<span id="timer-${m.id}">active</span>`;

            // Terminal logs
            const logsText = m.logs.map(l => esc(l)).join('<br>');
            const responseHtml = m.response ? `
                <div class="sh-m-response">
                    <div class="sh-m-resp-header"><i class="fas fa-robot"></i> Agent Output</div>
                    <div class="sh-m-resp-body">${esc(m.response).replace(/\n/g, '<br>')}</div>
                </div>` : '';

            card.innerHTML = `
                <div class="sh-m-header">
                    <div class="sh-m-header-left">
                        <i class="fas fa-terminal sh-m-icon"></i>
                        <span class="sh-m-prompt" title="${esc(m.prompt)}">${esc(m.prompt)}</span>
                        <span class="sh-m-timer"><i class="fas fa-stopwatch"></i> ${elapsed}</span>
                    </div>
                    <div class="sh-m-header-right">
                        ${statusBadge}
                        ${m.status === 'running' 
                            ? `<button class="sh-m-btn sh-m-stop" title="Stop agent execution" onclick="window._cancelMission('${m.id}')"><i class="fas fa-stop"></i> Stop</button>`
                            : `<button class="sh-m-btn sh-m-dismiss" title="Dismiss" onclick="window._dismissMission('${m.id}')"><i class="fas fa-xmark"></i></button>`
                        }
                    </div>
                </div>
                <div class="sh-m-terminal" id="term-${m.id}">
                    <div class="sh-m-logs">${logsText}</div>
                    ${responseHtml}
                </div>
                <div class="sh-m-steer">
                    <input type="text" id="steer-input-${m.id}" class="sh-m-steer-input" 
                           placeholder="Steer this agent or give follow-up instructions..." autocomplete="off">
                    <button class="sh-m-steer-btn" onclick="window._steerMission('${m.id}')">
                        <span>Send</span> <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
            `;

            // Wire Enter key on steer input
            const steerInput = card.querySelector(`#steer-input-${m.id}`);
            if (steerInput) {
                steerInput.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        steerMission(m.id);
                    }
                });
            }

            list.appendChild(card);
        });
    }

    // Expose control actions to window for onclick handlers
    window._cancelMission = cancelMission;
    window._dismissMission = dismissMission;
    window._steerMission = steerMission;

    // ── Life Context & Memory Brief ────────────────────────────────────────

    async function loadLifeContext() {
        const container = document.getElementById('sh-context-body');
        if (!container) return;

        try {
            const res = await fetch('/api/memory/persistent');
            if (!res.ok) throw new Error('Memory API unavailable');
            const data = await res.json();
            const topics = Object.keys(data || {});

            setVal('snap-memory-topics-val', String(topics.length));

            if (!topics.length) {
                container.innerHTML = `
                    <div class="sh-context-empty">
                        <i class="fas fa-brain"></i>
                        <span>No persistent memory recorded yet. Chats and preferences will appear here automatically.</span>
                    </div>`;
                return;
            }

            for (const key of topics) {
                const raw = typeof data[key] === 'object' ? data[key]?.content : data[key];
                if (raw && /Name:\s*([A-Za-z]+)/i.test(raw)) {
                    const match = raw.match(/Name:\s*([A-Za-z]+)/i);
                    if (match && match[1]) {
                        _userName = match[1];
                        updateGreeting();
                    }
                    break;
                }
            }

            let html = '<div class="sh-context-grid">';

            const projectTopic = topics.find(t => /company|game|project/i.test(t));
            const profileTopic = topics.find(t => /user profile/i.test(t));
            const suiteTopic = topics.find(t => /suite/i.test(t));

            const displayKeys = [projectTopic, profileTopic, suiteTopic].filter(Boolean);
            const chosen = displayKeys.length ? displayKeys : topics.slice(0, 3);

            chosen.forEach(k => {
                const item = data[k];
                const content = (typeof item === 'object' ? item.content : String(item || '')).trim();
                const icon = /project|game/i.test(k) ? 'fa-gamepad' :
                             /profile/i.test(k) ? 'fa-user' :
                             /company/i.test(k) ? 'fa-building' : 'fa-brain';
                
                const preview = content
                    .replace(/[*#_`]/g, '')
                    .replace(/\s+/g, ' ')
                    .slice(0, 160) + (content.length > 160 ? '…' : '');

                html += `
                    <div class="sh-context-card" onclick="switchMainTab('persistent-memory')">
                        <div class="sh-ctx-header">
                            <span class="sh-ctx-icon"><i class="fas ${icon}"></i></span>
                            <span class="sh-ctx-title">${esc(k)}</span>
                        </div>
                        <p class="sh-ctx-snippet">${esc(preview)}</p>
                    </div>`;
            });

            html += '</div>';
            container.innerHTML = html;

        } catch (e) {
            console.warn('[home] Failed to load persistent memory:', e);
            container.innerHTML = `
                <div class="sh-context-empty">
                    <i class="fas fa-brain"></i>
                    <span>Memory system active. Context loaded on conversation.</span>
                </div>`;
        }
    }

    // ── Schedules & Automations ────────────────────────────────────────────

    async function loadSchedulesAndWorkflows() {
        const container = document.getElementById('sh-schedule-list');
        if (!container) return;

        let taskList = [];
        let workflowList = [];

        try {
            const [schedRes, wfRes] = await Promise.allSettled([
                fetch('/api/schedule/tasks'),
                fetch('/api/automate/workflows')
            ]);

            if (schedRes.status === 'fulfilled' && schedRes.value.ok) {
                const sData = await schedRes.value.json();
                taskList = sData.tasks ? (Array.isArray(sData.tasks) ? sData.tasks : Object.values(sData.tasks)) : [];
            }

            if (wfRes.status === 'fulfilled' && wfRes.value.ok) {
                const wData = await wfRes.value.json();
                workflowList = wData.workflows || [];
            }
        } catch (e) {
            console.warn('[home] Failed loading schedules/workflows:', e);
        }

        setVal('snap-workflows-val', String(workflowList.length));

        if (!taskList.length && !workflowList.length) {
            container.innerHTML = `
                <div class="sh-sched-empty">
                    <div class="sh-sched-empty-icon"><i class="fas fa-robot"></i></div>
                    <div class="sh-sched-empty-text">No active background automations running</div>
                    <button class="sh-action-btn sh-action-btn--primary" style="margin-top:8px;" onclick="switchMainTab('automate');">
                        <i class="fas fa-plus"></i><span>Create Workflow</span>
                    </button>
                </div>`;
            return;
        }

        let html = '<div class="sh-sched-items">';

        taskList.slice(0, 2).forEach(task => {
            const isPaused = task.is_paused || false;
            const badgeClass = isPaused ? 'badge-paused' : 'badge-active';
            const badgeText = isPaused ? 'Paused' : 'Active';
            html += `
                <div class="sh-sched-item" onclick="switchMainTab('schedule')">
                    <div class="sh-sched-left">
                        <span class="sh-sched-icon"><i class="fas fa-calendar-check"></i></span>
                        <div class="sh-sched-meta">
                            <span class="sh-sched-name">${esc(task.name || task.id)}</span>
                            <span class="sh-sched-desc">${esc(task.cron_expr || 'Scheduled Trigger')}</span>
                        </div>
                    </div>
                    <span class="sh-sched-badge ${badgeClass}">${badgeText}</span>
                </div>`;
        });

        workflowList.slice(0, 2).forEach(wf => {
            html += `
                <div class="sh-sched-item" onclick="switchMainTab('automate')">
                    <div class="sh-sched-left">
                        <span class="sh-sched-icon"><i class="fas fa-bolt"></i></span>
                        <div class="sh-sched-meta">
                            <span class="sh-sched-name">${esc(wf.name || 'Automate Workflow')}</span>
                            <span class="sh-sched-desc">${wf.node_count || 0} nodes configured</span>
                        </div>
                    </div>
                    <span class="sh-sched-badge badge-workflow">Ready</span>
                </div>`;
        });

        html += '</div>';
        container.innerHTML = html;
    }

    // ── Stats & Telemetry ──────────────────────────────────────────────────

    function setVal(id, val) {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    function loadStats() {
        const nav = window._sidebarNav;
        if (nav) setVal('snap-tabs-val', String(nav.getTotalTabCount()));

        const vBadge = document.getElementById('suite-hero-version');
        const vText  = vBadge?.textContent?.replace('Version ', '').trim();
        setVal('snap-version-val', vText && vText !== '—' ? vText : '2.0-secure');

        function syncUsage() {
            const t = document.getElementById('tokens-today')?.textContent?.trim();
            const c = document.getElementById('cost-today')?.textContent?.trim();
            if (t) setVal('snap-tokens-val', t);
            if (c) setVal('snap-cost-val', c);
        }
        syncUsage();
        const usageTick = setInterval(syncUsage, 5000);
        window._suiteHomeUsageTick = usageTick;

        let tries = 0;
        const ticker = setInterval(() => {
            const label = document.getElementById('hub-servers-label')?.textContent || '';
            const match = label.match(/(\d+)\s*\/\s*(\d+)/);
            if (match) {
                setVal('snap-servers-val', `${match[1]}/${match[2]}`);
                clearInterval(ticker);
            } else if (label && !label.includes('checking') && !label.includes('…')) {
                setVal('snap-servers-val', label.split(' ').slice(0, 2).join(' '));
                clearInterval(ticker);
            }
            if (++tries > 20) clearInterval(ticker);
        }, 200);

        fetch('/api/system/status')
            .then(r => r.ok ? r.json() : null)
            .then(d => {
                if (d?.data_folders != null) setVal('snap-folders-val', String(d.data_folders));
                else setVal('snap-folders-val', '—');

                if (d?.vitals?.cpu_percent != null) {
                    setVal('snap-cpu-val', `${d.vitals.cpu_percent}%`);
                } else {
                    setVal('snap-cpu-val', 'Nominal');
                }
            })
            .catch(() => {
                setVal('snap-folders-val', '—');
                setVal('snap-cpu-val', 'Nominal');
            });
    }

    // ── Recent Conversations ───────────────────────────────────────────────

    function esc(s) {
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

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
        return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }

    async function renderRecentThreads() {
        const container = document.getElementById('sh-recent-list');
        if (!container) return;

        let threadArr = [];
        try {
            if (window.threads && Object.keys(window.threads).length > 0) {
                threadArr = Object.values(window.threads);
            } else {
                const res = await fetch('/api/tasks/threads');
                if (res.ok) {
                    const data = await res.json();
                    threadArr = data.threads || [];
                }
            }
        } catch (e) {
            console.error('[home] Failed to fetch threads:', e);
        }

        const sorted = threadArr
            .filter(t => !t.id.startsWith('agents-') && !t.id.startsWith('dispatched-'))
            .sort((a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at));

        if (!sorted.length) {
            container.innerHTML = `
                <div class="ae-empty" style="min-height:100px;padding:1.5rem 1rem;">
                    <div class="ae-empty-icon"><i class="fas fa-comments"></i></div>
                    <div class="ae-empty-title">No conversations yet</div>
                    <div class="ae-empty-desc">Start a chat session to see history here.</div>
                </div>`;
            return;
        }

        container.innerHTML = '';
        sorted.slice(0, 4).forEach(t => {
            const row = document.createElement('button');
            row.className = 'sh-thread-row';
            const preview = (t.last_message || '').replace(/<[^>]+>/g, '').trim().slice(0, 95) || 'No messages yet';
            const isPinned = t.is_pinned ? '<i class="fas fa-thumbtack sh-thread-pin" title="Pinned"></i>' : '';
            row.innerHTML = `
                <div class="sh-thread-icon">
                    <i class="fas fa-comment-dots"></i>
                </div>
                <div class="sh-thread-body">
                    <div class="sh-thread-top">
                        <span class="sh-thread-title">${esc(t.title)}${isPinned}</span>
                        <span class="sh-thread-time">${relativeTime(t.updated_at || t.created_at)}</span>
                    </div>
                    <div class="sh-thread-preview">${esc(preview)}</div>
                </div>
                <i class="fas fa-chevron-right sh-thread-arrow"></i>`;
            row.addEventListener('click', () => {
                window.setDashboardMode?.('home');
                window.switchMainTab?.('chat');
                setTimeout(() => window.switchThread?.(t.id), 80);
            });
            container.appendChild(row);
        });
    }

    // ── Main Controller ────────────────────────────────────────────────────

    function update() {
        loadMissions();
        updateGreeting();
        setupOmnibar();
        renderMissions();
        // Resume pollers for running missions
        _missions.filter(m => m.status === 'running' && m.taskId).forEach(startMissionPoller);
        loadStats();
        loadLifeContext();
        loadSchedulesAndWorkflows();
        renderRecentThreads();
    }

    window._suiteHomeUpdate = update;

    function watchPanel() {
        const panel = document.getElementById('suite-home-panel');
        if (!panel) { setTimeout(watchPanel, 300); return; }

        function check() {
            if (panel.classList.contains('active') && !panel.querySelector('.partial-loading')) {
                if (window._suiteHomeUsageTick) clearInterval(window._suiteHomeUsageTick);
                update();
            }
        }

        const obs = new MutationObserver(check);
        obs.observe(panel, { attributes: true, attributeFilter: ['class'], childList: true });
        check();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', watchPanel);
    } else {
        watchPanel();
    }
})();
