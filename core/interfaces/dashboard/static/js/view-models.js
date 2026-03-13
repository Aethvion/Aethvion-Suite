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
            const res = await fetch('/api/registry/local/models/status');
            const data = await res.json();
            const models = data.models || {};

            if (Object.keys(models).length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="placeholder-text">No models found in /LocalModels</td></tr>';
                return;
            }

            tbody.innerHTML = Object.entries(models).map(([filename, info]) => `
                <tr>
                    <td><strong>${filename}</strong></td>
                    <td>${info.size_mb} MB</td>
                    <td><code style="font-size:0.75rem;">${info.path}</code></td>
                    <td>
                        <button class="btn-icon xs-btn delete-model-btn" data-filename="${filename}" title="Delete Model" style="color:#ff7675;">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                </tr>
            `).join('');

            // Add delete events
            tbody.querySelectorAll('.delete-model-btn').forEach(btn => {
                btn.onclick = () => this.deleteModel(btn.dataset.filename);
            });

        } catch (e) {
            console.error("Failed to load local models:", e);
            tbody.innerHTML = '<tr><td colspan="4" class="placeholder-text" style="color:#ff7675;">Error loading models</td></tr>';
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
