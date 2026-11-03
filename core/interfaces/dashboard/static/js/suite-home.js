/**
 * suite-home.js — Home dashboard logic (Autonomous Life Command Center)
 *
 * Drives:
 *   - Assistant Hero & Omnibar (One-click instruction dispatch)
 *   - Proactive Life Context (Persistent memory integration)
 *   - Autonomous Schedules & Automations (Cron & Blueprint workflows)
 *   - Recent Conversations & Telemetry Deck
 */

(function () {
    'use strict';

    let _userName = 'Marcel';

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

    // ── Omnibar Dispatch ───────────────────────────────────────────────────

    function setupOmnibar() {
        const input = document.getElementById('sh-omnibar-input');
        const submitBtn = document.getElementById('sh-omnibar-submit');
        if (!input || input.dataset.wired) return;
        input.dataset.wired = 'true';

        function dispatch() {
            const text = input.value.trim();
            if (!text) return;
            input.value = '';

            // Switch to chat panel
            if (typeof window.setDashboardMode === 'function') {
                window.setDashboardMode('home', true, 'chat');
            } else if (typeof window.switchMainTab === 'function') {
                window.switchMainTab('chat');
            }

            // Populate chat input and trigger send
            setTimeout(() => {
                const chatInput = document.getElementById('chat-input');
                const sendBtn = document.getElementById('send-button');
                if (chatInput) {
                    chatInput.value = text;
                    chatInput.dispatchEvent(new Event('input', { bubbles: true }));
                    chatInput.focus();
                    if (sendBtn) {
                        setTimeout(() => sendBtn.click(), 50);
                    }
                }
            }, 200);
        }

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                dispatch();
            }
        });

        if (submitBtn) {
            submitBtn.addEventListener('click', (e) => {
                e.preventDefault();
                dispatch();
            });
        }
    }

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

            // Extract user name if stored
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

            // Build rich contextual briefing cards
            let html = '<div class="sh-context-grid">';

            // Filter key topics: Project, Company, Profile
            const projectTopic = topics.find(t => /company|game|project/i.test(t));
            const profileTopic = topics.find(t => /user profile/i.test(t));
            const suiteTopic = topics.find(t => /suite/i.test(t));

            const displayKeys = [projectTopic, profileTopic, suiteTopic].filter(Boolean);
            // Fallback to first 2-3 topics if no exact match
            const chosen = displayKeys.length ? displayKeys : topics.slice(0, 3);

            chosen.forEach(k => {
                const item = data[k];
                const content = (typeof item === 'object' ? item.content : String(item || '')).trim();
                const icon = /project|game/i.test(k) ? 'fa-gamepad' :
                             /profile/i.test(k) ? 'fa-user' :
                             /company/i.test(k) ? 'fa-building' : 'fa-brain';
                
                // Truncate cleanly for dashboard display
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

        // Render up to 2 active tasks
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

        // Render up to 2 workflows
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
        // Active modules from sidebar nav
        const nav = window._sidebarNav;
        if (nav) setVal('snap-tabs-val', String(nav.getTotalTabCount()));

        // Build version
        const vBadge = document.getElementById('suite-hero-version');
        const vText  = vBadge?.textContent?.replace('Version ', '').trim();
        setVal('snap-version-val', vText && vText !== '—' ? vText : '2.0-secure');

        // Tokens + cost — mirror the live header counters
        function syncUsage() {
            const t = document.getElementById('tokens-today')?.textContent?.trim();
            const c = document.getElementById('cost-today')?.textContent?.trim();
            if (t) setVal('snap-tokens-val', t);
            if (c) setVal('snap-cost-val', c);
        }
        syncUsage();
        const usageTick = setInterval(syncUsage, 5000);
        window._suiteHomeUsageTick = usageTick;

        // Core servers
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

        // System CPU / status
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
            .filter(t => !t.id.startsWith('agents-'))
            .sort((a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at));

        if (!sorted.length) {
            container.innerHTML = `
                <div class="ae-empty" style="min-height:100px;padding:1.5rem 1rem;">
                    <div class="ae-empty-icon"><i class="fas fa-comments"></i></div>
                    <div class="ae-empty-title">No conversations yet</div>
                    <div class="ae-empty-desc">Dispatch an instruction above to start a session.</div>
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
        updateGreeting();
        setupOmnibar();
        loadStats();
        loadLifeContext();
        loadSchedulesAndWorkflows();
        renderRecentThreads();
    }

    window._suiteHomeUpdate = update;

    // Watch for panel activation
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
