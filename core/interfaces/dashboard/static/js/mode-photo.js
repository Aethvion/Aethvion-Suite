/**
 * Aethvion Suite — Photo Studio View (Workspace > Photo)
 * High-performance image generation, inpainting, upscaling, and history studio.
 * Powered by local SD WebUI / Forge, ComfyUI, downloaded local weights, and cloud backends.
 */

(function () {
    'use strict';

    const SAMPLE_PROMPTS = [
        "A majestic obsidian cyber-dragon perched on a neon skyscraper, volumetric mist, cinematic 8k render, octane",
        "Ethereal bioluminescent forest with glowing mushrooms and crystalline river, fantasy digital painting, high detail",
        "Retro-futuristic 1980s synthwave sports car speeding through a laser grid highway towards a neon sun, aesthetic",
        "Cinematic portrait of an ancient sorceress with floating arcane runes, volumetric lighting, photorealistic, 8k",
        "Cozy steampunk coffee shop in Victorian London with brass pipes, warm amber lighting, intricate interior details",
        "Isometric 3D diorama of a floating miniature cyberpunk city island, soft ambient occlusion, tilt-shift render"
    ];

    let currentRefImageBase64 = null;
    let currentMaskImageBase64 = null;

    const PhotoStudio = {
        state: {
            mode: 'generate',
            selectedSize: '1024x1024',
            selectedAspect: '1:1',
            generating: false,
            currentImage: null,
            history: []
        },

        init() {
            this.bindModeSwitcher();
            this.setupDropzones();
            this.bindControls();
            this.loadModels();
            this.loadHistory();
        },

        bindModeSwitcher() {
            document.querySelectorAll('.ps-mode-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    document.querySelectorAll('.ps-mode-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');

                    const mode = btn.dataset.mode || 'generate';
                    this.state.mode = mode;

                    const refGroup = document.getElementById('ps-ref-group');
                    const maskGroup = document.getElementById('ps-mask-group');

                    if (refGroup) {
                        refGroup.style.display = (mode === 'edit' || mode === 'upscale' || mode === 'expand') ? 'flex' : 'none';
                    }
                    if (maskGroup) {
                        maskGroup.style.display = (mode === 'edit' || mode === 'expand') ? 'flex' : 'none';
                    }
                });
            });
        },

        setupDropzones() {
            this.initDropzone('ps-ref-dropzone', 'ps-ref-input', 'ps-ref-preview', 'ps-ref-clear', 'ps-ref-text', (b64) => {
                currentRefImageBase64 = b64;
            });

            this.initDropzone('ps-mask-dropzone', 'ps-mask-input', 'ps-mask-preview', 'ps-mask-clear', 'ps-mask-text', (b64) => {
                currentMaskImageBase64 = b64;
            });
        },

        initDropzone(dropzoneId, inputId, previewId, clearId, textId, callback) {
            const dropzone = document.getElementById(dropzoneId);
            const input = document.getElementById(inputId);
            const preview = document.getElementById(previewId);
            const clearBtn = document.getElementById(clearId);
            const textEl = document.getElementById(textId);
            if (!dropzone || !input) return;

            dropzone.addEventListener('click', () => input.click());

            dropzone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropzone.style.borderColor = 'var(--primary, #38bdf8)';
            });
            dropzone.addEventListener('dragleave', (e) => {
                e.preventDefault();
                dropzone.style.borderColor = 'rgba(255, 255, 255, 0.12)';
            });
            dropzone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropzone.style.borderColor = 'rgba(255, 255, 255, 0.12)';
                if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                    this.loadFileIntoDropzone(e.dataTransfer.files[0], preview, clearBtn, textEl, callback);
                }
            });

            input.addEventListener('change', (e) => {
                if (e.target.files && e.target.files[0]) {
                    this.loadFileIntoDropzone(e.target.files[0], preview, clearBtn, textEl, callback);
                }
            });

            if (clearBtn) {
                clearBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (preview) { preview.src = ''; preview.style.display = 'none'; }
                    clearBtn.style.display = 'none';
                    if (textEl) textEl.style.display = 'block';
                    input.value = '';
                    callback(null);
                });
            }
        },

        loadFileIntoDropzone(file, preview, clearBtn, textEl, callback) {
            if (!file.type.startsWith('image/')) return;
            const reader = new FileReader();
            reader.onload = (e) => {
                if (preview) { preview.src = e.target.result; preview.style.display = 'block'; }
                if (clearBtn) clearBtn.style.display = 'flex';
                if (textEl) textEl.style.display = 'none';
                callback(e.target.result);
            };
            reader.readAsDataURL(file);
        },

        bindControls() {
            // Aspect Ratio Buttons
            document.querySelectorAll('.ps-aspect-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    document.querySelectorAll('.ps-aspect-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    this.state.selectedSize = btn.dataset.size || '1024x1024';
                    this.state.selectedAspect = btn.dataset.aspect || '1:1';
                });
            });

            // Sliders
            const stepsSlider = document.getElementById('ps-steps-slider');
            const stepsVal = document.getElementById('ps-steps-val');
            if (stepsSlider && stepsVal) {
                stepsSlider.addEventListener('input', (e) => stepsVal.textContent = e.target.value);
            }

            const cfgSlider = document.getElementById('ps-cfg-slider');
            const cfgVal = document.getElementById('ps-cfg-val');
            if (cfgSlider && cfgVal) {
                cfgSlider.addEventListener('input', (e) => cfgVal.textContent = parseFloat(e.target.value).toFixed(1));
            }

            // Random Idea Button
            const randomBtn = document.getElementById('ps-btn-random-idea');
            if (randomBtn) {
                randomBtn.addEventListener('click', () => {
                    const promptInput = document.getElementById('ps-prompt-input');
                    if (promptInput) {
                        const random = SAMPLE_PROMPTS[Math.floor(Math.random() * SAMPLE_PROMPTS.length)];
                        promptInput.value = random;
                    }
                });
            }

            // Quick Style Tags
            document.querySelectorAll('.ps-pill[data-append]').forEach(pill => {
                pill.addEventListener('click', () => {
                    const promptInput = document.getElementById('ps-prompt-input');
                    if (promptInput) {
                        const text = pill.dataset.append || '';
                        if (!promptInput.value.includes(text.trim())) {
                            promptInput.value = (promptInput.value.trim() + text).trim();
                        }
                    }
                });
            });

            // Random Seed
            const randomSeedBtn = document.getElementById('ps-btn-random-seed');
            if (randomSeedBtn) {
                randomSeedBtn.addEventListener('click', () => {
                    const seedInput = document.getElementById('ps-seed-input');
                    if (seedInput) seedInput.value = -1;
                });
            }

            // Generate Button
            const genBtn = document.getElementById('ps-generate-btn');
            if (genBtn) {
                genBtn.addEventListener('click', () => this.generateImage());
            }

            // Keyboard shortcut Ctrl+Enter on prompt
            const promptInput = document.getElementById('ps-prompt-input');
            if (promptInput) {
                promptInput.addEventListener('keydown', (e) => {
                    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                        e.preventDefault();
                        this.generateImage();
                    }
                });
            }

            // Viewport Actions
            const downloadBtn = document.getElementById('ps-btn-download');
            if (downloadBtn) {
                downloadBtn.addEventListener('click', () => this.downloadCurrentImage());
            }

            const copyPromptBtn = document.getElementById('ps-btn-copy-prompt');
            if (copyPromptBtn) {
                copyPromptBtn.addEventListener('click', () => this.copyCurrentPrompt());
            }

            const useAsRefBtn = document.getElementById('ps-btn-use-ref');
            if (useAsRefBtn) {
                useAsRefBtn.addEventListener('click', () => this.useCurrentImageAsReference());
            }

            const editCanvasBtn = document.getElementById('ps-btn-edit-canvas');
            if (editCanvasBtn) {
                editCanvasBtn.addEventListener('click', () => {
                    if (!this.state.currentImage) return;
                    window.open(`http://localhost:8005/?img=${encodeURIComponent(this.state.currentImage.url)}`, '_blank');
                });
            }

            // Refresh Strip
            const refreshStripBtn = document.getElementById('ps-btn-refresh-strip');
            if (refreshStripBtn) {
                refreshStripBtn.addEventListener('click', () => this.loadHistory());
            }
        },

        async loadModels() {
            try {
                const res = await fetch('/api/photo/models');
                if (!res.ok) return;
                const data = await res.json();
                this.populateModelSelect(data);
            } catch (e) {
                console.warn('[PhotoStudio] loadModels error:', e);
            }
        },

        populateModelSelect(data) {
            const select = document.getElementById('ps-model-select');
            if (!select) return;

            const currentVal = select.value;
            let html = '';

            // 1. SD WebUI Models if online
            if (data.sd_webui && data.sd_webui.length > 0) {
                html += `<optgroup label="Local SD WebUI Active Checkpoints">`;
                data.sd_webui.forEach(m => {
                    html += `<option value="${m.id}">${m.name}</option>`;
                });
                html += `</optgroup>`;
            }

            // 2. Local Downloaded / Suggested Checkpoints
            const suggested = data.suggested || [];
            if (suggested.length > 0) {
                html += `<optgroup label="Local Models & Checkpoints">`;
                suggested.forEach(m => {
                    const tag = m.installed ? ' (Ready)' : '';
                    html += `<option value="${m.id}">${m.name} — ${m.resolution}${tag}</option>`;
                });
                html += `</optgroup>`;
            }

            // 3. Custom dropped checkpoints
            if (data.custom && data.custom.length > 0) {
                html += `<optgroup label="Local Custom Weights">`;
                data.custom.forEach(m => {
                    html += `<option value="${m.id}">${m.name} (${m.size_label})</option>`;
                });
                html += `</optgroup>`;
            }

            // 4. Cloud providers
            html += `<optgroup label="Cloud Providers">
                <option value="imagen-3.0-generate-002">Google AI — Imagen 3</option>
                <option value="dall-e-3">OpenAI — DALL-E 3</option>
            </optgroup>`;

            select.innerHTML = html;
            if (currentVal && select.querySelector(`option[value="${currentVal}"]`)) {
                select.value = currentVal;
            }
        },

        selectModel(modelId) {
            const select = document.getElementById('ps-model-select');
            if (select && modelId) {
                select.value = modelId;
            }
        },

        async generateImage() {
            if (this.state.generating) return;

            const prompt = (document.getElementById('ps-prompt-input')?.value || '').trim();
            const mode = this.state.mode || 'generate';

            if (mode === 'generate' && !prompt) {
                if (window.showToast) window.showToast('Please enter a prompt first.', 'warning');
                document.getElementById('ps-prompt-input')?.focus();
                return;
            }

            if ((mode === 'edit' || mode === 'upscale' || mode === 'expand') && !currentRefImageBase64) {
                if (window.showToast) window.showToast(`Please provide a reference image for ${mode} mode.`, 'warning');
                return;
            }

            const negPrompt = (document.getElementById('ps-neg-prompt')?.value || '').trim();
            const model = document.getElementById('ps-model-select')?.value || 'sd-1-5';
            const size = this.state.selectedSize || '1024x1024';
            const steps = parseInt(document.getElementById('ps-steps-slider')?.value || 25, 10);
            const cfg = parseFloat(document.getElementById('ps-cfg-slider')?.value || 7.0);
            const seedVal = parseInt(document.getElementById('ps-seed-input')?.value || -1, 10);

            this.setGenerating(true);

            const startTime = Date.now();
            const timerEl = document.getElementById('ps-loading-timer');
            const timerInterval = setInterval(() => {
                const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
                if (timerEl) timerEl.textContent = `${elapsed}s`;
            }, 100);

            try {
                const res = await fetch('/api/photo/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        prompt: prompt,
                        negative_prompt: negPrompt,
                        model: model,
                        action: mode,
                        input_image: currentRefImageBase64,
                        mask_image: currentMaskImageBase64,
                        size: size,
                        steps: steps,
                        cfg_scale: cfg,
                        seed: seedVal >= 0 ? seedVal : undefined
                    })
                });

                clearInterval(timerInterval);

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Generation request failed');
                }

                const data = await res.json();
                if (!data.success || !data.images || data.images.length === 0) {
                    throw new Error(data.error || 'No images returned from generator');
                }

                const imgObj = data.images[0];
                this.displayGeneratedImage(imgObj, prompt);
                this.loadHistory();
                if (window.showToast) window.showToast('Image generated successfully!', 'success');
            } catch (e) {
                clearInterval(timerInterval);
                console.error('[PhotoStudio] generation error:', e);
                if (window.showToast) window.showToast(`Generation error: ${e.message}`, 'error');
            } finally {
                this.setGenerating(false);
            }
        },

        setGenerating(isGenerating) {
            this.state.generating = isGenerating;
            const overlay = document.getElementById('ps-loading-overlay');
            const genBtn = document.getElementById('ps-generate-btn');

            if (overlay) overlay.style.display = isGenerating ? 'flex' : 'none';
            if (genBtn) {
                genBtn.disabled = isGenerating;
                genBtn.innerHTML = isGenerating
                    ? `<i class="fas fa-spinner fa-spin"></i> Synthesizing...`
                    : `<i class="fas fa-wand-magic-sparkles"></i> Generate Image`;
            }
        },

        displayGeneratedImage(imgObj, prompt) {
            this.state.currentImage = { ...imgObj, prompt };
            const imgEl = document.getElementById('ps-viewport-img');
            const emptyEl = document.getElementById('ps-empty-state');
            const actionsEl = document.getElementById('ps-viewport-actions');

            if (imgEl) {
                imgEl.src = imgObj.url;
                imgEl.style.display = 'block';
            }
            if (emptyEl) emptyEl.style.display = 'none';
            if (actionsEl) actionsEl.style.display = 'flex';
        },

        downloadCurrentImage() {
            if (!this.state.currentImage) return;
            const a = document.createElement('a');
            a.href = this.state.currentImage.url;
            a.download = this.state.currentImage.filename || 'aethvion-visual.png';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        },

        copyCurrentPrompt() {
            if (!this.state.currentImage || !this.state.currentImage.prompt) return;
            navigator.clipboard.writeText(this.state.currentImage.prompt);
            if (window.showToast) window.showToast('Prompt copied to clipboard.', 'success');
        },

        useCurrentImageAsReference() {
            if (!this.state.currentImage) return;
            const imgUrl = this.state.currentImage.url;

            // Fetch blob and convert to base64
            fetch(imgUrl)
                .then(r => r.blob())
                .then(blob => {
                    const reader = new FileReader();
                    reader.onload = (e) => {
                        currentRefImageBase64 = e.target.result;
                        const preview = document.getElementById('ps-ref-preview');
                        const clearBtn = document.getElementById('ps-ref-clear');
                        const textEl = document.getElementById('ps-ref-text');

                        if (preview) { preview.src = e.target.result; preview.style.display = 'block'; }
                        if (clearBtn) clearBtn.style.display = 'flex';
                        if (textEl) textEl.style.display = 'none';

                        // Switch mode to Edit
                        const editBtn = document.querySelector('.ps-mode-btn[data-mode="edit"]');
                        if (editBtn) editBtn.click();

                        if (window.showToast) window.showToast('Loaded into Reference Image (Edit mode).', 'info');
                    };
                    reader.readAsDataURL(blob);
                })
                .catch(err => {
                    if (window.showToast) window.showToast('Failed to load image as reference: ' + err.message, 'error');
                });
        },

        async loadHistory() {
            try {
                const res = await fetch('/api/photo/history?limit=30');
                if (!res.ok) return;
                const data = await res.json();
                this.state.history = data.images || [];
                this.renderHistoryStrip();
            } catch (e) {
                console.warn('[PhotoStudio] loadHistory error:', e);
            }
        },

        renderHistoryStrip() {
            const strip = document.getElementById('ps-strip-row');
            if (!strip) return;

            if (this.state.history.length === 0) {
                strip.innerHTML = '<span style="font-size:0.75rem; color:var(--text-tertiary); padding: 0.5rem 0;">No creations yet.</span>';
                return;
            }

            strip.innerHTML = this.state.history.map(item => `
                <div class="ps-strip-item" data-url="${item.url}" data-filename="${item.filename}" data-prompt="${item.prompt || ''}" title="${item.prompt || item.filename}">
                    <img src="${item.url}" alt="${item.filename}" loading="lazy">
                </div>
            `).join('');

            strip.querySelectorAll('.ps-strip-item').forEach(el => {
                el.addEventListener('click', () => {
                    const url = el.dataset.url;
                    const filename = el.dataset.filename;
                    const prompt = el.dataset.prompt;

                    this.displayGeneratedImage({ url, filename }, prompt);
                    const promptInput = document.getElementById('ps-prompt-input');
                    if (promptInput && prompt && prompt !== 'Generated Image') {
                        promptInput.value = prompt;
                    }
                });
            });
        }
    };

    document.addEventListener('panelLoaded', (e) => {
        if (e.detail && e.detail.tabName === 'photo') {
            PhotoStudio.init();
        }
    });

    if (document.getElementById('ps-generate-btn') || document.getElementById('ps-prompt-input')) {
        PhotoStudio.init();
    }

    if (typeof registerTabInit === 'function') {
        registerTabInit('photo', () => PhotoStudio.init());
    }

    window.PhotoStudio = PhotoStudio;
})();
