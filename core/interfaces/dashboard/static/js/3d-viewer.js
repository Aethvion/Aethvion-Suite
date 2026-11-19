/**
 * Aethvion Suite — 3DViewer Engine
 * 
 * A high-fidelity Three.js viewport with OrbitControls, cinematic lighting presets,
 * and cohesive environment mapping. Optimized for GLB generated models.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { Reflector } from 'three/addons/objects/Reflector.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

export class ThreeDViewer {
    constructor(containerOrId, options = {}) {
        this.container = typeof containerOrId === 'string'
            ? document.getElementById(containerOrId)
            : containerOrId;
        if (!this.container) {
            console.error(`[ThreeDViewer] Container not found:`, containerOrId);
            return;
        }
        this.options = options || {};
        this._rafId = null;

        const w = this.container.clientWidth || 300;
        const h = this.container.clientHeight || 220;

        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 1000);

        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        this.renderer.setSize(w, h);
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.0;

        this.renderer.domElement.style.display = 'block';
        this.renderer.domElement.style.width = '100%';
        this.renderer.domElement.style.height = '100%';
        if (this.options.stopPropagation) {
            ['mousedown', 'pointerdown', 'wheel'].forEach((evt) => {
                this.renderer.domElement.addEventListener(evt, (e) => e.stopPropagation());
            });
        }

        this.container.appendChild(this.renderer.domElement);

        // Pre-compile the environment map to be used across presets
        const pmremGenerator = new THREE.PMREMGenerator(this.renderer);
        pmremGenerator.compileEquirectangularShader();
        this.envMap = pmremGenerator.fromScene(new RoomEnvironment(), 0.04).texture;
        pmremGenerator.dispose();
        this.scene.environment = this.envMap;

        this.controls = new OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.04;
        this.controls.screenSpacePanning = true;
        this.controls.maxPolarAngle = Math.PI / 2 - 0.02;
        this.controls.minDistance = 0.1;
        this.controls.maxDistance = 10;
        this.controls.autoRotate = !!this.options.autoRotate;
        this.controls.autoRotateSpeed = 2.0;

        this.loader = new GLTFLoader();
        this.model = null;
        this.ground = null;
        this.reflector = null;
        this.lights = [];
        this.currentPreset = 'studio';
        this.lightIntensity = 1.0;
        this.currentShadingMode = 'normal';

        this.isAnimating = true; // Master kill switch
        this.isRendering = false; // Current loop state
        this.init();
    }

    init() {
        this.camera.position.set(1.5, 1.2, 1.5);
        this.controls.target.set(0, 0.5, 0);
        
        // Resume rendering when controls change
        this.controls.addEventListener('change', () => this.requestRender());

        this.initGround();
        this.setLightingPreset('studio');

        this.resizeObserver = new ResizeObserver(() => this.onResize());
        this.resizeObserver.observe(this.container);

        this.requestRender();
    }

    initGround() {
        const groundGeo = this.options.compact
            ? new THREE.CircleGeometry(3.0, 48)
            : new THREE.PlaneGeometry(50, 50);

        // 1. Static Mesh (The material layer)
        const groundMat = new THREE.MeshStandardMaterial({
            color: this.options.compact ? 0x0b0e14 : 0x050505,
            metalness: this.options.compact ? 0.35 : 0.9,
            roughness: this.options.compact ? 0.65 : 0.15,
            opacity: this.options.compact ? 0.55 : 0.65,
            transparent: true,
            depthWrite: false
        });
        this.ground = new THREE.Mesh(groundGeo, groundMat);
        this.ground.rotation.x = -Math.PI / 2;
        this.ground.position.y = 0;
        this.ground.receiveShadow = true;
        this.scene.add(this.ground);

        if (!this.options.compact) {
            // 2. Real-time Reflector (The mirroring layer)
            this.reflector = new Reflector(groundGeo, {
                clipBias: 0.003,
                textureWidth: window.innerWidth * window.devicePixelRatio,
                textureHeight: window.innerHeight * window.devicePixelRatio,
                color: 0x888888
            });
            this.reflector.rotation.x = -Math.PI / 2;
            this.reflector.position.y = -0.001;
            this.scene.add(this.reflector);
        }
    }

    configureShadow(light) {
        light.castShadow = true;
        light.shadow.mapSize.width = 2048;
        light.shadow.mapSize.height = 2048;
        light.shadow.bias = -0.0001;
        light.shadow.normalBias = 0.02;
        light.shadow.camera.left = -1.5;
        light.shadow.camera.right = 1.5;
        light.shadow.camera.top = 1.5;
        light.shadow.camera.bottom = -1.5;
        light.shadow.camera.near = 0.1;
        light.shadow.camera.far = 15;
        light.shadow.radius = 4;
    }

    clearLights() {
        this.lights.forEach(l => this.scene.remove(l));
        this.lights = [];
    }

    setLightingPreset(id) {
        this.currentPreset = id;
        this.clearLights();

        if (id === 'none') {
            this.scene.environment = this.envMap;
            const hemiFlat = new THREE.HemisphereLight(0xffffff, 0xffffff, 1.2);
            const ambient = new THREE.AmbientLight(0xffffff, 0.4);
            this.lights.push(hemiFlat, ambient);
            this.scene.background = new THREE.Color(0x1a1a1a);
            this.scene.fog = new THREE.FogExp2(0x1a1a1a, 0.05);
            this.lights.forEach(l => this.scene.add(l));
            this.requestRender();
            return;
        }

        this.scene.environment = this.envMap;

        switch (id) {
            case 'dramatic':
                const ambientD = new THREE.AmbientLight(0x080c16, 0.1);
                const keyD = new THREE.DirectionalLight(0xaaaaff, 2.5);
                keyD.position.set(3, 4, 3);
                this.configureShadow(keyD);
                const rimLight = new THREE.DirectionalLight(0xff7733, 4.0);
                rimLight.position.set(-3, 2, -4);
                this.lights.push(ambientD, keyD, rimLight);
                this.scene.background = new THREE.Color(0x050608);
                this.scene.fog = new THREE.FogExp2(0x050608, 0.08);
                break;
            case 'outdoor':
                const hemiOutdoor = new THREE.HemisphereLight(0x88ccff, 0x443322, 0.5);
                const sun = new THREE.DirectionalLight(0xffeedd, 3.0);
                sun.position.set(5, 6, 3);
                this.configureShadow(sun);
                this.lights.push(hemiOutdoor, sun);
                this.scene.background = new THREE.Color(0x161a22);
                this.scene.fog = new THREE.FogExp2(0x161a22, 0.06);
                break;
            case 'studio':
            default:
                const hemiStudio = new THREE.HemisphereLight(0xffffff, 0x444444, 0.6);
                const keyLight = new THREE.DirectionalLight(0xfff5e6, 1.8);
                keyLight.position.set(2, 4, 3);
                this.configureShadow(keyLight);
                const fillLight = new THREE.DirectionalLight(0xaaccff, 0.8);
                fillLight.position.set(-4, 3, -2);
                this.lights.push(hemiStudio, keyLight, fillLight);
                this.scene.background = new THREE.Color(0x0e1014);
                this.scene.fog = new THREE.FogExp2(0x0e1014, 0.05);
                break;
        }

        this.lights.forEach(l => this.scene.add(l));
        this.requestRender();
    }

    setLightIntensity(val) {
        this.lightIntensity = parseFloat(val);
        this.renderer.toneMappingExposure = Math.max(0.01, this.lightIntensity);
        this.requestRender();
    }

    setShadingMode(mode) {
        this.currentShadingMode = mode;
        if (!this.model) return;

        this.model.traverse(node => {
            if (node.isMesh && !node.userData.isWireframeOverlay) {
                const showSolid = (mode !== 'wireframe');
                if (node.material) {
                    if (Array.isArray(node.material)) node.material.forEach(m => m.visible = showSolid);
                    else node.material.visible = showSolid;
                }
                const showWire = (mode === 'solid-wire' || mode === 'wireframe');
                if (showWire) {
                    if (!node.userData.wireframeOverlay) {
                        const wireMat = new THREE.MeshBasicMaterial({ 
                            color: 0x00e5ff, wireframe: true, transparent: true,
                            opacity: 0.35, depthWrite: false
                        });
                        const wireMesh = new THREE.Mesh(node.geometry, wireMat);
                        wireMesh.userData.isWireframeOverlay = true; 
                        wireMesh.scale.setScalar(1.002);
                        node.add(wireMesh);
                        node.userData.wireframeOverlay = wireMesh;
                    }
                    node.userData.wireframeOverlay.material.opacity = (mode === 'wireframe') ? 0.8 : 0.35;
                    node.userData.wireframeOverlay.visible = true;
                } else if (node.userData.wireframeOverlay) {
                    node.userData.wireframeOverlay.visible = false;
                }
            }
        });
        this.requestRender();
    }

    async loadModel(url) {
        if (!url) return;
        this.container.dispatchEvent(new CustomEvent('viewer-loading'));
        if (this.model) this.scene.remove(this.model);

        return new Promise((resolve, reject) => {
            this.loader.load(url, (gltf) => {
                this.model = gltf.scene;
                this.model.rotation.y = 0;
                const box = new THREE.Box3().setFromObject(this.model);
                const size = new THREE.Vector3();
                box.getSize(size);
                const center = new THREE.Vector3();
                box.getCenter(center);
                this.model.position.x -= center.x;
                this.model.position.z -= center.z;
                const maxDim = Math.max(size.x, size.y, size.z);
                const scale = maxDim > 0 ? 0.85 / maxDim : 1.0;
                this.model.scale.setScalar(scale);
                const finalBox = new THREE.Box3().setFromObject(this.model);
                this.model.position.y = -finalBox.min.y;
                this.model.traverse(node => {
                    if (node.isMesh) {
                        node.castShadow = true;
                        node.receiveShadow = true;
                        if (node.material && node.material.envMapIntensity !== undefined) node.material.envMapIntensity = 1.0;
                    }
                });
                this.scene.add(this.model);
                this.resetCamera();
                if (this.currentShadingMode !== 'normal') this.setShadingMode(this.currentShadingMode);
                this.container.dispatchEvent(new CustomEvent('viewer-loaded', { detail: { scene: gltf.scene } }));
                this.requestRender();
                resolve(gltf);
            }, undefined, (err) => {
                this.container.dispatchEvent(new CustomEvent('viewer-error', { detail: err }));
                reject(err);
            });
        });
    }

    toggleFloor(visible) {
        if (this.ground) this.ground.visible = visible;
        if (this.reflector) this.reflector.visible = visible;
        this.requestRender();
    }

    setAutoRotate(enabled) {
        if (!this.controls) return;
        this.controls.autoRotate = !!enabled;
        this.requestRender();
    }

    resetCamera() {
        this.controls.reset();
        this.camera.position.set(1.5, 1.2, 1.5);
        this.controls.target.set(0, 0.4, 0);
        this.controls.update();
        this.requestRender();
    }

    onResize() {
        if (!this.container || !this.renderer) return;
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;
        if (width === 0 || height === 0) return;
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
        this.requestRender();
    }

    requestRender() {
        if (!this.renderer || this.isRendering || !this.isAnimating) return;

        // Visibility guard
        if (document.hidden || !this.container.isConnected || this.container.clientWidth === 0) return;

        this.isRendering = true;
        this._rafId = requestAnimationFrame(() => this.renderLoop());
    }

    renderLoop() {
        if (!this.isAnimating || !this.renderer) {
            this.isRendering = false;
            this._rafId = null;
            return;
        }

        // Check if camera is still moving (controls.update returns true if damping is active)
        const needsMore = this.controls.update();

        this.renderer.render(this.scene, this.camera);

        if (needsMore || this.controls.autoRotate) {
            this._rafId = requestAnimationFrame(() => this.renderLoop());
        } else {
            this.isRendering = false;
            this._rafId = null;
        }
    }

    dispose() {
        this.isAnimating = false;
        this.isRendering = false;
        if (this._rafId !== null) {
            cancelAnimationFrame(this._rafId);
            this._rafId = null;
        }
        if (this.resizeObserver) this.resizeObserver.disconnect();
        if (this.controls) this.controls.dispose();
        if (this.scene) {
            this.scene.traverse(obj => {
                if (obj.geometry) obj.geometry.dispose();
                if (obj.material) {
                    if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
                    else obj.material.dispose();
                }
            });
        }
        if (this.envMap) this.envMap.dispose();
        if (this.renderer) {
            this.renderer.dispose();
            if (this.renderer.domElement && this.renderer.domElement.parentNode) {
                this.renderer.domElement.parentNode.removeChild(this.renderer.domElement);
            }
        }
    }
}