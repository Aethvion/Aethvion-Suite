/**
 * Aethvion Suite — 3D Models View
 * 
 * Handles search, filtering, and interaction for 3D generation models.
 */

(function () {
    'use strict';

    const View3DModels = {
        init() {
            console.log('[View3DModels] Initializing...');
            this.bindEvents();
            this.updateStatus();
            this.loadLocalModels();
        },

        bindEvents() {
            // Search filtering
            const searchInput = document.getElementById('td-model-search');
            if (searchInput) {
                searchInput.addEventListener('input', (e) => this.filterModels(e.target.value));
            }

            // Refresh button
            const refreshBtn = document.getElementById('refresh-3d-models');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => {
                    this.refresh();
                });
            }

            // Generation cards
            document.querySelectorAll('.td-gen-card .td-btn-action').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const card = e.target.closest('.td-gen-card');
                    const modelId = card.dataset.model;
                    this.handleRunModel(modelId);
                });
            });

            // Mini tool buttons
            document.querySelectorAll('.td-mini-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const itemName = e.target.closest('.td-tool-item').querySelector('.td-item-name').textContent;
                    window.showToast(`Loading ${itemName} configuration...`, 'info');
                });
            });
        },

        filterModels(query) {
            const q = query.toLowerCase();
            document.querySelectorAll('.td-gen-card').forEach(card => {
                const name = card.querySelector('.td-gen-name').textContent.toLowerCase();
                const desc = card.querySelector('.td-gen-desc').textContent.toLowerCase();
                const visible = name.includes(q) || desc.includes(q);
                card.style.display = visible ? 'flex' : 'none';
            });
        },

        async updateStatus() {
            const statusText = document.getElementById('td-engine-status');
            if (!statusText) return;

            try {
                // Placeholder for real backend check
                // const res = await fetch('/api/system/3d/status');
                // const data = await res.json();
                statusText.textContent = '3D Engine Ready';
            } catch (e) {
                statusText.textContent = '3D Engine Offline';
                statusText.parentElement.querySelector('.td-status-dot').style.background = 'var(--error)';
            }
        },

        async loadLocalModels() {
            const grid = document.getElementById('td-local-grid');
            if (!grid) return;

            try {
                // Placeholder for fetching local checkpoints
                // const res = await fetch('/api/models/3d/local');
                // const data = await res.json();
                
                // For now, keep the empty message or add placeholders if any are detected
            } catch (e) {
                console.error('[View3DModels] Failed to load local models:', e);
            }
        },

        handleRunModel(modelId) {
            window.showToast(`Selected model: ${modelId}. Feature integration coming soon.`, 'info');
            
            // Logic to switch to a generation workspace or open a modal
            if (modelId === 'trellis-2') {
                console.log('Trellis 2 selected');
            }
        },

        refresh() {
            const icon = document.querySelector('#refresh-3d-models i');
            if (icon) icon.classList.add('fa-spin');
            
            setTimeout(() => {
                this.loadLocalModels();
                this.updateStatus();
                if (icon) icon.classList.remove('fa-spin');
                window.showToast('3D Model database updated.', 'success');
            }, 800);
        }
    };

    // Initialize when panel is loaded
    document.addEventListener('panelLoaded', (e) => {
        if (e.detail.tabName === '3d-models') {
            View3DModels.init();
        }
    });

    window.View3DModels = View3DModels;

})();
