// Handles interacting with the System Status and Roadmap data


async function loadSystemStatusTab() {
    const container = document.querySelector('.roadmap-tree');
    if (!container) return;

    try {
        const [roadmapRes, metricsRes, apiRes] = await Promise.all([
            fetch('/static/assets/system-status.json?v=' + Date.now()),
            fetch('/static/assets/system-metrics.json?v=' + Date.now()),
            fetch('/api/system/status')
        ]);

        const roadmapData = roadmapRes.ok ? await roadmapRes.json() : {};
        const metricsData = metricsRes.ok ? await metricsRes.json() : {};
        const apiData = apiRes.ok ? await apiRes.json() : {};

        const nameEl = document.getElementById('system-name-display');
        const verEl = document.getElementById('system-version-display');
        const dateEl = document.getElementById('status-last-update');
        const compEl = document.getElementById('system-company-display');
        const contactEl = document.getElementById('system-contact-display');

        const sys = roadmapData.system || roadmapData;

        if (nameEl) nameEl.textContent = sys.name || sys.system_name || 'Aethvion Suite';
        if (dateEl) dateEl.textContent = sys.last_sync || sys.last_update || 'Unknown';

        // Version is git-derived — fetch from version API
        if (verEl) {
            fetch('/api/system/version-info?v=' + Date.now())
                .then(r => r.ok ? r.json() : null)
                .then(d => { if (d && d.local && d.local.version) verEl.textContent = d.local.version; })
                .catch(() => {});
        }
        if (compEl) compEl.textContent = sys.company || '';
        if (contactEl) contactEl.textContent = sys.contact || '';
        if (contactEl && sys.contact) contactEl.href = `mailto:${sys.contact}`;

        renderSystemTelemetry(apiData, metricsData);
        initLoopsPanel();

        const roadmap = roadmapData.roadmap || {};
        let html = '';

        const renderItem = (item) => {
            if (typeof item === 'string') {
                return `<div class="roadmap-item"><div class="item-content"><div class="item-name">${item}</div></div></div>`;
            } else if (item && item.name) {
                return `
                    <div class="roadmap-item">
                        <div class="item-content">
                            <div class="item-name">${item.name}</div>
                            ${item.desc ? `<div class="item-desc">${item.desc}</div>` : ''}
                        </div>
                    </div>
                `;
            }
            return '';
        };

        const renderSection = (title, items, type) => {
            let itemsHtml = '';

            if (Array.isArray(items)) {
                itemsHtml = items.map(renderItem).join('');
            } else if (items && typeof items === 'object') {
                for (const [category, list] of Object.entries(items)) {
                    const titleStr = category.toUpperCase();
                    itemsHtml += `<div class="roadmap-category" style="margin-top: 0.8rem;">
                        <div class="roadmap-category-title" style="font-size: 0.75rem; color: var(--primary); font-weight: bold; margin-bottom: 0.4rem; letter-spacing: 0.05em;">${titleStr}</div>
                        ${(list || []).map(renderItem).join('')}
                    </div>`;
                }
            }

            return `
                <div class="roadmap-section ${type}">
                    <h3>${title}</h3>
                    <div class="roadmap-items">
                        ${itemsHtml}
                    </div>
                </div>
            `;
        };

        // Core System Roadmap
        html += `<div class="section-label roadmap-full-width" style="margin-top: 1rem; margin-bottom: 1.5rem; justify-content: flex-start; font-size: 1.2rem; letter-spacing: 0.2em; color: var(--text-bright);">AETHVION SUITE</div>`;
        html += renderSection('FEATURES', roadmap.features || roadmap.working, 'working');
        html += renderSection('WORK IN PROGRESS', roadmap.wip, 'wip');
        html += renderSection('PLANNED', roadmap.planned, 'planned');

        // Individual Module Roadmaps
        const modules = roadmapData.modules || [];
        modules.forEach(mod => {
            html += `<div class="roadmap-divider roadmap-full-width" style="margin: 2.5rem 0; border-top: 1px solid var(--border-color); opacity: 0.5;"></div>`;
            html += `<div class="section-label roadmap-full-width" style="margin-bottom: 1.5rem; justify-content: flex-start; font-size: 1.2rem; letter-spacing: 0.2em; color: var(--text-bright);">${mod.name.toUpperCase()}</div>`;

            // Only render sections if they have items or if it's the standard roadmap feel
            html += renderSection('FEATURES', mod.features, 'working');
            html += renderSection('WORK IN PROGRESS', mod.wip, 'wip');
            html += renderSection('PLANNED', mod.planned, 'planned');
        });

        if (!html) {
            console.warn('[StatusTab] Content HTML is empty!');
            html = '<div class="placeholder-text">No system or module data available.</div>';
        }

        container.innerHTML = html;

        startVitalsPolling();

    } catch (error) {
        console.error('Error loading system status:', error);
        container.innerHTML = '<div class="error-placeholder">Couldn\'t load system info. Try refreshing.</div>';
    }
}

let vitalsInterval = null;
let _loopsFilter = 'all';
let _loopsUnsub = null;

function _formatInterval(ms) {
    if (!ms || ms < 1000) return `${ms || 0}ms`;
    if (ms < 60000) return `${Math.round(ms / 1000)}s`;
    return `${Math.round(ms / 60000)}m`;
}

function _formatAgo(ts) {
    if (!ts) return 'Never';
    const diff = Math.max(0, Math.floor((Date.now() - ts) / 1000));
    if (diff < 5) return 'Just now';
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
}

function renderActiveLoops() {
    const listEl = document.getElementById('active-loops-list');
    const summaryEl = document.getElementById('loops-summary-pill');
    if (!listEl || !window.AethvionLoops) return;

    const all = window.AethvionLoops.list();
    const summary = window.AethvionLoops.getSummary();

    if (summaryEl) {
        summaryEl.textContent = `${summary.running} running · ${summary.paused + summary.stopped} inactive (${summary.total} total)`;
    }

    const filtered = all.filter(item => {
        if (_loopsFilter === 'all') return true;
        if (_loopsFilter === 'critical' || _loopsFilter === 'standard' || _loopsFilter === 'optional') {
            return item.criticality === _loopsFilter;
        }
        if (_loopsFilter === 'running') return item.status === 'running';
        if (_loopsFilter === 'stopped') return item.status !== 'running';
        return true;
    });

    if (!filtered.length) {
        listEl.innerHTML = `<div class="placeholder-text">No loops match the "${_loopsFilter}" filter.</div>`;
        return;
    }

    listEl.innerHTML = filtered.map(item => {
        const isRunning = item.status === 'running';
        const isPaused = item.status === 'paused';
        const statusLabel = isRunning ? 'Running' : (isPaused ? 'Paused' : 'Stopped');
        const critLabel = item.criticality === 'critical' ? 'Critical' : (item.criticality === 'standard' ? 'Standard' : 'Optional');
        const metaParts = [
            `Every ${_formatInterval(item.intervalMs)}`,
            `Runs: ${item.runCount}`,
            `Last: ${_formatAgo(item.lastRunAt)}`,
            item.lastDurationMs !== null ? `${item.lastDurationMs}ms` : null,
        ].filter(Boolean).join(' · ');

        return `
        <div class="loop-row" data-loop-id="${item.id}">
            <div class="loop-row-main">
                <div class="loop-row-title-line">
                    <span class="loop-name">${item.name}</span>
                    <span class="loop-badge loop-crit-${item.criticality}">${critLabel}</span>
                    <span class="loop-badge loop-cat">${item.category}</span>
                    <span class="loop-status-pill loop-status-${item.status}">● ${statusLabel}</span>
                </div>
                <div class="loop-desc">${item.description || item.id}</div>
                <div class="loop-meta">${metaParts}${item.lastError ? ` · <span class="loop-err">Error: ${item.lastError}</span>` : ''}</div>
            </div>
            <div class="loop-row-controls">
                <label class="loop-startup-toggle" title="Start this loop automatically on dashboard startup">
                    <input type="checkbox" class="loop-autostart-cb" data-loop-id="${item.id}" ${item.autoStart ? 'checked' : ''}>
                    <span>Startup</span>
                </label>
                <div class="loop-btn-group">
                    ${isRunning
                        ? `<button type="button" class="action-btn secondary xs-btn loop-action-btn" data-action="pause" data-loop-id="${item.id}" title="Pause loop"><i class="fas fa-pause"></i> Pause</button>`
                        : `<button type="button" class="action-btn xs-btn loop-action-btn" data-action="start" data-loop-id="${item.id}" title="Start loop"><i class="fas fa-play"></i> Start</button>`
                    }
                    ${item.status !== 'stopped'
                        ? `<button type="button" class="action-btn secondary xs-btn loop-action-btn" data-action="stop" data-loop-id="${item.id}" title="Stop loop"><i class="fas fa-stop"></i></button>`
                        : ''
                    }
                    <button type="button" class="action-btn secondary xs-btn loop-action-btn" data-action="run" data-loop-id="${item.id}" title="Run one tick now"><i class="fas fa-bolt"></i></button>
                </div>
            </div>
        </div>`;
    }).join('');
}

function initLoopsPanel() {
    if (!window.AethvionLoops) return;

    const filterBar = document.getElementById('loops-filter-bar');
    if (filterBar && !filterBar.dataset.bound) {
        filterBar.dataset.bound = '1';
        filterBar.addEventListener('click', e => {
            const btn = e.target.closest('.loops-filter-btn');
            if (!btn) return;
            _loopsFilter = btn.dataset.filter || 'all';
            filterBar.querySelectorAll('.loops-filter-btn').forEach(b => b.classList.toggle('active', b === btn));
            renderActiveLoops();
        });
    }

    const listEl = document.getElementById('active-loops-list');
    if (listEl && !listEl.dataset.bound) {
        listEl.dataset.bound = '1';
        listEl.addEventListener('click', e => {
            const btn = e.target.closest('.loop-action-btn');
            if (!btn) return;
            const id = btn.dataset.loopId;
            const action = btn.dataset.action;
            if (!id || !action) return;
            if (action === 'start') window.AethvionLoops.start(id);
            else if (action === 'pause') window.AethvionLoops.pause(id);
            else if (action === 'stop') window.AethvionLoops.stop(id);
            else if (action === 'run') window.AethvionLoops.runNow(id);
            renderActiveLoops();
        });

        listEl.addEventListener('change', e => {
            const cb = e.target.closest('.loop-autostart-cb');
            if (!cb) return;
            window.AethvionLoops.setAutoStart(cb.dataset.loopId, cb.checked);
            renderActiveLoops();
        });
    }

    const enableBtn = document.getElementById('loops-enable-companions-btn');
    if (enableBtn && !enableBtn.dataset.bound) {
        enableBtn.dataset.bound = '1';
        enableBtn.addEventListener('click', () => {
            window.AethvionLoops.setOptionalAutoStart(true, true);
            renderActiveLoops();
        });
    }

    const disableBtn = document.getElementById('loops-disable-optional-btn');
    if (disableBtn && !disableBtn.dataset.bound) {
        disableBtn.dataset.bound = '1';
        disableBtn.addEventListener('click', () => {
            window.AethvionLoops.setOptionalAutoStart(false, true);
            renderActiveLoops();
        });
    }

    if (!_loopsUnsub) {
        _loopsUnsub = window.AethvionLoops.onChange(() => {
            if (document.querySelector('.main-tab-panel.active')?.id === 'status-panel') {
                renderActiveLoops();
            }
        });
    }

    renderActiveLoops();
}

function startVitalsPolling() {
    const tickVitals = async () => {
        if (document.querySelector('.main-tab-panel.active')?.id !== 'status-panel') {
            stopVitalsPolling();
            return;
        }
        try {
            const res = await fetch('/api/system/status');
            if (res.ok) {
                const data = await res.json();
                updateRealtimeVitals(data);
            }
        } catch (e) { console.warn('Vitals poll failed', e); }
    };

    if (window.AethvionLoops) {
        window.AethvionLoops.register('status.vitals', {
            name: 'Status Realtime Vitals',
            category: 'Status',
            criticality: 'standard',
            description: 'Polls live CPU, RAM, and agent counts while the Status tab is open.',
            intervalMs: 3000,
            fn: tickVitals,
        });
        return;
    }

    if (vitalsInterval) return;
    vitalsInterval = setInterval(tickVitals, 3000);
}

function stopVitalsPolling() {
    if (window.AethvionLoops) {
        window.AethvionLoops.stop('status.vitals');
    }
    if (vitalsInterval) {
        clearInterval(vitalsInterval);
        vitalsInterval = null;
    }
}

function updateRealtimeVitals(apiData) {
    const container = document.getElementById('realtime-info-grid');
    if (!container) return;

    const aetherStatus = apiData.aether || {};
    const factoryStatus = apiData.factory || {};
    const vitals = apiData.vitals || {};

    container.innerHTML = renderRealtimeCards(aetherStatus, factoryStatus, vitals);
}

function renderSystemTelemetry(apiData, metricsData) {
    const rtContainer = document.getElementById('realtime-info-grid');
    if (rtContainer) {
        rtContainer.innerHTML = renderRealtimeCards(
            apiData.aether || {},
            apiData.factory || {},
            apiData.vitals || {}
        );
    }

    const localContainer = document.getElementById('local-info-grid');
    if (localContainer) {
        const forgeStatus = apiData.forge || {};
        const systemMetrics = metricsData.system || {};
        const memoryMetrics = metricsData.memory || {};

        const formatBytes = (bytes) => {
            if (!bytes) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        };

        const syncEl = document.getElementById('telemetry-last-sync');
        if (syncEl) {
            const lastSync = systemMetrics.last_sync;
            syncEl.textContent = lastSync ? new Date(lastSync).toLocaleString() : 'Never';
        }

        localContainer.innerHTML = `
            <div class="telemetry-card">
                <div class="t-label">Project Size</div>
                <div class="t-value">${formatBytes(systemMetrics.project_size_bytes)}</div>
            </div>
            <div class="telemetry-card">
                <div class="t-label">Memory Entries</div>
                <div class="t-value">${memoryMetrics.episodic_count || 0} <span class="t-sub">(Memories)</span></div>
            </div>
            <div class="telemetry-card">
                <div class="t-label">Knowledge Base</div>
                <div class="t-value">${formatBytes(systemMetrics.db_size_bytes)} <span class="t-sub">(DB)</span></div>
            </div>

        `;

        const extContainer = document.getElementById('extended-info-grid');
        if (extContainer) {
            extContainer.innerHTML = `
                <div class="telemetry-card">
                    <div class="t-label">Git Latest</div>
                    <div class="t-value" style="font-size: 0.85rem; font-family: 'Fira Code', monospace; line-height: 1.4;">${systemMetrics.git_commit || 'Unknown'}</div>
                </div>
                <div class="telemetry-card">
                    <div class="t-label">Host Platform</div>
                    <div class="t-value" style="font-size: 0.95rem;">${systemMetrics.platform || 'Unknown'}</div>
                </div>
                <div class="telemetry-card">
                    <div class="t-label">Python Runtime</div>
                    <div class="t-value">${systemMetrics.python_version || 'Unknown'}</div>
                </div>
                <div class="telemetry-card">
                    <div class="t-label">Local Models</div>
                    <div class="t-value">${systemMetrics.model_count || 0} <span class="t-sub">GGUF</span></div>
                </div>
            `;
        }
    }
}

function renderRealtimeCards(aetherStatus, factoryStatus, vitals) {
    return `
        <div class="telemetry-card">
            <div class="t-label">System Status</div>
            <div class="t-value ${aetherStatus.initialized ? 'online' : 'offline'}">
                ${aetherStatus.initialized ? 'Online' : 'Offline'}
            </div>
        </div>
        <div class="telemetry-card">
            <div class="t-label">CPU Usage</div>
            <div class="t-value">
                ${vitals.cpu_percent || 0}%
            </div>
        </div>
        <div class="telemetry-card">
            <div class="t-label">RAM Usage</div>
            <div class="t-value" style="font-size: 1rem;">
                ${vitals.ram_used_gb || 0} GB <span class="t-sub">/ ${vitals.ram_total_gb || 0} GB (${vitals.ram_percent || 0}%)</span>
            </div>
        </div>
        <div class="telemetry-card">
            <div class="t-label">Active Agents</div>
            <div class="t-value">${factoryStatus.active_agents || 0} <span class="t-sub">/ ${factoryStatus.total_agents || 0}</span></div>
        </div>
    `;
}

async function syncSystemTelemetry() {
    const btn = document.getElementById('sync-telemetry-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spin fa-spinner"></i> Syncing...';
    }

    try {
        const response = await fetch('/api/system/telemetry/sync', { method: 'POST' });
        if (!response.ok) throw new Error('Sync failed');

        await loadSystemStatusTab();

        if (btn) {
            btn.innerHTML = '<i class="fas fa-check"></i> Synced';
            setTimeout(() => {
                btn.innerHTML = '<i class="fas fa-sync"></i> Sync Telemetry';
                btn.disabled = false;
            }, 2000);
        }
    } catch (error) {
        console.error('Telemetry sync error:', error);
        if (btn) {
            btn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error';
            btn.disabled = false;
        }
    }
}

window.toggleRoadmapView = function () {
    const tree = document.querySelector('.roadmap-tree');
    const btn = document.getElementById('roadmap-view-toggle');
    if (!tree || !btn) return;

    tree.classList.toggle('detailed-view');
    const isDetailed = tree.classList.contains('detailed-view');

    if (isDetailed) {
        btn.innerHTML = '<i class="fas fa-bars"></i> Simple View';
    } else {
        btn.innerHTML = '<i class="fas fa-list"></i> Detailed View';
    }
};
