/**
 * Aethvion Suite — Image Models & Generation Studio View
 * Handles local SD WebUI / Forge, ComfyUI, Hugging Face checkpoint downloads,
 * hardware compatibility evaluation, and live image generation.
 */

(function () {
    'use strict';

    const SAMPLE_PROMPTS = [
        "A majestic obsidian cyber-dragon perched on a neon skyscraper, volumetric mist, cinematic 8k render, octane",
        "Ethereal bioluminescent forest with glowing mushrooms and crystalline river, fantasy digital painting, high detail",
        "Retro-futuristic 1980s synthwave sports car speeding through a laser grid highway towards a neon sun, aesthetic",
        "Cinematic portrait of an ancient sorceress with floating arcane runes, volumetric lighting, photorealistic, 8k",
        "Cozy steampunk coffee shop in Victorian London with brass pipes, warm amber lighting, intricate interior details",
        "Isometric 3D diorama of a floating miniature cyberpunk city island, soft ambient occlusion, tilt-shift render"
    ];

    const ViewImageModels = {
        state: {
            currentTab: 'studio',
            selectedSize: '1024x1024',
            selectedAspect: '1:1',
            status: null,
            models: null,
            history: [],
            currentImage: null,
            generating: false,
            downloadPollers: {}
        },

        init() {
            this.bindEvents();
            this.initHardwareProfile();
            this.loadStatus();
            this.loadModels();
            this.loadGallery();
        },

        bindEvents() {
            // Tab switching
            ['studio', 'models', 'gallery'].forEach(tab => {
                const btn = document.getElementById(`im-tab-${tab}-btn`);
                if (btn) btn.addEventListener('click', () => this.switchTab(tab));
            });

            // Refresh button
            const refreshBtn = document.getElementById('im-btn-refresh');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => {
                    const icon = refreshBtn.querySelector('i');
                    if (icon) icon.classList.add('fa-spin');
                    Promise.all([this.loadStatus(), this.loadModels(), this.loadGallery()]).finally(() => {
                        if (icon) icon.classList.remove('fa-spin');
                        if (window.showToast) window.showToast('Image models and backends refreshed.', 'success');
                    });
                });
            }

            // Aspect ratio buttons
            document.querySelectorAll('.im-aspect-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    document.querySelectorAll('.im-aspect-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    this.state.selectedSize = btn.dataset.size || '1024x1024';
                    this.state.selectedAspect = btn.dataset.aspect || '1:1';
                });
            });

            // Sliders
            const stepsSlider = document.getElementById('im-steps');
            const stepsVal = document.getElementById('im-steps-val');
            if (stepsSlider && stepsVal) {
                stepsSlider.addEventListener('input', (e) => stepsVal.textContent = e.target.value);
            }

            const cfgSlider = document.getElementById('im-cfg');
            const cfgVal = document.getElementById('im-cfg-val');
            if (cfgSlider && cfgVal) {
                cfgSlider.addEventListener('input', (e) => cfgVal.textContent = parseFloat(e.target.value).toFixed(1));
            }

            // Random Prompt & Quick Tags
            const randomPromptBtn = document.getElementById('im-btn-random-prompt');
            if (randomPromptBtn) {
                randomPromptBtn.addEventListener('click', () => {
                    const promptInput = document.getElementById('im-prompt');
                    if (promptInput) {
                        const random = SAMPLE_PROMPTS[Math.floor(Math.random() * SAMPLE_PROMPTS.length)];
                        promptInput.value = random;
                    }
                });
            }

            document.querySelectorAll('.im-prompt-pill[data-append]').forEach(pill => {
                pill.addEventListener('click', () => {
                    const promptInput = document.getElementById('im-prompt');
                    if (promptInput) {
                        const appendText = pill.dataset.append || '';
                        if (!promptInput.value.includes(appendText.trim())) {
                            promptInput.value = (promptInput.value.trim() + appendText).trim();
                        }
                    }
                });
            });

            // Random seed button
            const randomSeedBtn = document.getElementById('im-btn-random-seed');
            if (randomSeedBtn) {
                randomSeedBtn.addEventListener('click', () => {
                    const seedInput = document.getElementById('im-seed');
                    if (seedInput) seedInput.value = -1;
                });
            }

            // Generate Button
            const generateBtn = document.getElementById('im-btn-generate');
            if (generateBtn) {
                generateBtn.addEventListener('click', () => this.generateImage());
            }

            // Keyboard shortcut Ctrl+Enter on prompt
            const promptInput = document.getElementById('im-prompt');
            if (promptInput) {
                promptInput.addEventListener('keydown', (e) => {
                    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                        e.preventDefault();
                        this.generateImage();
                    }
                });
            }

            // Viewport Actions
            const downloadBtn = document.getElementById('im-btn-download');
            if (downloadBtn) {
                downloadBtn.addEventListener('click', () => this.downloadCurrentImage());
            }

            const copyPromptBtn = document.getElementById('im-btn-copy-prompt');
            if (copyPromptBtn) {
                copyPromptBtn.addEventListener('click', () => this.copyCurrentPrompt());
            }

            const openPhotoBtn = document.getElementById('im-btn-open-photo');
            if (openPhotoBtn) {
                openPhotoBtn.addEventListener('click', () => this.openInPhotoEditor());
            }

            // Refresh Gallery
            const refreshGalleryBtn = document.getElementById('im-btn-refresh-gallery');
            if (refreshGalleryBtn) {
                refreshGalleryBtn.addEventListener('click', () => this.loadGallery());
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

        switchTab(tab) {
            this.state.currentTab = tab;
            ['studio', 'models', 'gallery'].forEach(t => {
                const btn = document.getElementById(`im-tab-${t}-btn`);
                const sec = document.getElementById(`im-section-${t}`);
                if (btn) btn.classList.toggle('active', t === tab);
                if (sec) sec.style.display = (t === tab) ? (t === 'studio' ? 'grid' : 'block') : 'none';
            });

            if (tab === 'gallery') this.loadGallery();
            if (tab === 'models') this.loadModels();
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
                            <span class="im-status-chip online"><i class="fas fa-check-circle"></i> Service Ready</span>
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
                                    <div style="font-size: 0.75rem; color: var(--text-tertiary);">Imagen 3 / DALL-E 3 are available. To run fully offline, launch AUTOMATIC1111/Forge with <code>--api</code>.</div>
                                </div>
                            </div>
                            <span class="im-status-chip online" style="color:#38bdf8; border-color:rgba(56, 189, 248, 0.3); background:rgba(56, 189, 248, 0.1);">Cloud Active</span>
                        </div>
                    `;
                }
            } else {
                engineChip.style.color = '#fbbf24';
                engineChip.innerHTML = `<i class="fas fa-circle-exclamation"></i> Offline`;

                if (banner) {
                    banner.innerHTML = `
                        <div style="background: rgba(251, 191, 36, 0.08); border: 1px solid rgba(251, 191, 36, 0.25); border-radius: 12px; padding: 0.9rem 1.25rem; display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 0.85rem;">
                                <i class="fas fa-circle-info" style="color: #fbbf24; font-size: 1.25rem;"></i>
                                <div>
                                    <strong style="color: #fff; font-size: 0.85rem;">No Image Generation Backend Detected</strong>
                                    <div style="font-size: 0.75rem; color: var(--text-tertiary);">To generate images, launch AUTOMATIC1111 or Forge with <code>--api</code> (port 7860), or add an API key in <strong>API Providers</strong>.</div>
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

                this.populateDropdown(data);
                this.renderCatalogCards();
            } catch (e) {
                console.error('[ViewImageModels] loadModels error:', e);
            }
        },

        populateDropdown(data) {
            const select = document.getElementById('im-model-select');
            if (!select) return;

            const currentVal = select.value;
            let optionsHtml = '';

            // 1. SD WebUI Models if online
            if (data.sd_webui && data.sd_webui.length > 0) {
                optionsHtml += `<optgroup label="Local SD WebUI Active Checkpoints">`;
                data.sd_webui.forEach(m => {
                    optionsHtml += `<option value="${m.id}">${m.name}</option>`;
                });
                optionsHtml += `</optgroup>`;
            }

            // 2. Downloaded / Suggested Local Checkpoints
            optionsHtml += `<optgroup label="Local Recommended Checkpoints">`;
            const suggested = data.suggested || [];
            suggested.forEach(m => {
                const statusTag = m.installed ? ' (Ready)' : '';
                optionsHtml += `<option value="${m.id}">${m.name} — ${m.resolution}${statusTag}</option>`;
            });
            optionsHtml += `</optgroup>`;

            // 3. Custom dropped checkpoints
            if (data.custom && data.custom.length > 0) {
                optionsHtml += `<optgroup label="Local / Custom Weights">`;
                data.custom.forEach(m => {
                    optionsHtml += `<option value="${m.id}">${m.name} (${m.size_label})</option>`;
                });
                optionsHtml += `</optgroup>`;
            }

            // 4. Cloud providers
            optionsHtml += `<optgroup label="Cloud Providers">
                <option value="imagen-3.0-generate-002">Google AI — Imagen 3</option>
                <option value="dall-e-3">OpenAI — DALL-E 3</option>
            </optgroup>`;

            select.innerHTML = optionsHtml;
            if (currentVal && select.querySelector(`option[value="${currentVal}"]`)) {
                select.value = currentVal;
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
                groups['Local Custom Checkpoints'] = custom;
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
                ? `<span class="hub-status-badge" style="color:#34d399; border-color:rgba(52,211,153,0.3);"><i class="fas fa-check"></i> Ready</span>`
                : `<span class="hub-status-badge">Available</span>`;

            const actionBtn = isInstalled
                ? `<button class="hub-action-btn im-btn-use-model" data-id="${m.id}" data-steps="${m.recommended_steps || 25}" data-cfg="${m.recommended_cfg || 7.0}" data-res="${m.resolution || '1024x1024'}" style="background:var(--primary); color:#000;">
                       <i class="fas fa-wand-magic-sparkles"></i> Use in Studio
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
                        <div class="hub-model-icon"><i class="fas fa-palette"></i></div>
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
            // Use in studio
            document.querySelectorAll('.im-btn-use-model').forEach(btn => {
                btn.addEventListener('click', () => {
                    const modelId = btn.dataset.id;
                    const steps = btn.dataset.steps;
                    const cfg = btn.dataset.cfg;
                    const res = btn.dataset.res;

                    const select = document.getElementById('im-model-select');
                    if (select && modelId) select.value = modelId;

                    if (steps) {
                        const sEl = document.getElementById('im-steps');
                        const sVal = document.getElementById('im-steps-val');
                        if (sEl) sEl.value = steps;
                        if (sVal) sVal.textContent = steps;
                    }
                    if (cfg) {
                        const cEl = document.getElementById('im-cfg');
                        const cVal = document.getElementById('im-cfg-val');
                        if (cEl) cEl.value = cfg;
                        if (cVal) cVal.textContent = parseFloat(cfg).toFixed(1);
                    }
                    if (res) {
                        const matchBtn = document.querySelector(`.im-aspect-btn[data-size="${res}"]`);
                        if (matchBtn) matchBtn.click();
                    }

                    this.switchTab('studio');
                    if (window.showToast) window.showToast(`Loaded ${modelId} in Studio.`, 'info');
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
                        if (dlStatus) dlStatus.textContent = 'Completed!';
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
        },

        async generateImage() {
            if (this.state.generating) return;

            const prompt = (document.getElementById('im-prompt')?.value || '').trim();
            if (!prompt) {
                if (window.showToast) window.showToast('Please enter a prompt first.', 'warning');
                document.getElementById('im-prompt')?.focus();
                return;
            }

            const negPrompt = (document.getElementById('im-negative-prompt')?.value || '').trim();
            const model = document.getElementById('im-model-select')?.value || 'sd-1-5';
            const size = this.state.selectedSize || '1024x1024';
            const steps = parseInt(document.getElementById('im-steps')?.value || 25, 10);
            const cfg = parseFloat(document.getElementById('im-cfg')?.value || 7.0);
            const seedVal = parseInt(document.getElementById('im-seed')?.value || -1, 10);

            this.setGenerating(true);

            const startTime = Date.now();
            const timerEl = document.getElementById('im-generating-timer');
            const timerInterval = setInterval(() => {
                const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
                if (timerEl) timerEl.textContent = `${elapsed}s`;
            }, 100);

            try {
                const res = await fetch('/api/photo/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        prompt: prompt,
                        negative_prompt: negPrompt,
                        model: model,
                        size: size,
                        steps: steps,
                        cfg_scale: cfg,
                        seed: seedVal >= 0 ? seedVal : undefined
                    })
                });

                clearInterval(timerInterval);

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Generation request failed');
                }

                const data = await res.json();
                if (!data.success || !data.images || data.images.length === 0) {
                    throw new Error(data.error || 'No images returned');
                }

                const imgObj = data.images[0];
                this.displayGeneratedImage(imgObj, prompt);
                this.loadGallery();
                if (window.showToast) window.showToast('Image generated successfully!', 'success');
            } catch (e) {
                clearInterval(timerInterval);
                console.error('[ViewImageModels] generation error:', e);
                if (window.showToast) window.showToast(`Generation error: ${e.message}`, 'error');
            } finally {
                this.setGenerating(false);
            }
        },

        setGenerating(isGenerating) {
            this.state.generating = isGenerating;
            const overlay = document.getElementById('im-generating-overlay');
            const genBtn = document.getElementById('im-btn-generate');

            if (overlay) overlay.style.display = isGenerating ? 'flex' : 'none';
            if (genBtn) {
                genBtn.disabled = isGenerating;
                genBtn.innerHTML = isGenerating
                    ? `<i class="fas fa-spinner fa-spin"></i> Synthesizing...`
                    : `<i class="fas fa-wand-magic-sparkles"></i> Generate Image`;
            }
        },

        displayGeneratedImage(imgObj, prompt) {
            this.state.currentImage = { ...imgObj, prompt };
            const imgEl = document.getElementById('im-viewport-img');
            const emptyEl = document.getElementById('im-viewport-empty');
            const actionsEl = document.getElementById('im-viewport-actions');
            const metaEl = document.getElementById('im-viewport-meta');

            if (imgEl) {
                imgEl.src = imgObj.url;
                imgEl.style.display = 'block';
            }
            if (emptyEl) emptyEl.style.display = 'none';
            if (actionsEl) actionsEl.style.display = 'flex';
            if (metaEl) metaEl.textContent = `${this.state.selectedSize} · Ready`;
        },

        downloadCurrentImage() {
            if (!this.state.currentImage) return;
            const a = document.createElement('a');
            a.href = this.state.currentImage.url;
            a.download = this.state.currentImage.filename || 'aethvion-image.png';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        },

        copyCurrentPrompt() {
            if (!this.state.currentImage || !this.state.currentImage.prompt) return;
            navigator.clipboard.writeText(this.state.currentImage.prompt);
            if (window.showToast) window.showToast('Prompt copied to clipboard.', 'success');
        },

        openInPhotoEditor() {
            if (!this.state.currentImage) return;
            // Check if Aethvion Photo tab or window is available
            if (window.location.port !== '8005') {
                window.open(`http://localhost:8005/?img=${encodeURIComponent(this.state.currentImage.url)}`, '_blank');
            } else {
                if (window.showToast) window.showToast('Loading into canvas...', 'info');
            }
        },

        async loadGallery() {
            try {
                const res = await fetch('/api/photo/history?limit=40');
                if (!res.ok) return;
                const data = await res.json();
                this.state.history = data.images || [];

                const countEl = document.getElementById('im-stat-gallery-count');
                if (countEl) countEl.textContent = this.state.history.length;

                this.renderGallery();
            } catch (e) {
                console.warn('[ViewImageModels] loadGallery error:', e);
            }
        },

        renderGallery() {
            const grid = document.getElementById('im-gallery-grid');
            if (!grid) return;

            if (this.state.history.length === 0) {
                grid.innerHTML = `
                    <div style="grid-column: 1/-1; padding: 4rem; text-align: center; border: 1px dashed var(--hub-card-border); border-radius: 16px; color: var(--text-tertiary);">
                        <i class="fas fa-images" style="font-size: 3rem; margin-bottom: 1rem; opacity: 0.2;"></i>
                        <p style="margin: 0;">No creations in gallery yet.</p>
                        <p style="margin: 0.25rem 0 0 0; font-size: 0.8rem;">Images generated in the Studio will appear here automatically.</p>
                    </div>
                `;
                return;
            }

            grid.innerHTML = this.state.history.map(item => `
                <div class="im-gallery-item" data-url="${item.url}" data-filename="${item.filename}" data-prompt="${item.prompt || ''}">
                    <img src="${item.url}" alt="${item.prompt || 'Artwork'}" loading="lazy">
                    <div class="im-gallery-overlay">
                        <div class="im-gallery-prompt">${item.prompt || item.filename}</div>
                        <div class="im-gallery-meta">
                            <span>${item.timestamp || ''}</span>
                            <div class="im-gallery-actions">
                                <button class="im-gallery-btn im-gallery-inspect" title="Load into Studio"><i class="fas fa-eye"></i></button>
                                <button class="im-gallery-btn im-gallery-del" title="Delete image" style="color:#f87171;"><i class="fas fa-trash"></i></button>
                            </div>
                        </div>
                    </div>
                </div>
            `).join('');

            // Click to load in Studio
            grid.querySelectorAll('.im-gallery-item').forEach(el => {
                el.addEventListener('click', (e) => {
                    if (e.target.closest('.im-gallery-del')) return;
                    const url = el.dataset.url;
                    const filename = el.dataset.filename;
                    const prompt = el.dataset.prompt;

                    this.displayGeneratedImage({ url, filename }, prompt);
                    const promptInput = document.getElementById('im-prompt');
                    if (promptInput && prompt) promptInput.value = prompt;

                    this.switchTab('studio');
                });
            });

            // Delete action
            grid.querySelectorAll('.im-gallery-del').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    const item = btn.closest('.im-gallery-item');
                    const filename = item.dataset.filename;
                    if (!confirm(`Delete this image (${filename})?`)) return;

                    try {
                        const res = await fetch(`/api/photo/history/${encodeURIComponent(filename)}`, { method: 'DELETE' });
                        if (!res.ok) throw new Error('Delete failed');
                        item.remove();
                        if (window.showToast) window.showToast('Image deleted.', 'info');
                    } catch (err) {
                        if (window.showToast) window.showToast(`Error: ${err.message}`, 'error');
                    }
                });
            });
        }
    };

    document.addEventListener('panelLoaded', (e) => {
        if (e.detail && e.detail.tabName === 'image-models') {
            ViewImageModels.init();
        }
    });

    if (document.getElementById('im-section-studio') || document.getElementById('im-prompt')) {
        ViewImageModels.init();
    }

    window.ViewImageModels = ViewImageModels;
})();
