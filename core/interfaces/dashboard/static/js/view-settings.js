// Misaka Cipher - Preferences & Settings View
// Handles interacting with user preferences and provider configuration data

// Make prefs global for other scripts
window.prefs = {
    data: {},

    async load() {
        try {
            const response = await fetch('/api/preferences');
            this.data = await response.json();
            
            // On very first load, trigger update check logic async
            if (!window._hasCheckedUpdates) {
                window._hasCheckedUpdates = true;
                setTimeout(() => runStartupUpdateCheck(), 2500);
            }

            console.log('Loaded preferences:', this.data);
            return this.data;
        } catch (error) {
            console.error('Failed to load preferences:', error);
            return {};
        }
    },

    get(key, defaultValue) {
        // Generic dot notation support
        if (key.includes('.')) {
            const parts = key.split('.');
            let current = this.data;
            for (const part of parts) {
                if (current === undefined || current === null) return defaultValue;
                current = current[part];
            }
            return current !== undefined ? current : defaultValue;
        }

        return this.data[key] !== undefined ? this.data[key] : defaultValue;
    },

    async set(key, value) {
        // Update local cache immediately
        if (key.includes('.')) {
            const parts = key.split('.');
            if (!this.data[parts[0]]) this.data[parts[0]] = {};
            this.data[parts[0]][parts[1]] = value;
        } else {
            this.data[key] = value;
        }

        // Save to server
        try {
            await fetch(`/api/preferences/${key}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key, value })
            });
        } catch (error) {
            console.error(`Failed to save preference ${key}:`, error);
        }
    }
};

async function loadPreferences() {
    await prefs.load();

    // Assistant Settings
    const assistantEnabled = document.getElementById('setting-assistant-enabled');
    if (assistantEnabled) {
        assistantEnabled.checked = prefs.get('assistant.enabled', true);
        assistantEnabled.onchange = async (e) => {
            await savePreference('assistant.enabled', e.target.checked);
            window.dispatchEvent(new CustomEvent('assistantSettingsUpdated', {
                detail: { enabled: e.target.checked }
            }));
        };
    }

    const assistantModel = document.getElementById('setting-assistant-model');
    if (assistantModel) {
        assistantModel.onchange = async (e) => {
            await savePreference('assistant.model', e.target.value);
        };
    }

    const assistantContext = document.getElementById('setting-assistant-context');
    if (assistantContext) {
        assistantContext.checked = prefs.get('assistant.include_web_context', false);
        assistantContext.onchange = async (e) => {
            await savePreference('assistant.include_web_context', e.target.checked);
        };
    }

    const assistantDashControl = document.getElementById('setting-assistant-dashboard-control');
    if (assistantDashControl) {
        assistantDashControl.checked = prefs.get('assistant.allow_dashboard_control', false);
        assistantDashControl.onchange = async (e) => {
            await savePreference('assistant.allow_dashboard_control', e.target.checked);
        };
    }

    const assistantTypingSpeed = document.getElementById('setting-assistant-typing-speed');
    const assistantTypingVal = document.getElementById('setting-assistant-typing-speed-val');
    if (assistantTypingSpeed && assistantTypingVal) {
        const currentSpeed = prefs.get('assistant.typing_speed', 20);
        assistantTypingSpeed.value = currentSpeed;
        assistantTypingVal.textContent = currentSpeed;

        assistantTypingSpeed.oninput = (e) => {
            assistantTypingVal.textContent = e.target.value;
        };
        assistantTypingSpeed.onchange = async (e) => {
            const val = parseInt(e.target.value, 10);
            await savePreference('assistant.typing_speed', val);
            window.dispatchEvent(new CustomEvent('assistantSettingsUpdated', {
                detail: { typing_speed: val }
            }));
        };
    }

    const assistantContextLimit = document.getElementById('setting-assistant-context-limit');
    const assistantContextLimitVal = document.getElementById('setting-assistant-context-limit-val');
    if (assistantContextLimit && assistantContextLimitVal) {
        const currentLimit = prefs.get('assistant.context_limit', 5);
        assistantContextLimit.value = currentLimit;
        assistantContextLimitVal.textContent = currentLimit;

        assistantContextLimit.oninput = (e) => {
            assistantContextLimitVal.textContent = e.target.value;
        };
        assistantContextLimit.onchange = async (e) => {
            const val = parseInt(e.target.value, 10);
            await savePreference('assistant.context_limit', val);
            window.dispatchEvent(new CustomEvent('assistantSettingsUpdated', {
                detail: { context_limit: val }
            }));
        };
    }

    // Misaka Cipher Settings
    const misakaModel = document.getElementById('setting-misakacipher-model');
    if (misakaModel) {
        misakaModel.onchange = async (e) => {
            await savePreference('misakacipher.model', e.target.value);
        };
    }

    const misakaTypingSpeed = document.getElementById('setting-misakacipher-typing-speed');
    const misakaTypingVal = document.getElementById('setting-misakacipher-typing-speed-val');
    if (misakaTypingSpeed && misakaTypingVal) {
        const currentSpeed = prefs.get('misakacipher.typing_speed', 20);
        misakaTypingSpeed.value = currentSpeed;
        misakaTypingVal.textContent = currentSpeed;

        misakaTypingSpeed.oninput = (e) => {
            misakaTypingVal.textContent = e.target.value;
        };
        misakaTypingSpeed.onchange = async (e) => {
            const val = parseInt(e.target.value, 10);
            await savePreference('misakacipher.typing_speed', val);
            window.dispatchEvent(new CustomEvent('misakaSettingsUpdated', {
                detail: { typing_speed: val }
            }));
        };
    }

    const misakaContextLimit = document.getElementById('setting-misakacipher-context-limit');
    const misakaContextLimitVal = document.getElementById('setting-misakacipher-context-limit-val');
    if (misakaContextLimit && misakaContextLimitVal) {
        const currentLimit = prefs.get('misakacipher.context_limit', 6);
        misakaContextLimit.value = currentLimit;
        misakaContextLimitVal.textContent = currentLimit;

        misakaContextLimit.oninput = (e) => {
            misakaContextLimitVal.textContent = e.target.value;
        };
        misakaContextLimit.onchange = async (e) => {
            const val = parseInt(e.target.value, 10);
            await savePreference('misakacipher.context_limit', val);
            window.dispatchEvent(new CustomEvent('misakaSettingsUpdated', {
                detail: { context_limit: val }
            }));
        };
    }

    // Proactive Messaging Settings
    const proactiveSettings = [
        { id: 'setting-misaka-proactive-enabled', pref: 'misakacipher.proactive_enabled', type: 'toggle', default: true },
        { id: 'setting-misaka-proactive-popup', pref: 'misakacipher.proactive_popup', type: 'toggle', default: true },
        { id: 'setting-misaka-startup-hours', pref: 'misakacipher.startup_trigger_hours', type: 'range', default: 4, valId: 'setting-misaka-startup-hours-val' },
        { id: 'setting-misaka-startup-chance', pref: 'misakacipher.startup_chance', type: 'range', default: 75, valId: 'setting-misaka-startup-chance-val' },
        { id: 'setting-misaka-startup-delay-min', pref: 'misakacipher.startup_delay_min', type: 'range', default: 10, valId: 'setting-misaka-startup-delay-min-val' },
        { id: 'setting-misaka-startup-delay-max', pref: 'misakacipher.startup_delay_max', type: 'range', default: 45, valId: 'setting-misaka-startup-delay-max-val' },
        { id: 'setting-misaka-session-interval-min', pref: 'misakacipher.session_interval_min', type: 'range', default: 45, valId: 'setting-misaka-session-interval-min-val' },
        { id: 'setting-misaka-session-interval-max', pref: 'misakacipher.session_interval_max', type: 'range', default: 90, valId: 'setting-misaka-session-interval-max-val' },
        { id: 'setting-misaka-session-chance', pref: 'misakacipher.session_chance', type: 'range', default: 60, valId: 'setting-misaka-session-chance-val' },
        { id: 'setting-misakacipher-proactive-tools', pref: 'misakacipher.allow_proactive_tools', type: 'toggle', default: false },
    ];

    for (const s of proactiveSettings) {
        const el = document.getElementById(s.id);
        if (!el) continue;
        if (s.type === 'toggle') {
            el.checked = prefs.get(s.pref, s.default);
        } else {
            const val = prefs.get(s.pref, s.default);
            el.value = val;
            const display = document.getElementById(s.valId);
            if (display) display.textContent = val;
            el.oninput = (e) => { if (display) display.textContent = e.target.value; };
        }

        el.onchange = async (e) => {
            const val = s.type === 'toggle' ? e.target.checked : parseFloat(e.target.value);
            await savePreference(s.pref, val);
            window.dispatchEvent(new CustomEvent('misakaSettingsUpdated', {
                detail: { proactive_change: true }
            }));
        };
    }

    // Initialize Other Sections
    loadGlobalSettings();
    initDevMode();
    loadMisakaWorkspaces();
    loadNexusModules();
}

async function savePreference(key, value) {
    await prefs.set(key, value);
}

// ===== Nexus Module Management =====

async function loadNexusModules() {
    try {
        const res = await fetch('/api/misakacipher/nexus/registry');
        if (!res.ok) return;
        const data = await res.json();
        renderNexusModules(data.modules || []);
    } catch (e) {
        console.warn('Could not load Nexus modules:', e);
    }
}

function renderNexusModules(modules) {
    const container = document.getElementById('nexus-module-list');
    if (!container) return;
    if (!modules.length) {
        container.innerHTML = '<span style="color: var(--text-secondary); font-size: 0.8rem; font-style: italic;">No Nexus modules available.</span>';
        return;
    }
    container.innerHTML = '';
    for (const mod of modules) {
        const card = document.createElement('div');
        card.style.cssText = 'padding:1rem; background:rgba(255,255,255,0.02); border:1px solid var(--border); border-radius:8px;';

        let settingsHtml = '';
        if (mod.settings && mod.settings.length > 0) {
            settingsHtml = `
                <div style="margin-top:0.75rem; display:flex; flex-direction:column; gap:0.5rem; border-top:1px solid rgba(255,255,255,0.05); padding-top:0.75rem;">
                    ${mod.settings.map(s => `
                        <div style="display:flex; flex-direction:column; gap:0.2rem;">
                            <label style="font-size:0.75rem; color:var(--text-secondary);">${s.replace(/_/g, ' ').toUpperCase()}</label>
                            <input type="password" class="control-input nexus-setting" data-mod="${mod.id}" data-key="${s}" value="${prefs.get(`nexus.${mod.id}.${s}`, '')}" style="width:100%; box-sizing:border-box; font-size:0.8rem; padding:0.4rem;">
                        </div>
                    `).join('')}
                    <button class="btn btn-secondary" style="font-size:0.75rem; margin-top:0.25rem;" onclick="saveNexusSettings('${mod.id}')">Save ${mod.name} Settings</button>
                </div>
            `;
        }

        const authBtn = (mod.requires_auth && !mod.is_authorized)
            ? `<button class="btn btn-primary" style="font-size:0.75rem; margin-top:0.5rem;" onclick="authorizeNexusModule('${mod.id}')">Connect ${mod.name}</button>`
            : (mod.requires_auth ? `<span style="color:#00ff88; font-size:0.75rem; margin-top:0.5rem; display:block;"><i class="fas fa-check-circle"></i> Authorized</span>` : '');

        card.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:start;">
                <div>
                    <div style="font-weight:600; color:var(--text-primary); font-size:0.9rem;">${mod.name}</div>
                    <div style="color:var(--text-secondary); font-size:0.8rem; margin-top:0.2rem;">${mod.description}</div>
                </div>
                <div style="font-size:0.7rem; color:var(--primary); font-family:Orbitron,sans-serif;">ID: ${mod.id}</div>
            </div>
            ${authBtn}
            ${settingsHtml}
        `;
        container.appendChild(card);
    }
}

async function saveNexusSettings(moduleId) {
    const inputs = document.querySelectorAll(`.nexus-setting[data-mod="${moduleId}"]`);
    for (const input of inputs) {
        const key = input.getAttribute('data-key');
        const val = input.value.trim();
        await savePreference(`nexus.${moduleId}.${key}`, val);
    }
    alert(`${moduleId} settings saved!`);
}

async function authorizeNexusModule(moduleId) {
    if (moduleId === 'spotify') {
        const settings = {
            client_id: prefs.get('nexus.spotify.client_id', ''),
            client_secret: prefs.get('nexus.spotify.client_secret', ''),
            redirect_uri: prefs.get('nexus.spotify.redirect_uri', 'http://localhost:8080/callback')
        };

        if (!settings.client_id || !settings.client_secret) {
            alert('Please enter and save your Spotify Client ID and Secret first.');
            return;
        }

        try {
            const res = await fetch('/api/misakacipher/nexus/spotify/authorize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
            if (!res.ok) throw new Error('Failed to get auth URL');
            const data = await res.json();
            window.open(data.url, '_blank', 'width=600,height=800');
        } catch (e) {
            alert('Error: ' + e.message);
        }
    }
}

// ===== Misaka Workspace Management =====

async function loadMisakaWorkspaces() {
    try {
        const res = await fetch('/api/misakacipher/workspaces');
        if (!res.ok) return;
        const data = await res.json();
        renderWorkspaces(data.workspaces || []);

        const addBtn = document.getElementById('ws-add-btn');
        if (addBtn) addBtn.onclick = addMisakaWorkspace;
    } catch (e) {
        console.warn('Could not load Misaka workspaces:', e);
    }
}

function renderWorkspaces(workspaces) {
    const container = document.getElementById('misaka-workspace-list');
    if (!container) return;
    if (!workspaces.length) {
        container.innerHTML = '<span style="color: var(--text-secondary); font-size: 0.8rem; font-style: italic;">No workspaces configured.</span>';
        return;
    }
    container.innerHTML = '';
    for (const ws of workspaces) {
        const perms = ws.permissions.map(p => `<span style="background: rgba(0,217,255,0.1); border: 1px solid rgba(0,217,255,0.25); border-radius: 4px; padding: 1px 6px; font-size: 0.7rem; color: var(--primary);">${p}</span>`).join(' ');
        const row = document.createElement('div');
        row.style.cssText = 'display:flex; align-items:center; gap:0.6rem; padding:0.5rem 0.6rem; background:rgba(255,255,255,0.02); border:1px solid var(--border); border-radius:6px; font-size:0.82rem;';
        row.innerHTML = `
            <div style="flex:1; min-width:0;">
                <div style="font-weight:600; color:var(--text-primary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${ws.label}</div>
                <div style="color:var(--text-secondary); font-size:0.75rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${ws.path}">${ws.path}</div>
            </div>
            <div style="display:flex; gap:0.3rem; flex-shrink:0;">${perms}</div>
            <span style="color:var(--text-secondary); font-size:0.7rem; flex-shrink:0;">${ws.recursive ? '↳ recursive' : 'folder only'}</span>
            <button data-wsid="${ws.id}" title="Remove workspace" style="background:none; border:none; color:var(--text-secondary); cursor:pointer; font-size:0.85rem; padding:0.2rem 0.4rem; transition:color 0.2s;" onmouseover="this.style.color='#ff4444'" onmouseout="this.style.color=''">✕</button>
        `;
        row.querySelector('button').onclick = () => deleteMisakaWorkspace(ws.id);
        container.appendChild(row);
    }
}

async function addMisakaWorkspace() {
    const path = document.getElementById('ws-add-path')?.value?.trim();
    const label = document.getElementById('ws-add-label')?.value?.trim() || path;
    if (!path) return;

    const permissions = [];
    if (document.getElementById('ws-perm-read')?.checked) permissions.push('read');
    if (document.getElementById('ws-perm-write')?.checked) permissions.push('write');
    if (document.getElementById('ws-perm-delete')?.checked) permissions.push('delete');
    const recursive = document.getElementById('ws-recursive')?.checked ?? true;

    try {
        const res = await fetch('/api/misakacipher/workspaces', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ label, path, permissions, recursive })
        });
        if (!res.ok) {
            const err = await res.json();
            alert('Error: ' + (err.detail || 'Unknown error'));
            return;
        }
        document.getElementById('ws-add-path').value = '';
        document.getElementById('ws-add-label').value = '';
        await loadMisakaWorkspaces();
    } catch (e) {
        console.error('Failed to add workspace:', e);
    }
}

async function deleteMisakaWorkspace(id) {
    if (!confirm('Remove this workspace?')) return;
    try {
        await fetch(`/api/misakacipher/workspaces/${id}`, { method: 'DELETE' });
        await loadMisakaWorkspaces();
    } catch (e) {
        console.error('Failed to delete workspace:', e);
    }
}

// ===== Global settings.json Management =====

async function loadGlobalSettings() {
    const container = document.getElementById('global-settings-container');
    if (!container) return;

    try {
        const response = await fetch('/api/settings');
        const settings = await response.json();

        // Recursively flatten or pick important ones?
        // For simplicity, we'll render output_validation and system blocks
        let html = '';

        // Tooltip descriptions for global settings
        const tooltips = {
            'output_validation.check_file_content': 'Verifies that the generated file contains valid content.',
            'output_validation.check_file_location': 'Ensures the generated file is saved in the correct directory.',
            'output_validation.min_file_size': 'Minimum file size (in bytes) to be considered valid.',
            'output_validation.min_content_length': 'Minimum character length for content to be considered valid.',
            'system.open_browser_on_startup': 'Automatically opens the dashboard in your default web browser when Misaka Cipher starts.',
            'voice.input_model': 'Model used for voice input transcription. "browser" uses the built-in Web Speech API (free, no API key needed).'
        };

        // Flatten settings for editing
        const renderGroup = (title, obj, prefix = '') => {
            let groupHtml = `<div class="settings-subgroup"><h4>${title}</h4>`;
            for (const [key, value] of Object.entries(obj)) {
                const fullKey = prefix ? `${prefix}.${key}` : key;
                const tooltipText = tooltips[fullKey] ? ` title="${tooltips[fullKey]}"` : '';

                if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
                    groupHtml += renderGroup(key, value, fullKey);
                } else if (typeof value === 'boolean') {
                    groupHtml += `
                        <div class="compact-item toggle-item" ${tooltipText}>
                            <div class="item-label">${key.replace(/_/g, ' ')}</div>
                            <label class="switch small">
                                <input type="checkbox" class="global-setting-input" data-key="${fullKey}" ${value ? 'checked' : ''}>
                                <span class="slider round"></span>
                            </label>
                        </div>
                    `;
                } else {
                    groupHtml += `
                        <div class="compact-item" ${tooltipText}>
                            <div class="item-label">${key.replace(/_/g, ' ')}</div>
                            <input type="${typeof value === 'number' ? 'number' : 'text'}"
                                class="global-setting-input control-input-small"
                                data-key="${fullKey}"
                                value="${value}">
                        </div>
                    `;
                }
            }
            groupHtml += `</div>`;
            return groupHtml;
        };

        if (settings.output_validation) html += renderGroup('Output Validation', settings.output_validation, 'output_validation');
        if (settings.system) html += renderGroup('System Settings', settings.system, 'system');

        // Render voice settings with a special dropdown for input_model
        const voiceSettings = settings.voice || { input_model: 'browser', input_provider: 'browser' };
        html += renderVoiceSettings(voiceSettings);

        container.innerHTML = html;

        // Attach listeners for standard inputs
        container.querySelectorAll('.global-setting-input').forEach(input => {
            input.addEventListener('change', async (e) => {
                const key = e.target.dataset.key;
                let value = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
                if (e.target.type === 'number') value = parseFloat(value);

                try {
                    await fetch('/api/settings', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ [key]: value })
                    });
                } catch (err) {
                    console.error('Failed to save global setting:', err);
                }
            });
        });

        // Populate and attach voice model selector
        await populateVoiceModelSelector(voiceSettings);

    } catch (error) {
        console.error('Failed to load settings.json:', error);
        container.innerHTML = '<div class="loading-placeholder">Failed to load settings</div>';
    }
}

function renderVoiceSettings(voiceSettings) {
    const currentModel = voiceSettings.input_model || 'browser';
    return `
        <div class="settings-subgroup">
            <h4>Voice Settings</h4>
            <div class="compact-item" title="Model used for voice input transcription. 'browser' uses the built-in Web Speech API (free, no API key needed).">
                <div class="item-label">voice input model</div>
                <select id="voice-input-model-select" class="control-select" style="min-width:160px; font-size:0.82rem;">
                    <option value="browser" ${currentModel === 'browser' ? 'selected' : ''}>Browser (Web Speech API)</option>
                </select>
            </div>
        </div>
    `;
}

async function populateVoiceModelSelector(voiceSettings) {
    const select = document.getElementById('voice-input-model-select');
    if (!select) return;

    const currentModel = voiceSettings.input_model || 'browser';

    try {
        // Load registry to find VOICEINPUT-capable models
        if (typeof _registryData === 'undefined' || !_registryData) {
            if (typeof loadProviderSettings === 'function') await loadProviderSettings();
        }

        if (_registryData && _registryData.providers) {
            for (const [providerName, config] of Object.entries(_registryData.providers)) {
                if (!config.models) continue;
                for (const [modelKey, info] of Object.entries(config.models)) {
                    const caps = (info.capabilities || []).map(c => c.toUpperCase());
                    if (caps.includes('VOICEINPUT')) {
                        const option = document.createElement('option');
                        option.value = modelKey;
                        option.dataset.provider = providerName;
                        option.textContent = `${providerName}: ${info.id || modelKey}`;
                        if (modelKey === currentModel) option.selected = true;
                        select.appendChild(option);
                    }
                }
            }
        }
    } catch (e) {
        console.warn('Could not load voice models:', e);
    }

    select.addEventListener('change', async (e) => {
        const selectedOption = e.target.selectedOptions[0];
        const model = e.target.value;
        const provider = selectedOption ? (selectedOption.dataset.provider || 'browser') : 'browser';

        try {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    'voice.input_model': model,
                    'voice.input_provider': model === 'browser' ? 'browser' : provider
                })
            });
            showNotification('Voice input model updated.', 'success');
        } catch (err) {
            console.error('Failed to save voice model:', err);
        }
    });
}

// ===== Developer Mode & .env Management =====

let devModeActive = false;

function initDevMode() {
    const btn = document.getElementById('btn-toggle-dev-mode');
    if (!btn || btn.dataset.initialized) return;
    btn.dataset.initialized = 'true';

    btn.addEventListener('click', () => {
        devModeActive = !devModeActive;
        const icon = btn.querySelector('i');
        const envContainer = document.getElementById('env-status-container');

        if (devModeActive) {
            btn.classList.add('active');
            icon.className = 'fas fa-lock-open';
            loadEnvStatus();
        } else {
            btn.classList.remove('active');
            icon.className = 'fas fa-lock';
            if (envContainer) envContainer.innerHTML = '<div class="locked-placeholder"><i class="fas fa-lock"></i> Developer Mode Restricted</div>';
        }

        // Also show/hide dev-only fields in provider cards if they exist
        document.querySelectorAll('.dev-only-field').forEach(f => f.style.display = devModeActive ? '' : 'none');
    });

    // Initial state
    const envContainer = document.getElementById('env-status-container');
    if (envContainer) envContainer.innerHTML = '<div class="locked-placeholder"><i class="fas fa-lock"></i> Developer Mode Restricted</div>';
}

async function loadEnvStatus() {
    const container = document.getElementById('env-status-container');
    if (!container || !devModeActive) return;

    container.innerHTML = '<div class="loading-placeholder">Loading environment variables...</div>';

    try {
        const res = await fetch('/api/registry/env/status');
        if (!res.ok) throw new Error('Failed to load status');
        const data = await res.json();

        if (!data.exists) {
            container.innerHTML = `
                <div class="env-not-found">
                    <p>No <code>.env</code> file found.</p>
                    <button id="create-env-btn" class="action-btn secondary small">Create from Template</button>
                </div>
            `;
            document.getElementById('create-env-btn').onclick = async () => {
                await fetch('/api/registry/env/create', { method: 'POST' });
                loadEnvStatus();
            };
        } else {
            let keysHtml = '<div class="env-keys-list-compact">';
            for (const k of data.keys) {
                keysHtml += `
                    <div class="env-key-row-compact">
                        <div class="key-info">
                            <span class="key-name">${k.name}</span>
                            <span class="key-status ${k.has_value ? 'set' : 'unset'}"></span>
                        </div>
                        <div class="key-actions">
                            <input type="password" class="env-key-input-compact" data-key="${k.name}" placeholder="${k.has_value ? '********' : 'Not set'}">
                            <button class="action-btn xs-btn env-save-key-btn" data-key="${k.name}"><i class="fas fa-save"></i></button>
                        </div>
                    </div>
                `;
            }
            keysHtml += '</div>';
            container.innerHTML = keysHtml;

            container.querySelectorAll('.env-save-key-btn').forEach(b => {
                b.onclick = async () => {
                    const kname = b.dataset.key;
                    const input = container.querySelector(`input[data-key="${kname}"]`);
                    if (!input.value.trim()) return;

                    await fetch('/api/registry/env/update', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ key: kname, value: input.value.trim() })
                    });
                    input.value = '';
                    loadEnvStatus();
                };
            });
        }
    } catch (e) {
        container.innerHTML = '<div class="loading-placeholder error">Error loading .env</div>';
    }
}

// ===== Tooltips =====

function initTooltips() {
    document.querySelectorAll('.tooltip-trigger').forEach(trigger => {
        trigger.addEventListener('click', (e) => {
            const title = trigger.getAttribute('title');
            alert(title); // Simple for now, can be improved to floating tooltips
        });
    });
}

// ===== Provider & Profile Management =====

let _registryData = null;
let _suggestedModels = {};
let _settingsDirty = false;

function markSettingsDirty() {
    if (_settingsDirty) return;
    _settingsDirty = true;
    const banner = document.getElementById('provider-unsaved-banner');
    if (banner) banner.style.display = 'block';
}

function clearSettingsDirty() {
    _settingsDirty = false;
    const banner = document.getElementById('provider-unsaved-banner');
    if (banner) banner.style.display = 'none';
}

async function loadProviderSettings() {
    try {
        const [regRes, sugRes] = await Promise.all([
            fetch('/api/registry'),
            fetch('/api/registry/suggested')
        ]);

        if (regRes.ok) _registryData = await regRes.json();
        if (sugRes.ok) _suggestedModels = await sugRes.json();

        if (_registryData) {
            renderProviderCards(_registryData);
            renderProfiles();
        }
        initProfileCreationButtons();
        initProviderCreationButtons();

        const pSaveBtn = document.getElementById('save-provider-settings');
        if (pSaveBtn) pSaveBtn.onclick = saveProviderSettings;
    } catch (error) {
        console.error('Failed to load registry:', error);
        showNotification('Failed to load provider settings.', 'error');
    }
}

function initProviderCreationButtons() {
    const btn = document.getElementById('add-provider-btn');
    if (btn) {
        btn.onclick = toggleAddProviderInline;
    }
}

async function toggleAddProviderInline() {
    const container = document.getElementById('inline-add-provider');
    if (!container) return;

    if (container.style.display === 'block') {
        container.style.display = 'none';
        return;
    }

    try {
        const res = await fetch('/api/registry/available_types');
        const types = await res.json();

        // Filter out already added providers
        const existing = Object.keys(_registryData?.providers || {});
        const available = types.filter(t => !existing.includes(t));

        if (available.length === 0) {
            showNotification('All supported provider types have already been added.', 'info');
            return;
        }

        container.style.display = 'block';
        container.innerHTML = `
            <div style="display: flex; flex-direction: column; gap: 0.8rem;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h4 style="margin: 0; font-size: 0.9rem; color: var(--primary);">Add Supported Provider</h4>
                    <button class="icon-btn xs-btn" onclick="document.getElementById('inline-add-provider').style.display='none'"><i class="fas fa-times"></i></button>
                </div>
                <div style="display: flex; gap: 0.5rem; align-items: center;">
                    <select id="new-provider-type-select" class="control-select" style="flex: 1;">
                        ${available.map(t => `<option value="${t}">${t.replace('_', ' ').toUpperCase()}</option>`).join('')}
                    </select>
                    <button class="action-btn primary xs-btn" id="confirm-add-provider-inline">Add</button>
                </div>
                <p class="section-hint" style="margin: 0;">Selecting a type will add the provider with default system configuration.</p>
            </div>
        `;

        document.getElementById('confirm-add-provider-inline').onclick = async () => {
            const type = document.getElementById('new-provider-type-select').value;
            try {
                const addRes = await fetch('/api/registry/providers', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ type })
                });

                if (addRes.ok) {
                    showNotification(`Provider added successfully.`, 'success');
                    container.style.display = 'none';
                    await loadProviderSettings(); // Refresh
                } else {
                    const data = await addRes.json();
                    showNotification(data.detail || 'Failed to add provider.', 'error');
                }
            } catch (e) {
                showNotification('Error connecting to server.', 'error');
            }
        };
    } catch (e) {
        console.error('Failed to load available types:', e);
    }
}

// Available capability tags
const AVAILABLE_CAPS = ['CHAT', 'IMAGE', 'AUDIO'];

/**
 * Renders the inner HTML of a caps table cell.
 * Returns a string with .caps-cell div containing pills and a + button.
 */
function renderCapsTd(caps = [], modelKey = null) {
    const pills = caps.map(c => `
        <span class="cap-tag" data-cap="${c}" title="Click to remove">
            ${c}<span class="cap-remove">✕</span>
        </span>
    `).join('');

    let gearBtns = '';
    const hasImageCap = caps.some(c => c.toLowerCase() === 'image' || c.toLowerCase() === 'image_generation');
    if (hasImageCap && modelKey) {
        gearBtns += `<button class="icon-btn xs-btn toggle-image-settings" title="Image Settings" data-model="${modelKey}"><i class="fas fa-cog"></i></button>`;
    }

    const hasAudioCap = caps.some(c => c.toLowerCase() === 'audio');
    if (hasAudioCap && modelKey) {
        gearBtns += `<button class="icon-btn xs-btn toggle-audio-settings" title="Audio Settings" data-model="${modelKey}"><i class="fas fa-microphone"></i></button>`;
    }

    const isEmpty = caps.length === 0 ? 'empty' : '';
    return `<div class="caps-cell ${isEmpty}" style="position:relative;">${pills}<div class="caps-actions">${gearBtns}<button class="add-cap-btn" title="Add capability">+</button></div></div>`;
}

function renderImageConfigRow(modelKey, m) {
    const config = m.image_config || {};
    const ar = config.aspect_ratios || ['1:1'];
    return `
        <tr class="image-config-row" data-model="${modelKey}" style="display:none;">
            <td colspan="5">
                <div class="image-config-container">
                    <div class="image-config-header">
                        <i class="fas fa-image"></i> Image Capability Configuration
                    </div>
                    <div class="image-config-grid">
                        <div class="config-field">
                            <label>Aspect Ratios</label>
                            <div style="display:flex; gap:10px; flex-wrap:wrap;">
                                <label style="display:flex; align-items:center; gap:4px; font-size:0.75rem;"><input type="checkbox" class="img-ar-1-1" ${ar.includes('1:1') ? 'checked' : ''}> 1:1</label>
                                <label style="display:flex; align-items:center; gap:4px; font-size:0.75rem;"><input type="checkbox" class="img-ar-16-9" ${ar.includes('16:9') ? 'checked' : ''}> 16:9</label>
                                <label style="display:flex; align-items:center; gap:4px; font-size:0.75rem;"><input type="checkbox" class="img-ar-9-16" ${ar.includes('9:16') ? 'checked' : ''}> 9:16</label>
                                <label style="display:flex; align-items:center; gap:4px; font-size:0.75rem;"><input type="checkbox" class="img-ar-custom" ${ar.includes('custom') ? 'checked' : ''}> custom</label>
                            </div>
                        </div>
                        <div class="config-field">
                            <label>Quality Options (comma-sep)</label>
                            <input type="text" class="img-quality-options" value="${(config.quality_options || ['standard', 'hd']).join(', ')}" placeholder="standard, hd...">
                        </div>
                        <div class="config-field toggle-field">
                            <label>Negative Prompt</label>
                            <label class="switch small">
                                <input type="checkbox" class="img-neg-prompt" ${config.supports_negative_prompt ? 'checked' : ''}>
                                <span class="slider round"></span>
                            </label>
                        </div>
                        <div class="config-field toggle-field">
                            <label>Supports Seed</label>
                            <label class="switch small">
                                <input type="checkbox" class="img-supports-seed" ${config.supports_seed ? 'checked' : ''}>
                                <span class="slider round"></span>
                            </label>
                        </div>
                    </div>
                </div>
            </td>
        </tr>
    `;
}

function renderAudioConfigRow(modelKey, m) {
    const config = m.audio_config || {};
    return `
        <tr class="audio-config-row" data-model="${modelKey}" style="display:none;">
            <td colspan="5">
                <div class="image-config-container" style="border-color: var(--primary);">
                    <div class="image-config-header" style="background: var(--primary); color: white;">
                        <i class="fas fa-microphone"></i> Audio Capability Configuration
                    </div>
                    <div class="image-config-grid">
                        <div class="config-field">
                            <label>Preferred Voice</label>
                            <input type="text" class="audio-voice" value="${config.voice || 'alloy'}" placeholder="alloy, echo, fable...">
                        </div>
                        <div class="config-field">
                            <label>Format</label>
                            <input type="text" class="audio-format" value="${config.format || 'mp3'}" placeholder="mp3, wav, pcm...">
                        </div>
                        <div class="config-field toggle-field">
                            <label>STT Support</label>
                            <label class="switch small">
                                <input type="checkbox" class="audio-stt" ${config.supports_stt ? 'checked' : ''}>
                                <span class="slider round"></span>
                            </label>
                        </div>
                        <div class="config-field toggle-field">
                            <label>TTS Support</label>
                            <label class="switch small">
                                <input type="checkbox" class="audio-tts" ${config.supports_tts ? 'checked' : ''}>
                                <span class="slider round"></span>
                            </label>
                        </div>
                    </div>
                </div>
            </td>
        </tr>
    `;
}

/**
 * Attaches interactive listeners to a .caps-cell element.
 * Handles clicking + to show dropdown, clicking tag to remove, clicking dropdown item to add.
 */
function initCapsTd(cell) {
    if (!cell || cell._capsInited) return;
    cell._capsInited = true;

    // Remove existing tag on click
    cell.addEventListener('click', (e) => {
        const tag = e.target.closest('.cap-tag');
        if (tag) {
            const removedCap = tag.dataset.cap;
            const currentCell = tag.closest('.caps-cell');
            tag.remove();

            if (removedCap && (removedCap.toLowerCase() === 'image' || removedCap.toLowerCase() === 'image_generation')) {
                const gear = currentCell.querySelector('.toggle-image-settings');
                if (gear) gear.remove();

                // Also hide the config row if it's currently open
                const tr = cell.closest('tr');
                if (tr) {
                    const modelInput = tr.querySelector('.model-id-input-small');
                    const modelKey = modelInput ? modelInput.value.trim() : '';
                    if (modelKey) {
                        const configRow = tr.parentNode.querySelector(`.image-config-row[data-model="${modelKey}"]`);
                        if (configRow) configRow.style.display = 'none';
                    }
                }
            }

            if (removedCap && removedCap.toLowerCase() === 'audio') {
                const gear = currentCell.querySelector('.toggle-audio-settings');
                if (gear) gear.remove();

                const tr = cell.closest('tr');
                if (tr) {
                    const modelInput = tr.querySelector('.model-id-input-small');
                    const modelKey = modelInput ? modelInput.value.trim() : '';
                    if (modelKey) {
                        const configRow = tr.parentNode.querySelector(`.audio-config-row[data-model="${modelKey}"]`);
                        if (configRow) configRow.style.display = 'none';
                    }
                }
            }

            if (currentCell && currentCell.querySelectorAll('.cap-tag').length === 0) {
                currentCell.classList.add('empty');
            }
            markSettingsDirty();
            return;
        }

        // + button clicked
        const addBtn = e.target.closest('.add-cap-btn');
        if (addBtn) {
            // Close any open dropdowns first
            document.querySelectorAll('.cap-dropdown').forEach(d => d.remove());

            const currentCaps = Array.from(cell.querySelectorAll('.cap-tag')).map(t => t.dataset.cap);
            const available = AVAILABLE_CAPS.filter(c => !currentCaps.includes(c));

            if (available.length === 0) {
                showNotification('All capabilities already added.', 'info');
                return;
            }

            const dropdown = document.createElement('div');
            dropdown.className = 'cap-dropdown';
            dropdown.innerHTML = available.map(c =>
                `<div class="cap-dropdown-item" data-cap="${c}">${c}</div>`
            ).join('');

            // Position below the button
            cell.style.position = 'relative';
            cell.appendChild(dropdown);

            // Select capability from dropdown
            dropdown.addEventListener('click', (de) => {
                const item = de.target.closest('.cap-dropdown-item');
                if (!item) return;
                const cap = item.dataset.cap;
                dropdown.remove();

                // Insert tag before the + button
                const pill = document.createElement('span');
                pill.className = 'cap-tag';
                pill.dataset.cap = cap;
                pill.title = 'Click to remove';
                pill.innerHTML = `${cap}<span class="cap-remove">✕</span>`;
                const actions = cell.querySelector('.caps-actions');
                cell.insertBefore(pill, actions);
                cell.classList.remove('empty');

                // If 'image' capability added, dynamically add gear button and config row if missing
                if (cap.toLowerCase() === 'image' || cap.toLowerCase() === 'image_generation') {
                    const actions = cell.querySelector('.caps-actions');
                    if (actions && !actions.querySelector('.toggle-image-settings')) {
                        const tr = cell.closest('tr');
                        const modelInput = tr.querySelector('.model-id-input-small');
                        const modelKey = modelInput ? modelInput.value.trim() : '';

                        if (modelKey) {
                            const gear = document.createElement('button');
                            gear.className = 'icon-btn xs-btn toggle-image-settings';
                            gear.title = 'Image Settings';
                            gear.dataset.model = modelKey;
                            gear.innerHTML = '<i class="fas fa-cog"></i>';
                            actions.insertBefore(gear, actions.firstChild);

                            gear.onclick = (ge) => {
                                const providerItem = gear.closest('.compact-provider-item');
                                let row = providerItem.querySelector(`.image-config-row[data-model="${modelKey}"]`);

                                if (!row) {
                                    tr.insertAdjacentHTML('afterend', renderImageConfigRow(modelKey, {}));
                                    row = tr.nextElementSibling;
                                }

                                const isVisible = row.style.display !== 'none';
                                row.style.display = isVisible ? 'none' : 'table-row';
                                gear.classList.toggle('active', !isVisible);
                                ge.stopPropagation();
                            };
                        }
                    }
                }

                if (cap.toLowerCase() === 'audio') {
                    const actions = cell.querySelector('.caps-actions');
                    if (actions && !actions.querySelector('.toggle-audio-settings')) {
                        const tr = cell.closest('tr');
                        const modelInput = tr.querySelector('.model-id-input-small');
                        const modelKey = modelInput ? modelInput.value.trim() : '';

                        if (modelKey) {
                            const gear = document.createElement('button');
                            gear.className = 'icon-btn xs-btn toggle-audio-settings';
                            gear.title = 'Audio Settings';
                            gear.dataset.model = modelKey;
                            gear.innerHTML = '<i class="fas fa-microphone"></i>';
                            actions.insertBefore(gear, actions.firstChild);

                            gear.onclick = (ge) => {
                                const providerItem = gear.closest('.compact-provider-item');
                                let row = providerItem.querySelector(`.audio-config-row[data-model="${modelKey}"]`);

                                if (!row) {
                                    tr.insertAdjacentHTML('afterend', renderAudioConfigRow(modelKey, {}));
                                    row = tr.nextElementSibling;
                                }

                                const isVisible = row.style.display !== 'none';
                                row.style.display = isVisible ? 'none' : 'table-row';
                                gear.classList.toggle('active', !isVisible);
                                ge.stopPropagation();
                            };
                        }
                    }
                }

                markSettingsDirty();
            });

            // Close on outside click
            setTimeout(() => {
                document.addEventListener('click', function closeDropdown(ev) {
                    if (!dropdown.contains(ev.target)) {
                        dropdown.remove();
                        document.removeEventListener('click', closeDropdown);
                    }
                });
            }, 0);
            e.stopPropagation();
        }
    });
}

async function loadChatModels() {
    const selects = [
        document.getElementById('model-select'),
        document.getElementById('setting-assistant-model'),
        document.getElementById('agent-model-select'),
        document.getElementById('arena-model-add'),
        document.getElementById('aiconv-model-add'),
        document.getElementById('advaiconv-person-add'),
        document.getElementById('setting-misakacipher-model')
    ].filter(Boolean);

    if (selects.length === 0) return;

    try {
        const res = await fetch('/api/registry/models/chat');
        if (!res.ok) throw new Error('Failed to load chat models');
        const data = await res.json();

        // Standardize tags in registry data too if they come back as lowercase
        if (data.models) {
            data.models.forEach(m => {
                if (m.capabilities) {
                    m.capabilities = m.capabilities.map(c => c.toUpperCase());
                }
            });
        }

        const chatOptions = generateCategorizedModelOptions(data, 'chat');
        const agentOptions = generateCategorizedModelOptions(data, 'agent');

        selects.forEach(sel => {
            const currentVal = sel.value;
            const isAgent = sel.id === 'agent-model-select';
            sel.innerHTML = isAgent ? agentOptions : chatOptions;

            // Fix for model select initialization
            if (sel.id === 'setting-assistant-model') {
                const prefModel = prefs.get('assistant.model', 'gemini-2.0-flash');
                if (sel.querySelector(`option[value="${prefModel}"]`)) {
                    sel.value = prefModel;
                }
            } else if (sel.id === 'setting-misakacipher-model') {
                const prefModel = prefs.get('misakacipher.model', 'gemini-1.5-flash');
                if (sel.querySelector(`option[value="${prefModel}"]`)) {
                    sel.value = prefModel;
                }
            } else if (currentVal && sel.querySelector(`option[value="${currentVal}"]`)) {
                sel.value = currentVal;
            }
        });

    } catch (err) {
        console.error('Error loading chat models:', err);
    }
}

function renderProviderCards(registry, expandedProviderName = null) {
    const container = document.getElementById('provider-cards-container');
    if (!container) return;

    const providers = registry.providers || {};
    let html = '';

    for (const [name, config] of Object.entries(providers)) {
        const isActive = (config.chat_config?.active || config.agent_config?.active);
        const shouldBeExpanded = (name === expandedProviderName);

        html += `
            <div class="compact-provider-item ${isActive ? 'active' : ''}" data-provider="${name}">
                <div class="provider-info-row">
                    <div class="provider-main">
                        <span class="status-dot ${isActive ? 'active' : ''}"></span>
                        <span class="provider-name">${name}</span>
                    </div>
                    <div class="provider-actions">
                        <button class="action-btn xs-btn toggle-models-btn" title="Edit Models"><i class="fas fa-list"></i></button>
                    </div>
                </div>
                <div class="provider-config-grid">
                    <div class="config-row">
                        <span class="label">Chat</span>
                        <label class="switch small">
                            <input type="checkbox" class="chat-active-toggle" data-provider="${name}" ${config.chat_config?.active ? 'checked' : ''}>
                            <span class="slider round"></span>
                        </label>
                    </div>
                    <div class="config-row">
                        <span class="label">Agent</span>
                        <label class="switch small">
                            <input type="checkbox" class="agent-active-toggle" data-provider="${name}" ${config.agent_config?.active ? 'checked' : ''}>
                            <span class="slider round"></span>
                        </label>
                    </div>
                </div>
                <div class="provider-models-foldout" style="display:${shouldBeExpanded ? 'block' : 'none'};">
                    <table class="compact-models-table">
                        <thead>
                            <tr>
                                <th>Model ID</th>
                                <th>Cost (In/Out)</th>
                                <th>Capabilities</th>
                                <th>Description</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                             ${Object.entries(config.models || {}).map(([key, m]) => {
            const modelId = typeof m === 'string' ? m : (m.id || key);
            const caps = Array.isArray(m.capabilities) ? m.capabilities : [];
            const desc = (typeof m === 'object' && m.description) ? m.description : '';
            return `
                                    <tr class="model-main-row" data-model="${key}">
                                        <td><input type="text" class="model-id-input-small" value="${key}" data-key="${key}"></td>
                                        <td>
                                            <div class="cost-inputs">
                                                <input type="number" step="0.01" class="model-cost-in" value="${m.input_cost_per_1m_tokens || 0}">
                                                <input type="number" step="0.01" class="model-cost-out" value="${m.output_cost_per_1m_tokens || 0}">
                                            </div>
                                        </td>
                                        <td>${renderCapsTd(caps, key)}</td>
                                        <td><input type="text" class="model-desc-input" value="${desc.replace(/"/g, '&quot;')}" placeholder="Best for..."></td>
                                        <td>
                                            <button class="btn-icon xs-btn del-model" data-key="${key}"><i class="fas fa-trash"></i></button>
                                        </td>
                                    </tr>
                                    ${renderImageConfigRow(key, m)}
                                    ${renderAudioConfigRow(key, m)}
                                 `;
        }).join('')}
                        </tbody>
                    </table>
                    <div class="add-model-line">
                        <button class="action-btn xs-btn secondary add-model-btn" data-provider="${name}">+ Add Model</button>
                        <button class="action-btn xs-btn secondary suggested-model-btn" data-provider="${name}"><i class="fas fa-magic"></i> Suggested</button>
                    </div>
                </div>
            </div>
        `;
    }

    container.innerHTML = html || '<div class="placeholder-text">No providers found.</div>';

    // Event Listeners
    container.querySelectorAll('.toggle-models-btn').forEach(btn => {
        btn.onclick = () => {
            const foldout = btn.closest('.compact-provider-item').querySelector('.provider-models-foldout');
            foldout.style.display = foldout.style.display === 'none' ? 'block' : 'none';
        };
    });

    container.querySelectorAll('.toggle-image-settings').forEach(btn => {
        btn.onclick = (e) => {
            const modelKey = btn.dataset.model;
            // Find the image config row for THIS model in THIS provider card
            const providerItem = btn.closest('.compact-provider-item');
            const row = providerItem.querySelector(`.image-config-row[data-model="${modelKey}"]`);
            if (row) {
                const isVisible = row.style.display !== 'none';
                row.style.display = isVisible ? 'none' : 'table-row';
                btn.classList.toggle('active', !isVisible);
            }
            e.stopPropagation();
        };
    });

    container.querySelectorAll('.toggle-audio-settings').forEach(btn => {
        btn.onclick = (e) => {
            const modelKey = btn.dataset.model;
            // Find the audio config row for THIS model in THIS provider card
            const providerItem = btn.closest('.compact-provider-item');
            const row = providerItem.querySelector(`.audio-config-row[data-model="${modelKey}"]`);
            if (row) {
                const isVisible = row.style.display !== 'none';
                row.style.display = isVisible ? 'none' : 'table-row';
                btn.classList.toggle('active', !isVisible);
            }
            e.stopPropagation();
        };
    });

    container.addEventListener('change', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') {
            markSettingsDirty();
        }
    });
    container.querySelectorAll('.caps-cell').forEach(cell => initCapsTd(cell));
    container.querySelectorAll('.chat-active-toggle, .agent-active-toggle').forEach(t => {
        t.onchange = (e) => {
            const item = e.target.closest('.compact-provider-item');
            const dot = item.querySelector('.status-dot');
            const isActive = item.querySelector('.chat-active-toggle').checked || item.querySelector('.agent-active-toggle').checked;
            item.classList.toggle('active', isActive);
            dot.classList.toggle('active', isActive);
            markSettingsDirty();
        };
    });

    container.querySelectorAll('.add-model-btn').forEach(btn => {
        btn.onclick = () => addModelRowInline(btn.dataset.provider);
    });

    container.querySelectorAll('.suggested-model-btn').forEach(btn => {
        btn.onclick = () => openAddModelModal(btn.dataset.provider);
    });

    container.querySelectorAll('.del-model').forEach(btn => {
        btn.onclick = () => {
            btn.closest('tr').remove();
            markSettingsDirty();
        };
    });

    const saveBtn = document.getElementById('save-provider-settings');
    if (saveBtn) saveBtn.onclick = saveProviderSettings;
}

function addModelRowInline(providerName) {
    const providerItem = document.querySelector(`.compact-provider-item[data-provider="${providerName}"]`);
    if (!providerItem) return;

    const tbody = providerItem.querySelector('tbody');
    const foldout = providerItem.querySelector('.provider-models-foldout');
    foldout.style.display = 'block';

    const row = document.createElement('tr');
    row.className = 'model-main-row';
    row.innerHTML = `
        <td><input type="text" class="model-id-input-small" value="" data-key="" placeholder="model-id"></td>
        <td>
            <div class="cost-inputs">
                <input type="number" step="0.01" class="model-cost-in" value="0">
                <input type="number" step="0.01" class="model-cost-out" value="0">
            </div>
        </td>
        <td>${renderCapsTd([], '')}</td>
        <td><input type="text" class="model-desc-input" value="" placeholder="Best for..."></td>
        <td>
            <button class="btn-icon xs-btn del-model" onclick="this.closest('tr').remove(); markSettingsDirty();"><i class="fas fa-trash"></i></button>
        </td>
    `;
    tbody.appendChild(row);
    // Note: We don't render image config row for new models until they get the 'image' cap
    initCapsTd(row.querySelector('.caps-cell'));
    markSettingsDirty();
    row.querySelector('input').focus();
}

async function saveProviderSettings() {
    if (!_registryData) return;

    const items = document.querySelectorAll('.compact-provider-item');
    items.forEach(item => {
        const name = item.dataset.provider;
        const prov = _registryData.providers[name];
        if (!prov) return;

        prov.chat_config = { active: item.querySelector('.chat-active-toggle').checked, priority: 1 };
        prov.agent_config = { active: item.querySelector('.agent-active-toggle').checked, priority: 1 };

        // Model updates - Rebuild from scratch to handle additions/deletions
        prov.models = {};
        const modelRows = item.querySelectorAll('tbody tr.model-main-row');
        modelRows.forEach(row => {
            const input = row.querySelector('.model-id-input-small');
            const modelName = input.value.trim();
            if (!modelName) return; // Skip empty names

            const costIn = parseFloat(row.querySelector('.model-cost-in').value);
            const costOut = parseFloat(row.querySelector('.model-cost-out').value);
            // Read capabilities from tag pills
            const capsCell = row.querySelector('.caps-cell');
            const capabilities = capsCell
                ? Array.from(capsCell.querySelectorAll('.cap-tag')).map(t => t.dataset.cap)
                : [];
            const descInput = row.querySelector('.model-desc-input');
            const description = descInput ? descInput.value.trim() : '';

            // Image config (if row exists)
            const imgRow = item.querySelector(`.image-config-row[data-model="${modelName}"]`);
            let image_config = null;
            if (imgRow && capabilities.includes('IMAGE')) {
                const ar = [];
                if (imgRow.querySelector('.img-ar-1-1').checked) ar.push('1:1');
                if (imgRow.querySelector('.img-ar-16-9').checked) ar.push('16:9');
                if (imgRow.querySelector('.img-ar-9-16').checked) ar.push('9:16');
                if (imgRow.querySelector('.img-ar-custom').checked) ar.push('custom');

                const qual = imgRow.querySelector('.img-quality-options').value.split(',').map(s => s.trim()).filter(Boolean);
                const neg = imgRow.querySelector('.img-neg-prompt').checked;
                const seed = imgRow.querySelector('.img-supports-seed').checked;

                image_config = {
                    aspect_ratios: ar,
                    quality_options: qual,
                    supports_negative_prompt: neg,
                    supports_seed: seed
                };
            }

            // Audio config (if row exists)
            const audioRow = item.querySelector(`.audio-config-row[data-model="${modelName}"]`);
            let audio_config = null;
            if (audioRow && capabilities.includes('AUDIO')) {
                audio_config = {
                    voice: audioRow.querySelector('.audio-voice').value.trim(),
                    format: audioRow.querySelector('.audio-format').value.trim(),
                    supports_stt: audioRow.querySelector('.audio-stt').checked,
                    supports_tts: audioRow.querySelector('.audio-tts').checked
                };
            }

            prov.models[modelName] = {
                input_cost_per_1m_tokens: costIn,
                output_cost_per_1m_tokens: costOut,
                capabilities: capabilities,
                ...(description ? { description } : {}),
                ...(image_config ? { image_config } : {}),
                ...(audio_config ? { audio_config } : {})
            };
        });
    });

    try {
        const res = await fetch('/api/registry', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(_registryData)
        });
        if (res.ok) {
            clearSettingsDirty();
            loadChatModels();
            showNotification('Settings saved successfully.', 'success');
        } else {
            showNotification('Failed to save settings.', 'error');
        }
    } catch (e) {
        console.error('Save failed:', e);
        showNotification('Failed to save settings.', 'error');
    }
}

function renderProfiles() {
    if (!_registryData) return;
    const profiles = _registryData.profiles || { chat_profiles: {}, agent_profiles: {} };

    const render = (containerId, dict, type) => {
        const container = document.getElementById(containerId);
        if (!container) return;

        let html = '';
        const dictToUse = dict || {};
        for (const [name, models] of Object.entries(dictToUse)) {
            html += `
                <div class="profile-compact-item" data-name="${name}" data-type="${type}">
                    <div class="profile-main">
                        <span class="profile-name">${name === 'default' ? '⭐ default' : name}</span>
                        <div class="profile-models-badges">
                            ${models.map(m => `<span class="model-badge">${m.split('/').pop()}</span>`).join('')}
                        </div>
                    </div>
                    <div class="profile-actions">
                        <button class="action-btn xs-btn secondary edit-profile" data-name="${name}" data-type="${type}" title="Edit Profile Models">
                            <i class="fas fa-edit"></i> Edit
                        </button>
                        ${name !== 'default' ? `
                            <button class="action-btn xs-btn danger del-profile" data-name="${name}" data-type="${type}" title="Delete Profile">
                                <i class="fas fa-trash"></i>
                            </button>
                        ` : ''}
                    </div>
                    <div class="profile-editor-inline" id="editor-${type}-${name.replace(/\s+/g, '-')}">
                        <!-- Inline editor content injected here -->
                    </div>
                </div>
            `;
        }
        container.innerHTML = html || '<div class="placeholder-text">No profiles.</div>';

        container.querySelectorAll('.edit-profile').forEach(b => {
            b.onclick = () => toggleProfileEditor(b.dataset.name, b.dataset.type, b);
        });

        container.querySelectorAll('.del-profile').forEach(b => {
            b.onclick = async () => {
                if (confirm(`Delete ${type} profile "${b.dataset.name}"?`)) {
                    await deleteProfile(b.dataset.name, b.dataset.type);
                }
            };
        });
    };

    render('chat-profiles-container', profiles.chat_profiles, 'chat');
    render('agent-profiles-container', profiles.agent_profiles, 'agent');
}

function toggleProfileEditor(name, type, button) {
    const item = button.closest('.profile-compact-item');
    const editor = item.querySelector('.profile-editor-inline');
    const isActive = editor.classList.toggle('active');

    if (isActive) {
        button.innerHTML = '<i class="fas fa-times"></i> Close';
        button.classList.add('active');
        renderInlineProfileEditor(editor, name, type);
    } else {
        button.innerHTML = '<i class="fas fa-edit"></i> Edit';
        button.classList.remove('active');
    }
}

function renderInlineProfileEditor(container, name, type) {
    if (!_registryData) return;
    const profiles = type === 'chat' ? _registryData.profiles.chat_profiles : _registryData.profiles.agent_profiles;
    const selectedModels = profiles[name] || [];

    // All available models from registry
    let allModels = [];
    for (const [pName, pConfig] of Object.entries(_registryData.providers)) {
        for (const [mKey, mVal] of Object.entries(pConfig.models)) {
            if (!allModels.includes(mKey)) allModels.push(mKey);
        }
    }

    const renderList = () => {
        const listHtml = selectedModels.map((m, index) => `
            <div class="draggable-model-item" draggable="true" data-index="${index}">
                <div class="drag-handle"><i class="fas fa-grip-lines"></i></div>
                <div class="model-name">${m}</div>
                <button class="icon-btn xs-btn danger remove-model" data-index="${index}">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `).join('');

        container.innerHTML = `
            <div class="draggable-model-list">
                ${listHtml || '<div class="placeholder-text">No models in this profile.</div>'}
            </div>
            <div class="model-registry-add">
                <select class="control-input-small add-model-select">
                    <option value="">-- Add Model to Profile --</option>
                    ${allModels.filter(m => !selectedModels.includes(m)).map(m => `
                        <option value="${m}">${m}</option>
                    `).join('')}
                </select>
                <button class="action-btn xs-btn primary add-model-to-profile-btn">Add</button>
            </div>
            <div style="margin-top: 1rem; display: flex; justify-content: flex-end;">
                <button class="action-btn xs-btn primary save-profile-inline-btn">Save Sequence</button>
            </div>
        `;

        // Add Listeners
        const list = container.querySelector('.draggable-model-list');
        list.querySelectorAll('.draggable-model-item').forEach(item => {
            item.ondragstart = (e) => {
                e.dataTransfer.setData('text/plain', item.dataset.index);
                item.classList.add('dragging');
            };
            item.ondragend = () => item.classList.remove('dragging');
            item.ondragover = (e) => e.preventDefault();
            item.ondrop = (e) => {
                e.preventDefault();
                const fromIndex = parseInt(e.dataTransfer.getData('text/plain'));
                const toIndex = parseInt(item.dataset.index);
                if (fromIndex !== toIndex) {
                    const movedItem = selectedModels.splice(fromIndex, 1)[0];
                    selectedModels.splice(toIndex, 0, movedItem);
                    renderList();
                }
            };
        });

        container.querySelectorAll('.remove-model').forEach(b => {
            b.onclick = () => {
                selectedModels.splice(parseInt(b.dataset.index), 1);
                renderList();
            };
        });

        container.querySelector('.add-model-to-profile-btn').onclick = () => {
            const sel = container.querySelector('.add-model-select');
            if (sel.value) {
                selectedModels.push(sel.value);
                renderList();
            }
        };

        container.querySelector('.save-profile-inline-btn').onclick = async () => {
            profiles[name] = selectedModels;
            await saveRegistry();
        };
    };

    renderList();
}

async function deleteProfile(name, type) {
    if (!_registryData) return;
    const profiles = type === 'chat' ? _registryData.profiles.chat_profiles : _registryData.profiles.agent_profiles;
    delete profiles[name];
    await saveRegistry();
}

async function saveRegistry() {
    try {
        const res = await fetch('/api/registry', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(_registryData)
        });
        if (res.ok) {
            renderProfiles();
            loadChatModels();
            showNotification('Profiles updated successfully.', 'success');
        } else {
            showNotification('Failed to save profiles.', 'error');
        }
    } catch (e) {
        console.error('Failed to save registry:', e);
    }
}

function initProfileCreationButtons() {
    const addChatBtn = document.getElementById('add-chat-profile-btn');
    const addAgentBtn = document.getElementById('add-agent-profile-btn');

    if (addChatBtn) {
        addChatBtn.onclick = () => createNewProfile('chat');
    }
    if (addAgentBtn) {
        addAgentBtn.onclick = () => createNewProfile('agent');
    }
}

async function createNewProfile(type) {
    const name = prompt(`Enter name for new ${type} profile:`);
    if (!name) return;

    if (!_registryData.profiles) _registryData.profiles = { chat_profiles: {}, agent_profiles: {} };
    const dict = type === 'chat' ? _registryData.profiles.chat_profiles : _registryData.profiles.agent_profiles;

    if (dict[name]) {
        showNotification('Profile name already exists.', 'warning');
        return;
    }

    dict[name] = [];
    await saveRegistry();
    renderProfiles();
    editProfile(name, type);
}

// ===== Enhanced Add Model Modal =====

async function openAddModelModal(providerName) {
    if (!_suggestedModels || !_registryData) return;

    const providerSuggested = _suggestedModels[providerName] || [];
    const providerExisting = _registryData.providers[providerName]?.models || {};

    const html = `
        <div class="modal-content add-model-modal">
            <div class="modal-header">
                <h3>Add Model to ${providerName}</h3>
                <button class="icon-btn xs-btn" onclick="closeModal()"><i class="fas fa-times"></i></button>
            </div>
            <div class="modal-body">
                <div class="setting-group">
                    <label>Select from suggested models</label>
                    <div class="suggested-select-wrapper">
                        <i class="fas fa-wand-sparkles select-magic-icon"></i>
                        <select id="suggested-model-select" class="term-select-main">
                            <option value="">-- Choose a Model --</option>
                            ${providerSuggested.map(m => `
                                <option value="${m.id}" data-cost-in="${m.input_cost || 0}" data-cost-out="${m.output_cost || 0}" data-caps="${(m.capabilities || []).join(',')}">
                                    ${m.id} (${m.tier || 'custom'})
                                </option>
                            `).join('')}
                        </select>
                    </div>
                </div>
                <div class="divider"><span>OR CUSTOM</span></div>
                <div class="setting-group">
                    <label>Custom Model ID</label>
                    <input type="text" id="custom-model-id" class="term-input" placeholder="e.g. gpt-4-turbo">
                </div>
                <div class="cost-row-grid">
                    <div class="setting-group">
                        <label>Input Cost ($/1M)</label>
                        <input type="number" step="0.01" id="new-model-cost-in" class="term-input" value="0">
                    </div>
                    <div class="setting-group">
                        <label>Output Cost ($/1M)</label>
                        <input type="number" step="0.01" id="new-model-cost-out" class="term-input" value="0">
                    </div>
                </div>
                 <div class="setting-group">
                    <label>Capabilities</label>
                    <div id="new-model-caps-container">
                        ${renderCapsTd([], null)}
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="action-btn secondary" onclick="closeModal()">Cancel</button>
                <button id="confirm-add-model" class="action-btn">Add Model</button>
            </div>
        </div>
    `;

    openCustomModal(html);

    const select = document.getElementById('suggested-model-select');
    const customInput = document.getElementById('custom-model-id');
    const costIn = document.getElementById('new-model-cost-in');
    const costOut = document.getElementById('new-model-cost-out');
    const capsContainer = document.getElementById('new-model-caps-container');

    // Initialize the capability picker logic for the modal
    initCapsTd(capsContainer.querySelector('.caps-cell'));

    select.onchange = () => {
        if (select.value) {
            const opt = select.options[select.selectedIndex];
            customInput.value = select.value;
            costIn.value = opt.dataset.costIn;
            costOut.value = opt.dataset.costOut;

            // Clear existing and set new caps
            const cell = capsContainer.querySelector('.caps-cell');
            cell.querySelectorAll('.cap-tag').forEach(t => t.remove());
            const caps = opt.dataset.caps.split(',').filter(Boolean);
            const addBtn = cell.querySelector('.add-cap-btn');
            caps.forEach(cap => {
                const pill = document.createElement('span');
                pill.className = 'cap-tag';
                pill.dataset.cap = cap;
                pill.title = 'Click to remove';
                pill.innerHTML = `${cap}<span class="cap-remove">✕</span>`;
                const actions = cell.querySelector('.caps-actions');
                cell.insertBefore(pill, actions);
            });
            cell.classList.toggle('empty', caps.length === 0);
        }
    };

    document.getElementById('confirm-add-model').onclick = () => {
        const modelId = customInput.value.trim();
        if (!modelId) {
            showNotification('Model ID is required.', 'warning');
            return;
        }

        const capsCell = capsContainer.querySelector('.caps-cell');
        const capabilities = Array.from(capsCell.querySelectorAll('.cap-tag')).map(t => t.dataset.cap);

        const modelEntry = {
            input_cost_per_1m_tokens: parseFloat(costIn.value) || 0,
            output_cost_per_1m_tokens: parseFloat(costOut.value) || 0,
            capabilities: capabilities
        };

        // Add to registry data
        if (!_registryData.providers[providerName].models) {
            _registryData.providers[providerName].models = {};
        }
        _registryData.providers[providerName].models[modelId] = modelEntry;

        closeModal();
        markSettingsDirty();
        renderProviderCards(_registryData, providerName);
        showNotification(`Model ${modelId} added (unsaved).`, 'info');
    };
}

// ===== Profile Reordering =====

async function moveProfile(element, direction) {
    const name = element.dataset.name;
    const type = element.dataset.type;
    const profiles = type === 'chat' ? _registryData.profiles.chat_profiles : _registryData.profiles.agent_profiles;

    const keys = Object.keys(profiles);
    const index = keys.indexOf(name);

    if (direction === 'up' && index > 0) {
        [keys[index], keys[index - 1]] = [keys[index - 1], keys[index]];
    } else if (direction === 'down' && index < keys.length - 1) {
        [keys[index], keys[index + 1]] = [keys[index + 1], keys[index]];
    } else {
        return; // Already at boundary
    }

    // Rebuild the profile object to maintain order
    const newProfiles = {};
    keys.forEach(k => newProfiles[k] = profiles[k]);

    if (type === 'chat') _registryData.profiles.chat_profiles = newProfiles;
    else _registryData.profiles.agent_profiles = newProfiles;

    await saveRegistry();
    renderProfiles();
    showNotification('Profile order updated.', 'success');
}

// Global initialization
window.addEventListener('DOMContentLoaded', () => {
    loadPreferences();
    loadProviderSettings();
    initSettingsSubNav();
});

async function initSettingsSubNav() {
    const navItems = document.querySelectorAll('.settings-nav-item');
    navItems.forEach(item => {
        item.onclick = async () => {
            const subTab = item.dataset.settingsubtab;
            await switchSettingsSubTab(subTab);
        };
    });

    // Restore active sub-tab from server
    try {
        const response = await fetch('/api/preferences/get?key=active_settings_subtab');
        let savedSubTab = 'assistant';
        if (response.ok) {
            const data = await response.json();
            if (data.value) savedSubTab = data.value;
        }
        // Redirect 'assistant' to 'assistant' (default) if that's what was intended
        // or stay on 'assistant' if it was renamed from something else.
        switchSettingsSubTab(savedSubTab, false);
    } catch (e) {
        switchSettingsSubTab('assistant', false);
    }
}

async function switchSettingsSubTab(subTab, save = true) {
    // Update nav items
    document.querySelectorAll('.settings-nav-item').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.settingsubtab === subTab);
    });

    // Update panels
    document.querySelectorAll('.settings-panel').forEach(panel => {
        panel.classList.toggle('active', panel.id === `settings-panel-${subTab}`);
    });

    if (subTab === 'profiles') {
        loadRoutingProfiles();
    }

    if (subTab === 'modules') {
        loadNexusModules();
    }

    if (subTab === 'discord') {
        initDiscordSettings();
        loadDiscordStatus();
    }

    if (save && typeof savePreference === 'function') {
        savePreference('active_settings_subtab', subTab);
    }
}

// Attach to window
window.switchSettingsSubTab = switchSettingsSubTab;

// ===== Auto Routing Profile Management =====

let _autoRoutingData = null;

async function loadRoutingProfiles() {
    try {
        const res = await fetch('/api/registry/auto-routing');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        _autoRoutingData = data.auto_routing;
        const allModels = data.all_chat_models || [];
        renderAutoRoutingProfile('chat', _autoRoutingData.chat, allModels);
        renderAutoRoutingProfile('agent', _autoRoutingData.agent, allModels);
    } catch (e) {
        console.error('Failed to load auto routing profiles:', e);
    }
}

function renderAutoRoutingProfile(type, profile, allModels) {
    const pickerSelect = document.getElementById(`auto-routing-${type}-picker`);
    const modelList = document.getElementById(`auto-routing-${type}-models`);
    if (!pickerSelect || !modelList) return;

    const currentPicker = profile?.route_picker || '';
    const pool = profile?.models || {};

    // Populate route picker dropdown
    pickerSelect.innerHTML = allModels.map(mid =>
        `<option value="${mid}" ${mid === currentPicker ? 'selected' : ''}>${mid}</option>`
    ).join('');

    // Populate model toggle list
    if (Object.keys(pool).length === 0) {
        modelList.innerHTML = '<div class="placeholder-text">No chat models configured.</div>';
        return;
    }

    modelList.innerHTML = Object.entries(pool).map(([modelId, cfg]) => {
        const enabled = cfg.enabled !== false;
        const desc = cfg.description || '';
        const provider = cfg.provider || '';
        return `
            <div class="routing-model-item" data-model="${modelId}" data-type="${type}">
                <label class="switch small">
                    <input type="checkbox" class="routing-model-toggle" data-model="${modelId}" ${enabled ? 'checked' : ''}>
                    <span class="slider round"></span>
                </label>
                <div class="routing-model-info">
                    <span class="routing-model-id">${modelId}</span>
                    ${provider ? `<span class="routing-model-provider">${provider}</span>` : ''}
                    ${desc ? `<span class="routing-model-desc">${desc}</span>` : ''}
                </div>
            </div>`;
    }).join('');
}

async function saveAutoRoutingProfile(type) {
    if (!_autoRoutingData) return;

    const pickerSelect = document.getElementById(`auto-routing-${type}-picker`);
    const modelList = document.getElementById(`auto-routing-${type}-models`);
    if (!pickerSelect || !modelList) return;

    const routePicker = pickerSelect.value;
    const models = {};
    modelList.querySelectorAll('.routing-model-item').forEach(item => {
        const modelId = item.dataset.model;
        const toggle = item.querySelector('.routing-model-toggle');
        models[modelId] = { enabled: toggle ? toggle.checked : true };
    });

    _autoRoutingData[type] = { route_picker: routePicker, models };

    try {
        const res = await fetch('/api/registry/auto-routing', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ auto_routing: _autoRoutingData })
        });
        if (res.ok) {
            showNotification(`Auto Routing (${type}) saved.`, 'success');
        } else {
            showNotification('Failed to save auto routing config.', 'error');
        }
    } catch (e) {
        showNotification('Network error saving auto routing.', 'error');
    }
}

// ===== Version Control & Update Checker =====
const REMOTE_VERSION_URL = "https://raw.githubusercontent.com/Aethvion/Misaka-Cipher/main/core/interfaces/dashboard/static/assets/system-status.json";

async function checkForUpdates(manual = false) {
    try {
        // Fetch local version
        const localResp = await fetch('/static/assets/system-status.json');
        const localData = await localResp.json();
        const localVersion = parseFloat(localData.system.version) || 0;
        
        // Show loading if manual
        const btn = document.getElementById('settings-check-update-btn');
        if (manual && btn) {
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Checking...';
            btn.disabled = true;
        }

        // Fetch remote version
        const remoteResp = await fetch(REMOTE_VERSION_URL, { cache: "no-store" });
        if (!remoteResp.ok) throw new Error("Failed to fetch remote status");
        
        const remoteData = await remoteResp.json();
        const remoteVersion = parseFloat(remoteData.system.version) || 0;

        const isUpdateAvailable = remoteVersion > localVersion;

        if (manual && btn) {
            btn.innerHTML = isUpdateAvailable ? '<i class="fas fa-download"></i> Update Available on GitHub' : '<i class="fas fa-check"></i> Up to Date';
            btn.disabled = false;
        }

        // Render dot in sidebar if update available
        const dot = document.getElementById('sidebar-version-dot');
        if (dot) dot.style.display = isUpdateAvailable ? 'block' : 'none';

        if (manual || document.getElementById('settings-version-banner')) {
            renderVersionTabContent(localData, remoteData, isUpdateAvailable);
        }

        return isUpdateAvailable;
    } catch (err) {
        console.error("Update check failed:", err);
        const btn = document.getElementById('settings-check-update-btn');
        if (manual && btn) {
            btn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Check Failed';
            btn.disabled = false;
        }
        return false;
    }
}

async function renderVersionTabContent(localData = null, remoteData = null, isUpdateAvailable = false) {
    if (!localData) {
        try {
            const resp = await fetch('/static/assets/system-status.json');
            localData = await resp.json();
        } catch (e) {
            console.error("Failed to load local version data");
            return;
        }
    }

    const localInfo = document.getElementById('local-version-info');
    const versionBanner = document.getElementById('settings-version-banner');
    const changelogList = document.getElementById('settings-changelog-list');
    
    // 1. Render Local Info Box
    if (localInfo) {
        localInfo.innerHTML = `
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="font-size: 2rem;">🛡️</div>
                <div>
                    <div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; color: var(--text-secondary);">Currently Installed</div>
                    <div style="font-size: 1.25rem; font-weight: bold; color: var(--primary);">Misaka Cipher v${localData.system.version}</div>
                    <div style="font-size: 0.8rem; color: var(--text-secondary);">Build Sync: ${localData.system.last_sync || 'Unknown'}</div>
                </div>
            </div>
        `;
    }

    // 2. Render Update Banner
    if (versionBanner) {
        if (isUpdateAvailable && remoteData) {
            versionBanner.innerHTML = `
                <div style="margin-top: 15px; padding: 15px; background: rgba(85, 239, 196, 0.1); border-left: 4px solid #55efc4; border-radius: 4px; display: flex; align-items: center; gap: 15px;">
                    <div style="font-size: 1.5rem;">🚀</div>
                    <div style="flex: 1;">
                        <strong style="color: #55efc4; font-size: 1rem;">Update Available!</strong>
                        <div style="font-size: 0.9rem; color: var(--text-secondary); margin-top: 4px;">
                            Version <strong>${remoteData.system.version}</strong> is now live on GitHub.
                        </div>
                    </div>
                    <a href="https://github.com/Aethvion/Misaka-Cipher" target="_blank" class="action-btn small primary" style="text-decoration: none;">View Repo</a>
                </div>
            `;
        } else if (remoteData) {
            versionBanner.innerHTML = `
                <div style="margin-top: 15px; padding: 12px; border-radius: 4px; border: 1px solid var(--border); background: rgba(255,255,255,0.02); display: flex; align-items: center; gap: 10px;">
                    <i class="fas fa-check-circle" style="color:#55efc4;"></i>
                    <span style="font-size: 0.9rem; color: var(--text-secondary);">System is up to date. No new versions found.</span>
                </div>
            `;
        } else {
            versionBanner.innerHTML = '';
        }
    }

    // 3. Render Version-Grouped Changelog
    if (changelogList) {
        const dataToUse = (remoteData && remoteData.system.changelog) ? remoteData.system.changelog : localData.system.changelog;
        
        if (dataToUse && Array.isArray(dataToUse)) {
            // Sort versions descending (assuming semver or incremental strings/numbers)
            const sorted = [...dataToUse].sort((a, b) => b.version.localeCompare(a.version, undefined, {numeric: true, sensitivity: 'base'}));
            
            changelogList.innerHTML = sorted.map(entry => {
                const isCurrent = entry.version === localData.system.version;
                const highlightStyle = isCurrent ? 'border-left: 3px solid var(--primary); background: rgba(0, 217, 255, 0.03);' : '';
                const currentBadge = isCurrent ? '<span style="background: var(--primary); color: #000; font-size: 0.65rem; padding: 2px 6px; border-radius: 3px; font-weight: bold; margin-left: 10px;">INSTALLED</span>' : '';

                return `
                    <div style="margin-bottom: 25px; padding: 15px; border-radius: 8px; border: 1px solid var(--border); ${highlightStyle}">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <div style="font-weight: bold; color: var(--text-primary); font-size: 1.1rem;">
                                Version ${entry.version} ${currentBadge}
                            </div>
                            <div style="font-size: 0.8rem; color: var(--text-secondary);">${entry.date || ''}</div>
                        </div>
                        <ul style="margin: 0; padding-left: 20px; color: var(--text-secondary);">
                            ${entry.changes.map(change => `<li style="margin-bottom: 5px;">${change}</li>`).join('')}
                        </ul>
                    </div>
                `;
            }).join('');
        } else {
            changelogList.innerHTML = '<li style="color:var(--text-secondary);">No changelog data available.</li>';
        }
    }
}

function runStartupUpdateCheck() {
    // 1. Always check once on startup/page load
    console.log("Running startup update check...");
    checkForUpdates(false);

    // 2. Set interval to check once every 24 hours for long-running sessions
    const ONE_DAY = 24 * 60 * 60 * 1000;
    setInterval(() => {
        console.log("Running scheduled daily update check...");
        checkForUpdates(false);
    }, ONE_DAY);
}
window.checkForUpdates = checkForUpdates;
window.runStartupUpdateCheck = runStartupUpdateCheck;

// Initialize Manual Update Button
document.addEventListener('click', (e) => {
    if (e.target && e.target.id === 'settings-check-update-btn') {
        checkForUpdates(true);
    } else if (e.target && e.target.closest('#settings-check-update-btn')) {
        checkForUpdates(true);
    }
});


// ===== Discord Worker Management =====

let _discordStatusInterval = null;

function initDiscordSettings() {
    const tokenInput = document.getElementById('setting-discord-token');
    const toggleBtn = document.getElementById('toggle-discord-token-visibility');
    const startBtn = document.getElementById('btn-discord-start');
    const stopBtn = document.getElementById('btn-discord-stop');

    if (tokenInput) {
        tokenInput.value = prefs.get('nexus.discord_link.bot_token', '');
        tokenInput.onchange = async (e) => {
            await savePreference('nexus.discord_link.bot_token', e.target.value.trim());
        };
    }

    if (toggleBtn && tokenInput) {
        toggleBtn.onclick = () => {
            const isPassword = tokenInput.type === 'password';
            tokenInput.type = isPassword ? 'text' : 'password';
            toggleBtn.innerHTML = isPassword ? '<i class="fas fa-eye-slash"></i>' : '<i class="fas fa-eye"></i>';
        };
    }

    if (startBtn) {
        startBtn.onclick = async () => {
            startBtn.disabled = true;
            startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> STARTING...';
            try {
                const res = await fetch('/api/discord/start', { method: 'POST' });
                const data = await res.json();
                if (res.ok) {
                    showNotification('Discord Worker starting...', 'success');
                    setTimeout(loadDiscordStatus, 2000);
                } else {
                    showNotification(data.detail || 'Failed to start Discord Worker', 'error');
                }
            } catch (e) {
                showNotification('Network error starting worker', 'error');
            } finally {
                startBtn.disabled = false;
                startBtn.innerHTML = '<i class="fas fa-play"></i> START WORKER';
            }
        };
    }

    if (stopBtn) {
        stopBtn.onclick = async () => {
            stopBtn.disabled = true;
            stopBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> STOPPING...';
            try {
                const res = await fetch('/api/discord/stop', { method: 'POST' });
                if (res.ok) {
                    showNotification('Discord Worker stopped', 'success');
                    loadDiscordStatus();
                } else {
                    showNotification('Failed to stop Discord Worker', 'error');
                }
            } catch (e) {
                showNotification('Network error stopping worker', 'error');
            } finally {
                stopBtn.disabled = false;
                stopBtn.innerHTML = '<i class="fas fa-stop"></i> STOP WORKER';
            }
        };
    }

    // Start polling if not already
    if (!_discordStatusInterval) {
        _discordStatusInterval = setInterval(loadDiscordStatus, 5000);
    }
}

async function loadDiscordStatus() {
    // Only poll if the discord panel is active or if we're just starting
    const panel = document.getElementById('settings-panel-discord');
    if (!panel || !panel.classList.contains('active')) {
        return;
    }

    try {
        const res = await fetch('/api/discord/status');
        if (!res.ok) return;
        const status = await res.json();
        updateDiscordUI(status);
    } catch (e) {
        console.warn('Failed to fetch Discord status:', e);
    }
}

function updateDiscordUI(status) {
    const badge = document.getElementById('discord-status-badge');
    const userDisplay = document.getElementById('discord-bot-user');
    const guildsDisplay = document.getElementById('discord-bot-guilds');
    const startBtn = document.getElementById('btn-discord-start');
    const stopBtn = document.getElementById('btn-discord-stop');

    if (!badge || !userDisplay || !guildsDisplay) return;

    // Status Badge
    badge.className = `status-badge ${status.status}`;
    badge.querySelector('.status-text').textContent = status.status.toUpperCase();

    // Vitals
    userDisplay.textContent = status.user || (status.status === 'offline' ? 'Not Connected' : 'Connecting...');
    guildsDisplay.textContent = status.guilds || 0;

    // Buttons
    if (startBtn) startBtn.disabled = (status.status === 'online' || status.status === 'connecting');
    if (stopBtn) stopBtn.disabled = (status.status === 'offline');
    
    if (status.status === 'error' && status.error) {
        userDisplay.textContent = 'ERROR';
        userDisplay.title = status.error;
    }
}

