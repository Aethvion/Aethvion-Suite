'use strict';
console.log('[ATB] app-tabs.js loaded (v10.0.0)');

/**
 * Aethvion App Tab System  (app-tabs.js)
 * ───────────────────────────────────────
 * Manages the top tab bar that lets users open Aethvion apps inside the
 * main dashboard window without losing any app state.
 *
 * Key design rules
 * ────────────────
 * • Each app gets ONE iframe, created on first open and never destroyed until
 *   the tab is explicitly closed.  Tab switching only toggles CSS display.
 *
 * • Ports are FULLY DYNAMIC — no hardcoded ports anywhere.  The iframe src is
 *   only set once the app's portKey appears in the PortManager registry
 *   (/api/system/ports).  This prevents loading the wrong app if an expected
 *   port is occupied by something else.
 *
 * • The Nexus tab is permanent and cannot be closed.
 *
 * Public API (window.ATB)
 * ───────────────────────
 *   ATB.openApp(appId)      – open (or focus) an app by id
 *   ATB.switchTo(panelId)   – switch the visible panel by DOM id
 *   ATB.retryApp(appId)     – tear down and rebuild a failed app tab
 *   ATB.refreshPorts()      – re-fetch ports; returns { name → port } map
 */
const ATB = (() => {

    // ── App registry ──────────────────────────────────────────────────────────
    // portKey MUST match the name passed to PortManager.bind_port() on the
    // server side.  No hardcoded port numbers — the actual port is discovered
    // at runtime via the PortManager registry.
    // --- Running Services Logic ---
    const ServiceMonitor = {
        init() {
            this.btn = document.getElementById('atb-services-btn');
            this.wrapper = document.getElementById('atb-services-wrapper');
            this.menu = document.getElementById('atb-services-menu');
            this.list = document.getElementById('services-list-root');
            this.count = document.getElementById('active-services-count');

            if (!this.btn) return;

            this.btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.menu.classList.toggle('open');
                this.btn.classList.toggle('open');
            });

            document.addEventListener('click', () => {
                this.menu.classList.remove('open');
                this.btn.classList.remove('open');
            });

            this.startPolling();
        },

        async startPolling() {
            const poll = async () => {
                try {
                    const res = await fetch('/api/3d/active_services');
                    const services = await res.json();
                    this.updateUI(services);
                } catch (e) {
                    console.error('[ServiceMonitor] Poll failed:', e);
                }
            };
            poll();
            setInterval(poll, 5000);
        },

        updateUI(services) {
            this.wrapper.style.display = 'block';
            
            if (!services || services.length === 0) {
                this.list.innerHTML = '<div class="services-empty">No active neural models.</div>';
                this.count.textContent = '0';
                return;
            }

            this.count.textContent = services.length;
            this.list.innerHTML = '';

            services.forEach(svc => {
                const card = document.createElement('div');
                card.className = 'service-card';
                
                const statusClass = `status-${svc.status.toLowerCase()}`;
                const vramText = svc.vram_used ? `${svc.vram_used.toFixed(1)} GB / ${svc.vram_total.toFixed(1)} GB` : '0 GB / -- GB';

                card.innerHTML = `
                    <div class="service-row">
                        <span class="service-name">${svc.name}</span>
                        <span class="service-status ${statusClass}">${svc.status}</span>
                    </div>
                    <div class="service-row">
                        <div class="service-telemetry">
                            <span class="telemetry-vram"><i class="fas fa-memory"></i> ${vramText}</span>
                        </div>
                        <button class="service-stop-btn" onclick="ATB.stopService('${svc.id}')">Stop</button>
                    </div>
                `;
                this.list.appendChild(card);
            });
        }
    };

    const APPS = [
        { id: 'code',         label: 'Code IDE',      emoji: '💻', category: 'Professional Development', port: null, portKey: 'Aethvion Code IDE'     },
        { id: 'photo',        label: 'Photo Studio',   emoji: '🎨', category: 'Creative & Production',    port: null, portKey: 'Aethvion Photo'        },
        { id: 'audio',        label: 'Audio Studio',   emoji: '🎙️', category: 'Creative & Production',    port: null, portKey: 'Aethvion Audio'        },
        { id: 'vtuber',       label: 'VTuber',         emoji: '🎭', category: 'Streaming & Performance',  port: null, portKey: 'VTuber Engine'         },
        { id: 'tracking',     label: 'Tracking',       emoji: '📡', category: 'Streaming & Performance',  port: null, portKey: 'Aethvion Tracking'     },
        { id: 'hardwareinfo', label: 'Hardware Info',  emoji: '🖥️', category: 'System & Analytics',       port: null, portKey: 'Aethvion Hardware Info' },
        { id: 'linkmap',      label: 'LinkMap',        emoji: '🗺️', category: 'System & Analytics',       port: null, portKey: 'Aethvion LinkMap'      },
        { id: 'driveinfo',    label: 'Drive Info',     emoji: '💿', category: 'System & Analytics',       port: null, portKey: 'Aethvion Drive Info'   },
        { id: 'finance',      label: 'Finance',        emoji: '💰', category: 'Other',                    port: null, portKey: 'Aethvion Finance'      },
        { id: 'kanban',       label: 'Kanban',         emoji: '📋', category: 'Professional Development', port: null, portKey: 'Aethvion Kanban'       },
    ];

    const NEXUS_PANEL = 'panel-nexus';
    let _active = NEXUS_PANEL;

    // ── Dynamic port discovery ────────────────────────────────────────────────
    // Returns { "Aethvion Code IDE": 8083, ... } and updates APPS[].port.
    async function refreshPorts() {
        try {
            const res = await fetch('/api/system/ports');
            if (!res.ok) return {};
            const raw = await res.json();       // { "8083": "Aethvion Code IDE", ... }
            const nameToPort = {};
            Object.entries(raw).forEach(([port, name]) => {
                nameToPort[name] = parseInt(port, 10);
            });
            APPS.forEach(app => {
                if (app.portKey in nameToPort) {
                    app.port = nameToPort[app.portKey];
                }
            });
            return nameToPort;
        } catch (_) {
            return {};
        }
    }

    // ── Tab switching ─────────────────────────────────────────────────────────
    function switchTo(panelId) {
        if (panelId === _active) return;

        // Hide the currently active panel
        const prev = document.getElementById(_active);
        if (prev) prev.style.display = 'none';

        // Show the target panel; fall back to Nexus if it doesn't exist
        const next = document.getElementById(panelId);
        if (!next) {
            const nexus = document.getElementById(NEXUS_PANEL);
            if (nexus) nexus.style.display = 'flex';
            _active = NEXUS_PANEL;
            document.querySelectorAll('.atb-tab').forEach(t =>
                t.classList.toggle('atb-tab--active', t.dataset.panel === NEXUS_PANEL)
            );
            _refreshMenuOpenStates();
            return;
        }

        console.log(`[ATB] Switching to ${panelId}`);
        next.style.display = (panelId === NEXUS_PANEL) ? 'flex' : 'block';
        next.style.visibility = 'visible'; // Ensure visibility
        next.style.opacity = '1';

        document.querySelectorAll('.atb-tab').forEach(t =>
            t.classList.toggle('atb-tab--active', t.dataset.panel === panelId)
        );

        _active = panelId;
        _refreshMenuOpenStates();
    }

    // ── Open an app ───────────────────────────────────────────────────────────
    async function openApp(appOrId) {
        const app = typeof appOrId === 'string'
            ? APPS.find(a => a.id === appOrId)
            : appOrId;
        if (!app) return;

        const panelId = `panel-app-${app.id}`;

        // Already open → just focus it
        if (document.getElementById(panelId)) {
            switchTo(panelId);
            return;
        }

        // 1. Tell backend to start the service (async, don't block UI)
        fetch('/api/system/modules/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ module: app.id, action: 'run' })
        }).catch(err => console.error(`[ATB] Failed to start service for ${app.id}:`, err));

        const panel = _buildPanel(app, panelId);
        document.body.appendChild(panel);

        const tab = _buildTab(app, panelId);
        document.getElementById('atb-tabs').appendChild(tab);

        switchTo(panelId);
    }

    // ── Wait for the server to register its port, then load iframe ────────────
    // Polls /api/system/ports until the app's portKey appears.
    // This is identity-based (not port-based) so a different server running on
    // the expected port will never be loaded by mistake.
    async function _waitAndLoad(iframe, loadingEl, app, panelId) {
        const MAX_WAIT     = 90_000;   // 90 s total before showing error
        const POLL_INTERVAL = 1_500;   // check registry every 1.5 s
        const start        = Date.now();

        while (Date.now() - start < MAX_WAIT) {
            const elapsed = Math.round((Date.now() - start) / 1000);
            const hint = loadingEl.querySelector('.app-iframe-hint');
            if (hint) {
                hint.textContent = elapsed === 0
                    ? 'Waiting for server to register…'
                    : `Waiting for server… (${elapsed}s)`;
            }

            const nameToPort = await refreshPorts();
            console.log(`[ATB] refreshing ports for ${app.id}...`, nameToPort);

            if (app.portKey in nameToPort) {
                // ✓ Server has registered its port — now we know exactly where to go
                const port = nameToPort[app.portKey];
                console.log(`[ATB] Found port ${port} for ${app.id}. Loading iframe...`);
                // Append cache-buster to ensure the latest version is loaded
                const cb = Date.now();
                iframe.src = `http://localhost:${port}/?_cb=${cb}`;
                // iframe load event hides the spinner and shows the iframe
                return;
            }

            await new Promise(r => setTimeout(r, POLL_INTERVAL));
        }

        // Timed out — give up and show error
        _showError(loadingEl, app);
    }

    // ── Build iframe panel ────────────────────────────────────────────────────
    function _buildPanel(app, panelId) {
        const loadId = `${panelId}-loading`;
        const frmId  = `${panelId}-iframe`;

        const panel = document.createElement('div');
        panel.id    = panelId;
        panel.className = 'app-panel app-iframe-panel';
        panel.style.display = 'none';

        const loadingEl = document.createElement('div');
        loadingEl.id        = loadId;
        loadingEl.className = 'app-iframe-loading';
        loadingEl.style.boxSizing = 'border-box';
        loadingEl.innerHTML = `
            <div class="app-iframe-spinner"></div>
            <p class="app-iframe-loading-text">Starting up <strong>${app.label}</strong>…</p>
            <p class="app-iframe-hint">Waiting for server to register…</p>
            <button class="app-iframe-manual-launch-btn">
                <i class="fas fa-rocket"></i> Launch Service
            </button>`;

        // Add listener for manual launch
        loadingEl.querySelector('.app-iframe-manual-launch-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            fetch('/api/system/modules/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ module: app.id, action: 'run' })
            }).then(() => {
                if (window.showToast) window.showToast(`Launch command sent for ${app.label}`, 'info');
            }).catch(err => console.error('Manual launch failed:', err));
        });

        // iframe — src is intentionally NOT set yet
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

        // Wire the load event BEFORE we ever set src
        iframe.addEventListener('load', () => {
            console.log(`[ATB] iframe LOAD event for ${app.id}. src:`, iframe.src);
            // Ignore initial about:blank loads that occur when appending to DOM
            if (!iframe.src || iframe.src === 'about:blank' || iframe.src === window.location.href) {
                return;
            }
            loadingEl.style.display = 'none';
            iframe.style.display    = 'block';
        });

        panel.appendChild(loadingEl);
        panel.appendChild(iframe);

        // Start polling the registry; sets iframe.src once the server is ready
        _waitAndLoad(iframe, loadingEl, app, panelId);

        return panel;
    }

    // ── Error state ───────────────────────────────────────────────────────────
    function _showError(loadingEl, app) {
        loadingEl.innerHTML = `
            <div class="app-iframe-error-icon">⚠️</div>
            <p class="app-iframe-error">Could not connect to <strong>${app.label}</strong></p>
            <p class="app-iframe-error-msg">
                The server did not register within the timeout.<br>
                Make sure it started correctly, then click Retry.
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

        if (_active === panelId) switchTo(NEXUS_PANEL);   // switch away first

        tabEl?.remove();
        panelEl?.remove();

        if (app) openApp(app);
    }

    // ── Refresh: Hard reload an app ───────────────────────────────────────────
    function refreshApp(appId) {
        const panelId = `panel-app-${appId}`;
        const iframe  = document.getElementById(`${panelId}-iframe`);
        const loading = document.getElementById(`${panelId}-loading`);
        if (!iframe) return;

        console.log(`[ATB] Manually refreshing ${appId}...`);

        // Hide iframe and show same spinner while we reload
        if (loading) {
            loading.style.display = 'flex';
            const hint = loading.querySelector('.app-iframe-hint');
            if (hint) hint.textContent = 'Refreshing cache…';
        }
        iframe.style.display = 'none';

        // Set src with new cache-buster
        const port = iframe.src.match(/:(\d+)/)?.[1];
        if (port) {
            iframe.src = `http://localhost:${port}/?_cb=${Date.now()}`;
        } else {
            // fallback (if src is wonky)
            iframe.src = iframe.src.split('?')[0] + `?_cb=${Date.now()}`;
        }
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
            <span class="atb-tab-refresh" title="Hard Refresh App"><i class="fas fa-sync-alt"></i></span>
            <span class="atb-tab-close" title="Close tab">✕</span>`;

        tab.addEventListener('click', e => {
            if (!e.target.closest('.atb-tab-close') && !e.target.closest('.atb-tab-refresh')) {
                switchTo(panelId);
            }
        });

        tab.querySelector('.atb-tab-refresh').addEventListener('click', e => {
            e.stopPropagation();
            refreshApp(app.id);
        });

        tab.querySelector('.atb-tab-close').addEventListener('click', e => {
            e.stopPropagation();
            _closeTab(panelId, tab);
        });

        return tab;
    }

    // ── Close tab ─────────────────────────────────────────────────────────────
    function _closeTab(panelId, tabEl) {
        // Extract app ID from panel ID (panel-app-ID)
        const appId = panelId.replace('panel-app-', '');

        // 1. Tell backend to stop the service
        fetch('/api/system/modules/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ module: appId, action: 'stop' })
        }).catch(err => console.error(`[ATB] Failed to stop service for ${appId}:`, err));

        // Call switchTo FIRST while _active === panelId so the guard passes
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

        // Group apps by category
        const categories = {};
        APPS.forEach(app => {
            const cat = app.category || 'Other';
            if (!categories[cat]) categories[cat] = [];
            categories[cat].push(app);
        });

        // Use a predefined order for categories
        const order = [
            'Professional Development',
            'Creative & Production',
            'Streaming & Performance',
            'System & Analytics',
            'Other'
        ];

        order.forEach(catName => {
            const appsInCat = categories[catName];
            if (!appsInCat || appsInCat.length === 0) return;

            // Add category header
            const catHeader = document.createElement('div');
            catHeader.className = 'atb-apps-menu-category';
            catHeader.textContent = catName;
            menu.appendChild(catHeader);

            appsInCat.forEach(app => {
                const isOpen  = !!document.getElementById(`panel-app-${app.id}`);
                const portStr = app.port ? `:${app.port}` : '—';
                const btn     = document.createElement('button');
                btn.className = `atb-app-item${isOpen ? ' atb-app-item--open' : ''}`;
                btn.dataset.appId = app.id;
                btn.innerHTML = `
                    <span class="atb-app-emoji">${app.emoji}</span>
                    <span class="atb-app-name">${app.label}</span>
                    <span class="atb-app-port">${portStr}</span>
                    <span class="atb-app-checkmark">✓</span>`;
                btn.addEventListener('click', () => {
                    openApp(app);
                    _closeMenu();
                });
                menu.appendChild(btn);
            });
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
        const isOpen = document.getElementById('atb-apps-menu')?.classList.contains('open');
        isOpen ? _closeMenu() : _openMenu();
    }

    // ── Suite page status dots ────────────────────────────────────────────────
    async function _updateSuiteStatus() {
        try {
            const nameToPort = await refreshPorts();
            let runCount = 0;

            APPS.forEach(app => {
                const running = app.portKey in nameToPort;
                if (running) runCount++;

                const dot = document.getElementById(`sac-status-${app.id}`);
                if (dot) {
                    dot.className = `sac-status sac-status--${running ? 'running' : 'offline'}`;
                    dot.title     = running
                        ? `Running on :${nameToPort[app.portKey]}`
                        : 'Not running';
                }
            });

            // Section header count
            const countEl = document.getElementById('suite-running-count');
            if (countEl) {
                countEl.textContent = runCount > 0
                    ? `${runCount} / ${APPS.length} servers running`
                    : 'no servers running';
                countEl.className = `suite-port-note${runCount > 0 ? ' suite-port-note--live' : ''}`;
            }

            // Hero pill
            const heroLabel = document.getElementById('hub-servers-label');
            if (heroLabel) {
                heroLabel.textContent = runCount > 0
                    ? `${runCount} / ${APPS.length} apps online`
                    : 'no apps running';
            }
            const heroDot = document.getElementById('hub-servers-dot');
            if (heroDot) {
                heroDot.className = `hub-status-dot${runCount > 0 ? ' hub-status-dot--live' : ''}`;
            }
        } catch (_) { /* ignore */ }
    }

    // ── System Shutdown ────────────────────────────────────────────────────────
    async function quitSystem() {
        if (!confirm("Are you sure you want to shut down Aethvion Suite and all background services?")) {
            return;
        }

        const btn = document.getElementById('atb-quit-btn');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> <span>Quitting...</span>`;
        }

        try {
            const resp = await fetch('/api/system/shutdown', { method: 'POST' });
            if (resp.ok) {
                // Show a nice overlay or just wait for the connection to die
                document.body.innerHTML = `
                    <div style="height:100vh; display:flex; flex-direction:column; align-items:center; justify-content:center; background:#0a0a0b; color:#fff; font-family:sans-serif;">
                        <h2 style="color:#f87171;">Shutting Down...</h2>
                        <p style="opacity:0.7;">Aethvion Suite is closing. You can close this window now.</p>
                    </div>
                `;
            } else {
                alert("Shutdown failed. Check logs.");
                location.reload();
            }
        } catch (err) {
            console.error("Shutdown error:", err);
            // If connection dies, it probably worked
            setTimeout(() => {
                document.body.innerHTML = `
                    <div style="height:100vh; display:flex; flex-direction:column; align-items:center; justify-content:center; background:#0a0a0b; color:#fff; font-family:sans-serif;">
                        <h2 style="color:#f87171;">System Stopped</h2>
                        <p style="opacity:0.7;">The backend has disconnected. You may close your browser.</p>
                    </div>
                `;
            }, 1000);
        }
    }

    async function stopService(modelId) {
        try {
            const res = await fetch(`/api/3d/stop/${modelId}`, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                if (window.showToast) window.showToast(`${modelId} stopped`, 'info');
            } else {
                if (window.showToast) window.showToast(`Stop failed: ${data.error}`, 'error');
            }
        } catch (e) {
            console.error('[ATB] Stop failed:', e);
        }
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        ServiceMonitor.init();

        document.querySelector('[data-panel="panel-nexus"]')
            ?.addEventListener('click', () => switchTo(NEXUS_PANEL));

        document.getElementById('atb-apps-btn')
            ?.addEventListener('click', e => { e.stopPropagation(); _toggleMenu(); });

        document.getElementById('atb-quit-btn')
            ?.addEventListener('click', e => { e.stopPropagation(); quitSystem(); });

        document.getElementById('nexus-refresh')
            ?.addEventListener('click', e => {
                e.stopPropagation();
                window.location.reload();
            });

        document.getElementById('atb-apps-menu')
            ?.addEventListener('click', e => e.stopPropagation());

        document.addEventListener('click', () => {
            _closeMenu();
        });
        
        document.addEventListener('keydown', e => { if (e.key === 'Escape') _closeMenu(); });

        // Suite status — initial + every 5 s
        _updateSuiteStatus();
        setInterval(_updateSuiteStatus, 5_000);
    }

    const exported = { init, openApp, switchTo, retryApp, refreshApp, refreshPorts, quitSystem, stopService };
    window.ATB = exported;
    return exported;

})();

document.addEventListener('DOMContentLoaded', () => {
    if (window.ATB && window.ATB.init) window.ATB.init();
});
