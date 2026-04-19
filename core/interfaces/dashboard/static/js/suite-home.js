/**
 * suite-home.js — Mission Control: informational home page logic
 *
 * Renders:
 *   - Hero subtitle + profile pill (profile-aware)
 *   - CTA buttons (preset-aware)
 *   - System Snapshot stats (folder count, tab count, version)
 *   - Layout Overview (profile's folders + tabs as interactive cards)
 *
 * Called by sidebar-manager.js via window._suiteHomeUpdate()
 * whenever the active profile changes.
 */

(function () {
    'use strict';

    const STORAGE_KEY = 'sidebar_profiles_v1';

    // ── Tab metadata (mirrors sidebar-manager.js TABS) ────────────────────────
    const TAB_INFO = {
        'suite-home':        { label: 'Home',              icon: 'fas fa-house' },
        'chat':              { label: 'Chat',              icon: 'fas fa-comments' },
        'agents':            { label: 'Agents',            icon: 'fas fa-robot' },
        'agent-corp':        { label: 'Agent Corp',        icon: 'fas fa-building' },
        'schedule':          { label: 'Schedule',          icon: 'fas fa-calendar-alt' },
        'photo':             { label: 'Photo',             icon: 'fas fa-image' },
        'audio':             { label: 'Audio',             icon: 'fas fa-microphone' },
        'advaiconv':         { label: 'Adv. AI Conv.',     icon: 'fas fa-flask' },
        'researchboard':     { label: 'Directors',         icon: 'fas fa-balance-scale' },
        'arena':             { label: 'Arena',             icon: 'fas fa-shield-halved' },
        'aiconv':            { label: 'AI Conv.',          icon: 'fas fa-masks-theater' },
        'explained':         { label: 'Explained',         icon: 'fas fa-lightbulb' },
        'misaka-cipher':     { label: 'Misaka Cipher',     icon: 'fas fa-wand-magic-sparkles' },
        'axiom':             { label: 'Axiom',             icon: 'fas fa-atom' },
        'lyra':              { label: 'Lyra',              icon: 'fas fa-music' },
        'companion-creator': { label: 'Create Companion',  icon: 'fas fa-plus-circle' },
        'games-center':      { label: 'Games Center',      icon: 'fas fa-gamepad' },
        'memory':            { label: 'Memory',            icon: 'fas fa-book' },
        'persistent-memory': { label: 'Persistent',        icon: 'fas fa-brain' },
        'sched-overview':    { label: 'Scheduled',         icon: 'fas fa-calendar-check' },
        'output':            { label: 'Output',            icon: 'fas fa-upload' },
        'screenshots':       { label: 'Gallery',           icon: 'fas fa-camera-retro' },
        'camera':            { label: 'Camera',            icon: 'fas fa-camera' },
        'uploads':           { label: 'Uploads',           icon: 'fas fa-folder' },
        'local-models':      { label: 'Text & Chat',       icon: 'fas fa-microchip' },
        'image-models':      { label: 'Image Models',      icon: 'fas fa-mountain-sun' },
        'audio-models':      { label: 'Audio & Speech',    icon: 'fas fa-volume-high' },
        'api-providers':     { label: 'API Providers',     icon: 'fas fa-plug' },
        'logs':              { label: 'Logs',              icon: 'fas fa-scroll' },
        'documentation':     { label: 'Docs',              icon: 'fas fa-book-open' },
        'usage':             { label: 'Usage',             icon: 'fas fa-chart-bar' },
        'status':            { label: 'Status',            icon: 'fas fa-traffic-light' },
        'ports':             { label: 'Ports',             icon: 'fas fa-plug' },
        'settings':          { label: 'Settings',          icon: 'fas fa-gear' },
        'version':           { label: 'Version',           icon: 'fas fa-code-branch' },
    };

    // ── Per-preset hero content ───────────────────────────────────────────────
    const PRESET_INFO = {
        professional: {
            subtitle: 'Professional workspace active — agents, scheduling, and system management at your fingertips.',
            ctas: [
                { label: 'Open Workspace', icon: 'fas fa-briefcase', tab: 'chat',   mode: 'ai' },
                { label: 'Launch Agents',  icon: 'fas fa-robot',     tab: 'agents', mode: 'ai' },
            ],
        },
        creative: {
            subtitle: 'Creative studio active — photo, audio, and AI tools ready for your next project.',
            ctas: [
                { label: 'Open Studio', icon: 'fas fa-palette',  tab: 'photo', mode: 'ai' },
                { label: 'Start Chat',  icon: 'fas fa-comments', tab: 'chat',  mode: 'ai' },
            ],
        },
        researcher: {
            subtitle: 'Research environment loaded — deep analysis, model comparisons, and knowledge tools ready.',
            ctas: [
                { label: 'Start Research', icon: 'fas fa-microscope',    tab: 'advaiconv', mode: 'ai' },
                { label: 'Open Arena',     icon: 'fas fa-shield-halved', tab: 'arena',     mode: 'ai' },
            ],
        },
        companion: {
            subtitle: 'Companion Hub active — your AI companions are ready and waiting.',
            ctas: [
                { label: 'Open Companions', icon: 'fas fa-heart',   tab: 'misaka-cipher', mode: 'ai' },
                { label: 'Games Center',    icon: 'fas fa-gamepad', tab: 'games-center',  mode: 'ai' },
            ],
        },
        full: {
            subtitle: 'Full suite access — every tool and every tab is available.',
            ctas: [
                { label: 'Open Workspace', icon: 'fas fa-layer-group', tab: 'chat',   mode: 'ai' },
                { label: 'Launch Agents',  icon: 'fas fa-robot',       tab: 'agents', mode: 'ai' },
            ],
        },
        custom: {
            subtitle: 'Your custom layout is active — build and tailor your perfect workspace.',
            ctas: [
                { label: 'Open AI',   icon: 'fas fa-brain',  tab: 'chat', mode: 'ai' },
                { label: 'Customize', icon: 'fas fa-sliders', tab: null,  mode: null },
            ],
        },
    };

    const DEFAULT_INFO = {
        subtitle: 'Welcome to your advanced AI operations center. Aethvion Suite is designed to orchestrate complex tasks, manage local models, and provide a unified interface for all your AI needs.',
        ctas: [
            { label: 'Quick Start Chat', icon: 'fas fa-rocket',       tab: 'chat',          mode: 'ai' },
            { label: 'Read Overview',    icon: 'fas fa-book-open',    tab: 'documentation', mode: null },
        ],
    };

    // ── Read active profile ───────────────────────────────────────────────────
    function getActiveProfile() {
        try {
            const data = JSON.parse(localStorage.getItem(STORAGE_KEY));
            if (!data?.profiles || !data.activeProfile) return null;
            return { _id: data.activeProfile, ...data.profiles[data.activeProfile] };
        } catch (_) { return null; }
    }

    // ── Main update (called on profile switch + panel open) ───────────────────
    function update() {
        const profile = getActiveProfile();
        if (!profile) return;

        const info = PRESET_INFO[profile.presetId] || DEFAULT_INFO;

        updateProfilePill(profile.name);
        updateSubtitle(info.subtitle);
        updateCTAs(info.ctas);
        updateBadge(profile.name);
        updateSnapshot(profile);
        renderRecentActivity();
    }

    // ── Hero updates ──────────────────────────────────────────────────────────
    function updateProfilePill(name) {
        const el = document.getElementById('sh-profile-name');
        if (el) el.textContent = name;
    }

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
            if (c2.tab) {
                secondary.onclick = () => { if (c2.mode) window.setDashboardMode?.(c2.mode); window.switchMainTab?.(c2.tab); };
            } else if (c2.label === 'Customize') {
                secondary.onclick = () => document.getElementById('cust-toggle')?.click();
            }
        }
    }

    function updateBadge(name) {
        const el = document.getElementById('lo-profile-badge');
        if (el) el.textContent = name;
    }

    // ── System Snapshot stats ─────────────────────────────────────────────────
    function updateSnapshot(profile) {
        // Count enabled tabs across the whole profile
        const order = profile.order || [];
        let tabCount    = 0;
        let folderCount = 0;

        for (const entry of order) {
            if (entry.type === 'tab') {
                if (entry.id === 'suite-home') continue;
                if (!profile.hidden?.[entry.id]) tabCount++;
            } else if (entry.type === 'folder') {
                const visible = (entry.children || []).filter(id => !profile.hidden?.[id]);
                if (visible.length > 0) { folderCount++; tabCount += visible.length; }
            }
        }

        setSnap('snap-folders-val', folderCount > 0 ? String(folderCount) : '—');
        setSnap('snap-tabs-val',    tabCount    > 0 ? String(tabCount)    : '—');

        // Version — try the badge that the server populates
        const vBadge = document.getElementById('suite-hero-version');
        const vText = vBadge?.textContent?.replace('Version ', '').trim();
        setSnap('snap-version-val', vText && vText !== '—' ? vText : '—');

        // Servers — read the existing label
        pollServersLabel();
    }

    function setSnap(id, val) {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    function pollServersLabel() {
        // The hub-servers-label is populated by core.js; poll it briefly
        let tries = 0;
        const ticker = setInterval(() => {
            const label = document.getElementById('hub-servers-label')?.textContent || '';
            const match  = label.match(/(\d+)\s*\/\s*(\d+)/);
            if (match) {
                setSnap('snap-servers-val', `${match[1]}/${match[2]}`);
                clearInterval(ticker);
            } else if (label && !label.includes('checking') && !label.includes('…')) {
                // Single word e.g. "offline"
                setSnap('snap-servers-val', label.split(' ').slice(0, 2).join(' '));
                clearInterval(ticker);
            }
            if (++tries > 20) clearInterval(ticker); // give up after ~4s
        }, 200);
    }

    function esc(s) {
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
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

    // ── Recent Activity ───────────────────────────────────────────────────────
    async function renderRecentActivity() {
        const container = document.getElementById('sh-recent-list');
        if (!container) return;

        let threadArr = [];
        try {
            // Check global store first
            if (window.threads && Object.keys(window.threads).length > 0) {
                threadArr = Object.values(window.threads);
            } else {
                // Fetch if not loaded (e.g. fresh home page load)
                const res = await fetch('/api/tasks/threads');
                if (res.ok) {
                    const data = await res.json();
                    threadArr = data.threads || [];
                }
            }
        } catch (e) { console.error("Home: Failed to fetch recent activity", e); }

        if (!threadArr.length) {
            container.innerHTML = `
                <div class="ae-empty" style="min-height:140px;padding:2rem;">
                    <div class="ae-empty-icon"><i class="fas fa-clock-rotate-left"></i></div>
                    <div class="ae-empty-title">No recent activity</div>
                    <div class="ae-empty-desc">Start a conversation in Chat to see your activity here.</div>
                </div>`;
            return;
        }

        // Sort by updated_at desc
        const sorted = threadArr
            .filter(t => !t.id.startsWith('agents-')) // skip specific agent internal threads
            .sort((a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at));

        const recent = sorted.slice(0, 3);
        container.innerHTML = '';

        recent.forEach(t => {
            const row = document.createElement('div');
            row.className = 'sh-recent-row';
            row.title = `Switch to ${t.title}`;

            const preview = (t.last_message || 'No messages yet').replace(/<[^>]+>/g, '').slice(0, 70);
            const time    = relativeTime(t.updated_at || t.created_at);

            row.innerHTML = `
                <div class="sh-rr-icon"><i class="fas fa-comment-dots"></i></div>
                <div class="sh-rr-body">
                    <div class="sh-rr-top">
                        <span class="sh-rr-name">${esc(t.title)}</span>
                        <span class="sh-rr-time">${time}</span>
                    </div>
                    <div class="sh-rr-preview">${esc(preview)}</div>
                </div>
                <i class="fas fa-chevron-right sh-rr-arrow"></i>
            `;

            row.addEventListener('click', () => {
                window.setDashboardMode?.('ai');
                window.switchMainTab?.('chat');
                // We need to wait a tiny bit for the tab to switch before calling switchThread
                setTimeout(() => {
                    if (typeof window.switchThread === 'function') {
                        window.switchThread(t.id);
                    }
                }, 50);
            });

            container.appendChild(row);
        });
    }

    // ── Public API ────────────────────────────────────────────────────────────
    window._suiteHomeUpdate = update;

    // ── Watch for the panel to load ───────────────────────────────────────────
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
