/**
 * app.js — Main application logic for Aethvion Photo
 */
import { CanvasEngine } from './canvas_engine.js';
import { FilterEngine } from './filters.js';

class AethvionPhoto {
    constructor() {
        this.engine = new CanvasEngine('main-canvas');
        this.filters = new FilterEngine(this.engine);
        this.init();
    }

    init() {
        this.bindEvents();
        this.bindFilters();
        console.log("Aethvion Photo Initialized");
        
        // Create initial layer
        this.engine.addLayer('Background');
        this.updateLayerStack();
    }

    bindEvents() {
        // Toolbar
        document.querySelectorAll('.tool-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.tool-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.currentTool = btn.dataset.tool;
            });
        });
        this.currentTool = 'select'; // Default

        // Menu items
        document.querySelectorAll('.menu-item').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const action = e.target.innerText.trim().toLowerCase();
                this.handleMenuAction(action);
            });
        });

        // Export button
        const exportBtn = document.getElementById('btn-export');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.handleExport());
        }

        // Layer actions
        document.getElementById('add-layer-btn').addEventListener('click', () => {
            this.engine.addLayer(`Layer ${this.engine.layers.length + 1}`);
            this.updateLayerStack();
        });

        // Canvas mouse events
        const resetBtn = document.getElementById('reset-filters');
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                this.filters.reset();
                this.syncFilters();
            });
        }
        const canvas = document.getElementById('main-canvas');
        let isDrawing = false;

        canvas.addEventListener('mousedown', (e) => {
            if (this.currentTool === 'brush' || this.currentTool === 'eraser') {
                isDrawing = true;
                this.handleDraw(e);
            }
        });

        canvas.addEventListener('mousemove', (e) => {
            if (isDrawing) {
                this.handleDraw(e);
            }
            this.updateCoords(e);
        });

        window.addEventListener('mouseup', () => {
            isDrawing = false;
        });
    }

    handleMenuAction(action) {
        console.log("Menu action:", action);
        switch (action) {
            case 'file':
                // Show file dropdown (simplified for now)
                break;
            case 'layer':
                this.engine.addLayer(`Layer ${this.engine.layers.length + 1}`);
                this.updateLayerStack();
                break;
            case 'view':
                // Toggle grid etc.
                break;
        }
    }

    handleExport() {
        const dataUrl = this.engine.exportToPNG();
        const link = document.createElement('a');
        link.download = `aethvion-photo-${Date.now()}.png`;
        link.href = dataUrl;
        link.click();
    }

    bindFilters() {
        document.querySelectorAll('#filter-controls input[type="range"]').forEach(input => {
            input.addEventListener('input', (e) => {
                const filter = e.target.dataset.filter;
                const value = parseInt(e.target.value);
                this.filters.setFilter(filter, value);
            });
        });
    }

    syncFilters() {
        const layer = this.engine.getActiveLayer();
        if (!layer) return;

        document.querySelectorAll('#filter-controls input[type="range"]').forEach(input => {
            const filter = input.dataset.filter;
            if (layer.filters.hasOwnProperty(filter)) {
                input.value = layer.filters[filter];
            }
        });
    }

    handleDraw(e) {
        const rect = e.target.getBoundingClientRect();
        const x = (e.clientX - rect.left) * (this.engine.width / rect.width);
        const y = (e.clientY - rect.top) * (this.engine.height / rect.height);
        
        if (this.currentTool === 'brush') {
            this.engine.drawBrush(x, y, '#7c6ff7', 10);
        } else if (this.currentTool === 'eraser') {
            this.engine.drawEraser(x, y, 15);
        }
    }

    updateCoords(e) {
        const rect = e.target.getBoundingClientRect();
        const x = Math.round((e.clientX - rect.left) * (this.engine.width / rect.width));
        const y = Math.round((e.clientY - rect.top) * (this.engine.height / rect.height));
        document.getElementById('coord-display').textContent = `${x} : ${y} px`;
    }

    updateLayerStack() {
        const stack = document.getElementById('layer-stack');
        stack.innerHTML = '';
        
        // Reverse for display (top to bottom)
        [...this.engine.layers].reverse().forEach((layer, revIdx) => {
            const idx = this.engine.layers.length - 1 - revIdx;
            const li = document.createElement('li');
            li.className = `layer-item ${idx === this.engine.activeLayerIndex ? 'active' : ''}`;
            li.innerHTML = `
                <div class="layer-thumb"></div>
                <span class="layer-name">${layer.name}</span>
                <i class="fa-solid ${layer.visible ? 'fa-eye' : 'fa-eye-slash'}"></i>
            `;
            li.onclick = () => {
                this.engine.setActiveLayer(idx);
                this.updateLayerStack();
                this.syncFilters();
            };

            const eye = li.querySelector('.fa-eye, .fa-eye-slash');
            eye.onclick = (e) => {
                e.stopPropagation();
                const isVisible = !layer.visible;
                this.engine.setLayerVisibility(idx, isVisible);
                this.updateLayerStack();
            };

            stack.appendChild(li);
        });
    }
}

window.addEventListener('load', () => {
    window.photoApp = new AethvionPhoto();
});
