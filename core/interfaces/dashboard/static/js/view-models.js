/**
 * Misaka Cipher - Local Models Management View
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
            const registryRes = await fetch('/api/registry/models');
            const registryData = await registryRes.json();
            const registeredModels = registryData.providers?.local?.models || {};

            const res = await fetch('/api/registry/local/models/status');
            const data = await res.json();
            const models = data.models || {};

            if (Object.keys(models).length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="placeholder-text">No models found in /LocalModels</td></tr>';
                return;
            }

            tbody.innerHTML = Object.entries(models).map(([filename, info]) => {
                const isRegistered = !!registeredModels[filename];
                return `
                    <tr>
                        <td><strong>${filename}</strong></td>
                        <td>${info.size_mb} MB</td>
                        <td>
                            ${isRegistered ? 
                                '<span style="color:#00b894; font-size:0.75rem; font-weight:bold;"><i class="fas fa-check-circle"></i> Registered</span>' : 
                                '<span style="color:#fab1a0; font-size:0.75rem; font-weight:bold;"><i class="fas fa-exclamation-circle"></i> Unregistered</span>'
                            }
                        </td>
                        <td style="display: flex; gap: 0.5rem; justify-content: flex-end;">
                            ${!isRegistered ? `
                                <button class="action-btn xs-btn register-model-btn" data-filename="${filename}" title="Register Model">
                                    <i class="fas fa-plus"></i> Register
                                </button>
                            ` : ''}
                            <button class="btn-icon xs-btn delete-model-btn" data-filename="${filename}" title="Delete Model" style="color:#ff7675;">
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
            tbody.innerHTML = '<tr><td colspan="4" class="placeholder-text" style="color:#ff7675;">Error loading models</td></tr>';
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

            grid.innerHTML = suggestions.map(model => `
                <div class="model-card suggestion-card" id="suggested-${model.id}" style="background: rgba(255,255,255,0.05); border-radius: 12px; padding: 1.25rem; border: 1px solid rgba(255,255,255,0.1); display: flex; flex-direction: column; transition: transform 0.2s, background 0.2s;">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.75rem;">
                        <h4 style="margin: 0; font-size: 1.1rem; color: #fff;">${model.name}</h4>
                        <span class="installed-badge" style="display: none; background: #00b894; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.7rem; font-weight: bold;">INSTALLED</span>
                    </div>
                    <p style="font-size: 0.85rem; color: #b2bec3; margin: 0 0 1rem 0; flex-grow: 1;">${model.description}</p>
                    <div style="display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap;">
                        ${model.tags.map(tag => `<span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 0.7rem;">${tag}</span>`).join('')}
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 0.8rem; font-weight: bold; color: #fab1a0;">${model.size}</span>
                        <button class="action-btn sm-btn install-btn" 
                                onclick="LocalModels.installSuggestedModel('${model.id}', '${model.repo}', '${model.filename}')"
                                style="font-size: 0.8rem; padding: 0.4rem 1rem;">
                            <i class="fas fa-download"></i> Install
                        </button>
                    </div>
                </div>
            `).join('');

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

        grid.querySelectorAll('.suggestion-card').forEach(card => {
            const installBtn = card.querySelector('.install-btn');
            const badge = card.querySelector('.installed-badge');
            
            // This is a bit naive, ideally we check repo too, but filename match is usually enough for local
            const modelId = card.id.replace('suggested-', '');
            // We need to find the filename for this modelId in suggestions
            // For now, let's just look at the button attributes or re-fetch (slow)
            // Let's assume the button still has the filename if we haven't overwritten it
            const installAction = installBtn.getAttribute('onclick');
            const filenameMatch = installAction.match(/'([^']+)'\s*\)$/);
            const filename = filenameMatch ? filenameMatch[1] : '';

            if (installedFiles.includes(filename)) {
                badge.style.display = 'block';
                installBtn.disabled = true;
                installBtn.innerHTML = '<i class="fas fa-check"></i> Installed';
                installBtn.classList.add('secondary');
            } else {
                badge.style.display = 'none';
                installBtn.disabled = false;
                installBtn.innerHTML = '<i class="fas fa-download"></i> Install';
                installBtn.classList.remove('secondary');
            }
        });
    },

    async installSuggestedModel(id, repo, filename) {
        const card = document.getElementById(`suggested-${id}`);
        const btn = card ? card.querySelector('.install-btn') : null;
        
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Installing...';
        }

        try {
            showNotification(`Starting installation of ${filename}...`, 'info');
            
            const res = await fetch('/api/registry/local/models/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ repo_id: repo, filename: filename })
            });

            const result = await res.json();
            if (res.ok) {
                showNotification(`Successfully installed ${filename}`, 'success');
                this.loadModels(); // This will also update suggested badges
            } else {
                showNotification(result.detail || 'Installation failed', 'error');
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-download"></i> Install';
                }
            }
        } catch (e) {
            showNotification('Error connecting to download service', 'error');
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-download"></i> Install';
            }
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
                // We might also need to notify the provider manager to reload,
                // but the backend endpoint already calls reload_config()
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
        if (typeof showToast !== 'undefined') {
            showToast(msg, type === 'error' ? 'danger' : type);
        } else {
            alert(`${type.toUpperCase()}: ${msg}`);
        }
    };
}

// Initialize on script load
LocalModels.init();
