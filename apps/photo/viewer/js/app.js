/**
 * app.js — Main application logic for Aethvion Photo
 */
import { CanvasEngine } from './canvas_engine.js';
import { FilterEngine  } from './filters.js';

// ─────────────────────────────────────────────────────────────────────────────
// Workspace
// ─────────────────────────────────────────────────────────────────────────────

class Workspace {
    constructor(name, engine) {
        this.id      = Math.random().toString(36).substr(2, 9);
        this.name    = name;
        this.engine  = engine;
        this.dirty   = false;   // unsaved changes indicator
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// AethvionPhoto
// ─────────────────────────────────────────────────────────────────────────────

class AethvionPhoto {
    constructor() {
        this.workspaces           = [];
        this.activeWorkspaceIndex = -1;

        // Tool state
        this.currentTool = 'select';
        this.brushSize   = 20;
        this.fgColor     = '#000000';
        this.bgColor     = '#ffffff';

        // Text options
        this.textSize   = 24;
        this.textFont   = 'Inter';
        this.textBold   = false;
        this.textItalic = false;

        // Internal draw state
        this._lastDrawX = 0;
        this._lastDrawY = 0;
        this._histPushed = false;   // pushed for current stroke?

        // Selection drag state
        this._selStart  = null;

        // Crop drag state
        this._cropStart = null;
        this._cropRect  = null;

        // Text overlay state
        this._textClickX = 0;
        this._textClickY = 0;

        this.init();
    }

    init() {
        this.addWorkspace('Untitled-1', true);
        this.bindEvents();
        this.bindDropdowns();
        this.bindFilters();
        this.bindLayerActions();
        this.bindKeyboard();
        this.initColorPicker();
        this.initToolOptionsBar();
    }

    // ─── Toast notification ────────────────────────────────────────

    notify(message, type = 'success') {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const toast = document.createElement('div');
        toast.className = `ae-toast ae-toast-${type}`;
        const icons = { success: 'fa-circle-check', error: 'fa-circle-xmark', info: 'fa-circle-info', warn: 'fa-triangle-exclamation' };
        toast.innerHTML = `<i class="fa-solid ${icons[type] || icons.info}"></i><span>${message}</span>`;
        container.appendChild(toast);
        // Animate in
        requestAnimationFrame(() => toast.classList.add('show'));
        setTimeout(() => {
            toast.classList.remove('show');
            toast.addEventListener('transitionend', () => toast.remove());
        }, 3200);
    }

    // ─── Workspace management ─────────────────────────────────────

    addWorkspace(name, withInitialLayer = true) {
        const engine    = new CanvasEngine('main-canvas');
        engine.onAfterRender = () => {
            this.updateLayerThumbnails();
            this.updateNavigator();
        };
        const workspace = new Workspace(name, engine);
        this.workspaces.push(workspace);
        this.setActiveWorkspace(this.workspaces.length - 1);
        this.updateTabStrip();

        if (withInitialLayer) {
            const bg = engine.addLayer('Background', false);
            bg.ctx.fillStyle = '#ffffff';
            bg.ctx.fillRect(0, 0, bg.canvas.width, bg.canvas.height);
            engine.pushHistory();  // seed undo
        }
        this.updateLayerStack();
    }

    setActiveWorkspace(index) {
        if (index < 0 || index >= this.workspaces.length) return;
        this.activeWorkspaceIndex = index;
        const ws = this.getActiveWorkspace();

        // Re-hook the render callback whenever we switch workspace
        ws.engine.onAfterRender = () => {
            this.updateLayerThumbnails();
            this.updateNavigator();
        };

        this.updateTabStrip();
        this.updateLayerStack();
        this.syncFilters();
        this.syncCanvasSettings();
        this.syncZoomDisplay();
        this.syncZoomCSS();
        ws.engine.setupCanvas();

        document.getElementById('coord-display').textContent = '0 : 0 px';
        this.updateCanvasSizeDisplay();
    }

    getActiveWorkspace() {
        return this.workspaces[this.activeWorkspaceIndex];
    }

    get engine() {
        const ws = this.getActiveWorkspace();
        return ws ? ws.engine : null;
    }

    closeWorkspace(index) {
        if (this.workspaces.length <= 1) return;
        this.workspaces.splice(index, 1);
        if (this.activeWorkspaceIndex >= this.workspaces.length)
            this.activeWorkspaceIndex = this.workspaces.length - 1;
        this.setActiveWorkspace(this.activeWorkspaceIndex);
    }

    // ─── Tab strip ────────────────────────────────────────────────

    updateTabStrip() {
        const strip  = document.getElementById('tab-bar');
        const addBtn = document.getElementById('add-workspace-btn');
        Array.from(strip.children).forEach(c => { if (c !== addBtn) c.remove(); });

        this.workspaces.forEach((ws, idx) => {
            const tab = document.createElement('div');
            tab.className = `workspace-tab ${idx === this.activeWorkspaceIndex ? 'active' : ''}`;
            tab.innerHTML = `<span class="tab-name">${ws.name}${ws.dirty ? ' •' : ''}</span>
                             <i class="fa-solid fa-xmark close-tab"></i>`;
            tab.onclick = () => this.setActiveWorkspace(idx);
            tab.querySelector('.close-tab').onclick = e => { e.stopPropagation(); this.closeWorkspace(idx); };
            strip.insertBefore(tab, addBtn);
        });
    }

    // ─── Canvas / zoom helpers ────────────────────────────────────

    syncCanvasSettings() {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        document.getElementById('canvas-width').value  = ws.engine.width;
        document.getElementById('canvas-height').value = ws.engine.height;
    }

    syncZoomCSS() {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        const canvas    = document.getElementById('main-canvas');
        const container = canvas.parentElement;
        canvas.style.transform = `scale(${ws.engine.zoom})`;
        container.style.width  = (ws.engine.width  * ws.engine.zoom) + 'px';
        container.style.height = (ws.engine.height * ws.engine.zoom) + 'px';
    }

    syncZoomDisplay() {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        document.getElementById('zoom-display').textContent = Math.round(ws.engine.zoom * 100) + '%';
    }

    updateCanvasSizeDisplay() {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        const el = document.getElementById('canvas-size-display');
        if (el) el.textContent = `${ws.engine.width} × ${ws.engine.height}`;
    }

    setZoom(zoom) {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        ws.engine.zoom = Math.max(0.01, Math.min(100, zoom));
        this.syncZoomDisplay();
        this.syncZoomCSS();
    }

    zoomFit() {
        const ws       = this.getActiveWorkspace();
        if (!ws) return;
        const viewport = document.getElementById('editor-viewport');
        const rect     = viewport.getBoundingClientRect();
        const padding  = 120;
        const zoomW    = (rect.width  - padding) / ws.engine.width;
        const zoomH    = (rect.height - padding) / ws.engine.height;
        this.setZoom(Math.min(zoomW, zoomH, 1));
    }

    // ─── Canvas coordinates helper ────────────────────────────────

    _canvasCoords(e) {
        const canvas = document.getElementById('main-canvas');
        const rect   = canvas.getBoundingClientRect();
        const ws     = this.getActiveWorkspace();
        return {
            x: (e.clientX - rect.left)  * (ws.engine.width  / rect.width),
            y: (e.clientY - rect.top)   * (ws.engine.height / rect.height),
            rect,
            scale: rect.width / ws.engine.width     // screen px per canvas px
        };
    }

    // ─── Bind events ──────────────────────────────────────────────

    bindEvents() {
        // Tool palette buttons
        document.querySelectorAll('.tool-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.tool-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const tool = btn.dataset.tool;
                this.setTool(tool);
            });
        });

        // Add / delete layer buttons
        document.getElementById('add-layer-btn').addEventListener('click', () => {
            this.engine.addLayer(`Layer ${this.engine.layers.length + 1}`);
            this.updateLayerStack();
            this.notify('Layer added');
        });

        document.getElementById('del-layer-btn').addEventListener('click', () => {
            const ws = this.getActiveWorkspace();
            if (!ws || ws.engine.layers.length <= 1) { this.notify('Cannot delete last layer', 'warn'); return; }
            ws.engine.removeLayer(ws.engine.activeLayerIndex);
            this.updateLayerStack();
            this.notify('Layer deleted');
        });

        // New workspace
        document.getElementById('add-workspace-btn').addEventListener('click', () => {
            this.addWorkspace(`Untitled-${this.workspaces.length + 1}`);
        });

        // Canvas resize
        document.getElementById('apply-canvas-size').addEventListener('click', () => {
            const ws = this.getActiveWorkspace();
            const w  = parseInt(document.getElementById('canvas-width').value);
            const h  = parseInt(document.getElementById('canvas-height').value);
            if (w > 0 && h > 0) {
                ws.engine.setDimensions(w, h);
                this.syncZoomCSS();
                this.updateCanvasSizeDisplay();
                this.notify(`Canvas resized to ${w}×${h}`);
            }
        });

        // Reset filters
        document.getElementById('reset-filters').addEventListener('click', () => {
            const ws = this.getActiveWorkspace();
            new FilterEngine(ws.engine).reset();
            this.syncFilters();
            this.notify('Filters reset');
        });

        // Export button
        document.getElementById('btn-export').addEventListener('click', () => this.handleExport());

        // Zoom controls
        document.getElementById('zoom-in-btn') .addEventListener('click', () => this.setZoom((this.engine?.zoom || 1) * 1.25));
        document.getElementById('zoom-out-btn').addEventListener('click', () => this.setZoom((this.engine?.zoom || 1) / 1.25));
        document.getElementById('zoom-fit-btn').addEventListener('click', () => this.zoomFit());
        document.getElementById('zoom-100-btn').addEventListener('click', () => this.setZoom(1.0));

        // Canvas mouse events
        const canvas = document.getElementById('main-canvas');
        this._bindCanvasMouse(canvas);

        // Brush cursor div
        const brushCursor = document.getElementById('brush-cursor');
        canvas.addEventListener('mouseleave', () => { if (brushCursor) brushCursor.style.display = 'none'; });
    }

    setTool(tool) {
        this.currentTool = tool;
        const ws = this.getActiveWorkspace();
        if (ws) {
            ws.engine.showTransformHandles = (tool === 'transform');
            ws.engine.render();
        }
        // Cancel active text overlay when switching tools
        this._hideTextOverlay(false);
        // Crop: clear any in-progress crop marker
        if (tool !== 'crop') {
            this._cropRect  = null;
            this._cropStart = null;
        }
        this.updateToolOptionsBar(tool);
        this.updateCursor(tool);
    }

    updateCursor(tool) {
        const canvas = document.getElementById('main-canvas');
        const cursors = {
            brush:       'none',
            eraser:      'none',
            eyedropper:  'crosshair',
            transform:   'default',
            select:      'default',
            zoom:        'zoom-in',
            crop:        'crosshair',
            'rect-select': 'crosshair',
            text:        'text'
        };
        canvas.style.cursor = cursors[tool] || 'default';
    }

    _bindCanvasMouse(canvas) {
        let isDrawing       = false;
        let isTransforming  = false;
        let transformMode   = null;
        let startX, startY, startLX, startLY, startW, startH;

        canvas.addEventListener('mousedown', (e) => {
            const { x, y } = this._canvasCoords(e);
            const ws = this.getActiveWorkspace();

            if (this.currentTool === 'brush' || this.currentTool === 'eraser') {
                isDrawing = true;
                if (!this._histPushed) {
                    ws.engine.pushHistory();
                    this._histPushed = true;
                }
                this._lastDrawX = x;
                this._lastDrawY = y;
                // Draw a dot at start point
                if (this.currentTool === 'brush')
                    ws.engine.drawBrush(x, y, this.fgColor, this.brushSize);
                else
                    ws.engine.drawEraser(x, y, this.brushSize);
                ws.dirty = true;

            } else if (this.currentTool === 'eyedropper') {
                this.handleEyedropper(x, y);

            } else if (this.currentTool === 'zoom') {
                const factor = e.altKey ? (1 / 1.4) : 1.4;
                this.setZoom((ws.engine.zoom || 1) * factor);

            } else if (this.currentTool === 'rect-select') {
                ws.engine.clearSelection();
                this._selStart = { x, y };

            } else if (this.currentTool === 'crop') {
                this._cropStart = { x, y };
                this._cropRect  = null;

            } else if (this.currentTool === 'text') {
                this._textClickX = x;
                this._textClickY = y;
                this._showTextOverlay(e.clientX, e.clientY);
                return;

            } else if (this.currentTool === 'transform') {
                const layer = ws.engine.getActiveLayer();
                if (!layer) return;
                const { x: lx, y: ly } = layer;
                const lw = layer.displayWidth, lh = layer.displayHeight;
                const hs = 15;
                const handles = [
                    { n:'nw', x:lx,       y:ly       }, { n:'n',  x:lx+lw/2, y:ly       },
                    { n:'ne', x:lx+lw,    y:ly       }, { n:'w',  x:lx,       y:ly+lh/2  },
                    { n:'e',  x:lx+lw,    y:ly+lh/2  }, { n:'sw', x:lx,       y:ly+lh    },
                    { n:'s',  x:lx+lw/2,  y:ly+lh    }, { n:'se', x:lx+lw,    y:ly+lh    }
                ];
                let hit = null;
                for (const h of handles) {
                    if (x >= h.x-hs && x <= h.x+hs && y >= h.y-hs && y <= h.y+hs) { hit = h.n; break; }
                }
                if (hit) {
                    isTransforming = true;  transformMode = hit;
                } else if (x >= lx && x <= lx+lw && y >= ly && y <= ly+lh) {
                    isTransforming = true;  transformMode = 'move';
                }
                if (isTransforming) {
                    ws.engine.pushHistory();
                    startX = x;  startY = y;
                    startLX = lx; startLY = ly;
                    startW  = lw; startH  = lh;
                    ws.dirty = true;
                }
            }
        });

        canvas.addEventListener('mousemove', (e) => {
            const { x, y, rect, scale } = this._canvasCoords(e);
            const ws = this.getActiveWorkspace();

            // Brush cursor ring
            this._updateBrushCursor(e, scale);

            if (isDrawing) {
                if (this.currentTool === 'brush')
                    ws.engine.drawBrushLine(this._lastDrawX, this._lastDrawY, x, y, this.fgColor, this.brushSize);
                else
                    ws.engine.drawEraserLine(this._lastDrawX, this._lastDrawY, x, y, this.brushSize);
                this._lastDrawX = x;
                this._lastDrawY = y;

            } else if (isTransforming) {
                const layer = ws.engine.getActiveLayer();
                const dx = x - startX, dy = y - startY;
                const ratio = startW / startH;

                if (transformMode === 'move') {
                    layer.x = startLX + dx;
                    layer.y = startLY + dy;
                } else {
                    let nx = startLX, ny = startLY, nw = startW, nh = startH;
                    if (transformMode.includes('w')) { const dw=-dx; nw=Math.max(10,startW+dw); nx=startLX+(startW-nw); }
                    else if (transformMode.includes('e')) nw = Math.max(10, startW + dx);
                    if (transformMode.includes('n')) { const dh=-dy; nh=Math.max(10,startH+dh); ny=startLY+(startH-nh); }
                    else if (transformMode.includes('s')) nh = Math.max(10, startH + dy);
                    if (e.shiftKey && transformMode.length === 2) {
                        nh = nw / ratio;
                        if (transformMode.includes('n')) ny = startLY + (startH - nh);
                    }
                    layer.x = nx;  layer.y = ny;
                    layer.displayWidth = nw;  layer.displayHeight = nh;
                }
                ws.engine.render();

            } else if (this._selStart && this.currentTool === 'rect-select') {
                const sx = this._selStart.x, sy = this._selStart.y;
                ws.engine.setSelection(sx, sy, x - sx, y - sy);

            } else if (this._cropStart && this.currentTool === 'crop') {
                this._cropRect = {
                    x: Math.min(x, this._cropStart.x),
                    y: Math.min(y, this._cropStart.y),
                    w: Math.abs(x - this._cropStart.x),
                    h: Math.abs(y - this._cropStart.y)
                };
                // Show crop region as selection visually
                ws.engine.setSelection(this._cropRect.x, this._cropRect.y, this._cropRect.w, this._cropRect.h);
            }

            this.updateCoords(e);
        });

        canvas.addEventListener('mouseup', () => {
            if (isDrawing)      { isDrawing = false;  this._histPushed = false; }
            if (isTransforming) { isTransforming = false; transformMode = null; }
            if (this._selStart) this._selStart = null;
            if (this._cropStart && this.currentTool === 'crop' && this._cropRect) {
                this._cropStart = null;
                // Crop rect stays visible — user presses Enter or clicks Crop button to confirm
                this._showCropConfirm();
            }
        });

        canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const ws = this.getActiveWorkspace();
            if (!ws) return;
            const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
            this.setZoom(ws.engine.zoom * factor);
        }, { passive: false });
    }

    _updateBrushCursor(e, scale) {
        const cursor = document.getElementById('brush-cursor');
        if (!cursor) return;
        const active = this.currentTool === 'brush' || this.currentTool === 'eraser';
        if (!active) { cursor.style.display = 'none'; return; }
        const d = Math.max(2, this.brushSize * 2 * scale);
        cursor.style.display = 'block';
        cursor.style.width   = d + 'px';
        cursor.style.height  = d + 'px';
        cursor.style.left    = e.clientX + 'px';
        cursor.style.top     = e.clientY + 'px';
    }

    _showCropConfirm() {
        // Show a small "Commit Crop" button overlay near the crop region
        let btn = document.getElementById('crop-confirm-btn');
        if (!btn) {
            btn = document.createElement('button');
            btn.id = 'crop-confirm-btn';
            btn.className = 'btn-primary crop-confirm-overlay';
            btn.innerHTML = '<i class="fa-solid fa-crop-simple"></i> Crop (Enter)';
            btn.addEventListener('click', () => this._commitCrop());
            document.getElementById('editor-viewport').appendChild(btn);
        }
        btn.style.display = 'block';
    }

    _commitCrop() {
        if (!this._cropRect) return;
        const ws = this.getActiveWorkspace();
        ws.engine.cropToSelection();
        this._cropRect = null;
        const btn = document.getElementById('crop-confirm-btn');
        if (btn) btn.style.display = 'none';
        this.syncCanvasSettings();
        this.syncZoomCSS();
        this.updateCanvasSizeDisplay();
        this.notify('Canvas cropped');
    }

    // ─── Text overlay ─────────────────────────────────────────────

    _showTextOverlay(clientX, clientY) {
        const overlay = document.getElementById('text-overlay');
        const input   = document.getElementById('text-input');
        if (!overlay || !input) return;

        const zoom = this.engine?.zoom || 1;
        overlay.style.left    = clientX + 'px';
        overlay.style.top     = clientY + 'px';
        overlay.style.display = 'block';
        input.style.fontSize  = `${this.textSize * zoom}px`;
        input.style.fontFamily = `"${this.textFont}", sans-serif`;
        input.style.fontWeight  = this.textBold   ? 'bold'   : 'normal';
        input.style.fontStyle   = this.textItalic ? 'italic' : 'normal';
        input.value = '';
        setTimeout(() => input.focus(), 50);

        // Auto-resize height as user types
        input.oninput = () => {
            input.style.height = 'auto';
            input.style.height = input.scrollHeight + 'px';
        };
    }

    _hideTextOverlay(commit = true) {
        const overlay = document.getElementById('text-overlay');
        const input   = document.getElementById('text-input');
        if (!overlay || !input) return;
        if (commit && input.value.trim()) {
            this.engine.addTextLayer(input.value, {
                x:      this._textClickX,
                y:      this._textClickY,
                size:   this.textSize,
                font:   this.textFont,
                color:  this.fgColor,
                bold:   this.textBold,
                italic: this.textItalic
            });
            this.updateLayerStack();
            this.notify('Text layer added');
        }
        overlay.style.display = 'none';
        input.value = '';
    }

    // ─── Keyboard shortcuts ───────────────────────────────────────

    bindKeyboard() {
        document.addEventListener('keydown', (e) => {
            const tag = document.activeElement?.tagName?.toUpperCase();
            // Allow typing in inputs/textareas
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
                // Text overlay: Ctrl+Enter to commit, Escape to cancel
                if (tag === 'TEXTAREA' && document.activeElement.id === 'text-input') {
                    if (e.key === 'Escape') { e.preventDefault(); this._hideTextOverlay(false); }
                    if (e.key === 'Enter' && e.ctrlKey) { e.preventDefault(); this._hideTextOverlay(true); }
                }
                return;
            }

            const ws = this.getActiveWorkspace();

            // Tool shortcuts
            const toolKeys = { v:'select', b:'brush', e:'eraser', t:'text', c:'crop', i:'eyedropper', z:'zoom', m:'rect-select' };
            if (!e.ctrlKey && !e.metaKey && toolKeys[e.key.toLowerCase()]) {
                e.preventDefault();
                const tool = toolKeys[e.key.toLowerCase()];
                document.querySelectorAll('.tool-btn').forEach(b => b.classList.remove('active'));
                document.querySelector(`.tool-btn[data-tool="${tool}"]`)?.classList.add('active');
                this.setTool(tool);
                return;
            }

            // Brush size  [ / ]
            if (e.key === '[') { e.preventDefault(); this.brushSize = Math.max(1, this.brushSize - 5); this._syncBrushSizeUI(); }
            if (e.key === ']') { e.preventDefault(); this.brushSize = Math.min(500, this.brushSize + 5); this._syncBrushSizeUI(); }

            // X = swap colours
            if (e.key === 'x' || e.key === 'X') { e.preventDefault(); this.swapColors(); }

            // Ctrl shortcuts
            if (e.ctrlKey || e.metaKey) {
                switch (e.key.toLowerCase()) {
                    case 'z':
                        e.preventDefault();
                        if (e.shiftKey) {
                            if (ws) ws.engine.redo();
                        } else {
                            if (ws) ws.engine.undo();
                        }
                        this.updateLayerStack();
                        this.syncFilters();
                        this.syncCanvasSettings();
                        this.updateCanvasSizeDisplay();
                        this.syncZoomCSS();
                        break;
                    case 'y':
                        e.preventDefault();
                        if (ws) ws.engine.redo();
                        this.updateLayerStack();
                        this.syncFilters();
                        break;
                    case 's':
                        e.preventDefault();
                        this.handleSaveProject();
                        break;
                    case 'd':
                        e.preventDefault();
                        if (ws) { ws.engine.clearSelection(); this.updateLayerStack(); }
                        break;
                    case 'c':
                        e.preventDefault();
                        if (ws) ws.engine.copySelection();
                        break;
                    case 'v':
                        e.preventDefault();
                        if (ws) { ws.engine.pasteAsLayer(); this.updateLayerStack(); this.notify('Pasted as new layer'); }
                        break;
                    case 'j':
                        // Duplicate active layer
                        e.preventDefault();
                        if (ws) {
                            ws.engine.duplicateLayer(ws.engine.activeLayerIndex);
                            this.updateLayerStack();
                            this.notify('Layer duplicated');
                        }
                        break;
                }
            }

            // Delete key: clear selection or clear layer
            if (e.key === 'Delete' || e.key === 'Backspace') {
                if (!ws) return;
                if (ws.engine.selection) { ws.engine.deleteSelection(); }
                else {
                    const ly = ws.engine.getActiveLayer();
                    if (ly) { ws.engine.pushHistory(); ly.clear(); ws.engine.render(); }
                }
            }

            // Enter key: commit crop
            if (e.key === 'Enter' && this.currentTool === 'crop' && this._cropRect) {
                e.preventDefault();
                this._commitCrop();
            }

            // Escape: cancel selection / crop
            if (e.key === 'Escape') {
                this._cropRect  = null;
                this._selStart  = null;
                if (ws) ws.engine.clearSelection();
                const btn = document.getElementById('crop-confirm-btn');
                if (btn) btn.style.display = 'none';
            }

            // Zoom with + and -
            if (e.key === '+' || e.key === '=') { e.preventDefault(); this.setZoom((this.engine?.zoom || 1) * 1.2); }
            if (e.key === '-' || e.key === '_') { e.preventDefault(); this.setZoom((this.engine?.zoom || 1) / 1.2); }
        });
    }

    // ─── Tool options bar ─────────────────────────────────────────

    initToolOptionsBar() {
        // Brush size slider
        const slider = document.getElementById('brush-size-slider');
        const num    = document.getElementById('brush-size-num');
        if (slider) {
            slider.value = this.brushSize;
            slider.addEventListener('input', () => {
                this.brushSize = parseInt(slider.value);
                if (num) num.value = this.brushSize;
            });
        }
        if (num) {
            num.value = this.brushSize;
            num.addEventListener('input', () => {
                this.brushSize = Math.max(1, Math.min(500, parseInt(num.value) || 1));
                if (slider) slider.value = this.brushSize;
            });
        }

        // Text options
        const textFont = document.getElementById('text-font');
        const textSize = document.getElementById('text-size-opt');
        const boldBtn  = document.getElementById('text-bold');
        const italBtn  = document.getElementById('text-italic');

        if (textFont) textFont.addEventListener('change', () => { this.textFont = textFont.value; });
        if (textSize) textSize.addEventListener('input', () => { this.textSize = parseInt(textSize.value) || 24; });
        if (boldBtn)  boldBtn .addEventListener('click',  () => { this.textBold   = !this.textBold;   boldBtn.classList.toggle('active', this.textBold); });
        if (italBtn)  italBtn .addEventListener('click',  () => { this.textItalic = !this.textItalic; italBtn.classList.toggle('active', this.textItalic); });

        this.updateToolOptionsBar(this.currentTool);
    }

    updateToolOptionsBar(tool) {
        document.querySelectorAll('.tool-opt-group').forEach(g => g.style.display = 'none');
        const map = {
            brush:          'tool-opts-brush',
            eraser:         'tool-opts-eraser',
            text:           'tool-opts-text',
            zoom:           'tool-opts-zoom',
            'rect-select':  'tool-opts-select',
            crop:           'tool-opts-crop'
        };
        if (map[tool]) {
            const el = document.getElementById(map[tool]);
            if (el) el.style.display = 'flex';
        }
    }

    _syncBrushSizeUI() {
        const slider = document.getElementById('brush-size-slider');
        const num    = document.getElementById('brush-size-num');
        if (slider) slider.value = this.brushSize;
        if (num)    num.value    = this.brushSize;
    }

    // ─── Color picker ─────────────────────────────────────────────

    initColorPicker() {
        const fgPreview = document.getElementById('color-preview');
        const fgInput   = document.getElementById('active-color');
        const bgPreview = document.getElementById('bg-color-preview');
        const bgInput   = document.getElementById('bg-color-input');
        const swapBtn   = document.getElementById('color-swap');

        if (fgPreview) fgPreview.style.backgroundColor = this.fgColor;
        if (bgPreview) bgPreview.style.backgroundColor = this.bgColor;

        if (fgPreview) fgPreview.addEventListener('click', () => fgInput.click());
        if (fgInput)   fgInput.addEventListener('input', e => {
            this.fgColor = e.target.value;
            if (fgPreview) fgPreview.style.backgroundColor = this.fgColor;
        });

        if (bgPreview) bgPreview.addEventListener('click', () => bgInput.click());
        if (bgInput)   bgInput.addEventListener('input', e => {
            this.bgColor = e.target.value;
            if (bgPreview) bgPreview.style.backgroundColor = this.bgColor;
        });

        if (swapBtn) swapBtn.addEventListener('click', () => this.swapColors());
    }

    swapColors() {
        [this.fgColor, this.bgColor] = [this.bgColor, this.fgColor];
        const fgPreview = document.getElementById('color-preview');
        const fgInput   = document.getElementById('active-color');
        const bgPreview = document.getElementById('bg-color-preview');
        const bgInput   = document.getElementById('bg-color-input');
        if (fgPreview) fgPreview.style.backgroundColor = this.fgColor;
        if (fgInput)   fgInput.value   = this.fgColor;
        if (bgPreview) bgPreview.style.backgroundColor = this.bgColor;
        if (bgInput)   bgInput.value   = this.bgColor;
    }

    // ─── Eyedropper ───────────────────────────────────────────────

    handleEyedropper(x, y) {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        const pixel = ws.engine.mainCtx.getImageData(
            Math.round(x), Math.round(y), 1, 1
        ).data;
        const hex = '#' + [pixel[0], pixel[1], pixel[2]].map(v =>
            v.toString(16).padStart(2, '0')).join('');
        this.fgColor = hex;
        const fgPreview = document.getElementById('color-preview');
        const fgInput   = document.getElementById('active-color');
        if (fgPreview) fgPreview.style.backgroundColor = hex;
        if (fgInput)   fgInput.value = hex;
    }

    // ─── Coordinate display ───────────────────────────────────────

    updateCoords(e) {
        const { x, y } = this._canvasCoords(e);
        document.getElementById('coord-display').textContent = `${Math.round(x)} : ${Math.round(y)} px`;
    }

    // ─── Menu dropdowns ───────────────────────────────────────────

    bindDropdowns() {
        document.querySelectorAll('.dropdown-content button').forEach(btn => {
            btn.addEventListener('click', e => {
                this.handleAction(e.target.closest('button').dataset.action);
            });
        });
    }

    handleAction(action) {
        if (!action) return;
        const [cat, ...rest] = action.split('-');
        const sub = rest.join('-');
        switch (cat) {
            case 'file':   this.handleFileAction(sub);   break;
            case 'edit':   this.handleEditAction(sub);   break;
            case 'image':  this.handleImageAction(sub);  break;
            case 'layer':  this.handleLayerAction(sub);  break;
            case 'filter': this.handleFilterAction(sub); break;
        }
    }

    async handleFileAction(sub) {
        switch (sub) {
            case 'new':         this.addWorkspace(`Untitled-${this.workspaces.length + 1}`); break;
            case 'open':        this.triggerFileOpen('image', false); break;
            case 'import':      this.triggerFileOpen('image', true);  break;
            case 'load':        this.triggerFileOpen('project');       break;
            case 'load-server': this.openProjectModal();               break;
            case 'save':        this.handleSaveProject();              break;
            case 'export':      this.handleExport();                   break;
        }
    }

    handleEditAction(sub) {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        switch (sub) {
            case 'undo': ws.engine.undo(); this.updateLayerStack(); this.syncFilters(); break;
            case 'redo': ws.engine.redo(); this.updateLayerStack(); this.syncFilters(); break;
            case 'copy':  ws.engine.copySelection(); this.notify('Copied'); break;
            case 'paste': ws.engine.pasteAsLayer();  this.updateLayerStack(); this.notify('Pasted'); break;
            case 'clear': {
                const l = ws.engine.getActiveLayer();
                if (l) { ws.engine.pushHistory(); l.clear(); ws.engine.render(); this.notify('Layer cleared'); }
                break;
            }
            case 'select-all':
                ws.engine.setSelection(0, 0, ws.engine.width, ws.engine.height);
                break;
            case 'deselect':
                ws.engine.clearSelection();
                break;
            case 'fill-fg': ws.engine.fillSelection(this.fgColor); this.notify('Filled with foreground'); break;
            case 'fill-bg': ws.engine.fillSelection(this.bgColor); this.notify('Filled with background'); break;
        }
    }

    handleImageAction(sub) {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        switch (sub) {
            case 'flip-h':    ws.engine.flipHorizontal(); break;
            case 'flip-v':    ws.engine.flipVertical();   break;
            case 'rotate-90': ws.engine.rotate90CW(); this.syncCanvasSettings(); this.updateCanvasSizeDisplay(); this.syncZoomCSS(); break;
            case 'desaturate': ws.engine.desaturate(); break;
        }
    }

    handleLayerAction(sub) {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        switch (sub) {
            case 'new':
                ws.engine.addLayer(`Layer ${ws.engine.layers.length + 1}`);
                this.updateLayerStack();
                this.notify('Layer added');
                break;
            case 'duplicate':
                ws.engine.duplicateLayer(ws.engine.activeLayerIndex);
                this.updateLayerStack();
                this.notify('Layer duplicated');
                break;
            case 'delete':
                if (ws.engine.layers.length <= 1) { this.notify('Cannot delete last layer', 'warn'); return; }
                ws.engine.removeLayer(ws.engine.activeLayerIndex);
                this.updateLayerStack();
                this.notify('Layer deleted');
                break;
            case 'merge':
                ws.engine.mergeDown(ws.engine.activeLayerIndex);
                this.updateLayerStack();
                this.notify('Merged down');
                break;
            case 'flatten':
                ws.engine.flatten();
                this.updateLayerStack();
                this.notify('Image flattened');
                break;
        }
    }

    handleFilterAction(sub) {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        switch (sub) {
            case 'invert':     ws.engine.invertColors(); break;
            case 'desaturate': ws.engine.desaturate();   break;
            case 'grayscale':  ws.engine.desaturate();   break;
        }
    }

    // ─── File operations ──────────────────────────────────────────

    triggerFileOpen(type, isImport = false) {
        const input  = document.createElement('input');
        input.type   = 'file';
        input.accept = type === 'project' ? '.aethphoto' : 'image/*';
        input.onchange = async e => {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = async ev => {
                if (type === 'project') {
                    const ws = this.getActiveWorkspace();
                    await ws.engine.fromJSON(ev.target.result);
                    ws.name = file.name.replace('.aethphoto', '');
                    this.updateTabStrip();
                    this.updateLayerStack();
                    this.syncFilters();
                    this.syncCanvasSettings();
                    this.syncZoomCSS();
                    this.updateCanvasSizeDisplay();
                    this.notify(`Loaded: ${ws.name}`);
                } else if (isImport) {
                    const ws = this.getActiveWorkspace();
                    await ws.engine.loadImage(ev.target.result, file.name);
                    ws.engine.pushHistory();
                    this.updateLayerStack();
                    this.notify(`Imported: ${file.name}`);
                } else {
                    this.addWorkspace(file.name.split('.')[0], false);
                    const ws = this.getActiveWorkspace();
                    await ws.engine.loadImage(ev.target.result, 'Background', true);
                    ws.engine.pushHistory();
                    this.updateLayerStack();
                    this.syncCanvasSettings();
                    this.syncZoomCSS();
                    ws.engine.render();
                    this.notify(`Opened: ${file.name}`);
                }
            };
            if (type === 'project') reader.readAsText(file);
            else reader.readAsDataURL(file);
        };
        input.click();
    }

    async handleSaveProject() {
        const ws   = this.getActiveWorkspace();
        const json = ws.engine.toJSON();
        try {
            const resp   = await fetch('/api/save-project', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: ws.name, data: json })
            });
            const result = await resp.json();
            if (result.success) {
                ws.dirty = false;
                this.updateTabStrip();
                this.notify(`Saved: ${result.filename}`);
            } else throw new Error(result.error || 'Failed to save');
        } catch (err) {
            // Fallback: local download
            const blob = new Blob([json], { type: 'application/json' });
            const url  = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.download = `${ws.name}.aethphoto`;
            link.href = url;
            link.click();
            URL.revokeObjectURL(url);
            this.notify('Saved locally (server unavailable)', 'info');
        }
    }

    async openProjectModal() {
        const modal = document.getElementById('project-modal');
        const list  = document.getElementById('project-list-container');
        if (!modal || !list) return;
        list.innerHTML = '<div class="modal-loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading…</div>';
        modal.style.display = 'flex';

        try {
            const resp = await fetch('/api/projects');
            const data = await resp.json();
            if (!data.projects || !data.projects.length) {
                list.innerHTML = '<p class="modal-empty">No saved projects found.</p>';
                return;
            }
            list.innerHTML = '';
            data.projects.forEach(p => {
                const row = document.createElement('button');
                row.className = 'project-row';
                row.innerHTML = `<i class="fa-regular fa-file-image"></i> <span>${p.name}</span>`;
                row.addEventListener('click', async () => {
                    modal.style.display = 'none';
                    const loadResp = await fetch(`/api/load-project/${p.filename}`);
                    const loadData = await loadResp.json();
                    if (loadData.data) {
                        const ws = this.getActiveWorkspace();
                        await ws.engine.fromJSON(loadData.data);
                        ws.name = p.name;
                        this.updateTabStrip();
                        this.updateLayerStack();
                        this.syncFilters();
                        this.syncCanvasSettings();
                        this.syncZoomCSS();
                        this.updateCanvasSizeDisplay();
                        this.notify(`Loaded: ${p.name}`);
                    }
                });
                list.appendChild(row);
            });
        } catch {
            list.innerHTML = '<p class="modal-empty modal-error">Could not connect to server.</p>';
        }
    }

    handleExport() {
        const ws   = this.getActiveWorkspace();
        const url  = ws.engine.exportToPNG();
        const link = document.createElement('a');
        link.download = `${ws.name}.png`;
        link.href = url;
        link.click();
        this.notify(`Exported: ${ws.name}.png`);
    }

    // ─── Filters ──────────────────────────────────────────────────

    bindFilters() {
        let filterDragPushed = false;
        document.querySelectorAll('#filter-controls input[type="range"]').forEach(input => {
            input.addEventListener('mousedown', () => {
                if (!filterDragPushed) {
                    this.engine?.pushHistory();
                    filterDragPushed = true;
                }
            });
            input.addEventListener('mouseup', () => { filterDragPushed = false; });
            input.addEventListener('input', e => {
                const ws = this.getActiveWorkspace();
                if (!ws) return;
                new FilterEngine(ws.engine).setFilter(e.target.dataset.filter, parseInt(e.target.value));
                // Show live value beside label
                const label = e.target.closest('.control-group')?.querySelector('.filter-val');
                if (label) label.textContent = e.target.value;
            });
        });
    }

    syncFilters() {
        const ws    = this.getActiveWorkspace();
        if (!ws) return;
        const layer = ws.engine.getActiveLayer();
        if (!layer) return;
        document.querySelectorAll('#filter-controls input[type="range"]').forEach(input => {
            const f = input.dataset.filter;
            if (Object.prototype.hasOwnProperty.call(layer.filters, f)) {
                input.value = layer.filters[f];
                const label = input.closest('.control-group')?.querySelector('.filter-val');
                if (label) label.textContent = layer.filters[f];
            }
        });
    }

    // ─── Layer stack UI ───────────────────────────────────────────

    bindLayerActions() {
        const blendSel  = document.getElementById('layer-blend-mode');
        const opacInput = document.getElementById('layer-opacity-input');
        const dupBtn    = document.getElementById('duplicate-layer-btn');
        const mergeBtn  = document.getElementById('merge-down-btn');
        const flatBtn   = document.getElementById('flatten-btn');

        if (blendSel) {
            blendSel.addEventListener('change', () => {
                const ws = this.getActiveWorkspace();
                if (!ws) return;
                ws.engine.pushHistory();
                ws.engine.setLayerBlendMode(ws.engine.activeLayerIndex, blendSel.value);
            });
        }
        if (opacInput) {
            opacInput.addEventListener('input', () => {
                const ws = this.getActiveWorkspace();
                if (!ws) return;
                ws.engine.setLayerOpacity(ws.engine.activeLayerIndex, parseInt(opacInput.value) / 100);
            });
        }
        if (dupBtn)   dupBtn  .addEventListener('click', () => this.handleLayerAction('duplicate'));
        if (mergeBtn) mergeBtn.addEventListener('click', () => this.handleLayerAction('merge'));
        if (flatBtn)  flatBtn .addEventListener('click', () => this.handleLayerAction('flatten'));
    }

    updateLayerStack() {
        const stack = document.getElementById('layer-stack');
        stack.innerHTML = '';
        const ws = this.getActiveWorkspace();
        if (!ws) return;

        // Update blend mode / opacity controls
        const layer = ws.engine.getActiveLayer();
        const blendSel  = document.getElementById('layer-blend-mode');
        const opacInput = document.getElementById('layer-opacity-input');
        if (blendSel  && layer) blendSel.value  = layer.blendMode;
        if (opacInput && layer) opacInput.value  = Math.round(layer.opacity * 100);

        // Render layers in reverse (top of stack first)
        [...ws.engine.layers].reverse().forEach((layer, revIdx) => {
            const idx = ws.engine.layers.length - 1 - revIdx;
            const li  = document.createElement('li');
            li.className   = `layer-item ${idx === ws.engine.activeLayerIndex ? 'active' : ''}`;
            li.draggable   = true;
            li.dataset.idx = idx;

            li.innerHTML = `
                <i class="fa-solid fa-grip-vertical layer-drag-handle"></i>
                <canvas class="layer-thumb" width="36" height="36"></canvas>
                <span class="layer-name" title="${layer.name}">${layer.name}</span>
                <span class="layer-opacity-badge">${Math.round(layer.opacity * 100)}%</span>
                <i class="fa-solid ${layer.visible ? 'fa-eye' : 'fa-eye-slash'} layer-vis" title="Toggle visibility"></i>
                ${layer.locked ? '<i class="fa-solid fa-lock layer-lock-icon" title="Locked"></i>' : ''}
            `;

            // Click to select
            li.addEventListener('click', () => {
                ws.engine.setActiveLayer(idx);
                this.updateLayerStack();
                this.syncFilters();
            });

            // Visibility toggle
            li.querySelector('.layer-vis').addEventListener('click', e => {
                e.stopPropagation();
                ws.engine.setLayerVisibility(idx, !layer.visible);
                this.updateLayerStack();
            });

            // Drag reorder
            li.addEventListener('dragstart', e => {
                e.dataTransfer.setData('text/plain', idx);
                li.classList.add('dragging');
            });
            li.addEventListener('dragend', () => li.classList.remove('dragging'));
            li.addEventListener('dragover', e => { e.preventDefault(); li.classList.add('drag-over'); });
            li.addEventListener('dragleave', () => li.classList.remove('drag-over'));
            li.addEventListener('drop', e => {
                e.preventDefault();
                li.classList.remove('drag-over');
                const fromIdx = parseInt(e.dataTransfer.getData('text/plain'));
                const toIdx   = parseInt(li.dataset.idx);
                if (fromIdx === toIdx) return;
                // Move layer from fromIdx towards toIdx one step at a time
                let cur = fromIdx;
                if (fromIdx < toIdx) {
                    while (cur < toIdx) { ws.engine.moveLayerUp(cur); cur++; }
                } else {
                    while (cur > toIdx) { ws.engine.moveLayerDown(cur); cur--; }
                }
                this.updateLayerStack();
                this.syncFilters();
            });

            stack.appendChild(li);
        });

        // Populate layer thumbnails after DOM is settled
        requestAnimationFrame(() => this.updateLayerThumbnails());
    }

    updateLayerThumbnails() {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        document.querySelectorAll('.layer-item').forEach(li => {
            const idx   = parseInt(li.dataset.idx);
            const layer = ws.engine.layers[idx];
            const thumb = li.querySelector('.layer-thumb');
            if (!layer || !thumb) return;
            const ctx = thumb.getContext('2d');
            ctx.clearRect(0, 0, 36, 36);
            if (layer.canvas.width > 0 && layer.canvas.height > 0) {
                ctx.drawImage(layer.canvas, 0, 0, layer.canvas.width, layer.canvas.height, 0, 0, 36, 36);
            }
        });
    }

    // ─── Navigator minimap ────────────────────────────────────────

    updateNavigator() {
        const navCanvas = document.getElementById('nav-canvas');
        if (!navCanvas) return;
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        const ctx = navCanvas.getContext('2d');
        ctx.clearRect(0, 0, navCanvas.width, navCanvas.height);
        ctx.drawImage(ws.engine.mainCanvas, 0, 0, navCanvas.width, navCanvas.height);
    }

    // ─── Sync helpers ─────────────────────────────────────────────

    syncCanvasSettings() {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        document.getElementById('canvas-width').value  = ws.engine.width;
        document.getElementById('canvas-height').value = ws.engine.height;
    }

    syncZoomCSS() {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        const canvas    = document.getElementById('main-canvas');
        const container = canvas.parentElement;
        canvas.style.transform = `scale(${ws.engine.zoom})`;
        container.style.width  = (ws.engine.width  * ws.engine.zoom) + 'px';
        container.style.height = (ws.engine.height * ws.engine.zoom) + 'px';
    }

    syncZoomDisplay() {
        const ws = this.getActiveWorkspace();
        if (!ws) return;
        document.getElementById('zoom-display').textContent = Math.round(ws.engine.zoom * 100) + '%';
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Bootstrap
// ─────────────────────────────────────────────────────────────────────────────

window.addEventListener('load', () => {
    window.photoApp = new AethvionPhoto();
});
