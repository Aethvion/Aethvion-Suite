/**
 * Aethvion Suite — Sidebar Navigation (Drill-down edition)
 *
 * Two-level navigation:
 *   Root  → category rows (Workspace, Research, …)
 *   Drill → back button + tabs for that category
 *
 * No profiles, no customization layer, no drag-drop.
 * State persisted to localStorage key 'snav_v1'.
 */

(function () {
    'use strict';

    // ── Tab registry ───────────────────────────────────────────────────────
    const TABS = {
        'suite-home':        { label: 'Home',           icon: 'fas fa-house' },
        'agent-corp':        { label: 'Agent Corp',     icon: 'fas fa-building' },
        'schedule':          { label: 'Schedule',       icon: 'fas fa-calendar-alt' },
        'photo':             { label: 'Photo',          icon: 'fas fa-image' },
        'audio':             { label: 'Audio',          icon: 'fas fa-microphone' },
        '3d-gen':            { label: '3D Workspace',   icon: 'fas fa-vector-square' },
        'advaiconv':         { label: 'Adv. AI Conv.',  icon: 'fas fa-flask' },
        'researchboard':     { label: 'Directors',      icon: 'fas fa-balance-scale' },
        'arena':             { label: 'Arena',          icon: 'fas fa-shield-halved' },
        'aiconv':            { label: 'AI Conv.',       icon: 'fas fa-masks-theater' },
        'explained':         { label: 'Explained',      icon: 'fas fa-lightbulb' },
        'memory':            { label: 'Memory',         icon: 'fas fa-book' },
        'persistent-memory': { label: 'Persistent',     icon: 'fas fa-brain' },
        'sched-overview':    { label: 'Scheduled',      icon: 'fas fa-calendar-check' },
        'output':            { label: 'Output',         icon: 'fas fa-upload' },
        'screenshots':       { label: 'Gallery',        icon: 'fas fa-camera-retro' },
        'camera':            { label: 'Camera',         icon: 'fas fa-camera' },
        'uploads':           { label: 'Uploads',        icon: 'fas fa-folder' },
        'local-models':      { label: 'Text & Chat',    icon: 'fas fa-microchip' },
        'image-models':      { label: 'Image Models',   icon: 'fas fa-mountain-sun' },
        'audio-models':      { label: 'Audio & Speech', icon: 'fas fa-volume-high' },
        'api-providers':     { label: 'API Providers',  icon: 'fas fa-plug' },
        '3d-models':         { label: '3D Models',      icon: 'fas fa-cube' },
        'logs':              { label: 'Logs',            icon: 'fas fa-scroll' },
        'documentation':     { label: 'Docs',           icon: 'fas fa-book-open' },
        'usage':             { label: 'Usage',          icon: 'fas fa-chart-bar' },
        'status':            { label: 'Status',         icon: 'fas fa-traffic-light' },
        'ports':             { label: 'Ports',          icon: 'fas fa-ethernet' },
        'worldsim':          { label: 'WorldSim',       icon: 'fas fa-globe' },
    };

    // ── Category definitions ───────────────────────────────────────────────
    const CATEGORIES = [
        {
            id: 'workspace',
            label: 'Workspace',
            icon: 'fas fa-briefcase',
            tabs: ['agent-corp', 'schedule', 'photo', 'audio', '3d-gen'],
        },
        {
            id: 'research',
            label: 'Research',
            icon: 'fas fa-microscope',
            tabs: ['advaiconv', 'researchboard', 'arena', 'aiconv', 'explained'],
        },
        {
            id: 'memory',
            label: 'Memory',
            icon: 'fas fa-brain',
            tabs: ['memory', 'persistent-memory', 'sched-overview'],
        },
        {
            id: 'storage',
            label: 'Storage',
            icon: 'fas fa-folder-open',
            tabs: ['output', 'screenshots', 'camera', 'uploads'],
        },
        {
            id: 'model-hub',
            label: 'Model Hub',
            icon: 'fas fa-microchip',
            tabs: ['local-models', 'image-models', 'audio-models', 'api-providers', '3d-models'],
        },
        {
            id: 'system',
            label: 'System',
            icon: 'fas fa-server',
            tabs: ['logs', 'documentation', 'usage', 'status', 'ports'],
        },
        {
            id: 'experimental',
            label: 'Experimental',
            icon: 'fas fa-flask-vial',
            tabs: ['worldsim'],
        },
    ];

    // ── State ──────────────────────────────────────────────────────────────
    let _depth     = 'root';   // 'root' | 'category'
    let _activeCat = null;     // category id when drilled in
    let _activeTab = null;     // currently active tab id
    let _searching = false;

    // ── Helpers ────────────────────────────────────────────────────────────
    function esc(s) {
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function catForTab(tabId) {
        return CATEGORIES.find(c => c.tabs.includes(tabId)) || null;
    }

    // ── Render ─────────────────────────────────────────────────────────────
    function render(direction) {
        const container = document.getElementById('sidebar-tab-list');
        if (!container) return;

        const view = document.createElement('div');
        view.className = 'snav-view';
        if (direction === 'in')  view.classList.add('snav-slide-in');
        if (direction === 'out') view.classList.add('snav-slide-out');

        if (_depth === 'root') buildRoot(view);
        else                   buildCategory(view, _activeCat);

        container.innerHTML = '';
        container.appendChild(view);
    }

    function buildRoot(view) {
        // Home tab — always at the top
        view.appendChild(makeTabBtn('suite-home'));

        // Divider
        const div = document.createElement('div');
        div.className = 'snav-divider';
        view.appendChild(div);

        // Category rows
        CATEGORIES.forEach(cat => {
            const hasActive = _activeTab && cat.tabs.includes(_activeTab);
            const row = document.createElement('button');
            row.className = 'snav-cat-row' + (hasActive ? ' has-active' : '');
            row.dataset.catId = cat.id;
            row.title = cat.label;
            row.innerHTML =
                `<span class="snav-cat-icon"><i class="${esc(cat.icon)}"></i></span>` +
                `<span class="snav-cat-label">${esc(cat.label)}</span>` +
                (cat.tabs.length
                    ? `<i class="fas fa-chevron-right snav-cat-chevron"></i>`
                    : `<span class="snav-cat-badge">new</span>`);
            row.addEventListener('click', () => drillInto(cat.id));
            view.appendChild(row);
        });
    }

    function buildCategory(view, catId) {
        const cat = CATEGORIES.find(c => c.id === catId);
        if (!cat) { _depth = 'root'; render(); return; }

        // Back + title row
        const header = document.createElement('div');
        header.className = 'snav-cat-header';
        header.innerHTML =
            `<button class="snav-back-btn" title="Back"><i class="fas fa-arrow-left"></i></button>` +
            `<i class="${esc(cat.icon)} snav-cat-header-icon"></i>` +
            `<span class="snav-cat-header-label">${esc(cat.label)}</span>`;
        header.querySelector('.snav-back-btn').addEventListener('click', goBack);
        view.appendChild(header);

        const sep = document.createElement('div');
        sep.className = 'snav-sep';
        view.appendChild(sep);

        if (cat.tabs.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'snav-empty';
            empty.innerHTML =
                `<i class="fas fa-flask-vial"></i>` +
                `<span>No features yet</span>` +
                `<span class="snav-empty-sub">New experimental features will appear here</span>`;
            view.appendChild(empty);
            return;
        }

        cat.tabs.forEach(tabId => view.appendChild(makeTabBtn(tabId)));
    }

    function makeTabBtn(tabId) {
        const tab = TABS[tabId];
        if (!tab) return document.createDocumentFragment();
        const btn = document.createElement('button');
        btn.className = 'main-tab mode-home' + (_activeTab === tabId ? ' active' : '');
        btn.dataset.maintab = tabId;
        btn.dataset.tooltip  = tab.label;
        btn.innerHTML =
            `<span class="tab-icon"><i class="${esc(tab.icon)}"></i></span>` +
            `<span class="tab-label">${esc(tab.label)}</span>`;
        btn.addEventListener('click', () => activateTab(tabId));
        return btn;
    }

    // ── Navigation ─────────────────────────────────────────────────────────
    function drillInto(catId) {
        _depth = 'category';
        _activeCat = catId;
        saveState();
        render('in');
    }

    function goBack() {
        _depth = 'root';
        _activeCat = null;
        saveState();
        render('out');
    }

    function activateTab(tabId) {
        _activeTab = tabId;
        if (typeof switchMainTab === 'function') switchMainTab(tabId);

        if (_searching) {
            _searching = false;
            const input = document.getElementById('sidebar-search-input');
            if (input) {
                input.value = '';
                input.dispatchEvent(new Event('input', { bubbles: true }));
            }
            const cat = catForTab(tabId);
            if (cat) {
                _depth = 'category';
                _activeCat = cat.id;
            } else {
                _depth = 'root';
                _activeCat = null;
            }
            saveState();
            render();
            return;
        }

        // Update active class on visible tab buttons (core.js also does this globally)
        document.querySelectorAll('#sidebar-tab-list .main-tab[data-maintab]').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.maintab === tabId);
        });
        // Update category row highlight at root
        document.querySelectorAll('.snav-cat-row').forEach(row => {
            const cat = CATEGORIES.find(c => c.id === row.dataset.catId);
            row.classList.toggle('has-active', !!(cat && cat.tabs.includes(tabId)));
        });
    }

    // ── Public API (called by core.js switchMainTab) ───────────────────────
    window._sidebarNav = {
        getTotalTabCount() {
            return CATEGORIES.reduce((sum, c) => sum + c.tabs.length, 0);
        },
        setActiveTab(tabId) {
            _activeTab = tabId;
            document.querySelectorAll('#sidebar-tab-list .main-tab[data-maintab]').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.maintab === tabId);
            });
            document.querySelectorAll('.snav-cat-row').forEach(row => {
                const cat = CATEGORIES.find(c => c.id === row.dataset.catId);
                row.classList.toggle('has-active', !!(cat && cat.tabs.includes(tabId)));
            });
        },
    };

    // ── Search ─────────────────────────────────────────────────────────────
    // When the user types, temporarily show all tabs so core.js's applyFilter
    // can do text matching. Clearing search restores the navigation state.
    function setupSearch() {
        const input   = document.getElementById('sidebar-search-input');
        const clearEl = document.getElementById('sidebar-search-clear');
        if (!input) return;

        input.addEventListener('input', () => {
            const q = input.value.trim();
            if (q) {
                if (!_searching) { _searching = true; showAllTabsForSearch(); }
            } else {
                if (_searching) { _searching = false; render(); }
            }
        }, true); // capture — runs before core.js bubble listener

        if (clearEl) {
            clearEl.addEventListener('click', () => {
                if (_searching) { _searching = false; render(); }
            });
        }
    }

    function showAllTabsForSearch() {
        const container = document.getElementById('sidebar-tab-list');
        if (!container) return;
        const view = document.createElement('div');
        view.className = 'snav-view';
        // Render every tab across every category so core.js text filter can work
        CATEGORIES.forEach(cat => {
            cat.tabs.forEach(tabId => view.appendChild(makeTabBtn(tabId)));
        });
        container.innerHTML = '';
        container.appendChild(view);
    }

    // ── State persistence ──────────────────────────────────────────────────
    const STATE_KEY = 'snav_v1';

    function saveState() {
        try {
            localStorage.setItem(STATE_KEY, JSON.stringify({ depth: _depth, cat: _activeCat }));
        } catch (_) {}
    }

    function loadState() {
        try {
            const s = JSON.parse(localStorage.getItem(STATE_KEY) || '{}');
            _depth = s.depth === 'category' ? 'category' : 'root';
            _activeCat = s.cat || null;
            if (_depth === 'category' && !CATEGORIES.find(c => c.id === _activeCat)) {
                _depth = 'root'; _activeCat = null;
            }
        } catch (_) {}

        // Restore active tab from the preference core.js saves
        try {
            const raw = localStorage.getItem('aethvion_preferences') || '{}';
            const prefs = JSON.parse(raw);
            _activeTab = prefs['active_tab_home'] || prefs['active_tab_ai'] || null;
        } catch (_) {}
    }

    // ── Init ───────────────────────────────────────────────────────────────
    function init() {
        loadState();
        render();
        setupSearch();
        document.dispatchEvent(new CustomEvent('sidebar-ready'));
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        setTimeout(init, 0);
    }
})();
