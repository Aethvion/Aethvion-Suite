/**
 * suite-home.js — Home dashboard logic
 *
 * Drives:
 *   - Greeting bar (time-based greeting + today's date)
 *   - Today's stats (tokens, cost, servers, build)
 *   - Recent Conversations (last 5 chat threads)
 *   - System snapshot (active modules, data folders)
 */

(function () {
    'use strict';

    // ── Greeting ───────────────────────────────────────────────────────────

    function updateGreeting() {
        const hour = new Date().getHours();
        const title = document.getElementById('sh-greeting-title');
        if (title) {
            const greeting =
                hour < 5  ? 'Good night' :
                hour < 12 ? 'Good morning' :
                hour < 17 ? 'Good afternoon' :
                            'Good evening';
            title.textContent = greeting;
        }

        const dateEl = document.getElementById('sh-greeting-date');
        if (dateEl) {
            dateEl.textContent = new Date().toLocaleDateString('en-US', {
                weekday: 'long', month: 'short', day: 'numeric', year: 'numeric',
            });
        }
    }

    // ── Stats ──────────────────────────────────────────────────────────────

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
        setVal('snap-version-val', vText && vText !== '—' ? vText : '—');

        // Tokens + cost — mirror the live header counters
        function syncUsage() {
            const t = document.getElementById('tokens-today')?.textContent?.trim();
            const c = document.getElementById('cost-today')?.textContent?.trim();
            if (t) setVal('snap-tokens-val', t);
            if (c) setVal('snap-cost-val', c);
        }
        syncUsage();
        // Keep re-syncing every 5s while the panel is visible
        const usageTick = setInterval(syncUsage, 5000);
        // Stop when panel goes inactive (MutationObserver clears it)
        window._suiteHomeUsageTick = usageTick;

        // Core servers — poll the label populated by core.js
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

        // Data folders — count from /api/system/status if available
        fetch('/api/system/status')
            .then(r => r.ok ? r.json() : null)
            .then(d => {
                if (d?.data_folders != null) setVal('snap-folders-val', String(d.data_folders));
                else setVal('snap-folders-val', '—');
            })
            .catch(() => setVal('snap-folders-val', '—'));
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
                <div class="ae-empty" style="min-height:160px;padding:2rem 1rem;">
                    <div class="ae-empty-icon"><i class="fas fa-comments"></i></div>
                    <div class="ae-empty-title">No conversations yet</div>
                    <div class="ae-empty-desc">Start a chat to see your recent threads here.</div>
                </div>`;
            return;
        }

        container.innerHTML = '';
        sorted.slice(0, 5).forEach(t => {
            const row = document.createElement('button');
            row.className = 'sh-thread-row';
            const preview = (t.last_message || '').replace(/<[^>]+>/g, '').trim().slice(0, 90) || 'No messages yet';
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

    // ── Main ───────────────────────────────────────────────────────────────

    function update() {
        updateGreeting();
        loadStats();
        renderRecentThreads();
    }

    window._suiteHomeUpdate = update;

    // Watch for panel activation
    function watchPanel() {
        const panel = document.getElementById('suite-home-panel');
        if (!panel) { setTimeout(watchPanel, 300); return; }

        function check() {
            if (panel.classList.contains('active') && !panel.querySelector('.partial-loading')) {
                // Clear any previous usage ticker before starting fresh
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
