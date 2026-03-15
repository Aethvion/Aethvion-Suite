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
        const menuMapping = {
            'file': () => this.handleFileAction('open'), // Default to open for now
            'edit': () => this.handleEditAction('clear_layer'),
            'image': () => this.handleImageAction('flip_h'),
            'layer': () => this.handleLayerAction('new'),
            'filter': () => this.handleFilterAction('invert'),
            'view': () => console.log("View options coming soon")
        };

        document.querySelectorAll('.menu-item').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const action = e.target.innerText.trim().toLowerCase();
                if (menuMapping[action]) menuMapping[action]();
                
                // Allow specific project loading if Shift+Clicking File
                if (action === 'file' && e.shiftKey) {
                    this.triggerFileOpen('project');
                }
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
        // We can use a map or more complex routing, but for now simple switch
        const menuItems = {
            'file': ['New', 'Open', 'Save Project', 'Export'],
            'edit': ['Undo', 'Clear Layer'],
            'image': ['Flip Horizontal', 'Flip Vertical'],
            'layer': ['New Layer', 'Delete Layer', 'Merge Down'],
            'filter': ['Invert Colors'],
            'view': ['Zoom In', 'Zoom Out', 'Reset View']
        };
        // This button click just identifies the top level. 
        // We actually need to handle the dropdown content if it existed.
        // For now, we will interpret the NEXT click or just use simplified logic.
        console.log("Menu bar interaction:", action);
    }

    // Simplified handlers for the actions we want to implement
    async handleFileAction(subAction) {
        switch(subAction) {
            case 'new':
                if (confirm("Create new project? Current work will be lost.")) {
                    this.engine.layers = [];
                    this.engine.addLayer('Background');
                    this.updateLayerStack();
                }
                break;
            case 'open':
                this.triggerFileOpen('image');
                break;
            case 'save_project':
                this.handleSaveProject();
                break;
            case 'export':
                this.handleExport();
                break;
        }
    }

    handleEditAction(subAction) {
        switch(subAction) {
            case 'clear_layer':
                const layer = this.engine.getActiveLayer();
                if (layer) {
                    layer.clear();
                    this.engine.render();
                }
                break;
        }
    }

    handleImageAction(subAction) {
        switch(subAction) {
            case 'flip_h': this.engine.flipHorizontal(); break;
            case 'flip_v': this.engine.flipVertical(); break;
        }
    }

    handleLayerAction(subAction) {
        switch(subAction) {
            case 'new':
                this.engine.addLayer(`Layer ${this.engine.layers.length + 1}`);
                this.updateLayerStack();
                break;
            case 'delete':
                if (this.engine.layers.length > 1) {
                    this.engine.removeLayer(this.engine.activeLayerIndex);
                    this.updateLayerStack();
                }
                break;
        }
    }

    handleFilterAction(subAction) {
        switch(subAction) {
            case 'invert': this.engine.invertColors(); break;
        }
    }

    triggerFileOpen(type) {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = type === 'project' ? '.aethphoto' : 'image/*';
        input.onchange = (e) => {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = async (event) => {
                if (type === 'project') {
                    await this.engine.fromJSON(event.target.result);
                    this.updateLayerStack();
                    this.syncFilters();
                } else {
                    await this.engine.loadImage(event.target.result, file.name);
                    this.updateLayerStack();
                }
            };
            if (type === 'project') reader.readAsText(file);
            else reader.readAsDataURL(file);
        };
        input.click();
    }

    handleSaveProject() {
        const json = this.engine.toJSON();
        const blob = new Blob([json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.download = `project-${Date.now()}.aethphoto`;
        link.href = url;
        link.click();
        URL.revokeObjectURL(url);
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
