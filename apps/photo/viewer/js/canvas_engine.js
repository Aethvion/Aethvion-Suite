/**
 * canvas_engine.js — Core rendering and layer management for Aethvion Photo
 */

export class Layer {
    constructor(name, width, height) {
        this.id = Math.random().toString(36).substr(2, 9);
        this.name = name;
        this.visible = true;
        this.opacity = 1.0;
        this.blendMode = 'normal';
        this.x = 0;
        this.y = 0;
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
        let f = this.filters;
        let str = '';
        if (f.brightness !== 100) str += `brightness(${f.brightness}%) `;
        if (f.contrast !== 100) str += `contrast(${f.contrast}%) `;
        if (f.saturate !== 100) str += `saturate(${f.saturate}%) `;
        if (f.blur !== 0) str += `blur(${f.blur}px) `;
        if (f.grayscale !== 0) str += `grayscale(${f.grayscale}%) `;
        if (f.sepia !== 0) str += `sepia(${f.sepia}%) `;
        return str || 'none';
    }
}

export class CanvasEngine {
    constructor(canvasId, containerId) {
        this.mainCanvas = document.getElementById(canvasId);
        this.mainCtx = this.mainCanvas.getContext('2d');
        this.container = document.getElementById(containerId);
        
        this.width = 1920;
        this.height = 1080;
        this.layers = [];
        this.activeLayerIndex = -1;
        this.zoom = 1.0;
        
        this.setupCanvas();
    }

    setupCanvas() {
        this.mainCanvas.width = this.width;
        this.mainCanvas.height = this.height;
        this.render();
    }

    addLayer(name = 'New Layer') {
        const layer = new Layer(name, this.width, this.height);
        this.layers.push(layer);
        this.activeLayerIndex = this.layers.length - 1;
        this.render();
        return layer;
    }

    removeLayer(index) {
        if (index >= 0 && index < this.layers.length) {
            this.layers.splice(index, 1);
            this.activeLayerIndex = Math.min(this.activeLayerIndex, this.layers.length - 1);
            this.render();
        }
    }

    setActiveLayer(index) {
        if (index >= 0 && index < this.layers.length) {
            this.activeLayerIndex = index;
        }
    }

    getActiveLayer() {
        return this.layers[this.activeLayerIndex];
    }

    render() {
        // Clear main canvas
        this.mainCtx.clearRect(0, 0, this.width, this.height);
        
        // Render layers from bottom to top
        for (const layer of this.layers) {
            if (!layer.visible) continue;
            
            this.mainCtx.globalAlpha = layer.opacity;
            this.mainCtx.globalCompositeOperation = this.getCompositeOperation(layer.blendMode);
            // Apply CSS filter from the layer data
            this.mainCtx.filter = layer.getFilterString();
            this.mainCtx.drawImage(layer.canvas, layer.x, layer.y);
            // Reset filter after drawing the layer
            this.mainCtx.filter = 'none';
        }
        
        // Reset composite for UI overlays if any
        this.mainCtx.globalCompositeOperation = 'source-over';
        this.mainCtx.globalAlpha = 1.0;
    }

    getCompositeOperation(mode) {
        const modes = {
            'normal': 'source-over',
            'multiply': 'multiply',
            'screen': 'screen',
            'overlay': 'overlay',
            'darken': 'darken',
            'lighten': 'lighten'
        };
        return modes[mode] || 'source-over';
    }

    async loadImage(url, name = 'Image Layer') {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.crossOrigin = "anonymous";
            img.onload = () => {
                const layer = this.addLayer(name);
                // Center image if smaller than canvas
                layer.ctx.drawImage(img, 0, 0);
                this.render();
                resolve(layer);
            };
            img.onerror = reject;
            img.src = url;
        });
    }

    exportToPNG() {
        return this.mainCanvas.toDataURL("image/png");
    }

    setLayerVisibility(index, visible) {
        if (this.layers[index]) {
            this.layers[index].visible = visible;
            this.render();
        }
    }

    // Tools
    drawBrush(x, y, color = '#000000', size = 5, opacity = 1.0) {
        const layer = this.getActiveLayer();
        if (!layer) return;
        
        const ctx = layer.ctx;
        ctx.globalAlpha = opacity;
        ctx.fillStyle = color;
        ctx.globalCompositeOperation = 'source-over';
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fill();
        this.render();
    }

    drawEraser(x, y, size = 10) {
        const layer = this.getActiveLayer();
        if (!layer) return;

        const ctx = layer.ctx;
        ctx.globalCompositeOperation = 'destination-out';
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fill();
        this.render();
    }
}
