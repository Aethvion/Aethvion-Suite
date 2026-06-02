/**
 * Aethvion Suite — Audio Models View
 * Manages local TTS/STT models: install, load/unload, generate, voice cloning.
 */

const AudioModels = (() => {
    let _suggested = [];
    let _statuses  = {};   // model_id → status dict
    let _registered = new Set(); // model_ids registered in model_registry.json
    let _currentTab = 'tts';
    let _cloneModelId = null;
    let _cloneAudioB64 = null;
    let _defaultModel = null;
    let _defaultVoice = null;
    let _search = '';

    // Init
    async function init() {
        await refresh();
        _setupCloneDropzone();
        const searchEl = document.getElementById('audio-search-input');
        if (searchEl) {
            searchEl.oninput = (e) => {
                _search = e.target.value.toLowerCase().trim();
                _render();
            };
        }
    }

    async function refresh() {
        await Promise.all([_loadStatuses(), _loadSuggested()]);
        _render();
        if (typeof markPanelUpdated === 'function') markPanelUpdated('audio-models');
    }

    async function _loadStatuses() {
        try {
            const [modR, defR, regR] = await Promise.all([
                fetch('/api/audio/local/models'),
                fetch('/api/audio/local/models/defaults'),
                fetch('/api/audio/local/models/registry-status'),
            ]);
            if (modR.ok) {
                const d = await modR.json();
                _statuses = {};
                (d.models || []).forEach(m => { _statuses[m.id] = m; });
            }
            if (defR.ok) {
                const d = await defR.json();
                _defaultModel = d.model_id;
                _defaultVoice = d.voice_id;
            }
            if (regR.ok) {
                const d = await regR.json();
                _registered = new Set(d.registered || []);
            }
        } catch (e) { console.warn('Audio model status fetch failed:', e); }
    }

    async function _loadSuggested() {
        try {
            const r = await fetch('/api/audio/local/suggested');
            if (!r.ok) return;
            const d = await r.json();
            _suggested = d.audio_models || [];
        } catch (e) { console.warn('Suggested audio models fetch failed:', e); }
    }

    // Rendering
    function _matchesSearch(m) {
        if (!_search) return true;
        const hay = `${m.name} ${(m.tags || []).join(' ')} ${m.description || ''}`.toLowerCase();
        return hay.includes(_search);
    }

    function _render() {
        const ttsEl = document.getElementById('am-tts-cards');
        const sttEl = document.getElementById('am-stt-cards');
        if (!ttsEl || !sttEl) return;

        const tts = _suggested.filter(m => m.category === 'tts' && _matchesSearch(m));
        const stt = _suggested.filter(m => m.category === 'stt' && _matchesSearch(m));

        ttsEl.innerHTML = tts.map(m => _modelCard(m)).join('') || '<p class="empty-state">No TTS models configured.</p>';
        sttEl.innerHTML = stt.map(m => _modelCard(m)).join('') || '<p class="empty-state">No STT models configured.</p>';
    }

    function _modelCard(m) {
        const status = _statuses[m.id] || {};
        const installed = status.installed || false;
        const loaded    = status.loaded    || false;
        const device    = status.device    || '—';

        // Capability badges (compact)
        const capBadges = (m.capabilities || []).map(c =>
            `<span class="hub-tag" style="background:rgba(var(--primary-rgb),0.05); color:var(--primary);">${c.toUpperCase()}</span>`
        ).join('');

        // Status pill
        let statusBadge = `<span class="hub-status-badge">Not Installed</span>`;
        if (installed && loaded)   statusBadge = `<span class="hub-status-badge loaded">Active · ${device}</span>`;
        else if (installed)        statusBadge = `<span class="hub-status-badge installed">Ready</span>`;

        const isDefault = _defaultModel === m.id;
        const isRegistered = _registered.has(m.id);

        // Register button
        const registerBtn = installed
            ? `<button class="hub-action-btn secondary ${isRegistered ? 'success' : ''}" 
                onclick="AudioModels.registerToRegistry('${m.id}', this)"
                title="Add to system model registry"
                ${isRegistered ? 'disabled' : ''}>
                <i class="fas fa-${isRegistered ? 'check-circle' : 'plus-circle'}"></i>
                ${isRegistered ? 'Registered' : 'Register'}
            </button>`
            : '';

        // Action buttons
        let actions = '';
        if (!installed) {
            actions = `<button class="hub-action-btn" onclick="AudioModels.install('${m.id}', \`${m.install_packages}\`, this)">
                <i class="fas fa-download"></i> Install Model
            </button>`;
        } else if (!loaded) {
            let sizeSelect = '';
            if (m.model_sizes) {
                sizeSelect = `<select class="lm-filter-select" id="am-size-${m.id}" style="margin-right:0.5rem; height:32px; padding:0 0.5rem; font-size:0.75rem;">
                    ${m.model_sizes.map(s => `<option value="${s.id}" ${s.id === 'medium' ? 'selected' : ''}>${s.label}</option>`).join('')}
                </select>`;
            }
            actions = `<div style="display:flex; align-items:center;">${sizeSelect}<button class="hub-action-btn" onclick="AudioModels.load('${m.id}', this)">
                <i class="fas fa-play"></i> Load
            </button></div>${registerBtn}`;
        } else {
            actions = `
                <button class="hub-action-btn secondary" onclick="AudioModels.unload('${m.id}', this)">
                    <i class="fas fa-stop"></i> Stop
                </button>
                <button class="hub-action-btn ${isDefault ? '' : 'secondary'}" onclick="AudioModels.setDefault('${m.id}', this)" 
                        style="${isDefault ? 'background:#f59e0b; color:#000;' : ''}">
                    <i class="fas fa-star"></i> ${isDefault ? 'Main' : 'Set Main'}
                </button>
                ${registerBtn}`;
        }

        const testSection = loaded ? _testSection(m) : '';

        return `
        <div class="hub-card ${loaded ? 'active' : ''}" id="am-card-${m.id}" style="--brand-color: var(--primary);">
            <div class="hub-card-top">
                <div class="hub-model-icon"><i class="fas fa-wave-square"></i></div>
                ${statusBadge}
            </div>
            
            <div class="hub-model-info">
                <h3>${m.name} ${m.recommended ? '⭐' : ''}</h3>
                <p>${m.description}</p>
            </div>

            <div class="hub-tags">
                ${capBadges}
                <span class="hub-tag"><i class="fas fa-hdd" style="font-size:0.6rem;"></i> ${m.size_label}</span>
            </div>

            <div class="hub-card-footer" style="flex-wrap: wrap; gap: 0.5rem;">
                ${actions}
            </div>
            ${testSection}
        </div>`;
    }

    function _testSection(m) {
        if (m.category === 'stt') {
            return `<div class="am-test-section">
                <label class="am-test-label">Test Transcription</label>
                <div id="am-stt-drop-${m.id}" class="am-dropzone am-small-drop">
                    <i class="fas fa-microphone"></i>
                    <span>Drop audio or click to browse</span>
                    <input type="file" accept=".wav,.mp3,.ogg,.flac" onchange="AudioModels.testSTT('${m.id}', this)">
                </div>
                <div id="am-stt-result-${m.id}" class="am-test-result" style="display:none"></div>
            </div>`;
        }
        // TTS test
        const voiceOpts = _getVoiceOptions(m.id);
        return `<div class="am-test-section">
            <label class="am-test-label">Test Voice</label>
            <div class="am-test-row">
                <textarea id="am-test-text-${m.id}" class="am-test-textarea" rows="2" placeholder="Enter text to speak…">Hello, I am your local AI voice.</textarea>
                ${voiceOpts ? `<select class="setting-select am-voice-select" id="am-test-voice-${m.id}">${voiceOpts}</select>` : ''}
                <button class="action-btn accent" onclick="AudioModels.testTTS('${m.id}', this)">
                    <i class="fas fa-play-circle"></i> Speak
                </button>
            </div>
            <audio id="am-test-audio-${m.id}" controls style="display:none;margin-top:0.5rem;width:100%;"></audio>
        </div>`;
    }

    function _getVoiceOptions(modelId) {
        if (modelId === 'kokoro') {
            const voices = [
                ['af_heart','Heart (F)'],['af_bella','Bella (F)'],['af_nova','Nova (F)'],
                ['af_sky','Sky (F)'],['am_adam','Adam (M)'],['am_echo','Echo (M)'],
                ['am_michael','Michael (M)'],['bf_emma','Emma (F, GB)'],['bm_george','George (M, GB)'],
            ];
            return voices.map(([id, name]) => `<option value="${id}">${name}</option>`).join('');
        }
        if (modelId === 'vibevoice-realtime') {
            const voices = [
                ['en-Carter_man.pt', 'Carter (M)'],
                ['en-Davis_man.pt',  'Davis (M)'],
                ['en-Emma_woman.pt', 'Emma (F)'],
                ['en-Frank_man.pt',  'Frank (M)'],
                ['en-Grace_woman.pt','Grace (F)'],
                ['en-Mike_man.pt',   'Mike (M)'],
                ['in-Samuel_man.pt', 'Samuel (M · Indian)'],
            ];
            return voices.map(([id, name]) => `<option value="${id}">${name}</option>`).join('');
        }
        return '';
    }

    // Voices tab
    async function _renderVoices() {
        const selector = document.getElementById('am-voices-model-select');
        const list     = document.getElementById('am-voices-list');
        if (!selector || !list) return;

        // Models that support voice_cloning and are installed
        const clonable = _suggested.filter(m =>
            m.capabilities?.includes('voice_cloning') && (_statuses[m.id]?.installed || false)
        );

        if (!clonable.length) {
            selector.innerHTML = '';
            list.innerHTML = '<p class="empty-state">Install XTTS-v2 to use voice cloning.</p>';
            document.getElementById('am-clone-form').style.display = 'none';
            return;
        }

        document.getElementById('am-clone-form').style.display = '';
        selector.innerHTML = clonable.map(m =>
            `<button class="action-btn secondary ${_cloneModelId === m.id ? 'active' : ''}"
                onclick="AudioModels._selectVoiceModel('${m.id}')">${m.name}</button>`
        ).join('');

        if (!_cloneModelId) _cloneModelId = clonable[0].id;

        // Fetch voices for selected model
        try {
            const r = await fetch(`/api/audio/local/voices/${_cloneModelId}`);
            const d = await r.json();
            const voices = d.voices || [];
            if (!voices.length) {
                list.innerHTML = '<p class="empty-state">No cloned voices yet. Use the form below to create one.</p>';
                return;
            }
            list.innerHTML = voices.map(v => `
                <div class="hub-card" style="padding: 1rem; --hub-card-bg: rgba(52, 211, 153, 0.05);">
                    <div class="hub-card-top" style="margin-bottom: 0.5rem;">
                        <div class="hub-model-icon" style="width:32px; height:32px; font-size:0.9rem;"><i class="fas fa-microphone"></i></div>
                        <button class="hub-dl-del" onclick="AudioModels.deleteVoice('${v.id}', this)" title="Delete voice"
                                style="background:none; border:none; color:var(--text-tertiary); cursor:pointer;">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                    <div class="hub-model-info">
                        <h3 style="font-size:0.85rem; margin:0;">${v.name}</h3>
                        <p style="font-size:0.7rem;">${v.language.toUpperCase()} · ${v.gender}</p>
                    </div>
                </div>
            `).join('');
        } catch (e) {
            list.innerHTML = '<p class="empty-state">Could not load voices.</p>';
        }
    }

    function _selectVoiceModel(id) {
        _cloneModelId = id;
        _renderVoices();
    }

    // Actions
    async function install(modelId, packages, btn) {
        const card = document.getElementById(`am-card-${modelId}`);

        // Inject (or reuse) install log panel
        let logEl = card.querySelector('.am-install-log');
        if (!logEl) {
            logEl = document.createElement('div');
            logEl.className = 'am-install-log';
            logEl.innerHTML = `
                <div class="am-log-header">
                    <span class="am-log-title"><i class="fas fa-terminal"></i> Installing…</span>
                    <span class="am-log-pct">0%</span>
                </div>
                <div class="am-log-bar-wrap"><div class="am-log-bar"></div></div>
                <pre class="am-log-output"></pre>`;
            card.appendChild(logEl);
        }

        const logTitle  = logEl.querySelector('.am-log-title');
        const logPct    = logEl.querySelector('.am-log-pct');
        const logBar    = logEl.querySelector('.am-log-bar');
        const logOutput = logEl.querySelector('.am-log-output');

        // Reset state
        logTitle.innerHTML = '<i class="fas fa-terminal"></i> Installing…';
        logPct.textContent = '0%';
        logBar.style.width = '5%';
        logBar.className   = 'am-log-bar';
        logOutput.textContent = '';

        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Installing…';

        try {
            const resp = await fetch('/api/audio/local/install/stream', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({packages}),
            });

            const reader  = resp.body.getReader();
            const decoder = new TextDecoder();
            let   buffer  = '';
            let   lines   = 0;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, {stream: true});

                const parts = buffer.split('\n\n');
                buffer = parts.pop();

                for (const part of parts) {
                    if (!part.startsWith('data: ')) continue;
                    let msg;
                    try { msg = JSON.parse(part.slice(6)); } catch (_) { continue; }

                    if (msg.line !== undefined) {
                        logOutput.textContent += msg.line + '\n';
                        logOutput.scrollTop = logOutput.scrollHeight;
                        lines++;
                        const pct = Math.min(5 + lines * 1.5, 90);
                        logBar.style.width = pct + '%';
                        logPct.textContent = Math.round(pct) + '%';
                    } else if (msg.done) {
                        logBar.style.width = '100%';
                        logPct.textContent = '100%';
                        if (msg.success) {
                            logBar.classList.add('am-bar-done');
                            logTitle.innerHTML = '<i class="fas fa-check-circle" style="color:#34d399"></i> Installed';
                            showNotification(`${modelId} installed successfully`, 'success');
                            setTimeout(() => refresh(), 600);
                        } else {
                            logBar.classList.add('am-bar-fail');
                            logTitle.innerHTML = '<i class="fas fa-times-circle" style="color:#f87171"></i> Failed';
                            showNotification('Install failed — see log above', 'error');
                            btn.disabled = false;
                            btn.innerHTML = '<i class="fas fa-redo"></i> Retry';
                        }
                    }
                }
            }
        } catch (e) {
            showNotification('Install request failed', 'error');
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-download"></i> Install';
        }
    }

    async function load(modelId, btn) {
        const sizeEl = document.getElementById(`am-size-${modelId}`);
        const modelSize = sizeEl ? sizeEl.value : 'medium';
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading…';
        try {
            const r = await fetch('/api/audio/local/models/load', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({model_id: modelId, device: 'cuda', model_size: modelSize}),
            });
            const d = await r.json();
            if (d.success) {
                showNotification(`${modelId} loaded`, 'success');
                await refresh();
            } else {
                let msg = d.detail || 'Unknown error';
                // Surface numpy fix hint prominently
                if (msg.includes('numpy') || msg.includes('binary incompatibility')) {
                    msg = 'numpy version conflict — run: pip install "numpy<2"';
                }
                showNotification(`Load failed: ${msg}`, 'error');
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-play"></i> Load Model';
            }
        } catch (e) {
            showNotification('Load request failed', 'error');
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-play"></i> Load Model';
        }
    }

    async function registerToRegistry(modelId, btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        try {
            const r = await fetch('/api/audio/local/models/register-to-registry', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({model_id: modelId}),
            });
            const d = await r.json();
            if (d.success) {
                _registered.add(modelId);
                const caps = (d.capabilities || []).join(', ');
                showNotification(`${modelId} registered (${caps})`, 'success');
                // Update just this button without full re-render
                btn.innerHTML = '<i class="fas fa-check-circle"></i> Registered';
                btn.classList.remove('secondary');
                btn.classList.add('success');
                // Immediately refresh Misaka Cipher voice dropdown
                if (typeof loadMisakaTTSModels === 'function') loadMisakaTTSModels();
            } else {
                showNotification(`Registration failed: ${d.detail || 'Error'}`, 'error');
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-plus-circle"></i> Register';
            }
        } catch (e) {
            showNotification('Registration request failed', 'error');
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-plus-circle"></i> Register';
        }
    }

    async function setDefault(modelId, btn) {
        try {
            await fetch('/api/audio/local/models/set-default', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({model_id: modelId}),
            });
            _defaultModel = modelId;
            showNotification(`${modelId} set as default TTS`, 'success');
            _render();
            // Notify Misaka Cipher to refresh its model list
            if (typeof loadMisakaTTSModels === 'function') loadMisakaTTSModels();
        } catch (e) {
            showNotification('Could not save default', 'error');
        }
    }

    async function unload(modelId, btn) {
        btn.disabled = true;
        try {
            await fetch('/api/audio/local/models/unload', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({model_id: modelId}),
            });
            showNotification(`${modelId} unloaded`, 'success');
            await refresh();
        } catch (e) {
            showNotification('Unload failed', 'error');
            btn.disabled = false;
        }
    }

    async function testTTS(modelId, btn) {
        const text    = document.getElementById(`am-test-text-${modelId}`)?.value?.trim();
        const voiceEl = document.getElementById(`am-test-voice-${modelId}`);
        const voice   = voiceEl ? voiceEl.value : null;
        if (!text) return;

        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        try {
            const r = await fetch('/api/audio/local/generate', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({text, model_id: modelId, voice_id: voice}),
            });
            const d = await r.json();
            if (d.success) {
                const audioEl = document.getElementById(`am-test-audio-${modelId}`);
                audioEl.src = d.audio;
                audioEl.style.display = 'block';
                audioEl.play();
            } else {
                showNotification(`TTS failed: ${d.detail || 'Error'}`, 'error');
            }
        } catch (e) {
            showNotification('TTS request failed', 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-play-circle"></i> Speak';
        }
    }

    async function testSTT(modelId, input) {
        const file = input.files[0];
        if (!file) return;
        const resultEl = document.getElementById(`am-stt-result-${modelId}`);
        resultEl.style.display = 'block';
        resultEl.textContent = 'Transcribing…';

        const reader = new FileReader();
        reader.onload = async (e) => {
            const b64 = e.target.result.split(',')[1];
            try {
                const r = await fetch('/api/audio/local/transcribe', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({audio_b64: b64, model_id: modelId}),
                });
                const d = await r.json();
                resultEl.textContent = d.success ? d.text : `Error: ${d.detail}`;
            } catch (e) {
                resultEl.textContent = 'Request failed.';
            }
        };
        reader.readAsDataURL(file);
    }

    async function cloneVoice() {
        if (!_cloneModelId) { showNotification('Select a model first', 'error'); return; }
        if (!_cloneAudioB64) { showNotification('Upload reference audio first', 'error'); return; }
        const name = document.getElementById('am-clone-name')?.value?.trim();
        const lang = document.getElementById('am-clone-lang')?.value || 'en';
        if (!name) { showNotification('Enter a voice name', 'error'); return; }

        try {
            const r = await fetch('/api/audio/local/voices/clone', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({
                    model_id: _cloneModelId,
                    reference_audio_b64: _cloneAudioB64,
                    name, language: lang,
                }),
            });
            const d = await r.json();
            if (d.success) {
                showNotification(`Voice "${name}" cloned successfully`, 'success');
                _cloneAudioB64 = null;
                document.getElementById('am-clone-name').value = '';
                document.getElementById('am-clone-filename').textContent = '';
                _renderVoices();
            } else {
                showNotification(`Clone failed: ${d.detail}`, 'error');
            }
        } catch (e) {
            showNotification('Clone request failed', 'error');
        }
    }

    async function deleteVoice(voiceId, btn) {
        if (!confirm(`Delete voice "${voiceId}"?`)) return;
        btn.disabled = true;
        try {
            await fetch('/api/audio/local/voices', {
                method: 'DELETE',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({model_id: _cloneModelId, voice_id: voiceId}),
            });
            showNotification('Voice deleted', 'success');
            _renderVoices();
        } catch (e) {
            showNotification('Delete failed', 'error');
            btn.disabled = false;
        }
    }

    // Tab switching
    function switchTab(tab, btn) {
        _currentTab = tab;
        ['tts','stt','voices'].forEach(t => {
            document.getElementById(`am-section-${t}`).style.display = t === tab ? '' : 'none';
        });
        document.querySelectorAll('.am-tab-btn').forEach(b =>
            b.classList.toggle('active', b.dataset.amtab === tab)
        );
        if (tab === 'voices') _renderVoices();
    }

    // Clone dropzone
    function _setupCloneDropzone() {
        const dz   = document.getElementById('am-clone-dropzone');
        const inp  = document.getElementById('am-clone-file');
        const name = document.getElementById('am-clone-filename');
        if (!dz || !inp) return;

        dz.addEventListener('click', () => inp.click());
        dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag-over'); });
        dz.addEventListener('dragleave', () => dz.classList.remove('drag-over'));
        dz.addEventListener('drop', e => {
            e.preventDefault(); dz.classList.remove('drag-over');
            if (e.dataTransfer.files[0]) _readCloneFile(e.dataTransfer.files[0], name);
        });
        inp.addEventListener('change', () => {
            if (inp.files[0]) _readCloneFile(inp.files[0], name);
        });
    }

    function _readCloneFile(file, nameEl) {
        nameEl.textContent = file.name;
        const reader = new FileReader();
        reader.onload = e => { _cloneAudioB64 = e.target.result.split(',')[1]; };
        reader.readAsDataURL(file);
    }

    // Tab init registration
    if (typeof registerTabInit === 'function') {
        registerTabInit('audio-models', init);
    }

    // Load when the partial is first injected
    document.addEventListener('panelLoaded', function (e) {
        if (e.detail.panelId === 'audio-models-panel') init();
    });

    return { init, refresh, switchTab, install, load, unload, registerToRegistry, setDefault, testTTS, testSTT, cloneVoice, deleteVoice, _selectVoiceModel };
})();
