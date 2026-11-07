/**
 * Aethvion Suite — Global Connectors & Connector Profiles View (Library > Connectors)
 * Manage global bridges/connectors, live-test commands and /slash_commands,
 * and configure Connector Access Profiles for Companions & Chat.
 */

const ConnectorsView = (() => {
    let _modules = [];
    let _profiles = [];
    let _currentTab = 'connectors';
    let _selectedProfileId = 'full_local';

    function _esc(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    async function init() {
        await refresh();
    }

    async function refresh() {
        try {
            const res = await fetch('/api/connectors/registry');
            if (!res.ok) throw new Error('Failed to load connectors registry');
            const data = await res.json();
            _modules = data.modules || [];
            _profiles = data.profiles || [];

            _renderStats();
            _populateSlashProfileSelect();
            if (window.AethvionSlashAutocomplete) window.AethvionSlashAutocomplete.invalidateCache();
            _renderConnectors();
            _renderProfiles();
            if (typeof markPanelUpdated === 'function') markPanelUpdated('connectors');
        } catch (e) {
            console.error('[ConnectorsView] Refresh error:', e);
            const grid = document.getElementById('cn-connectors-grid');
            if (grid) grid.innerHTML = `<p class="empty-state">Failed to load Connectors: ${_esc(e.message)}</p>`;
        }
    }

    function _renderStats() {
        const activeCount = _modules.filter(m => m.enabled !== false).length;
        const statActive = document.getElementById('cn-stat-active');
        const statProfiles = document.getElementById('cn-stat-profiles');
        if (statActive) statActive.textContent = `${activeCount}/${_modules.length}`;
        if (statProfiles) statProfiles.textContent = _profiles.length;
    }

    function _populateSlashProfileSelect() {
        const sel = document.getElementById('cn-slash-test-profile');
        if (!sel) return;
        const cur = sel.value || 'full_local';
        sel.innerHTML = _profiles.map(p =>
            `<option value="${_esc(p.id)}">Profile: ${_esc(p.name)}</option>`
        ).join('');
        if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
    }

    function onFilterChange() {
        _renderConnectors();
    }

    function _renderConnectors() {
        const grid = document.getElementById('cn-connectors-grid');
        if (!grid) return;

        const q = (document.getElementById('cn-search-input')?.value || '').toLowerCase().trim();
        const catFilter = document.getElementById('cn-cat-filter')?.value || 'all';
        const privFilter = document.getElementById('cn-privacy-filter')?.value || 'all';
        const stateFilter = document.getElementById('cn-state-filter')?.value || 'all';

        const filtered = _modules.filter(m => {
            const isEnabled = m.enabled !== false;
            if (catFilter !== 'all' && (m.category || 'system') !== catFilter) return false;
            if (privFilter !== 'all' && (m.privacy_tier || 'local_sensitive') !== privFilter) return false;
            if (stateFilter === 'enabled' && !isEnabled) return false;
            if (stateFilter === 'disabled' && isEnabled) return false;
            if (q) {
                const hay = `${m.name} ${m.id} ${m.description} ${m.slash_command || ''}`.toLowerCase();
                if (!hay.includes(q)) return false;
            }
            return true;
        });

        if (!filtered.length) {
            grid.innerHTML = `<p class="empty-state">No connectors match your filters.</p>`;
            return;
        }

        grid.innerHTML = filtered.map(mod => {
            const enabled = mod.enabled !== false;
            const priv = mod.privacy_tier || 'local_sensitive';
            const privLabel = priv === 'cloud_safe' ? '🌐 Cloud Safe' : '🔒 Local / Sensitive';
            const cat = mod.category || 'system';
            const slash = mod.slash_command || `/${mod.id}`;
            const cmds = Object.entries(mod.available_commands || {});
            const hasSettings = Array.isArray(mod.settings) && mod.settings.length > 0;

            const cmdOptions = cmds.map(([cmd, desc]) =>
                `<option value="${_esc(cmd)}" title="${_esc(desc)}">${_esc(cmd)}</option>`
            ).join('');

            const cmdPillsHtml = cmds.map(([cmd, desc]) =>
                `<span class="cn-cmd-tag" title="${_esc(desc)}">${_esc(cmd)}</span>`
            ).join('');

            let settingsDrawerHtml = '';
            if (hasSettings) {
                const savedVals = mod.saved_settings || {};
                settingsDrawerHtml = `
                <div id="cn-settings-drawer-${_esc(mod.id)}" class="cn-row-drawer" style="display:none;">
                    <div class="cn-settings-grid">
                        ${mod.settings.map(sKey => {
                            const isSecret = /secret|key|token/i.test(sKey);
                            const val = savedVals[sKey] ?? '';
                            return `
                            <div>
                                <label class="lm-hf-label" style="font-size:0.68rem;">${_esc(sKey.replace(/_/g, ' ').toUpperCase())}</label>
                                <input type="${isSecret ? 'password' : 'text'}"
                                       class="lm-finput cn-setting-input"
                                       data-mod="${_esc(mod.id)}"
                                       data-key="${_esc(sKey)}"
                                       value="${_esc(val)}"
                                       placeholder="Enter ${_esc(sKey)}..."
                                       style="height:32px; font-size:0.78rem;">
                            </div>`;
                        }).join('')}
                        <div style="display:flex; gap:0.5rem; align-items:center;">
                            <button class="hub-action-btn secondary" style="height:32px; font-size:0.75rem; padding:0 0.8rem;"
                                    onclick="ConnectorsView.saveSettings('${_esc(mod.id)}')">
                                <i class="fas fa-save"></i> Save Settings
                            </button>
                            ${mod.requires_auth ? `
                                <button class="hub-action-btn" style="height:32px; font-size:0.75rem; padding:0 0.8rem;"
                                        onclick="ConnectorsView.authorizeConnector('${_esc(mod.id)}')">
                                    <i class="fas fa-key"></i> ${mod.is_authorized ? 'Re-Authorize' : 'Connect OAuth'}
                                </button>
                            ` : ''}
                        </div>
                    </div>
                </div>`;
            }

            return `
            <div class="cn-row-card ${enabled ? '' : 'disabled'}" id="cn-card-${_esc(mod.id)}">
                <div class="cn-row-main">
                    <!-- Column 1: Identity & Description -->
                    <div class="cn-row-identity">
                        <div class="cn-icon-box"><i class="${_esc(mod.icon || 'fas fa-plug')}"></i></div>
                        <div style="min-width:0;">
                            <div class="cn-row-title-line">
                                <h3 class="cn-row-title">${_esc(mod.name)}</h3>
                                <span class="cn-privacy-pill ${_esc(priv)}">${privLabel}</span>
                                <span class="cn-cat-pill">${_esc(cat)}</span>
                            </div>
                            <p class="cn-row-desc">${_esc(mod.description)}</p>
                        </div>
                    </div>

                    <!-- Column 2: Slash Command & Available Tool Actions -->
                    <div class="cn-row-commands">
                        <div class="cn-slash-line">
                            <span class="cn-slash-pill" onclick="ConnectorsView.copySlash('${_esc(slash)}')" title="Click to copy slash command for Chat &amp; Companions">
                                <i class="fas fa-terminal"></i> ${_esc(slash)} <i class="fas fa-copy" style="opacity:0.65; font-size:0.65rem;"></i>
                            </span>
                            <span style="font-size:0.7rem; color:var(--text-tertiary); font-family:'Fira Code',monospace;">module="${_esc(mod.id)}"</span>
                        </div>
                        <div class="cn-cmd-pills">
                            ${cmdPillsHtml}
                        </div>
                    </div>

                    <!-- Column 3: Inline Live Tester -->
                    <div class="cn-row-tester">
                        <select id="cn-test-cmd-${_esc(mod.id)}" class="lm-filter-select" style="height:34px; font-size:0.76rem; min-width:130px; max-width:165px;">
                            ${cmdOptions}
                        </select>
                        <input type="text" id="cn-test-arg-${_esc(mod.id)}" class="lm-finput"
                               placeholder="Optional arg..."
                               style="flex:1; min-width:110px; height:34px; font-size:0.76rem; padding:0 0.65rem;">
                        <button class="hub-action-btn secondary" style="height:34px; padding:0 0.75rem; font-size:0.76rem; white-space:nowrap; flex-shrink:0;"
                                onclick="ConnectorsView.testConnector('${_esc(mod.id)}', this)">
                            <i class="fas fa-play"></i> Test
                        </button>
                    </div>

                    <!-- Column 4: Settings Toggle & Enable Switch -->
                    <div class="cn-row-actions">
                        ${hasSettings ? `
                            <button class="lm-icon-btn" style="width:34px; height:34px;"
                                    title="Configure Connector Settings (${mod.settings.length})"
                                    onclick="ConnectorsView.toggleSettingsDrawer('${_esc(mod.id)}')">
                                <i class="fas fa-sliders"></i>
                            </button>
                        ` : ''}
                        <label class="switch small" title="${enabled ? 'Connector Enabled' : 'Connector Disabled'}">
                            <input type="checkbox" ${enabled ? 'checked' : ''}
                                   onchange="ConnectorsView.toggleConnector('${_esc(mod.id)}', this.checked)">
                            <span class="slider round"></span>
                        </label>
                    </div>
                </div>

                <div id="cn-test-res-${_esc(mod.id)}" class="cn-row-drawer" style="display:none; font-size:0.76rem; font-family:'Fira Code',monospace; padding:0.7rem 0.85rem; border-radius:8px; background:rgba(0,0,0,0.3); white-space:pre-wrap;"></div>

                ${settingsDrawerHtml}
            </div>`;
        }).join('');
    }

    function toggleSettingsDrawer(moduleId) {
        const drawer = document.getElementById(`cn-settings-drawer-${moduleId}`);
        if (!drawer) return;
        drawer.style.display = drawer.style.display === 'none' ? 'block' : 'none';
    }

    function _renderProfiles() {
        const listEl = document.getElementById('cn-profiles-list');
        if (!listEl) return;

        if (!_profiles.some(p => p.id === _selectedProfileId) && _profiles.length) {
            _selectedProfileId = _profiles[0].id;
        }

        listEl.innerHTML = _profiles.map(p => {
            const isSelected = p.id === _selectedProfileId;
            const count = (p.allowed_connectors || []).length;
            return `
            <div class="cn-prof-item ${isSelected ? 'active' : ''}" onclick="ConnectorsView.selectProfile('${_esc(p.id)}')">
                <div style="display:flex; align-items:center; justify-content:space-between; gap:0.5rem;">
                    <div style="display:flex; align-items:center; gap:0.5rem; font-weight:600; font-size:0.88rem; color:var(--text-primary);">
                        <i class="${_esc(p.icon || 'fas fa-shield-halved')}" style="color:var(--primary);"></i>
                        <span>${_esc(p.name)}</span>
                    </div>
                    <span class="vl-badge" style="color:var(--primary);">${_esc(p.privacy_badge || 'Custom')}</span>
                </div>
                <p style="margin:0.35rem 0 0.45rem; font-size:0.76rem; color:var(--text-secondary);">${_esc(p.description || '')}</p>
                <div style="font-size:0.7rem; color:var(--text-tertiary);">
                    <strong>${count}</strong> / ${_modules.length} connectors permitted ${p.builtin ? '· Built-in preset' : '· Custom profile'}
                </div>
            </div>`;
        }).join('');

        const activeProf = _profiles.find(p => p.id === _selectedProfileId);
        if (activeProf) {
            _populateProfileEditor(activeProf);
        }
    }

    function selectProfile(profileId) {
        _selectedProfileId = profileId;
        _renderProfiles();
    }

    function startNewProfile() {
        _selectedProfileId = '';
        document.querySelectorAll('.cn-prof-item').forEach(el => el.classList.remove('active'));
        _populateProfileEditor({
            id: '',
            name: '',
            privacy_badge: 'Custom',
            description: '',
            builtin: false,
            allowed_connectors: ['web_search', 'weather_link', 'reddit']
        });
        document.getElementById('cn-prof-name')?.focus();
    }

    function _populateProfileEditor(prof) {
        const titleEl = document.getElementById('cn-prof-editor-title');
        const badgeEl = document.getElementById('cn-prof-editor-badge');
        const idEl = document.getElementById('cn-prof-id');
        const nameEl = document.getElementById('cn-prof-name');
        const privEl = document.getElementById('cn-prof-badge');
        const descEl = document.getElementById('cn-prof-desc');
        const delBtn = document.getElementById('cn-prof-delete-btn');
        const checklistEl = document.getElementById('cn-prof-connectors-checklist');

        if (titleEl) titleEl.textContent = prof.id ? `Edit Profile: ${prof.name}` : 'Create New Connector Profile';
        if (badgeEl) badgeEl.textContent = prof.builtin ? 'Built-in Preset' : 'Custom Profile';
        if (idEl) idEl.value = prof.id || '';
        if (nameEl) nameEl.value = prof.name || '';
        if (privEl) privEl.value = prof.privacy_badge || 'Custom';
        if (descEl) descEl.value = prof.description || '';
        if (delBtn) delBtn.style.display = (prof.id && !prof.builtin) ? '' : 'none';

        const allowedSet = new Set(prof.allowed_connectors || []);
        if (checklistEl) {
            checklistEl.innerHTML = _modules.map(m => {
                const checked = allowedSet.has(m.id);
                const isSensitive = (m.privacy_tier || 'local_sensitive') === 'local_sensitive';
                return `
                <label class="cn-check-row">
                    <div style="display:flex; align-items:center; gap:0.75rem; min-width:0;">
                        <input type="checkbox" class="cn-prof-conn-cb" value="${_esc(m.id)}"
                               data-tier="${_esc(m.privacy_tier || 'local_sensitive')}"
                               ${checked ? 'checked' : ''}>
                        <div class="cn-icon-box" style="width:32px; height:32px; font-size:0.85rem; margin:0;">
                            <i class="${_esc(m.icon || 'fas fa-plug')}"></i>
                        </div>
                        <div style="min-width:0;">
                            <div style="font-size:0.84rem; font-weight:600; color:var(--text-primary); display:flex; align-items:center; gap:0.45rem;">
                                <span>${_esc(m.name)}</span>
                                <code style="font-size:0.72rem; color:var(--primary);">${_esc(m.slash_command || '/' + m.id)}</code>
                            </div>
                            <div style="font-size:0.74rem; color:var(--text-secondary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                                ${_esc(m.description || '')}
                            </div>
                        </div>
                    </div>
                    <span class="cn-privacy-pill ${isSensitive ? 'local_sensitive' : 'cloud_safe'}">
                        ${isSensitive ? '🔒 Local / Sensitive' : '🌐 Cloud Safe'}
                    </span>
                </label>`;
            }).join('');
        }
    }

    function selectProfileConnectors(mode) {
        document.querySelectorAll('.cn-prof-conn-cb').forEach(cb => {
            if (mode === 'all') cb.checked = true;
            else if (mode === 'none') cb.checked = false;
            else if (mode === 'cloud_safe') cb.checked = cb.dataset.tier === 'cloud_safe';
        });
    }

    async function saveCurrentProfile() {
        const id = document.getElementById('cn-prof-id')?.value || '';
        const name = (document.getElementById('cn-prof-name')?.value || '').trim();
        const privacy_badge = (document.getElementById('cn-prof-badge')?.value || 'Custom').trim();
        const description = (document.getElementById('cn-prof-desc')?.value || '').trim();

        if (!name) {
            if (typeof showNotification === 'function') showNotification('Please enter a profile name.', 'warning');
            return;
        }

        const allowed_connectors = [...document.querySelectorAll('.cn-prof-conn-cb:checked')].map(cb => cb.value);

        try {
            const res = await fetch('/api/connectors/profiles', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: id || undefined,
                    name,
                    privacy_badge,
                    description,
                    allowed_connectors
                })
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.detail || 'Failed to save profile');
            _selectedProfileId = data.profile.id;
            if (typeof showNotification === 'function') showNotification(`Connector Profile "${name}" saved!`, 'success');
            await refresh();
        } catch (e) {
            if (typeof showNotification === 'function') showNotification(e.message, 'error');
        }
    }

    async function deleteCurrentProfile() {
        const id = document.getElementById('cn-prof-id')?.value;
        if (!id) return;
        if (!confirm('Delete this custom Connector Profile?')) return;
        try {
            const res = await fetch(`/api/connectors/profiles/${encodeURIComponent(id)}`, { method: 'DELETE' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Delete failed');
            _selectedProfileId = 'full_local';
            if (typeof showNotification === 'function') showNotification('Profile deleted.', 'success');
            await refresh();
        } catch (e) {
            if (typeof showNotification === 'function') showNotification(e.message, 'error');
        }
    }

    async function toggleConnector(moduleId, enabled) {
        try {
            const res = await fetch(`/api/connectors/${encodeURIComponent(moduleId)}/toggle`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled })
            });
            if (!res.ok) throw new Error('Failed to toggle connector');
            const mod = _modules.find(m => m.id === moduleId);
            if (mod) mod.enabled = enabled;
            const card = document.getElementById(`cn-card-${moduleId}`);
            if (card) card.classList.toggle('disabled', !enabled);
            _renderStats();
            if (window.AethvionSlashAutocomplete) window.AethvionSlashAutocomplete.invalidateCache();
            if (typeof showNotification === 'function') {
                showNotification(`${mod?.name || moduleId} ${enabled ? 'enabled' : 'disabled'}.`, 'success');
            }
        } catch (e) {
            if (typeof showNotification === 'function') showNotification(e.message, 'error');
        }
    }

    async function saveSettings(moduleId) {
        const inputs = document.querySelectorAll(`.cn-setting-input[data-mod="${moduleId}"]`);
        const settings = {};
        inputs.forEach(inp => {
            settings[inp.dataset.key] = inp.value.trim();
        });
        try {
            const res = await fetch(`/api/connectors/${encodeURIComponent(moduleId)}/settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings })
            });
            if (!res.ok) throw new Error('Failed to save settings');
            if (typeof showNotification === 'function') showNotification(`Saved ${moduleId} settings.`, 'success');
        } catch (e) {
            if (typeof showNotification === 'function') showNotification(e.message, 'error');
        }
    }

    async function authorizeConnector(moduleId) {
        if (moduleId === 'spotify') {
            await saveSettings('spotify');
            const inputs = document.querySelectorAll(`.cn-setting-input[data-mod="spotify"]`);
            const cfg = {};
            inputs.forEach(inp => { cfg[inp.dataset.key] = inp.value.trim(); });
            try {
                const res = await fetch(`/api/companions/misakacipher/bridges/spotify/authorize`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(cfg)
                });
                const d = await res.json();
                if (!res.ok) throw new Error(d.detail || 'Spotify auth failed');
                window.open(d.url, '_blank', 'width=600,height=800');
            } catch (e) {
                if (typeof showNotification === 'function') showNotification(e.message, 'error');
            }
        }
    }

    async function testConnector(moduleId, btn) {
        const cmd = document.getElementById(`cn-test-cmd-${moduleId}`)?.value || '';
        const rawArg = (document.getElementById(`cn-test-arg-${moduleId}`)?.value || '').trim();
        const resEl = document.getElementById(`cn-test-res-${moduleId}`);

        const args = {};
        if (rawArg) {
            if (moduleId === 'web_search') args.query = rawArg;
            else if (moduleId === 'weather_link') args.location = rawArg;
            else if (moduleId === 'reddit') {
                if (cmd === 'search_reddit') args.query = rawArg;
                else args.subreddit = rawArg;
            } else if (moduleId === 'screen_capture' || moduleId === 'screen_ocr') args.monitor = parseInt(rawArg, 10) || 0;
            else if (moduleId === 'webcam_capture') args.index = parseInt(rawArg, 10) || 0;
            else if (moduleId === 'spotify') args.target = rawArg;
            else if (moduleId === 'webpage_reader' || moduleId === 'youtube_link') args.url = rawArg;
            else if (moduleId === 'twitch_link') { args.channel = rawArg; args.query = rawArg; }
            else if (moduleId === 'clipboard_link') args.text = rawArg;
            else if (moduleId === 'git_link') args.path = rawArg;
            else if (moduleId === 'process_watcher') args.top_n = parseInt(rawArg, 10) || 8;
            else if (moduleId === 'companion_tasks') {
                if (cmd === 'complete_task') args.id = rawArg;
                else args.text = rawArg;
            } else args.query = rawArg;
        }

        const origHtml = btn ? btn.innerHTML : '';
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i>`;
        }
        if (resEl) {
            resEl.style.display = 'block';
            resEl.textContent = 'Running connector...';
        }

        try {
            const res = await fetch(`/api/connectors/${encodeURIComponent(moduleId)}/test`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: cmd, args })
            });
            const data = await res.json();
            if (resEl) {
                resEl.innerHTML = `<div>${_esc(data.output || '')}</div>`;
                if (data.attachments && data.attachments.length) {
                    resEl.innerHTML += data.attachments.map(a =>
                        `<img src="${_esc(a.url)}" style="max-width:100%; max-height:180px; border-radius:8px; margin-top:0.5rem; display:block;" alt="Capture">`
                    ).join('');
                }
            }
        } catch (e) {
            if (resEl) resEl.textContent = `Error: ${e.message}`;
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = origHtml;
            }
        }
    }

    async function runSlashTest(btn) {
        const message = (document.getElementById('cn-slash-test-input')?.value || '').trim();
        const profile_id = document.getElementById('cn-slash-test-profile')?.value || 'full_local';
        const outEl = document.getElementById('cn-slash-test-output');
        if (!message) return;

        const orig = btn ? btn.innerHTML : '';
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Running...`;
        }
        if (outEl) {
            outEl.style.display = 'block';
            outEl.textContent = `Executing "${message}" with profile [${profile_id}]...`;
        }

        try {
            const res = await fetch('/api/connectors/slash', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message, profile_id })
            });
            const d = await res.json();
            if (!d.triggered) {
                if (outEl) outEl.textContent = `No matching /slash_command found in "${message}". Try /system, /screen_capture, /media, /weather, /reddit, or /search.`;
            } else {
                const blocks = (d.results || []).map(r => `[${r.name} · ${r.module_id}.${r.command}]\n${r.output}`).join('\n\n');
                if (outEl) {
                    outEl.innerHTML = `<div>${_esc(blocks)}</div>`;
                    if (d.attachments && d.attachments.length) {
                        outEl.innerHTML += d.attachments.map(a =>
                            `<img src="${_esc(a.url)}" style="max-width:100%; max-height:220px; border-radius:8px; margin-top:0.6rem; display:block;" alt="Capture">`
                        ).join('');
                    }
                }
            }
        } catch (e) {
            if (outEl) outEl.textContent = `Slash command error: ${e.message}`;
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = orig;
            }
        }
    }

    function copySlash(slashCmd) {
        navigator.clipboard.writeText(slashCmd + ' ').then(() => {
            if (typeof showNotification === 'function') {
                showNotification(`Copied "${slashCmd}" — paste in Companion or Chat input!`, 'success');
            }
        }).catch(() => {});
    }

    function switchTab(tab) {
        _currentTab = tab;
        ['connectors', 'profiles'].forEach(t => {
            const sec = document.getElementById(`cn-section-${t}`);
            if (sec) sec.style.display = t === tab ? '' : 'none';
        });
        const filtersWrap = document.getElementById('cn-filters-wrap');
        if (filtersWrap) filtersWrap.style.display = tab === 'connectors' ? 'flex' : 'none';
        document.querySelectorAll('[data-cntab]').forEach(b => {
            b.classList.toggle('active', b.dataset.cntab === tab);
        });
    }

    if (typeof registerTabInit === 'function') {
        registerTabInit('connectors', init);
    }

    document.addEventListener('panelLoaded', function (e) {
        if (e.detail.panelId === 'connectors-panel') init();
    });

    return {
        init,
        refresh,
        switchTab,
        onFilterChange,
        toggleConnector,
        toggleSettingsDrawer,
        saveSettings,
        authorizeConnector,
        testConnector,
        runSlashTest,
        copySlash,
        selectProfile,
        startNewProfile,
        selectProfileConnectors,
        saveCurrentProfile,
        deleteCurrentProfile
    };
})();
