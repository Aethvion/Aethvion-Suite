/**
 * Aethvion Suite — Global Voice Library View (Library > Voice Library)
 * Browse voices across all TTS engines, preview with custom sample text,
 * manage global Voice Presets, and clone custom voices.
 */

const VoiceLibrary = (() => {
    let _models = [];
    let _presets = [];
    let _currentTab = 'voices';
    let _cloneAudioB64 = null;
    let _activeAudio = null;

    function _esc(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    async function init() {
        await refresh();
        _setupCloneDropzone();
    }

    async function refresh() {
        try {
            const res = await fetch('/api/audio/local/library');
            if (!res.ok) throw new Error('Failed to load voice library');
            const data = await res.json();
            _models = data.models || [];
            _presets = data.presets || [];

            if (window.AethvionVoice) {
                window.AethvionVoice.loadLibrary(true).catch(() => {});
            }

            _populateFilters();
            _renderStats();
            _renderVoices();
            _renderPresets();
            _renderCloning();
            if (typeof markPanelUpdated === 'function') markPanelUpdated('voice-library');
        } catch (e) {
            console.error('[VoiceLibrary] Refresh failed:', e);
            const vc = document.getElementById('vl-voices-container');
            if (vc) vc.innerHTML = `<p class="empty-state">Could not load Voice Library: ${_esc(e.message)}</p>`;
        }
    }

    function _renderStats() {
        const totalVoices = _models.reduce((acc, m) => acc + (m.voices?.length || 0), 0);
        const voicesEl = document.getElementById('vl-stat-voices');
        const presetsEl = document.getElementById('vl-stat-presets');
        if (voicesEl) voicesEl.textContent = totalVoices;
        if (presetsEl) presetsEl.textContent = _presets.length;
    }

    function _populateFilters() {
        const engineSel = document.getElementById('vl-engine-filter');
        if (engineSel) {
            const current = engineSel.value || 'all';
            engineSel.innerHTML = `<option value="all">Engine: All (${_models.length})</option>` +
                _models.map(m => `<option value="${_esc(m.id)}">${_esc(m.name)} (${m.voices?.length || 0})</option>`).join('');
            if ([...engineSel.options].some(o => o.value === current)) engineSel.value = current;
        }

        const presetModelSel = document.getElementById('vl-new-preset-model');
        if (presetModelSel) {
            const cur = presetModelSel.value || (_models[0]?.id || 'kokoro');
            presetModelSel.innerHTML = _models.map(m =>
                `<option value="${_esc(m.id)}">${_esc(m.name)}${m.installed ? ' (Ready)' : ''}</option>`
            ).join('');
            if ([...presetModelSel.options].some(o => o.value === cur)) presetModelSel.value = cur;
            onPresetModelChange();
        }
    }

    function onPresetModelChange() {
        const modelId = document.getElementById('vl-new-preset-model')?.value;
        const voiceSel = document.getElementById('vl-new-preset-voice');
        if (!voiceSel) return;
        const mod = _models.find(m => m.id === modelId) || _models[0];
        const voices = mod?.voices || [];
        voiceSel.innerHTML = voices.map(v =>
            `<option value="${_esc(v.id)}">${_esc(v.name)} (${_esc((v.language || 'en').toUpperCase())} · ${_esc(v.gender || 'neutral')})</option>`
        ).join('');
    }

    function onFilterChange() {
        _renderVoices();
    }

    function _renderVoices() {
        const container = document.getElementById('vl-voices-container');
        if (!container) return;

        const q = (document.getElementById('vl-search-input')?.value || '').toLowerCase().trim();
        const engineFilter = document.getElementById('vl-engine-filter')?.value || 'all';
        const genderFilter = document.getElementById('vl-gender-filter')?.value || 'all';

        const sectionsHtml = [];

        for (const mod of _models) {
            if (engineFilter !== 'all' && mod.id !== engineFilter) continue;

            const matchingVoices = (mod.voices || []).filter(v => {
                if (genderFilter !== 'all' && (v.gender || 'neutral').toLowerCase() !== genderFilter) return false;
                if (q) {
                    const hay = `${v.name} ${v.id} ${v.language || ''} ${mod.name}`.toLowerCase();
                    if (!hay.includes(q)) return false;
                }
                return true;
            });

            if (!matchingVoices.length) continue;

            const statusBadge = mod.is_cloud
                ? `<span class="hub-status-badge installed" style="margin-left:0.5rem;">Cloud Ready</span>`
                : mod.loaded
                    ? `<span class="hub-status-badge loaded" style="margin-left:0.5rem;">Loaded (${_esc(mod.device || 'gpu')})</span>`
                    : mod.installed
                        ? `<span class="hub-status-badge installed" style="margin-left:0.5rem;">Installed</span>`
                        : `<span class="hub-status-badge" style="margin-left:0.5rem; cursor:pointer;" onclick="switchMainTab('audio-models')" title="Click to install in Model Hub">Not Installed →</span>`;

            const rows = matchingVoices.map(v => {
                const g = (v.gender || 'neutral').toLowerCase();
                return `
                <div class="vl-row-card">
                    <!-- Column 1: Voice Name & ID -->
                    <div class="vl-row-identity">
                        <div class="vl-voice-icon ${_esc(g)}">
                            <i class="fas fa-waveform-lines"></i>
                        </div>
                        <div style="min-width:0;">
                            <div style="display:flex; align-items:center; gap:0.55rem; flex-wrap:wrap;">
                                <h3 class="vl-row-title">${_esc(v.name)}</h3>
                                <span class="vl-row-id">${_esc(v.id)}</span>
                            </div>
                        </div>
                    </div>

                    <!-- Column 2: Engine, Gender & Language Badges -->
                    <div class="vl-voice-meta">
                        <span class="vl-badge" style="color:var(--primary);">${_esc(mod.name)}</span>
                        <span class="vl-badge ${_esc(g)}">${_esc(g)}</span>
                        <span class="vl-badge">${_esc((v.language || 'en').toUpperCase())}</span>
                        ${v.cloned ? `<span class="vl-badge cloned"><i class="fas fa-dna"></i> Cloned</span>` : ''}
                    </div>

                    <!-- Column 3: Actions -->
                    <div class="vl-row-actions">
                        <button class="hub-action-btn" style="height:32px; padding:0 0.85rem; font-size:0.76rem;"
                                onclick="VoiceLibrary.previewVoice('${_esc(mod.id)}', '${_esc(v.id)}', this)">
                            <i class="fas fa-play"></i> Preview Voice
                        </button>
                        <button class="hub-action-btn secondary" style="height:32px; padding:0 0.7rem; font-size:0.76rem;"
                                title="Save this voice as a global preset"
                                onclick="VoiceLibrary.quickSavePreset('${_esc(mod.id)}', '${_esc(v.id)}', '${_esc(v.name)}', '${_esc(v.language || 'en')}', '${_esc(v.gender || 'neutral')}')">
                            <i class="fas fa-bookmark"></i> Save Preset
                        </button>
                    </div>
                </div>`;
            }).join('');

            sectionsHtml.push(`
                <section class="hub-provider-section" style="margin-bottom:1.65rem;">
                    <div class="hub-provider-hd" style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.65rem;">
                        <div style="display:flex; align-items:center; gap:0.5rem;">
                            <div class="hub-provider-dot" style="--brand-color: var(--primary);"></div>
                            <h2 class="hub-provider-name">${_esc(mod.name)}</h2>
                            ${statusBadge}
                        </div>
                        <span style="font-size:0.75rem; color:var(--text-tertiary);">${matchingVoices.length} voice${matchingVoices.length === 1 ? '' : 's'}</span>
                    </div>
                    <div class="vl-list">${rows}</div>
                </section>
            `);
        }

        container.innerHTML = sectionsHtml.length
            ? sectionsHtml.join('')
            : `<p class="empty-state">No voices match your current filters.</p>`;
    }

    function _renderPresets() {
        const grid = document.getElementById('vl-presets-grid');
        if (!grid) return;

        if (!_presets.length) {
            grid.innerHTML = `<p class="empty-state">No saved presets yet. Create one above!</p>`;
            return;
        }

        grid.innerHTML = _presets.map(p => {
            const mod = _models.find(m => m.id === p.model_id);
            const modName = mod ? mod.name : p.model_id;
            return `
            <div class="vl-row-card">
                <div class="vl-row-identity">
                    <div class="vl-voice-icon">
                        <i class="fas fa-bookmark"></i>
                    </div>
                    <div style="min-width:0;">
                        <div style="display:flex; align-items:center; gap:0.55rem; flex-wrap:wrap;">
                            <h3 class="vl-row-title">${_esc(p.name)}</h3>
                            <span class="vl-row-id">${_esc(p.voice_id)}</span>
                        </div>
                        ${p.description ? `<p style="margin:0.18rem 0 0; font-size:0.76rem; color:var(--text-secondary);">${_esc(p.description)}</p>` : ''}
                    </div>
                </div>
                <div class="vl-voice-meta">
                    <span class="vl-badge" style="color:var(--primary);">${_esc(modName)}</span>
                    <span class="vl-badge">${Number(p.speed || 1.0).toFixed(2)}x speed</span>
                    <span class="vl-badge">${_esc((p.language || 'en').toUpperCase())}</span>
                </div>
                <div class="vl-row-actions">
                    <button class="hub-action-btn" style="height:32px; padding:0 0.85rem; font-size:0.76rem;"
                            onclick="VoiceLibrary.previewVoice('${_esc(p.model_id)}', '${_esc(p.voice_id)}', this, ${Number(p.speed || 1.0)})">
                        <i class="fas fa-volume-high"></i> Preview Preset
                    </button>
                    <button class="lm-icon-btn" style="width:32px; height:32px; color:#f87171;"
                            title="Delete preset" onclick="VoiceLibrary.deletePreset('${_esc(p.id)}')">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>`;
        }).join('');
    }

    function _renderCloning() {
        const cloneModelSel = document.getElementById('vl-clone-model');
        const bannerEl = document.getElementById('vl-cloning-status-banner');
        const clonedGrid = document.getElementById('vl-cloned-voices-grid');
        if (!cloneModelSel || !clonedGrid) return;

        const clonable = _models.filter(m => m.supports_cloning);
        cloneModelSel.innerHTML = clonable.map(m =>
            `<option value="${_esc(m.id)}">${_esc(m.name)} ${m.installed ? '(Installed)' : '(Not Installed)'}</option>`
        ).join('') || `<option value="xtts">Coqui XTTS-v2</option>`;

        const anyInstalled = clonable.some(m => m.installed);
        if (bannerEl) {
            bannerEl.innerHTML = anyInstalled
                ? ''
                : `<div style="padding:0.85rem 1rem; border-radius:10px; background:rgba(251,146,60,0.1); border:1px solid rgba(251,146,60,0.3); display:flex; align-items:center; justify-content:space-between; gap:1rem;">
                    <div style="font-size:0.82rem; color:var(--text-primary);">
                        <i class="fas fa-circle-info" style="color:#fb923c; margin-right:0.4rem;"></i>
                        <strong>Voice Cloning Engine Required:</strong> Install <strong>Coqui XTTS-v2</strong> in Model Hub &gt; Audio &amp; Speech to clone voices locally.
                    </div>
                    <button class="hub-action-btn secondary" onclick="switchMainTab('audio-models')" style="white-space:nowrap;">
                        <i class="fas fa-download"></i> Go to Audio Models
                    </button>
                </div>`;
        }

        const clonedVoices = [];
        for (const m of _models) {
            for (const v of (m.voices || [])) {
                if (v.cloned) clonedVoices.push({ ...v, model_id: m.id, model_name: m.name });
            }
        }

        if (!clonedVoices.length) {
            clonedGrid.innerHTML = `<p class="empty-state">No cloned voices yet. Upload a reference clip above to create your first custom voice.</p>`;
            return;
        }

        clonedGrid.innerHTML = clonedVoices.map(v => `
            <div class="vl-row-card">
                <div class="vl-row-identity">
                    <div class="vl-voice-icon">
                        <i class="fas fa-dna"></i>
                    </div>
                    <div style="min-width:0;">
                        <div style="display:flex; align-items:center; gap:0.55rem; flex-wrap:wrap;">
                            <h3 class="vl-row-title">${_esc(v.name)}</h3>
                            <span class="vl-row-id">${_esc(v.id)}</span>
                        </div>
                    </div>
                </div>
                <div class="vl-voice-meta">
                    <span class="vl-badge cloned">${_esc(v.model_name)}</span>
                    <span class="vl-badge">${_esc((v.language || 'en').toUpperCase())}</span>
                </div>
                <div class="vl-row-actions">
                    <button class="hub-action-btn" style="height:32px; padding:0 0.85rem; font-size:0.76rem;"
                            onclick="VoiceLibrary.previewVoice('${_esc(v.model_id)}', '${_esc(v.id)}', this)">
                        <i class="fas fa-play"></i> Preview Cloned Voice
                    </button>
                    <button class="lm-icon-btn" style="width:32px; height:32px; color:#f87171;"
                            title="Delete cloned voice" onclick="VoiceLibrary.deleteClonedVoice('${_esc(v.model_id)}', '${_esc(v.id)}')">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
    }

    async function previewVoice(modelId, voiceId, btn, customSpeed = null) {
        const text = (document.getElementById('vl-sample-text')?.value || 'Hello, I am ready to assist you.').trim();
        const speed = customSpeed !== null
            ? customSpeed
            : parseFloat(document.getElementById('vl-sample-speed')?.value || '1.0');

        const origHtml = btn ? btn.innerHTML : '';
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Speaking...`;
        }

        try {
            if (window.AethvionVoice) {
                await window.AethvionVoice.speak(text, { model_id: modelId, voice_id: voiceId, speed });
            } else {
                const res = await fetch('/api/audio/local/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text, model_id: modelId, voice_id: voiceId, speed })
                });
                const d = await res.json();
                if (d.success && d.audio) {
                    if (_activeAudio) { _activeAudio.pause(); _activeAudio = null; }
                    _activeAudio = new Audio(d.audio);
                    await _activeAudio.play();
                } else {
                    throw new Error(d.detail || 'TTS preview failed');
                }
            }
        } catch (e) {
            if (typeof showNotification === 'function') {
                showNotification(`Preview error: ${e.message}`, 'error');
            }
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = origHtml;
            }
        }
    }

    function previewDraftPreset() {
        const modelId = document.getElementById('vl-new-preset-model')?.value || 'kokoro';
        const voiceId = document.getElementById('vl-new-preset-voice')?.value || 'af_heart';
        const speed = parseFloat(document.getElementById('vl-new-preset-speed')?.value || '1.0');
        previewVoice(modelId, voiceId, null, speed);
    }

    async function createPreset() {
        const nameEl = document.getElementById('vl-new-preset-name');
        const descEl = document.getElementById('vl-new-preset-desc');
        const modelId = document.getElementById('vl-new-preset-model')?.value || 'kokoro';
        const voiceId = document.getElementById('vl-new-preset-voice')?.value || 'af_heart';
        const speed = parseFloat(document.getElementById('vl-new-preset-speed')?.value || '1.0');

        const name = (nameEl?.value || '').trim();
        if (!name) {
            if (typeof showNotification === 'function') showNotification('Please enter a preset name.', 'warning');
            return;
        }

        const mod = _models.find(m => m.id === modelId);
        const voiceObj = mod?.voices?.find(v => v.id === voiceId);

        try {
            const res = await fetch('/api/audio/local/library/presets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name,
                    model_id: modelId,
                    voice_id: voiceId,
                    speed,
                    language: voiceObj?.language || 'en',
                    gender: voiceObj?.gender || 'neutral',
                    description: (descEl?.value || '').trim()
                })
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.detail || 'Failed to save preset');
            if (nameEl) nameEl.value = '';
            if (descEl) descEl.value = '';
            if (typeof showNotification === 'function') showNotification(`Saved voice preset "${name}"`, 'success');
            await refresh();
        } catch (e) {
            if (typeof showNotification === 'function') showNotification(e.message, 'error');
        }
    }

    async function quickSavePreset(modelId, voiceId, voiceName, lang, gender) {
        const defaultName = `${voiceName} (${modelId})`;
        const name = prompt('Enter a name for this global Voice Preset:', defaultName);
        if (!name || !name.trim()) return;
        const speed = parseFloat(document.getElementById('vl-sample-speed')?.value || '1.0');
        try {
            const res = await fetch('/api/audio/local/library/presets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name.trim(),
                    model_id: modelId,
                    voice_id: voiceId,
                    speed,
                    language: lang || 'en',
                    gender: gender || 'neutral',
                    description: `Saved from ${modelId} (${voiceName})`
                })
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.detail || 'Failed to save preset');
            if (typeof showNotification === 'function') showNotification(`Preset "${name.trim()}" saved to Voice Library!`, 'success');
            await refresh();
        } catch (e) {
            if (typeof showNotification === 'function') showNotification(e.message, 'error');
        }
    }

    async function deletePreset(presetId) {
        if (!confirm('Remove this voice preset from the library?')) return;
        try {
            const res = await fetch(`/api/audio/local/library/presets/${encodeURIComponent(presetId)}`, {
                method: 'DELETE'
            });
            if (!res.ok) throw new Error('Delete failed');
            if (typeof showNotification === 'function') showNotification('Voice preset removed.', 'success');
            await refresh();
        } catch (e) {
            if (typeof showNotification === 'function') showNotification(e.message, 'error');
        }
    }

    function _setupCloneDropzone() {
        const dz = document.getElementById('vl-clone-dropzone');
        const inp = document.getElementById('vl-clone-file');
        const nameEl = document.getElementById('vl-clone-filename');
        if (!dz || !inp) return;

        dz.onclick = () => inp.click();
        dz.ondragover = e => { e.preventDefault(); dz.classList.add('drag-over'); };
        dz.ondragleave = () => dz.classList.remove('drag-over');
        dz.ondrop = e => {
            e.preventDefault();
            dz.classList.remove('drag-over');
            if (e.dataTransfer.files[0]) _readCloneFile(e.dataTransfer.files[0], nameEl);
        };
        inp.onchange = () => {
            if (inp.files[0]) _readCloneFile(inp.files[0], nameEl);
        };
    }

    function _readCloneFile(file, nameEl) {
        if (nameEl) nameEl.textContent = `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
        const reader = new FileReader();
        reader.onload = e => { _cloneAudioB64 = e.target.result.split(',')[1]; };
        reader.readAsDataURL(file);
    }

    async function cloneVoice() {
        const modelId = document.getElementById('vl-clone-model')?.value || 'xtts';
        const name = (document.getElementById('vl-clone-name')?.value || '').trim();
        const language = document.getElementById('vl-clone-lang')?.value || 'en';
        const btn = document.getElementById('vl-clone-submit-btn');

        if (!_cloneAudioB64) {
            if (typeof showNotification === 'function') showNotification('Please upload a reference audio file first.', 'warning');
            return;
        }
        if (!name) {
            if (typeof showNotification === 'function') showNotification('Please enter a name for the cloned voice.', 'warning');
            return;
        }

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Cloning Voice...`;
        }
        try {
            const res = await fetch('/api/audio/local/voices/clone', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model_id: modelId,
                    reference_audio_b64: _cloneAudioB64,
                    name,
                    language
                })
            });
            const d = await res.json();
            if (!res.ok || !d.success) throw new Error(d.detail || 'Voice cloning failed');
            if (typeof showNotification === 'function') showNotification(`Voice "${name}" cloned successfully!`, 'success');
            _cloneAudioB64 = null;
            const nEl = document.getElementById('vl-clone-name');
            const fEl = document.getElementById('vl-clone-filename');
            if (nEl) nEl.value = '';
            if (fEl) fEl.textContent = '';
            await refresh();
        } catch (e) {
            if (typeof showNotification === 'function') showNotification(e.message, 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<i class="fas fa-plus-circle"></i> Clone Voice Profile`;
            }
        }
    }

    async function deleteClonedVoice(modelId, voiceId) {
        if (!confirm(`Delete cloned voice "${voiceId}"?`)) return;
        try {
            const res = await fetch('/api/audio/local/voices', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model_id: modelId, voice_id: voiceId })
            });
            if (!res.ok) throw new Error('Failed to delete cloned voice');
            if (typeof showNotification === 'function') showNotification('Cloned voice deleted.', 'success');
            await refresh();
        } catch (e) {
            if (typeof showNotification === 'function') showNotification(e.message, 'error');
        }
    }

    function switchTab(tab, btn) {
        _currentTab = tab;
        ['voices', 'presets', 'cloning'].forEach(t => {
            const sec = document.getElementById(`vl-section-${t}`);
            if (sec) sec.style.display = t === tab ? '' : 'none';
        });
        const filtersWrap = document.getElementById('vl-filters-wrap');
        if (filtersWrap) filtersWrap.style.display = tab === 'voices' ? 'flex' : 'none';
        document.querySelectorAll('[data-vltab]').forEach(b => {
            b.classList.toggle('active', b.dataset.vltab === tab);
        });
    }

    if (typeof registerTabInit === 'function') {
        registerTabInit('voice-library', init);
    }

    document.addEventListener('panelLoaded', function (e) {
        if (e.detail.panelId === 'voice-library-panel') init();
    });

    return {
        init,
        refresh,
        switchTab,
        onFilterChange,
        onPresetModelChange,
        previewVoice,
        previewDraftPreset,
        createPreset,
        quickSavePreset,
        deletePreset,
        cloneVoice,
        deleteClonedVoice
    };
})();
