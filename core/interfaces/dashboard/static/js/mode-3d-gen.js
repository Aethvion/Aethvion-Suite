/**
 * Aethvion Suite — 3D Workspace Mode
 * 
 * Logic for generation, previewing, and managing 3D assets.
 */

(function () {
    'use strict';

    const Mode3DGen = {
        state: {
            currentMode: 'i23d', // 'i23d' or 't23d'
            generating: false,
            uploadedImage: null
        },

        init() {
            console.log('[Mode3DGen] Initializing Workspace...');
            this.bindEvents();
            this.initDropzone();
            this.loadHistory();
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

            // HUD Controls
            document.querySelectorAll('.tg-view-control').forEach(ctrl => {
                ctrl.addEventListener('click', (e) => {
                    const viewer = document.getElementById('tg-model-viewer');
                    if (!viewer) return;
                    
                    const title = ctrl.getAttribute('title');
                    if (title === 'Auto-Rotate') {
                        viewer.autoRotate = !viewer.autoRotate;
                        ctrl.classList.toggle('active', viewer.autoRotate);
                    } else if (title === 'Toggle Grid') {
                        // model-viewer doesn't have a native grid toggle, 
                        // we'd need a custom floor plane, but let's at least show the intention
                        window.showToast('Grid toggle toggled', 'info');
                    } else if (title === 'Toggle wireframe') {
                        window.showToast('Wireframe mode (Coming soon)', 'info');
                    }
                });
            });
        },

        switchMode(mode) {
            this.state.currentMode = mode;
            
            // UI Updates
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

            dropzone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropzone.style.borderColor = 'var(--primary)';
            });

            dropzone.addEventListener('dragleave', () => {
                dropzone.style.borderColor = 'var(--border)';
            });

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
            const seed = document.getElementById('tg-seed').value;

            // Basic Validation
            if (this.state.currentMode === 'i23d' && !this.state.uploadedImage) {
                window.showToast('Please upload a reference image.', 'warn');
                return;
            }
            if (this.state.currentMode === 't23d' && !prompt.trim()) {
                window.showToast('Please enter a description.', 'warn');
                return;
            }

            // Start Generation
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
                        seed: seed ? parseInt(seed) : null
                    })
                });

                if (response.status === 503) {
                    window.showToast('Trellis 2 is currently launching (Loading 12GB VRAM payload). Please wait...', 'info');
                    return;
                }

                const data = await response.json();
                if (!data.success) throw new Error(data.error || 'Generation failed');
                
                window.showToast('3D Generation Successful! Previewing mesh...', 'success');
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
            const viewer = document.getElementById('tg-model-viewer');
            
            if (!asset || !asset.url) return;
            
            if (placeholder) placeholder.style.display = 'none';
            if (canvasRoot) canvasRoot.style.display = 'block';
            
            if (viewer) {
                viewer.src = asset.url;
                viewer.dismissPoster();
            }

            this.loadHistory();
        },

        async loadHistory() {
            const list = document.getElementById('tg-history-list');
            if (!list) return;

            try {
                const response = await fetch('/api/3d/history');
                const assets = await response.json();
                
                list.innerHTML = '';
                assets.forEach(asset => {
                    const card = document.createElement('div');
                    card.className = 'tg-asset-card';
                    card.onclick = () => this.showResult(asset);
                    
                    const sizeMB = (asset.size_bytes / (1024 * 1024)).toFixed(1);
                    
                    card.innerHTML = `
                        <div class="tg-asset-thumb">
                            <i class="fas fa-cube" style="font-size:2rem; color:var(--primary);"></i>
                        </div>
                        <div class="tg-asset-info">
                            <span class="tg-asset-name">${asset.name || 'Generated Mesh'}</span>
                            <span class="tg-asset-meta">${asset.model} • ${asset.format.toUpperCase()} • ${sizeMB} MB</span>
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

    // Also listen for panelLoaded as a secondary hook
    document.addEventListener('panelLoaded', (e) => {
        if (e.detail.tabName === '3d-gen') {
            Mode3DGen.init();
        }
    });

    window.Mode3DGen = Mode3DGen;

})();
