// Aethvion Suite - Preferences & Settings View
// Handles interacting with user preferences and provider configuration data


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
        const currentSpeed = prefs.get('assistant.typing_speed', 75);
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

    const infoModel = document.getElementById('setting-info-model');
    if (infoModel) {
        infoModel.onchange = async (e) => {
            await savePreference('system.info_model', e.target.value);
        };
    }

    const misakaTypingSpeed = document.getElementById('setting-misakacipher-typing-speed');
    const misakaTypingVal = document.getElementById('setting-misakacipher-typing-speed-val');
    if (misakaTypingSpeed && misakaTypingVal) {
        const currentSpeed = prefs.get('misakacipher.typing_speed', 75);
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

    // Hide Character / Particle Sphere toggle
    const hideCharToggle = document.getElementById('setting-misakacipher-hide-character');
    if (hideCharToggle) {
        hideCharToggle.checked = prefs.get('misakacipher.hide_character', false);
        hideCharToggle.onchange = async (e) => {
            await savePreference('misakacipher.hide_character', e.target.checked);
            window.dispatchEvent(new CustomEvent('misakaSettingsUpdated', {
                detail: { hide_character: e.target.checked }
            }));
        };
    }

    // Reset button
    const resetBtn = document.getElementById('misaka-reset-btn');
    if (resetBtn) {
        resetBtn.addEventListener('click', async () => {
            const confirmed = confirm(
                'This will permanently delete all of Misaka Cipher\'s conversation history and memory.\n\nAre you sure?'
            );
            if (!confirmed) return;

            resetBtn.disabled = true;
            resetBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Resetting…';

            try {
                const res = await fetch('/api/misakacipher/reset', { method: 'POST' });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || `HTTP ${res.status}`);
                }
                resetBtn.innerHTML = '<i class="fas fa-check"></i> Reset complete';
                resetBtn.style.background = 'rgba(34,197,94,0.15)';
                resetBtn.style.borderColor = 'rgba(34,197,94,0.4)';
                resetBtn.style.color = 'rgba(34,197,94,0.9)';
                setTimeout(() => {
                    resetBtn.disabled = false;
                    resetBtn.innerHTML = '<i class="fas fa-trash-alt"></i> Reset Misaka Cipher';
                    resetBtn.style.cssText = '';
                }, 3000);
            } catch (e) {
                resetBtn.disabled = false;
                resetBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Reset failed';
                resetBtn.style.background = 'rgba(239,68,68,0.15)';
                resetBtn.style.borderColor = 'rgba(239,68,68,0.4)';
                resetBtn.style.color = 'rgba(239,68,68,0.9)';
                console.error('[Misaka Reset]', e);
                setTimeout(() => {
                    resetBtn.innerHTML = '<i class="fas fa-trash-alt"></i> Reset Misaka Cipher';
                    resetBtn.style.cssText = '';
                }, 3000);
            }
        });
    }

    // ── Global Companion Settings ────────────────────────────────────────────
    _bindRangeWithDisplay(
        'setting-companions-global-typing-speed',
        'setting-companions-global-typing-speed-val',
        'companions.global.typing_speed',
        75,
        (val) => window.dispatchEvent(new CustomEvent('companionSettingsUpdated', { detail: { typing_speed: val } }))
    );

    _bindToggle('setting-companions-global-typing-indicator', 'companions.global.typing_indicator', true);
    _bindToggle('setting-companions-global-sounds',           'companions.global.sounds',           false);
    _bindToggle('setting-companions-global-popups',           'companions.global.popups',           true);

    // ── Axiom Settings ────────────────────────────────────────────────────────
    _bindRangeWithDisplay(
        'setting-axiom-context-limit',
        'setting-axiom-context-limit-val',
        'axiom.context_limit',
        8,
        (val) => window.dispatchEvent(new CustomEvent('axiomSettingsUpdated', { detail: { context_limit: val } }))
    );

    const axiomModelEl = document.getElementById('setting-axiom-model');
    if (axiomModelEl) {
        axiomModelEl.onchange = async (e) => {
            await savePreference('axiom.model', e.target.value);
            window.dispatchEvent(new CustomEvent('axiomSettingsUpdated', { detail: { model: e.target.value } }));
        };
    }

    // Axiom proactive settings
    for (const item of [
        { id: 'setting-axiom-proactive-enabled',    pref: 'axiom.proactive_enabled',     type: 'toggle', default: false },
        { id: 'setting-axiom-proactive-popup',       pref: 'axiom.proactive_popup',       type: 'toggle', default: true  },
        { id: 'setting-axiom-startup-hours',         pref: 'axiom.startup_trigger_hours', type: 'range',  default: 4,  valId: 'setting-axiom-startup-hours-val' },
        { id: 'setting-axiom-startup-chance',        pref: 'axiom.startup_chance',        type: 'range',  default: 75, valId: 'setting-axiom-startup-chance-val' },
        { id: 'setting-axiom-startup-delay-min',     pref: 'axiom.startup_delay_min',     type: 'range',  default: 10, valId: 'setting-axiom-startup-delay-min-val' },
        { id: 'setting-axiom-startup-delay-max',     pref: 'axiom.startup_delay_max',     type: 'range',  default: 45, valId: 'setting-axiom-startup-delay-max-val' },
        { id: 'setting-axiom-session-interval-min',  pref: 'axiom.session_interval_min',  type: 'range',  default: 45, valId: 'setting-axiom-session-interval-min-val' },
        { id: 'setting-axiom-session-interval-max',  pref: 'axiom.session_interval_max',  type: 'range',  default: 90, valId: 'setting-axiom-session-interval-max-val' },
        { id: 'setting-axiom-session-chance',        pref: 'axiom.session_chance',        type: 'range',  default: 60, valId: 'setting-axiom-session-chance-val' },
    ]) {
        if (item.type === 'toggle') {
            _bindToggle(item.id, item.pref, item.default,
                (val) => window.dispatchEvent(new CustomEvent('axiomSettingsUpdated', { detail: { [item.pref.split('.').pop()]: val } }))
            );
        } else {
            _bindRangeWithDisplay(item.id, item.valId, item.pref, item.default,
                (val) => window.dispatchEvent(new CustomEvent('axiomSettingsUpdated', { detail: { [item.pref.split('.').pop()]: val } }))
            );
        }
    }

    // Axiom reset button
    const axiomResetBtn = document.getElementById('axiom-reset-btn');
    if (axiomResetBtn) {
        axiomResetBtn.addEventListener('click', async () => {
            if (!confirm('This will permanently delete all of Axiom\'s conversation history and memory.\n\nAre you sure?')) return;
            try {
                axiomResetBtn.disabled = true;
                axiomResetBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Resetting...';
                const res = await fetch('/api/axiom/reset', { method: 'POST' });
                if (!res.ok) throw new Error((await res.json()).detail || 'Reset failed');
                axiomResetBtn.innerHTML = '<i class="fas fa-check"></i> Reset Complete';
                setTimeout(() => { axiomResetBtn.disabled = false; axiomResetBtn.innerHTML = '<i class="fas fa-trash-alt"></i> Reset Axiom'; }, 3000);
            } catch (e) {
                console.error('[Axiom Reset]', e);
                axiomResetBtn.disabled = false;
                axiomResetBtn.innerHTML = '<i class="fas fa-trash-alt"></i> Reset Axiom';
            }
        });
    }

    // ── Lyra Settings ─────────────────────────────────────────────────────────
    _bindRangeWithDisplay(
        'setting-lyra-context-limit',
        'setting-lyra-context-limit-val',
        'lyra.context_limit',
        8,
        (val) => window.dispatchEvent(new CustomEvent('lyraSettingsUpdated', { detail: { context_limit: val } }))
    );

    const lyraModelEl = document.getElementById('setting-lyra-model');
    if (lyraModelEl) {
        lyraModelEl.onchange = async (e) => {
            await savePreference('lyra.model', e.target.value);
            window.dispatchEvent(new CustomEvent('lyraSettingsUpdated', { detail: { model: e.target.value } }));
        };
    }

    // Lyra proactive settings
    for (const item of [
        { id: 'setting-lyra-proactive-enabled',    pref: 'lyra.proactive_enabled',     type: 'toggle', default: false },
        { id: 'setting-lyra-proactive-popup',       pref: 'lyra.proactive_popup',       type: 'toggle', default: true  },
        { id: 'setting-lyra-startup-hours',         pref: 'lyra.startup_trigger_hours', type: 'range',  default: 4,  valId: 'setting-lyra-startup-hours-val' },
        { id: 'setting-lyra-startup-chance',        pref: 'lyra.startup_chance',        type: 'range',  default: 75, valId: 'setting-lyra-startup-chance-val' },
        { id: 'setting-lyra-startup-delay-min',     pref: 'lyra.startup_delay_min',     type: 'range',  default: 10, valId: 'setting-lyra-startup-delay-min-val' },
        { id: 'setting-lyra-startup-delay-max',     pref: 'lyra.startup_delay_max',     type: 'range',  default: 45, valId: 'setting-lyra-startup-delay-max-val' },
        { id: 'setting-lyra-session-interval-min',  pref: 'lyra.session_interval_min',  type: 'range',  default: 45, valId: 'setting-lyra-session-interval-min-val' },
        { id: 'setting-lyra-session-interval-max',  pref: 'lyra.session_interval_max',  type: 'range',  default: 90, valId: 'setting-lyra-session-interval-max-val' },
        { id: 'setting-lyra-session-chance',        pref: 'lyra.session_chance',        type: 'range',  default: 60, valId: 'setting-lyra-session-chance-val' },
    ]) {
        if (item.type === 'toggle') {
            _bindToggle(item.id, item.pref, item.default,
                (val) => window.dispatchEvent(new CustomEvent('lyraSettingsUpdated', { detail: { [item.pref.split('.').pop()]: val } }))
            );
        } else {
            _bindRangeWithDisplay(item.id, item.valId, item.pref, item.default,
                (val) => window.dispatchEvent(new CustomEvent('lyraSettingsUpdated', { detail: { [item.pref.split('.').pop()]: val } }))
            );
        }
    }

    // Lyra reset button
    const lyraResetBtn = document.getElementById('lyra-reset-btn');
    if (lyraResetBtn) {
        lyraResetBtn.addEventListener('click', async () => {
            if (!confirm('This will permanently delete all of Lyra\'s conversation history and memory.\n\nAre you sure?')) return;
            try {
                lyraResetBtn.disabled = true;
                lyraResetBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Resetting...';
                const res = await fetch('/api/lyra/reset', { method: 'POST' });
                if (!res.ok) throw new Error((await res.json()).detail || 'Reset failed');
                lyraResetBtn.innerHTML = '<i class="fas fa-check"></i> Reset Complete';
                setTimeout(() => { lyraResetBtn.disabled = false; lyraResetBtn.innerHTML = '<i class="fas fa-trash-alt"></i> Reset Lyra'; }, 3000);
            } catch (e) {
                console.error('[Lyra Reset]', e);
                lyraResetBtn.disabled = false;
                lyraResetBtn.innerHTML = '<i class="fas fa-trash-alt"></i> Reset Lyra';
            }
        });
    }

    // Initialize Other Sections
    loadGlobalSettings();
    initDevMode();
    loadMisakaWorkspaces();
    loadNexusModules();
}

// ── Companion Accordion toggle ────────────────────────────────────────────────

function toggleCompanionAccordion(id) {
    const body    = document.getElementById(`accordion-body-${id}`);
    const chevron = document.getElementById(`chevron-${id}`);
    if (!body) return;
    const isOpen = body.style.display !== 'none';
    body.style.display = isOpen ? 'none' : '';
    if (chevron) chevron.classList.toggle('open', !isOpen);
}

// ── Reusable binding helpers ──────────────────────────────────────────────────

function _bindRangeWithDisplay(rangeId, displayId, prefKey, defaultVal, onChange) {
    const rangeEl   = document.getElementById(rangeId);
    const displayEl = document.getElementById(displayId);
    if (!rangeEl) return;
    const current = prefs.get(prefKey, defaultVal);
    rangeEl.value = current;
    if (displayEl) displayEl.textContent = current;
    rangeEl.oninput = (e) => { if (displayEl) displayEl.textContent = e.target.value; };
    rangeEl.onchange = async (e) => {
        const val = parseFloat(e.target.value);
        await savePreference(prefKey, val);
        if (onChange) onChange(val);
    };
}

function _bindToggle(checkboxId, prefKey, defaultVal, onChange) {
    const el = document.getElementById(checkboxId);
    if (!el) return;
    el.checked = prefs.get(prefKey, defaultVal);
    el.onchange = async (e) => {
        await savePreference(prefKey, e.target.checked);
        if (onChange) onChange(e.target.checked);
    };
}

async function savePreference(key, value) {
    await prefs.set(key, value);
}
// Expose globally for dynamic companion loader
window.savePreference = savePreference;

// Populate a <select> with chat model options and restore a saved value
window._populateModelSelect = function(sel, prefModel) {
    if (!sel) return;
    // If generateCategorizedModelOptions is available (models already loaded), use cached HTML
    if (window._cachedChatModelOptions) {
        sel.innerHTML = window._cachedChatModelOptions;
    } else {
        const opt = document.createElement('option');
        opt.value = prefModel;
        opt.textContent = prefModel;
        sel.innerHTML = '';
        sel.appendChild(opt);
    }
    if (prefModel && sel.querySelector(`option[value="${prefModel}"]`)) {
        sel.value = prefModel;
    }
};

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
    showToast(`${moduleId} settings saved!`, 'success');
}

async function authorizeNexusModule(moduleId) {
    if (moduleId === 'spotify') {
        const settings = {
            client_id: prefs.get('nexus.spotify.client_id', ''),
            client_secret: prefs.get('nexus.spotify.client_secret', ''),
            redirect_uri: prefs.get('nexus.spotify.redirect_uri', 'http://localhost:8080/callback')
        };

        if (!settings.client_id || !settings.client_secret) {
            showToast('Please enter and save your Spotify Client ID and Secret first.', 'warn');
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
            showToast('Spotify auth error: ' + e.message, 'error');
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
            showToast('Error: ' + (err.detail || 'Unknown error'), 'error');
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
            if (title) showToast(title, 'info', 4000);
        });
    });
}

// ===== Provider & Profile Management =====

let _registryData = null;
let _localModelsStatus = {}; // { filename: { exists: bool, size_mb: num } }
let _suggestedModels = {};
let _settingsDirty = false;
let _activeRegistryTab = null;

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
        const [regRes, sugRes, localRes] = await Promise.all([
            fetch('/api/registry'),
            fetch('/api/registry/suggested'),
            fetch('/api/registry/local/models/status')
        ]);

        if (regRes.ok) _registryData = await regRes.json();
        if (sugRes.ok) _suggestedModels = await sugRes.json();
        if (localRes.ok) {
            const localData = await localRes.json();
            _localModelsStatus = localData.models || {};
        }

        if (_registryData) {
            renderProviderCards(_registryData);
            renderProfiles();
        }
        initProfileCreationButtons();
        initProviderCreationButtons();

        const pSaveBtn = document.getElementById('save-provider-settings');
        if (pSaveBtn) pSaveBtn.onclick = saveProviderSettings;

        // Privacy Mode toggle (lives on the System sub-panel)
        if (typeof initPrivacyToggle === 'function') initPrivacyToggle();
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
        document.getElementById('setting-misakacipher-model'),
        document.getElementById('setting-axiom-model'),
        document.getElementById('setting-lyra-model'),
        document.getElementById('setting-info-model'),
        document.getElementById('overlay-model')
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
        window._cachedChatModelOptions = chatOptions; // cache for dynamic selects

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
            } else if (sel.id === 'setting-axiom-model') {
                const prefModel = prefs.get('axiom.model', 'gemini-1.5-flash');
                if (sel.querySelector(`option[value="${prefModel}"]`)) {
                    sel.value = prefModel;
                }
            } else if (sel.id === 'setting-lyra-model') {
                const prefModel = prefs.get('lyra.model', 'gemini-1.5-flash');
                if (sel.querySelector(`option[value="${prefModel}"]`)) {
                    sel.value = prefModel;
                }
            } else if (sel.id === 'setting-info-model') {
                const prefModel = prefs.get('system.info_model', 'flash');
                if (sel.querySelector(`option[value="${prefModel}"]`)) {
                    sel.value = prefModel;
                }
            } else if (sel.id === 'overlay-model') {
                // Restored separately by loadOverlaySettings() after config is fetched
                // Keep current selection if still valid, otherwise leave at default
                if (currentVal && sel.querySelector(`option[value="${currentVal}"]`)) {
                    sel.value = currentVal;
                }
            } else if (currentVal && sel.querySelector(`option[value="${currentVal}"]`)) {
                sel.value = currentVal;
            }
        });

    } catch (err) {
        console.error('Error loading chat models:', err);
    }
}

function renderProviderCards(registry) {
    const container = document.getElementById('provider-cards-container');
    if (!container) return;

    const providers = registry.providers || {};
    const names = Object.keys(providers);
    if (!names.length) {
        container.innerHTML = '<div class="placeholder-text">No providers found.</div>';
        return;
    }

    // Pick initial tab (preserve selection if still valid)
    if (!_activeRegistryTab || !providers[_activeRegistryTab]) {
        _activeRegistryTab = names[0];
    }

    // Build tab bar
    let tabsHtml = '<div class="registry-tabs-bar">';
    for (const name of names) {
        const cfg = providers[name];
        const isActive = (cfg.chat_config?.active || cfg.agent_config?.active);
        const isSelected = name === _activeRegistryTab;
        tabsHtml += `
            <button class="registry-tab${isSelected ? ' active' : ''}" data-tab="${name}" onclick="selectRegistryTab('${name}')">
                <span class="registry-tab-dot${isActive ? ' active' : ''}"></span>
                ${name}
            </button>`;
    }
    tabsHtml += '</div>';
    tabsHtml += '<div id="registry-tab-content"></div>';

    container.innerHTML = tabsHtml;

    const saveBtn = document.getElementById('save-provider-settings');
    if (saveBtn) saveBtn.onclick = saveProviderSettings;

    _renderActiveTabContent();
}

function _renderActiveTabContent() {
    const content = document.getElementById('registry-tab-content');
    if (!content || !_registryData || !_activeRegistryTab) return;

    const config = (_registryData.providers || {})[_activeRegistryTab];
    if (!config) { content.innerHTML = '<div class="placeholder-text">Provider not found.</div>'; return; }

    content.innerHTML = _buildProviderHtml(_activeRegistryTab, config);
    _bindProviderTabEvents(content, _activeRegistryTab);
}

function _buildProviderHtml(name, config) {
    const isActive = (config.chat_config?.active || config.agent_config?.active);
    const modelsHtml = Object.entries(config.models || {}).map(([key, m]) => {
        const caps = Array.isArray(m.capabilities) ? m.capabilities : [];
        const desc = (typeof m === 'object' && m.description) ? m.description : '';

        let localStatusHtml = '';
        if (name === 'local') {
            const status = _localModelsStatus[key] || { exists: false };
            if (status.exists) {
                localStatusHtml = `<span style="color:#00ff88; font-size:0.7rem;"><i class="fas fa-check-circle"></i> ${status.size_mb} MB</span>`;
            } else {
                localStatusHtml = `<button class="action-btn xs-btn download-local-btn" data-model="${key}" title="Download from HuggingFace"><i class="fas fa-download"></i> Download</button>`;
            }
        }

        return `
            <tr class="model-main-row" data-model="${key}">
                <td>
                    <div style="display:flex; flex-direction:column; gap:4px;">
                        <input type="text" class="model-id-input-small" value="${key}" data-key="${key}">
                        ${localStatusHtml}
                    </div>
                </td>
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
            ${renderAudioConfigRow(key, m)}`;
    }).join('');

    return `
        <div class="compact-provider-item${isActive ? ' active' : ''}" data-provider="${name}">
            <div class="provider-models-foldout" style="display:block;">
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
                    <tbody>${modelsHtml}</tbody>
                </table>
                <div class="add-model-line">
                    <button class="action-btn xs-btn secondary add-model-btn" data-provider="${name}">+ Add Model</button>
                    <button class="action-btn xs-btn secondary suggested-model-btn" data-provider="${name}"><i class="fas fa-magic"></i> Suggested</button>
                </div>
            </div>
        </div>`;
}

function _bindProviderTabEvents(container, name) {
    container.querySelectorAll('.toggle-image-settings').forEach(btn => {
        btn.onclick = (e) => {
            const modelKey = btn.dataset.model;
            const row = container.querySelector(`.image-config-row[data-model="${modelKey}"]`);
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
            const row = container.querySelector(`.audio-config-row[data-model="${modelKey}"]`);
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
        t.onchange = () => {
            const item = t.closest('.compact-provider-item');
            const isActive = item.querySelector('.chat-active-toggle').checked || item.querySelector('.agent-active-toggle').checked;
            item.classList.toggle('active', isActive);
            // Sync tab dot
            const dot = document.querySelector(`.registry-tab[data-tab="${name}"] .registry-tab-dot`);
            if (dot) dot.classList.toggle('active', isActive);
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

    container.querySelectorAll('.download-local-btn').forEach(btn => {
        btn.onclick = async () => {
            const modelKey = btn.dataset.model;
            let repoId = "unsloth/Llama-3.2-1B-Instruct-GGUF";
            let filename = modelKey;

            if (confirm(`Download ${modelKey} from HuggingFace? This might take a few minutes.`)) {
                btn.disabled = true;
                btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Downloading...';
                try {
                    const res = await fetch('/api/registry/local/download', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ repo_id: repoId, filename: filename })
                    });
                    const result = await res.json();
                    if (res.ok) {
                        showNotification(result.message, 'success');
                        await loadProviderSettings();
                    } else {
                        showNotification(result.detail || 'Download failed', 'error');
                        btn.disabled = false;
                        btn.innerHTML = '<i class="fas fa-download"></i> Download';
                    }
                } catch (e) {
                    showNotification('Error connecting to download service', 'error');
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-download"></i> Download';
                }
            }
        };
    });
}

function selectRegistryTab(name) {
    if (!_registryData?.providers[name]) return;
    // Sync current tab data before switching
    if (_activeRegistryTab && _activeRegistryTab !== name) {
        _syncActiveTabToRegistry();
    }
    _activeRegistryTab = name;
    document.querySelectorAll('.registry-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === name);
    });
    _renderActiveTabContent();
}

function _syncActiveTabToRegistry() {
    if (!_activeRegistryTab || !_registryData) return;
    const content = document.getElementById('registry-tab-content');
    if (!content) return;
    const item = content.querySelector('.compact-provider-item');
    if (!item) return;

    const prov = _registryData.providers[_activeRegistryTab];
    if (!prov) return;

    prov.chat_config = { active: true, priority: 1 };
    prov.agent_config = { active: true, priority: 1 };

    prov.models = {};
    item.querySelectorAll('tbody tr.model-main-row').forEach(row => {
        const modelName = row.querySelector('.model-id-input-small')?.value.trim();
        if (!modelName) return;

        const costIn = parseFloat(row.querySelector('.model-cost-in')?.value || 0);
        const costOut = parseFloat(row.querySelector('.model-cost-out')?.value || 0);
        const capsCell = row.querySelector('.caps-cell');
        const capabilities = capsCell ? Array.from(capsCell.querySelectorAll('.cap-tag')).map(t => t.dataset.cap) : [];
        const description = row.querySelector('.model-desc-input')?.value.trim() || '';

        const imgRow = item.querySelector(`.image-config-row[data-model="${modelName}"]`);
        let image_config = null;
        if (imgRow && capabilities.includes('IMAGE')) {
            const ar = [];
            if (imgRow.querySelector('.img-ar-1-1').checked) ar.push('1:1');
            if (imgRow.querySelector('.img-ar-16-9').checked) ar.push('16:9');
            if (imgRow.querySelector('.img-ar-9-16').checked) ar.push('9:16');
            if (imgRow.querySelector('.img-ar-custom').checked) ar.push('custom');
            const qual = imgRow.querySelector('.img-quality-options').value.split(',').map(s => s.trim()).filter(Boolean);
            image_config = {
                aspect_ratios: ar,
                quality_options: qual,
                supports_negative_prompt: imgRow.querySelector('.img-neg-prompt').checked,
                supports_seed: imgRow.querySelector('.img-supports-seed').checked
            };
        }

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
            capabilities,
            ...(description ? { description } : {}),
            ...(image_config ? { image_config } : {}),
            ...(audio_config ? { audio_config } : {})
        };
    });
}

function addModelRowInline(providerName) {
    const content = document.getElementById('registry-tab-content');
    const providerItem = content
        ? content.querySelector('.compact-provider-item')
        : document.querySelector(`.compact-provider-item[data-provider="${providerName}"]`);
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
            <button class="btn-icon xs-btn confirm-new-model" title="Save model" style="color:#00ff88"><i class="fas fa-check"></i></button>
            <button class="btn-icon xs-btn del-model" onclick="this.closest('tr').remove(); markSettingsDirty();"><i class="fas fa-trash"></i></button>
        </td>
    `;
    tbody.appendChild(row);
    // Note: We don't render image config row for new models until they get the 'image' cap
    initCapsTd(row.querySelector('.caps-cell'));

    // Confirm button — validate then auto-save so the model persists immediately
    row.querySelector('.confirm-new-model').onclick = async () => {
        const modelId = row.querySelector('.model-id-input-small').value.trim();
        if (!modelId) {
            row.querySelector('.model-id-input-small').focus();
            showNotification('Model ID is required.', 'warning');
            return;
        }
        await saveProviderSettings();
    };

    // Also save on Enter in the model ID input
    row.querySelector('.model-id-input-small').addEventListener('keydown', async (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            row.querySelector('.confirm-new-model').click();
        }
    });

    row.querySelector('input').focus();
}

async function saveProviderSettings() {
    if (!_registryData) return;

    // Sync the currently visible tab's DOM data into _registryData before saving
    _syncActiveTabToRegistry();

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

    let providerSuggested = _suggestedModels[providerName] || [];
    const providerExisting = _registryData.providers[providerName]?.models || {};

    // Special logic for Local Provider: suggest installed but unregistered models
    if (providerName === 'local') {
        try {
            const res = await fetch('/api/registry/local/models/status');
            if (res.ok) {
                const statusData = await res.json();
                // Filter out models that are already registered
                const installedUnregistered = (statusData.models || []).filter(m => {
                    const modelId = m.filename || m.id;
                    return m.exists && !providerExisting[modelId];
                }).map(m => ({
                    id: m.filename || m.id,
                    tier: 'installed',
                    input_cost: 0,
                    output_cost: 0,
                    capabilities: ['CHAT']
                }));
                
                // Merge with existing suggestions if any (unique by ID)
                const seenIds = new Set(installedUnregistered.map(m => m.id));
                providerSuggested = [...installedUnregistered, ...providerSuggested.filter(m => !seenIds.has(m.id))];
            }
        } catch (e) {
            console.warn("Failed to fetch local model status for suggestions:", e);
        }
    }

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
                    ${providerName === 'local' ? `
                        <div style="margin-top: 8px; text-align: right;">
                            <a href="#" id="go-to-local-models" style="font-size: 0.8rem; color: var(--primary); text-decoration: none;">
                                <i class="fas fa-external-link-alt"></i> Manage Local Models
                            </a>
                        </div>
                    ` : ''}
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
    const manageLink = document.getElementById('go-to-local-models');

    if (manageLink) {
        manageLink.onclick = (e) => {
            e.preventDefault();
            closeModal();
            switchMainTab('local_models');
        };
    }

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

    document.getElementById('confirm-add-model').onclick = async () => {
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
        _activeRegistryTab = providerName;
        renderProviderCards(_registryData);
        await saveRegistry();
        clearSettingsDirty();
        showNotification(`Model ${modelId} added and saved.`, 'success');
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
// Expose so other views can trigger a fresh reload of registry data + re-render
window.loadProviderSettings = loadProviderSettings;
window.toggleCompanionAccordion = toggleCompanionAccordion;

// ── Settings panel init (deferred until partial is injected) ─────────────────
let _settingsInitDone = false;

function _initSettingsPanel() {
    // Guard: partial not loaded yet if nav items are absent
    if (!document.querySelector('.settings-nav-item')) return;
    if (_settingsInitDone) return;
    _settingsInitDone = true;
    loadPreferences();
    loadProviderSettings();
    loadChatModels();
    initSettingsSubNav();
}

window.addEventListener('DOMContentLoaded', _initSettingsPanel);

document.addEventListener('panelLoaded', function (e) {
    if (e.detail.panelId === 'settings-panel') {
        _settingsInitDone = false; // allow fresh init after partial injection
        _initSettingsPanel();
    }
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
        let savedSubTab = 'system';
        if (response.ok) {
            const data = await response.json();
            if (data.value) savedSubTab = data.value;
        }
        switchSettingsSubTab(savedSubTab, false);
    } catch (e) {
        switchSettingsSubTab('system', false);
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

    if (subTab === 'assistant' || subTab === 'misakacipher') {
        loadChatModels();
    }

    if (subTab === 'extapi') {
        loadExternalApiSettings();
    }

    if (subTab === 'overlay') {
        loadOverlaySettings();
    }

    if (subTab === 'system') {
        loadDisplayTimezone();
    }

    if (subTab === 'providers') {
        loadProviderSettings();
    }

    if (subTab === 'notifications') {
        loadNotificationSettings();
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
        // 1. Fetch local version & commit info from our new API
        const localResp = await fetch('/api/system/version-info?v=' + Date.now());
        const localInfo = await localResp.json();
        
        const localVersion = parseFloat(localInfo.local.version) || 0;
        const localCommit = localInfo.local.commit || "Unknown";
        const lastUpdateCommit = localInfo.local.last_update_commit || "Unknown";

        // Show loading if manual
        const btn = document.getElementById('settings-check-update-btn');
        if (manual && btn) {
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Checking...';
            btn.disabled = true;
        }

        // 2. Fetch remote version + changelog
        const remoteResp = await fetch(REMOTE_VERSION_URL, { cache: "no-store" });
        if (!remoteResp.ok) throw new Error("Failed to fetch remote status");
        
        const remoteData = await remoteResp.json();
        const remoteVersion = parseFloat(remoteData.system.version) || 0;
        const remoteCommit = localInfo.remote.commit || "Unknown"; // From our server API check

        const isNewVersion = remoteVersion > localVersion;
        const isNewCommit = !isNewVersion && (remoteCommit !== "Unknown" && remoteCommit !== localCommit);
        const isUpdateAvailable = isNewVersion || isNewCommit;

        if (manual && btn) {
            if (isNewVersion) {
                btn.innerHTML = `<i class="fas fa-download"></i> Update to v${remoteVersion}`;
            } else if (isNewCommit) {
                btn.innerHTML = `<i class="fas fa-code-commit"></i> Update to Latest Commit`;
            } else {
                btn.innerHTML = '<i class="fas fa-check"></i> Up to Date';
            }
            btn.disabled = false;
        }

        // Render dot in sidebar if any update available
        const dot = document.getElementById('sidebar-version-dot');
        if (dot) dot.style.display = isUpdateAvailable ? 'block' : 'none';

        if (manual || document.getElementById('settings-version-banner')) {
            renderVersionTabContent(localInfo.local, remoteData, remoteCommit, isNewVersion, isNewCommit);
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

async function renderVersionTabContent(localInfo = null, remoteData = null, remoteCommit = "Unknown", isNewVersion = false, isNewCommit = false) {
    if (!localInfo) {
        try {
            const resp = await fetch('/api/system/version-info?v=' + Date.now());
            const data = await resp.json();
            localInfo = data.local;
            remoteCommit = data.remote.commit;
        } catch (e) {
            console.error("Failed to load local version data");
            return;
        }
    }

    const localInfoBox = document.getElementById('local-version-info');
    const versionBanner = document.getElementById('settings-version-banner');
    const changelogList = document.getElementById('settings-changelog-list');
    
    // 1. Render Local Info Box
    if (localInfoBox) {
        localInfoBox.innerHTML = `
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="font-size: 2rem;">🛡️</div>
                <div style="flex: 1;">
                    <div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; color: var(--text-secondary);">Currently Installed</div>
                    <div style="font-size: 1.25rem; font-weight: bold; color: var(--primary);">Aethvion Suite v${localInfo.version}</div>
                    <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 4px;">
                        <span style="opacity: 0.7;">Active Build:</span> <code style="background: rgba(0,0,0,0.2); padding: 2px 5px; border-radius: 4px; font-family: 'Fira Code', monospace;">${localInfo.commit}</code>
                        ${localInfo.last_update_commit !== localInfo.commit && localInfo.last_update_commit !== "Unknown" ? 
                            `<span style="margin-left: 10px; opacity: 0.5; font-size: 0.7rem;">(Synced from: ${localInfo.last_update_commit})</span>` : ''}
                    </div>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 0.65rem; text-transform: uppercase; color: var(--text-secondary);">Latest on GitHub</div>
                    <code style="font-size: 0.85rem; color: var(--text-bright); font-family: 'Fira Code', monospace;">${remoteCommit || 'Checking...'}</code>
                </div>
            </div>
        `;
    }

    // 2. Render Update Banner
    if (versionBanner) {
        if ((isNewVersion || isNewCommit) && remoteData) {
            const bannerTitle = isNewVersion ? "New Version Available!" : "New Patches Available";
            const bannerIcon = isNewVersion ? "🚀" : "🛠️";
            const bannerBody = isNewVersion 
                ? `Version <strong>${remoteData.system.version}</strong> is now live on GitHub.`
                : `New improvements are available for v${localInfo.version} (Commit <strong>${remoteCommit}</strong>).`;
            const btnText = isNewVersion ? `Update to v${remoteData.system.version}` : "Download Patches";

            versionBanner.innerHTML = `
                <div style="margin-top: 15px; padding: 15px; background: rgba(85, 239, 196, 0.1); border-left: 4px solid #55efc4; border-radius: 4px; display: flex; align-items: center; gap: 15px;">
                    <div style="font-size: 1.5rem;">${bannerIcon}</div>
                    <div style="flex: 1;">
                        <strong style="color: #55efc4; font-size: 1rem;">${bannerTitle}</strong>
                        <div style="font-size: 0.9rem; color: var(--text-secondary); margin-top: 4px;">
                            ${bannerBody}
                        </div>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <button id="trigger-self-update-btn" class="action-btn small primary">${btnText}</button>
                        <a href="https://github.com/Aethvion/Aethvion-Suite" target="_blank" class="action-btn small secondary" style="text-decoration: none;">View Repo</a>
                    </div>
                </div>
            `;
            
            // Re-attach button listener
            setTimeout(() => {
                const updateBtn = document.getElementById('trigger-self-update-btn');
                if (updateBtn) updateBtn.onclick = () => triggerSelfUpdate();
            }, 100);
        } else if (remoteData) {
            versionBanner.innerHTML = `
                <div style="margin-top: 15px; padding: 12px; border-radius: 4px; border: 1px solid var(--border); background: rgba(255,255,255,0.02); display: flex; align-items: center; gap: 10px;">
                    <i class="fas fa-check-circle" style="color:#55efc4;"></i>
                    <span style="font-size: 0.9rem; color: var(--text-secondary);">Aethvion Suite is up to date (Patch ${localInfo.commit}).</span>
                </div>
            `;
        } else {
            versionBanner.innerHTML = '';
        }
    }

    // 3. Render Version-Grouped Changelog
    if (changelogList) {
        const dataToUse = (remoteData && remoteData.system.changelog) ? remoteData.system.changelog : (localInfo.changelog || []);
        
        if (dataToUse && Array.isArray(dataToUse)) {
            // Sort versions descending
            const sorted = [...dataToUse].sort((a, b) => b.version.localeCompare(a.version, undefined, {numeric: true, sensitivity: 'base'}));
            
            changelogList.innerHTML = '';
            sorted.forEach(entry => {
                const isCurrent = entry.version === localInfo.version;
                const highlightStyle = isCurrent ? 'border-left: 3px solid var(--primary); background: rgba(0, 217, 255, 0.03);' : '';
                const currentBadge = isCurrent ? '<span style="background: var(--primary); color: #000; font-size: 0.65rem; padding: 2px 6px; border-radius: 3px; font-weight: bold; margin-left: 10px;">INSTALLED</span>' : '';
                
                // Calculate summaries
                const counts = {
                    added: (entry.added || []).length,
                    improved: (entry.improved || []).length,
                    changed: (entry.changed || []).length,
                    fixed: (entry.fixed || []).length,
                    upgraded: (entry.upgraded || []).length,
                    removed: (entry.removed || []).length
                };
                
                let summaryParts = [];
                if (counts.added) summaryParts.push(`${counts.added} added`);
                if (counts.improved) summaryParts.push(`${counts.improved} improved`);
                if (counts.changed) summaryParts.push(`${counts.changed} changed`);
                if (counts.fixed) summaryParts.push(`${counts.fixed} fixed`);
                
                const summaryText = summaryParts.length > 0 ? ` — ${summaryParts.join(', ')}` : '';

                const versionItem = document.createElement('div');
                versionItem.className = 'changelog-version-entry';
                versionItem.style.cssText = `margin-bottom: 12px; border-radius: 8px; border: 1px solid var(--border); overflow: hidden; transition: all 0.2s ease; ${highlightStyle}`;
                
                const header = document.createElement('div');
                header.className = 'version-entry-header';
                header.style.cssText = `padding: 12px 15px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.02); transition: background 0.2s;`;
                header.onmouseover = () => header.style.background = 'rgba(255,255,255,0.05)';
                header.onmouseout = () => header.style.background = 'rgba(255,255,255,0.02)';
                
                header.innerHTML = `
                    <div style="font-weight: bold; color: var(--text-primary); font-size: 0.95rem; display: flex; align-items: center;">
                        <i class="fas fa-chevron-right toggle-icon" style="font-size: 0.7rem; margin-right: 10px; transition: transform 0.2s; transform: ${isCurrent ? 'rotate(90deg)' : 'none'};"></i>
                        Version ${entry.version} <span class="version-summary" style="font-weight: normal; font-size: 0.8rem; color: var(--text-secondary); margin-left: 8px; ${isCurrent ? 'display:none;' : ''}">${summaryText}</span> ${currentBadge}
                    </div>
                    <div style="font-size: 0.75rem; color: var(--text-secondary);">${entry.date || ''}</div>
                `;

                const body = document.createElement('div');
                body.className = 'version-entry-body';
                body.style.cssText = `padding: 0 15px 15px 15px; display: ${isCurrent ? 'block' : 'none'}; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 15px;`;
                
                // Define categories
                const categories = [
                    { key: 'added', label: 'Added', color: '#55efc4' },
                    { key: 'improved', label: 'Improved', color: '#74b9ff' },
                    { key: 'changed', label: 'Changed', color: '#a29bfe' },
                    { key: 'fixed', label: 'Fixed', color: '#fdcb6e' },
                    { key: 'upgraded', label: 'Upgraded', color: '#00cec9' },
                    { key: 'removed', label: 'Removed', color: '#ff7675' }
                ];

                let detailsHtml = '';
                if (entry.changes && Array.isArray(entry.changes) && entry.changes.length > 0) {
                     detailsHtml += `<ul style="margin: 0 0 10px 0; padding-left: 20px; color: var(--text-secondary);">
                        ${entry.changes.map(c => `<li style="margin-bottom: 5px;">${c}</li>`).join('')}
                     </ul>`;
                }

                categories.forEach(cat => {
                    if (entry[cat.key] && Array.isArray(entry[cat.key]) && entry[cat.key].length > 0) {
                        detailsHtml += `
                            <div style="margin-bottom: 12px;">
                                <span style="display: inline-block; font-size: 0.6rem; font-weight: bold; text-transform: uppercase; color: ${cat.color}; border: 1px solid ${cat.color}40; background: ${cat.color}15; padding: 1px 5px; border-radius: 4px; margin-bottom: 6px; letter-spacing: 0.5px;">${cat.label}</span>
                                <ul style="margin: 0; padding-left: 18px; color: var(--text-secondary); font-size: 0.85rem; line-height: 1.5;">
                                    ${entry[cat.key].map(item => `<li style="margin-bottom: 3px;">${item}</li>`).join('')}
                                </ul>
                            </div>
                        `;
                    }
                });
                
                body.innerHTML = detailsHtml;
                
                header.onclick = () => {
                    const isVisible = body.style.display === 'block';
                    body.style.display = isVisible ? 'none' : 'block';
                    header.querySelector('.toggle-icon').style.transform = isVisible ? 'none' : 'rotate(90deg)';
                    header.querySelector('.version-summary').style.display = isVisible ? 'inline' : 'none';
                };

                versionItem.appendChild(header);
                versionItem.appendChild(body);
                changelogList.appendChild(versionItem);
            });
        } else {
            changelogList.innerHTML = '<div style="color:var(--text-secondary); padding: 20px; text-align: center;">No changelog data available.</div>';
        }
    }
}

async function triggerSelfUpdate() {
    if (!confirm("Are you sure you want to update Aethvion? This will restart the entire suite and current sessions will be disconnected.")) {
        return;
    }

    const overlay = document.getElementById('self-update-overlay');
    const statusText = document.getElementById('update-status-text');
    const progressBar = document.getElementById('update-progress-bar');

    if (overlay) overlay.classList.add('active');
    
    const setStatus = (text, progress) => {
        if (statusText) statusText.textContent = text;
        if (progressBar) progressBar.style.width = `${progress}%`;
    };

    try {
        setStatus("Running Git lifecycle (fetch/stash/pull)...", 20);
        
        const res = await fetch('/api/system/update', { method: 'POST' });
        const data = await res.json();

        if (res.ok) {
            setStatus("Update applied! Restarting system...", 90);
            
            // The server will close in ~1s. We poll for health until it's back.
            setTimeout(() => {
                setStatus("System is restarting. Reconnecting...", 95);
                checkSystemBack();
            }, 3000);
        } else {
            if (overlay) overlay.classList.remove('active');
            showNotification(data.detail || "Update failed", "error");
        }
    } catch (e) {
        if (overlay) overlay.classList.remove('active');
        showNotification("Connection lost during update. System might be restarting.", "warning");
        // Try to reconnect anyway
        checkSystemBack();
    }
}

function checkSystemBack() {
    const statusText = document.getElementById('update-status-text');
    const progressBar = document.getElementById('update-progress-bar');

    let attempts = 0;
    const interval = setInterval(async () => {
        attempts++;
        if (statusText) statusText.textContent = `Reconnecting (Attempt ${attempts})...`;
        
        try {
            const res = await fetch('/health');
            if (res.ok) {
                clearInterval(interval);
                if (statusText) statusText.textContent = "Online! Reloading...";
                if (progressBar) progressBar.style.width = "100%";
                setTimeout(() => window.location.reload(), 1000);
            }
        } catch (e) {
            // Keep trying
        }

        if (attempts > 60) {
            clearInterval(interval);
            alert("System took too long to restart. Please check the logs or start manually.");
        }
    }, 2000);
}

window.triggerSelfUpdate = triggerSelfUpdate;

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

// Initialize Manual Update Button (delegated — works even before partial loads)
document.addEventListener('click', (e) => {
    if (e.target && e.target.id === 'settings-check-update-btn') {
        checkForUpdates(true);
    } else if (e.target && e.target.closest('#settings-check-update-btn')) {
        checkForUpdates(true);
    }
});

// Load version data when the version partial is first injected
document.addEventListener('panelLoaded', function (e) {
    if (e.detail.panelId === 'version-panel') checkForUpdates(false);
});


// ===== Discord Worker Management =====

let _discordStatusInterval = null;

function initDiscordSettings() {
    const tokenInput = document.getElementById('setting-discord-token');
    const mainUserIdInput = document.getElementById('setting-discord-main-user-id');
    const enabledToggle = document.getElementById('setting-discord-enabled');
    const toggleBtn = document.getElementById('toggle-discord-token-visibility');
    const startBtn = document.getElementById('btn-discord-start');
    const stopBtn = document.getElementById('btn-discord-stop');

    if (enabledToggle) {
        enabledToggle.checked = prefs.get('nexus.discord_link.enabled', false);
        enabledToggle.onchange = async (e) => {
            await savePreference('nexus.discord_link.enabled', e.target.checked);
        };
    }

    if (tokenInput) {
        tokenInput.value = prefs.get('nexus.discord_link.bot_token', '');
        tokenInput.onchange = async (e) => {
            await savePreference('nexus.discord_link.bot_token', e.target.value.trim());
        };
    }

    if (mainUserIdInput) {
        mainUserIdInput.value = prefs.get('nexus.discord_link.main_user_id', '');
        mainUserIdInput.onchange = async (e) => {
            await savePreference('nexus.discord_link.main_user_id', e.target.value.trim());
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

// ===== Interface Settings (Sidebar Visibility) =====


// ===== Display Timezone =====

async function loadDisplayTimezone() {
    const sel = document.getElementById('display-timezone-select');
    if (!sel) return;
    try {
        const resp = await fetch('/api/settings');
        if (!resp.ok) throw new Error('settings fetch failed');
        const data = await resp.json();
        const tz = (data.display && data.display.timezone) || localStorage.getItem('display_timezone') || 'UTC';
        if (sel.querySelector(`option[value="${tz}"]`)) sel.value = tz;
    } catch (_) {
        const stored = localStorage.getItem('display_timezone');
        if (stored && sel.querySelector(`option[value="${stored}"]`)) sel.value = stored;
    }

    const saveBtn = document.getElementById('display-timezone-save-btn');
    const savedSpan = document.getElementById('display-timezone-saved');
    if (saveBtn) {
        saveBtn.addEventListener('click', async () => {
            const tz = sel.value;
            localStorage.setItem('display_timezone', tz);
            try {
                await fetch('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 'display.timezone': tz }),
                });
            } catch (_) {}
            if (savedSpan) {
                savedSpan.style.display = 'inline';
                setTimeout(() => { savedSpan.style.display = 'none'; }, 2000);
            }
        }, { once: false });
        // Guard against attaching twice on re-entry
        saveBtn.dataset.tzWired = '1';
    }
}


// ===== Notification Visibility Management =====

function createNotifRow(id, label, icon, checked) {
    const row = document.createElement('div');
    row.className = 'iface-row'; // reuse iface-row style

    const uid = `notif-vis-${id}`;

    row.innerHTML = `
        <div class="toggle-switch-mini">
            <input type="checkbox" id="${uid}"${checked ? ' checked' : ''}>
            <label for="${uid}"></label>
        </div>
        <span class="iface-row-icon">${icon}</span>
        <span class="iface-row-label">${label}</span>
    `;

    const checkbox = row.querySelector('input');
    checkbox.addEventListener('change', async () => {
        const isNowVisible = checkbox.checked;
        const prefKey = `notification_hidden_${id}`;
        await prefs.set(prefKey, !isNowVisible);

        // Tell notification system to refresh/re-render
        if (window.Notifications && typeof window.Notifications.refresh === 'function') {
            window.Notifications.refresh();
        }
    });

    return row;
}

function loadNotificationSettings() {
    const container = document.getElementById('notif-visibility-list');
    if (!container) return;

    // Based on SOURCE_ICONS in notifications.js
    const sources = [
        { id: 'agents',   label: 'Agents',   icon: '🤖' },
        { id: 'schedule', label: 'Schedule', icon: '🗓️' },
        { id: 'system',   label: 'System',   icon: '⚙️' },
        { id: 'chat',     label: 'Chat',     icon: '💬' },
        { id: 'audio',    label: 'Audio',    icon: '🎙️' },
        { id: 'photo',    label: 'Photo',    icon: '🎨' },
        { id: 'corp',     label: 'Corp',     icon: '🏢' },
        { id: 'memory',   label: 'Memory',   icon: '🧠' }
    ];

    container.innerHTML = '';

    sources.forEach(source => {
        const hidden = prefs.get(`notification_hidden_${source.id}`, false);
        const row = createNotifRow(source.id, source.label, source.icon, !(hidden === true || hidden === 'true'));
        container.appendChild(row);
    });
}

// ===== External API Settings =====

async function loadExternalApiSettings() {
    try {
        const [cfgRes, keysRes] = await Promise.all([
            fetch('/api/external-api/config'),
            fetch('/api/external-api/keys'),
        ]);
        if (!cfgRes.ok || !keysRes.ok) throw new Error('Failed to load external API settings');
        const cfg  = await cfgRes.json();
        const data = await keysRes.json();

        const enabledEl     = document.getElementById('extapi-enabled');
        const requireAuthEl = document.getElementById('extapi-require-auth');
        if (enabledEl)     { enabledEl.checked = cfg.enabled !== false; enabledEl.onchange = () => extApiSaveConfig(); }
        if (requireAuthEl) { requireAuthEl.checked = !!cfg.require_auth; requireAuthEl.onchange = () => extApiSaveConfig(); }

        _renderExtApiKeys(data.keys || []);
    } catch (e) {
        console.error('[ExtAPI] Failed to load settings:', e);
    }
}

async function extApiSaveConfig() {
    const enabledEl     = document.getElementById('extapi-enabled');
    const requireAuthEl = document.getElementById('extapi-require-auth');
    try {
        await fetch('/api/external-api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                enabled:      enabledEl     ? enabledEl.checked      : true,
                require_auth: requireAuthEl ? requireAuthEl.checked  : false,
            }),
        });
        showNotification('External API settings saved', 'success');
    } catch (e) {
        showNotification('Failed to save settings', 'error');
    }
}

function _renderExtApiKeys(keys) {
    const list = document.getElementById('extapi-keys-list');
    if (!list) return;
    if (!keys.length) {
        list.innerHTML = '<p class="section-hint" style="padding: 0.5rem 0;">No API keys yet. Click <strong>New Key</strong> to create one.</p>';
        return;
    }
    list.innerHTML = keys.map(k => `
        <div class="extapi-key-row" id="extapi-key-row-${k.id}">
            <div class="extapi-key-info">
                <span class="extapi-key-name">${_escHtml(k.name)}</span>
                <code class="extapi-key-preview">${_escHtml(k.key_preview)}</code>
            </div>
            <div class="extapi-key-meta">
                <span class="extapi-key-stat">${k.request_count} requests</span>
                <span class="extapi-key-stat">${k.last_used ? 'Last used ' + new Date(k.last_used).toLocaleDateString() : 'Never used'}</span>
            </div>
            <button class="action-btn secondary xs-btn" onclick="extApiDeleteKey('${k.id}', '${_escHtml(k.name)}')" title="Revoke key">
                <i class="fas fa-trash"></i>
            </button>
        </div>
    `).join('');
}

async function extApiCreateKey() {
    const name = prompt('Key name (e.g. "My App", "Home Server"):');
    if (!name) return;
    try {
        const res = await fetch('/api/external-api/keys', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
        });
        if (!res.ok) throw new Error('Failed');
        const data = await res.json();

        // Show the key once
        const revealBox  = document.getElementById('extapi-new-key-reveal');
        const revealCode = document.getElementById('extapi-new-key-value');
        if (revealBox && revealCode) {
            revealCode.textContent = data.key;
            revealBox.style.display = 'block';
        }

        showNotification(`Key "${name}" created`, 'success');
        loadExternalApiSettings();
    } catch (e) {
        showNotification('Failed to create key', 'error');
    }
}

async function extApiDeleteKey(keyId, name) {
    if (!confirm(`Revoke key "${name}"? Any apps using it will stop working.`)) return;
    try {
        const res = await fetch(`/api/external-api/keys/${keyId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Failed');
        document.getElementById(`extapi-key-row-${keyId}`)?.remove();
        showNotification(`Key "${name}" revoked`, 'success');
        loadExternalApiSettings();
    } catch (e) {
        showNotification('Failed to delete key', 'error');
    }
}

function extApiCopy(elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;
    navigator.clipboard.writeText(el.textContent.trim())
        .then(() => showNotification('Copied to clipboard', 'success'))
        .catch(() => showNotification('Copy failed', 'error'));
}

function extApiCopyNewKey() {
    const code = document.getElementById('extapi-new-key-value');
    if (!code) return;
    navigator.clipboard.writeText(code.textContent.trim())
        .then(() => showNotification('Key copied!', 'success'))
        .catch(() => showNotification('Copy failed', 'error'));
}

function extApiQsTab(tab, btn) {
    ['python', 'node', 'curl'].forEach(t => {
        const el = document.getElementById(`extapi-qs-${t}`);
        if (el) el.style.display = t === tab ? 'block' : 'none';
    });
    document.querySelectorAll('.extapi-qs-tab').forEach(b => b.classList.toggle('active', b === btn));
}

function _escHtml(str) {
    return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Desktop Overlay Settings ──────────────────────────────────────────────────

async function loadOverlaySettings() {
    try {
        const [cfgRes, statusRes] = await Promise.all([
            fetch('/api/overlay/config'),
            fetch('/api/overlay/status'),
        ]);
        const cfg    = cfgRes.ok    ? await cfgRes.json()    : {};
        const status = statusRes.ok ? await statusRes.json() : {};

        // Populate basic fields
        const hotkeyEl    = document.getElementById('overlay-hotkey');
        const autostartEl = document.getElementById('overlay-autostart');
        const modelEl     = document.getElementById('overlay-model');

        if (hotkeyEl)    hotkeyEl.value      = cfg.hotkey           ?? 'ctrl+shift+space';
        if (autostartEl) autostartEl.checked = !!cfg.launch_with_suite;

        // Load model dropdown via the shared helper (same source as all other dropdowns)
        await loadChatModels();

        // After loadChatModels populates the options, restore the saved value
        if (modelEl) {
            const savedModel = cfg.model || '';
            if (savedModel && modelEl.querySelector(`option[value="${savedModel}"]`)) {
                modelEl.value = savedModel;
            } else {
                modelEl.value = '';   // "Use Info Assistant (default)"
            }
        }

        // Save autostart immediately on toggle
        if (autostartEl) {
            autostartEl.onchange = () => overlaySaveConfig();
        }

        _overlayApplyStatus(status);
    } catch (e) {
        console.error('loadOverlaySettings error', e);
    }
}

function _overlayApplyStatus(status) {
    const badge      = document.getElementById('overlay-status-badge');
    const textEl     = badge?.querySelector('.overlay-status-text');
    const launchBtn  = document.getElementById('overlay-launch-btn');
    const stopBtn    = document.getElementById('overlay-stop-btn');
    const installBtn = document.getElementById('overlay-install-btn');

    const running = status?.running ?? false;

    if (badge) {
        badge.className = `overlay-status-badge overlay-status--${running ? 'running' : 'stopped'}`;
    }
    if (textEl) textEl.textContent = running ? 'Running' : 'Not running';

    if (launchBtn) launchBtn.style.display = running ? 'none' : '';
    if (stopBtn)   stopBtn.style.display   = running ? ''     : 'none';

    // Dependencies
    const deps   = status?.deps ?? {};
    const depsEl = document.getElementById('overlay-deps-list');
    if (depsEl) {
        const pkgs    = ['PyQt6', 'pystray', 'Pillow', 'mss', 'keyboard'];
        const missing = pkgs.filter(p => deps[p] === false);

        depsEl.innerHTML = pkgs.map(pkg => {
            const ok = deps[pkg] !== false;
            return `<div class="overlay-dep-chip overlay-dep-chip--${ok ? 'ok' : 'missing'}">
                        <i class="fas fa-${ok ? 'check' : 'xmark'}"></i> ${_escHtml(pkg)}
                    </div>`;
        }).join('');

        // Show install button only when something is missing
        if (installBtn) installBtn.style.display = missing.length ? '' : 'none';
    }

    if (!status?.script_exists) {
        if (launchBtn) {
            launchBtn.disabled = true;
            launchBtn.title = 'Overlay script not found (apps/overlay/main.py)';
        }
    }
}

async function overlayRefreshStatus() {
    try {
        const res    = await fetch('/api/overlay/status');
        const status = res.ok ? await res.json() : {};
        _overlayApplyStatus(status);
    } catch (_) {}
}

async function overlaySaveConfig() {
    const hotkeyEl    = document.getElementById('overlay-hotkey');
    const autostartEl = document.getElementById('overlay-autostart');
    const modelEl     = document.getElementById('overlay-model');

    const body = {
        hotkey:            hotkeyEl?.value?.trim()  || 'ctrl+shift+space',
        launch_with_suite: autostartEl?.checked     ?? false,
        model:             modelEl?.value           || null,
    };

    try {
        const res = await fetch('/api/overlay/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(await res.text());
        _overlayToast('Settings saved.');
    } catch (e) {
        _overlayToast(`Save failed: ${e.message}`, true);
    }
}

async function overlayLaunch() {
    const btn = document.getElementById('overlay-launch-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Launching…'; }
    try {
        const res  = await fetch('/api/overlay/launch', { method: 'POST' });
        const data = res.ok ? await res.json() : {};
        if (data.status === 'already_running') {
            _overlayToast('Overlay is already running.');
        } else {
            _overlayToast('Overlay launched — check your system tray.');
            // Wait a moment then refresh status
            setTimeout(overlayRefreshStatus, 2000);
        }
    } catch (e) {
        _overlayToast(`Launch failed: ${e.message}`, true);
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-play"></i> Launch Overlay'; }
    }
}

async function overlayStop() {
    const btn = document.getElementById('overlay-stop-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Stopping…'; }
    try {
        await fetch('/api/overlay/stop', { method: 'POST' });
        _overlayToast('Overlay stopped.');
        setTimeout(overlayRefreshStatus, 800);
    } catch (e) {
        _overlayToast(`Stop failed: ${e.message}`, true);
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-stop"></i> Stop Overlay'; }
    }
}

function _overlayToast(msg, isError = false) {
    // Reuse existing toast/notify if available, otherwise console
    if (typeof showNotification === 'function') {
        showNotification(msg, isError ? 'error' : 'success');
    } else {
        console[isError ? 'error' : 'log']('[Overlay]', msg);
    }
}

async function overlayInstallDeps() {
    const btn     = document.getElementById('overlay-install-btn');
    const logWrap = document.getElementById('overlay-install-log-wrap');
    const logEl   = document.getElementById('overlay-install-log');

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Installing…';
    }
    if (logWrap) logWrap.style.display = '';
    if (logEl)   logEl.textContent = 'Running pip install…\n';

    try {
        const res  = await fetch('/api/overlay/install-deps', { method: 'POST' });
        const data = res.ok ? await res.json() : { success: false, output: await res.text() };

        if (logEl) logEl.textContent = data.output ?? '(no output)';

        if (data.success) {
            _overlayToast('Packages installed successfully.');
            // Re-apply deps chips from the fresh check returned by the endpoint
            if (data.deps) _overlayApplyStatus({ deps: data.deps, running: false, script_exists: true });
        } else {
            _overlayToast('Some packages may not have installed — check the log below.', true);
        }
    } catch (e) {
        if (logEl) logEl.textContent += `\nError: ${e.message}`;
        _overlayToast(`Install failed: ${e.message}`, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-download"></i> Install Missing';
        }
        // Refresh status so chips update
        setTimeout(overlayRefreshStatus, 500);
    }
}

function overlayInstallLogCopy() {
    const logEl = document.getElementById('overlay-install-log');
    if (!logEl) return;
    navigator.clipboard.writeText(logEl.textContent).then(() => {
        _overlayToast('Log copied to clipboard.');
    }).catch(() => {});
}

window.overlayLaunch            = overlayLaunch;
window.overlayStop              = overlayStop;
window.overlayRefreshStatus     = overlayRefreshStatus;
window.overlaySaveConfig        = overlaySaveConfig;
window.overlayInstallDeps       = overlayInstallDeps;
window.overlayInstallLogCopy    = overlayInstallLogCopy;

// ── Privacy Mode Toggle ────────────────────────────────────────────────────────
async function initPrivacyToggle() {
    const toggle = document.getElementById('privacy-mode-toggle');
    const badge  = document.getElementById('privacy-mode-badge');
    if (!toggle) return;

    try {
        const res  = await fetch('/api/settings/privacy-mode');
        const data = await res.json();
        toggle.checked = !!data.enabled;
        _updatePrivacyBadge(badge, toggle.checked);
    } catch (e) {
        console.warn('[Privacy] Could not load privacy mode state:', e);
    }

    toggle.addEventListener('change', async () => {
        const enabled = toggle.checked;
        try {
            const res  = await fetch('/api/settings/privacy-mode', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ enabled }),
            });
            const data = await res.json();
            _updatePrivacyBadge(badge, enabled);
            if (typeof showToast === 'function') {
                showToast(data.message, enabled ? 'warn' : 'success');
            }
        } catch (e) {
            toggle.checked = !enabled;   // revert on failure
            if (typeof showToast === 'function') showToast('Failed to update privacy mode.', 'error');
        }
    });
}

function _updatePrivacyBadge(badge, enabled) {
    if (!badge) return;
    badge.textContent = enabled ? '🔒 Privacy Mode ON' : '🌐 Cloud OK';
    badge.className   = `privacy-badge ${enabled ? 'privacy-badge-on' : 'privacy-badge-off'}`;
}

window.initPrivacyToggle = initPrivacyToggle;

