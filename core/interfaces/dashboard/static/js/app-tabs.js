'use strict';

/**
 * Aethvion App Tab System  (app-tabs.js)
 * ───────────────────────────────────────
 * Manages the top tab bar that lets users open Aethvion apps inside the
 * main dashboard window without losing any app state.
 *
 * Key design rules
 * ────────────────
 * • Each app gets ONE iframe created on first open and NEVER destroyed until
 *   the tab is explicitly closed.  Tab switching only toggles CSS display.
 * • The iframe src is NOT set immediately — a health-check polls the target
 *   URL until the server responds, then sets src.  This gives a proper
 *   "Starting…" spinner instead of a browser connection-refused error page.
 * • The Nexus tab is permanent and cannot be closed.
 *
 * Public API (window.ATB)
 * ───────────────────────
 *   ATB.openApp(appId)      – open (or focus) an app by id
 *   ATB.switchTo(panelId)   – switch the visible panel by DOM id
 *   ATB.retryApp(appId)     – tear down and rebuild a failed app tab
 *   ATB.refreshPorts()      – re-fetch ports from /api/system/ports
 */
const ATB = (() => {

    // ── App registry ──────────────────────────────────────────────────────────
    // portKey must match the name used in PortManager.bind_port() on the server.
    const APPS = [
        { id: 'code',         label: 'Code IDE',      emoji: '💻', port: 8083, portKey: 'Aethvion Code IDE'     },
        { id: 'hardwareinfo', label: 'Hardware Info',  emoji: '🖥️', port: 8084, portKey: 'Aethvion Hardware Info' },
        { id: 'vtuber',       label: 'VTuber',         emoji: '🎭', port: 8081, portKey: 'VTuber Engine'         },
        { id: 'audio',        label: 'Audio Studio',   emoji: '🎙️', port: 8085, portKey: 'Aethvion Audio'        },
        { id: 'photo',        label: 'Photo Studio',   emoji: '🎨', port: 8086, portKey: 'Aethvion Photo'        },
        { id: 'finance',      label: 'Finance',        emoji: '💰', port: 8087, portKey: 'Aethvion Finance'      },
        { id: 'tracking',     label: 'Tracking',       emoji: '📡', port: 8082, portKey: 'Aethvion Tracking'     },
        { id: 'driveinfo',    label: 'Drive Info',     emoji: '💿', port: 8088, portKey: 'Aethvion Drive Info'   },
    ];

    const NEXUS_PANEL = 'panel-nexus';
    let _active = NEXUS_PANEL;

    // ── Dynamic port discovery ────────────────────────────────────────────────
    async function refreshPorts() {
        try {
            const res = await fetch('/api/system/ports');
            if (!res.ok) return;
            const raw = await res.json();
            // raw = { "8083": "Aethvion Code IDE", ... }
            const nameToPort = {};
            Object.entries(raw).forEach(([port, name]) => {
                nameToPort[name] = parseInt(port, 10);
            });
            APPS.forEach(app => {
                if (app.portKey && nameToPort[app.portKey]) {
                    app.port = nameToPort[app.portKey];
                }
            });
        } catch (_) { /* ignore — defaults remain */ }
    }

    // ── Tab switching ─────────────────────────────────────────────────────────
    function switchTo(panelId) {
        if (panelId === _active) return;

        // Hide the currently active panel
        const prev = document.getElementById(_active);
        if (prev) prev.style.display = 'none';

        // Show the target panel
        const next = document.getElementById(panelId);
        if (!next) {
            // Target panel doesn't exist — fall back to nexus
            const nexus = document.getElementById(NEXUS_PANEL);
            if (nexus) nexus.style.display = 'flex';
            _active = NEXUS_PANEL;
            document.querySelectorAll('.atb-tab').forEach(t =>
                t.classList.toggle('atb-tab--active', t.dataset.panel === NEXUS_PANEL)
            );
            return;
        }

        // Nexus uses flex-column layout; all iframe panels use block
        next.style.display = panelId === NEXUS_PANEL ? 'flex' : 'block';

        document.querySelectorAll('.atb-tab').forEach(t =>
            t.classList.toggle('atb-tab--active', t.dataset.panel === panelId)
        );

        _active = panelId;
        _refreshMenuOpenStates();
    }

    // ── Open an app ───────────────────────────────────────────────────────────
    async function openApp(appOrId) {
        await refreshPorts();

        const app = typeof appOrId === 'string'
            ? APPS.find(a => a.id === appOrId)
            : appOrId;
        if (!app) return;

        const panelId = `panel-app-${app.id}`;

        // Already open → just switch to it
        if (document.getElementById(panelId)) {
            switchTo(panelId);
            return;
        }

        // Build panel + tab, then switch
        const panel = _buildPanel(app, panelId);
        document.body.appendChild(panel);

        const tab = _buildTab(app, panelId);
        document.getElementById('atb-tabs').appendChild(tab);

        switchTo(panelId);
    }

    // ── Health-check helper ───────────────────────────────────────────────────
    // Tries a no-cors HEAD request; returns true if the server responds with
    // anything (even a 404), false if the connection is refused / times out.
    function _fetchHead(url, timeoutMs) {
        return new Promise(resolve => {
            const ctrl  = new AbortController();
            const timer = setTimeout(() => { ctrl.abort(); resolve(false); }, timeoutMs);
            fetch(url, { method: 'HEAD', mode: 'no-cors', signal: ctrl.signal })
                .then(() => { clearTimeout(timer); resolve(true);  })
                .catch(() => { clearTimeout(timer); resolve(false); });
        });
    }

    // ── Wait for server, then load iframe ─────────────────────────────────────
    async function _waitAndLoad(iframe, baseUrl, loadingEl, app, panelId) {
        const MAX_WAIT  = 90_000;  // 90 s total
        const INTERVAL  = 1_500;   // poll every 1.5 s
        const start     = Date.now();
        let   attempt   = 0;

        while (Date.now() - start < MAX_WAIT) {
            const hint = loadingEl.querySelector('.app-iframe-hint');

            if (hint) {
                const elapsed = Math.round((Date.now() - start) / 1000);
                hint.textContent = attempt === 0
                    ? 'Waiting for server to come online…'
                    : `Waiting for server… (${elapsed}s elapsed)`;
            }

            const up = await _fetchHead(baseUrl, 1200);

            if (up) {
                // Server is up — re-fetch ports so we use the correct bound port
                await refreshPorts();
                const appNow  = APPS.find(a => `panel-app-${a.id}` === panelId);
                const finalUrl = appNow ? `http://localhost:${appNow.port}` : baseUrl;
                iframe.src = finalUrl;
                return;  // iframe load event takes over from here
            }

            attempt++;
            await new Promise(r => setTimeout(r, INTERVAL));
        }

        // Give up — show error with retry button
        _showError(loadingEl, app);
    }

    // ── Build iframe panel ────────────────────────────────────────────────────
    function _buildPanel(app, panelId) {
        const url    = `http://localhost:${app.port}`;
        const loadId = `${panelId}-loading`;
        const frmId  = `${panelId}-iframe`;

        const panel = document.createElement('div');
        panel.id    = panelId;
        panel.className = 'app-panel app-iframe-panel';
        panel.style.display = 'none';

        // ── Loading overlay ───────────────────────────────────────────────────
        const loadingEl = document.createElement('div');
        loadingEl.id        = loadId;
        loadingEl.className = 'app-iframe-loading';
        loadingEl.innerHTML = `
            <div class="app-iframe-spinner"></div>
            <p>Starting <strong>${app.label}</strong>…</p>
            <p class="app-iframe-port">${url}</p>
            <p class="app-iframe-hint">Waiting for server to come online…</p>`;

        // ── iframe — src intentionally NOT set yet ────────────────────────────
        const iframe = document.createElement('iframe');
        iframe.id    = frmId;
        iframe.title = app.label;
        iframe.allowFullscreen = true;
        Object.assign(iframe.style, {
            display:  'none',
            width:    '100%',
            height:   '100%',
            border:   'none',
            position: 'absolute',
            inset:    '0',
        });

        // Wire load event BEFORE setting src (avoids missing early-fire)
        iframe.addEventListener('load', () => {
            loadingEl.style.display = 'none';
            iframe.style.display    = 'block';
        });

        panel.appendChild(loadingEl);
        panel.appendChild(iframe);

        // Start health-check loop; sets iframe.src once the server is ready
        _waitAndLoad(iframe, url, loadingEl, app, panelId);

        return panel;
    }

    // ── Error state ───────────────────────────────────────────────────────────
    function _showError(loadingEl, app) {
        loadingEl.innerHTML = `
            <div class="app-iframe-error-icon">⚠️</div>
            <p class="app-iframe-error">Could not connect to <strong>${app.label}</strong></p>
            <p class="app-iframe-error-msg">
                Server did not respond on port ${app.port}.<br>
                Make sure the app server is running, then click Retry.
            </p>
            <button class="app-iframe-retry-btn"
                    onclick="ATB.retryApp('${app.id}')">
                ↺ Retry
            </button>`;
    }

    // ── Retry: tear down and rebuild ──────────────────────────────────────────
    function retryApp(appId) {
        const app     = APPS.find(a => a.id === appId);
        const panelId = `panel-app-${appId}`;
        const tabEl   = document.querySelector(`[data-panel="${panelId}"]`);
        const panelEl = document.getElementById(panelId);

        // Switch away before removing
        if (_active === panelId) switchTo(NEXUS_PANEL);

        tabEl?.remove();
        panelEl?.remove();

        if (app) openApp(app);
    }

    // ── Build tab button ──────────────────────────────────────────────────────
    function _buildTab(app, panelId) {
        const tab     = document.createElement('button');
        tab.className = 'atb-tab';
        tab.dataset.panel = panelId;
        tab.setAttribute('title', app.label);
        tab.innerHTML = `
            <span class="atb-tab-emoji">${app.emoji}</span>
            <span class="atb-tab-label">${app.label}</span>
            <span class="atb-tab-close" title="Close tab">✕</span>`;

        tab.addEventListener('click', e => {
            if (!e.target.classList.contains('atb-tab-close')) {
                switchTo(panelId);
            }
        });

        tab.querySelector('.atb-tab-close').addEventListener('click', e => {
            e.stopPropagation();
            _closeTab(panelId, tab);
        });

        return tab;
    }

    // ── Close tab ─────────────────────────────────────────────────────────────
    function _closeTab(panelId, tabEl) {
        // Switch FIRST (while _active === panelId so switchTo guard passes),
        // THEN remove the panel.  Previously _active was pre-set which caused
        // switchTo to short-circuit and left a black screen.
        if (_active === panelId) {
            switchTo(NEXUS_PANEL);
        }
        tabEl.remove();
        document.getElementById(panelId)?.remove();
        _refreshMenuOpenStates();
    }

    // ── Apps dropdown ─────────────────────────────────────────────────────────
    function _buildAppsMenu() {
        const menu = document.getElementById('atb-apps-menu');
        if (!menu) return;
        menu.innerHTML = `<div class="atb-apps-menu-title">Aethvion Apps</div>`;

        APPS.forEach(app => {
            const isOpen = !!document.getElementById(`panel-app-${app.id}`);
            const btn    = document.createElement('button');
            btn.className = `atb-app-item${isOpen ? ' atb-app-item--open' : ''}`;
            btn.dataset.appId = app.id;
            btn.innerHTML = `
                <span class="atb-app-emoji">${app.emoji}</span>
                <span class="atb-app-name">${app.label}</span>
                <span class="atb-app-port">:${app.port}</span>
                <span class="atb-app-checkmark">✓</span>`;
            btn.addEventListener('click', () => {
                openApp(app);
                _closeMenu();
            });
            menu.appendChild(btn);
        });
    }

    function _refreshMenuOpenStates() {
        document.querySelectorAll('.atb-app-item').forEach(item => {
            const id     = item.dataset.appId;
            const isOpen = !!document.getElementById(`panel-app-${id}`);
            item.classList.toggle('atb-app-item--open', isOpen);
        });
    }

    function _openMenu() {
        refreshPorts().then(() => _buildAppsMenu());
        document.getElementById('atb-apps-menu')?.classList.add('open');
        document.getElementById('atb-apps-btn')?.classList.add('open');
    }
    function _closeMenu() {
        document.getElementById('atb-apps-menu')?.classList.remove('open');
        document.getElementById('atb-apps-btn')?.classList.remove('open');
    }
    function _toggleMenu() {
        const open = document.getElementById('atb-apps-menu')?.classList.contains('open');
        open ? _closeMenu() : _openMenu();
    }

    // ── Suite page status dots ────────────────────────────────────────────────
    // Polls /api/system/ports every 5 s and updates the coloured dots on the
    // Suite Home app cards as well as the running-count label.
    async function _updateSuiteStatus() {
        try {
            const res = await fetch('/api/system/ports');
            if (!res.ok) return;
            const raw = await res.json();  // { "8083": "Aethvion Code IDE", ... }

            const portByName = {};
            Object.entries(raw).forEach(([port, name]) => { portByName[name] = port; });

            let runCount = 0;

            APPS.forEach(app => {
                const running    = app.portKey in portByName;
                const actualPort = portByName[app.portKey];
                if (running) {
                    runCount++;
                    app.port = parseInt(actualPort, 10);   // keep ATB in sync
                }

                // Card status dot
                const dot = document.getElementById(`sac-status-${app.id}`);
                if (dot) {
                    dot.className = `sac-status sac-status--${running ? 'running' : 'offline'}`;
                    dot.title     = running
                        ? `Running on :${actualPort}`
                        : 'Not running';
                }

                // ATB menu port labels
                const menuPort = document.querySelector(
                    `[data-app-id="${app.id}"] .atb-app-port`
                );
                if (menuPort) menuPort.textContent = `:${app.port}`;
            });

            // Running-count label in suite section header
            const countEl = document.getElementById('suite-running-count');
            if (countEl) {
                countEl.textContent = runCount > 0
                    ? `${runCount} / ${APPS.length} servers running`
                    : 'no servers running — click a card to queue';
                countEl.className   = `suite-port-note${runCount > 0 ? ' suite-port-note--live' : ''}`;
            }

            // Hero server pill
            const heroEl = document.getElementById('hub-servers-label');
            if (heroEl) {
                heroEl.textContent = runCount > 0
                    ? `${runCount} / ${APPS.length} apps online`
                    : 'no apps running';
            }
            const heroDot = document.getElementById('hub-servers-dot');
            if (heroDot) {
                heroDot.className = `hub-status-dot${runCount > 0 ? ' hub-status-dot--live' : ''}`;
            }
        } catch (_) { /* ignore network errors */ }
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        // Nexus tab click
        document.querySelector('[data-panel="panel-nexus"]')
            ?.addEventListener('click', () => switchTo(NEXUS_PANEL));

        // Apps button
        document.getElementById('atb-apps-btn')
            ?.addEventListener('click', e => { e.stopPropagation(); _toggleMenu(); });

        // Prevent click-inside from closing the menu
        document.getElementById('atb-apps-menu')
            ?.addEventListener('click', e => e.stopPropagation());

        // Click outside closes the menu
        document.addEventListener('click', _closeMenu);

        // Escape closes the menu
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') _closeMenu();
        });

        // Initial port refresh
        refreshPorts();

        // Suite status dots — initial + polling
        _updateSuiteStatus();
        setInterval(_updateSuiteStatus, 5_000);
    }

    // ── Public surface ────────────────────────────────────────────────────────
    return { init, openApp, switchTo, retryApp, refreshPorts };

})();

document.addEventListener('DOMContentLoaded', () => ATB.init());
