// Handles interacting with the System Status and Roadmap data

async function loadHeaderStatus() {
    try {
        const response = await fetch('/api/system/status');
        if (!response.ok) return;
        const data = await response.json();

        const nexusEl = document.getElementById('nexus-status');
        const agentsEl = document.getElementById('agents-count');
        const indicator = document.getElementById('nexus-status-indicator');
        if (indicator) {
            const dot = indicator.querySelector('.status-dot');
            const text = indicator.querySelector('.status-text');
            const isOnline = data.nexus && data.nexus.initialized;

            if (dot) dot.style.backgroundColor = isOnline ? 'var(--success)' : 'var(--error)';
            if (indicator) indicator.style.borderColor = isOnline ? 'var(--success)' : 'var(--error)';
            if (text) {
                text.textContent = isOnline ? 'ONLINE' : 'OFFLINE';
                text.style.color = isOnline ? 'var(--success)' : 'var(--error)';
            }
        }

        const agentsCount = document.getElementById('agents-count');
        const toolsCount = document.getElementById('tools-count');

        if (agentsCount) agentsCount.textContent = data.factory ? data.factory.active_agents : '0';
        if (toolsCount) toolsCount.textContent = data.forge ? data.forge.total_tools : '0';

        // Update compact status bar with today's usage
        if (data.usage_today) {
            const tokensEl = document.getElementById('tokens-today');
            const costEl = document.getElementById('cost-today');
            if (tokensEl && typeof formatNumber === 'function') {
                tokensEl.textContent = formatNumber(data.usage_today.tokens || 0);
            }
            if (costEl && typeof formatCost === 'function') {
                costEl.textContent = formatCost(data.usage_today.cost || 0);
            }
        }

    } catch (error) {
        const indicator = document.getElementById('nexus-status-indicator');
        if (indicator) {
            const dot = indicator.querySelector('.status-dot');
            const text = indicator.querySelector('.status-text');
            if (dot) dot.style.backgroundColor = 'var(--error)';
            if (indicator) indicator.style.borderColor = 'var(--error)';
            if (text) {
                text.textContent = 'DISCONNECTED';
                text.style.color = 'var(--error)';
            }
        }
    }
}

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

        if (nameEl) nameEl.textContent = sys.name || sys.system_name || 'Misaka Cipher';
        if (verEl) verEl.textContent = sys.version ? `v${sys.version}` : '';
        if (dateEl) dateEl.textContent = sys.last_sync || sys.last_update || 'Unknown';
        if (compEl) compEl.textContent = sys.company || '';
        if (contactEl) contactEl.textContent = sys.contact || '';
        if (contactEl && sys.contact) contactEl.href = `mailto:${sys.contact}`;

        renderSystemTelemetry(apiData, metricsData);

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

        html += renderSection('CORE FEATURES', roadmap.features || roadmap.working, 'working');
        html += renderSection('CORE WORK IN PROGRESS', roadmap.wip, 'wip');
        html += renderSection('CORE PLANNED', roadmap.planned, 'planned');

        const modules = roadmapData.modules || [];
        if (modules.length > 0) {
            html += `<div class="roadmap-divider roadmap-full-width" style="margin: 2.5rem 0; border-top: 1px solid var(--border-color); opacity: 0.5;"></div>`;
            html += `<div class="section-label roadmap-full-width" style="margin-bottom: 1.5rem; justify-content: center; font-size: 1.2rem; letter-spacing: 0.2em;">MODULE ROADMAPS</div>`;

            // Group all module data into matching categories for a unified 3-column grid
            const moduleFeatures = {};
            const moduleWip = {};
            const modulePlanned = {};

            modules.forEach(mod => {
                if (mod.features && mod.features.length > 0) moduleFeatures[mod.name] = mod.features;
                if (mod.wip && mod.wip.length > 0) moduleWip[mod.name] = mod.wip;
                if (mod.planned && mod.planned.length > 0) modulePlanned[mod.name] = mod.planned;
            });

            html += renderSection('FEATURES', moduleFeatures, 'working');
            html += renderSection('WORK IN PROGRESS', moduleWip, 'wip');
            html += renderSection('PLANNED', modulePlanned, 'planned');
        }

        if (!html) {
            console.warn('[StatusTab] Content HTML is empty!');
            html = '<div class="placeholder-text">No system or module data available.</div>';
        }

        container.innerHTML = html;

        startVitalsPolling();

    } catch (error) {
        console.error('Error loading system status:', error);
        container.innerHTML = '<div class="error-placeholder">Failed to load system status. Check console.</div>';
    }
}

let vitalsInterval = null;

function startVitalsPolling() {
    if (vitalsInterval) return;
    vitalsInterval = setInterval(async () => {
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
    }, 3000);
}

function stopVitalsPolling() {
    if (vitalsInterval) {
        clearInterval(vitalsInterval);
        vitalsInterval = null;
    }
}

function updateRealtimeVitals(apiData) {
    const container = document.getElementById('realtime-info-grid');
    if (!container) return;

    const nexusStatus = apiData.nexus || {};
    const factoryStatus = apiData.factory || {};
    const vitals = apiData.vitals || {};

    container.innerHTML = renderRealtimeCards(nexusStatus, factoryStatus, vitals);
}

function renderSystemTelemetry(apiData, metricsData) {
    const rtContainer = document.getElementById('realtime-info-grid');
    if (rtContainer) {
        rtContainer.innerHTML = renderRealtimeCards(
            apiData.nexus || {},
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
                <div class="t-label">PROJECT SIZE</div>
                <div class="t-value">${formatBytes(systemMetrics.project_size_bytes)}</div>
            </div>
            <div class="telemetry-card">
                <div class="t-label">EPISODIC (DB)</div>
                <div class="t-value">${memoryMetrics.episodic_count || 0} <span class="t-sub">(Memories)</span></div>
            </div>
            <div class="telemetry-card">
                <div class="t-label">KNOWLEDGE BASE</div>
                <div class="t-value">${formatBytes(systemMetrics.db_size_bytes)} <span class="t-sub">(DB)</span></div>
            </div>
            <div class="telemetry-card">
                <div class="t-label">TOOLS</div>
                <div class="t-value">${forgeStatus.total_tools || 0}</div>
            </div>
        `;
    }
}

function renderRealtimeCards(nexusStatus, factoryStatus, vitals) {
    return `
        <div class="telemetry-card">
            <div class="t-label">NEXUS STATUS</div>
            <div class="t-value ${nexusStatus.initialized ? 'online' : 'offline'}">
                ${nexusStatus.initialized ? 'ONLINE' : 'OFFLINE'}
            </div>
        </div>
        <div class="telemetry-card">
            <div class="t-label">CPU USAGE</div>
            <div class="t-value">
                ${vitals.cpu_percent || 0}%
            </div>
        </div>
        <div class="telemetry-card">
            <div class="t-label">RAM USAGE</div>
            <div class="t-value" style="font-size: 1rem;">
                ${vitals.ram_used_gb || 0} GB <span class="t-sub">/ ${vitals.ram_total_gb || 0} GB (${vitals.ram_percent || 0}%)</span>
            </div>
        </div>
        <div class="telemetry-card">
            <div class="t-label">ACTIVE AGENTS</div>
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
