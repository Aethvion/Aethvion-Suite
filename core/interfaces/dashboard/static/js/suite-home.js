/**
 * suite-home.js — Home page logic
 *
 * Renders:
 *   - Hero subtitle + CTA buttons
 *   - System Snapshot stats (module count, servers, build version)
 *   - Recent Activity (last 3 chat threads)
 */

(function () {
    'use strict';

    const DEFAULT_INFO = {
        subtitle: 'Welcome to your advanced AI operations center. Aethvion Suite is designed to orchestrate complex tasks, manage local models, and provide a unified interface for all your AI needs.',
        ctas: [
            { label: 'Quick Start Chat', icon: 'fas fa-rocket',    tab: 'chat',          mode: 'home' },
            { label: 'Read Overview',    icon: 'fas fa-book-open', tab: 'documentation', mode: null   },
        ],
    };

    // ── Hero ───────────────────────────────────────────────────────────────

    function updateSubtitle(text) {
        const el = document.getElementById('sh-subtitle');
        if (!el) return;
        el.style.opacity = '0';
        setTimeout(() => { el.textContent = text; el.style.opacity = '1'; }, 120);
    }

    function updateCTAs(ctas) {
        const primary   = document.getElementById('sh-cta-primary');
        const secondary = document.getElementById('sh-cta-secondary');
        if (!primary || !secondary || !ctas) return;
        const [c1, c2] = ctas;
        if (c1) {
            primary.innerHTML = `<i class="${c1.icon}"></i><span>${c1.label}</span><i class="fas fa-arrow-right sh-cta-arrow"></i>`;
            primary.onclick = c1.tab
                ? () => { if (c1.mode) window.setDashboardMode?.(c1.mode); window.switchMainTab?.(c1.tab); }
                : null;
        }
        if (c2) {
            secondary.innerHTML = `<i class="${c2.icon}"></i><span>${c2.label}</span>`;
            secondary.onclick = c2.tab
                ? () => { if (c2.mode) window.setDashboardMode?.(c2.mode); window.switchMainTab?.(c2.tab); }
                : null;
        }
    }

    // ── System Snapshot ────────────────────────────────────────────────────

    function setSnap(id, val) {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    function loadStats() {
        // Active modules — total tab count from sidebar nav
        const nav = window._sidebarNav;
        if (nav) setSnap('snap-tabs-val', String(nav.getTotalTabCount()));

        // Build version — read from the version badge the server populates
        const vBadge = document.getElementById('suite-hero-version');
        const vText  = vBadge?.textContent?.replace('Version ', '').trim();
        setSnap('snap-version-val', vText && vText !== '—' ? vText : '—');

        // Core servers — poll the label populated by core.js
        let tries = 0;
        const ticker = setInterval(() => {
            const label = document.getElementById('hub-servers-label')?.textContent || '';
            const match  = label.match(/(\d+)\s*\/\s*(\d+)/);
            if (match) {
                setSnap('snap-servers-val', `${match[1]}/${match[2]}`);
                clearInterval(ticker);
            } else if (label && !label.includes('checking') && !label.includes('…')) {
                setSnap('snap-servers-val', label.split(' ').slice(0, 2).join(' '));
                clearInterval(ticker);
            }
            if (++tries > 20) clearInterval(ticker);
        }, 200);
    }

    // ── Recent Activity ────────────────────────────────────────────────────

    function esc(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
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
        return new Date(dateStr).toLocaleDateString();
    }

    async function renderRecentActivity() {
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
        } catch (e) { console.error('Home: Failed to fetch recent activity', e); }

        if (!threadArr.length) {
            container.innerHTML = `
                <div class="ae-empty" style="min-height:140px;padding:2rem;">
                    <div class="ae-empty-icon"><i class="fas fa-clock-rotate-left"></i></div>
                    <div class="ae-empty-title">No recent activity</div>
                    <div class="ae-empty-desc">Start a conversation in Chat to see your activity here.</div>
                </div>`;
            return;
        }

        const sorted = threadArr
            .filter(t => !t.id.startsWith('agents-'))
            .sort((a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at));

        container.innerHTML = '';
        sorted.slice(0, 3).forEach(t => {
            const row     = document.createElement('div');
            row.className = 'sh-recent-row';
            row.title     = `Switch to ${t.title}`;
            const preview = (t.last_message || 'No messages yet').replace(/<[^>]+>/g, '').slice(0, 70);
            row.innerHTML = `
                <div class="sh-rr-icon"><i class="fas fa-comment-dots"></i></div>
                <div class="sh-rr-body">
                    <div class="sh-rr-top">
                        <span class="sh-rr-name">${esc(t.title)}</span>
                        <span class="sh-rr-time">${relativeTime(t.updated_at || t.created_at)}</span>
                    </div>
                    <div class="sh-rr-preview">${esc(preview)}</div>
                </div>
                <i class="fas fa-chevron-right sh-rr-arrow"></i>`;
            row.addEventListener('click', () => {
                window.setDashboardMode?.('home');
                window.switchMainTab?.('chat');
                setTimeout(() => { window.switchThread?.(t.id); }, 50);
            });
            container.appendChild(row);
        });
    }

    // ── Main update ────────────────────────────────────────────────────────

    function update() {
        updateSubtitle(DEFAULT_INFO.subtitle);
        updateCTAs(DEFAULT_INFO.ctas);
        loadStats();
        renderRecentActivity();
    }

    // ── Public API ─────────────────────────────────────────────────────────
    window._suiteHomeUpdate = update;

    // ── Watch for panel activation ─────────────────────────────────────────
    function watchPanel() {
        const panel = document.getElementById('suite-home-panel');
        if (!panel) { setTimeout(watchPanel, 300); return; }

        function check() {
            if (panel.classList.contains('active') && !panel.querySelector('.partial-loading')) {
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
