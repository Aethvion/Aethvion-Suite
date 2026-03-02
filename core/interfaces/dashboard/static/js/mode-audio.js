// Misaka Cipher - Audio Studio Mode
// Handles interactions with the Audio Generation/Processing UI

let currentAudioInputBase64 = null;

function setupAudioDropzone(dropzoneId, inputId, previewId, filenameId, base64Callback) {
    const dropzone = document.getElementById(dropzoneId);
    const input = document.getElementById(inputId);
    const preview = document.getElementById(previewId);
    const filenameLabel = document.getElementById(filenameId);
    const dropzoneText = dropzone.querySelector('.dropzone-text');

    if (!dropzone || !input) return;

    dropzone.onclick = () => input.click();

    dropzone.ondragover = (e) => { e.preventDefault(); dropzone.style.borderColor = 'var(--primary)'; };
    dropzone.ondragleave = (e) => { e.preventDefault(); dropzone.style.borderColor = 'var(--border)'; };

    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.style.borderColor = 'var(--primary)';
    });

    dropzone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropzone.style.borderColor = 'var(--border)';
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.style.borderColor = 'var(--border)';
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            handleAudioFile(e.dataTransfer.files[0]);
        }
    });

    input.onchange = (e) => {
        if (e.target.files && e.target.files[0]) {
            handleAudioFile(e.target.files[0]);
        }
    };

    function handleAudioFile(file) {
        if (!file.type.startsWith('audio/')) {
            showNotification('Please upload an audio file.', 'error');
            return;
        }
        const reader = new FileReader();
        reader.onload = (e) => {
            preview.style.display = 'block';
            filenameLabel.textContent = file.name;
            dropzoneText.style.display = 'none';
            base64Callback(e.target.result);
        };
        reader.readAsDataURL(file);
    }
}

function initializeAudioStudio() {
    setupAudioDropzone('audio-input-dropzone', 'audio-input-file', 'audio-input-preview', 'audio-input-filename', (b64) => currentAudioInputBase64 = b64);

    const modeToggles = document.querySelectorAll('input[name="audio_mode"]');
    modeToggles.forEach(r => r.addEventListener('change', () => {
        const mode = document.querySelector('input[name="audio_mode"]:checked').value;
        const uploadGroup = document.getElementById('audio-upload-group');
        const promptInput = document.getElementById('audio-prompt-input');

        // Update UI based on mode
        uploadGroup.style.display = (mode === 'stt' || mode === 'edit') ? 'block' : 'none';

        if (mode === 'tts') {
            promptInput.placeholder = "Enter text to convert to speech...";
        } else if (mode === 'stt') {
            promptInput.placeholder = "Upload audio to transcribe...";
            promptInput.value = ""; // Clear for STT as it generates text
        } else if (mode === 'music') {
            promptInput.placeholder = "Describe the music style, mood, or instruments...";
        } else {
            promptInput.placeholder = "Enter prompt or instructions...";
        }

        loadAudioModels(); // Re-filter models
    }));

    const processBtn = document.getElementById('process-audio-btn');
    const loadingOverlay = document.getElementById('audio-loading-overlay');
    const promptInput = document.getElementById('audio-prompt-input');
    const resultArea = document.getElementById('audio-result-area');

    if (processBtn) {
        processBtn.onclick = async () => {
            const prompt = promptInput?.value.trim() || '';
            const mode = document.querySelector('input[name="audio_mode"]:checked').value;

            // Validate
            if ((mode === 'tts' || mode === 'music') && !prompt) {
                showNotification('Please enter a prompt or text.', 'warning');
                return;
            }
            if ((mode === 'stt' || mode === 'edit') && !currentAudioInputBase64) {
                showNotification('Please upload an audio file for this mode.', 'warning');
                return;
            }

            const checkedModels = Array.from(document.querySelectorAll('.audio-model-checkbox:checked')).map(cb => {
                return { key: cb.value, provider: cb.dataset.provider };
            });

            if (checkedModels.length === 0) {
                showNotification('Please select at least one model.', 'warning');
                return;
            }

            // Show loading
            loadingOverlay.style.display = 'flex';
            processBtn.disabled = true;
            processBtn.textContent = 'PROCESSING...';
            resultArea.style.display = 'none';

            const m = checkedModels[0]; // Currently just handle first selected model for simplicity

            try {
                const response = await fetch('/api/audio/process', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        prompt: prompt,
                        model: m.key,
                        mode: mode,
                        input_audio: currentAudioInputBase64
                    })
                });

                const data = await response.json();
                loadingOverlay.style.display = 'none';
                processBtn.disabled = false;
                processBtn.textContent = 'PROCESS';

                if (data.success) {
                    resultArea.style.display = 'block';
                    const player = document.getElementById('audio-result-player');
                    const title = document.getElementById('audio-result-title');

                    if (mode === 'stt') {
                        title.textContent = 'Transcription Result';
                        promptInput.value = data.text; // Show text in the prompt area
                        player.style.display = 'none';
                    } else {
                        title.textContent = mode === 'music' ? 'Generated Music' : 'Generated Speech';
                        // Handle both data URI 'audio' and URL 'audio_url'
                        player.src = data.audio || data.audio_url;
                        player.style.display = 'block';
                        document.getElementById('audio-result-format').textContent = data.format || (data.audio ? 'MP3' : 'WAV');
                    }

                    showNotification('Audio process completed.', 'success');
                } else {
                    showNotification(data.error || 'Processing failed.', 'error');
                }
            } catch (err) {
                loadingOverlay.style.display = 'none';
                processBtn.disabled = false;
                processBtn.textContent = 'PROCESS';
                console.error(err);
                showNotification('Error processing audio: ' + err.message, 'error');
            }
        };
    }

    loadAudioModels();
}

async function loadAudioModels() {
    const checklist = document.getElementById('audio-model-checklist');
    if (!checklist) return;

    if (typeof _registryData === 'undefined' || !_registryData) {
        if (typeof loadProviderSettings === 'function') await loadProviderSettings();
    }
    if (typeof _registryData === 'undefined' || !_registryData || !_registryData.providers) return;

    const mode = document.querySelector('input[name="audio_mode"]:checked').value;
    let html = '';
    const models = [];

    for (const [providerName, config] of Object.entries(_registryData.providers)) {
        if (!config.models) continue;
        for (const [key, info] of Object.entries(config.models)) {
            const caps = (info.capabilities || []).map(c => c.toUpperCase());
            if (caps.includes('AUDIO')) {
                const audioConfig = info.audio_config || {};

                // Basic filtering by mode if config specifies
                if (mode === 'stt' && audioConfig.supports_stt === false) continue;
                if (mode === 'tts' && audioConfig.supports_tts === false) continue;

                models.push({
                    key: key,
                    id: info.id || key,
                    provider: providerName,
                    name: `${providerName}: ${info.id || key}`
                });
            }
        }
    }

    if (models.length === 0) {
        html = '<div style="color:var(--text-secondary); font-size:0.85em; padding: 10px; text-align: center;">No audio models found.</div>';
    } else {
        models.forEach((m, idx) => {
            html += `<label class="checklist-item" style="display:flex; align-items:center; gap:8px; padding:6px 10px; cursor:pointer; font-size: 0.85rem; border-bottom: 1px solid var(--border-light);">
                <input type="radio" name="selected_audio_model" class="audio-model-checkbox" value="${m.key}" data-provider="${m.provider}" ${idx === 0 ? 'checked' : ''}>
                <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${m.name}</span>
            </label>`;
        });
    }

    checklist.innerHTML = html;
}

// Register initialization
if (typeof registerTabInit === 'function') {
    registerTabInit('audio', initializeAudioStudio);
} else {
    // Fallback if core logic hasn't loaded yet
    window.addEventListener('load', () => {
        if (typeof registerTabInit === 'function') {
            registerTabInit('audio', initializeAudioStudio);
        }
    });
}
