'use strict';
/**
 * Aethvion Suite — WorldSim Dashboard
 * mode-worldsim.js
 */

(function () {
    const API        = '/api/worldsim';
    const BROWSE_API = '/api/agents/browse/native';

    // ── State ─────────────────────────────────────────────────────────────────
    let _currentEntityId = null;
    let _currentDb       = 'default'; // named database
    let _currentPath     = null;      // folder-path database (overrides _currentDb)

    // ── Helpers ───────────────────────────────────────────────────────────────

    function _el(id)   { return document.getElementById(id); }
    function _show(id) { _el(id)?.classList.remove('hidden'); }
    function _hide(id) { _el(id)?.classList.add('hidden'); }

    function _showBusy(text = 'Working…') {
        _el('ws-busy-overlay')?.classList.remove('hidden');
        const t = _el('ws-busy-text'); if (t) t.textContent = text;
    }
    function _hideBusy() { _el('ws-busy-overlay')?.classList.add('hidden'); }

    function _toast(msg, type = 'info') {
        if (typeof showToast === 'function') showToast(msg, type);
        else console.log(`[WorldSim] ${msg}`);
    }

    function _fmtDate(iso) {
        if (!iso) return '—';
        try { return new Date(iso).toLocaleDateString(); } catch { return iso; }
    }

    /**
     * Build a URLSearchParams string that includes either ?path= (folder db)
     * or ?db= (named db), plus any extra key/value pairs.
     */
    function _dbParam(extra = {}) {
        const p = new URLSearchParams();
        if (_currentPath) {
            p.set('path', _currentPath);
        } else {
            p.set('db', _currentDb);
        }
        for (const [k, v] of Object.entries(extra)) {
            if (v !== null && v !== undefined && v !== '') p.set(k, String(v));
        }
        return p.toString();
    }

    // ── DB indicator ──────────────────────────────────────────────────────────

    function _updateDbIndicator() {
        const el = _el('ws-db-indicator-name');
        if (!el) return;
        if (_currentPath) {
            // Show just the last folder segment
            const parts = _currentPath.replace(/\\/g, '/').split('/').filter(Boolean);
            el.textContent = parts[parts.length - 1] || _currentPath;
            el.title = _currentPath;
        } else {
            el.textContent = _currentDb;
            el.title = '';
        }
    }

    function _persistDb() {
        const val = _currentPath
            ? JSON.stringify({ type: 'path', path: _currentPath })
            : JSON.stringify({ type: 'named', name: _currentDb });
        localStorage.setItem('worldsim_last_db', val);
    }

    function _resetView() {
        _hide('ws-entity-view');
        _hide('ws-list-view');
        _hide('ws-validation-view');
        _show('ws-placeholder');
        _currentEntityId = null;
    }

    // ── Database modal ────────────────────────────────────────────────────────

    async function _openDbModal() {
        _show('ws-db-modal');
        // Load named databases
        const listEl = _el('ws-db-named-list');
        if (listEl) {
            listEl.innerHTML = '<div class="ws-empty-hint"><i class="fas fa-spinner fa-spin"></i></div>';
            try {
                const res  = await fetch(`${API}/databases`);
                const data = await res.json();
                let dbs = (data.databases || []).map(d => d.name);
                if (!dbs.includes('default')) dbs.unshift('default');

                if (!dbs.length) {
                    listEl.innerHTML = '<div class="ws-empty-hint">No named databases yet.</div>';
                } else {
                    listEl.innerHTML = dbs.map(name => {
                        const active = (!_currentPath && name === _currentDb) ? ' ws-db-named-active' : '';
                        return `<div class="ws-db-named-item${active}" data-name="${name}">
                            <i class="fas fa-database ws-db-named-icon"></i>
                            <span>${name}</span>
                        </div>`;
                    }).join('');
                    listEl.querySelectorAll('.ws-db-named-item').forEach(item => {
                        item.addEventListener('click', () => {
                            _switchToNamed(item.dataset.name);
                            _closeDbModal();
                        });
                    });
                }
            } catch (e) {
                listEl.innerHTML = '<div class="ws-empty-hint">Could not load databases.</div>';
            }
        }
        // Pre-fill path input if we're already on a folder db
        const folderInput = _el('ws-db-folder-input');
        if (folderInput) folderInput.value = _currentPath || '';
        folderInput?.focus();
    }

    function _closeDbModal() {
        _hide('ws-db-modal');
    }

    async function _browseFolder() {
        const btn = _el('ws-db-browse-btn');
        const folderInput = _el('ws-db-folder-input');
        const initial = folderInput?.value?.trim() || _currentPath || '';

        if (btn) { btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true; }

        try {
            const res  = await fetch(`${BROWSE_API}?initial=${encodeURIComponent(initial)}`);
            const data = await res.json();
            if (!data.cancelled && data.path) {
                if (folderInput) folderInput.value = data.path;
            }
        } catch (e) {
            _toast('Could not open folder browser.', 'error');
        } finally {
            if (btn) { btn.innerHTML = '<i class="fas fa-folder-open"></i>'; btn.disabled = false; }
        }
    }

    function _openSelectedDb() {
        const folderInput = _el('ws-db-folder-input');
        const path = folderInput?.value?.trim();
        if (path) {
            _switchToPath(path);
        }
        _closeDbModal();
    }

    function _switchToNamed(name) {
        _currentDb   = name;
        _currentPath = null;
        _updateDbIndicator();
        _persistDb();
        _resetView();
        _refreshStats();
        _toast(`Database: ${name}`, 'info');
    }

    function _switchToPath(folderPath) {
        _currentPath = folderPath;
        _currentDb   = 'default';
        _updateDbIndicator();
        _persistDb();
        _resetView();
        _refreshStats();
        const name = folderPath.replace(/\\/g, '/').split('/').filter(Boolean).pop() || folderPath;
        _toast(`Database: ${name}`, 'info');
    }

    // ── Models ────────────────────────────────────────────────────────────────

    async function _fetchModels() {
        const sel = _el('ws-distill-model');
        if (!sel) return;
        try {
            const res  = await fetch('/api/registry/models/chat');
            if (!res.ok) return;
            const data = await res.json();
            const saved = localStorage.getItem('worldsim_last_model') || 'auto';
            if (window.generateCategorizedModelOptions) {
                sel.innerHTML = window.generateCategorizedModelOptions(data, 'chat', saved);
            } else {
                let html = `<option value="auto" ${saved === 'auto' ? 'selected' : ''}>Auto Select</option>`;
                for (const m of data.models || []) {
                    html += `<option value="${m.id}" ${m.id === saved ? 'selected' : ''}>${m.name || m.id}</option>`;
                }
                sel.innerHTML = html;
            }
        } catch (e) {
            console.warn('[WorldSim] Model fetch failed:', e);
        }
    }

    // ── Stats ─────────────────────────────────────────────────────────────────

    async function _refreshStats() {
        try {
            const res  = await fetch(`${API}/stats?${_dbParam()}`);
            const data = await res.json();
            const total = data.total_entities ?? '—';
            const stubs = data.stub_count     ?? '—';
            const idx   = data.index_size     ?? '—';
            const te = _el('ws-stat-total'); if (te) te.innerHTML = `<i class="fas fa-database"></i> ${total} entities`;
            const st = _el('ws-stat-stubs'); if (st) st.innerHTML = `<i class="fas fa-circle-half-stroke"></i> ${stubs} stubs`;
            const si = _el('ws-stat-index'); if (si) si.innerHTML = `<i class="fas fa-hashtag"></i> ${idx} indexed`;
        } catch (e) {
            console.error('[WorldSim] Stats failed:', e);
        }
    }

    // ── Entity display ────────────────────────────────────────────────────────

    function _renderEntity(entity) {
        _currentEntityId = entity.id;
        _hide('ws-placeholder');
        _hide('ws-list-view');
        _hide('ws-validation-view');
        _show('ws-entity-view');

        const typeBadge = _el('ws-ev-type-badge');
        if (typeBadge) {
            typeBadge.textContent = entity.type || 'other';
            typeBadge.className = `ws-type-badge ws-type-${entity.type || 'other'}`;
        }
        const nameEl = _el('ws-ev-name');
        if (nameEl) nameEl.textContent = entity.name || '—';
        const summaryEl = _el('ws-ev-summary');
        if (summaryEl) summaryEl.textContent = entity.sections?.core?.summary || '';
        const statusEl = _el('ws-ev-status-badge');
        if (statusEl) {
            statusEl.textContent = entity.status || 'active';
            statusEl.className = `ws-status-badge ws-status-${entity.status || 'active'}`;
        }
        const metaEl = _el('ws-ev-meta');
        if (metaEl) {
            metaEl.innerHTML = `
                <span>ID: <code>${entity.id}</code></span>
                <span>v${entity.version || 1}</span>
                <span>Source: ${entity.source || '—'}</span>
                <span>Updated: ${_fmtDate(entity.updated)}</span>`;
        }

        const core    = entity.sections?.core || {};
        const aliasEl = _el('ws-ev-aliases');
        if (aliasEl) {
            aliasEl.innerHTML = core.aliases?.length
                ? `<div class="ws-ev-section-label">Aliases</div><div class="ws-tag-row">${core.aliases.map(a => `<span class="ws-tag">${a}</span>`).join('')}</div>`
                : '';
        }
        const catEl = _el('ws-ev-categories');
        if (catEl) {
            catEl.innerHTML = core.categories?.length
                ? `<div class="ws-ev-section-label">Categories</div><div class="ws-tag-row">${core.categories.map(c => `<span class="ws-cat">${c}</span>`).join('')}</div>`
                : '';
        }
        const tagEl = _el('ws-ev-tags');
        if (tagEl) {
            tagEl.innerHTML = core.tags?.length
                ? `<div class="ws-ev-section-label">Tags</div><div class="ws-tag-row">${core.tags.map(t => `<span class="ws-tag ws-tag-accent">${t}</span>`).join('')}</div>`
                : '';
        }

        const timeline = entity.sections?.timeline || [];
        const tlEl = _el('ws-ev-timeline-list');
        if (tlEl) {
            tlEl.innerHTML = timeline.length
                ? timeline.map(ev => `
                    <div class="ws-tl-item">
                        <div class="ws-tl-date">${ev.date || '?'}</div>
                        <div class="ws-tl-event">${ev.event || ''}</div>
                    </div>`).join('')
                : '<div class="ws-empty-hint">No timeline events</div>';
        }

        const relations = entity.sections?.relations || [];
        const relEl = _el('ws-ev-relations-list');
        if (relEl) {
            relEl.innerHTML = relations.length
                ? relations.map(rel => `
                    <div class="ws-rel-item" data-target="${rel.target_id || ''}" role="button" tabindex="0">
                        <span class="ws-rel-kind">${rel.kind || 'related_to'}</span>
                        <span class="ws-rel-target">${rel.target_id || '—'}</span>
                        ${rel.note ? `<span class="ws-rel-note">${rel.note}</span>` : ''}
                    </div>`).join('')
                : '<div class="ws-empty-hint">No relations</div>';

            relEl.querySelectorAll('.ws-rel-item[data-target]').forEach(item => {
                const tid = item.dataset.target;
                if (!tid) return;
                item.addEventListener('click', () => _loadEntity(tid));
                item.addEventListener('keydown', e => { if (e.key === 'Enter') _loadEntity(tid); });
                fetch(`${API}/entities/${tid}?${_dbParam()}`)
                    .then(r => r.ok ? r.json() : null)
                    .then(ent => {
                        if (ent) {
                            const tEl = item.querySelector('.ws-rel-target');
                            if (tEl) tEl.textContent = ent.name;
                        }
                    }).catch(() => {});
            });
        }

        const props = entity.sections?.properties || {};
        const propEl = _el('ws-ev-props-table');
        if (propEl) {
            const entries = Object.entries(props);
            propEl.innerHTML = entries.length
                ? `<table class="ws-props-tbl"><tbody>${entries.map(([k, v]) => `<tr><td class="ws-prop-key">${k}</td><td class="ws-prop-val">${v}</td></tr>`).join('')}</tbody></table>`
                : '<div class="ws-empty-hint">No properties</div>';
        }

        const stubs = entity.sections?.stubs || [];
        const stubEl = _el('ws-ev-stubs-list');
        if (stubEl) {
            stubEl.innerHTML = stubs.length
                ? stubs.map(s => `<div class="ws-stub-item"><i class="fas fa-circle-half-stroke"></i> ${s}</div>`).join('')
                : '<div class="ws-empty-hint">No sub-topics listed</div>';
        }

        const rawEl = _el('ws-ev-raw-json');
        if (rawEl) rawEl.textContent = JSON.stringify(entity, null, 2);

        _activateEntityTab('ws-ev-tab-core');
    }

    function _activateEntityTab(targetId) {
        document.querySelectorAll('.ws-ev-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.target === targetId);
        });
        document.querySelectorAll('.ws-ev-panel').forEach(panel => {
            panel.classList.toggle('hidden', panel.id !== targetId);
            panel.classList.toggle('active', panel.id === targetId);
        });
    }

    async function _loadEntity(entityId) {
        try {
            const res = await fetch(`${API}/entities/${entityId}?${_dbParam()}`);
            if (!res.ok) { _toast(`Entity not found: ${entityId}`, 'error'); return; }
            _renderEntity(await res.json());
        } catch (e) {
            _toast(`Failed to load entity: ${e.message}`, 'error');
        }
    }

    // ── Distillation ──────────────────────────────────────────────────────────

    async function _distill() {
        const content = _el('ws-distill-text')?.value?.trim();
        const model   = _el('ws-distill-model')?.value || null;
        if (!content) { _toast('Paste some content to distill.', 'error'); return; }
        if (model && model !== 'auto') localStorage.setItem('worldsim_last_model', model);

        const statusEl = _el('ws-distill-status');
        if (statusEl) {
            statusEl.textContent = 'Distilling…';
            statusEl.className = 'ws-status ws-status-loading';
            statusEl.classList.remove('hidden');
        }
        _el('ws-distill-btn').disabled = true;

        try {
            const res  = await fetch(`${API}/distill?${_dbParam()}`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ content, model: (model && model !== 'auto') ? model : undefined }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail?.message || JSON.stringify(data.detail) || 'Distillation failed');
            if (statusEl) {
                statusEl.textContent = data.was_created
                    ? `✓ Created: ${data.entity_name} (${data.stub_count} stubs found)`
                    : `✓ Updated: ${data.entity_name}`;
                statusEl.className = 'ws-status ws-status-ok';
            }
            await _loadEntity(data.entity_id);
            await _refreshStats();
        } catch (e) {
            if (statusEl) { statusEl.textContent = `✗ ${e.message}`; statusEl.className = 'ws-status ws-status-error'; }
            _toast(e.message, 'error');
        } finally {
            _el('ws-distill-btn').disabled = false;
        }
    }

    // ── Search ────────────────────────────────────────────────────────────────

    async function _search() {
        const q    = _el('ws-search-input')?.value?.trim() || '';
        const type = _el('ws-search-type')?.value || '';
        const resultsEl = _el('ws-search-results');
        if (!resultsEl) return;
        resultsEl.innerHTML = '<div class="ws-empty-hint"><i class="fas fa-spinner fa-spin"></i> Searching…</div>';

        try {
            const params = new URLSearchParams(_dbParam({ limit: 40 }));
            if (q)    params.set('q', q);
            if (type) params.set('entity_type', type);
            const res  = await fetch(`${API}/search?${params}`);
            const data = await res.json();
            const results = data.results || [];

            if (!results.length) { resultsEl.innerHTML = '<div class="ws-empty-hint">No results found</div>'; return; }

            resultsEl.innerHTML = results.map(r => `
                <div class="ws-search-item" data-id="${r.id}" role="button" tabindex="0">
                    <div class="ws-si-row">
                        <span class="ws-type-badge ws-type-${r.type || 'other'}">${r.type || '?'}</span>
                        <span class="ws-si-name">${r.name}</span>
                        ${r.status === 'stub' ? '<span class="ws-status-badge ws-status-stub">stub</span>' : ''}
                    </div>
                    ${r.summary ? `<div class="ws-si-summary">${r.summary}</div>` : ''}
                </div>`).join('');

            resultsEl.querySelectorAll('.ws-search-item').forEach(item => {
                item.addEventListener('click', () => _loadEntity(item.dataset.id));
                item.addEventListener('keydown', e => { if (e.key === 'Enter') _loadEntity(item.dataset.id); });
            });
        } catch (e) {
            resultsEl.innerHTML = `<div class="ws-empty-hint">Error: ${e.message}</div>`;
        }
    }

    // ── List view ─────────────────────────────────────────────────────────────

    async function _showList(mode = 'stubs') {
        _hide('ws-placeholder'); _hide('ws-entity-view'); _hide('ws-validation-view'); _show('ws-list-view');
        const titleEl = _el('ws-lv-title');
        const itemsEl = _el('ws-lv-items');
        if (!itemsEl) return;
        if (titleEl) titleEl.textContent = mode === 'stubs' ? 'Stub Entities' : 'All Entities';
        itemsEl.innerHTML = '<div class="ws-empty-hint"><i class="fas fa-spinner fa-spin"></i> Loading…</div>';

        try {
            const url = mode === 'stubs'
                ? `${API}/stubs?${_dbParam()}`
                : `${API}/entities?${_dbParam({ limit: 200 })}`;
            const res   = await fetch(url);
            const data  = await res.json();
            const items = mode === 'stubs' ? (data.stubs || []) : (data.entities || []);

            if (!items.length) { itemsEl.innerHTML = '<div class="ws-empty-hint">None found</div>'; return; }

            itemsEl.innerHTML = items.map(e => `
                <div class="ws-lv-item" data-id="${e.id}" role="button" tabindex="0">
                    <span class="ws-type-badge ws-type-${e.type || 'other'}">${e.type || '?'}</span>
                    <span class="ws-lv-name">${e.name || e.id}</span>
                    ${e.status === 'stub' ? '<span class="ws-status-badge ws-status-stub">stub</span>' : ''}
                </div>`).join('');

            itemsEl.querySelectorAll('.ws-lv-item').forEach(item => {
                item.addEventListener('click', () => _loadEntity(item.dataset.id));
                item.addEventListener('keydown', e => { if (e.key === 'Enter') _loadEntity(item.dataset.id); });
            });
        } catch (e) {
            itemsEl.innerHTML = `<div class="ws-empty-hint">Error: ${e.message}</div>`;
        }
    }

    // ── Expansion ─────────────────────────────────────────────────────────────

    async function _expandAll() {
        _showBusy('Expanding stubs…');
        try {
            const res  = await fetch(`${API}/expand?${_dbParam()}`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ max_entities: 10 }),
            });
            const data = await res.json();
            _toast(`Expanded ${data.expanded?.length || 0}, ${data.new_stubs?.length || 0} new stubs`, 'success');
            await _refreshStats();
        } catch (e) {
            _toast(`Expansion failed: ${e.message}`, 'error');
        } finally { _hideBusy(); }
    }

    async function _deepenCurrent() {
        if (!_currentEntityId) return;
        _showBusy('Deepening entity stubs…');
        try {
            const res  = await fetch(`${API}/entities/${_currentEntityId}/deepen?${_dbParam({ max_stubs: 5 })}`, { method: 'POST' });
            const data = await res.json();
            _toast(`Deepened: ${data.expanded?.length || 0} new entities expanded`, 'success');
            await _loadEntity(_currentEntityId);
            await _refreshStats();
        } catch (e) {
            _toast(`Deepen failed: ${e.message}`, 'error');
        } finally { _hideBusy(); }
    }

    // ── Validation ────────────────────────────────────────────────────────────

    async function _validateAll() {
        _showBusy('Running integrity checks…');
        try {
            const res  = await fetch(`${API}/validate?${_dbParam()}`);
            const data = await res.json();
            _hide('ws-placeholder'); _hide('ws-entity-view'); _hide('ws-list-view'); _show('ws-validation-view');

            const sumEl = _el('ws-val-summary');
            if (sumEl) {
                sumEl.innerHTML = `
                    <div class="ws-val-chips">
                        <span class="ws-val-chip ws-val-ok"><i class="fas fa-check-circle"></i> ${data.clean ?? 0} clean</span>
                        <span class="ws-val-chip ws-val-err"><i class="fas fa-exclamation-circle"></i> ${data.with_errors ?? 0} with errors</span>
                        <span class="ws-val-chip"><i class="fas fa-triangle-exclamation"></i> ${data.total_warnings ?? 0} warnings</span>
                    </div>`;
            }
            const issueEl = _el('ws-val-issues');
            if (issueEl) {
                const failed = data.failed_ids || [];
                issueEl.innerHTML = failed.length
                    ? failed.map(id => `<div class="ws-val-item" data-id="${id}" role="button" tabindex="0"><i class="fas fa-exclamation-triangle"></i> <code>${id}</code></div>`).join('')
                    : '<div class="ws-empty-hint">All entities passed checks.</div>';
                issueEl.querySelectorAll('.ws-val-item[data-id]').forEach(item => {
                    item.addEventListener('click', () => _loadEntity(item.dataset.id));
                });
            }
        } catch (e) {
            _toast(`Validation failed: ${e.message}`, 'error');
        } finally { _hideBusy(); }
    }

    async function _validateCurrent() {
        if (!_currentEntityId) return;
        try {
            const res    = await fetch(`${API}/validate/${_currentEntityId}?${_dbParam()}`);
            const data   = await res.json();
            const issues = data.issues || [];
            const errors = issues.filter(i => i.severity === 'error').length;
            const warns  = issues.filter(i => i.severity === 'warning').length;
            if (!errors && !warns) _toast('Entity passed all integrity checks ✓', 'success');
            else { _toast(`${errors} error(s), ${warns} warning(s) — check console`, 'error'); console.table(issues); }
        } catch (e) {
            _toast(`Validation failed: ${e.message}`, 'error');
        }
    }

    // ── Init ──────────────────────────────────────────────────────────────────

    function _wire() {
        // Distill
        _el('ws-distill-btn')?.addEventListener('click', _distill);
        _el('ws-distill-text')?.addEventListener('keydown', e => { if (e.key === 'Enter' && e.ctrlKey) _distill(); });

        // Search
        _el('ws-search-btn')?.addEventListener('click', _search);
        _el('ws-search-input')?.addEventListener('keydown', e => { if (e.key === 'Enter') _search(); });

        // Toolbar
        _el('ws-refresh-btn')?.addEventListener('click', _refreshStats);
        _el('ws-expand-btn')?.addEventListener('click', _expandAll);
        _el('ws-validate-btn')?.addEventListener('click', _validateAll);

        // Quick actions
        _el('ws-load-stubs-btn')?.addEventListener('click', () => _showList('stubs'));
        _el('ws-load-all-btn')?.addEventListener('click', () => _showList('all'));

        // Entity view
        _el('ws-ev-expand-btn')?.addEventListener('click', _deepenCurrent);
        _el('ws-ev-validate-btn')?.addEventListener('click', _validateCurrent);
        document.querySelectorAll('.ws-ev-tab').forEach(btn => {
            btn.addEventListener('click', () => _activateEntityTab(btn.dataset.target));
        });

        // List / validation close
        _el('ws-lv-close')?.addEventListener('click', () => { _hide('ws-list-view');       _show('ws-placeholder'); });
        _el('ws-val-close')?.addEventListener('click', () => { _hide('ws-validation-view'); _show('ws-placeholder'); });

        // Database selector
        _el('ws-db-change-btn')?.addEventListener('click', _openDbModal);
        _el('ws-db-modal-close')?.addEventListener('click', _closeDbModal);
        _el('ws-db-modal-cancel')?.addEventListener('click', _closeDbModal);
        _el('ws-db-browse-btn')?.addEventListener('click', _browseFolder);
        _el('ws-db-modal-open')?.addEventListener('click', _openSelectedDb);
        _el('ws-db-folder-input')?.addEventListener('keydown', e => { if (e.key === 'Enter') _openSelectedDb(); });

        // Close modal on overlay click
        _el('ws-db-modal')?.addEventListener('click', e => {
            if (e.target === _el('ws-db-modal')) _closeDbModal();
        });
    }

    function init() {
        const root = _el('worldsim-root');
        if (!root || root.dataset.wsInit) return;
        root.dataset.wsInit = '1';

        // Restore last-used database
        try {
            const saved = localStorage.getItem('worldsim_last_db');
            if (saved) {
                const obj = JSON.parse(saved);
                if (obj.type === 'path' && obj.path) {
                    _currentPath = obj.path;
                    _currentDb   = 'default';
                } else if (obj.type === 'named' && obj.name) {
                    _currentDb   = obj.name;
                    _currentPath = null;
                }
            }
        } catch { /* ignore bad storage */ }

        _updateDbIndicator();
        _wire();
        _fetchModels();
        _refreshStats();
    }

    document.addEventListener('panelLoaded', function (e) {
        if (e.detail?.tabName === 'worldsim') init();
    });
})();
