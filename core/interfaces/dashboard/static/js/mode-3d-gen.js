/**
 * Aethvion Suite — 3D Workspace Mode
 * 
 * Logic for generation, previewing, and managing 3D assets.
 * Integrates with ThreeDViewer engine for high-fidelity rendering.
 */

import { ThreeDViewer } from './3d-viewer.js';

(function () {
    'use strict';

    const Mode3DGen = {
        state: {
            currentMode: 'i23d', // 'i23d' or 't23d'
            generating: false,
            uploadedImage: null,
            initialized: false,
            viewer: null
        },

        init() {
            if (this.state.initialized) {
                console.log('[Mode3DGen] Already initialized.');
                return;
            }
            console.log('[Mode3DGen] Initializing Workspace (Three.js Engine)...');
            
            // Initialize Three.js Viewer
            this.state.viewer = new ThreeDViewer('tg-three-container');

            this.bindEvents();
            this.initDropzone();
            this.loadHistory();
            this.state.initialized = true;

            // Handle listener for loading states
            const container = document.getElementById('tg-three-container');
            const overlay = document.getElementById('tg-loading');

            if (container) {
                container.addEventListener('viewer-loading', () => {
                    if (overlay) overlay.style.display = 'flex';
                });
                container.addEventListener('viewer-loaded', (e) => {
                    if (overlay) overlay.style.display = 'none';
                    this.updateModelInfo(this.state.viewer);
                });
                container.addEventListener('viewer-error', (e) => {
                    if (overlay) overlay.style.display = 'none';
                    window.showToast('Model render error', 'error');
                });
            }
        },

        bindEvents() {
            // Tab Switching
            document.querySelectorAll('.tg-tab-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const type = btn.dataset.type;
                    this.switchMode(type);
                });
            });

            // Generate Button
            const genBtn = document.getElementById('tg-generate-btn');
            if (genBtn) {
                genBtn.addEventListener('click', () => this.handleGenerate());
            }

            // Lighting Presets (New Three.js v14.2)
            document.querySelectorAll('[data-preset]').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const preset = e.target.dataset.preset;
                    this.state.viewer.setLightingPreset(preset);
                    
                    document.querySelectorAll('[data-preset]').forEach(b => b.classList.remove('active'));
                    e.target.classList.add('active');
                });
            });

            // Lighting Intensity
            const intensitySlider = document.getElementById('ctrl-light-intensity');
            if (intensitySlider) {
                intensitySlider.addEventListener('input', (e) => {
                    if (this.state.viewer) {
                        this.state.viewer.setLightIntensity(e.target.value);
                    }
                });
            }

            // View Mode Shading (Normal/Wireframe)
            document.querySelectorAll('.tg-mode-chip[data-mode]').forEach(chip => {
                chip.addEventListener('click', (e) => {
                    const mode = e.target.dataset.mode;
                    if (!this.state.viewer || !this.state.viewer.model) return;

                    this.applyShadingMode(mode);

                    document.querySelectorAll('.tg-mode-chip[data-mode]').forEach(c => c.classList.remove('active'));
                    e.target.classList.add('active');
                });
            });

            // Utility Controls
            const btnFloor = document.getElementById('ctrl-floor');
            if (btnFloor) {
                btnFloor.addEventListener('click', () => {
                    const nextState = !btnFloor.classList.contains('active');
                    this.state.viewer.toggleFloor(nextState);
                    btnFloor.classList.toggle('active', nextState);
                });
            }

            const btnResetCam = document.getElementById('ctrl-reset-cam');
            if (btnResetCam) {
                btnResetCam.addEventListener('click', () => {
                    this.state.viewer.resetCamera();
                });
            }
        },

        applyShadingMode(mode) {
            if (this.state.viewer) {
                this.state.viewer.setShadingMode(mode);
            }
        },

        updateModelInfo(viewerEngine) {
            const infoBox = document.getElementById('tg-model-stats');
            const customLoader = document.querySelector('.tg-loader-sphere');
            
            if (customLoader) {
                customLoader.style.visibility = 'hidden';
                customLoader.style.display = 'none';
            }

            if (!infoBox || !viewerEngine.model) {
                if (infoBox) infoBox.style.display = 'none';
                return;
            }

            infoBox.style.display = 'flex';

            // Calculate real triangle and vertex counts from Three.js
            let totalTris = 0;
            let totalVerts = 0;

            viewerEngine.model.traverse(obj => {
                if (obj.isMesh && obj.geometry) {
                    const geo = obj.geometry;
                    if (geo.index) {
                        totalTris += geo.index.count / 3;
                    } else if (geo.attributes.position) {
                        totalTris += geo.attributes.position.count / 3;
                    }
                    if (geo.attributes.position) {
                        totalVerts += geo.attributes.position.count;
                    }
                }
            });

            try {
                const modelPath = viewerEngine.model.name || 'Generated Mesh';
                
                infoBox.innerHTML = `
                    <div class="tg-stat-item"><span style="color:var(--primary); font-weight:700;">SPECIFICATIONS</span></div>
                    <div class="tg-stat-item"><span>Format</span> <span class="tg-stat-val">GLB/2.0</span></div>
                    <div class="tg-stat-item"><span>Complexity</span> <span class="tg-stat-val">${Math.round(totalTris).toLocaleString()} tris</span></div>
                    <div class="tg-stat-item"><span>Topology</span> <span class="tg-stat-val">${Math.round(totalVerts).toLocaleString()} verts</span></div>
                `;
            } catch (e) {
                console.warn('[Mode3DGen] Stat calculation failed:', e);
            }
        },

        switchMode(mode) {
            this.state.currentMode = mode;
            
            document.querySelectorAll('.tg-tab-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.type === mode);
            });

            const i23dGroup = document.getElementById('tg-group-i23d');
            const t23dGroup = document.getElementById('tg-group-t23d');

            if (mode === 'i23d') {
                i23dGroup.style.display = 'flex';
                t23dGroup.style.display = 'none';
            } else {
                i23dGroup.style.display = 'none';
                t23dGroup.style.display = 'flex';
            }
        },

        initDropzone() {
            const dropzone = document.getElementById('tg-dropzone');
            const fileInput = document.getElementById('tg-file-input');
            const preview = document.getElementById('tg-preview');

            if (!dropzone || !fileInput) return;

            dropzone.addEventListener('click', () => fileInput.click());

            fileInput.addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (file) this.handleImage(file);
            });

            dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.style.borderColor = 'var(--primary)'; });
            dropzone.addEventListener('dragleave', () => { dropzone.style.borderColor = 'var(--border)'; });

            dropzone.addEventListener('drop', (e) => {
                e.preventDefault();
                const file = e.dataTransfer.files[0];
                if (file) this.handleImage(file);
            });
        },

        handleImage(file) {
            if (!file.type.startsWith('image/')) {
                window.showToast('Please upload a valid image file.', 'error');
                return;
            }

            const reader = new FileReader();
            const preview = document.getElementById('tg-preview');
            
            reader.onload = (e) => {
                preview.src = e.target.result;
                preview.style.display = 'block';
                this.state.uploadedImage = e.target.result;
            };
            reader.readAsDataURL(file);
        },

        async handleGenerate() {
            if (this.state.generating) return;

            const model = document.getElementById('tg-model-select').value;
            const prompt = document.getElementById('tg-prompt').value;
            const quality = document.getElementById('tg-quality').value;
            const textured = document.getElementById('tg-textured').checked;
            const pbr = Boolean(document.getElementById('tg-pbr')?.checked);
            const seed = document.getElementById('tg-seed').value;

            if (this.state.currentMode === 'i23d' && !this.state.uploadedImage) {
                window.showToast('Please upload a reference image.', 'warn');
                return;
            }
            if (this.state.currentMode === 't23d' && !prompt.trim()) {
                window.showToast('Please enter a description.', 'warn');
                return;
            }

            this.state.generating = true;
            this.updateGenUI(true);

            try {
                const response = await fetch('/api/3d/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action: this.state.currentMode,
                        prompt: prompt,
                        input_image: this.state.uploadedImage,
                        model: model,
                        quality: quality,
                        textured: textured,
                        pbr: pbr,
                        seed: seed ? parseInt(seed) : null
                    })
                });

                if (response.status === 503) {
                    const modelLabel = model === 'triposr' ? 'TripoSR' : 'Trellis 2';
                    window.showToast(`${modelLabel} is launching...`, 'info');
                    return;
                }

                const data = await response.json();
                if (!data.success) throw new Error(data.error || 'Generation failed');
                
                window.showToast('Mesh generated successfully!', 'success');
                this.showResult(data.asset);
            } catch (e) {
                console.error('[Mode3DGen] Generation error:', e);
                window.showToast('Generation failed: ' + e.message, 'error');
            } finally {
                this.state.generating = false;
                this.updateGenUI(false);
            }
        },

        updateGenUI(isGenerating) {
            const btn = document.getElementById('tg-generate-btn');
            const overlay = document.getElementById('tg-loading');
            
            if (isGenerating) {
                btn.disabled = true;
                btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> GENERATING...';
                overlay.style.display = 'flex';
            } else {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i> GENERATE 3D ASSET';
                overlay.style.display = 'none';
            }
        },

        showResult(asset) {
            const placeholder = document.getElementById('tg-placeholder');
            const canvasRoot = document.getElementById('tg-canvas-root');
            
            if (!asset || !asset.url) return;
            
            if (placeholder) placeholder.style.display = 'none';
            if (canvasRoot) canvasRoot.style.display = 'block';
            
            if (this.state.viewer) {
                this.state.viewer.onResize();
                this.state.viewer.loadModel(asset.url);
            }

            this.loadHistory();
        },

        async loadHistory() {
            const list = document.getElementById('tg-history-list');
            if (!list) return;

            try {
                const response = await fetch('/api/3d/history?page=1&limit=10');
                const data = await response.json();
                const assets = data.assets || [];
                
                list.innerHTML = '';
                assets.forEach(asset => {
                    const card = document.createElement('div');
                    card.className = 'tg-asset-card';
                    card.onclick = () => this.showResult(asset);
                    
                    const sizeMB = (asset.size_bytes / (1024 * 1024)).toFixed(1);
                    const date = new Date(asset.created_at).toLocaleDateString();
                    const thumbHtml = asset.thumbnail_url 
                        ? `<img src="${asset.thumbnail_url}" alt="Preview" class="tg-asset-thumbnail">`
                        : `<div class="tg-asset-placeholder"><i class="fas fa-cube"></i></div>`;

                    card.innerHTML = `
                        <div class="tg-asset-thumb">${thumbHtml}</div>
                        <div class="tg-asset-info">
                            <span class="tg-asset-name">${asset.name || 'Generated Mesh'}</span>
                            <span class="tg-asset-meta">${date} • ${sizeMB} MB</span>
                        </div>
                    `;
                    list.appendChild(card);
                });

                if (assets.length === 0) {
                    list.innerHTML = '<div style="text-align:center; padding:2rem; color:var(--text-tertiary); font-size:0.8rem;">No recent generations</div>';
                }
            } catch (e) {
                console.error('[Mode3DGen] History load failed:', e);
            }
        }
    };

    // Register with tab system
    if (typeof registerTabInit === 'function') {
        registerTabInit('3d-gen', () => Mode3DGen.init());
    }

    // Panel loading hook
    document.addEventListener('panelLoaded', (e) => {
        if (e.detail.tabName === '3d-gen') {
            Mode3DGen.init();
        }
    });

    window.Mode3DGen = Mode3DGen;
})();
