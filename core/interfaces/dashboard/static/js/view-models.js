/**
 * Aethvion Suite - Local Models Management View
 */

const LocalModels = {
    _models: {},
    _suggestions: [],
    _registered: {},
    _ollama: { models: [], registered: new Set(), running: false },
    _filters: { search: '', size: 'all', status: 'all', sort: 'name-asc', group: 'none' },

    init() {
        console.log("[LocalModels] Initializing...");
        this.addEventListeners();
        this.initFilters();
        
        const isAlreadyOnTab = typeof currentMainTab !== 'undefined' && currentMainTab === 'local-models';
        const isPanelInDom = !!document.getElementById('models-filter-panel');

        if (isAlreadyOnTab || isPanelInDom) {
            console.log("[LocalModels] UI detected, loading data...");
            this.loadAll();
        }
    },

    loadAll() {
        this.loadModels();
        this.loadSuggestedModels();
        this.loadGPUStatus();
        this.loadOllamaStatus();
    },

    addEventListeners() {
        const refreshBtn = document.getElementById('refresh-local-models');
        if (refreshBtn) refreshBtn.onclick = () => this.loadAll();

        const startDownloadBtn = document.getElementById('start-hf-download');
        if (startDownloadBtn) startDownloadBtn.onclick = () => this.startDownload();

        // Filter Listeners
        const searchInput = document.getElementById('model-search-input');
        if (searchInput) {
            searchInput.oninput = (e) => {
                this._filters.search = e.target.value.toLowerCase();
                this.applyFilters();
            };
        }

        ['filter-size', 'filter-status', 'sort-models', 'group-models'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.onchange = (e) => {
                const key = id.replace('filter-', '').replace('-models', '');
                this._filters[key] = e.target.value;
                this.applyFilters();
            };
        });

        const clearBtn = document.getElementById('clear-models-filters');
        if (clearBtn) {
            clearBtn.onclick = () => {
                if (searchInput) searchInput.value = '';
                const sizeEl = document.getElementById('filter-size');
                const statusEl = document.getElementById('filter-status');
                const sortEl = document.getElementById('sort-models');
                const groupEl = document.getElementById('group-models');
                
                if (sizeEl) sizeEl.value = 'all';
                if (statusEl) statusEl.value = 'all';
                if (sortEl) sortEl.value = 'name-asc';
                if (groupEl) groupEl.value = 'none';
                
                this._filters = { search: '', size: 'all', status: 'all', sort: 'name-asc', group: 'none' };
                this.applyFilters();
            };
        }
    },

    initFilters() {
        this._filters = { search: '', size: 'all', status: 'all', sort: 'name-asc', group: 'none' };
    },

    applyFilters() {
        this.renderModels();
        this.renderSuggestedModels();
        this.renderOllamaModels();
    },

    async loadModels() {
        try {
            const registryRes = await fetch('/api/registry');
            const registryData = await registryRes.json();
            this._registered = registryData.providers?.local?.models || {};

            const res = await fetch('/api/registry/local/models/status');
            const data = await res.json();
            this._models = data.models || {};

            if (typeof markPanelUpdated !== 'undefined') markPanelUpdated('models');
            this.renderModels();
            this.updateSuggestedBadges(Object.keys(this._models));

        } catch (e) {
            console.error("Failed to load local models:", e);
            const tbody = document.getElementById('local-models-list');
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="4" class="placeholder-text" style="color:#ff7675;">
                    Error loading models
                    <button class="action-btn small primary" style="margin-left:1rem;" onclick="LocalModels.loadModels()">
                        <i class="fas fa-rotate-right"></i> Retry
                    </button>
                </td></tr>`;
            }
        }
    },

    renderModels() {
        const tbody = document.getElementById('local-models-list');
        if (!tbody) return;

        let entries = Object.entries(this._models).map(([filename, info]) => {
            return {
                filename,
                ...info,
                isRegistered: !!this._registered[filename],
                bsize: this._getBSize(filename),
                creator: this._getCreator(filename),
                arch: this._getArch(filename)
            };
        });

        // Filter Search & Size & Status
        entries = entries.filter(m => {
            if (this._filters.search && !m.filename.toLowerCase().includes(this._filters.search)) return false;
            
            const sizeGb = m.size_mb / 1024;
            if (this._filters.size === 'small' && sizeGb >= 3) return false;
            if (this._filters.size === 'medium' && (sizeGb < 3 || sizeGb > 10)) return false;
            if (this._filters.size === 'large' && sizeGb <= 10) return false;

            if (this._filters.status === 'registered' && !m.isRegistered) return false;
            if (this._filters.status === 'unregistered' && m.isRegistered) return false;

            return true;
        });

        // Sort
        entries.sort((a, b) => {
            let res = 0;
            switch (this._filters.sort) {
                case 'name-asc':   res = a.filename.localeCompare(b.filename); break;
                case 'name-desc':  res = b.filename.localeCompare(a.filename); break;
                case 'size-asc':   res = a.size_mb - b.size_mb; break;
                case 'size-desc':  res = b.size_mb - a.size_mb; break;
                case 'params-asc': res = a.bsize - b.bsize; break;
                case 'params-desc':res = b.bsize - a.bsize; break;
            }
            return res;
        });

        if (entries.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="placeholder-text">No models match filters</td></tr>`;
            return;
        }

        // Grouping
        let html = '';
        if (this._filters.group === 'none') {
            html = entries.map(m => this._buildModelRow(m)).join('');
        } else {
            const groupKey = this._filters.group; // Usually 'arch'
            const groups = {};
            entries.forEach(m => {
                const val = m[groupKey] || 'Other';
                if (!groups[val]) groups[val] = [];
                groups[val].push(m);
            });

            Object.keys(groups).sort().forEach(groupName => {
                html += `<tr class="group-header-v12"><td colspan="4"><i class="fas fa-folder-open"></i> ${groupName} <span style="font-size:0.75rem; font-weight:400; opacity:0.6; margin-left:0.5rem;">(${groups[groupName].length} models)</span></td></tr>`;
                html += groups[groupName].map(m => this._buildModelRow(m)).join('');
            });
        }

        tbody.innerHTML = html;

        // Re-add events
        tbody.querySelectorAll('.delete-model-btn').forEach(btn => {
            btn.onclick = () => this.deleteModel(btn.dataset.filename);
        });
        tbody.querySelectorAll('.register-model-btn').forEach(btn => {
            btn.onclick = () => this.registerModel(btn.dataset.filename);
        });
    },

    _buildModelRow(m) {
        return `
            <tr class="faded-in-row">
                <td style="font-weight: 600; color: #fff;">
                    <div style="display:flex; flex-direction:column;">
                        <span>${m.filename}</span>
                        <span style="font-size:0.7rem; font-weight:400; color:var(--text-tertiary);">${m.arch} ${m.bsize ? `• ${m.bsize}B` : ''}</span>
                    </div>
                </td>
                <td style="color: var(--text-secondary);">${m.size_mb} MB</td>
                <td>
                    ${m.isRegistered ? 
                        '<span class="status-badge success-v12"><i class="fas fa-check-circle"></i> Registered</span>' : 
                        '<span class="status-badge warning-v12"><i class="fas fa-exclamation-circle"></i> Unregistered</span>'
                    }
                </td>
                <td style="display: flex; gap: 0.75rem; justify-content: flex-end; align-items: center;">
                    ${!m.isRegistered ? `
                        <button class="action-btn sm-btn register-model-btn" data-filename="${m.filename}" title="Register Model">
                            <i class="fas fa-plus"></i> Register
                        </button>
                    ` : ''}
                    <button class="btn-icon sm-btn delete-model-btn" data-filename="${m.filename}" title="Delete Model" style="color: rgba(255, 118, 117, 0.8);">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            </tr>
        `;
    },

    async loadSuggestedModels() {
        try {
            const res = await fetch('/api/registry/local/suggested');
            const data = await res.json();
            this._suggestions = data.suggested || [];
            this.renderSuggestedModels();

            // After loading suggestions, check which ones are already installed
            const localRes = await fetch('/api/registry/local/models/status');
            const localData = await localRes.json();
            this.updateSuggestedBadges(Object.keys(localData.models || {}));

        } catch (e) {
            console.error("Failed to load suggested models:", e);
            const grid = document.getElementById('suggested-models-grid');
            if (grid) grid.innerHTML = '<div class="placeholder-text" style="color:#ff7675;">Error loading suggestions</div>';
        }
    },

    renderSuggestedModels() {
        const grid = document.getElementById('suggested-models-grid');
        if (!grid) return;

        let filtered = this._suggestions.map(m => {
            const bsize = parseFloat(m.size) || this._getBSize(m.name || m.repo);
            return {
                ...m,
                bsize,
                creator: m.repo.split('/')[0],
                arch: this._getArch(m.name || m.repo)
            };
        });

        // Filter Search & Size & Status
        filtered = filtered.filter(model => {
            if (this._filters.search) {
                const inTitle = model.name.toLowerCase().includes(this._filters.search);
                const inRepo  = model.repo.toLowerCase().includes(this._filters.search);
                const inDesc  = (model.description || '').toLowerCase().includes(this._filters.search);
                if (!inTitle && !inRepo && !inDesc) return false;
            }

            const sizeMatch = (model.size || '').match(/(\d+\.?\d*)\s*GB/i);
            if (sizeMatch && this._filters.size !== 'all') {
                const val = parseFloat(sizeMatch[1]);
                if (this._filters.size === 'small' && val >= 3) return false;
                if (this._filters.size === 'medium' && (val < 3 || val > 10)) return false;
                if (this._filters.size === 'large' && val <= 10) return false;
            }

            if (this._filters.status === 'supported' && model.unsupported) return false;
            return true;
        });

        // Sort
        filtered.sort((a, b) => {
            let res = 0;
            switch (this._filters.sort) {
                case 'name-asc':   res = a.name.localeCompare(b.name); break;
                case 'name-desc':  res = b.name.localeCompare(a.name); break;
                case 'size-asc':
                case 'size-desc':
                    const sA = parseFloat(a.size) || 0;
                    const sB = parseFloat(b.size) || 0;
                    res = this._filters.sort.endsWith('asc') ? sA - sB : sB - sA;
                    break;
                case 'params-asc': res = a.bsize - b.bsize; break;
                case 'params-desc':res = b.bsize - a.bsize; break;
            }
            return res;
        });

        if (filtered.length === 0) {
            grid.innerHTML = '<div class="placeholder-text">No suggestions match filters</div>';
            return;
        }

        let html = '';
        if (this._filters.group === 'none') {
            html = filtered.map(m => this._buildSuggestedCard(m)).join('');
        } else {
            const groupKey = this._filters.group; // Usually 'arch'
            const groups = {};
            filtered.forEach(m => {
                const val = m[groupKey] || 'Other';
                if (!groups[val]) groups[val] = [];
                groups[val].push(m);
            });

            Object.keys(groups).sort().forEach(groupName => {
                html += `<div class="group-section-v12" style="grid-column: 1 / -1;">
                            <h3 class="group-title-v12"><i class="fas fa-folder-open"></i> ${groupName} <span>(${groups[groupName].length})</span></h3>
                            <div class="group-grid-container-v12">
                                ${groups[groupName].map(m => this._buildSuggestedCard(m)).join('')}
                            </div>
                         </div>`;
            });
        }

        grid.innerHTML = html;
    },

    _buildSuggestedCard(model) {
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
        <div class="suggestion-card-v12 faded-in-card" id="suggested-${model.id}" style="${isUnsupported ? 'opacity: 0.6;' : ''}">
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

    async loadGPUStatus() {
        const statusRow  = document.getElementById('gpu-status-row');
        const settingsEl = document.getElementById('gpu-settings-form');
        if (!statusRow) return;

        try {
            const [gpuRes, cfgRes] = await Promise.all([
                fetch('/api/registry/local/gpu-status'),
                fetch('/api/registry/local/inference-config'),
            ]);
            const gpu = gpuRes.ok ? await gpuRes.json() : {};
            const cfg = cfgRes.ok ? await cfgRes.json() : { n_gpu_layers: -1, n_ctx: 4096, n_threads: -1 };

            const slider = document.getElementById('gpu-layers-slider');
            const numIn  = document.getElementById('gpu-layers-input');
            const ctxSel = document.getElementById('gpu-ctx-select');
            const thrIn  = document.getElementById('gpu-threads-input');
            if (slider) slider.value = cfg.n_gpu_layers;
            if (numIn)  numIn.value  = cfg.n_gpu_layers;
            if (ctxSel) ctxSel.value = cfg.n_ctx;
            if (thrIn)  thrIn.value  = cfg.n_threads;

            if (slider && numIn) {
                slider.oninput = () => { numIn.value = slider.value; };
                numIn.oninput  = () => { slider.value = numIn.value; };
            }

            let html = '';
            if (gpu.cuda_available && gpu.gpu_name) {
                html += `<span class="gpu-badge gpu-badge-ok"><i class="fas fa-check-circle"></i> ${gpu.gpu_name} · ${gpu.vram_gb} GB VRAM</span>`;
            } else {
                html += `<span class="gpu-badge gpu-badge-off"><i class="fas fa-microchip"></i> No CUDA GPU detected</span>`;
            }

            if (gpu.llama_cuda) {
                html += `<span class="gpu-badge gpu-badge-ok"><i class="fas fa-bolt"></i> llama.cpp CUDA build</span>`;
                if (settingsEl) settingsEl.style.display = '';
            } else {
                html += `<span class="gpu-badge gpu-badge-warn"><i class="fas fa-exclamation-triangle"></i> llama.cpp CPU-only</span>`;
                html += `<button class="action-btn primary" style="margin-left:auto;" onclick="LocalModels.installCudaLlama(this)">
                    <i class="fas fa-bolt"></i> Install CUDA Build
                </button>`;
                if (settingsEl) settingsEl.style.display = '';
            }
            statusRow.innerHTML = html;

        } catch (e) {
            statusRow.innerHTML = `<span class="gpu-badge gpu-badge-off"><i class="fas fa-question-circle"></i> Status unavailable</span>`;
        }
    },

    async installCudaLlama(btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Installing…';

        const panel = document.getElementById('gpu-config-panel');
        let logEl = panel?.querySelector('.gpu-install-log');
        if (panel && !logEl) {
            logEl = document.createElement('div');
            logEl.className = 'gpu-install-log am-install-log';
            logEl.innerHTML = `
                <div class="am-log-header">
                    <span class="am-log-title"><i class="fas fa-terminal"></i> Installing llama-cpp-python (CUDA)…</span>
                    <span class="am-log-pct">0%</span>
                </div>
                <div class="am-log-bar-wrap"><div class="am-log-bar"></div></div>
                <pre class="am-log-output"></pre>`;
            panel.appendChild(logEl);
        }

        const logTitle  = logEl?.querySelector('.am-log-title');
        const logPct    = logEl?.querySelector('.am-log-pct');
        const logBar    = logEl?.querySelector('.am-log-bar');
        const logOutput = logEl?.querySelector('.am-log-output');
        if (logBar)   { logBar.style.width = '5%'; logBar.className = 'am-log-bar'; }
        if (logOutput) logOutput.textContent = '';

        try {
            const resp = await fetch('/api/registry/local/install-cuda-llama', { method: 'POST' });
            const reader  = resp.body.getReader();
            const decoder = new TextDecoder();
            let   buffer  = '';
            let   lines   = 0;

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

                    if (msg.line !== undefined) {
                        if (logOutput) { logOutput.textContent += msg.line + '\n'; logOutput.scrollTop = logOutput.scrollHeight; }
                        lines++;
                        const pct = Math.min(5 + lines * 1.5, 90);
                        if (logBar) logBar.style.width = pct + '%';
                        if (logPct) logPct.textContent = Math.round(pct) + '%';
                    } else if (msg.done) {
                        if (logBar) logBar.style.width = '100%';
                        if (logPct) logPct.textContent = '100%';
                        if (msg.success) {
                            if (logBar)   logBar.classList.add('am-bar-done');
                            if (logTitle) logTitle.innerHTML = '<i class="fas fa-check-circle" style="color:#34d399"></i> Installed — restart Aethvion to activate';
                            showNotification('CUDA llama-cpp-python installed — please restart Aethvion Suite', 'success');
                            setTimeout(() => this.loadGPUStatus(), 1000);
                        } else {
                            if (logBar)   logBar.classList.add('am-bar-fail');
                            if (logTitle) logTitle.innerHTML = '<i class="fas fa-times-circle" style="color:#f87171"></i> Install failed — see log above';
                            showNotification('Installation failed', 'error');
                            btn.disabled = false;
                            btn.innerHTML = '<i class="fas fa-redo"></i> Retry';
                        }
                    }
                }
            }
        } catch (e) {
            showNotification(`Error: ${e.message}`, 'error');
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-bolt"></i> Install CUDA Build';
        }
    },

    async saveGPUConfig() {
        const saveStatus = document.getElementById('gpu-save-status');
        const n_gpu_layers = parseInt(document.getElementById('gpu-layers-input')?.value ?? -1);
        const n_ctx        = parseInt(document.getElementById('gpu-ctx-select')?.value   ?? 4096);
        const n_threads    = parseInt(document.getElementById('gpu-threads-input')?.value ?? -1);

        try {
            const r = await fetch('/api/registry/local/inference-config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ n_gpu_layers, n_ctx, n_threads }),
            });
            if (r.ok) {
                if (saveStatus) {
                    saveStatus.textContent = '✓ Saved — takes effect on next model load';
                    setTimeout(() => { saveStatus.textContent = ''; }, 4000);
                }
                showNotification('GPU config saved', 'success');
            } else {
                showNotification('Failed to save GPU config', 'error');
            }
        } catch (e) {
            showNotification('Error saving GPU config', 'error');
        }
    },

    async loadOllamaStatus() {
        const statusRow  = document.getElementById('ollama-status-row');
        const modelsSection = document.getElementById('ollama-models-section');
        if (!statusRow) return;

        try {
            const [statusRes, registryRes] = await Promise.all([
                fetch('/api/ollama/status'),
                fetch('/api/registry').catch(() => ({ ok: false })),
            ]);
            const status = statusRes.ok ? await statusRes.json() : { running: false };
            const registry = registryRes.ok ? await registryRes.json() : {};

            this._ollama.running = status.running || false;
            this._ollama.models = status.models || [];
            this._ollama.registered = new Set(
                Object.keys(registry.providers?.ollama?.models || {})
            );

            if (!this._ollama.running) {
                statusRow.innerHTML = `
                    <span class="gpu-badge gpu-badge-off"><i class="fas fa-circle"></i> Ollama not running</span>
                    <span class="gpu-badge-hint">
                        <a href="https://ollama.com/download" target="_blank" style="color:var(--primary)">Download Ollama</a>
                        — install it and run <code>ollama serve</code>, then refresh.
                    </span>`;
                if (modelsSection) modelsSection.style.display = 'none';
                return;
            }

            statusRow.innerHTML = `
                <span class="gpu-badge gpu-badge-ok"><i class="fas fa-circle"></i> Ollama running</span>
                <span style="font-size:0.8rem; color:var(--text-tertiary);">${this._ollama.models.length} model${this._ollama.models.length !== 1 ? 's' : ''} available</span>
                <button class="action-btn secondary" style="margin-left:auto;" onclick="LocalModels.loadOllamaStatus()">
                    <i class="fas fa-sync-alt"></i> Refresh
                </button>`;
            if (modelsSection) modelsSection.style.display = '';

            this.renderOllamaModels();

        } catch (e) {
            statusRow.innerHTML = `<span class="gpu-badge gpu-badge-off">Status unavailable</span>`;
        }
    },

    renderOllamaModels() {
        const listEl = document.getElementById('ollama-models-list');
        if (!listEl) return;

        if (!this._ollama.running) return;

        let filtered = this._ollama.models.map(name => {
            return {
                name,
                isReg: this._ollama.registered.has(name),
                bsize: this._getBSize(name),
                creator: this._getCreator(name),
                arch: this._getArch(name)
            };
        });

        filtered = filtered.filter(m => {
            if (this._filters.search && !m.name.toLowerCase().includes(this._filters.search)) return false;
            
            if (this._filters.status === 'registered' && !m.isReg) return false;
            if (this._filters.status === 'unregistered' && m.isReg) return false;

            return true;
        });

        filtered.sort((a, b) => {
            let res = 0;
            switch (this._filters.sort) {
                case 'name-asc':   res = a.name.localeCompare(b.name); break;
                case 'name-desc':  res = b.name.localeCompare(a.name); break;
                case 'params-asc': res = a.bsize - b.bsize; break;
                case 'params-desc':res = b.bsize - a.bsize; break;
            }
            return res;
        });

        if (!filtered.length) {
            listEl.innerHTML = '<p class="placeholder-text">No Ollama models match filters.</p>';
            return;
        }

        let html = '';
        if (this._filters.group === 'none') {
            html = filtered.map(m => this._buildOllamaCard(m)).join('');
        } else {
            const groupKey = this._filters.group; // Usually 'arch'
            const groups = {};
            filtered.forEach(m => {
                const val = m[groupKey] || 'Other';
                if (!groups[val]) groups[val] = [];
                groups[val].push(m);
            });

            Object.keys(groups).sort().forEach(groupName => {
                html += `<div class="ollama-group-header-v12" style="width: 100%; margin: 1rem 0 0.5rem 0; padding: 0.5rem; background: rgba(255,255,255,0.03); border-radius: 8px; border-left: 3px solid var(--primary); font-family: 'Outfit'; font-size: 0.9rem; font-weight: 600; color: var(--text-secondary);"><i class="fas fa-folder-open" style="margin-right:0.5rem;"></i> ${groupName} <span style="font-weight:400; opacity:0.6; font-size:0.75rem;">(${groups[groupName].length})</span></div>`;
                html += groups[groupName].map(m => this._buildOllamaCard(m)).join('');
            });
        }

        listEl.innerHTML = html;
    },

    _buildOllamaCard(m) {
        return `<div class="ollama-model-card ${m.isReg ? 'ollama-registered' : ''}" id="ollama-card-${CSS.escape(m.name)}">
            <div class="ollama-model-name">
                ${m.name}
                <div style="font-size:0.65rem; font-weight:400; color:var(--text-tertiary); margin-top:0.1rem;">${m.arch} ${m.bsize ? `• ${m.bsize}B` : ''}</div>
            </div>
            <div class="ollama-model-btns">
                <button class="action-btn ${m.isReg ? 'success' : 'primary'} sm-btn"
                    onclick="LocalModels.toggleOllamaModel('${m.name}', ${m.isReg})"
                    ${m.isReg ? 'disabled' : ''}>
                    <i class="fas fa-${m.isReg ? 'check-circle' : 'plus-circle'}"></i>
                    ${m.isReg ? 'In Registry' : 'Add to Aethvion'}
                </button>
                <button class="action-btn secondary sm-btn"
                    onclick="LocalModels.deleteOllamaModel('${m.name}')">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>`;
    },

    _getBSize(text) {
        if (!text) return 0;
        const match = text.match(/(\d+\.?\d*)\s*[Bb]/);
        return match ? parseFloat(match[1]) : 0;
    },

    _getCreator(text) {
        if (!text) return 'Other';
        if (text.includes('-')) return text.split('-')[0];
        if (text.includes('/')) return text.split('/')[0];
        return 'Other';
    },

    _getArch(text) {
        if (!text) return 'LLM';
        const t = text.toLowerCase();
        if (t.includes('llama')) return 'Llama';
        if (t.includes('mistral')) return 'Mistral';
        if (t.includes('mixtral')) return 'Mixtral';
        if (t.includes('phi')) return 'Phi';
        if (t.includes('gemma')) return 'Gemma';
        if (t.includes('qwen')) return 'Qwen';
        if (t.includes('deepseek')) return 'DeepSeek';
        if (t.includes('command')) return 'Command';
        if (t.includes('stable')) return 'StableLM';
        if (t.includes('coder')) return 'Coder';
        return 'General';
    },

    async pullOllamaModel() {
        const input   = document.getElementById('ollama-pull-name');
        const progEl  = document.getElementById('ollama-pull-progress');
        const barEl   = document.getElementById('ollama-pull-bar');
        const labelEl = document.getElementById('ollama-pull-label');
        const pctEl   = document.getElementById('ollama-pull-pct');
        const name    = input?.value?.trim();
        if (!name) { showNotification('Enter a model name', 'warning'); return; }

        if (progEl) progEl.style.display = '';
        if (barEl)  { barEl.style.width = '0%'; barEl.className = 'model-dl-bar'; }
        if (labelEl) labelEl.textContent = 'Pulling…';
        if (pctEl)   pctEl.textContent   = '0%';

        try {
            const resp = await fetch('/api/ollama/pull', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: name }),
            });
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

                    if (msg.status && !msg.done) {
                        if (labelEl) labelEl.textContent = msg.status;
                        if (msg.pct > 0) {
                            if (barEl) barEl.style.width = msg.pct + '%';
                            if (pctEl) pctEl.textContent = msg.pct + '%';
                        }
                    } else if (msg.done) {
                        if (msg.success) {
                            if (barEl)  { barEl.style.width = '100%'; barEl.classList.add('dl-bar-done'); }
                            if (labelEl) labelEl.textContent = 'Complete!';
                            if (pctEl)   pctEl.textContent   = '100%';
                            if (input)   input.value = '';
                            showNotification(`${name} pulled successfully`, 'success');
                            setTimeout(() => this.loadOllamaStatus(), 600);
                        } else {
                            if (barEl) barEl.classList.add('dl-bar-fail');
                            if (labelEl) labelEl.textContent = 'Failed';
                            showNotification(`Pull failed: ${msg.error || 'unknown error'}`, 'error');
                        }
                    }
                }
            }
        } catch (e) {
            showNotification(`Error: ${e.message}`, 'error');
        }
    },

    async toggleOllamaModel(name, isRegistered) {
        if (isRegistered) return;
        try {
            const r = await fetch('/api/ollama/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: name }),
            });
            if (r.ok) {
                showNotification(`${name} added to Aethvion registry`, 'success');
                this.loadOllamaStatus();
            } else {
                showNotification('Registration failed', 'error');
            }
        } catch (e) {
            showNotification('Error', 'error');
        }
    },

    async deleteOllamaModel(name) {
        if (!confirm(`Delete Ollama model "${name}"? This removes it from disk.`)) return;
        try {
            const r = await fetch('/api/ollama/model', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: name }),
            });
            if (r.ok) {
                showNotification(`${name} deleted`, 'success');
                this.loadOllamaStatus();
            }
        } catch (e) {
            showNotification('Delete failed', 'error');
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

// Also re-init when the panel is loaded via PartialLoader
document.addEventListener('panelLoaded', (e) => {
    if (e.detail && e.detail.tabName === 'local-models') {
        console.log("[LocalModels] Panel detected via event, re-initializing...");
        LocalModels.init();
    }
});

// Export to window for inline onclick handlers
window.LocalModels = LocalModels;
