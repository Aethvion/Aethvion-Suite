// Handles interacting with the System Status and Roadmap data

async function loadHeaderStatus() {
    const indicator = document.getElementById('home-status-indicator');
    const updateUI = (isOnline) => {
        if (!indicator) return;
        const dot = indicator.querySelector('.status-dot');
        const text = indicator.querySelector('.status-text');
        
        const color = isOnline ? 'var(--success)' : 'var(--error)';
        const statusText = isOnline ? 'Online' : 'Offline';
        
        if (dot) {
            dot.style.backgroundColor = color;
            if (isOnline) dot.style.boxShadow = `0 0 8px ${color}`;
            else dot.style.boxShadow = 'none';
        }
        if (indicator) {
            indicator.style.borderColor = isOnline ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)';
            indicator.style.background = isOnline ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)';
            indicator.style.color = color;
        }
        if (text) text.textContent = statusText;
    };

    try {
        const response = await fetch('/api/system/status');
        if (!response.ok) {
            updateUI(false);
            return;
        }
        const data = await response.json();
        const isOnline = data.aether && data.aether.initialized;
        updateUI(isOnline);

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
        console.error("Failed to load header status:", error);
        updateUI(false);
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

        if (nameEl) nameEl.textContent = sys.name || sys.system_name || 'Aethvion Suite';
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

        // --- Core System Roadmap ---
        html += `<div class="section-label roadmap-full-width" style="margin-top: 1rem; margin-bottom: 1.5rem; justify-content: flex-start; font-size: 1.2rem; letter-spacing: 0.2em; color: var(--text-bright);">AETHVION SUITE</div>`;
        html += renderSection('FEATURES', roadmap.features || roadmap.working, 'working');
        html += renderSection('WORK IN PROGRESS', roadmap.wip, 'wip');
        html += renderSection('PLANNED', roadmap.planned, 'planned');

        // --- Individual Module Roadmaps ---
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
