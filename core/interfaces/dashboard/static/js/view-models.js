/**
 * Aethvion Suite - Local Models Management View
 */

const LocalModels = {
    _models: {},
    _suggestions: [],
    _registered: {},
    _arenaData: {},
    _ollama: { models: [], registered: new Set(), running: false },
    _filters: { search: '', sort: 'name-asc', group: 'none' },
    _systemSpecs: null,
    _infoCache: {},

    // ── Provider brand metadata ───────────────────────────────────────────────
    _PROVIDER_BRANDS: {
        Google:    { accent: '#4285f4', bg: 'rgba(66,133,244,0.08)',   icon: 'fab fa-google',   desc: 'Gemma series — Google\'s efficient open models for local inference' },
        Meta:      { accent: '#0082fb', bg: 'rgba(0,130,251,0.08)',    icon: 'fas fa-infinity',  desc: 'Llama series — Meta\'s open-weight foundation models' },
        Microsoft: { accent: '#00a4ef', bg: 'rgba(0,164,239,0.08)',    icon: 'fab fa-windows',  desc: 'Phi series — small but highly capable language models' },
        Alibaba:   { accent: '#ff6a00', bg: 'rgba(255,106,0,0.08)',    icon: 'fas fa-cloud',    desc: 'Qwen series — multilingual models from Alibaba Cloud' },
        DeepSeek:  { accent: '#1a56db', bg: 'rgba(26,86,219,0.08)',    icon: 'fas fa-water',    desc: 'DeepSeek — advanced reasoning and code-focused models' },
        NVIDIA:    { accent: '#76b900', bg: 'rgba(118,185,0,0.08)',    icon: 'fas fa-bolt',     desc: 'NVIDIA — models optimised for local GPU inference' },
        Mistral:   { accent: '#f97316', bg: 'rgba(249,115,22,0.08)',   icon: 'fas fa-wind',     desc: 'Mistral AI — efficient open models from Europe' },
        Other:     { accent: '#6366f1', bg: 'rgba(99,102,241,0.08)',   icon: 'fas fa-cube',     desc: 'Additional models available for local inference' },
    },

    _getProviderFromTags(tags) {
        if (!tags || !tags.length) return 'Other';
        const priority = ['DeepSeek', 'Meta', 'Microsoft', 'Alibaba', 'Mistral', 'Google', 'NVIDIA'];
        for (const p of priority) {
            if (tags.some(t => t.toLowerCase() === p.toLowerCase())) return p;
        }
        return 'Other';
    },

    init() {
        console.log("[LocalModels] Initializing...");
        this.addEventListeners();
        this.initFilters();
        
        const isAlreadyOnTab = typeof currentMainTab !== 'undefined' && currentMainTab === 'local-models';
        const isPanelInDom = !!document.getElementById('suggested-models-grid');

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
        this.loadArenaData();
        this.loadSystemSpecs(false);
    },

    async loadArenaData() {
        try {
            const res = await fetch('/api/arena/leaderboard');
            if (res.ok) {
                const data = await res.json();
                this._arenaData = data.models || {};
            }
        } catch (e) {
            this._arenaData = {};
        }
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

        ['sort-models', 'group-models'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.onchange = (e) => {
                const key = id === 'sort-models' ? 'sort' : 'group';
                this._filters[key] = e.target.value;
                this.applyFilters();
            };
        });

        const clearBtn = document.getElementById('clear-models-filters');
        if (clearBtn) {
            clearBtn.onclick = () => {
                if (searchInput) searchInput.value = '';
                const sortEl  = document.getElementById('sort-models');
                const groupEl = document.getElementById('group-models');
                if (sortEl)  sortEl.value  = 'name-asc';
                if (groupEl) groupEl.value = 'none';
                this._filters = { search: '', sort: 'name-asc', group: 'none' };
                this.applyFilters();
            };
        }
    },

    initFilters() {
        this._filters = { search: '', sort: 'name-asc', group: 'none' };
    },

    applyFilters() {
        this.renderModels();
        this.renderSuggestedModels();
        this.renderOllamaModels();
    },

    async loadModels() {
        try {
            // First fetch local status so new files are auto-registered
            const res = await fetch('/api/registry/local/models/status');
            const data = await res.json();
            this._models = data.models || {};

            // Then fetch registry which will now contain the auto-registered models
            const registryRes = await fetch('/api/registry');
            const registryData = await registryRes.json();
            this._registered = registryData.providers?.local?.models || {};

            if (typeof markPanelUpdated !== 'undefined') markPanelUpdated('models');
            this.renderModels();
            this.updateSuggestedBadges(Object.keys(this._models));

        } catch (e) {
            console.error("Failed to load local models:", e);
            const container = document.getElementById('local-models-list');
            if (container) {
                container.innerHTML = `<div class="ae-empty" style="grid-column:1/-1;"><div class="ae-empty-icon error"><i class="fas fa-triangle-exclamation"></i></div><div class="ae-empty-title">Failed to load models</div><div class="ae-empty-desc">Check your connection and try again.</div><button class="action-btn primary ae-empty-action" onclick="LocalModels.loadModels()"><i class="fas fa-rotate-right"></i> Retry</button></div>`;
            }
        }
    },

    renderModels() {
        const container = document.getElementById('local-models-list');
        if (!container) return;

        let entries = Object.entries(this._models).map(([filename, info]) => {
            return {
                filename,
                ...info,
                isRegistered: !!this._registered[filename],
                bsize: this._getBSize(filename),
                creator: this._getCreator(filename),
                arch: this._getArch(filename),
                company: this._getCompany(filename)
            };
        });

        // Filter by search
        entries = entries.filter(m => {
            if (this._filters.search && !m.filename.toLowerCase().includes(this._filters.search)) return false;
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
                case 'arena-score-desc': {
                    const sa = this._arenaData[a.filename];
                    const sb = this._arenaData[b.filename];
                    const scoreA = sa && sa.scores_count > 0 ? sa.scores_total / sa.scores_count : -1;
                    const scoreB = sb && sb.scores_count > 0 ? sb.scores_total / sb.scores_count : -1;
                    res = scoreB - scoreA;
                    break;
                }
                case 'win-rate-desc': {
                    const wa = this._arenaData[a.filename];
                    const wb = this._arenaData[b.filename];
                    const rateA = wa && wa.battles > 0 ? wa.wins / wa.battles : -1;
                    const rateB = wb && wb.battles > 0 ? wb.wins / wb.battles : -1;
                    res = rateB - rateA;
                    break;
                }
                case 'speed-asc': {
                    const qa = this._arenaData[a.filename];
                    const qb = this._arenaData[b.filename];
                    const timeA = qa && qa.battles > 0 ? qa.total_time_ms / qa.battles : Infinity;
                    const timeB = qb && qb.battles > 0 ? qb.total_time_ms / qb.battles : Infinity;
                    res = timeA - timeB;
                    break;
                }
            }
            return res;
        });

        if (entries.length === 0) {
            container.innerHTML = `<div class="ae-empty" style="grid-column:1/-1;"><div class="ae-empty-icon"><i class="fas fa-microchip"></i></div><div class="ae-empty-title">No models downloaded yet</div><div class="ae-empty-desc">Install a model from the catalogue above, or download from Hugging Face below.</div></div>`;
            return;
        }

        // Grouping
        let html = '';
        if (this._filters.group === 'none') {
            html = entries.map(m => this._buildModelRow(m)).join('');
        } else {
            const groupKey = this._filters.group;
            const groups = {};
            entries.forEach(m => {
                const val = m[groupKey] || 'Other';
                if (!groups[val]) groups[val] = [];
                groups[val].push(m);
            });

            Object.keys(groups).sort().forEach(groupName => {
                html += `<div class="lm-dl-group-hd" style="grid-column:1/-1;"><i class="fas fa-folder-open"></i> ${groupName} <span>(${groups[groupName].length} models)</span></div>`;
                html += groups[groupName].map(m => this._buildModelRow(m)).join('');
            });
        }

        container.innerHTML = html;

        // Re-attach delete events
        container.querySelectorAll('.delete-model-btn').forEach(btn => {
            btn.onclick = () => this.deleteModel(btn.dataset.filename);
        });
    },

    _buildModelRow(m) {
        const arena = this._arenaData[m.filename];
        let arenaHtml = '';
        if (arena && arena.battles > 0) {
            const winRate = Math.round((arena.wins / arena.battles) * 100);
            arenaHtml = `<span class="hub-tag" style="background:rgba(99,102,241,0.1); color:#818cf8;">${winRate}% Arena Winrate</span>`;
        }

        return `
        <div class="hub-card faded-in-row">
            <div class="hub-card-top">
                <div class="hub-model-icon"><i class="fas fa-file-code"></i></div>
                <div style="display:flex; gap:0.4rem;">
                    <span class="hub-status-badge installed">Ready</span>
                    <button class="hub-dl-del delete-model-btn" data-filename="${m.filename}" 
                            style="background:none; border:none; color:var(--text-tertiary); cursor:pointer;">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
            
            <div class="hub-model-info">
                <h3 style="font-family:'Fira Code', monospace; font-size:0.8rem; word-break:break-all;">${m.filename}</h3>
                <p>${m.arch} Architecture · ${(m.size_mb/1024).toFixed(1)} GB</p>
            </div>

            <div class="hub-tags">
                <span class="hub-tag">${m.bsize ? `${m.bsize}B Parameters` : 'Unknown Size'}</span>
                ${arenaHtml}
            </div>

            <div class="hub-card-footer">
                <div class="hub-meta-info">
                   <i class="fas fa-check-double" style="color:#4ade80;"></i> Optimized & Verified
                </div>
                <button class="hub-action-btn secondary" onclick="switchMainTab('chat')">
                    <i class="fas fa-comment"></i> Chat
                </button>
            </div>
        </div>`;
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
            if (grid) grid.innerHTML = `<div class="ae-empty"><div class="ae-empty-icon error"><i class="fas fa-triangle-exclamation"></i></div><div class="ae-empty-title">Failed to load suggestions</div><div class="ae-empty-desc">Check your connection and try again.</div></div>`;
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
                arch: this._getArch(m.name || m.repo),
                company: this._getCompany(m.name || m.repo),
                provider: this._getProviderFromTags(m.tags),
            };
        });

        // Filter by search
        filtered = filtered.filter(model => {
            if (this._filters.search) {
                const inTitle = model.name.toLowerCase().includes(this._filters.search);
                const inRepo  = model.repo.toLowerCase().includes(this._filters.search);
                const inDesc  = (model.description || '').toLowerCase().includes(this._filters.search);
                const inTags  = (model.tags || []).some(t => t.toLowerCase().includes(this._filters.search));
                if (!inTitle && !inRepo && !inDesc && !inTags) return false;
            }
            return true;
        });

        // Sort within each provider section
        filtered.sort((a, b) => {
            let res = 0;
            switch (this._filters.sort) {
                case 'name-asc':   res = a.name.localeCompare(b.name); break;
                case 'name-desc':  res = b.name.localeCompare(a.name); break;
                case 'size-asc':
                case 'size-desc': {
                    const sA = parseFloat(a.size) || 0;
                    const sB = parseFloat(b.size) || 0;
                    res = this._filters.sort.endsWith('asc') ? sA - sB : sB - sA;
                    break;
                }
                case 'params-asc': res = a.bsize - b.bsize; break;
                case 'params-desc':res = b.bsize - a.bsize; break;
            }
            return res;
        });

        if (filtered.length === 0) {
            grid.innerHTML = `<div class="ae-empty"><div class="ae-empty-icon"><i class="fas fa-filter"></i></div><div class="ae-empty-title">No models match your search</div><div class="ae-empty-desc">Try adjusting or clearing your filter.</div></div>`;
            return;
        }

        // Group by provider in a fixed display order
        const providerOrder = ['Google', 'Meta', 'Microsoft', 'Alibaba', 'DeepSeek', 'NVIDIA', 'Mistral', 'Other'];
        const groups = {};
        filtered.forEach(m => {
            const prov = m.provider || 'Other';
            if (!groups[prov]) groups[prov] = [];
            groups[prov].push(m);
        });

        let html = '';
        providerOrder.forEach(provName => {
            const models = groups[provName];
            if (!models || models.length === 0) return;
            const brand = this._PROVIDER_BRANDS[provName] || this._PROVIDER_BRANDS.Other;
            html += `
            <div class="hub-provider-section">
                <div class="hub-provider-hd">
                    <div class="hub-provider-dot" style="--brand-color: ${brand.accent};"></div>
                    <h2 class="hub-provider-name">${provName}</h2>
                </div>
                <div class="hub-grid">
                    ${models.map(m => this._buildSuggestedCard(m)).join('')}
                </div>
            </div>`;
        });

        grid.innerHTML = html;
    },

    _buildSuggestedCard(model) {
        const isUnsupported = !!model.unsupported;
        const compatBadge   = this._getCompatBadge(model);
        const brand = this._PROVIDER_BRANDS[model.provider] || this._PROVIDER_BRANDS.Other;

        const actionHtml = isUnsupported
            ? `<span class="hub-status-badge">Incompatible</span>`
            : `<div style="display:flex; gap:0.4rem; justify-content:flex-end;">
                   <button class="hub-action-btn delete-btn" style="display:none; padding: 0.6rem; color: #ef4444; background: rgba(239, 68, 68, 0.1); border-color: rgba(239, 68, 68, 0.2);"
                           onclick="LocalModels.deleteModel('${model.filename}')" title="Delete Model">
                       <i class="fas fa-trash"></i>
                   </button>
                   <button class="hub-action-btn install-btn"
                           onclick="LocalModels.installSuggestedModel('${model.id}', '${model.repo}', '${model.filename}')">
                       <i class="fas fa-download"></i> Install
                   </button>
               </div>`;

        return `
        <div class="hub-card suggestion-card-v12 faded-in-card" id="suggested-${model.id}" 
             style="--brand-color: ${brand.accent}; ${isUnsupported ? 'opacity:0.6;' : ''}">
            <div class="hub-card-top">
                <div class="hub-model-icon"><i class="${brand.icon}"></i></div>
                <span class="hub-status-badge installed-badge" style="display:none;">Owned</span>
            </div>
            
            <div class="hub-model-info">
                <h3>${model.name}</h3>
                <p>${model.description}</p>
            </div>

            <div class="hub-tags">
                ${(model.tags || []).map(tag => `<span class="hub-tag">${tag}</span>`).join('')}
            </div>

            <div class="hub-card-footer">
                <div class="hub-meta-info">
                   <i class="fas fa-weight-hanging"></i> ${model.size}
                   ${compatBadge}
                </div>
                ${actionHtml}
            </div>
            <div class="sug-info-panel" id="sug-info-${model.id}" style="display:none;"></div>
        </div>`;
    },

    _getCompatBadge(model) {
        if (!this._systemSpecs) return '';
        const vram = this._systemSpecs.vram_gb || 0;
        const ram  = this._systemSpecs.ram_total_gb || 0;

        // Parse model size in GB from size string like "4.1 GB" or "7B"
        let sizeGb = 0;
        const gbMatch = (model.size || '').match(/(\d+\.?\d*)\s*GB/i);
        const bMatch  = (model.size || '').match(/(\d+\.?\d*)B/i);
        if (gbMatch)     sizeGb = parseFloat(gbMatch[1]);
        else if (bMatch) sizeGb = parseFloat(bMatch[1]) * 0.6; // rough Q4 estimate

        if (sizeGb === 0) return '';

        let cls, label, icon;
        if (vram >= sizeGb * 1.1) {
            cls = 'compat-great'; label = 'Runs on GPU'; icon = 'fa-bolt';
        } else if (vram >= sizeGb * 0.6) {
            cls = 'compat-good';  label = 'Partial GPU';  icon = 'fa-microchip';
        } else if (ram >= sizeGb * 1.2) {
            cls = 'compat-ok';    label = 'CPU Only';      icon = 'fa-server';
        } else {
            cls = 'compat-heavy'; label = 'Very Heavy';    icon = 'fa-triangle-exclamation';
        }
        return `<span class="compat-badge ${cls}" title="Based on your ${vram}GB VRAM / ${ram}GB RAM"><i class="fas ${icon}"></i> ${label}</span>`;
    },

    async loadSystemSpecs(forceRefresh = false) {
        const row = document.getElementById('system-specs-row');

        // Use cached specs if available and not forcing refresh
        if (this._systemSpecs && !forceRefresh) {
            this._renderSpecsRow(row, this._systemSpecs);
            return;
        }

        if (row) row.innerHTML = '<span class="placeholder-text"><i class="fas fa-spinner fa-spin"></i> Detecting hardware…</span>';

        try {
            const res = await fetch('/api/registry/local/system-specs');
            if (!res.ok) throw new Error('failed');
            const specs = await res.json();
            this._systemSpecs = specs;
            this._renderSpecsRow(row, specs);
            // Re-render suggested cards to show compat badges
            this.renderSuggestedModels();
        } catch (e) {
            if (row) row.innerHTML = '<span class="placeholder-text">Could not detect hardware</span>';
        }
    },

    _renderSpecsRow(row, specs) {
        if (!row) return;
        const chips = [];

        if (specs.cpu_name && specs.cpu_name !== 'Unknown') {
            chips.push(`<div class="spec-chip">
                <i class="fas fa-microchip"></i>
                <div><span class="spec-chip-label">CPU</span><span class="spec-chip-value">${specs.cpu_name}</span></div>
            </div>`);
        }
        if (specs.cpu_cores) {
            chips.push(`<div class="spec-chip">
                <i class="fas fa-layer-group"></i>
                <div><span class="spec-chip-label">Cores / Threads</span><span class="spec-chip-value">${specs.cpu_cores}C / ${specs.cpu_threads}T</span></div>
            </div>`);
        }
        if (specs.ram_total_gb) {
            chips.push(`<div class="spec-chip">
                <i class="fas fa-memory"></i>
                <div><span class="spec-chip-label">System RAM</span><span class="spec-chip-value">${specs.ram_total_gb} GB</span></div>
            </div>`);
        }
        if (specs.gpu_name) {
            chips.push(`<div class="spec-chip">
                <i class="fas fa-bolt"></i>
                <div><span class="spec-chip-label">GPU</span><span class="spec-chip-value">${specs.gpu_name}</span></div>
            </div>`);
            chips.push(`<div class="spec-chip">
                <i class="fas fa-database"></i>
                <div><span class="spec-chip-label">VRAM</span><span class="spec-chip-value">${specs.vram_gb} GB</span></div>
            </div>`);
        } else {
            chips.push(`<div class="spec-chip">
                <i class="fas fa-microchip" style="color:var(--text-tertiary)"></i>
                <div><span class="spec-chip-label">GPU</span><span class="spec-chip-value" style="color:var(--text-tertiary)">No CUDA GPU</span></div>
            </div>`);
        }

        const updated = specs.last_updated ? new Date(specs.last_updated).toLocaleString() : '';
        row.innerHTML = chips.join('') + (updated ? `<div style="flex-basis:100%;font-size:0.7rem;color:var(--text-tertiary);margin-top:0.25rem;">Last updated: ${updated}</div>` : '');
    },

    updateSuggestedBadges(installedFiles) {
        const grid = document.getElementById('suggested-models-grid');
        if (!grid) return;

        grid.querySelectorAll('.suggestion-card-v12').forEach(card => {
            const installBtn = card.querySelector('.install-btn');
            const badge = card.querySelector('.installed-badge');
            const deleteBtn = card.querySelector('.delete-btn');

            // Skip unsupported cards — they have no install button
            if (!installBtn) return;

            const installAction = installBtn.getAttribute('onclick');
            const filenameMatch = installAction ? installAction.match(/'([^']+)'\s*\)$/) : null;
            const filename = filenameMatch ? filenameMatch[1] : '';

            if (installedFiles.includes(filename)) {
                if (badge) badge.style.display = 'flex';
                installBtn.disabled = true;
                installBtn.innerHTML = '<i class="fas fa-check"></i> Installed';
                installBtn.classList.add('secondary');
                if (deleteBtn) deleteBtn.style.display = 'block';
            } else {
                if (badge) badge.style.display = 'none';
                installBtn.disabled = false;
                installBtn.innerHTML = '<i class="fas fa-download"></i> Install';
                installBtn.classList.remove('secondary');
                if (deleteBtn) deleteBtn.style.display = 'none';
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

                    if (msg.done) {
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
                    } else if (msg.pct !== undefined) {
                        if (dlBar)   dlBar.style.width    = msg.pct + '%';
                        if (dlPct)   dlPct.textContent    = msg.pct + '%';
                        if (dlLabel) dlLabel.textContent  = 'Downloading…';
                        if (dlSize && msg.downloaded_mb)
                            dlSize.textContent = `${msg.downloaded_mb} MB / ${msg.total_mb} MB`;
                        if (btn) btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${msg.pct}%`;
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
                arch: this._getArch(name),
                company: this._getCompany(name)
            };
        });

        filtered = filtered.filter(m => {
            if (this._filters.search && !m.name.toLowerCase().includes(this._filters.search)) return false;
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
            listEl.innerHTML = `<div class="ae-empty"><div class="ae-empty-icon"><i class="fas fa-cube"></i></div><div class="ae-empty-title">No Ollama models match filters</div><div class="ae-empty-desc">Try adjusting your search or pull a model from the registry.</div></div>`;
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

    _getCompany(text) {
        if (!text) return 'Other';
        const t = text.toLowerCase();
        // NVIDIA-specific variants first
        if (t.includes('nv-') || t.includes('nvembed') || t.includes('nvidia')) return 'NVIDIA';
        // Google
        if (t.includes('gemma') || t.includes('codegemma') || t.includes('gemini') || t.includes('recurrentgemma')) return 'Google';
        // Meta
        if (t.includes('llama') || t.includes('codellama') || t.includes('meta-llama')) return 'Meta';
        // Microsoft
        if (t.includes('phi-') || t.startsWith('phi') || t.includes('wizardlm') || t.includes('orca')) return 'Microsoft';
        // Mistral AI
        if (t.includes('mistral') || t.includes('mixtral') || t.includes('mathstral') || t.includes('devstral') || t.includes('codestral')) return 'Mistral AI';
        // Alibaba
        if (t.includes('qwen') || t.includes('qwq') || t.includes('marco')) return 'Alibaba';
        // DeepSeek
        if (t.includes('deepseek')) return 'DeepSeek';
        // 01.AI
        if (t.includes('yi-') || t.includes('yi1.') || t.includes('/yi')) return '01.AI';
        // TII
        if (t.includes('falcon')) return 'TII';
        // Cohere
        if (t.includes('command') || t.includes('aya')) return 'Cohere';
        // xAI
        if (t.includes('grok')) return 'xAI';
        // Stability AI
        if (t.includes('stable') || t.includes('stablelm')) return 'Stability AI';
        // HuggingFace / SmolLM
        if (t.includes('smollm') || t.includes('zephyr') || t.includes('idefics')) return 'HuggingFace';
        // Nous Research
        if (t.includes('nous') || t.includes('hermes') || t.includes('capybara') || t.includes('solar')) return 'Nous Research';
        return 'Other';
    },

    async toggleModelInfo(modelId, btn) {
        const panel = document.getElementById(`sug-info-${modelId}`);
        if (!panel) return;

        // Toggle if already showing
        if (panel.style.display !== 'none' && panel.dataset.loaded === 'true') {
            panel.style.display = 'none';
            btn.classList.remove('active');
            return;
        }

        // Show panel
        panel.style.display = 'block';
        btn.classList.add('active');

        // Use cached response if available
        if (this._infoCache[modelId]) {
            panel.innerHTML = `<div class="sug-info-content">${this._infoCache[modelId]}</div>`;
            panel.dataset.loaded = 'true';
            return;
        }

        // Find model data
        const model = this._suggestions.find(m => m.id === modelId);
        if (!model) { panel.innerHTML = '<div class="sug-info-content">Model not found.</div>'; return; }

        panel.innerHTML = `<div class="sug-info-content sug-info-loading"><i class="fas fa-spinner fa-spin"></i> Asking AI about compatibility with your hardware…</div>`;

        try {
            const res = await fetch('/api/registry/local/model-info-query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model_name: model.name,
                    model_size: model.size || '',
                    model_description: model.description || '',
                    model_tags: model.tags || [],
                    specs: this._systemSpecs || {}
                })
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || `Server error ${res.status}`);
            }
            const data = await res.json();
            const escaped = data.response.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
            this._infoCache[modelId] = escaped;
            panel.innerHTML = `<div class="sug-info-content">${escaped}</div>`;
            panel.dataset.loaded = 'true';
        } catch (e) {
            panel.innerHTML = `<div class="sug-info-content sug-info-error"><i class="fas fa-triangle-exclamation"></i> ${e.message || 'Could not fetch compatibility info.'}</div>`;
        }
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
