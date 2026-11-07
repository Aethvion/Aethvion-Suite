/**
 * Aethvion Suite — Global Context-Aware Slash Command Autocomplete
 * Provides real-time `/` command autocomplete across Chat, Companions, Automate,
 * and Connectors Tester, dynamically filtered by the active service's Connector Profile
 * and global connector enable state.
 */

window.AethvionSlashAutocomplete = (() => {
    let _modules = [];
    let _profiles = [];
    let _loaded = false;
    let _loadingPromise = null;

    let _popupEl = null;
    let _activeInput = null;
    let _activeItems = [];
    let _selectedIndex = 0;
    let _tokenRange = null; // { start, end, query }

    const TARGET_IDS = new Set([
        'chat-input',
        'cc-chat-input',
        'cn-slash-test-input',
        'corp-chat-input',
        'axiom-chat-input',
        'lyra-chat-input',
        'misaka-chat-input'
    ]);

    const ARG_HINTS = {
        screen_capture: '[optional prompt or monitor #]',
        webcam_capture: '[optional prompt]',
        reddit: '[subreddit or search query]',
        weather_link: '[city / location]',
        web_search: '[search query]',
        media_sentinel: '[optional prompt]',
        system_link: '[optional prompt]',
        spotify: '[optional track / query]'
    };

    function _esc(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    async function loadRegistry(force = false) {
        if (_loaded && !force) return { modules: _modules, profiles: _profiles };
        if (_loadingPromise && !force) return _loadingPromise;

        _loadingPromise = (async () => {
            try {
                const res = await fetch('/api/connectors/registry');
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                _modules = data.modules || [];
                _profiles = data.profiles || [];
                _loaded = true;
                _populateChatProfileSelect();
            } catch (e) {
                console.warn('[SlashAutocomplete] Could not fetch connectors registry:', e);
            } finally {
                _loadingPromise = null;
            }
            return { modules: _modules, profiles: _profiles };
        })();
        return _loadingPromise;
    }

    function invalidateCache() {
        _loaded = false;
        loadRegistry(true);
    }

    /**
     * Populate the Main Chat Connector Profile dropdown (#chat-connector-profile)
     * whenever the registry/profiles are loaded.
     */
    function _populateChatProfileSelect() {
        const sel = document.getElementById('chat-connector-profile');
        if (!sel || !_profiles.length) return;
        const cur = sel.value || localStorage.getItem('aethvion_chat_connector_profile') || 'auto';
        const opts = [
            `<option value="auto">Auto (By Model)</option>`,
            ..._profiles.map(p => `<option value="${_esc(p.id)}">${_esc(p.name)}</option>`)
        ];
        sel.innerHTML = opts.join('');
        if ([...sel.options].some(o => o.value === cur)) {
            sel.value = cur;
        } else {
            sel.value = 'auto';
        }
    }

    /**
     * Determine whether the currently selected model in Main Chat is local or cloud.
     */
    function _resolveMainChatEffectiveProfile() {
        const sel = document.getElementById('chat-connector-profile');
        const chosen = sel?.value || localStorage.getItem('aethvion_chat_connector_profile') || 'auto';
        if (chosen && chosen !== 'auto') {
            return { profileId: chosen, reason: 'Chat Profile' };
        }
        // Auto-detect from #model-select
        const modelId = document.getElementById('model-select')?.value || 'auto';
        const cachedModels = window._cachedRegistryData?.models || [];
        const modelObj = cachedModels.find(m => m.id === modelId);
        const provider = (modelObj?.provider || '').toLowerCase();
        const isLocal = modelId === 'auto'
            || provider.includes('ollama')
            || provider.includes('local')
            || provider.includes('gguf')
            || provider.includes('lmstudio')
            || modelId.startsWith('ollama/');

        return {
            profileId: isLocal ? 'full_local' : 'cloud_safe',
            reason: isLocal ? 'Auto · Local Model' : 'Auto · Cloud Model'
        };
    }

    /**
     * Resolve which Connector Profile applies to a given input element.
     */
    function resolveContextForInput(inputEl) {
        if (!inputEl) return { profileId: 'full_local', contextLabel: 'Global' };
        const id = inputEl.id || '';

        if (id === 'chat-input') {
            const { profileId, reason } = _resolveMainChatEffectiveProfile();
            const prof = _profiles.find(p => p.id === profileId);
            return {
                profileId,
                contextLabel: prof ? `${prof.name} (${reason})` : reason
            };
        }

        if (id === 'cc-chat-input') {
            const profSel = document.getElementById('cc-cap-connector-profile');
            const profileId = profSel?.value || 'full_local';
            const compName = document.getElementById('cc-pane-name')?.textContent?.trim() || 'Companion';
            const prof = _profiles.find(p => p.id === profileId);
            return {
                profileId,
                contextLabel: `${compName} · ${prof ? prof.name : profileId}`
            };
        }

        if (id === 'cn-slash-test-input') {
            const profSel = document.getElementById('cn-slash-test-profile');
            const profileId = profSel?.value || 'full_local';
            const prof = _profiles.find(p => p.id === profileId);
            return {
                profileId,
                contextLabel: `Tester · ${prof ? prof.name : profileId}`
            };
        }

        const customProfile = inputEl.dataset?.connectorProfile || 'full_local';
        const prof = _profiles.find(p => p.id === customProfile);
        return {
            profileId: customProfile,
            contextLabel: prof ? prof.name : 'Full Local Suite'
        };
    }

    /**
     * Expose helper for threads.js so `/api/tasks/submit` receives the resolved profile_id.
     */
    function getResolvedChatProfileId() {
        return _resolveMainChatEffectiveProfile().profileId;
    }

    /**
     * Filter connectors that are:
     * 1) Globally enabled (`enabled !== false`)
     * 2) Permitted by `profileId`
     * 3) Matching the typed `/query`
     */
    function _getMatchingConnectors(profileId, query) {
        const prof = _profiles.find(p => p.id === profileId);
        const allowedSet = prof ? new Set(prof.allowed_connectors || []) : null;

        let blockedByProfileCount = 0;
        let disabledGloballyCount = 0;

        const matching = [];
        const q = (query || '').toLowerCase();

        for (const mod of _modules) {
            const slash = (mod.slash_command || `/${mod.id}`).toLowerCase();
            if (mod.enabled === false) {
                disabledGloballyCount++;
                continue;
            }
            if (allowedSet && !allowedSet.has(mod.id)) {
                blockedByProfileCount++;
                continue;
            }
            if (q && !slash.startsWith(q) && !mod.id.toLowerCase().includes(q.replace(/^\//, '')) && !mod.name.toLowerCase().includes(q.replace(/^\//, ''))) {
                continue;
            }
            matching.push(mod);
        }

        return {
            matching,
            blockedByProfileCount,
            disabledGloballyCount
        };
    }

    /**
     * Extract the `/command` token immediately preceding the cursor position.
     * Triggers when `/` is at index 0 or preceded by whitespace, and the token has no spaces.
     */
    function _extractSlashToken(inputEl) {
        const val = inputEl.value || '';
        const caret = typeof inputEl.selectionStart === 'number' ? inputEl.selectionStart : val.length;
        const beforeCaret = val.slice(0, caret);

        const match = /(?:^|\s)(\/[a-zA-Z0-9_-]*)$/.exec(beforeCaret);
        if (!match) return null;

        const query = match[1];
        const start = caret - query.length;
        return {
            start,
            end: caret,
            query
        };
    }

    function _ensurePopupDOM() {
        if (_popupEl) return _popupEl;

        const style = document.createElement('style');
        style.textContent = `
        .ag-slash-ac-popup {
            position: fixed;
            z-index: 9999;
            width: 480px;
            max-width: calc(100vw - 24px);
            background: rgba(15, 23, 42, 0.97);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(99, 102, 241, 0.35);
            border-radius: 12px;
            box-shadow: 0 18px 42px rgba(0, 0, 0, 0.55);
            overflow: hidden;
            display: none;
            font-family: inherit;
        }
        .ag-slash-ac-hdr {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.5rem;
            padding: 0.5rem 0.85rem;
            background: rgba(255, 255, 255, 0.03);
            border-bottom: 1px solid rgba(255, 255, 255, 0.07);
            font-size: 0.71rem;
            color: var(--text-secondary, #94a3b8);
        }
        .ag-slash-ac-hdr-left {
            display: flex;
            align-items: center;
            gap: 0.4rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: var(--text-primary, #f8fafc);
        }
        .ag-slash-ac-hdr-left i {
            color: var(--primary, #6366f1);
        }
        .ag-slash-ac-prof-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.14rem 0.5rem;
            border-radius: 999px;
            background: rgba(99, 102, 241, 0.14);
            color: #a5b4fc;
            font-weight: 600;
            font-size: 0.68rem;
        }
        .ag-slash-ac-list {
            max-height: 260px;
            overflow-y: auto;
            padding: 0.35rem;
        }
        .ag-slash-ac-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            width: 100%;
            text-align: left;
            padding: 0.5rem 0.65rem;
            border: none;
            border-radius: 8px;
            background: transparent;
            color: var(--text-primary, #f8fafc);
            cursor: pointer;
            transition: background 0.12s;
        }
        .ag-slash-ac-item:hover,
        .ag-slash-ac-item.active {
            background: rgba(99, 102, 241, 0.18);
        }
        .ag-slash-ac-item-left {
            display: flex;
            align-items: center;
            gap: 0.65rem;
            min-width: 0;
            flex: 1;
        }
        .ag-slash-ac-icon {
            width: 30px;
            height: 30px;
            border-radius: 8px;
            background: rgba(99, 102, 241, 0.14);
            color: var(--primary, #818cf8);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.82rem;
            flex-shrink: 0;
        }
        .ag-slash-ac-cmd-line {
            display: flex;
            align-items: center;
            gap: 0.45rem;
            flex-wrap: wrap;
        }
        .ag-slash-ac-cmd {
            font-family: 'Fira Code', monospace;
            font-size: 0.79rem;
            font-weight: 700;
            color: #818cf8;
        }
        .ag-slash-ac-arg {
            font-family: 'Fira Code', monospace;
            font-size: 0.69rem;
            color: var(--text-tertiary, #64748b);
        }
        .ag-slash-ac-desc {
            font-size: 0.73rem;
            color: var(--text-secondary, #94a3b8);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            margin-top: 0.1rem;
        }
        .ag-slash-ac-tier {
            font-size: 0.64rem;
            padding: 0.12rem 0.42rem;
            border-radius: 999px;
            font-weight: 600;
            white-space: nowrap;
            flex-shrink: 0;
        }
        .ag-slash-ac-tier.local_sensitive {
            background: rgba(251, 146, 60, 0.14);
            color: #fb923c;
        }
        .ag-slash-ac-tier.cloud_safe {
            background: rgba(52, 211, 153, 0.14);
            color: #34d399;
        }
        .ag-slash-ac-ftr {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.38rem 0.85rem;
            background: rgba(0, 0, 0, 0.25);
            border-top: 1px solid rgba(255, 255, 255, 0.06);
            font-size: 0.68rem;
            color: var(--text-tertiary, #64748b);
        }
        .ag-slash-ac-kbd {
            background: rgba(255, 255, 255, 0.08);
            padding: 0.08rem 0.35rem;
            border-radius: 4px;
            font-family: monospace;
            color: var(--text-secondary, #cbd5e1);
        }
        `;
        document.head.appendChild(style);

        _popupEl = document.createElement('div');
        _popupEl.className = 'ag-slash-ac-popup';
        _popupEl.id = 'ag-slash-ac-popup';
        document.body.appendChild(_popupEl);
        return _popupEl;
    }

    function _positionPopup(inputEl) {
        const popup = _ensurePopupDOM();
        const rect = inputEl.getBoundingClientRect();
        const popupHeight = popup.offsetHeight || 260;
        const spaceAbove = rect.top;
        const spaceBelow = window.innerHeight - rect.bottom;

        let left = Math.max(12, Math.min(rect.left, window.innerWidth - popup.offsetWidth - 12));
        popup.style.left = `${left}px`;

        if (spaceAbove >= popupHeight + 12 || spaceAbove > spaceBelow) {
            popup.style.top = 'auto';
            popup.style.bottom = `${window.innerHeight - rect.top + 8}px`;
        } else {
            popup.style.bottom = 'auto';
            popup.style.top = `${rect.bottom + 8}px`;
        }
    }

    async function _updateForInput(inputEl, forceOpen = false) {
        await loadRegistry();
        if (!inputEl) {
            close();
            return;
        }

        let token = _extractSlashToken(inputEl);
        if (!token && forceOpen) {
            const val = inputEl.value || '';
            const caret = typeof inputEl.selectionStart === 'number' ? inputEl.selectionStart : val.length;
            token = { start: caret, end: caret, query: '/' };
        }

        if (!token) {
            close();
            return;
        }

        const { profileId, contextLabel } = resolveContextForInput(inputEl);
        const { matching, blockedByProfileCount } = _getMatchingConnectors(profileId, token.query);

        _activeInput = inputEl;
        _tokenRange = token;
        _activeItems = matching;
        if (_selectedIndex >= _activeItems.length) _selectedIndex = 0;

        const popup = _ensurePopupDOM();

        if (!matching.length) {
            if (token.query === '/' || blockedByProfileCount > 0) {
                popup.innerHTML = `
                <div class="ag-slash-ac-hdr">
                    <span class="ag-slash-ac-hdr-left"><i class="fas fa-plug-circle-bolt"></i> Connectors</span>
                    <span class="ag-slash-ac-prof-badge"><i class="fas fa-user-shield"></i> ${_esc(contextLabel)}</span>
                </div>
                <div style="padding:0.85rem 1rem; font-size:0.78rem; color:var(--text-secondary);">
                    No matching connectors permitted by <strong>${_esc(contextLabel)}</strong>
                    ${blockedByProfileCount ? `(${blockedByProfileCount} blocked by active profile)` : ''}.
                </div>`;
                popup.style.display = 'block';
                _positionPopup(inputEl);
            } else {
                close();
            }
            return;
        }

        const rowsHtml = matching.map((mod, idx) => {
            const slash = mod.slash_command || `/${mod.id}`;
            const argHint = ARG_HINTS[mod.id] || '';
            const tier = mod.privacy_tier || 'local_sensitive';
            const tierLabel = tier === 'cloud_safe' ? '🌐 Cloud Safe' : '🔒 Local';
            return `
            <button type="button" class="ag-slash-ac-item ${idx === _selectedIndex ? 'active' : ''}" data-idx="${idx}">
                <div class="ag-slash-ac-item-left">
                    <div class="ag-slash-ac-icon"><i class="${_esc(mod.icon || 'fas fa-plug')}"></i></div>
                    <div style="min-width:0; flex:1;">
                        <div class="ag-slash-ac-cmd-line">
                            <span class="ag-slash-ac-cmd">${_esc(slash)}</span>
                            ${argHint ? `<span class="ag-slash-ac-arg">${_esc(argHint)}</span>` : ''}
                        </div>
                        <div class="ag-slash-ac-desc">${_esc(mod.name)} — ${_esc(mod.description || '')}</div>
                    </div>
                </div>
                <span class="ag-slash-ac-tier ${_esc(tier)}">${tierLabel}</span>
            </button>`;
        }).join('');

        popup.innerHTML = `
            <div class="ag-slash-ac-hdr">
                <span class="ag-slash-ac-hdr-left"><i class="fas fa-plug-circle-bolt"></i> Slash Connectors</span>
                <span class="ag-slash-ac-prof-badge"><i class="fas fa-user-shield"></i> ${_esc(contextLabel)}</span>
            </div>
            <div class="ag-slash-ac-list">
                ${rowsHtml}
            </div>
            <div class="ag-slash-ac-ftr">
                <span><span class="ag-slash-ac-kbd">↑↓</span> Navigate · <span class="ag-slash-ac-kbd">Tab</span> / <span class="ag-slash-ac-kbd">Enter</span> Insert · <span class="ag-slash-ac-kbd">Esc</span> Close</span>
                ${blockedByProfileCount > 0 ? `<span title="Blocked by current Connector Profile"><i class="fas fa-lock"></i> ${blockedByProfileCount} hidden by profile</span>` : `<a href="#" id="ag-slash-ac-manage" style="color:var(--primary,#818cf8);text-decoration:none;">Manage Connectors &rarr;</a>`}
            </div>
        `;

        popup.querySelectorAll('.ag-slash-ac-item').forEach(btn => {
            btn.addEventListener('mouseenter', () => {
                _selectedIndex = parseInt(btn.dataset.idx, 10) || 0;
                _highlightSelection();
            });
            btn.addEventListener('mousedown', e => {
                e.preventDefault(); // Keep focus on input
                const idx = parseInt(btn.dataset.idx, 10) || 0;
                _applySelection(idx);
            });
        });

        popup.querySelector('#ag-slash-ac-manage')?.addEventListener('mousedown', e => {
            e.preventDefault();
            close();
            if (typeof window.switchMainTab === 'function') window.switchMainTab('connectors');
        });

        popup.style.display = 'block';
        _positionPopup(inputEl);
    }

    function _highlightSelection() {
        if (!_popupEl) return;
        const items = _popupEl.querySelectorAll('.ag-slash-ac-item');
        items.forEach((el, idx) => {
            const active = idx === _selectedIndex;
            el.classList.toggle('active', active);
            if (active) el.scrollIntoView({ block: 'nearest' });
        });
    }

    function _applySelection(index) {
        const mod = _activeItems[index];
        if (!mod || !_activeInput || !_tokenRange) {
            close();
            return;
        }
        const slash = mod.slash_command || `/${mod.id}`;
        const val = _activeInput.value || '';
        const before = val.slice(0, _tokenRange.start);
        const after = val.slice(_tokenRange.end);
        const insertion = `${slash} `;
        const nextVal = before + insertion + after.replace(/^\s+/, '');
        _activeInput.value = nextVal;

        const newCaret = (before + insertion).length;
        _activeInput.focus();
        if (typeof _activeInput.setSelectionRange === 'function') {
            _activeInput.setSelectionRange(newCaret, newCaret);
        }
        _activeInput.dispatchEvent(new Event('input', { bubbles: true }));
        close();
    }

    function isOpen() {
        return !!(_popupEl && _popupEl.style.display === 'block');
    }

    function close() {
        if (_popupEl) _popupEl.style.display = 'none';
        _activeItems = [];
        _tokenRange = null;
    }

    function openForInput(inputEl) {
        if (!inputEl) return;
        inputEl.focus();
        _updateForInput(inputEl, true);
    }

    function _isEligibleInput(el) {
        if (!el || (el.tagName !== 'TEXTAREA' && el.tagName !== 'INPUT')) return false;
        if (TARGET_IDS.has(el.id)) return true;
        if (el.dataset && el.dataset.slashAutocomplete !== undefined) return true;
        return false;
    }

    function init() {
        loadRegistry();

        // Capture-phase keydown so Enter/Tab/Arrows are intercepted before chat submit handlers
        document.addEventListener('keydown', e => {
            if (!isOpen() || !_activeInput || e.target !== _activeInput) return;

            if (e.key === 'ArrowDown') {
                if (_activeItems.length) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    _selectedIndex = (_selectedIndex + 1) % _activeItems.length;
                    _highlightSelection();
                }
            } else if (e.key === 'ArrowUp') {
                if (_activeItems.length) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    _selectedIndex = (_selectedIndex - 1 + _activeItems.length) % _activeItems.length;
                    _highlightSelection();
                }
            } else if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
                if (_activeItems.length) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    _applySelection(_selectedIndex);
                }
            } else if (e.key === 'Escape') {
                e.preventDefault();
                e.stopImmediatePropagation();
                close();
            }
        }, true);

        document.addEventListener('input', e => {
            const el = e.target;
            if (!_isEligibleInput(el)) return;
            _updateForInput(el, false);
        });

        document.addEventListener('click', e => {
            if (_popupEl && _popupEl.contains(e.target)) return;
            if (e.target?.closest?.('#cc-chat-slash-btn') || e.target?.closest?.('#chat-slash-btn')) return;
            if (_isEligibleInput(e.target)) {
                _updateForInput(e.target, false);
                return;
            }
            close();
        });

        // Re-populate chat profile selector when chat partial or models load
        document.addEventListener('panelLoaded', e => {
            if (e.detail?.tabName === 'chat' || e.detail?.panelId === 'chat-panel') {
                _populateChatProfileSelect();
            }
        });

        document.addEventListener('change', e => {
            if (e.target?.id === 'chat-connector-profile') {
                try { localStorage.setItem('aethvion_chat_connector_profile', e.target.value); } catch {}
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    return {
        loadRegistry,
        invalidateCache,
        resolveContextForInput,
        getResolvedChatProfileId,
        openForInput,
        close,
        isOpen
    };
})();
