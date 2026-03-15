/**
 * canvas_engine.js — Core rendering and layer management for Aethvion Photo
 */

export class Layer {
    constructor(name, width, height) {
        this.id = Math.random().toString(36).substr(2, 9);
        this.name = name;
        this.visible = true;
        this.locked = false;
        this.opacity = 1.0;
        this.blendMode = 'normal';
        this.x = 0;
        this.y = 0;
        this.displayWidth = width;
        this.displayHeight = height;
        this.filters = {
            brightness: 100,
            contrast: 100,
            saturate: 100,
            blur: 0,
            grayscale: 0,
            sepia: 0
        };
        this.canvas = document.createElement('canvas');
        this.canvas.width = width;
        this.canvas.height = height;
        this.ctx = this.canvas.getContext('2d');
    }

    clear() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }

    getFilterString() {
        const f = this.filters;
        let str = '';
        if (f.brightness !== 100) str += `brightness(${f.brightness}%) `;
        if (f.contrast   !== 100) str += `contrast(${f.contrast}%) `;
        if (f.saturate   !== 100) str += `saturate(${f.saturate}%) `;
        if (f.blur       !== 0)   str += `blur(${f.blur}px) `;
        if (f.grayscale  !== 0)   str += `grayscale(${f.grayscale}%) `;
        if (f.sepia      !== 0)   str += `sepia(${f.sepia}%) `;
        return str || 'none';
    }
}

export class CanvasEngine {
    constructor(canvasId) {
        this.mainCanvas = document.getElementById(canvasId);
        this.mainCtx    = this.mainCanvas.getContext('2d');

        this.width  = 1920;
        this.height = 1080;
        this.layers = [];
        this.activeLayerIndex    = -1;
        this.zoom                = 1.0;
        this.showTransformHandles = false;

        // Selection state  {x, y, w, h}  — canvas pixel coordinates
        this.selection = null;

        // Undo / Redo
        this._undoStack   = [];
        this._undoPointer = -1;

        // Clipboard (internal)
        this._clipboard = null;

        // Optional post-render callback (set by app.js)
        this.onAfterRender = null;

        this.setupCanvas();
    }

    // ─────────────────────────────────────────────────────────────
    // Canvas setup
    // ─────────────────────────────────────────────────────────────

    setupCanvas() {
        this.mainCanvas.width  = this.width;
        this.mainCanvas.height = this.height;
        this.render();
    }

    setDimensions(w, h) {
        this.width  = w;
        this.height = h;
        this.setupCanvas();
    }

    // ─────────────────────────────────────────────────────────────
    // Undo / Redo
    // ─────────────────────────────────────────────────────────────

    pushHistory() {
        // Discard any redo states beyond the current pointer
        this._undoStack.splice(this._undoPointer + 1);

        const snapshot = {
            width:  this.width,
            height: this.height,
            activeLayerIndex: this.activeLayerIndex,
            layers: this.layers.map(layer => ({
                name:          layer.name,
                visible:       layer.visible,
                locked:        layer.locked,
                opacity:       layer.opacity,
                blendMode:     layer.blendMode,
                x:             layer.x,
                y:             layer.y,
                displayWidth:  layer.displayWidth,
                displayHeight: layer.displayHeight,
                filters:       { ...layer.filters },
                canvasW:       layer.canvas.width,
                canvasH:       layer.canvas.height,
                imageData:     layer.ctx.getImageData(0, 0, layer.canvas.width, layer.canvas.height)
            }))
        };

        this._undoStack.push(snapshot);
        // Keep at most 20 states to manage memory
        if (this._undoStack.length > 20) this._undoStack.shift();
        this._undoPointer = this._undoStack.length - 1;
    }

    _applySnapshot(snap) {
        this.width  = snap.width;
        this.height = snap.height;
        this.mainCanvas.width  = this.width;
        this.mainCanvas.height = this.height;

        this.layers = snap.layers.map(ld => {
            const layer = new Layer(ld.name, ld.canvasW, ld.canvasH);
            layer.visible       = ld.visible;
            layer.locked        = ld.locked;
            layer.opacity       = ld.opacity;
            layer.blendMode     = ld.blendMode;
            layer.x             = ld.x;
            layer.y             = ld.y;
            layer.displayWidth  = ld.displayWidth;
            layer.displayHeight = ld.displayHeight;
            layer.filters       = { ...ld.filters };
            layer.ctx.putImageData(ld.imageData, 0, 0);
            return layer;
        });

        this.activeLayerIndex = snap.activeLayerIndex;
        this.selection = null;
        this.render();
    }

    undo() {
        if (this._undoPointer <= 0) return false;
        this._undoPointer--;
        this._applySnapshot(this._undoStack[this._undoPointer]);
        return true;
    }

    redo() {
        if (this._undoPointer >= this._undoStack.length - 1) return false;
        this._undoPointer++;
        this._applySnapshot(this._undoStack[this._undoPointer]);
        return true;
    }

    canUndo() { return this._undoPointer > 0; }
    canRedo() { return this._undoPointer < this._undoStack.length - 1; }

    // ─────────────────────────────────────────────────────────────
    // Layer management
    // ─────────────────────────────────────────────────────────────

    addLayer(name = 'New Layer', pushUndo = true) {
        if (pushUndo) this.pushHistory();
        const layer = new Layer(name, this.width, this.height);
        this.layers.push(layer);
        this.activeLayerIndex = this.layers.length - 1;
        this.render();
        return layer;
    }

    removeLayer(index) {
        if (index < 0 || index >= this.layers.length) return;
        this.pushHistory();
        this.layers.splice(index, 1);
        this.activeLayerIndex = Math.min(this.activeLayerIndex, this.layers.length - 1);
        this.render();
    }

    duplicateLayer(index) {
        if (index < 0 || index >= this.layers.length) return;
        this.pushHistory();
        const src  = this.layers[index];
        const copy = new Layer(src.name + ' copy', src.canvas.width, src.canvas.height);
        copy.visible       = src.visible;
        copy.opacity       = src.opacity;
        copy.blendMode     = src.blendMode;
        copy.x             = src.x;
        copy.y             = src.y;
        copy.displayWidth  = src.displayWidth;
        copy.displayHeight = src.displayHeight;
        copy.filters       = { ...src.filters };
        copy.ctx.drawImage(src.canvas, 0, 0);
        this.layers.splice(index + 1, 0, copy);
        this.activeLayerIndex = index + 1;
        this.render();
        return copy;
    }

    moveLayerUp(index) {
        if (index >= this.layers.length - 1) return;
        this.pushHistory();
        [this.layers[index], this.layers[index + 1]] = [this.layers[index + 1], this.layers[index]];
        if      (this.activeLayerIndex === index)     this.activeLayerIndex = index + 1;
        else if (this.activeLayerIndex === index + 1) this.activeLayerIndex = index;
        this.render();
    }

    moveLayerDown(index) {
        if (index <= 0) return;
        this.moveLayerUp(index - 1);
    }

    mergeDown(index) {
        if (index <= 0 || index >= this.layers.length) return;
        this.pushHistory();
        const top    = this.layers[index];
        const bottom = this.layers[index - 1];

        bottom.ctx.save();
        bottom.ctx.globalAlpha = top.opacity;
        bottom.ctx.globalCompositeOperation = this.getCompositeOperation(top.blendMode);
        bottom.ctx.filter = top.getFilterString();
        bottom.ctx.drawImage(
            top.canvas, 0, 0, top.canvas.width, top.canvas.height,
            top.x - bottom.x, top.y - bottom.y, top.displayWidth, top.displayHeight
        );
        bottom.ctx.restore();

        this.layers.splice(index, 1);
        this.activeLayerIndex = Math.min(this.activeLayerIndex, this.layers.length - 1);
        this.render();
    }

    flatten() {
        if (this.layers.length <= 1) return;
        this.pushHistory();
        const temp  = document.createElement('canvas');
        temp.width  = this.width;
        temp.height = this.height;
        const tCtx  = temp.getContext('2d');

        for (const layer of this.layers) {
            if (!layer.visible) continue;
            tCtx.globalAlpha = layer.opacity;
            tCtx.globalCompositeOperation = this.getCompositeOperation(layer.blendMode);
            tCtx.filter = layer.getFilterString();
            tCtx.drawImage(
                layer.canvas, 0, 0, layer.canvas.width, layer.canvas.height,
                layer.x, layer.y, layer.displayWidth, layer.displayHeight
            );
            tCtx.filter = 'none';
        }

        const flat = new Layer('Merged', this.width, this.height);
        flat.ctx.drawImage(temp, 0, 0);
        this.layers = [flat];
        this.activeLayerIndex = 0;
        this.render();
    }

    setActiveLayer(index) {
        if (index >= 0 && index < this.layers.length) this.activeLayerIndex = index;
    }

    getActiveLayer() {
        return this.layers[this.activeLayerIndex];
    }

    setLayerVisibility(index, visible) {
        if (this.layers[index]) { this.layers[index].visible = visible; this.render(); }
    }

    setLayerOpacity(index, opacity) {
        if (this.layers[index]) { this.layers[index].opacity = Math.max(0, Math.min(1, opacity)); this.render(); }
    }

    setLayerBlendMode(index, mode) {
        if (this.layers[index]) { this.layers[index].blendMode = mode; this.render(); }
    }

    setLayerLocked(index, locked) {
        if (this.layers[index]) this.layers[index].locked = locked;
    }

    // ─────────────────────────────────────────────────────────────
    // Selection
    // ─────────────────────────────────────────────────────────────

    setSelection(x, y, w, h) {
        // Normalise negative dimensions (drag direction)
        if (w < 0) { x += w; w = -w; }
        if (h < 0) { y += h; h = -h; }
        if (w < 2 || h < 2) { this.selection = null; this.render(); return; }
        this.selection = { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) };
        this.render();
    }

    clearSelection() {
        this.selection = null;
        this.render();
    }

    cropToSelection() {
        if (!this.selection) return;
        this.pushHistory();
        const { x, y, w, h } = this.selection;

        for (const layer of this.layers) {
            const temp  = document.createElement('canvas');
            temp.width  = w;
            temp.height = h;
            // Map canvas selection coords to layer canvas pixel coords
            const scaleX = layer.canvas.width  / layer.displayWidth;
            const scaleY = layer.canvas.height / layer.displayHeight;
            const sx = (x - layer.x) * scaleX;
            const sy = (y - layer.y) * scaleY;
            temp.getContext('2d').drawImage(layer.canvas, sx, sy, w * scaleX, h * scaleY, 0, 0, w, h);
            layer.canvas.width  = w;
            layer.canvas.height = h;
            layer.ctx = layer.canvas.getContext('2d');
            layer.ctx.drawImage(temp, 0, 0);
            layer.x = 0;  layer.y = 0;
            layer.displayWidth = w;  layer.displayHeight = h;
        }

        this.width     = w;
        this.height    = h;
        this.selection = null;
        this.setupCanvas();
    }

    deleteSelection() {
        const layer = this.getActiveLayer();
        if (!layer || layer.locked || !this.selection) return;
        this.pushHistory();
        const { x, y, w, h } = this.selection;
        const scaleX = layer.canvas.width  / layer.displayWidth;
        const scaleY = layer.canvas.height / layer.displayHeight;
        layer.ctx.clearRect((x - layer.x) * scaleX, (y - layer.y) * scaleY, w * scaleX, h * scaleY);
        this.render();
    }

    fillSelection(color) {
        const layer = this.getActiveLayer();
        if (!layer || layer.locked) return;
        this.pushHistory();
        if (this.selection) {
            const { x, y, w, h } = this.selection;
            const scaleX = layer.canvas.width  / layer.displayWidth;
            const scaleY = layer.canvas.height / layer.displayHeight;
            layer.ctx.fillStyle = color;
            layer.ctx.fillRect((x - layer.x) * scaleX, (y - layer.y) * scaleY, w * scaleX, h * scaleY);
        } else {
            layer.ctx.fillStyle = color;
            layer.ctx.fillRect(0, 0, layer.canvas.width, layer.canvas.height);
        }
        this.render();
    }

    copySelection() {
        const layer = this.getActiveLayer();
        if (!layer) return;
        const temp = document.createElement('canvas');
        if (this.selection) {
            const { x, y, w, h } = this.selection;
            temp.width  = w;
            temp.height = h;
            const scaleX = layer.canvas.width  / layer.displayWidth;
            const scaleY = layer.canvas.height / layer.displayHeight;
            temp.getContext('2d').drawImage(layer.canvas,
                (x - layer.x) * scaleX, (y - layer.y) * scaleY, w * scaleX, h * scaleY,
                0, 0, w, h);
            this._clipboard = { canvas: temp, offsetX: x, offsetY: y };
        } else {
            temp.width  = layer.canvas.width;
            temp.height = layer.canvas.height;
            temp.getContext('2d').drawImage(layer.canvas, 0, 0);
            this._clipboard = { canvas: temp, offsetX: layer.x, offsetY: layer.y };
        }
    }

    pasteAsLayer() {
        if (!this._clipboard) return null;
        this.pushHistory();
        const cb    = this._clipboard;
        const layer = new Layer('Pasted', cb.canvas.width, cb.canvas.height);
        layer.ctx.drawImage(cb.canvas, 0, 0);
        layer.x            = cb.offsetX + 20;
        layer.y            = cb.offsetY + 20;
        layer.displayWidth  = cb.canvas.width;
        layer.displayHeight = cb.canvas.height;
        this.layers.push(layer);
        this.activeLayerIndex = this.layers.length - 1;
        this.render();
        return layer;
    }

    // ─────────────────────────────────────────────────────────────
    // Text
    // ─────────────────────────────────────────────────────────────

    addTextLayer(text, options = {}) {
        if (!text || !text.trim()) return null;
        const {
            x      = 50,
            y      = 50,
            size   = 24,
            font   = 'Inter',
            color  = '#000000',
            bold   = false,
            italic = false
        } = options;

        this.pushHistory();

        const fontStr = `${italic ? 'italic ' : ''}${bold ? 'bold ' : ''}${size}px "${font}", sans-serif`;
        const probe   = document.createElement('canvas').getContext('2d');
        probe.font    = fontStr;
        const lines   = text.split('\n');
        const lineH   = Math.ceil(size * 1.35);
        let maxW      = 0;
        for (const ln of lines) maxW = Math.max(maxW, probe.measureText(ln).width);

        const w = Math.max(1, Math.ceil(maxW) + 20);
        const h = Math.max(1, lines.length * lineH + 16);

        const layer = new Layer('Text', w, h);
        layer.ctx.font         = fontStr;
        layer.ctx.fillStyle    = color;
        layer.ctx.textBaseline = 'top';
        lines.forEach((ln, i) => layer.ctx.fillText(ln, 10, 8 + i * lineH));

        layer.x             = x;
        layer.y             = y;
        layer.displayWidth  = w;
        layer.displayHeight = h;

        this.layers.push(layer);
        this.activeLayerIndex = this.layers.length - 1;
        this.render();
        return layer;
    }

    // ─────────────────────────────────────────────────────────────
    // Render
    // ─────────────────────────────────────────────────────────────

    render() {
        this.mainCtx.clearRect(0, 0, this.mainCanvas.width, this.mainCanvas.height);

        for (const layer of this.layers) {
            if (!layer.visible) continue;
            this.mainCtx.globalAlpha              = layer.opacity;
            this.mainCtx.globalCompositeOperation = this.getCompositeOperation(layer.blendMode);
            this.mainCtx.filter                   = layer.getFilterString();
            this.mainCtx.drawImage(
                layer.canvas, 0, 0, layer.canvas.width, layer.canvas.height,
                layer.x, layer.y, layer.displayWidth, layer.displayHeight
            );
            this.mainCtx.filter = 'none';
        }

        // Reset composite
        this.mainCtx.globalCompositeOperation = 'source-over';
        this.mainCtx.globalAlpha              = 1.0;

        if (this.showTransformHandles) this._drawTransformHandles();
        if (this.selection)            this._drawSelection();

        if (this.onAfterRender) this.onAfterRender();
    }

    _drawTransformHandles() {
        const layer = this.getActiveLayer();
        if (!layer) return;
        const ctx = this.mainCtx;
        const { x, y } = layer, w = layer.displayWidth, h = layer.displayHeight;
        const s = 10, half = s / 2;

        ctx.save();
        ctx.strokeStyle = '#7c6ff7';
        ctx.lineWidth   = 1.5 / this.zoom;
        ctx.strokeRect(x, y, w, h);

        const positions = [
            [x, y], [x + w/2, y], [x + w, y],
            [x, y + h/2],                       [x + w, y + h/2],
            [x, y + h], [x + w/2, y + h], [x + w, y + h]
        ];
        ctx.fillStyle = 'white';
        for (const [px, py] of positions) {
            ctx.fillRect(px - half, py - half, s, s);
            ctx.strokeRect(px - half, py - half, s, s);
        }
        ctx.restore();
    }

    _drawSelection() {
        const { x, y, w, h } = this.selection;
        const ctx = this.mainCtx;
        ctx.save();
        // White dashes
        ctx.strokeStyle   = 'rgba(255,255,255,0.9)';
        ctx.lineWidth     = 1.5 / this.zoom;
        ctx.setLineDash([6 / this.zoom, 3 / this.zoom]);
        ctx.strokeRect(x, y, w, h);
        // Blue offset dashes
        ctx.strokeStyle   = 'rgba(50,140,255,0.85)';
        ctx.lineDashOffset = 6 / this.zoom;
        ctx.strokeRect(x, y, w, h);
        ctx.setLineDash([]);
        ctx.restore();
    }

    getCompositeOperation(mode) {
        const map = {
            'normal':     'source-over',
            'multiply':   'multiply',
            'screen':     'screen',
            'overlay':    'overlay',
            'darken':     'darken',
            'lighten':    'lighten',
            'color-dodge': 'color-dodge',
            'color-burn':  'color-burn',
            'hard-light':  'hard-light',
            'soft-light':  'soft-light',
            'difference':  'difference',
            'exclusion':   'exclusion'
        };
        return map[mode] || 'source-over';
    }

    // ─────────────────────────────────────────────────────────────
    // Image loading
    // ─────────────────────────────────────────────────────────────

    async loadImage(url, name = 'Image Layer', autoSize = false) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.crossOrigin = 'anonymous';
            img.onload = () => {
                if (autoSize) {
                    this.width  = img.width;
                    this.height = img.height;
                    this.mainCanvas.width  = this.width;
                    this.mainCanvas.height = this.height;
                }
                const layer = new Layer(name, img.width, img.height);
                layer.displayWidth  = img.width;
                layer.displayHeight = img.height;
                layer.ctx.drawImage(img, 0, 0);
                this.layers.push(layer);
                this.activeLayerIndex = this.layers.length - 1;
                this.render();
                resolve(layer);
            };
            img.onerror = reject;
            img.src = url;
        });
    }

    // ─────────────────────────────────────────────────────────────
    // Export / project serialisation
    // ─────────────────────────────────────────────────────────────

    exportToPNG() {
        return this.mainCanvas.toDataURL('image/png');
    }

    toJSON() {
        return JSON.stringify({
            width:   this.width,
            height:  this.height,
            version: '1.1.0',
            layers:  this.layers.map(l => ({
                name:          l.name,
                visible:       l.visible,
                locked:        l.locked,
                opacity:       l.opacity,
                blendMode:     l.blendMode,
                x:             l.x,
                y:             l.y,
                displayWidth:  l.displayWidth,
                displayHeight: l.displayHeight,
                filters:       { ...l.filters },
                data:          l.canvas.toDataURL('image/png')
            }))
        });
    }

    async fromJSON(jsonStr) {
        const project = JSON.parse(jsonStr);
        this.width  = project.width  || 1920;
        this.height = project.height || 1080;
        this.mainCanvas.width  = this.width;
        this.mainCanvas.height = this.height;
        this.layers = [];

        for (const ld of project.layers) {
            const layer = await new Promise(res => {
                const img = new Image();
                img.onload = () => {
                    const l = new Layer(ld.name, img.width, img.height);
                    l.visible       = ld.visible  ?? true;
                    l.locked        = ld.locked   ?? false;
                    l.opacity       = ld.opacity  ?? 1.0;
                    l.blendMode     = ld.blendMode ?? 'normal';
                    l.displayWidth  = ld.displayWidth  || img.width;
                    l.displayHeight = ld.displayHeight || img.height;
                    l.x             = ld.x || 0;
                    l.y             = ld.y || 0;
                    l.filters       = { ...ld.filters };
                    l.ctx.drawImage(img, 0, 0);
                    res(l);
                };
                img.src = ld.data;
            });
            this.layers.push(layer);
        }

        this.activeLayerIndex = this.layers.length - 1;
        // Seed the undo stack with the loaded state
        this._undoStack   = [];
        this._undoPointer = -1;
        this.pushHistory();
        this.render();
    }

    // ─────────────────────────────────────────────────────────────
    // Drawing tools
    // ─────────────────────────────────────────────────────────────

    _toLayerCoords(x, y, layer) {
        const scaleX = layer.canvas.width  / layer.displayWidth;
        const scaleY = layer.canvas.height / layer.displayHeight;
        return [(x - layer.x) * scaleX, (y - layer.y) * scaleY, scaleX, scaleY];
    }

    drawBrush(x, y, color = '#000000', size = 10, opacity = 1.0) {
        const layer = this.getActiveLayer();
        if (!layer || layer.locked) return;
        const [lx, ly, sX] = this._toLayerCoords(x, y, layer);
        const ctx = layer.ctx;
        ctx.save();
        ctx.globalAlpha = opacity;
        ctx.fillStyle   = color;
        ctx.beginPath();
        ctx.arc(lx, ly, size * sX, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
        this.render();
    }

    drawBrushLine(x1, y1, x2, y2, color, size, opacity = 1.0) {
        const layer = this.getActiveLayer();
        if (!layer || layer.locked) return;
        const [lx1, ly1, sX, sY] = this._toLayerCoords(x1, y1, layer);
        const [lx2, ly2]         = this._toLayerCoords(x2, y2, layer);
        const r = size * sX;

        const ctx = layer.ctx;
        ctx.save();
        ctx.globalAlpha              = opacity;
        ctx.strokeStyle              = color;
        ctx.lineWidth                = r * 2;
        ctx.lineCap                  = 'round';
        ctx.lineJoin                 = 'round';
        ctx.globalCompositeOperation = 'source-over';
        ctx.beginPath();
        ctx.moveTo(lx1, ly1);
        ctx.lineTo(lx2, ly2);
        ctx.stroke();
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(lx2, ly2, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
        this.render();
    }

    drawEraser(x, y, size = 10) {
        const layer = this.getActiveLayer();
        if (!layer || layer.locked) return;
        const [lx, ly, sX] = this._toLayerCoords(x, y, layer);
        const ctx = layer.ctx;
        ctx.save();
        ctx.globalCompositeOperation = 'destination-out';
        ctx.beginPath();
        ctx.arc(lx, ly, size * sX, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
        this.render();
    }

    drawEraserLine(x1, y1, x2, y2, size) {
        const layer = this.getActiveLayer();
        if (!layer || layer.locked) return;
        const [lx1, ly1, sX] = this._toLayerCoords(x1, y1, layer);
        const [lx2, ly2]     = this._toLayerCoords(x2, y2, layer);
        const r = size * sX;

        const ctx = layer.ctx;
        ctx.save();
        ctx.globalCompositeOperation = 'destination-out';
        ctx.lineWidth                = r * 2;
        ctx.lineCap                  = 'round';
        ctx.strokeStyle              = 'rgba(0,0,0,1)';
        ctx.beginPath();
        ctx.moveTo(lx1, ly1);
        ctx.lineTo(lx2, ly2);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(lx2, ly2, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
        this.render();
    }

    // ─────────────────────────────────────────────────────────────
    // Image operations
    // ─────────────────────────────────────────────────────────────

    flipHorizontal() {
        const layer = this.getActiveLayer();
        if (!layer) return;
        this.pushHistory();
        const temp = document.createElement('canvas');
        temp.width  = layer.canvas.width;
        temp.height = layer.canvas.height;
        const tctx  = temp.getContext('2d');
        tctx.scale(-1, 1);
        tctx.drawImage(layer.canvas, -layer.canvas.width, 0);
        layer.clear();
        layer.ctx.drawImage(temp, 0, 0);
        this.render();
    }

    flipVertical() {
        const layer = this.getActiveLayer();
        if (!layer) return;
        this.pushHistory();
        const temp = document.createElement('canvas');
        temp.width  = layer.canvas.width;
        temp.height = layer.canvas.height;
        const tctx  = temp.getContext('2d');
        tctx.scale(1, -1);
        tctx.drawImage(layer.canvas, 0, -layer.canvas.height);
        layer.clear();
        layer.ctx.drawImage(temp, 0, 0);
        this.render();
    }

    invertColors() {
        const layer = this.getActiveLayer();
        if (!layer) return;
        this.pushHistory();
        const w = layer.canvas.width, h = layer.canvas.height;
        const id = layer.ctx.getImageData(0, 0, w, h);
        const d  = id.data;
        for (let i = 0; i < d.length; i += 4) {
            if (d[i + 3] === 0) continue;
            d[i]     = 255 - d[i];
            d[i + 1] = 255 - d[i + 1];
            d[i + 2] = 255 - d[i + 2];
        }
        layer.ctx.putImageData(id, 0, 0);
        this.render();
    }

    desaturate() {
        const layer = this.getActiveLayer();
        if (!layer) return;
        this.pushHistory();
        const w = layer.canvas.width, h = layer.canvas.height;
        const id = layer.ctx.getImageData(0, 0, w, h);
        const d  = id.data;
        for (let i = 0; i < d.length; i += 4) {
            const g = Math.round(0.299 * d[i] + 0.587 * d[i+1] + 0.114 * d[i+2]);
            d[i] = d[i+1] = d[i+2] = g;
        }
        layer.ctx.putImageData(id, 0, 0);
        this.render();
    }

    rotate90CW() {
        const oldW = this.width, oldH = this.height;
        this.pushHistory();
        this.width  = oldH;
        this.height = oldW;
        this.mainCanvas.width  = this.width;
        this.mainCanvas.height = this.height;

        for (const layer of this.layers) {
            const temp  = document.createElement('canvas');
            temp.width  = layer.canvas.height;
            temp.height = layer.canvas.width;
            const tCtx  = temp.getContext('2d');
            tCtx.translate(temp.width, 0);
            tCtx.rotate(Math.PI / 2);
            tCtx.drawImage(layer.canvas, 0, 0);

            layer.canvas.width  = temp.width;
            layer.canvas.height = temp.height;
            layer.ctx = layer.canvas.getContext('2d');
            layer.ctx.drawImage(temp, 0, 0);

            const odw = layer.displayWidth, odh = layer.displayHeight;
            layer.displayWidth  = odh;
            layer.displayHeight = odw;
            const ox = layer.x, oy = layer.y;
            layer.x = oldH - (oy + odh);
            layer.y = ox;
        }
        this.render();
    }
}
