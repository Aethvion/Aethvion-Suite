/**
 * Aethvion Suite - Local Models Management View
 */

const LocalModels = {
    init() {
        console.log("[LocalModels] Initializing...");
        this.addEventListeners();
        // If we are already on this tab, load immediately
        if (typeof currentMainTab !== 'undefined' && currentMainTab === 'local-models') {
            console.log("[LocalModels] Already on tab, loading models...");
            this.loadModels();
            this.loadSuggestedModels();
        }
    },

    addEventListeners() {
        const refreshBtn = document.getElementById('refresh-local-models');
        if (refreshBtn) refreshBtn.onclick = () => this.loadModels();

        const startDownloadBtn = document.getElementById('start-hf-download');
        if (startDownloadBtn) startDownloadBtn.onclick = () => this.startDownload();
    },

    async loadModels() {
        const tbody = document.getElementById('local-models-list');
        if (!tbody) return;

        try {
            const registryRes = await fetch('/api/registry');
            const registryData = await registryRes.json();
            const registeredModels = registryData.providers?.local?.models || {};

            const res = await fetch('/api/registry/local/models/status');
            const data = await res.json();
            const models = data.models || {};
            if (typeof markPanelUpdated !== 'undefined') markPanelUpdated('models');

            if (Object.keys(models).length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="placeholder-text">No models found in localmodels/gguf/</td></tr>';
                return;
            }

            tbody.innerHTML = Object.entries(models).map(([filename, info]) => {
                const isRegistered = !!registeredModels[filename];
                return `
                    <tr>
                        <td style="font-weight: 600; color: #fff;">${filename}</td>
                        <td style="color: var(--text-secondary);">${info.size_mb} MB</td>
                        <td>
                            ${isRegistered ? 
                                '<span class="status-badge success-v12"><i class="fas fa-check-circle"></i> Registered</span>' : 
                                '<span class="status-badge warning-v12"><i class="fas fa-exclamation-circle"></i> Unregistered</span>'
                            }
                        </td>
                        <td style="display: flex; gap: 0.75rem; justify-content: flex-end; align-items: center;">
                            ${!isRegistered ? `
                                <button class="action-btn sm-btn register-model-btn" data-filename="${filename}" title="Register Model">
                                    <i class="fas fa-plus"></i> Register
                                </button>
                            ` : ''}
                            <button class="btn-icon sm-btn delete-model-btn" data-filename="${filename}" title="Delete Model" style="color: rgba(255, 118, 117, 0.8);">
                                <i class="fas fa-trash"></i>
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');

            // Add events
            tbody.querySelectorAll('.delete-model-btn').forEach(btn => {
                btn.onclick = () => this.deleteModel(btn.dataset.filename);
            });
            tbody.querySelectorAll('.register-model-btn').forEach(btn => {
                btn.onclick = () => this.registerModel(btn.dataset.filename);
            });

            // Update suggested models badges
            this.updateSuggestedBadges(Object.keys(models));

        } catch (e) {
            console.error("Failed to load local models:", e);
            tbody.innerHTML = `<tr><td colspan="4" class="placeholder-text" style="color:#ff7675;">
                Error loading models
                <button class="action-btn small primary" style="margin-left:1rem;" onclick="LocalModels.loadModels()">
                    <i class="fas fa-rotate-right"></i> Retry
                </button>
            </td></tr>`;
        }
    },

    async loadSuggestedModels() {
        const grid = document.getElementById('suggested-models-grid');
        if (!grid) return;

        try {
            const res = await fetch('/api/registry/local/suggested');
            const data = await res.json();
            const suggestions = data.suggested || [];

            if (suggestions.length === 0) {
                grid.innerHTML = '<div class="placeholder-text">No suggestions available</div>';
                return;
            }

            grid.innerHTML = suggestions.map(model => {
                const isUnsupported = !!model.unsupported;
                const actionHtml = isUnsupported
                    ? `<span title="${model.unsupported_reason || 'Not supported'}" style="font-size:0.75rem; color:#ff7675; display:flex; align-items:center; gap:0.3rem; cursor:help;">
                           <i class="fas fa-triangle-exclamation"></i> Not yet compatible
                       </span>`
                    : `<button class="action-btn sm-btn install-btn"
                               onclick="LocalModels.installSuggestedModel('${model.id}', '${model.repo}', '${model.filename}')">
                           <i class="fas fa-download"></i> Install
                       </button>`;
                
                return `
                <div class="suggestion-card-v12" id="suggested-${model.id}" style="${isUnsupported ? 'opacity: 0.6;' : ''}">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <h4>${model.name}</h4>
                        <span class="installed-badge" style="display: none; background: var(--success); color: white; padding: 2px 10px; border-radius: 12px; font-size: 0.65rem; font-weight: 800; letter-spacing: 0.5px;">INSTALLED</span>
                    </div>
                    <p class="description">${model.description}</p>
                    <div class="tag-list">
                        ${model.tags.map(tag => `<span class="tag-v12">${tag}</span>`).join('')}
                    </div>
                    <div class="card-footer-v12">
                        <span class="model-size-badge">
                            <i class="fas fa-microchip"></i> ${model.size}
                        </span>
                        ${actionHtml}
                    </div>
                </div>`;
            }).join('');

            // After loading suggestions, check which ones are already installed
            const localRes = await fetch('/api/registry/local/models/status');
            const localData = await localRes.json();
            this.updateSuggestedBadges(Object.keys(localData.models || {}));

        } catch (e) {
            console.error("Failed to load suggested models:", e);
            grid.innerHTML = '<div class="placeholder-text" style="color:#ff7675;">Error loading suggestions</div>';
        }
    },

    updateSuggestedBadges(installedFiles) {
        const grid = document.getElementById('suggested-models-grid');
        if (!grid) return;

        grid.querySelectorAll('.suggestion-card-v12').forEach(card => {
            const installBtn = card.querySelector('.install-btn');
            const badge = card.querySelector('.installed-badge');

            // Skip unsupported cards — they have no install button
            if (!installBtn) return;

            const installAction = installBtn.getAttribute('onclick');
            const filenameMatch = installAction ? installAction.match(/'([^']+)'\s*\)$/) : null;
            const filename = filenameMatch ? filenameMatch[1] : '';

            if (installedFiles.includes(filename)) {
                if (badge) badge.style.display = 'block';
                installBtn.disabled = true;
                installBtn.innerHTML = '<i class="fas fa-check"></i> Installed';
                installBtn.classList.add('secondary');
            } else {
                if (badge) badge.style.display = 'none';
                installBtn.disabled = false;
                installBtn.innerHTML = '<i class="fas fa-download"></i> Install';
                installBtn.classList.remove('secondary');
            }
        });
    },

    async installSuggestedModel(id, repo, filename) {
        const card = document.getElementById(`suggested-${id}`);
        const btn  = card ? card.querySelector('.install-btn') : null;

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting…';
        }

        // Inject (or reuse) progress panel inside the card
        let prog = card ? card.querySelector('.model-dl-progress') : null;
        if (card && !prog) {
            prog = document.createElement('div');
            prog.className = 'model-dl-progress';
            prog.innerHTML = `
                <div class="model-dl-row">
                    <span class="model-dl-label">Connecting…</span>
                    <span class="model-dl-pct">0%</span>
                </div>
                <div class="model-dl-bar-wrap">
                    <div class="model-dl-bar" style="width:0%"></div>
                </div>
                <span class="model-dl-size"></span>`;
            card.appendChild(prog);
        }

        const dlLabel = prog?.querySelector('.model-dl-label');
        const dlPct   = prog?.querySelector('.model-dl-pct');
        const dlBar   = prog?.querySelector('.model-dl-bar');
        const dlSize  = prog?.querySelector('.model-dl-size');

        try {
            const resp = await fetch('/api/registry/local/models/download/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ repo_id: repo, filename }),
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.detail || `HTTP ${resp.status}`);
            }

            const reader  = resp.body.getReader();
            const decoder = new TextDecoder();
            let   buffer  = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                const parts = buffer.split('\n\n');
                buffer = parts.pop();

                for (const part of parts) {
                    if (!part.startsWith('data: ')) continue;
                    let msg;
                    try { msg = JSON.parse(part.slice(6)); } catch { continue; }

                    if (msg.pct !== undefined) {
                        if (dlBar)   dlBar.style.width    = msg.pct + '%';
                        if (dlPct)   dlPct.textContent    = msg.pct + '%';
                        if (dlLabel) dlLabel.textContent  = 'Downloading…';
                        if (dlSize && msg.downloaded_mb)
                            dlSize.textContent = `${msg.downloaded_mb} MB / ${msg.total_mb} MB`;
                        if (btn) btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${msg.pct}%`;
                    } else if (msg.done) {
                        if (msg.success) {
                            if (dlBar)   { dlBar.style.width = '100%'; dlBar.classList.add('dl-bar-done'); }
                            if (dlLabel) dlLabel.textContent = 'Complete!';
                            if (dlPct)   dlPct.textContent   = '100%';
                            if (btn)     { btn.disabled = true; btn.innerHTML = '<i class="fas fa-check"></i> Installed'; }
                            showNotification(`${filename} downloaded successfully`, 'success');
                            setTimeout(() => this.loadModels(), 500);
                        } else {
                            if (dlBar)   dlBar.classList.add('dl-bar-fail');
                            if (dlLabel) dlLabel.textContent = 'Failed';
                            showNotification(`Download failed: ${msg.error || 'Unknown error'}`, 'error');
                            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-download"></i> Install'; }
                        }
                    }
                }
            }
        } catch (e) {
            showNotification(`Error: ${e.message || 'Connection failed'}`, 'error');
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-download"></i> Install'; }
        }
    },

    async registerModel(filename) {
        try {
            showNotification(`Registering ${filename}...`, 'info');
            const res = await fetch('/api/registry/local/models/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename })
            });

            if (res.ok) {
                showNotification(`Model ${filename} registered!`, 'success');
                this.loadModels();
                // Reload the Model Registry settings panel so _registryData stays fresh.
                // Without this, a later "Save Changes" in settings would overwrite the
                // registry file with stale data that doesn't include the newly registered model.
                if (typeof window.loadProviderSettings === 'function') {
                    window.loadProviderSettings();
                }
            } else {
                const err = await res.json();
                showNotification(err.detail || 'Registration failed', 'error');
            }
        } catch (e) {
            showNotification('Error connecting to server', 'error');
        }
    },

    async deleteModel(filename) {
        if (!confirm(`Are you sure you want to delete ${filename}? This cannot be undone.`)) return;

        try {
            // We need a delete endpoint
            const res = await fetch(`/api/registry/local/models/delete`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename })
            });

            if (res.ok) {
                showNotification(`Model ${filename} deleted`, 'success');
                this.loadModels();
            } else {
                const err = await res.json();
                showNotification(err.detail || 'Failed to delete model', 'error');
            }
        } catch (e) {
            showNotification('Error connecting to server', 'error');
        }
    },

    async startDownload() {
        const repoId = document.getElementById('hf-repo-id').value.trim();
        const filename = document.getElementById('hf-filename').value.trim();
        const btn = document.getElementById('start-hf-download');
        const progressContainer = document.getElementById('download-progress-container');
        const progressBar = document.getElementById('download-progress-bar');
        const statusText = document.getElementById('download-status');
        const percentText = document.getElementById('download-percent');

        if (!repoId || !filename) {
            showNotification('Repo ID and Filename are required', 'warning');
            return;
        }

        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Initializing...';
        progressContainer.style.display = 'block';
        progressBar.style.width = '0%';
        percentText.innerText = '0%';
        statusText.innerText = `Starting download of ${filename}...`;

        try {
            const res = await fetch('/api/registry/local/models/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ repo_id: repoId, filename: filename })
            });

            const result = await res.json();
            if (res.ok) {
                statusText.innerText = 'Download complete!';
                progressBar.style.width = '100%';
                percentText.innerText = '100%';
                showNotification(result.message, 'success');
                this.loadModels();
            } else {
                statusText.innerText = 'Download failed.';
                showNotification(result.detail || 'Download failed', 'error');
            }
        } catch (e) {
            statusText.innerText = 'Connection error.';
            showNotification('Error connecting to download service', 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-download"></i> Download';
        }
    }
};

// Listen for tab changes from core.js
document.addEventListener('tabChanged', (e) => {
    if (e.detail.tab === 'local-models') {
        LocalModels.loadModels();
        LocalModels.loadSuggestedModels();
    }
});

// Polyfill showNotification if not exists
if (typeof showNotification === 'undefined') {
    window.showNotification = (msg, type) => {
        const t = type === 'danger' ? 'error' : (type || 'info');
        if (typeof showToast !== 'undefined') {
            showToast(msg, t);
        } else {
            console.warn(`[notification] ${type}: ${msg}`);
        }
    };
}

// Initialize on script load
LocalModels.init();
