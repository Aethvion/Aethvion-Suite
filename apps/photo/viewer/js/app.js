/**
 * app.js — Main application logic for Aethvion Photo
 */
import { CanvasEngine } from './canvas_engine.js';
import { FilterEngine } from './filters.js';

class Workspace {
    constructor(name, engine) {
        this.id = Math.random().toString(36).substr(2, 9);
        this.name = name;
        this.engine = engine;
    }
}

class AethvionPhoto {
    constructor() {
        this.workspaces = [];
        this.activeWorkspaceIndex = -1;
        this.currentTool = 'select';
        
        this.init();
    }

    init() {
        this.bindEvents();
        this.bindDropdowns();
        this.bindFilters();
        
        // Create initial workspace
        this.addWorkspace("Untitled-1", true);
        
        console.log("Aethvion Photo Multi-Workspace Initialized");
    }

    addWorkspace(name, withInitialLayer = true) {
        const engine = new CanvasEngine('main-canvas');
        const workspace = new Workspace(name, engine);
        this.workspaces.push(workspace);
        this.setActiveWorkspace(this.workspaces.length - 1);
        this.updateTabStrip();
        
        if (withInitialLayer) {
            engine.addLayer('Background');
        }
        this.updateLayerStack();
    }

    setActiveWorkspace(index) {
        if (index < 0 || index >= this.workspaces.length) return;
        this.activeWorkspaceIndex = index;
        const ws = this.getActiveWorkspace();
        
        this.updateTabStrip();
        this.updateLayerStack();
        this.syncFilters();
        this.syncCanvasSettings();
        this.syncZoomDisplay();
        this.syncZoomCSS();
        
        // Update shared canvas resolution
        ws.engine.setupCanvas();
        
        document.getElementById('coord-display').textContent = `0 : 0 px`;
    }

    syncCanvasSettings() {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        document.getElementById('canvas-width').value = ws.engine.width;
        document.getElementById('canvas-height').value = ws.engine.height;
    }

    syncZoomCSS() {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        const canvas = document.getElementById('main-canvas');
        const container = canvas.parentElement;
        
        canvas.style.transform = `scale(${ws.engine.zoom})`;
        
        // Adjust container size so it scrolls correctly
        container.style.width = (ws.engine.width * ws.engine.zoom) + 'px';
        container.style.height = (ws.engine.height * ws.engine.zoom) + 'px';
    }

    syncZoomDisplay() {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        const zoomPct = Math.round(ws.engine.zoom * 100);
        document.getElementById('zoom-display').textContent = `Zoom: ${zoomPct}%`;
    }

    getActiveWorkspace() {
        return this.workspaces[this.activeWorkspaceIndex];
    }

    get engine() {
        const ws = this.getActiveWorkspace();
        return ws ? ws.engine : null;
    }

    bindEvents() {
        // Toolbar
        document.querySelectorAll('.tool-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.tool-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.currentTool = btn.dataset.tool;

                // Toggle transform handles in the engine
                const ws = this.getActiveWorkspace();
                if (ws) {
                    ws.engine.showTransformHandles = (this.currentTool === 'transform');
                    ws.engine.render();
                }
            });
        });

        // Layer actions
        document.getElementById('add-layer-btn').addEventListener('click', () => {
            const ws = this.getActiveWorkspace();
            ws.engine.addLayer(`Layer ${ws.engine.layers.length + 1}`);
            this.updateLayerStack();
        });

        // Add workspace button
        document.getElementById('add-workspace-btn').addEventListener('click', () => {
            this.addWorkspace(`Untitled-${this.workspaces.length + 1}`);
        });

        // Canvas mouse events
        const canvas = document.getElementById('main-canvas');
        let isDrawing = false;
        let isTransforming = false;
        let transformMode = null; // 'move' or 'resize-br' etc.
        let startX, startY;
        let startLayerX, startLayerY;
        let startWidth, startHeight;

        canvas.addEventListener('mousedown', (e) => {
            const rect = canvas.getBoundingClientRect();
            const ws = this.getActiveWorkspace();
            const x = (e.clientX - rect.left) * (ws.engine.width / rect.width);
            const y = (e.clientY - rect.top) * (ws.engine.height / rect.height);

            if (this.currentTool === 'brush' || this.currentTool === 'eraser') {
                isDrawing = true;
                this.handleDraw(e);
            } else if (this.currentTool === 'transform') {
                const layer = ws.engine.getActiveLayer();
                if (!layer) return;

                const lx = layer.x;
                const ly = layer.y;
                const lw = layer.displayWidth;
                const lh = layer.displayHeight;
                const handleSize = 15; // Hit area for handles

                const handles = [
                    { name: 'nw', x: lx, y: ly },
                    { name: 'n', x: lx + lw/2, y: ly },
                    { name: 'ne', x: lx + lw, y: ly },
                    { name: 'w', x: lx, y: ly + lh/2 },
                    { name: 'e', x: lx + lw, y: ly + lh/2 },
                    { name: 'sw', x: lx, y: ly + lh },
                    { name: 's', x: lx + lw/2, y: ly + lh },
                    { name: 'se', x: lx + lw, y: ly + lh }
                ];

                let hitHandle = null;
                for (const h of handles) {
                    if (x >= h.x - handleSize && x <= h.x + handleSize &&
                        y >= h.y - handleSize && y <= h.y + handleSize) {
                        hitHandle = h.name;
                        break;
                    }
                }

                if (hitHandle) {
                    isTransforming = true;
                    transformMode = hitHandle;
                } else if (x >= lx && x <= lx + lw && y >= ly && y <= ly + lh) {
                    isTransforming = true;
                    transformMode = 'move';
                }

                if (isTransforming) {
                    startX = x;
                    startY = y;
                    startLayerX = lx;
                    startLayerY = ly;
                    startWidth = lw;
                    startHeight = lh;
                }
            }
        });

        canvas.addEventListener('mousemove', (e) => {
            const rect = canvas.getBoundingClientRect();
            const ws = this.getActiveWorkspace();
            const x = (e.clientX - rect.left) * (ws.engine.width / rect.width);
            const y = (e.clientY - rect.top) * (ws.engine.height / rect.height);

            if (isDrawing) {
                this.handleDraw(e);
            } else if (isTransforming) {
                const layer = ws.engine.getActiveLayer();
                const dx = x - startX;
                const dy = y - startY;
                const ratio = startWidth / startHeight;

                if (transformMode === 'move') {
                    layer.x = startLayerX + dx;
                    layer.y = startLayerY + dy;
                } else {
                    let newX = startLayerX;
                    let newY = startLayerY;
                    let newW = startWidth;
                    let newH = startHeight;

                    // Horizontal logic
                    if (transformMode.includes('w')) {
                        const dw = -dx;
                        newW = Math.max(10, startWidth + dw);
                        newX = startLayerX + (startWidth - newW);
                    } else if (transformMode.includes('e')) {
                        newW = Math.max(10, startWidth + dx);
                    }

                    // Vertical logic
                    if (transformMode.includes('n')) {
                        const dh = -dy;
                        newH = Math.max(10, startHeight + dh);
                        newY = startLayerY + (startHeight - newH);
                    } else if (transformMode.includes('s')) {
                        newH = Math.max(10, startHeight + dy);
                    }

                    // Proportional scaling logic
                    if (e.shiftKey) {
                        // Ratio is width / height
                        if (transformMode.length === 2) { // Corner nw, ne, sw, se
                            // Use width as base
                            newH = newW / ratio;
                            // Re-calculate top corner if needed
                            if (transformMode.includes('n')) {
                                newY = startLayerY + (startHeight - newH);
                            }
                        } else { // Edge n, s, e, w
                            if (transformMode === 'n' || transformMode === 's') {
                                newW = newH * ratio;
                                newX = startLayerX + (startWidth - newW) / 2; // Center horizontally
                            } else {
                                newH = newW / ratio;
                                newY = startLayerY + (startHeight - newH) / 2; // Center vertically
                            }
                        }
                    }

                    layer.x = newX;
                    layer.y = newY;
                    layer.displayWidth = newW;
                    layer.displayHeight = newH;
                }
                ws.engine.render();
            }
            this.updateCoords(e);
        });

        canvas.addEventListener('wheel', (e) => {
            if (e.shiftKey) {
                e.preventDefault();
                const ws = this.getActiveWorkspace();
                if (!ws) return;
                
                const zoomFactor = 1.1;
                if (e.deltaY < 0) {
                    ws.engine.zoom *= zoomFactor;
                } else {
                    ws.engine.zoom /= zoomFactor;
                }
                
                // Clamp zoom
                ws.engine.zoom = Math.max(0.01, Math.min(100, ws.engine.zoom));
                ws.engine.render();
                this.syncZoomDisplay();
                this.syncZoomCSS();
            }
        });

        window.addEventListener('mouseup', () => {
            isDrawing = false;
            isTransforming = false;
            transformMode = null;
        });

        const resetBtn = document.getElementById('reset-filters');
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                const ws = this.getActiveWorkspace();
                const filters = new FilterEngine(ws.engine);
                filters.reset();
                this.syncFilters();
            });
        }

        // Canvas Settings
        document.getElementById('apply-canvas-size').addEventListener('click', () => {
            const ws = this.getActiveWorkspace();
            const w = parseInt(document.getElementById('canvas-width').value);
            const h = parseInt(document.getElementById('canvas-height').value);
            if (w > 0 && h > 0) {
                ws.engine.setDimensions(w, h);
            }
        });
    }

    bindDropdowns() {
        document.querySelectorAll('.dropdown-content button').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const action = e.target.dataset.action;
                this.handleAction(action);
            });
        });
    }

    handleAction(action) {
        const [category, type] = action.split('-');
        switch(category) {
            case 'file': this.handleFileAction(type); break;
            case 'edit': this.handleEditAction(type); break;
            case 'image': this.handleImageAction(type); break;
            case 'layer': this.handleLayerAction(type); break;
            case 'filter': this.handleFilterAction(type); break;
        }
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
                this.addWorkspace(`Untitled-${this.workspaces.length + 1}`);
                break;
            case 'open':
                this.triggerFileOpen('image', false); // false = not import, so new workspace
                break;
            case 'import':
                this.triggerFileOpen('image', true); // true = import into active workspace
                break;
            case 'load':
                this.triggerFileOpen('project');
                break;
            case 'save':
                this.handleSaveProject();
                break;
            case 'export':
                this.handleExport();
                break;
        }
    }

    handleEditAction(subAction) {
        const ws = this.getActiveWorkspace();
        switch(subAction) {
            case 'clear':
                const layer = ws.engine.getActiveLayer();
                if (layer) {
                    layer.clear();
                    ws.engine.render();
                }
                break;
        }
    }

    handleImageAction(subAction) {
        const ws = this.getActiveWorkspace();
        switch(subAction) {
            case 'flip-h': ws.engine.flipHorizontal(); break;
            case 'flip-v': ws.engine.flipVertical(); break;
        }
    }

    handleLayerAction(subAction) {
        const ws = this.getActiveWorkspace();
        switch(subAction) {
            case 'new':
                ws.engine.addLayer(`Layer ${ws.engine.layers.length + 1}`);
                this.updateLayerStack();
                break;
            case 'delete':
                if (ws.engine.layers.length > 1) {
                    ws.engine.removeLayer(ws.engine.activeLayerIndex);
                    this.updateLayerStack();
                }
                break;
        }
    }

    handleFilterAction(subAction) {
        const ws = this.getActiveWorkspace();
        switch(subAction) {
            case 'invert': ws.engine.invertColors(); break;
        }
    }

    triggerFileOpen(type, isImport = false) {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = type === 'project' ? '.aethphoto' : 'image/*';
        input.onchange = (e) => {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = async (event) => {
                if (type === 'project') {
                    const ws = this.getActiveWorkspace();
                    await ws.engine.fromJSON(event.target.result);
                    ws.name = file.name.replace('.aethphoto', '');
                    this.updateTabStrip();
                    this.updateLayerStack();
                    this.syncFilters();
                } else {
                    if (isImport) {
                        const ws = this.getActiveWorkspace();
                        await ws.engine.loadImage(event.target.result, file.name);
                        this.updateLayerStack();
                    } else {
                        // Open as new project with auto-resolution
                        // Create workspace WITHOUT initial layer to avoid duplicates
                        this.addWorkspace(file.name.split('.')[0], false);
                        const ws = this.getActiveWorkspace();
                        await ws.engine.loadImage(event.target.result, "Background", true);
                        this.updateLayerStack();
                        this.syncCanvasSettings();
                        this.syncZoomCSS();
                        ws.engine.render();
                    }
                }
            };
            if (type === 'project') reader.readAsText(file);
            else reader.readAsDataURL(file);
        };
        input.click();
    }

    handleSaveProject() {
        const ws = this.getActiveWorkspace();
        const json = ws.engine.toJSON();
        const blob = new Blob([json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.download = `${ws.name}.aethphoto`;
        link.href = url;
        link.click();
        URL.revokeObjectURL(url);
    }

    handleExport() {
        const ws = this.getActiveWorkspace();
        const dataUrl = ws.engine.exportToPNG();
        const link = document.createElement('a');
        link.download = `${ws.name}.png`;
        link.href = dataUrl;
        link.click();
    }

    updateTabStrip() {
        const strip = document.getElementById('tab-bar');
        // Clear all except the add button
        const addBtn = document.getElementById('add-workspace-btn');
        Array.from(strip.children).forEach(child => {
            if (child !== addBtn) strip.removeChild(child);
        });

        this.workspaces.forEach((ws, idx) => {
            const tab = document.createElement('div');
            tab.className = `workspace-tab ${idx === this.activeWorkspaceIndex ? 'active' : ''}`;
            tab.innerHTML = `
                <span>${ws.name}</span>
                <i class="fa-solid fa-xmark close-tab"></i>
            `;
            tab.onclick = () => this.setActiveWorkspace(idx);
            
            const closeBtn = tab.querySelector('.close-tab');
            closeBtn.onclick = (e) => {
                e.stopPropagation();
                this.closeWorkspace(idx);
            };

            strip.insertBefore(tab, addBtn);
        });
    }

    closeWorkspace(index) {
        if (this.workspaces.length <= 1) return;
        this.workspaces.splice(index, 1);
        if (this.activeWorkspaceIndex >= this.workspaces.length) {
            this.activeWorkspaceIndex = this.workspaces.length - 1;
        }
        this.setActiveWorkspace(this.activeWorkspaceIndex);
    }

    bindFilters() {
        document.querySelectorAll('#filter-controls input[type="range"]').forEach(input => {
            input.addEventListener('input', (e) => {
                const ws = this.getActiveWorkspace();
                if (!ws) return;
                const filter = e.target.dataset.filter;
                const value = parseInt(e.target.value);
                const filters = new FilterEngine(ws.engine);
                filters.setFilter(filter, value);
            });
        });
    }

    syncFilters() {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        const layer = ws.engine.getActiveLayer();
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
        const ws = this.getActiveWorkspace();
        const x = (e.clientX - rect.left) * (ws.engine.width / rect.width);
        const y = (e.clientY - rect.top) * (ws.engine.height / rect.height);
        
        if (this.currentTool === 'brush') {
            ws.engine.drawBrush(x, y, '#7c6ff7', 10);
        } else if (this.currentTool === 'eraser') {
            ws.engine.drawEraser(x, y, 15);
        }
    }

    updateCoords(e) {
        const rect = e.target.getBoundingClientRect();
        const ws = this.getActiveWorkspace();
        const x = Math.round((e.clientX - rect.left) * (ws.engine.width / rect.width));
        const y = Math.round((e.clientY - rect.top) * (ws.engine.height / rect.height));
        document.getElementById('coord-display').textContent = `${x} : ${y} px`;
    }

    updateLayerStack() {
        const stack = document.getElementById('layer-stack');
        stack.innerHTML = '';
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        
        // Reverse for display (top to bottom)
        [...ws.engine.layers].reverse().forEach((layer, revIdx) => {
            const idx = ws.engine.layers.length - 1 - revIdx;
            const li = document.createElement('li');
            li.className = `layer-item ${idx === ws.engine.activeLayerIndex ? 'active' : ''}`;
            li.innerHTML = `
                <div class="layer-thumb"></div>
                <span class="layer-name">${layer.name}</span>
                <i class="fa-solid ${layer.visible ? 'fa-eye' : 'fa-eye-slash'}"></i>
            `;
            li.onclick = () => {
                ws.engine.setActiveLayer(idx);
                this.updateLayerStack();
                this.syncFilters();
            };

            const eye = li.querySelector('.fa-eye, .fa-eye-slash');
            eye.onclick = (e) => {
                e.stopPropagation();
                const isVisible = !layer.visible;
                ws.engine.setLayerVisibility(idx, isVisible);
                this.updateLayerStack();
            };

            stack.appendChild(li);
        });
    }
}

window.addEventListener('load', () => {
    window.photoApp = new AethvionPhoto();
});
