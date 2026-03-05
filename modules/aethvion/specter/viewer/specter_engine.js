class SpecterEngine {
    constructor(containerId) {
        this.containerId = containerId;
        this.app = null;
        this.currentModel = null;
        this.params = {};
        this.layers = {}; // Map of layer names to Pixi objects (Sprite or Mesh)
        this.animations = {};
        this.activeAnimations = new Set();
        this.time = 0;
        this.currentModelConfigPath = null;
        this.editBonesMode = false;
        this.bonesContainer = null;

        // Effects
        this.bloomFilter = null;
        this.colorFilter = null;

        // Panning/Zooming
        this.isDragging = false;
        this.dragStart = { x: 0, y: 0 };
        this.stageStart = { x: 0, y: 0 };

        this.onLoadingComplete = null;
        this.onModelLoaded = null;

        // Track the ticker wrapper so we don't bind it raw repeatedly
        this._updateRef = this.update.bind(this);
        this.isTickerRunning = false;
    }

    async init() {
        const container = document.getElementById(this.containerId);

        this.app = new PIXI.Application({
            width: window.innerWidth,
            height: window.innerHeight,
            backgroundColor: 0x0f111a,
            antialias: true,
            resolution: window.devicePixelRatio || 1,
            autoDensity: true,
        });

        container.appendChild(this.app.view);

        // Handle resize
        window.addEventListener('resize', () => {
            this.app.renderer.resize(window.innerWidth, window.innerHeight);
        });

        // Expose updateParam globally for UI
        window.updateParam = (key, val) => this.setParam(key, parseFloat(val));
        window.resetParams = () => this.resetParams();
        window.playAnimation = (name) => this.playAnimation(name);
        window.pauseAnimation = () => this.pauseAnimation();
        window.stopAllAnimations = () => this.stopAllAnimations();
        window.isPlayingAnimation = (name) => this.activeAnimations.has(name) && this.isTickerRunning;

        window.updateEffect = (name, val) => this.setEffect(name, parseFloat(val));
        window.toggleBoneEditor = (active) => this.setBoneEditor(active);

        // Setup PIXI filters
        // For standard we use standard Blur as bloom proxy for now to avoid external dependencies if not present.
        this.bloomFilter = new PIXI.BlurFilter();
        this.bloomFilter.blur = 0;

        this.colorFilter = new PIXI.ColorMatrixFilter();
        this.app.stage.filters = [this.bloomFilter, this.colorFilter];

        // Enable sorting for Z-Index
        this.app.stage.sortableChildren = true;

        this.bonesContainer = new PIXI.Container();
        this.bonesContainer.zIndex = 9999; // Keep bones on top
        this.app.stage.addChild(this.bonesContainer);

        // Camera Controls Setup (Zoom/Pan)
        this.app.stage.interactive = true;
        this.app.view.addEventListener('wheel', (e) => {
            e.preventDefault();
            const sf = e.deltaY > 0 ? 0.9 : 1.1;
            this.app.stage.scale.x *= sf;
            this.app.stage.scale.y *= sf;
        });

        this.app.stage.on('pointerdown', (e) => {
            // Only drag stage if we aren't dragging a bone node (bone nodes intercept events)
            if (e.target !== this.app.stage) return;
            this.isDragging = true;
            this.dragStart.x = e.data.global.x;
            this.dragStart.y = e.data.global.y;
            this.stageStart.x = this.app.stage.x;
            this.stageStart.y = this.app.stage.y;
        });

        this.app.stage.on('pointerup', () => this.isDragging = false);
        this.app.stage.on('pointerupoutside', () => this.isDragging = false);
        this.app.stage.on('pointermove', (e) => {
            if (this.isDragging) {
                const dx = e.data.global.x - this.dragStart.x;
                const dy = e.data.global.y - this.dragStart.y;
                this.app.stage.position.set(this.stageStart.x + dx, this.stageStart.y + dy);
            }
        });

        if (this.onLoadingComplete) this.onLoadingComplete();
    }

    async loadModel(configPath) {
        console.log(`[Specter] Loading model: ${configPath}`);
        try {
            const response = await fetch(configPath);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

            const config = await response.json();
            if (!config.parts || !Array.isArray(config.parts)) {
                throw new Error("Invalid model configuration: 'parts' property is missing or not an array.");
            }

            // Clear current model
            if (this.currentModel) {
                // Remove all children except bonesContainer
                const childrenToRemove = this.app.stage.children.filter(c => c !== this.bonesContainer);
                childrenToRemove.forEach(c => this.app.stage.removeChild(c));
                this.bonesContainer.removeChildren();
            }

            this.currentModel = config;
            this.currentModelConfigPath = configPath;
            this.params = config.params || {};
            this.animations = config.animations || {};
            this.layers = {};
            this.activeAnimations.clear();

            // Load textures
            const baseDir = configPath.substring(0, configPath.lastIndexOf('/'));
            const textures = {};

            for (const part of config.parts) {
                const texPath = `${baseDir}/${part.texture}`;
                textures[part.id] = await PIXI.Assets.load(texPath);
            }

            // Create layers based on draw order
            const sortedParts = [...config.parts].sort((a, b) => (a.z || 0) - (b.z || 0));

            for (const part of sortedParts) {
                let displayObject;

                if (part.mesh) {
                    // Create Mesh
                    const vertices = new Float32Array(part.mesh.vertices.map((v, i) =>
                        i % 2 === 0 ? v * part.mesh.width : v * part.mesh.height
                    ));
                    const uvs = new Float32Array(part.mesh.uvs);
                    const indices = new Uint16Array(part.mesh.indices);

                    displayObject = new PIXI.SimpleMesh(textures[part.id], vertices, uvs, indices);
                } else {
                    // Fallback to Sprite
                    displayObject = new PIXI.Sprite(textures[part.id]);
                    displayObject.anchor.set(0.5);
                    displayObject.scale.set(part.scale || 1);
                }

                displayObject.x = part.x || 0;
                displayObject.y = part.y || 0;
                displayObject.zIndex = part.z || 0;
                // Save original reference config for re-exporting later
                displayObject.specterConfig = part;

                this.app.stage.addChild(displayObject);
                this.layers[part.id] = displayObject;
            }

            // Center stage
            this.app.stage.x = this.app.screen.width / 2;
            this.app.stage.y = this.app.screen.height / 2;

            // Rebuild bone UI if active
            this.setBoneEditor(this.editBonesMode);
            this.resetParams(); // Start from clean state

            if (this.onModelLoaded) this.onModelLoaded(config);

            // Safe start update loop
            if (!this.isTickerRunning) {
                this.app.ticker.add(this._updateRef);
                this.isTickerRunning = true;
            }

            // Load and Play IDLE if exists
            if (this.animations.idle) {
                // UI hack since we don't have direct access here easily without emitting,
                // but we know index.html populates select on load.
                setTimeout(() => {
                    const select = document.getElementById('anim-select');
                    if (select) select.value = 'idle';
                    this.playAnimation('idle');
                    const icon = document.getElementById('play-icon');
                    if (icon) icon.className = 'fas fa-pause';
                }, 100);
            }

        } catch (e) {
            console.error("[Specter] Model load failed:", e);
        }
    }

    playAnimation(name) {
        if (this.animations[name]) {
            this.activeAnimations.clear(); // Only play one at a time for basic setups
            this.activeAnimations.add(name);
            if (!this.isTickerRunning) {
                this.app.ticker.add(this._updateRef);
                this.isTickerRunning = true;
            }
            console.log(`[Specter] Playing animation: ${name}`);
        }
    }

    pauseAnimation() {
        if (this.isTickerRunning) {
            this.app.ticker.remove(this._updateRef);
            this.isTickerRunning = false;
            console.log(`[Specter] Animation paused`);
        }
    }

    stopAllAnimations() {
        this.activeAnimations.clear();
        this.pauseAnimation();
        this.resetParams(); // Send rig back to 0
    }

    setParam(key, val) {
        if (this.params[key]) {
            this.params[key].value = val;
            const valEl = document.getElementById(`val-${key}`);
            if (valEl) valEl.textContent = val.toFixed(2);
        }
    }

    reorderLayer(partId, direction) {
        if (!this.layers[partId]) return;

        const layer = this.layers[partId];
        // Move zIndex up or down
        layer.zIndex += direction;

        // Update the config so it persists if we save
        if (layer.specterConfig) {
            layer.specterConfig.z = layer.zIndex;
        }

        this.app.stage.sortChildren();
        window.rebuildLayerUI(this.layers); // Ask the frontend to redraw the list
    }

    toggleLayerVisibility(partId) {
        if (!this.layers[partId]) return;
        this.layers[partId].visible = !this.layers[partId].visible;
        window.rebuildLayerUI(this.layers);
    }

    resetParams() {
        Object.keys(this.params).forEach(key => {
            this.params[key].value = this.params[key].default || 0;
            // Update UI
            const input = document.querySelector(`input[oninput*="${key}"]`);
            if (input) input.value = this.params[key].value;
            const valEl = document.getElementById(`val-${key}`);
            if (valEl) valEl.textContent = this.params[key].value.toFixed(2);
        });
    }

    setEffect(name, val) {
        if (name === 'bloom') {
            this.bloomFilter.blur = val * 10;
            const el = document.getElementById('val-fx-bloom');
            if (el) el.textContent = val.toFixed(1);
        } else if (name === 'brightness') {
            this.colorFilter.brightness(val, false);
            const el = document.getElementById('val-fx-brightness');
            if (el) el.textContent = val.toFixed(1);
        }
    }

    setBoneEditor(active) {
        this.editBonesMode = active;
        this.bonesContainer.removeChildren();

        if (!active || !this.currentModel) return;

        // Create interactive bone nodes for any meshes
        for (const [partId, layer] of Object.entries(this.layers)) {
            if (layer instanceof PIXI.SimpleMesh) {
                const partConfig = this.currentModel.parts.find(p => p.id === partId);
                if (!partConfig || !partConfig.mesh) continue;

                // Create a node for each vertex
                for (let i = 0; i < partConfig.mesh.vertices.length; i += 2) {
                    const node = new PIXI.Graphics();
                    node.beginFill(0xffffff, 0.8);
                    node.lineStyle(2, 0x00d9ff, 1);
                    node.drawCircle(0, 0, 8);
                    node.endFill();

                    // Position node relative to the layer's local space
                    node.x = layer.x + (partConfig.mesh.vertices[i] * partConfig.mesh.width);
                    node.y = layer.y + (partConfig.mesh.vertices[i + 1] * partConfig.mesh.height);

                    node.interactive = true;
                    node.cursor = 'pointer';

                    // Drag logic
                    let dragging = false;
                    node.on('pointerdown', (e) => {
                        dragging = true;
                        node.alpha = 0.5;
                        this.app.stage.interactive = true;
                    });

                    node.on('pointerup', () => { dragging = false; node.alpha = 1; });
                    node.on('pointerupoutside', () => { dragging = false; node.alpha = 1; });

                    node.on('pointermove', (e) => {
                        if (dragging) {
                            const newPos = e.data.getLocalPosition(this.bonesContainer);
                            node.x = newPos.x;
                            node.y = newPos.y;

                            // Map screen coordinate back to relative vertex percentage
                            const rawX = node.x - layer.x;
                            const rawY = node.y - layer.y;

                            layer.vertices[i] = rawX;
                            layer.vertices[i + 1] = rawY;

                            // Save permanently into the array (so deformations stack over rest pos)
                            partConfig.mesh.vertices[i] = rawX / partConfig.mesh.width;
                            partConfig.mesh.vertices[i + 1] = rawY / partConfig.mesh.height;
                        }
                    });

                    this.bonesContainer.addChild(node);
                }
            }
        }
    }

    update(delta) {
        if (!this.currentModel) return;
        this.time += delta / 60; // Approximate seconds

        // 1. Update Animations
        for (const animName of this.activeAnimations) {
            const anim = this.animations[animName];
            for (const [paramKey, config] of Object.entries(anim)) {
                if (!this.params[paramKey]) continue;

                if (config.type === 'sine') {
                    const offset = config.offset || 0;
                    const val = (Math.sin(this.time * config.speed + offset) + 1) / 2 * config.amplitude;
                    this.setParam(paramKey, val); // Using setParam syncs the UI sliders visually
                } else if (config.type === 'fixed') {
                    this.setParam(paramKey, config.value);
                }
            }
        }

        // 2. Apply Mappings
        // This is a simplified version where we map params to layer properties
        for (const mapping of (this.currentModel.mappings || [])) {
            const param = this.params[mapping.param];
            const layer = this.layers[mapping.layer];

            if (param && layer) {
                const val = param.value;

                if (mapping.type === 'rotation') {
                    layer.rotation = mapping.base + (val * mapping.multiplier);
                } else if (mapping.type === 'scale') {
                    const s = mapping.base + (val * mapping.multiplier);
                    layer.scale.set(s);
                } else if (mapping.type === 'position_x') {
                    layer.x = mapping.base + (val * mapping.multiplier);
                } else if (mapping.type === 'position_y') {
                    layer.y = mapping.base + (val * mapping.multiplier);
                } else if (mapping.type === 'alpha') {
                    layer.alpha = mapping.base + (val * mapping.multiplier);
                } else if (mapping.type === 'mesh_deform' && layer.vertices) {
                    const partConfig = this.currentModel.parts.find(p => p.id === mapping.layer);
                    if (!partConfig || !partConfig.mesh) continue;

                    const idx = mapping.vertex_index * 2 + (mapping.axis === 'y' ? 1 : 0);
                    const basePos = partConfig.mesh.vertices[idx];
                    const extent = (mapping.axis === 'y' ? partConfig.mesh.height : partConfig.mesh.width);
                    layer.vertices[idx] = (basePos * extent) + (val * mapping.multiplier * extent);
                }
            }
        }
    }
}
