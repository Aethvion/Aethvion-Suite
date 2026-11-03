/**
 * agent-tray.js — Global Dispatched Agent Status Tray & Mini-Terminal
 *
 * Provides:
 *   - Global header status pill (idle / running with timer / completed notification)
 *   - Slide-down mini-terminal drawer accessible from any tab or app
 *   - Live progress, output, steering, and quick dispatch everywhere
 */

(function () {
    'use strict';

    let _drawerOpen = false;

    function initTray() {
        const pill = document.getElementById('hdr-agent-pill');
        const drawer = document.getElementById('hdr-agent-drawer');
        const wrapper = document.getElementById('hdr-agent-tray-wrapper');
        const closeBtn = document.getElementById('had-close-btn');
        const expandBtn = document.getElementById('had-expand-btn');
        const quickInput = document.getElementById('had-quick-input');
        const quickSend = document.getElementById('had-quick-send');

        if (!pill || !drawer || pill.dataset.wired) return;
        pill.dataset.wired = 'true';

        function toggleDrawer(forceState) {
            _drawerOpen = typeof forceState === 'boolean' ? forceState : !_drawerOpen;
            drawer.classList.toggle('open', _drawerOpen);
            pill.classList.toggle('drawer-open', _drawerOpen);
            pill.setAttribute('aria-expanded', String(_drawerOpen));

            if (_drawerOpen && quickInput) {
                setTimeout(() => quickInput.focus(), 100);
            }
        }

        function closeDrawer() {
            if (_drawerOpen) toggleDrawer(false);
        }

        pill.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleDrawer();
        });

        drawer.addEventListener('click', (e) => {
            e.stopPropagation();
        });

        if (closeBtn) {
            closeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                closeDrawer();
            });
        }

        if (expandBtn) {
            expandBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                closeDrawer();
                if (window.ATB && typeof window.ATB.switchTo === 'function') {
                    window.ATB.switchTo('panel-home');
                }
                if (typeof window.setDashboardMode === 'function') {
                    window.setDashboardMode('home', true, 'suite-home');
                } else if (typeof window.switchMainTab === 'function') {
                    window.switchMainTab('suite-home');
                }
            });
        }

        // Quick dispatch from drawer
        function handleQuickDispatch() {
            if (!quickInput) return;
            const text = quickInput.value.trim();
            if (!text) return;
            quickInput.value = '';

            if (window.AethvionMissions && typeof window.AethvionMissions.dispatch === 'function') {
                window.AethvionMissions.dispatch(text);
            }
        }

        if (quickSend) {
            quickSend.addEventListener('click', handleQuickDispatch);
        }

        if (quickInput) {
            quickInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleQuickDispatch();
                }
            });
        }

        // Close on escape or outside click
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && _drawerOpen) closeDrawer();
        });

        document.addEventListener('click', (e) => {
            if (_drawerOpen && wrapper && !wrapper.contains(e.target)) {
                closeDrawer();
            }
        });

        // Subscribe to global missions store
        if (window.AethvionMissions && typeof window.AethvionMissions.subscribe === 'function') {
            window.AethvionMissions.subscribe(renderTray);
        } else {
            const waitInterval = setInterval(() => {
                if (window.AethvionMissions && typeof window.AethvionMissions.subscribe === 'function') {
                    clearInterval(waitInterval);
                    window.AethvionMissions.subscribe(renderTray);
                }
            }, 100);
        }
    }

    function esc(s) {
        return String(s || '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function renderTray(missions = []) {
        const pill = document.getElementById('hdr-agent-pill');
        const text = document.getElementById('hdr-agent-text');
        const badge = document.getElementById('had-badge');
        const body = document.getElementById('had-body');

        if (!pill || !text || !body) return;

        const activeMissions = missions.filter(m => m.status === 'running' || m.status === 'queued');
        const completedMissions = missions.filter(m => m.status === 'completed');

        // Check if recently completed (within last 7 seconds)
        const recentCompleted = completedMissions.find(m => m.ended_at && (Date.now() - m.ended_at) < 7000);

        if (activeMissions.length > 0) {
            pill.className = 'hdr-agent-pill is-running' + (_drawerOpen ? ' drawer-open' : '');
            const oldestRunning = activeMissions.reduce((oldest, m) => (!oldest || m.started_at < oldest.started_at) ? m : oldest, null);
            const elapsed = oldestRunning && oldestRunning.started_at ? Math.max(0, Math.floor((Date.now() - oldestRunning.started_at) / 1000)) : 0;
            
            text.textContent = activeMissions.length === 1 
                ? `1 Running (${elapsed}s)` 
                : `${activeMissions.length} Running (${elapsed}s)`;
            
            if (badge) {
                badge.className = 'had-badge had-badge--running';
                badge.innerHTML = `<i class="fas fa-circle-notch fa-spin"></i> ${activeMissions.length} active`;
            }
        } else if (recentCompleted) {
            pill.className = 'hdr-agent-pill is-completed' + (_drawerOpen ? ' drawer-open' : '');
            text.textContent = 'Mission Finished';
            if (badge) {
                badge.className = 'had-badge had-badge--completed';
                badge.innerHTML = `<i class="fas fa-check"></i> Done`;
            }
        } else {
            pill.className = 'hdr-agent-pill' + (_drawerOpen ? ' drawer-open' : '');
            text.textContent = missions.length ? `${missions.length} Agents` : '0 Agents';
            if (badge) {
                badge.className = 'had-badge';
                badge.textContent = 'Idle';
            }
        }

        // Render Drawer Body
        if (!missions.length) {
            body.innerHTML = `
                <div class="had-empty">
                    <div class="had-empty-icon"><i class="fas fa-robot"></i></div>
                    <div class="had-empty-title">No Active Missions</div>
                    <div class="had-empty-desc">Dispatch tasks below to have agents execute in the background.</div>
                </div>`;
            return;
        }

        let html = '';
        missions.slice(0, 5).forEach(m => {
            const isRunning = m.status === 'running' || m.status === 'queued';
            const statusClass = isRunning ? 'had-card--running' : 
                                m.status === 'completed' ? 'had-card--completed' :
                                m.status === 'cancelled' ? 'had-card--cancelled' : 'had-card--failed';
            
            const badgeIcon = isRunning ? 'fa-circle-notch fa-spin' :
                              m.status === 'completed' ? 'fa-check' :
                              m.status === 'cancelled' ? 'fa-ban' : 'fa-triangle-exclamation';

            const elapsed = m.ended_at
                ? `${((m.ended_at - m.started_at) / 1000).toFixed(1)}s`
                : `${m.started_at ? Math.max(0, Math.floor((Date.now() - m.started_at) / 1000)) : 0}s`;

            const lastLog = m.logs && m.logs.length ? m.logs[m.logs.length - 1] : 'Executing task...';

            const mdRenderer = window.AethvionMissions?.renderMarkdown || ((t) => esc(t));
            const responseHtml = m.response ? `
                <div class="had-card-output">
                    <div class="had-output-label"><i class="fas fa-robot"></i> Agent Output</div>
                    <div class="had-output-body">${mdRenderer(m.response)}</div>
                </div>` : '';

            html += `
                <div class="had-mission-card ${statusClass}">
                    <div class="had-card-top">
                        <span class="had-card-prompt" title="${esc(m.prompt)}">${esc(m.prompt)}</span>
                        <div class="had-card-status">
                            <span class="had-card-timer"><i class="fas fa-stopwatch"></i> ${elapsed}</span>
                            <span class="had-card-badge">
                                <i class="fas ${badgeIcon}"></i> ${m.status.toUpperCase()}
                            </span>
                        </div>
                    </div>
                    <div class="had-card-log">
                        <code>${esc(lastLog)}</code>
                    </div>
                    ${responseHtml}
                    <div class="had-card-actions">
                        ${isRunning
                            ? `<button class="had-btn-act had-btn-stop" onclick="window.AethvionMissions.cancel('${m.id}')"><i class="fas fa-stop"></i> Stop</button>`
                            : `<button class="had-btn-act had-btn-dismiss" onclick="window.AethvionMissions.dismiss('${m.id}')"><i class="fas fa-xmark"></i> Dismiss</button>`
                        }
                    </div>
                </div>`;
        });

        body.innerHTML = html;
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTray);
    } else {
        initTray();
    }
})();
