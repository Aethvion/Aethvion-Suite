/**
 * Aethvion Suite — Hardware Profile & Model Compatibility Engine
 * (hardware-profile.js)
 * 
 * Manages system hardware detection, user-specified hardware overrides,
 * and unified compatibility analysis across Text, Image, Audio, and 3D models.
 */
'use strict';

const HardwareProfile = (() => {
    let _specs = null;
    let _loading = false;
    let _subscribers = new Set();

    /**
     * Fetch or retrieve cached hardware specifications.
     */
    async function getSpecs(forceRefresh = false) {
        if (_specs && !forceRefresh) return _specs;
        if (_loading) return _specs;

        _loading = true;
        try {
            const url = forceRefresh ? '/api/registry/local/system-specs?refresh=true' : '/api/registry/local/system-specs';
            const res = await fetch(url);
            if (res.ok) {
                _specs = await res.json();
                _notify();
            }
        } catch (e) {
            console.warn('[HardwareProfile] Hardware detection failed:', e);
        } finally {
            _loading = false;
        }
        return _specs;
    }

    function getCachedSpecs() {
        return _specs;
    }

    /**
     * Unified Compatibility Evaluator
     * Returns: { status: 'gpu'|'partial'|'cpu'|'heavy'|'unknown', label, badgeClass, icon, runnable: bool, hint }
     */
    function evaluate(modelInfo) {
        if (!_specs) {
            return {
                status: 'unknown',
                label: 'Checking...',
                badgeClass: 'compat-unknown',
                icon: 'fa-question-circle',
                runnable: true,
                hint: 'Analyzing hardware compatibility...'
            };
        }

        const vram = Number(_specs.vram_gb) || 0;
        const ram  = Number(_specs.ram_total_gb) || 0;
        const cuda = !!_specs.cuda_available;
        const type = (modelInfo.type || 'text').toLowerCase();

        // 1. 3D Models (e.g. Trellis 2, TripoSR)
        if (type === '3d') {
            const isTrellis = String(modelInfo.id || modelInfo.name || '').toLowerCase().includes('trellis');
            if (isTrellis) {
                if (cuda && vram >= 11.5) {
                    return { status: 'gpu', label: 'Runs on GPU', badgeClass: 'compat-great', icon: 'fa-bolt', runnable: true, hint: `Optimal speed on your ${vram}GB ${specsGpuName()}` };
                } else if (cuda && vram >= 7.5) {
                    return { status: 'partial', label: 'Low-VRAM Mode', badgeClass: 'compat-good', icon: 'fa-microchip', runnable: true, hint: `Will run in low-VRAM mode on your ${vram}GB VRAM (Full quality requires 12GB)` };
                } else {
                    return { status: 'heavy', label: 'Requires 12GB GPU', badgeClass: 'compat-heavy', icon: 'fa-triangle-exclamation', runnable: false, hint: `Trellis 2 requires an NVIDIA CUDA GPU with at least 8-12GB VRAM (Found: ${vram}GB)` };
                }
            } else {
                // TripoSR or lighter 3D reconstruction
                if (cuda && vram >= 4.0) {
                    return { status: 'gpu', label: 'Runs on GPU', badgeClass: 'compat-great', icon: 'fa-bolt', runnable: true, hint: `Fully accelerated on ${specsGpuName()}` };
                } else if (ram >= 8.0) {
                    return { status: 'cpu', label: 'CPU Fallback', badgeClass: 'compat-ok', icon: 'fa-server', runnable: true, hint: `Runs on CPU via ${ram}GB RAM (slower inference)` };
                } else {
                    return { status: 'heavy', label: 'Too Heavy', badgeClass: 'compat-heavy', icon: 'fa-triangle-exclamation', runnable: false, hint: `Requires at least 4GB VRAM or 8GB RAM` };
                }
            }
        }

        // 2. Image Models (e.g. SD 1.5, SDXL, Flux)
        if (type === 'image') {
            const name = String(modelInfo.id || modelInfo.name || '').toLowerCase();
            let reqVram = Number(modelInfo.req_vram_gb) || 0;
            let reqRam  = Number(modelInfo.req_ram_gb)  || 0;

            if (!reqVram) {
                if (name.includes('flux')) { reqVram = 12.0; reqRam = 24.0; }
                else if (name.includes('sdxl') || name.includes('xl')) { reqVram = 8.0; reqRam = 16.0; }
                else { reqVram = 4.0; reqRam = 8.0; }
            }

            if (cuda && vram >= reqVram * 0.95) {
                return { status: 'gpu', label: 'Runs on GPU', badgeClass: 'compat-great', icon: 'fa-bolt', runnable: true, hint: `Fast GPU generation on ${specsGpuName()}` };
            } else if (cuda && vram >= reqVram * 0.55 && (vram + ram) >= reqVram * 1.5) {
                return { status: 'partial', label: 'Partial GPU', badgeClass: 'compat-good', icon: 'fa-microchip', runnable: true, hint: `Offloads between ${vram}GB VRAM and system RAM` };
            } else if (ram >= reqRam) {
                return { status: 'cpu', label: 'CPU Fallback', badgeClass: 'compat-ok', icon: 'fa-server', runnable: true, hint: `Runs in system RAM on CPU (slower generation)` };
            } else {
                return { status: 'heavy', label: 'Too Heavy', badgeClass: 'compat-heavy', icon: 'fa-triangle-exclamation', runnable: false, hint: `Requires at least ${reqVram}GB VRAM or ${reqRam}GB RAM` };
            }
        }

        // 3. Audio & Speech Models (e.g. Kokoro, XTTS-v2, Whisper)
        if (type === 'audio') {
            const name = String(modelInfo.id || modelInfo.name || '').toLowerCase();
            let reqVram = Number(modelInfo.req_vram_gb) || 0;
            let reqRam  = Number(modelInfo.req_ram_gb)  || 4.0;

            if (!reqVram) {
                if (name.includes('whisper-large') || name.includes('large')) { reqVram = 6.0; reqRam = 10.0; }
                else if (name.includes('xtts')) { reqVram = 3.5; reqRam = 8.0; }
                else { reqVram = 1.0; reqRam = 3.0; } // Kokoro / Whisper Base
            }

            if (cuda && vram >= reqVram) {
                return { status: 'gpu', label: 'Runs on GPU', badgeClass: 'compat-great', icon: 'fa-bolt', runnable: true, hint: `Real-time GPU synthesis/transcription on ${specsGpuName()}` };
            } else if (ram >= reqRam) {
                return { status: 'cpu', label: 'Runs on CPU', badgeClass: 'compat-good', icon: 'fa-microchip', runnable: true, hint: `Runs smoothly on CPU with your ${ram}GB RAM` };
            } else {
                return { status: 'heavy', label: 'Too Heavy', badgeClass: 'compat-heavy', icon: 'fa-triangle-exclamation', runnable: false, hint: `Requires at least ${reqRam}GB RAM` };
            }
        }

        // 4. Text & Chat Models
        let sizeGb = Number(modelInfo.size_gb) || 0;
        if (!sizeGb && modelInfo.size) {
            const gbMatch = String(modelInfo.size).match(/(\d+\.?\d*)\s*GB/i);
            const bMatch  = String(modelInfo.size).match(/(\d+\.?\d*)B/i);
            if (gbMatch) sizeGb = parseFloat(gbMatch[1]);
            else if (bMatch) sizeGb = parseFloat(bMatch[1]) * 0.6; // ~Q4 GGUF weight estimate
        }

        if (sizeGb <= 0) {
            return { status: 'gpu', label: 'Runnable', badgeClass: 'compat-great', icon: 'fa-check', runnable: true, hint: 'Compatible' };
        }

        if (cuda && vram >= sizeGb * 1.15) {
            return {
                status: 'gpu',
                label: 'Runs on GPU',
                badgeClass: 'compat-great',
                icon: 'fa-bolt',
                runnable: true,
                hint: `Fits entirely into ${vram}GB VRAM for maximum speed`
            };
        } else if (cuda && vram >= sizeGb * 0.45 && (vram + ram) >= sizeGb * 1.2) {
            return {
                status: 'partial',
                label: 'Partial GPU',
                badgeClass: 'compat-good',
                icon: 'fa-microchip',
                runnable: true,
                hint: `Offloads layers between ${vram}GB VRAM and system RAM`
            };
        } else if (ram >= sizeGb * 1.25) {
            return {
                status: 'cpu',
                label: 'CPU Only',
                badgeClass: 'compat-ok',
                icon: 'fa-server',
                runnable: true,
                hint: `Runs in system RAM (${ram}GB) on CPU. Slower inference.`
            };
        } else {
            return {
                status: 'heavy',
                label: 'Too Heavy',
                badgeClass: 'compat-heavy',
                icon: 'fa-triangle-exclamation',
                runnable: false,
                hint: `Model size (${sizeGb.toFixed(1)} GB) exceeds available VRAM (${vram}GB) and RAM (${ram}GB)`
            };
        }
    }

    function specsGpuName() {
        return (_specs && _specs.gpu_name) ? _specs.gpu_name : 'GPU';
    }

    /**
     * Render a compatibility badge HTML string.
     */
    function renderBadge(modelInfo) {
        const c = evaluate(modelInfo);
        return `<span class="compat-badge ${c.badgeClass}" title="${c.hint}"><i class="fas ${c.icon}"></i> ${c.label}</span>`;
    }

    /**
     * Render the Hardware Profile Pill for toolbars.
     */
    function renderToolbarPill() {
        if (!_specs) {
            return `<div class="hub-hw-pill" onclick="HardwareProfile.openModal()" title="Detect or customize your PC hardware profile">
                <i class="fas fa-microchip"></i> <span>Hardware: Loading...</span>
            </div>`;
        }

        const gpuText = _specs.gpu_name ? `${_specs.gpu_name} (${_specs.vram_gb}GB)` : 'No CUDA GPU';
        const ramText = `${_specs.ram_total_gb}GB RAM`;
        const customBadge = _specs.custom_override ? '<span class="hw-tag-custom">Custom</span>' : '';

        return `<div class="hub-hw-pill" onclick="HardwareProfile.openModal()" title="Hardware: ${gpuText} | ${ramText} (Click to edit or re-detect)">
            <i class="fas fa-microchip"></i> <span>${gpuText} · ${ramText}</span>${customBadge}
        </div>`;
    }

    /**
     * Attach and auto-update toolbar pill in a given container.
     */
    function attachToolbarPill(containerEl) {
        if (!containerEl) return;
        containerEl.innerHTML = renderToolbarPill();
        subscribe(() => {
            if (document.body.contains(containerEl)) {
                containerEl.innerHTML = renderToolbarPill();
            }
        });
    }

    /**
     * Open the interactive Hardware Profile & Compatibility Settings Modal.
     */
    function openModal() {
        let overlay = document.getElementById('hardware-profile-modal-overlay');
        if (overlay) overlay.remove();

        overlay = document.createElement('div');
        overlay.id = 'hardware-profile-modal-overlay';
        overlay.className = 'hw-modal-overlay';

        const s = _specs || {
            cpu_name: 'Unknown',
            ram_total_gb: 16,
            gpu_name: 'NVIDIA GPU',
            vram_gb: 8,
            cuda_available: true,
            custom_override: false
        };

        overlay.innerHTML = `
        <div class="hw-modal-card">
            <div class="hw-modal-header">
                <h3 class="hw-modal-title"><i class="fas fa-microchip"></i> PC Hardware Profile</h3>
                <button class="hw-modal-close" onclick="HardwareProfile.closeModal()">&times;</button>
            </div>
            <div class="hw-modal-body">
                <p style="margin:0; font-size:0.85rem; color:var(--text-secondary); line-height:1.4;">
                    Configure your hardware specs to calculate model compatibility ratings (Runs on GPU, Partial GPU, or CPU Only) and filter models runnable on this PC.
                </p>

                <div style="background:rgba(15,23,42,0.4); border:1px solid rgba(255,255,255,0.08); border-radius:10px; padding:0.9rem;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:0.8rem; font-weight:700; color:#fff;">
                            <i class="fas fa-sliders" style="color:var(--primary); margin-right:4px;"></i> Custom Hardware Override
                        </span>
                        <input type="checkbox" id="hw-custom-toggle" ${s.custom_override ? 'checked' : ''} style="cursor:pointer; width:16px; height:16px; accent-color:var(--primary);">
                    </div>
                    <p style="margin:0.25rem 0 0; font-size:0.75rem; color:var(--text-tertiary);">
                        Enable to simulate or lock custom specifications instead of auto-detection.
                    </p>
                </div>

                <div class="hw-field-group">
                    <label class="hw-field-label">GPU Model Name</label>
                    <input type="text" id="hw-gpu-name" class="hw-input" value="${s.gpu_name || ''}" placeholder="e.g. NVIDIA GeForce RTX 4090">
                </div>

                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:1rem;">
                    <div class="hw-field-group">
                        <label class="hw-field-label">VRAM (GB)</label>
                        <input type="number" step="0.5" min="0" max="256" id="hw-vram-gb" class="hw-input" value="${s.vram_gb || 0}">
                    </div>
                    <div class="hw-field-group">
                        <label class="hw-field-label">System RAM (GB)</label>
                        <input type="number" step="0.5" min="1" max="1024" id="hw-ram-gb" class="hw-input" value="${s.ram_total_gb || 16}">
                    </div>
                </div>

                <div class="hw-field-group">
                    <label class="hw-field-label">CPU Name</label>
                    <input type="text" id="hw-cpu-name" class="hw-input" value="${s.cpu_name || ''}" placeholder="e.g. Intel Core i9 / AMD Ryzen">
                </div>
            </div>

            <div class="hw-modal-footer">
                <button class="hub-action-btn secondary" onclick="HardwareProfile.resetToAutoDetect()">
                    <i class="fas fa-arrows-rotate"></i> Auto-Detect
                </button>
                <div style="display:flex; gap:0.5rem;">
                    <button class="hub-action-btn secondary" onclick="HardwareProfile.closeModal()">Cancel</button>
                    <button class="hub-action-btn primary" onclick="HardwareProfile.saveFromModal()">
                        <i class="fas fa-save"></i> Save Hardware
                    </button>
                </div>
            </div>
        </div>`;

        document.body.appendChild(overlay);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeModal();
        });
    }

    function closeModal() {
        const overlay = document.getElementById('hardware-profile-modal-overlay');
        if (overlay) overlay.remove();
    }

    async function saveFromModal() {
        const customToggle = document.getElementById('hw-custom-toggle')?.checked ?? false;
        const gpuName = document.getElementById('hw-gpu-name')?.value || '';
        const vramGb = parseFloat(document.getElementById('hw-vram-gb')?.value) || 0;
        const ramGb = parseFloat(document.getElementById('hw-ram-gb')?.value) || 16;
        const cpuName = document.getElementById('hw-cpu-name')?.value || 'Unknown';

        try {
            const res = await fetch('/api/registry/local/system-specs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    gpu_name: gpuName,
                    vram_gb: vramGb,
                    ram_total_gb: ramGb,
                    cpu_name: cpuName,
                    custom_override: customToggle
                })
            });

            if (res.ok) {
                _specs = await res.json();
                closeModal();
                if (typeof showNotification === 'function') {
                    showNotification('Hardware profile saved!', 'success');
                }
                _notify();
            } else {
                throw new Error('Save failed');
            }
        } catch (e) {
            alert('Failed to save hardware profile: ' + e.message);
        }
    }

    async function resetToAutoDetect() {
        try {
            const res = await fetch('/api/registry/local/system-specs/reset', { method: 'POST' });
            if (res.ok) {
                _specs = await res.json();
                closeModal();
                if (typeof showNotification === 'function') {
                    showNotification('Hardware re-detected from system!', 'success');
                }
                _notify();
            }
        } catch (e) {
            alert('Failed to auto-detect hardware: ' + e.message);
        }
    }

    function subscribe(fn) {
        _subscribers.add(fn);
    }

    function _notify() {
        window.dispatchEvent(new CustomEvent('hardwareSpecsUpdated', { detail: _specs }));
        _subscribers.forEach(fn => {
            try { fn(_specs); } catch (e) { console.warn(e); }
        });
    }

    // Auto-init on script evaluation
    getSpecs();

    return {
        getSpecs,
        getCachedSpecs,
        evaluate,
        renderBadge,
        renderToolbarPill,
        attachToolbarPill,
        openModal,
        closeModal,
        saveFromModal,
        resetToAutoDetect,
        subscribe
    };
})();

window.HardwareProfile = HardwareProfile;
