/**
 * Aethvion Suite — Image Models Hub View (Model Hub > Image Models)
 * Dedicated to exploring, installing, downloading, and managing image checkpoints.
 * Actual generation is done in Workspace > Photo.
 */

(function () {
    'use strict';

    const ViewImageModels = {
        state: {
            status: null,
            models: null,
            downloadPollers: {}
        },

        init() {
            this.bindEvents();
            this.initHardwareProfile();
            this.loadStatus();
            this.loadModels();
        },

        bindEvents() {
            // Refresh button
            const refreshBtn = document.getElementById('im-btn-refresh');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => {
                    const icon = refreshBtn.querySelector('i');
                    if (icon) icon.classList.add('fa-spin');
                    Promise.all([this.loadStatus(), this.loadModels()]).finally(() => {
                        if (icon) icon.classList.remove('fa-spin');
                        if (window.showToast) window.showToast('Image models and backends refreshed.', 'success');
                    });
                });
            }

            // Library Search & Compat Filter
            const librarySearch = document.getElementById('image-search-input');
            if (librarySearch) {
                librarySearch.addEventListener('input', () => this.filterLibraryCards());
            }

            const compatFilter = document.getElementById('image-compat-filter');
            if (compatFilter) {
                compatFilter.addEventListener('change', () => this.filterLibraryCards());
            }
        },

        initHardwareProfile() {
            if (window.HardwareProfile) {
                window.HardwareProfile.attachToolbarPill('image-hw-slot');
                window.HardwareProfile.subscribe(() => {
                    this.renderCatalogCards();
                });
            }
        },

        async loadStatus() {
            try {
                const res = await fetch('/api/photo/status');
                if (!res.ok) throw new Error('Status failed');
                const data = await res.json();
                this.state.status = data;
                this.renderStatus(data);
            } catch (e) {
                console.warn('[ViewImageModels] loadStatus error:', e);
            }
        },

        renderStatus(status) {
            const engineChip = document.getElementById('im-stat-engine');
            const banner = document.getElementById('im-engine-banner');
            if (!engineChip) return;

            const isSdOnline = status.sd_webui && status.sd_webui.online;
            const hasCloud = status.cloud_providers && (status.cloud_providers.google_ai || status.cloud_providers.openai);
            const gpuName = status.hardware?.gpu_name || 'GPU';
            const vram = status.hardware?.vram_gb || 0;

            if (isSdOnline) {
                engineChip.style.color = '#34d399';
                engineChip.innerHTML = `<i class="fas fa-circle-check"></i> SD WebUI (${status.sd_webui.model_count} models)`;
                
                if (banner) {
                    banner.innerHTML = `
                        <div style="background: rgba(52, 211, 153, 0.08); border: 1px solid rgba(52, 211, 153, 0.25); border-radius: 12px; padding: 0.9rem 1.25rem; display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 0.85rem;">
                                <i class="fas fa-bolt" style="color: #34d399; font-size: 1.25rem;"></i>
                                <div>
                                    <strong style="color: #fff; font-size: 0.85rem;">Connected to Local Stable Diffusion WebUI / Forge</strong>
                                    <div style="font-size: 0.75rem; color: var(--text-tertiary);">API active at ${status.sd_webui.url} · Accelerated on ${gpuName} (${vram}GB VRAM)</div>
                                </div>
                            </div>
                            <button class="hub-action-btn" onclick="switchMainTab('photo')" style="background:var(--primary); color:#000; height:32px; font-size:0.75rem; padding:0 0.8rem; border:none; border-radius:6px; cursor:pointer;">
                                Use in Photo Studio →
                            </button>
                        </div>
                    `;
                }
            } else if (hasCloud) {
                engineChip.style.color = '#38bdf8';
                engineChip.innerHTML = `<i class="fas fa-cloud"></i> Cloud Ready`;

                if (banner) {
                    banner.innerHTML = `
                        <div style="background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 12px; padding: 0.9rem 1.25rem; display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 0.85rem;">
                                <i class="fas fa-cloud-arrow-up" style="color: #38bdf8; font-size: 1.25rem;"></i>
                                <div>
                                    <strong style="color: #fff; font-size: 0.85rem;">Cloud Image Backends Configured</strong>
                                    <div style="font-size: 0.75rem; color: var(--text-tertiary);">Google AI (Imagen 3) / OpenAI (DALL-E 3) are active. To run offline, download checkpoints below or launch AUTOMATIC1111/Forge with <code>--api</code>.</div>
                                </div>
                            </div>
                            <span class="im-status-chip online" style="color:#38bdf8; border-color:rgba(56, 189, 248, 0.3); background:rgba(56, 189, 248, 0.1);">Cloud Active</span>
                        </div>
                    `;
                }
            } else {
                engineChip.style.color = '#fbbf24';
                engineChip.innerHTML = `<i class="fas fa-circle-exclamation"></i> Standby`;

                if (banner) {
                    banner.innerHTML = `
                        <div style="background: rgba(251, 191, 36, 0.08); border: 1px solid rgba(251, 191, 36, 0.25); border-radius: 12px; padding: 0.9rem 1.25rem; display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 0.85rem;">
                                <i class="fas fa-circle-info" style="color: #fbbf24; font-size: 1.25rem;"></i>
                                <div>
                                    <strong style="color: #fff; font-size: 0.85rem;">Download Checkpoints to Run Fully Offline</strong>
                                    <div style="font-size: 0.75rem; color: var(--text-tertiary);">Download any model checkpoint below to save into <code>localmodels/image/</code>, or launch AUTOMATIC1111/Forge with <code>--api</code> (port 7860).</div>
                                </div>
                            </div>
                            <span class="im-status-chip offline"><i class="fas fa-power-off"></i> Standby</span>
                        </div>
                    `;
                }
            }
        },

        async loadModels() {
            try {
                const res = await fetch('/api/photo/models');
                if (!res.ok) throw new Error('Models fetch failed');
                const data = await res.json();
                this.state.models = data;

                // Update active count
                const activeCountEl = document.getElementById('im-stat-active-models');
                if (activeCountEl) {
                    activeCountEl.textContent = data.active_models_count || 0;
                }

                this.renderCatalogCards();
            } catch (e) {
                console.error('[ViewImageModels] loadModels error:', e);
            }
        },

        renderCatalogCards() {
            const container = document.getElementById('im-models-catalog-container');
            if (!container || !this.state.models) return;

            const suggested = this.state.models.suggested || [];
            const custom = this.state.models.custom || [];

            // Group by provider
            const groups = {};
            suggested.forEach(m => {
                const p = m.provider || 'Stability AI';
                if (!groups[p]) groups[p] = [];
                groups[p].push(m);
            });

            if (custom.length > 0) {
                groups['Custom Local Checkpoints'] = custom;
            }

            let html = '';
            for (const [provider, list] of Object.entries(groups)) {
                html += `
                    <section class="hub-provider-section im-provider-block">
                        <div class="hub-provider-hd">
                            <div class="hub-provider-dot" style="--brand-color: #38bdf8;"></div>
                            <h2 class="hub-provider-name">${provider}</h2>
                        </div>
                        <div class="hub-grid">
                `;

                list.forEach(m => {
                    html += this.renderModelCard(m);
                });

                html += `</div></section>`;
            }

            container.innerHTML = html;
            this.bindCardActions();
            this.filterLibraryCards();
        },

        renderModelCard(m) {
            const reqVram = Number(m.vram_gb) || 8;
            const reqRam = Number(m.ram_gb) || 16;
            const compatBadge = window.HardwareProfile 
                ? window.HardwareProfile.renderBadge({ name: m.name, req_vram_gb: reqVram, req_ram_gb: reqRam, type: 'image' }) 
                : '';

            const isInstalled = !!m.installed;
            const statusBadge = isInstalled
                ? `<span class="hub-status-badge" style="color:#34d399; border-color:rgba(52,211,153,0.3);"><i class="fas fa-check"></i> Installed</span>`
                : `<span class="hub-status-badge">Available</span>`;

            const actionBtn = isInstalled
                ? `<button class="hub-action-btn im-btn-open-photo" data-id="${m.id}" style="background:var(--primary); color:#000;">
                       <i class="fas fa-wand-magic-sparkles"></i> Open in Photo Studio
                   </button>
                   <button class="im-tool-btn im-btn-delete-model" data-filename="${m.filename}" title="Delete checkpoint file" style="color:#f87171;">
                       <i class="fas fa-trash"></i>
                   </button>`
                : `<button class="hub-action-btn im-btn-download-model" data-id="${m.id}" data-filename="${m.filename}">
                       <i class="fas fa-download"></i> Download Checkpoint
                   </button>`;

            const tagsHtml = (m.tags || ['1024px', 'Text to Image']).map(t => `<span class="hub-tag">${t}</span>`).join('');

            return `
                <div class="hub-card im-catalog-card" data-id="${m.id}" data-name="${m.name}" data-vram="${reqVram}" data-ram="${reqRam}">
                    <div class="hub-card-top">
                        <div class="hub-model-icon"><i class="fas fa-mountain-sun"></i></div>
                        <div style="display:flex; align-items:center; gap:0.4rem;">
                            ${compatBadge}
                            ${statusBadge}
                        </div>
                    </div>
                    <div class="hub-model-info">
                        <h3>${m.name}</h3>
                        <p>${m.description || 'High quality text-to-image neural network checkpoint.'}</p>
                    </div>
                    <div class="hub-tags">
                        ${tagsHtml}
                        <span class="hub-tag"><i class="fas fa-memory"></i> ${reqVram}GB VRAM</span>
                    </div>
                    <div id="dl-container-${m.id}" style="display:none; margin: 0.5rem 0;">
                        <div style="display:flex; justify-content:space-between; font-size:0.7rem; margin-bottom:4px; color:var(--text-tertiary);">
                            <span id="dl-status-${m.id}">Downloading...</span>
                            <span id="dl-percent-${m.id}" style="font-weight:700; color:var(--primary);">0%</span>
                        </div>
                        <div class="model-dl-bar-wrap">
                            <div id="dl-bar-${m.id}" class="model-dl-bar" style="width:0%;"></div>
                        </div>
                    </div>
                    <div class="hub-card-footer">
                        <div class="hub-meta-info">
                            <i class="fas fa-weight-hanging"></i> ${m.size_label || '~6 GB'}
                        </div>
                        <div style="display:flex; gap:0.4rem; align-items:center;">
                            ${actionBtn}
                        </div>
                    </div>
                </div>
            `;
        },

        bindCardActions() {
            // Open in Photo Studio
            document.querySelectorAll('.im-btn-open-photo').forEach(btn => {
                btn.addEventListener('click', () => {
                    const modelId = btn.dataset.id;
                    if (window.switchMainTab) {
                        window.switchMainTab('photo');
                        setTimeout(() => {
                            if (window.PhotoStudio && window.PhotoStudio.selectModel) {
                                window.PhotoStudio.selectModel(modelId);
                            }
                        }, 200);
                    }
                });
            });

            // Download model
            document.querySelectorAll('.im-btn-download-model').forEach(btn => {
                btn.addEventListener('click', () => {
                    const modelId = btn.dataset.id;
                    const filename = btn.dataset.filename;
                    this.startModelDownload(modelId, filename, btn);
                });
            });

            // Delete model
            document.querySelectorAll('.im-btn-delete-model').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const filename = btn.dataset.filename;
                    if (!confirm(`Are you sure you want to delete ${filename}? This cannot be undone.`)) return;

                    try {
                        const res = await fetch(`/api/photo/models/${encodeURIComponent(filename)}`, { method: 'DELETE' });
                        if (!res.ok) throw new Error('Delete failed');
                        if (window.showToast) window.showToast(`Deleted ${filename}`, 'success');
                        this.loadModels();
                    } catch (e) {
                        if (window.showToast) window.showToast(`Error: ${e.message}`, 'error');
                    }
                });
            });
        },

        async startModelDownload(modelId, filename, btn) {
            btn.style.display = 'none';
            const dlContainer = document.getElementById(`dl-container-${modelId}`);
            if (dlContainer) dlContainer.style.display = 'block';

            try {
                const res = await fetch('/api/photo/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_id: modelId, filename: filename })
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Download request failed');
                }

                const data = await res.json();
                const taskId = data.task_id;
                this.pollDownloadTask(taskId, modelId, btn);
            } catch (e) {
                if (window.showToast) window.showToast(`Download failed: ${e.message}`, 'error');
                btn.style.display = 'inline-flex';
                if (dlContainer) dlContainer.style.display = 'none';
            }
        },

        pollDownloadTask(taskId, modelId, originalBtn) {
            const dlBar = document.getElementById(`dl-bar-${modelId}`);
            const dlPercent = document.getElementById(`dl-percent-${modelId}`);
            const dlStatus = document.getElementById(`dl-status-${modelId}`);

            const interval = setInterval(async () => {
                try {
                    const res = await fetch(`/api/photo/download/${taskId}`);
                    if (!res.ok) return;
                    const task = await res.json();

                    if (task.status === 'downloading') {
                        const pct = (task.progress || 0).toFixed(1) + '%';
                        if (dlBar) dlBar.style.width = pct;
                        if (dlPercent) dlPercent.textContent = pct;
                        if (dlStatus) dlStatus.textContent = `${task.speed_mbps || 0} MB/s`;
                    } else if (task.status === 'completed') {
                        clearInterval(interval);
                        if (dlBar) dlBar.style.width = '100%';
                        if (dlPercent) dlPercent.textContent = '100%';
                        if (dlStatus) dlStatus.textContent = 'Ready!';
                        if (window.showToast) window.showToast(`${task.filename} ready for generation!`, 'success');
                        setTimeout(() => this.loadModels(), 1200);
                    } else if (task.status === 'error') {
                        clearInterval(interval);
                        if (window.showToast) window.showToast(`Download error: ${task.error}`, 'error');
                        originalBtn.style.display = 'inline-flex';
                    }
                } catch (e) { }
            }, 1000);

            this.state.downloadPollers[taskId] = interval;
        },

        filterLibraryCards() {
            const query = (document.getElementById('image-search-input')?.value || '').toLowerCase().trim();
            const compatFilter = document.getElementById('image-compat-filter')?.value || 'all';

            document.querySelectorAll('.im-catalog-card').forEach(card => {
                const name = (card.dataset.name || '').toLowerCase();
                const reqVram = parseFloat(card.dataset.vram || 8);
                const reqRam = parseFloat(card.dataset.ram || 16);

                let matchesSearch = !query || name.includes(query);
                let matchesCompat = true;

                if (compatFilter !== 'all' && window.HardwareProfile) {
                    const c = window.HardwareProfile.evaluate({ name, req_vram_gb: reqVram, req_ram_gb: reqRam, type: 'image' });
                    if (compatFilter === 'runnable') matchesCompat = c.runnable !== false;
                    else if (compatFilter === 'gpu') matchesCompat = (c.status === 'gpu');
                    else if (compatFilter === 'cpu') matchesCompat = (c.status === 'cpu' || c.status === 'partial');
                }

                card.style.display = (matchesSearch && matchesCompat) ? '' : 'none';
            });
        }
    };

    document.addEventListener('panelLoaded', (e) => {
        if (e.detail && e.detail.tabName === 'image-models') {
            ViewImageModels.init();
        }
    });

    if (document.getElementById('im-models-catalog-container')) {
        ViewImageModels.init();
    }

    window.ViewImageModels = ViewImageModels;
})();
