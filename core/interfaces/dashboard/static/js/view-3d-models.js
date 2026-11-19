/**
 * Aethvion Suite — 3D Models View (Unified Models View v14.2)
 * 
 * Handles search, filtering, and interaction for 3D generation models.
 */

(function () {
    'use strict';

    const View3DModels = {
        init() {
            this.bindEvents();
            this.initHardwareProfile();
            this.updateStatus();
            this.checkInstallStatus('trellis-2');
            this.checkInstallStatus('hunyuan3d');
            this.checkInstallStatus('triposr');
        },

        initHardwareProfile() {
            if (window.HardwareProfile) {
                window.HardwareProfile.attachToolbarPill('td-hw-slot');
                this.updateHardwareBadges();
                window.HardwareProfile.subscribe(() => {
                    this.updateHardwareBadges();
                    this.filterModels();
                });
            }
            const compatFilter = document.getElementById('td-compat-filter');
            if (compatFilter) {
                compatFilter.addEventListener('change', () => this.filterModels());
            }
        },

        updateHardwareBadges() {
            if (!window.HardwareProfile) return;
            const t2Badge = document.getElementById('trellis2-compat-badge');
            if (t2Badge) {
                t2Badge.innerHTML = window.HardwareProfile.renderBadge({ id: 'trellis-2', type: '3d', req_vram_gb: 16 });
            }
            const hyBadge = document.getElementById('hunyuan3d-compat-badge');
            if (hyBadge) {
                hyBadge.innerHTML = window.HardwareProfile.renderBadge({ id: 'hunyuan3d', type: '3d', req_vram_gb: 20 });
            }
            const tripoBadge = document.getElementById('triposr-compat-badge');
            if (tripoBadge) {
                tripoBadge.innerHTML = window.HardwareProfile.renderBadge({ id: 'triposr', type: '3d', req_vram_gb: 6 });
            }
        },

        bindEvents() {
            const searchInput = document.getElementById('td-model-search');
            if (searchInput) {
                searchInput.addEventListener('input', () => this.filterModels());
            }

            const refreshBtn = document.getElementById('refresh-3d-models');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => this.refresh());
            }

            // Bind for all 3D models
            [{id: 'trellis-2', mid: 'trellis2'}, {id: 'hunyuan3d', mid: 'hunyuan3d'}, {id: 'triposr', mid: 'triposr'}].forEach(m => {
                const btnInstall = document.getElementById(`btn-install-full-${m.mid}`);
                const btnRun = document.getElementById(`btn-run-${m.mid}`);
                const btnFix = document.getElementById(`btn-fix-${m.mid}`);

                if (btnInstall) btnInstall.addEventListener('click', () => this.handleUnifiedInstall(m.id));
                if (btnRun) btnRun.addEventListener('click', (e) => this.handleRunModel(m.id));
                if (btnFix) btnFix.addEventListener('click', () => this.handleRepair(m.id));
            });
        },

        filterModels() {
            const searchInput = document.getElementById('td-model-search');
            const q = (searchInput ? searchInput.value : '').toLowerCase().trim();
            const compatVal = (document.getElementById('td-compat-filter')?.value || 'all').toLowerCase();

            const models = [
                { id: 'trellis-2', name: 'trellis 2 trellis2 pbr', card: document.getElementById('btn-run-trellis2')?.closest('.hub-provider-section') },
                { id: 'hunyuan3d', name: 'hunyuan3d hunyuan 2.1 pbr tencent', card: document.getElementById('btn-run-hunyuan3d')?.closest('.hub-provider-section') },
                { id: 'triposr', name: 'triposr', card: document.getElementById('btn-run-triposr')?.closest('.hub-provider-section') }
            ];

            models.forEach(m => {
                if (!m.card) return;
                const matchesQuery = !q || m.name.includes(q);

                let matchesCompat = true;
                if (compatVal !== 'all' && window.HardwareProfile) {
                    const evalResult = window.HardwareProfile.evaluate({ id: m.id, type: '3d' });
                    if (compatVal === 'runnable') {
                        matchesCompat = evalResult.runnable !== false;
                    } else if (compatVal === 'gpu') {
                        matchesCompat = evalResult.status === 'gpu';
                    }
                }

                m.card.style.display = (matchesQuery && matchesCompat) ? 'block' : 'none';
            });
        },

        async updateStatus() {
            const statusText = document.getElementById('td-engine-status');
            if (!statusText) return;
            try {
                const res = await fetch('/api/3d/status');
                if (res.ok) statusText.textContent = '3D Service: Online';
            } catch (e) {
                statusText.textContent = '3D Service: Offline';
            }
        },

        async checkInstallStatus(modelId) {
            const mid = modelId.replace('-', '');
            const btnInstall = document.getElementById(`btn-install-full-${mid}`);
            const btnRun = document.getElementById(`btn-run-${mid}`);
            const fixContainer = document.getElementById(`${mid}-fix-container`);

            if (!btnInstall || !btnRun) return;

            try {
                const res = await fetch(`/api/3d/install_status/${modelId}?t=${Date.now()}`);
                if (!res.ok) throw new Error('Status check failed');

                const data = await res.json();
                const isFullyReady = data.installed && data.weights_installed;

                const upgBadge = document.getElementById(`${mid}-upgrade-badge`);
                if (upgBadge) upgBadge.style.display = data.needs_upgrade ? 'inline-flex' : 'none';

                btnInstall.style.display = isFullyReady ? 'none' : 'block';
                btnRun.style.display = isFullyReady ? 'block' : 'none';
                if (fixContainer) fixContainer.style.display = isFullyReady ? 'block' : 'none';

                if (isFullyReady) {
                    this.startHealthPolling(modelId);
                }

            } catch (e) {
                console.error(`[View3DModels] Failed to load status for ${modelId}:`, e);
            }
        },

        async handleRepair(modelId) {
            if (!confirm(`This will wipe the current ${modelId} deployment and re-initialize the environment. Weights will be preserved if already valid. Proceed?`)) return;

            const mid = modelId.replace('-', '');
            const fixContainer = document.getElementById(`${mid}-fix-container`);
            if (fixContainer) fixContainer.style.display = 'none';

            let skipWeights = false;
            try {
                await fetch(`/api/3d/stop/${modelId}`, { method: 'POST' });
                const stRes = await fetch(`/api/3d/install_status/${modelId}?t=${Date.now()}`);
                if (stRes.ok) {
                    const st = await stRes.json();
                    const expectedRepos = {
                        'trellis-2': 'microsoft/TRELLIS.2-4B',
                        'hunyuan3d': 'tencent/Hunyuan3D-2.1',
                        'triposr': 'stabilityai/TripoSR',
                    };
                    if (st.weights_installed && (!st.weights_repo || st.weights_repo === expectedRepos[modelId])) {
                        skipWeights = true;
                    }
                }
                const ok = await this.handleUnifiedInstall(modelId, { skipWeightsIfPresent: skipWeights });
                if (ok) window.showToast(`${modelId} repair complete.`, 'success');
            } catch (e) {
                window.showToast(`Repair failed: ${e.message}`, 'error');
                if (fixContainer) fixContainer.style.display = 'block';
            }
        },

        pollIntervals: {},
        startHealthPolling(modelId) {
            if (this.pollIntervals[modelId]) return;

            const mid = modelId.replace('-', '');
            const badge = document.getElementById(`${mid}-health-badge`);
            const statusDot = document.querySelector('.td-status-dot');
            const statusText = document.getElementById('td-engine-status');

            const check = async () => {
                try {
                    const res = await fetch(`/api/3d/health/${modelId}`);
                    const data = await res.json();

                    if (!badge) return;

                    const label = modelId === 'trellis-2' ? 'TRELLIS.2-4B' : modelId === 'hunyuan3d' ? 'Hunyuan3D 2.1' : 'TripoSR';

                    if (data.status === 'online') {
                        badge.innerHTML = `<i class="fas fa-check-circle" style="color:#4ade80;"></i> ${label} is Ready`;
                        badge.style.borderColor = 'rgba(74, 222, 128, 0.4)';
                        badge.style.color = '#4ade80';
                        badge.style.animation = 'none';
                        badge.classList.remove('pulse-amber');

                        if (statusDot) statusDot.style.background = '#4ade80';
                        if (statusText) statusText.textContent = 'Service: Running';

                        clearInterval(this.pollIntervals[modelId]);
                        delete this.pollIntervals[modelId];

                    } else if (data.status === 'launching') {
                        const vram = data.vram_used > 0
                            ? ` (${data.vram_used.toFixed(1)} / ${data.vram_total.toFixed(1)} GB VRAM)`
                            : '';
                        badge.innerHTML = `<i class="fas fa-spinner fa-spin" style="color:#fb923c;"></i> Loading VRAM…${vram}`;
                        badge.style.borderColor = 'rgba(251, 146, 60, 0.4)';
                        badge.style.color = '#fb923c';
                        badge.classList.add('pulse-amber');

                        if (statusDot) statusDot.style.background = '#fb923c';
                        if (statusText) statusText.textContent = 'Service: Launching';

                    } else if (data.status === 'failed') {
                        badge.innerHTML = `<i class="fas fa-exclamation-triangle" style="color:#f87171;"></i> ${label} Load failed`;
                        badge.style.borderColor = 'rgba(248, 113, 113, 0.4)';
                        badge.style.color = '#f87171';
                        badge.classList.remove('pulse-amber');

                        if (statusDot) statusDot.style.background = '#f87171';
                        if (statusText) statusText.textContent = 'Service: Error';

                        clearInterval(this.pollIntervals[modelId]);
                        delete this.pollIntervals[modelId];

                    } else {
                        badge.innerHTML = '<i class="fas fa-power-off"></i> Offline';
                        badge.style.borderColor = 'rgba(255,255,255,0.1)';
                        badge.style.color = 'var(--text-tertiary)';
                        badge.classList.remove('pulse-amber');
                    }
                } catch (e) { }
            };

            if (!document.getElementById('td-hub-styles')) {
                const style = document.createElement('style');
                style.id = 'td-hub-styles';
                style.innerHTML = `
                    @keyframes pulse-amber {
                        0% { opacity: 0.6; box-shadow: 0 0 0px rgba(251, 146, 60, 0); }
                        50% { opacity: 1.0; box-shadow: 0 0 15px rgba(251, 146, 60, 0.3); }
                        100% { opacity: 0.6; box-shadow: 0 0 0px rgba(251, 146, 60, 0); }
                    }
                    .pulse-amber { animation: pulse-amber 2s infinite ease-in-out; }
                `;
                document.head.appendChild(style);
            }

            check();
            this.pollIntervals[modelId] = setInterval(check, 3000);
        },

        _markInstallFailed(modelId, phase, errMsg) {
            const mid = modelId.replace('-', '');
            const logElement = document.getElementById(`${mid}-install-log`);
            const bar = document.getElementById(`${phase === 'weights' ? 'weights' : 'engine'}-bar-${mid}`);
            const text = document.getElementById(`${phase === 'weights' ? 'weights' : 'engine'}-text-${mid}`);
            const btnFull = document.getElementById(`btn-install-full-${mid}`);
            const fixContainer = document.getElementById(`${mid}-fix-container`);
            if (bar) bar.style.background = '#f87171';
            if (text) {
                text.style.color = '#f87171';
                text.textContent = `${phase === 'weights' ? '2. Model Weights' : '1. Environment & Core Files'} (Failed — see log below)`;
            }
            if (logElement) {
                logElement.textContent += `\n[ERROR] ${errMsg}\n`;
                logElement.scrollTop = logElement.scrollHeight;
            }
            if (btnFull) btnFull.style.display = 'block';
            if (fixContainer) fixContainer.style.display = 'block';
        },

        async handleUnifiedInstall(modelId, opts = {}) {
            const mid = modelId.replace('-', '');
            const btnFull = document.getElementById(`btn-install-full-${mid}`);
            const progressContainer = document.getElementById(`${mid}-install-progress-container`);
            const logContainer = document.getElementById(`${mid}-install-log-container`);
            const logElement = document.getElementById(`${mid}-install-log`);
            const engineBar = document.getElementById(`engine-bar-${mid}`);
            const weightsBar = document.getElementById(`weights-bar-${mid}`);

            if (btnFull) btnFull.style.display = 'none';
            if (progressContainer) progressContainer.style.display = 'block';
            if (logContainer) logContainer.style.display = 'block';
            if (logElement) logElement.textContent = `[System] Initiating ${modelId} Deployment...\n`;
            if (engineBar) { engineBar.style.width = '0%'; engineBar.style.background = ''; }
            if (weightsBar) { weightsBar.style.width = '0%'; weightsBar.style.background = ''; }

            try {
                const phase1Success = await this.installModelPhase(modelId);
                if (!phase1Success) return false;
                if (opts.skipWeightsIfPresent) {
                    const wText = document.getElementById(`weights-text-${mid}`);
                    const wPercent = document.getElementById(`weights-percent-${mid}`);
                    const wWrap = document.getElementById(`progress-weights-${mid}`);
                    if (wWrap) wWrap.style.opacity = '1';
                    if (weightsBar) weightsBar.style.width = '100%';
                    if (wPercent) wPercent.textContent = '100%';
                    if (wText) wText.textContent = '2. Model Weights (Preserved)';
                    if (logElement) logElement.textContent += '[System] Existing model weights preserved.\n';
                    window.showToast(`${modelId} is ready!`, 'success');
                    setTimeout(() => { this.checkInstallStatus(modelId); }, 1000);
                    return true;
                }
                return await this.installWeightsPhase(modelId);
            } catch (e) {
                window.showToast(`${modelId} setup failed: ${e.message}`, 'error');
                return false;
            }
        },

        async installModelPhase(modelId) {
            const mid = modelId.replace('-', '');
            const logElement = document.getElementById(`${mid}-install-log`);
            const bar = document.getElementById(`engine-bar-${mid}`);
            const percent = document.getElementById(`engine-percent-${mid}`);
            const text = document.getElementById(`engine-text-${mid}`);

            if (text) { text.style.color = ''; text.textContent = '1. Environment & Core Files (Active)'; }

            try {
                const res = await fetch(`/api/3d/install/${modelId}`, { method: 'POST' });
                if (!res.ok) throw new Error(`Install endpoint returned HTTP ${res.status}`);
                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let sawDone = false;

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

                        if (msg.line) {
                            logElement.textContent += msg.line + '\n';
                            logElement.scrollTop = logElement.scrollHeight;

                            if (msg.line.includes('environment')) { bar.style.width = '30%'; percent.textContent = '30%'; }
                            if (msg.line.includes('Cloning') || msg.line.includes('repository')) { bar.style.width = '50%'; percent.textContent = '50%'; }
                            if (msg.line.includes('Installing') || msg.line.includes('dependencies') || msg.line.includes('Building')) { bar.style.width = '75%'; percent.textContent = '75%'; }
                        }
                        if (msg.done) {
                            sawDone = true;
                            if (msg.success) {
                                if (bar) bar.style.width = '100%';
                                if (percent) percent.textContent = '100%';
                                if (text) text.textContent = '1. Environment & Core Files (Ready)';
                                return true;
                            } else {
                                throw new Error(msg.error || 'Setup failed');
                            }
                        }
                    }
                }
                if (!sawDone) throw new Error('Install stream ended unexpectedly before completion.');
            } catch (e) {
                this._markInstallFailed(modelId, 'engine', e.message);
                throw e;
            }
        },

        async installWeightsPhase(modelId) {
            const mid = modelId.replace('-', '');
            const logElement = document.getElementById(`${mid}-install-log`);
            const bar = document.getElementById(`weights-bar-${mid}`);
            const percent = document.getElementById(`weights-percent-${mid}`);
            const text = document.getElementById(`weights-text-${mid}`);
            const weightContainer = document.getElementById(`progress-weights-${mid}`);

            if (weightContainer) weightContainer.style.opacity = '1';
            if (text) { text.style.color = ''; text.textContent = '2. Model Weights (Active)'; }

            try {
                const response = await fetch(`/api/3d/install_weights/${modelId}`, { method: 'POST' });
                if (!response.ok) throw new Error(`Weights endpoint returned HTTP ${response.status}`);
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = "";
                let sawDone = false;

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const parts = buffer.split('\n\n');
                    buffer = parts.pop();

                    for (const part of parts) {
                        if (!part.startsWith('data: ')) continue;
                        let json;
                        try {
                            json = JSON.parse(part.substring(6));
                        } catch {
                            continue;
                        }
                        if (json.line) {
                            if (json.line.includes('\r')) {
                                const lines = logElement.textContent.split('\n');
                                lines[lines.length - 1] = json.line.split('\r').pop();
                                logElement.textContent = lines.join('\n');
                            } else {
                                logElement.textContent += json.line + '\n';
                            }
                            logElement.scrollTop = logElement.scrollHeight;

                            const matches = json.line.match(/(\d+)%/g);
                            if (matches && bar && percent) {
                                const p = matches[matches.length - 1].replace('%', '') + '%';
                                bar.style.width = p;
                                percent.textContent = p;
                            }
                        }
                        if (json.done) {
                            sawDone = true;
                            if (json.success) {
                                if (bar) bar.style.width = '100%';
                                if (percent) percent.textContent = '100%';
                                if (text) text.textContent = '2. Model Weights (Ready)';

                                setTimeout(() => {
                                    document.getElementById(`${mid}-install-progress-container`).style.display = 'none';
                                    document.getElementById(`${mid}-install-log-container`).style.display = 'none';
                                    window.showToast(`${modelId} is ready!`, 'success');
                                    this.checkInstallStatus(modelId);
                                }, 1500);
                                return true;
                            } else {
                                throw new Error(json.error || 'Weight download failed');
                            }
                        }
                    }
                }
                if (!sawDone) throw new Error('Weight download stream ended unexpectedly.');
            } catch (e) {
                this._markInstallFailed(modelId, 'weights', e.message);
                throw e;
            }
        },

        async handleRunModel(modelId) {
            window.showToast(`Launching ${modelId}…`, 'info');
            try {
                const res = await fetch(`/api/3d/launch/${modelId}`);
                const data = await res.json();
                if (!data.success) {
                    window.showToast(`Launch failed: ${data.error}`, 'error');
                    return;
                }
                this.startHealthPolling(modelId);
            } catch (e) {
                window.showToast(`Launch error: ${e.message}`, 'error');
            }
        },

        refresh() {
            const icon = document.querySelector('#refresh-3d-models i');
            if (icon) icon.classList.add('fa-spin');
            setTimeout(() => {
                this.checkInstallStatus('trellis-2');
                this.checkInstallStatus('hunyuan3d');
                this.checkInstallStatus('triposr');
                this.updateStatus();
                if (icon) icon.classList.remove('fa-spin');
                window.showToast('3D Models refreshed.', 'success');
            }, 800);
        }
    };

    document.addEventListener('panelLoaded', (e) => {
        if (e.detail && e.detail.tabName === '3d-models') View3DModels.init();
    });
    if (document.getElementById('td-model-search')) {
        View3DModels.init();
    }
    window.View3DModels = View3DModels;
})();
