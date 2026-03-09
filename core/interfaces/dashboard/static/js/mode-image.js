// Misaka Cipher - Image Studio Mode
// Handles interactions with the Image Generation UI and APIs

// Store base64 data outside
let currentRefImageBase64 = null;
let currentMaskImageBase64 = null;

function setupImageDropzone(dropzoneId, inputId, previewId, clearId, base64Callback) {
    const dropzone = document.getElementById(dropzoneId);
    const input = document.getElementById(inputId);
    const preview = document.getElementById(previewId);
    const clearBtn = document.getElementById(clearId);
    if (!dropzone || !input) return;

    dropzone.addEventListener('click', () => input.click());

    // Drag/drop events...
    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.style.borderColor = 'var(--accent-color)'; });
    dropzone.addEventListener('dragleave', (e) => { e.preventDefault(); dropzone.style.borderColor = 'var(--border-color)'; });
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.style.borderColor = 'var(--border-color)';
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            handleFile(e.dataTransfer.files[0]);
        }
    });

    input.addEventListener('change', (e) => {
        if (e.target.files && e.target.files[0]) {
            handleFile(e.target.files[0]);
        }
    });

    clearBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        preview.src = '';
        preview.style.display = 'none';
        clearBtn.style.display = 'none';
        input.value = '';
        base64Callback(null);
    });

    function handleFile(file) {
        if (!file.type.startsWith('image/')) return;
        const reader = new FileReader();
        reader.onload = (e) => {
            preview.src = e.target.result;
            preview.style.display = 'block';
            clearBtn.style.display = 'block';
            base64Callback(e.target.result);
        };
        reader.readAsDataURL(file);
    }
}

function initializeImageStudio() {
    setupImageDropzone('image-ref-dropzone', 'image-ref-input', 'image-ref-preview', 'image-ref-clear', (b64) => currentRefImageBase64 = b64);
    setupImageDropzone('mask-ref-dropzone', 'mask-ref-input', 'mask-ref-preview', 'mask-ref-clear', (b64) => currentMaskImageBase64 = b64);

    const modeToggles = document.querySelectorAll('input[name="image_mode"]');
    modeToggles.forEach(r => r.addEventListener('change', () => {
        const mode = document.querySelector('input[name="image_mode"]:checked').value;
        document.getElementById('image-upload-group').style.display = (mode === 'edit' || mode === 'upscale' || mode === 'expand') ? 'block' : 'none';
        document.getElementById('mask-upload-group').style.display = (mode === 'expand' || mode === 'edit') ? 'block' : 'none';
        loadImageModels(); // Re-filter models
    }));

    const generateBtn = document.getElementById('generate-image-btn');
    const loadingOverlay = document.getElementById('image-loading-overlay');
    const promptInput = document.getElementById('image-prompt-input');

    if (generateBtn) {
        generateBtn.addEventListener('click', async () => {
            const prompt = promptInput?.value.trim() || '';
            const mode = document.querySelector('input[name="image_mode"]:checked').value;

            // Validate
            if (mode === 'generate' && !prompt) {
                alert('Please enter a prompt first.'); return;
            }
            if ((mode === 'edit' || mode === 'upscale' || mode === 'expand') && !currentRefImageBase64) {
                alert('Please upload a reference image for this mode.'); return;
            }

            const checkedModels = Array.from(document.querySelectorAll('.image-model-checkbox:checked')).map(cb => {
                return { key: cb.value, provider: cb.dataset.provider };
            });

            if (checkedModels.length === 0) {
                alert('Please select at least one model.'); return;
            }

            // Show loading
            if (loadingOverlay) loadingOverlay.style.display = 'flex';
            generateBtn.disabled = true;
            generateBtn.textContent = 'GENERATING...';

            // Gather Promises
            const promises = checkedModels.map(async (m) => {
                const safeKey = m.key.replace(/[^a-zA-Z0-9]/g, '');
                const aspectRatio = document.getElementById(`ar-${safeKey}`)?.value;
                const customAr = document.getElementById(`ar-custom-${safeKey}`)?.value;
                const negPrompt = document.getElementById(`neg-${safeKey}`)?.value;
                const seed = document.getElementById(`seed-${safeKey}`)?.value;
                const quality = document.getElementById(`qual-${safeKey}`)?.value;

                return fetch('/api/image/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        prompt: prompt,
                        model: m.key,
                        action: mode,
                        input_image: currentRefImageBase64,
                        mask_image: currentMaskImageBase64,
                        n: 1,
                        aspect_ratio: aspectRatio === 'custom' ? customAr : aspectRatio,
                        negative_prompt: negPrompt,
                        seed: seed ? parseInt(seed) : null,
                        quality: quality || "standard"
                    })
                }).then(res => res.json()).then(data => ({ model: m.key, data }));
            });

            try {
                const results = await Promise.all(promises);
                if (loadingOverlay) loadingOverlay.style.display = 'none';
                generateBtn.disabled = false;
                generateBtn.textContent = 'GENERATE';

                const viewer = document.getElementById('image-viewer-container');
                const emptyState = viewer.querySelector('.empty-state-viewer');
                if (emptyState) emptyState.style.display = 'none';

                // Clear previous ALL results
                viewer.querySelectorAll('.generated-result-container').forEach(el => el.remove());

                results.forEach(res => {
                    const data = res.data;
                    if (data.success && data.images && data.images.length > 0) {
                        data.images.forEach(imgData => {
                            const container = document.createElement('div');
                            container.className = 'generated-result-container';
                            container.style.display = 'flex';
                            container.style.flexDirection = 'column';
                            container.style.alignItems = 'center';
                            container.style.gap = '1rem';
                            container.style.width = '100%';
                            container.style.marginBottom = '2rem'; // Extra margin for multi-images

                            const img = document.createElement('img');
                            img.src = imgData.url;
                            img.className = 'generated-image-preview';
                            img.style.maxWidth = '100%';
                            img.style.maxHeight = '80vh';
                            img.style.objectFit = 'contain';
                            img.style.borderRadius = '8px';
                            img.style.boxShadow = '0 0 20px rgba(0,0,0,0.5)';

                            const meta = document.createElement('div');
                            meta.className = 'image-meta';
                            meta.innerHTML = `<span style="color:var(--text-secondary); font-size:0.9em;">Model: ${res.model} | Saved to: ${imgData.filename}</span>`;

                            container.appendChild(img);
                            container.appendChild(meta);
                            viewer.appendChild(container);
                        });
                    } else {
                        const err = document.createElement('div');
                        err.style.color = 'var(--error-color)';
                        err.textContent = `Model ${res.model} failed: ${data.error || 'Unknown error'}`;
                        viewer.appendChild(err);
                    }
                });
            } catch (err) {
                if (loadingOverlay) loadingOverlay.style.display = 'none';
                generateBtn.disabled = false;
                generateBtn.textContent = 'GENERATE';
                console.error(err);
                alert('Error generating images: ' + err.message);
            }
        });
    }

    // Load models
    loadImageModels();
}

async function loadImageModels() {
    const checklist = document.getElementById('image-model-checklist');
    if (!checklist) return;

    if (typeof _registryData === 'undefined' || !_registryData) {
        if (typeof loadProviderSettings === 'function') await loadProviderSettings();
    }
    if (typeof _registryData === 'undefined' || !_registryData || !_registryData.providers) return;

    const mode = document.querySelector('input[name="image_mode"]:checked').value;
    let html = '';
    const models = [];

    for (const [providerName, config] of Object.entries(_registryData.providers)) {
        if (!config.models) continue;
        for (const [key, info] of Object.entries(config.models)) {
            const caps = (info.capabilities || []).map(c => c.toLowerCase());
            if (caps.includes('image') || caps.includes('image_generation')) {
                const imgConfig = info.image_config || {};

                // Filter by mode
                if (mode === 'edit' && !imgConfig.supports_edit) continue;
                if (mode === 'upscale' && !imgConfig.supports_upscale) continue;
                if (mode === 'expand' && !imgConfig.supports_expand) continue;

                models.push({
                    key: key,
                    id: info.id || key,
                    provider: providerName,
                    name: `${providerName}: ${info.id || key}`,
                    image_config: imgConfig
                });
            }
        }
    }

    if (models.length === 0) {
        html = '<div style="color:var(--text-secondary); font-size:0.9em; padding: 0.5rem 0;">No models support this mode.</div>';
    } else {
        models.forEach((m, idx) => {
            html += `<label class="checklist-item" style="display:block; padding:0.25rem 0; cursor:pointer;">
                <input type="checkbox" class="image-model-checkbox" value="${m.key}" data-provider="${m.provider}" ${idx === 0 ? 'checked' : ''}>
                ${m.name}
            </label>`;
        });
    }

    checklist.innerHTML = html;

    // Bind events
    document.querySelectorAll('.image-model-checkbox').forEach(cb => {
        cb.addEventListener('change', updateImageStudioControls);
    });

    // Initial update
    updateImageStudioControls();
}

function updateImageStudioControls() {
    const configContainer = document.getElementById('image-model-configs');
    if (!configContainer) return;

    configContainer.innerHTML = ''; // Clear existing

    if (typeof _registryData === 'undefined' || !_registryData || !_registryData.providers) return;

    const checkboxes = document.querySelectorAll('.image-model-checkbox:checked');
    if (checkboxes.length === 0) return;

    checkboxes.forEach(cb => {
        const selectedKey = cb.value;
        const providerName = cb.dataset.provider;
        const modelInfo = _registryData.providers[providerName]?.models[selectedKey];
        if (!modelInfo) return;

        const config = modelInfo.image_config || {};
        const safeKey = selectedKey.replace(/[^a-zA-Z0-9]/g, '');

        // Build panel
        const panel = document.createElement('div');
        panel.className = 'model-config-panel';
        panel.style.background = 'var(--panel-bg)';
        panel.style.padding = '0.75rem';
        panel.style.borderRadius = '4px';
        panel.style.border = '1px solid var(--border-color)';
        panel.style.marginBottom = '1rem';

        // Title block
        let html = `<div style="font-weight:600; font-size:0.85em; margin-bottom:0.5rem; color:var(--text-secondary); border-bottom:1px solid var(--border-color); padding-bottom:0.25rem;">${selectedKey}</div>`;

        // Aspect Ratios
        if (config.aspect_ratios && config.aspect_ratios.length > 0) {
            const options = config.aspect_ratios.map(r => `<option value="${r}">${r}</option>`).join('');
            html += `
                <div class="control-group" style="margin-top: 0.5rem;">
                    <label style="font-size:0.8em;">Aspect Ratio</label>
                    <select class="term-select" style="width:100%; font-size:0.85em;" id="ar-${safeKey}">
                        ${options}
                    </select>
                    <div id="ar-custom-container-${safeKey}" style="display:none; margin-top:0.25rem;">
                        <input type="text" class="term-input" style="font-size:0.85em;" id="ar-custom-${safeKey}" placeholder="e.g. 21:9">
                    </div>
                </div>
            `;
        }

        // Negative Prompt
        if (config.supports_negative_prompt) {
            html += `
                <div class="control-group" style="margin-top: 0.5rem;">
                    <label style="font-size:0.8em;">Negative Prompt</label>
                    <input type="text" class="term-input" style="font-size:0.85em;" id="neg-${safeKey}" placeholder="Low quality...">
                </div>
            `;
        }

        // Seed
        if (config.supports_seed) {
            html += `
                <div class="control-group" style="margin-top: 0.5rem;">
                    <label style="font-size:0.8em;">Seed (Optional)</label>
                    <input type="number" class="term-input" style="font-size:0.85em;" id="seed-${safeKey}" placeholder="Random">
                </div>
            `;
        }

        // Quality
        if (config.quality_options && config.quality_options.length > 1) {
            const options = config.quality_options.map(q => `<option value="${q}">${q}</option>`).join('');
            html += `
                <div class="control-group" style="margin-top: 0.5rem;">
                    <label style="font-size:0.8em;">Quality</label>
                    <select class="term-select" style="width:100%; font-size:0.85em;" id="qual-${safeKey}">
                        ${options}
                    </select>
                </div>
            `;
        }

        panel.innerHTML = html;
        configContainer.appendChild(panel);

        // Bind custom AR if it exists
        const arSelect = document.getElementById(`ar-${safeKey}`);
        const customContainer = document.getElementById(`ar-custom-container-${safeKey}`);
        if (arSelect && customContainer) {
            arSelect.onchange = () => {
                customContainer.style.display = arSelect.value === 'custom' ? 'block' : 'none';
            };
        }
    });
}

if (typeof registerTabInit === 'function') {
    registerTabInit('image', initializeImageStudio);
}
