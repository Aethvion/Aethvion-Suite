/**
 * Aethvion Suite — Global Connectors & Connector Profiles View (Library > Connectors)
 * Manage global bridges/connectors, live-test commands and /slash_commands,
 * and configure Connector Access Profiles for Companions & Chat.
 */

const ConnectorsView = (() => {
    let _modules = [];
    let _profiles = [];
    let _dynamicTools = [];
    let _currentTab = 'connectors';
    let _selectedProfileId = 'full_local';
    let _incubatorFilter = 'all';
    let _currentInspectingToolId = null;

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
            const [regRes, dynRes] = await Promise.all([
                fetch('/api/connectors/registry'),
                fetch('/api/connectors/dynamic')
            ]);
            if (!regRes.ok) throw new Error('Failed to load connectors registry');
            const data = await regRes.json();
            _modules = data.modules || [];
            _profiles = data.profiles || [];

            if (dynRes.ok) {
                const dynData = await dynRes.json();
                _dynamicTools = dynData.tools || [];
            }

            _renderStats();
            _populateSlashProfileSelect();
            if (window.AethvionSlashAutocomplete) window.AethvionSlashAutocomplete.invalidateCache();
            _renderConnectors();
            _renderProfiles();
            _renderIncubator();
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
        const incBadge = document.getElementById('cn-incubator-badge');
        if (statActive) statActive.textContent = `${activeCount}/${_modules.length}`;
        if (statProfiles) statProfiles.textContent = _profiles.length;
        if (incBadge) incBadge.textContent = _dynamicTools.length;
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
                            const val = savedVals[sKey] ?? '';
                            if (sKey === 'mode') {
                                return `
                                <div>
                                    <label class="lm-hf-label" style="font-size:0.68rem;">CONTROL MODE</label>
                                    <select class="lm-finput cn-setting-input"
                                            data-mod="${_esc(mod.id)}"
                                            data-key="mode"
                                            style="height:32px; font-size:0.78rem;">
                                        <option value="auto"${val === 'auto' || !val ? ' selected' : ''}>Auto (Local-First, Cloud if configured)</option>
                                        <option value="local"${val === 'local' ? ' selected' : ''}>Local Only (Zero credentials, PC app)</option>
                                        <option value="cloud"${val === 'cloud' ? ' selected' : ''}>Cloud API (OAuth, remote devices)</option>
                                    </select>
                                </div>`;
                            }
                            const isSecret = /secret|key|token/i.test(sKey);
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
                            ${(mod.requires_auth || mod.id === 'spotify') ? `
                                <button class="hub-action-btn" style="height:32px; font-size:0.75rem; padding:0 0.8rem;"
                                        onclick="ConnectorsView.authorizeConnector('${_esc(mod.id)}')">
                                    <i class="fas fa-key"></i> ${mod.is_authorized && mod.requires_auth ? 'Re-Authorize' : 'Connect Cloud OAuth'}
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
                    <div style="display:flex; align-items:center; gap:0.75rem; min-width:0; flex:1; overflow:hidden;">
                        <input type="checkbox" class="cn-prof-conn-cb" value="${_esc(m.id)}"
                               data-tier="${_esc(m.privacy_tier || 'local_sensitive')}"
                               ${checked ? 'checked' : ''} style="flex-shrink:0;">
                        <div class="cn-icon-box" style="width:32px; height:32px; font-size:0.85rem; margin:0; flex-shrink:0;">
                            <i class="${_esc(m.icon || 'fas fa-plug')}"></i>
                        </div>
                        <div style="min-width:0; flex:1; overflow:hidden;">
                            <div style="font-size:0.84rem; font-weight:600; color:var(--text-primary); display:flex; align-items:center; gap:0.45rem;">
                                <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${_esc(m.name)}</span>
                                <code style="font-size:0.72rem; color:var(--primary); flex-shrink:0;">${_esc(m.slash_command || '/' + m.id)}</code>
                            </div>
                            <div style="font-size:0.74rem; color:var(--text-secondary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${_esc(m.description || '')}">
                                ${_esc(m.description || '')}
                            </div>
                        </div>
                    </div>
                    <span class="cn-privacy-pill ${isSensitive ? 'local_sensitive' : 'cloud_safe'}" style="flex-shrink:0; margin-left:0.5rem;">
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

    // ── Realtime Incubator UI & Non-Destructive Evolution ──────────────────

    async function refreshDynamic() {
        try {
            const res = await fetch('/api/connectors/dynamic');
            if (res.ok) {
                const data = await res.json();
                _dynamicTools = data.tools || [];
                _renderStats();
                _renderIncubator();
            }
        } catch (e) {
            console.error('[ConnectorsView] refreshDynamic error:', e);
        }
    }

    function filterIncubator(filter, btn) {
        _incubatorFilter = filter;
        document.querySelectorAll('[data-incfilter]').forEach(b => {
            b.classList.toggle('active', b === btn);
        });
        _renderIncubator();
    }

    function _renderIncubator() {
        const grid = document.getElementById('cn-incubator-grid');
        if (!grid) return;

        let filtered = _dynamicTools;
        if (_incubatorFilter === 'incubating') {
            filtered = _dynamicTools.filter(t => t.status === 'incubating' && !t.ready_for_native);
        } else if (_incubatorFilter === 'ready') {
            filtered = _dynamicTools.filter(t => t.ready_for_native && t.status !== 'promoted');
        } else if (_incubatorFilter === 'promoted') {
            filtered = _dynamicTools.filter(t => t.status === 'promoted');
        }

        if (!filtered.length) {
            grid.innerHTML = `
                <div class="cn-empty-card" style="grid-column: 1 / -1; padding:2.5rem; text-align:center; background:rgba(255,255,255,0.02); border-radius:14px; border:1px dashed rgba(255,255,255,0.1);">
                    <i class="fas fa-flask" style="font-size:2.2rem; color:var(--text-tertiary); margin-bottom:0.75rem;"></i>
                    <h3 style="margin:0 0 0.4rem; font-size:1.05rem;">No realtime connectors match this filter</h3>
                    <p style="margin:0 0 1rem; font-size:0.82rem; color:var(--text-secondary);">Companions create and evolve tools as they need them, or you can create one manually.</p>
                    <button class="hub-action-btn" onclick="ConnectorsView.openCreateDynamicModal()"><i class="fas fa-plus"></i> Create Realtime Connector</button>
                </div>
            `;
            return;
        }

        grid.innerHTML = filtered.map(t => {
            const isReady = t.ready_for_native && t.status !== 'promoted';
            const statusClass = t.status === 'promoted' ? 'promoted' : (isReady ? 'ready' : 'incubating');
            const statusLabel = t.status === 'promoted' ? 'Promoted Native' : (isReady ? '★ Ready for Native' : 'Incubating');
            const tel = t.telemetry || {};
            const calls = tel.call_count || 0;
            const rate = t.success_rate != null ? t.success_rate : 100;
            const collabs = (t.collaborators || [t.author || 'Companion']).join(', ');

            return `
                <div class="cn-inc-card ${isReady ? 'ready-native' : ''}">
                    <div class="cn-inc-header">
                        <div class="cn-inc-title-wrap">
                            <div class="cn-inc-icon"><i class="${_esc(t.icon || 'fas fa-wrench')}"></i></div>
                            <div>
                                <h3 class="cn-inc-name">${_esc(t.name)} <span class="cn-inc-ver">v${_esc(t.version)}</span></h3>
                                <div class="cn-inc-meta-row">
                                    <span><i class="fas fa-user-astronaut"></i> ${_esc(t.author)}</span>
                                    <span>·</span>
                                    <span><i class="fas fa-code-fork"></i> ${_esc(t.id)}</span>
                                </div>
                            </div>
                        </div>
                        <span class="cn-inc-status-pill ${statusClass}">${_esc(statusLabel)}</span>
                    </div>

                    <p class="cn-inc-desc">${_esc(t.description || 'Dynamic companion connector.')}</p>

                    <div class="cn-inc-telemetry">
                        <div><strong>${calls}</strong> calls · <strong>${rate}%</strong> success</div>
                        <div style="color:var(--text-tertiary);">${(t.test_cases || []).length} test cases</div>
                    </div>

                    <div style="font-size:0.73rem; color:var(--text-tertiary);">
                        <i class="fas fa-users" style="margin-right:0.25rem;"></i> Collaborators: ${_esc(collabs)}
                    </div>

                    <div class="cn-inc-actions">
                        <button class="hub-action-btn secondary" style="padding:0.35rem 0.7rem; font-size:0.75rem;" onclick="ConnectorsView.openTestModal('${_esc(t.id)}')">
                            <i class="fas fa-play"></i> Run / Test
                        </button>
                        <button class="hub-action-btn secondary" style="padding:0.35rem 0.7rem; font-size:0.75rem;" onclick="ConnectorsView.openDynamicModal('${_esc(t.id)}')">
                            <i class="fas fa-code-branch"></i> Inspect &amp; Evolve
                        </button>
                        ${isReady ? `
                            <button class="hub-action-btn" style="padding:0.35rem 0.7rem; font-size:0.75rem; background:#10b981; border:none; margin-left:auto;" onclick="ConnectorsView.promoteTool('${_esc(t.id)}')">
                                <i class="fas fa-star"></i> Promote
                            </button>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }

    async function openDynamicModal(toolId) {
        _currentInspectingToolId = toolId;
        const modal = document.getElementById('cn-dyn-inspect-modal');
        if (!modal) return;

        try {
            const res = await fetch(`/api/connectors/dynamic/${encodeURIComponent(toolId)}`);
            if (!res.ok) throw new Error('Failed to load tool details');
            const data = await res.json();
            const t = data.tool;

            document.getElementById('cn-dyn-modal-title').innerHTML = `
                <i class="${_esc(t.icon || 'fas fa-flask')}" style="color:#a855f7;"></i>
                <span>${_esc(t.name)}</span>
                <span style="font-size:0.75rem; color:#a855f7; font-family:'Fira Code', monospace;">v${_esc(t.version)}</span>
            `;
            document.getElementById('cn-dyn-modal-subtitle').textContent = `ID: ${t.id} · Creator: ${t.author} · Collaborators: ${(t.collaborators || []).join(', ')}`;
            document.getElementById('cn-dyn-code-display').textContent = t.active_code || '';
            document.getElementById('cn-dyn-evolve-code').value = t.active_code || '';
            document.getElementById('cn-dyn-evolve-summary').value = '';

            // Promotion button visibility
            const promBtn = document.getElementById('cn-dyn-promote-btn');
            if (promBtn) promBtn.style.display = t.status === 'promoted' ? 'none' : 'flex';

            // Test cases
            const tcEl = document.getElementById('cn-dyn-testcases-list');
            if (tcEl) {
                const tests = t.test_cases || [];
                if (!tests.length) {
                    tcEl.innerHTML = `<span style="font-size:0.78rem; color:var(--text-tertiary);">(No automated test cases specified)</span>`;
                } else {
                    tcEl.innerHTML = tests.map((tc, idx) => `
                        <div style="padding:0.45rem 0.65rem; border-radius:6px; background:rgba(0,0,0,0.3); font-family:'Fira Code', monospace; font-size:0.74rem; margin-bottom:0.35rem;">
                            <strong>#${idx + 1}: ${tc.command}()</strong> -> args: ${JSON.stringify(tc.args || {})}
                            ${tc.expected_substring ? `<span style="color:#10b981;"> (expects "${_esc(tc.expected_substring)}")</span>` : ''}
                        </div>
                    `).join('');
                }
            }

            // Changelog
            const clEl = document.getElementById('cn-dyn-changelog-list');
            if (clEl) {
                const logs = t.changelog || [];
                clEl.innerHTML = logs.map(ch => `
                    <div class="cn-ch-item">
                        <div style="display:flex; justify-content:space-between; margin-bottom:0.2rem;">
                            <strong style="color:#a855f7;">v${_esc(ch.version)}</strong>
                            <span style="color:var(--text-tertiary); font-size:0.72rem;">${_esc(ch.author)} · ${ch.timestamp ? ch.timestamp.slice(0, 10) : ''}</span>
                        </div>
                        <div style="color:var(--text-secondary);">${_esc(ch.summary)}</div>
                    </div>
                `).reverse().join('');
            }

            switchDynModalTab('code');
            modal.style.display = 'flex';
        } catch (e) {
            alert(`Error inspecting connector: ${e.message}`);
        }
    }

    function closeDynamicModal() {
        const modal = document.getElementById('cn-dyn-inspect-modal');
        if (modal) modal.style.display = 'none';
        _currentInspectingToolId = null;
    }

    function switchDynModalTab(subtab) {
        ['code', 'evolve', 'history'].forEach(st => {
            const el = document.getElementById(`cn-dyn-view-${st}`);
            const btn = document.getElementById(`cn-dyn-tab-${st}-btn`);
            if (el) el.style.display = st === subtab ? '' : 'none';
            if (btn) btn.classList.toggle('active', st === subtab);
        });
        const resEl = document.getElementById('cn-dyn-evolve-result');
        if (resEl) resEl.style.display = 'none';
    }

    async function submitEvolutionUpdate(btn) {
        if (!_currentInspectingToolId) return;
        const summary = (document.getElementById('cn-dyn-evolve-summary')?.value || '').trim();
        const author = (document.getElementById('cn-dyn-evolve-author')?.value || 'Marcel').trim();
        const code = (document.getElementById('cn-dyn-evolve-code')?.value || '').trim();
        const resEl = document.getElementById('cn-dyn-evolve-result');

        if (!summary) {
            alert('Please provide a changelog summary explaining what was improved or fixed.');
            return;
        }
        if (!code) {
            alert('Code cannot be empty.');
            return;
        }

        const origText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<i class="fas fa-circle-notch fa-spin"></i> Verifying Tests...`;

        try {
            const res = await fetch(`/api/connectors/dynamic/${encodeURIComponent(_currentInspectingToolId)}/update`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code, summary, author })
            });
            const data = await res.json();

            if (resEl) {
                resEl.style.display = 'block';
                if (data.success) {
                    resEl.className = 'cn-info-banner';
                    resEl.style.borderColor = '#10b981';
                    resEl.style.background = 'rgba(16, 185, 129, 0.12)';
                    resEl.innerHTML = `<i class="fas fa-check-circle" style="color:#10b981; margin-right:0.35rem;"></i><strong>Upgrade Certified!</strong> ${data.message}`;
                    await refreshDynamic();
                    setTimeout(() => openDynamicModal(_currentInspectingToolId), 1200);
                } else if (data.status === 'proposal_saved') {
                    resEl.className = 'cn-info-banner';
                    resEl.style.borderColor = '#f59e0b';
                    resEl.style.background = 'rgba(245, 158, 11, 0.12)';
                    resEl.innerHTML = `<i class="fas fa-triangle-exclamation" style="color:#f59e0b; margin-right:0.35rem;"></i><strong>Non-Destructive Protection:</strong> ${data.message}`;
                } else {
                    resEl.className = 'cn-info-banner';
                    resEl.style.borderColor = '#ef4444';
                    resEl.style.background = 'rgba(239, 68, 68, 0.12)';
                    resEl.innerHTML = `<i class="fas fa-circle-xmark" style="color:#ef4444; margin-right:0.35rem;"></i>${data.detail || data.error || 'Failed update.'}`;
                }
            }
        } catch (e) {
            alert(`Evolution update error: ${e.message}`);
        } finally {
            btn.disabled = false;
            btn.innerHTML = origText;
        }
    }

    async function openTestModal(toolId) {
        _currentInspectingToolId = toolId;
        const modal = document.getElementById('cn-dyn-test-modal');
        if (!modal) return;

        try {
            const res = await fetch(`/api/connectors/dynamic/${encodeURIComponent(toolId)}`);
            if (!res.ok) throw new Error('Tool not found');
            const data = await res.json();
            const t = data.tool;

            document.getElementById('cn-dyn-test-title').innerHTML = `<i class="fas fa-play" style="color:var(--primary); margin-right:0.4rem;"></i>Test: ${_esc(t.name)}`;
            document.getElementById('cn-dyn-test-subtitle').textContent = `ID: ${t.id} · v${t.version}`;

            const cmdSelect = document.getElementById('cn-dyn-test-cmd');
            const commands = Object.keys(t.commands || {});
            cmdSelect.innerHTML = commands.length ?
                commands.map(c => `<option value="${_esc(c)}">${_esc(c)}()</option>`).join('') :
                `<option value="run">default</option>`;

            document.getElementById('cn-dyn-test-output').textContent = 'Ready to execute.';
            modal.style.display = 'flex';
        } catch (e) {
            alert(`Error opening test: ${e.message}`);
        }
    }

    function closeTestModal() {
        const modal = document.getElementById('cn-dyn-test-modal');
        if (modal) modal.style.display = 'none';
    }

    async function runDynamicTest(btn) {
        if (!_currentInspectingToolId) return;
        const cmd = document.getElementById('cn-dyn-test-cmd')?.value || '';
        const rawArgs = document.getElementById('cn-dyn-test-args')?.value || '{}';
        const outEl = document.getElementById('cn-dyn-test-output');

        let args = {};
        try {
            args = JSON.parse(rawArgs);
        } catch (e) {
            alert('Arguments must be valid JSON.');
            return;
        }

        const orig = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<i class="fas fa-circle-notch fa-spin"></i> Running...`;

        try {
            const res = await fetch(`/api/connectors/dynamic/${encodeURIComponent(_currentInspectingToolId)}/test`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: cmd, args })
            });
            const data = await res.json();
            if (outEl) outEl.textContent = data.output || '(No output returned)';
            refreshDynamic();
        } catch (e) {
            if (outEl) outEl.textContent = `Execution error: ${e.message}`;
        } finally {
            btn.disabled = false;
            btn.innerHTML = orig;
        }
    }

    function openCreateDynamicModal() {
        const modal = document.getElementById('cn-dyn-create-modal');
        if (!modal) return;
        document.getElementById('cn-dyn-new-id').value = '';
        document.getElementById('cn-dyn-new-name').value = '';
        document.getElementById('cn-dyn-new-desc').value = '';
        document.getElementById('cn-dyn-new-testcmd').value = 'get_info';
        document.getElementById('cn-dyn-new-testexpect').value = 'OK';
        document.getElementById('cn-dyn-new-code').value = `def get_info(args=None):
    """Custom connector command."""
    return "Status: OK"`;
        const errEl = document.getElementById('cn-dyn-create-err');
        if (errEl) errEl.style.display = 'none';
        modal.style.display = 'flex';
    }

    function closeCreateDynamicModal() {
        const modal = document.getElementById('cn-dyn-create-modal');
        if (modal) modal.style.display = 'none';
    }

    async function submitCreateDynamic(btn) {
        const id = (document.getElementById('cn-dyn-new-id')?.value || '').trim();
        const name = (document.getElementById('cn-dyn-new-name')?.value || '').trim();
        const desc = (document.getElementById('cn-dyn-new-desc')?.value || '').trim();
        const author = (document.getElementById('cn-dyn-new-author')?.value || 'Marcel').trim();
        const testCmd = (document.getElementById('cn-dyn-new-testcmd')?.value || '').trim();
        const testExpect = (document.getElementById('cn-dyn-new-testexpect')?.value || '').trim();
        const code = (document.getElementById('cn-dyn-new-code')?.value || '').trim();
        const errEl = document.getElementById('cn-dyn-create-err');

        if (!id || !code) {
            if (errEl) {
                errEl.textContent = 'Please fill out Tool ID and Python Code.';
                errEl.style.display = 'block';
            }
            return;
        }

        const test_cases = [];
        if (testCmd) {
            test_cases.push({
                command: testCmd,
                args: {},
                expected_substring: testExpect
            });
        }

        const orig = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<i class="fas fa-circle-notch fa-spin"></i> Compiling...`;

        try {
            const res = await fetch('/api/connectors/dynamic', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id, name, description: desc, code, author, test_cases
                })
            });
            const data = await res.json();
            if (!res.ok) {
                if (errEl) {
                    errEl.textContent = data.detail || data.error || 'Failed to create connector.';
                    errEl.style.display = 'block';
                }
                return;
            }
            closeCreateDynamicModal();
            await refreshDynamic();
            if (typeof showNotification === 'function') {
                showNotification(`Created dynamic connector '${id}' v1.0.0!`, 'success');
            }
        } catch (e) {
            if (errEl) {
                errEl.textContent = e.message;
                errEl.style.display = 'block';
            }
        } finally {
            btn.disabled = false;
            btn.innerHTML = orig;
        }
    }

    async function promoteCurrentTool() {
        if (!_currentInspectingToolId) return;
        await promoteTool(_currentInspectingToolId);
        closeDynamicModal();
    }

    async function promoteTool(toolId) {
        if (!confirm(`Are you sure you want to promote '${toolId}' to the permanent Native Suite? It will be added to core/bridges and become a permanent native connector.`)) {
            return;
        }

        try {
            const res = await fetch(`/api/connectors/dynamic/${encodeURIComponent(toolId)}/promote`, {
                method: 'POST'
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Promotion failed.');
            alert(data.message || 'Promoted to Native Suite!');
            await refresh();
        } catch (e) {
            alert(`Promotion error: ${e.message}`);
        }
    }

    function switchTab(tab) {
        _currentTab = tab;
        ['connectors', 'incubator', 'profiles'].forEach(t => {
            const sec = document.getElementById(`cn-section-${t}`);
            if (sec) sec.style.display = t === tab ? '' : 'none';
        });
        const filtersWrap = document.getElementById('cn-filters-wrap');
        if (filtersWrap) filtersWrap.style.display = tab === 'connectors' ? 'flex' : 'none';
        const slashBar = document.querySelector('.cn-slash-bar');
        if (slashBar) slashBar.style.display = tab === 'connectors' ? '' : 'none';
        const slashOutput = document.getElementById('cn-slash-test-output');
        if (slashOutput && tab !== 'connectors') slashOutput.style.display = 'none';
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
        refreshDynamic,
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
        deleteCurrentProfile,
        filterIncubator,
        openDynamicModal,
        closeDynamicModal,
        switchDynModalTab,
        submitEvolutionUpdate,
        openTestModal,
        closeTestModal,
        runDynamicTest,
        openCreateDynamicModal,
        closeCreateDynamicModal,
        submitCreateDynamic,
        promoteCurrentTool,
        promoteTool
    };
})();
