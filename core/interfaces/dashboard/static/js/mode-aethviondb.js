'use strict';
/**
 * Aethvion Suite — AethvionDB
 * mode-aethviondb.js
 *
 * Entity list is the primary view — auto-loaded on init.
 * Backend: /api/worldsim/ (unchanged).
 * All DOM IDs use the adb- prefix to match partials/aethviondb.html.
 */

(function () {
    const API        = '/api/worldsim';
    const BROWSE_API = '/api/agents/browse/native';

    // ── State ─────────────────────────────────────────────────────────────────
    let _currentEntityId     = null;
    let _currentEntityStatus = null;  // 'stub' | 'active' — set when entity detail opens
    let _currentDb           = 'default'; // named database
    let _currentPath         = null;      // folder-path database (overrides _currentDb)
    let _currentFilter       = 'all';     // 'all' | 'active' | 'stub'
    let _currentPage         = 0;         // 0-indexed current page
    let _totalCount          = 0;         // total entities for current filter
    const _PAGE_SIZE         = 100;

    // ── Helpers ───────────────────────────────────────────────────────────────

    function _el(id)   { return document.getElementById(id); }
    function _show(id) { _el(id)?.classList.remove('hidden'); }
    function _hide(id) { _el(id)?.classList.add('hidden'); }

    function _showBusy(text = 'Working…') {
        _el('adb-busy-overlay')?.classList.remove('hidden');
        const t = _el('adb-busy-text'); if (t) t.textContent = text;
    }
    function _hideBusy() { _el('adb-busy-overlay')?.classList.add('hidden'); }

    function _toast(msg, type = 'info') {
        if (typeof showToast === 'function') showToast(msg, type);
        else console.log(`[AethvionDB] ${msg}`);
    }

    function _fmtDate(iso) {
        if (!iso) return '—';
        try { return new Date(iso).toLocaleDateString(); } catch { return iso; }
    }

    function _fmtBytes(bytes) {
        if (bytes == null) return '—';
        if (bytes < 1024)             return bytes + ' B';
        if (bytes < 1024 * 1024)      return (bytes / 1024).toFixed(1) + ' KB';
        if (bytes < 1024 ** 3)        return (bytes / 1024 / 1024).toFixed(1) + ' MB';
        return (bytes / 1024 ** 3).toFixed(2) + ' GB';
    }

    function _fmtNum(n) {
        if (n == null) return '—';
        return Number(n).toLocaleString();
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

    // ── View switching ────────────────────────────────────────────────────────

    function _showEntityList() {
        _currentEntityId     = null;
        _currentEntityStatus = null;
        _show('adb-list-pane');
        _hide('adb-entity-detail');
        _hide('adb-validation-view');
    }

    function _showEntityDetail() {
        _hide('adb-list-pane');
        _show('adb-entity-detail');
        _hide('adb-validation-view');
    }

    function _showValidation() {
        _hide('adb-list-pane');
        _hide('adb-entity-detail');
        _show('adb-validation-view');
    }

    // ── DB indicator ──────────────────────────────────────────────────────────

    function _updateDbIndicator() {
        const el = _el('adb-db-indicator-name');
        if (!el) return;
        if (_currentPath) {
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
        localStorage.setItem('aethviondb_last_db', val);
    }

    // ── Database modal ────────────────────────────────────────────────────────

    async function _openDbModal() {
        _show('adb-db-modal');
        const listEl = _el('adb-db-named-list');
        if (listEl) {
            listEl.innerHTML = '<div class="adb-empty-hint"><i class="fas fa-spinner fa-spin"></i></div>';
            try {
                const res  = await fetch(`${API}/databases`);
                const data = await res.json();
                let dbs = (data.databases || []).map(d => d.name);
                if (!dbs.includes('default')) dbs.unshift('default');

                if (!dbs.length) {
                    listEl.innerHTML = '<div class="adb-empty-hint">No named databases yet.</div>';
                } else {
                    listEl.innerHTML = dbs.map(name => {
                        const active = (!_currentPath && name === _currentDb) ? ' adb-db-named-active' : '';
                        return `<div class="adb-db-named-item${active}" data-name="${name}">
                            <i class="fas fa-database adb-db-named-icon"></i>
                            <span>${name}</span>
                        </div>`;
                    }).join('');
                    listEl.querySelectorAll('.adb-db-named-item').forEach(item => {
                        item.addEventListener('click', () => {
                            _switchToNamed(item.dataset.name);
                            _closeDbModal();
                        });
                    });
                }
            } catch {
                listEl.innerHTML = '<div class="adb-empty-hint">Could not load databases.</div>';
            }
        }
        const folderInput = _el('adb-db-folder-input');
        if (folderInput) folderInput.value = _currentPath || '';
    }

    function _closeDbModal() {
        _hide('adb-db-modal');
    }

    async function _browseFolder() {
        const btn         = _el('adb-db-browse-btn');
        const folderInput = _el('adb-db-folder-input');
        const initial     = folderInput?.value?.trim() || _currentPath || '';

        if (btn) { btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true; }

        try {
            const res  = await fetch(`${BROWSE_API}?initial=${encodeURIComponent(initial)}`);
            const data = await res.json();
            if (!data.cancelled && data.path) {
                if (folderInput) folderInput.value = data.path;
            }
        } catch {
            _toast('Could not open folder browser.', 'error');
        } finally {
            if (btn) { btn.innerHTML = '<i class="fas fa-folder-open"></i>'; btn.disabled = false; }
        }
    }

    function _openSelectedDb() {
        const folderInput = _el('adb-db-folder-input');
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
        _currentFilter = 'all';
        _currentPage   = 0;
        _setFilterActive('all');
        _resetStatsDisplay();
        _loadEntityList('all', 0);
        _toast(`Database: ${name}`, 'info');
    }

    function _switchToPath(folderPath) {
        _currentPath = folderPath;
        _currentDb   = 'default';
        _updateDbIndicator();
        _persistDb();
        _currentFilter = 'all';
        _currentPage   = 0;
        _setFilterActive('all');
        _resetStatsDisplay();
        _loadEntityList('all', 0);
        const name = folderPath.replace(/\\/g, '/').split('/').filter(Boolean).pop() || folderPath;
        _toast(`Database: ${name}`, 'info');
    }

    /** Reset stat values to "—" and show the hint when the DB changes. */
    function _resetStatsDisplay() {
        ['adb-stat-total', 'adb-stat-stubs', 'adb-stat-index', 'adb-stat-size'].forEach(id => {
            const el = _el(id); if (el) el.textContent = '—';
        });
        _show('adb-stats-hint');
    }

    // ── Stats ─────────────────────────────────────────────────────────────────

    async function _refreshStats() {
        const refreshBtn = _el('adb-refresh-btn');
        if (refreshBtn) { refreshBtn.disabled = true; refreshBtn.classList.add('adb-btn-spinning'); }
        try {
            const res  = await fetch(`${API}/stats?${_dbParam()}`);
            const data = await res.json();
            const te = _el('adb-stat-total'); if (te) te.textContent = _fmtNum(data.total_entities);
            const st = _el('adb-stat-stubs'); if (st) st.textContent = _fmtNum(data.stub_count);
            const si = _el('adb-stat-index'); if (si) si.textContent = _fmtNum(data.index_size);
            const sz = _el('adb-stat-size');  if (sz) sz.textContent = _fmtBytes(data.total_size_bytes);
            _hide('adb-stats-hint');
        } catch (e) {
            console.error('[AethvionDB] Stats failed:', e);
            _toast('Failed to load stats', 'error');
        } finally {
            if (refreshBtn) { refreshBtn.disabled = false; refreshBtn.classList.remove('adb-btn-spinning'); }
        }
    }

    // ── Entity list (primary view) ────────────────────────────────────────────

    function _setFilterActive(filter) {
        document.querySelectorAll('.adb-filter-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.filter === filter);
        });
    }

    async function _loadEntityList(filter = 'all', page = 0) {
        _currentFilter = filter;
        _currentPage   = page;
        _showEntityList();
        _hide('adb-entity-pagination');

        const listEl = _el('adb-entity-list');
        if (!listEl) return;
        listEl.innerHTML = '<div class="adb-list-loading"><i class="fas fa-spinner fa-spin"></i> Loading…</div>';

        const offset = page * _PAGE_SIZE;

        try {
            const statusParam = filter === 'stub'   ? { status: 'stub' }
                              : filter === 'active' ? { status: 'active' }
                              : {};
            const res  = await fetch(`${API}/entities?${_dbParam({ limit: _PAGE_SIZE, offset, ...statusParam })}`);
            const data = await res.json();
            const total    = data.total    || 0;
            const entities = data.entities || [];

            _totalCount = total;

            if (!entities.length && page === 0) {
                listEl.innerHTML = '<div class="adb-empty-state"><i class="fas fa-inbox"></i><p>No entities found</p></div>';
                return;
            }

            listEl.innerHTML = _renderTable(entities);
            listEl.querySelectorAll('.adb-tr').forEach(row => {
                row.addEventListener('click',   ()  => _loadEntity(row.dataset.id));
                row.addEventListener('keydown', ev  => { if (ev.key === 'Enter') _loadEntity(row.dataset.id); });
            });

            _renderPagination(total, page);
        } catch (err) {
            listEl.innerHTML = `<div class="adb-empty-state"><i class="fas fa-exclamation-triangle"></i><p>Error: ${err.message}</p></div>`;
        }
    }

    function _renderPagination(total, page) {
        const pagEl = _el('adb-entity-pagination');
        if (!pagEl) return;

        const totalPages = Math.ceil(total / _PAGE_SIZE);
        if (total <= _PAGE_SIZE) {
            // Show count-only bar for context, no prev/next needed
            pagEl.classList.remove('hidden');
            pagEl.innerHTML = `<div class="adb-pag-info">${_fmtNum(total)} ${total === 1 ? 'entity' : 'entities'}</div>`;
            return;
        }

        const from = page * _PAGE_SIZE + 1;
        const to   = Math.min((page + 1) * _PAGE_SIZE, total);

        pagEl.classList.remove('hidden');
        pagEl.innerHTML = `
            <div class="adb-pag-info">
                Showing ${_fmtNum(from)}–${_fmtNum(to)} of ${_fmtNum(total)}
            </div>
            <div class="adb-pag-controls">
                <button class="adb-pag-btn" id="adb-pag-prev" ${page === 0 ? 'disabled' : ''}>
                    <i class="fas fa-chevron-left"></i> Prev
                </button>
                <span class="adb-pag-page">Page ${page + 1} of ${totalPages}</span>
                <button class="adb-pag-btn" id="adb-pag-next" ${page >= totalPages - 1 ? 'disabled' : ''}>
                    Next <i class="fas fa-chevron-right"></i>
                </button>
            </div>`;

        _el('adb-pag-prev')?.addEventListener('click', () => _loadEntityList(_currentFilter, page - 1));
        _el('adb-pag-next')?.addEventListener('click', () => _loadEntityList(_currentFilter, page + 1));
    }

    function _entityRowHtml(e) {
        const isStub    = e.status === 'stub';
        const badgeCls  = isStub ? 'adb-badge-stub' : 'adb-badge-expanded';
        const badgeTxt  = isStub ? 'stub' : 'expanded';
        const summary   = e.summary || e.sections?.core?.summary || '';
        const tags      = e.tags || e.sections?.core?.tags || [];
        const relCount  = e.relations_count != null ? e.relations_count : (e.sections?.relations?.length ?? null);
        const stubCount = e.stubs_count     != null ? e.stubs_count     : (e.sections?.stubs?.length    ?? null);

        const tagHtml = tags.slice(0, 3).map(t => `<span class="adb-tag-sm">${t}</span>`).join('')
                      + (tags.length > 3 ? `<span class="adb-tag-sm">+${tags.length - 3}</span>` : '');

        return `<tr class="adb-tr" data-id="${e.id}" tabindex="0">
            <td class="adb-td">
                <span class="adb-type-badge adb-type-${e.type || 'other'}">${e.type || 'other'}</span>
            </td>
            <td class="adb-td">
                <div class="adb-td-name-text">${e.name || e.id}</div>
                ${summary ? `<div class="adb-td-summary">${summary}</div>` : ''}
            </td>
            <td class="adb-td">
                <div class="adb-td-tags">${tagHtml}</div>
            </td>
            <td class="adb-td adb-td-num${relCount  ? ' has-data' : ''}">${relCount  ?? '—'}</td>
            <td class="adb-td adb-td-num${stubCount ? ' has-data' : ''}">${stubCount ?? '—'}</td>
            <td class="adb-td">
                <span class="adb-badge ${badgeCls}">${badgeTxt}</span>
            </td>
        </tr>`;
    }

    function _renderTable(entities) {
        return `<table class="adb-table">
            <colgroup>
                <col class="adb-col-type">
                <col>
                <col class="adb-col-tags">
                <col class="adb-col-rel">
                <col class="adb-col-stubs">
                <col class="adb-col-status">
            </colgroup>
            <thead>
                <tr>
                    <th class="adb-col-type">Type</th>
                    <th>Name / Summary</th>
                    <th class="adb-col-tags">Tags</th>
                    <th class="adb-col-rel" title="Number of relations">Rel.</th>
                    <th class="adb-col-stubs" title="Number of sub-topics">Sub.</th>
                    <th class="adb-col-status">Status</th>
                </tr>
            </thead>
            <tbody>
                ${entities.map(e => _entityRowHtml(e)).join('')}
            </tbody>
        </table>`;
    }

    // ── Search ────────────────────────────────────────────────────────────────

    async function _search() {
        const q    = _el('adb-search-input')?.value?.trim() || '';
        const type = _el('adb-search-type')?.value || '';

        // If both empty, reload the full list with current filter
        if (!q && !type) { _loadEntityList(_currentFilter); return; }

        _showEntityList();
        _hide('adb-entity-pagination');
        const listEl = _el('adb-entity-list');
        if (!listEl) return;
        listEl.innerHTML = '<div class="adb-list-loading"><i class="fas fa-spinner fa-spin"></i> Searching…</div>';

        try {
            const params = new URLSearchParams(_dbParam({ limit: 100 }));
            if (q)    params.set('q', q);
            if (type) params.set('entity_type', type);
            const res     = await fetch(`${API}/search?${params}`);
            const data    = await res.json();
            const results = data.results || [];

            if (!results.length) {
                listEl.innerHTML = '<div class="adb-empty-state"><i class="fas fa-search"></i><p>No results found</p></div>';
                return;
            }

            listEl.innerHTML = _renderTable(results);
            listEl.querySelectorAll('.adb-tr').forEach(row => {
                row.addEventListener('click',   ()  => _loadEntity(row.dataset.id));
                row.addEventListener('keydown', ev  => { if (ev.key === 'Enter') _loadEntity(row.dataset.id); });
            });
            // Show result count in pagination bar (no prev/next for search)
            const pagEl = _el('adb-entity-pagination');
            if (pagEl) {
                pagEl.classList.remove('hidden');
                pagEl.innerHTML = `<div class="adb-pag-info">${results.length} result${results.length !== 1 ? 's' : ''}${results.length === 100 ? ' (limit reached)' : ''}</div>`;
            }
        } catch (err) {
            listEl.innerHTML = `<div class="adb-empty-state"><i class="fas fa-exclamation-triangle"></i><p>Error: ${err.message}</p></div>`;
        }
    }

    // ── Entity detail ─────────────────────────────────────────────────────────

    function _activateEntityTab(targetId) {
        document.querySelectorAll('.adb-ev-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.target === targetId);
        });
        document.querySelectorAll('.adb-ev-panel').forEach(panel => {
            panel.classList.toggle('hidden', panel.id !== targetId);
            panel.classList.toggle('active', panel.id === targetId);
        });
    }

    function _renderEntity(entity) {
        _currentEntityId     = entity.id;
        _currentEntityStatus = entity.status || 'active';
        _showEntityDetail();

        // Update Deepen button label to reflect context
        const deepenBtn = _el('adb-ev-expand-btn');
        if (deepenBtn) {
            if (_currentEntityStatus === 'stub') {
                deepenBtn.innerHTML = '<i class="fas fa-wand-sparkles"></i> Expand';
                deepenBtn.title = 'Expand this stub into a full entity';
            } else {
                deepenBtn.innerHTML = '<i class="fas fa-wand-sparkles"></i> Deepen';
                deepenBtn.title = 'Expand the sub-topics listed in this entity';
            }
        }

        // Type badge
        const typeBadge = _el('adb-ev-type-badge');
        if (typeBadge) {
            typeBadge.textContent = entity.type || 'other';
            typeBadge.className = `adb-type-badge adb-type-${entity.type || 'other'}`;
        }

        // Name + summary
        const nameEl = _el('adb-ev-name');
        if (nameEl) nameEl.textContent = entity.name || '—';
        const summaryEl = _el('adb-ev-summary');
        if (summaryEl) summaryEl.textContent = entity.sections?.core?.summary || '';

        // Status badge
        const statusEl = _el('adb-ev-status-badge');
        if (statusEl) {
            const isStub = entity.status === 'stub';
            statusEl.textContent = isStub ? 'stub' : 'expanded';
            statusEl.className = `adb-badge ${isStub ? 'adb-badge-stub' : 'adb-badge-expanded'}`;
        }

        // Meta
        const metaEl = _el('adb-ev-meta');
        if (metaEl) {
            metaEl.innerHTML = [
                `<span>ID: <code>${entity.id}</code></span>`,
                `<span>v${entity.version || 1}</span>`,
                entity.source ? `<span>Source: ${entity.source}</span>` : '',
                entity.updated ? `<span>Updated: ${_fmtDate(entity.updated)}</span>` : '',
            ].filter(Boolean).join('');
        }

        // Core tab
        const core = entity.sections?.core || {};
        const aliasEl = _el('adb-ev-aliases');
        if (aliasEl) {
            aliasEl.innerHTML = core.aliases?.length
                ? `<div class="adb-ev-section-label">Aliases</div>
                   <div class="adb-tag-row">${core.aliases.map(a => `<span class="adb-tag">${a}</span>`).join('')}</div>`
                : '';
        }
        const catEl = _el('adb-ev-categories');
        if (catEl) {
            catEl.innerHTML = core.categories?.length
                ? `<div class="adb-ev-section-label">Categories</div>
                   <div class="adb-tag-row">${core.categories.map(c => `<span class="adb-cat">${c}</span>`).join('')}</div>`
                : '';
        }
        const tagEl = _el('adb-ev-tags');
        if (tagEl) {
            tagEl.innerHTML = core.tags?.length
                ? `<div class="adb-ev-section-label">Tags</div>
                   <div class="adb-tag-row">${core.tags.map(t => `<span class="adb-tag adb-tag-accent">${t}</span>`).join('')}</div>`
                : '';
        }

        // Timeline tab
        const timeline = entity.sections?.timeline || [];
        const tlEl = _el('adb-ev-timeline-list');
        if (tlEl) {
            tlEl.innerHTML = timeline.length
                ? timeline.map(ev => `
                    <div class="adb-tl-item">
                        <div class="adb-tl-date">${ev.date || '?'}</div>
                        <div class="adb-tl-event">${ev.event || ''}</div>
                    </div>`).join('')
                : '<div class="adb-empty-hint">No timeline events</div>';
        }

        // Relations tab
        const relations = entity.sections?.relations || [];
        const relEl = _el('adb-ev-relations-list');
        if (relEl) {
            relEl.innerHTML = relations.length
                ? relations.map(rel => `
                    <div class="adb-rel-item" data-target="${rel.target_id || ''}" role="button" tabindex="0">
                        <span class="adb-rel-kind">${rel.kind || 'related_to'}</span>
                        <span class="adb-rel-target">${rel.target_id || '—'}</span>
                        ${rel.note ? `<span class="adb-rel-note">${rel.note}</span>` : ''}
                    </div>`).join('')
                : '<div class="adb-empty-hint">No relations</div>';

            relEl.querySelectorAll('.adb-rel-item[data-target]').forEach(item => {
                const tid = item.dataset.target;
                if (!tid) return;
                item.addEventListener('click', () => _loadEntity(tid));
                item.addEventListener('keydown', e => { if (e.key === 'Enter') _loadEntity(tid); });
                // Resolve name for the target ID
                fetch(`${API}/entities/${tid}?${_dbParam()}`)
                    .then(r => r.ok ? r.json() : null)
                    .then(ent => {
                        if (ent) {
                            const tEl = item.querySelector('.adb-rel-target');
                            if (tEl) tEl.textContent = ent.name;
                        }
                    }).catch(() => {});
            });
        }

        // Properties tab
        const props = entity.sections?.properties || {};
        const propEl = _el('adb-ev-props-table');
        if (propEl) {
            const entries = Object.entries(props);
            propEl.innerHTML = entries.length
                ? `<table class="adb-props-tbl"><tbody>
                   ${entries.map(([k, v]) => `<tr><td class="adb-prop-key">${k}</td><td class="adb-prop-val">${v}</td></tr>`).join('')}
                   </tbody></table>`
                : '<div class="adb-empty-hint">No properties</div>';
        }

        // Stubs tab
        const stubs = entity.sections?.stubs || [];
        const stubEl = _el('adb-ev-stubs-list');
        if (stubEl) {
            stubEl.innerHTML = stubs.length
                ? stubs.map(s => `<div class="adb-stub-item"><i class="fas fa-circle-half-stroke"></i> ${s}</div>`).join('')
                : '<div class="adb-empty-hint">No sub-topics listed</div>';
        }

        // JSON tab
        const rawEl = _el('adb-ev-raw-json');
        if (rawEl) rawEl.textContent = JSON.stringify(entity, null, 2);

        // Reset to Core tab
        _activateEntityTab('adb-tab-core');
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

    // ── Models ────────────────────────────────────────────────────────────────

    async function _fetchModels() {
        const sel = _el('adb-distill-model');
        if (!sel) return;
        try {
            const res  = await fetch('/api/registry/models/chat');
            if (!res.ok) return;
            const data = await res.json();
            const saved = localStorage.getItem('aethviondb_last_model') || 'auto';
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
            console.warn('[AethvionDB] Model fetch failed:', e);
        }
    }

    // ── Distillation ──────────────────────────────────────────────────────────

    async function _distill() {
        const content = _el('adb-distill-text')?.value?.trim();
        const model   = _el('adb-distill-model')?.value || null;
        if (!content) { _toast('Paste some content to distill.', 'error'); return; }
        if (model && model !== 'auto') localStorage.setItem('aethviondb_last_model', model);

        const statusEl = _el('adb-distill-status');
        const btn      = _el('adb-distill-btn');
        if (statusEl) {
            statusEl.textContent = 'Distilling…';
            statusEl.className = 'adb-status adb-status-loading';
            statusEl.classList.remove('hidden');
        }
        if (btn) btn.disabled = true;

        try {
            const res  = await fetch(`${API}/distill?${_dbParam()}`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({
                    content,
                    model: (model && model !== 'auto') ? model : undefined,
                }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail?.message || JSON.stringify(data.detail) || 'Distillation failed');

            if (statusEl) {
                statusEl.textContent = data.was_created
                    ? `✓ Created: ${data.entity_name} (${data.stub_count} stubs found)`
                    : `✓ Updated: ${data.entity_name}`;
                statusEl.className = 'adb-status adb-status-ok';
            }
            await _loadEntity(data.entity_id);
        } catch (e) {
            if (statusEl) {
                statusEl.textContent = `✗ ${e.message}`;
                statusEl.className = 'adb-status adb-status-error';
            }
            _toast(e.message, 'error');
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    // ── Expansion ─────────────────────────────────────────────────────────────

    async function _expandAll() {
        _showBusy('Expanding stubs…');
        try {
            const res  = await fetch(`${API}/expand?${_dbParam()}`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ max_entities: 10 }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Expansion failed');

            const expanded = data.expanded?.length || 0;
            const failed   = data.failed?.length   || 0;
            const newStubs = data.new_stubs?.length || 0;
            const skipped  = data.skipped?.length   || 0;

            if (expanded === 0 && failed === 0 && skipped === 0) {
                _toast('No stubs to expand', 'info');
            } else if (failed > 0 && expanded === 0) {
                _toast(`Expansion failed for ${failed} stub${failed !== 1 ? 's' : ''} — check console`, 'error');
                console.warn('[AethvionDB] Expansion failures:', data.failed);
            } else if (failed > 0) {
                _toast(`Expanded ${expanded}, ${failed} failed${newStubs ? `, ${newStubs} new stubs` : ''}`, 'error');
                console.warn('[AethvionDB] Expansion failures:', data.failed);
            } else {
                _toast(
                    `Expanded ${expanded} stub${expanded !== 1 ? 's' : ''}` +
                    (newStubs ? ` — ${newStubs} new sub-topics discovered` : '') + ' ✓',
                    'success'
                );
            }
            await _loadEntityList(_currentFilter, 0);
        } catch (e) {
            _toast(`Expansion failed: ${e.message}`, 'error');
        } finally { _hideBusy(); }
    }

    async function _deepenCurrent() {
        if (!_currentEntityId) return;

        if (_currentEntityStatus === 'stub') {
            // Stub entity: expand it into a full entity
            _showBusy('Expanding stub…');
            try {
                const res  = await fetch(`${API}/entities/${_currentEntityId}/expand?${_dbParam()}`, { method: 'POST' });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Expand failed');
                if (data.error && data.error !== 'already_active') {
                    _toast(`Expand failed: ${data.error}`, 'error');
                } else {
                    const newStubs = data.new_stubs?.length || 0;
                    _toast(
                        data.error === 'already_active'
                            ? 'Entity is already expanded'
                            : `Expanded ✓${newStubs ? ` — ${newStubs} new sub-topics found` : ''}`,
                        data.error === 'already_active' ? 'info' : 'success'
                    );
                }
                await _loadEntity(_currentEntityId);
                // Refresh list (background) so stub→active badge updates when user goes Back
                _loadEntityList(_currentFilter, _currentPage);
            } catch (e) {
                _toast(`Expand failed: ${e.message}`, 'error');
            } finally { _hideBusy(); }
        } else {
            // Active entity: expand the sub-topics (stubs) listed inside it
            _showBusy('Deepening sub-topics…');
            try {
                const res  = await fetch(`${API}/entities/${_currentEntityId}/deepen?${_dbParam({ max_stubs: 5 })}`, { method: 'POST' });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Deepen failed');
                const n = data.expanded?.length || 0;
                const f = data.failed?.length   || 0;
                if (n === 0 && f === 0) {
                    _toast('No sub-topics to deepen (add some stubs first)', 'info');
                } else if (f > 0) {
                    _toast(`Deepened ${n}, ${f} failed — check console`, 'error');
                    console.warn('[AethvionDB] Deepen failures:', data.failed);
                } else {
                    _toast(`Deepened ${n} sub-topic${n !== 1 ? 's' : ''} ✓`, 'success');
                }
                await _loadEntity(_currentEntityId);
            } catch (e) {
                _toast(`Deepen failed: ${e.message}`, 'error');
            } finally { _hideBusy(); }
        }
    }

    // ── Validation ────────────────────────────────────────────────────────────

    async function _validateAll() {
        _showBusy('Running integrity checks…');
        try {
            const res  = await fetch(`${API}/validate?${_dbParam()}`);
            const data = await res.json();
            _showValidation();

            const sumEl = _el('adb-val-summary');
            if (sumEl) {
                sumEl.innerHTML = `
                    <div class="adb-val-chips">
                        <span class="adb-val-chip adb-val-chip-ok">
                            <i class="fas fa-check-circle"></i> ${data.clean ?? 0} clean
                        </span>
                        <span class="adb-val-chip adb-val-chip-err">
                            <i class="fas fa-exclamation-circle"></i> ${data.with_errors ?? 0} with errors
                        </span>
                        <span class="adb-val-chip">
                            <i class="fas fa-triangle-exclamation"></i> ${data.total_warnings ?? 0} warnings
                        </span>
                    </div>`;
            }

            const issueEl = _el('adb-val-issues');
            if (issueEl) {
                const failed = data.failed_ids || [];
                if (!failed.length) {
                    issueEl.innerHTML = '<div class="adb-empty-hint"><i class="fas fa-check-circle"></i> All entities passed checks.</div>';
                } else {
                    issueEl.innerHTML = failed.map(id =>
                        `<div class="adb-val-item" data-id="${id}" role="button" tabindex="0">
                            <i class="fas fa-exclamation-triangle"></i> <code>${id}</code>
                        </div>`).join('');
                    issueEl.querySelectorAll('.adb-val-item[data-id]').forEach(item => {
                        item.addEventListener('click', () => _loadEntity(item.dataset.id));
                        item.addEventListener('keydown', e => { if (e.key === 'Enter') _loadEntity(item.dataset.id); });
                    });
                }
            }
        } catch (e) {
            _toast(`Validation failed: ${e.message}`, 'error');
        } finally { _hideBusy(); }
    }

    async function _validateCurrent() {
        if (!_currentEntityId) return;
        _showBusy('Validating entity…');
        try {
            const res    = await fetch(`${API}/validate/${_currentEntityId}?${_dbParam()}`);
            const data   = await res.json();
            const issues = data.issues || [];
            const errors = issues.filter(i => i.severity === 'error').length;
            const warns  = issues.filter(i => i.severity === 'warning').length;
            if (!errors && !warns) {
                _toast('Entity passed all integrity checks ✓', 'success');
            } else {
                _toast(`${errors} error(s), ${warns} warning(s)`, 'error');
                console.table(issues);
            }
        } catch (e) {
            _toast(`Validation failed: ${e.message}`, 'error');
        } finally { _hideBusy(); }
    }

    // ── Wiring ────────────────────────────────────────────────────────────────

    function _wire() {
        // Distill
        _el('adb-distill-btn')?.addEventListener('click', _distill);
        _el('adb-distill-text')?.addEventListener('keydown', e => { if (e.key === 'Enter' && e.ctrlKey) _distill(); });

        // Search
        _el('adb-search-btn')?.addEventListener('click', _search);
        _el('adb-search-input')?.addEventListener('keydown', e => { if (e.key === 'Enter') _search(); });

        // Header toolbar — manual stats refresh + list reload
        _el('adb-refresh-btn')?.addEventListener('click', () => {
            _refreshStats();
            _loadEntityList(_currentFilter, _currentPage);
        });
        _el('adb-expand-btn')?.addEventListener('click', _expandAll);
        _el('adb-validate-btn')?.addEventListener('click', _validateAll);

        // Filter buttons always reset to page 0
        document.querySelectorAll('.adb-filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                _setFilterActive(btn.dataset.filter);
                _loadEntityList(btn.dataset.filter, 0);
            });
        });

        // Entity detail — back button restores the page the user was on
        _el('adb-detail-back')?.addEventListener('click', () => _loadEntityList(_currentFilter, _currentPage));
        _el('adb-ev-expand-btn')?.addEventListener('click', _deepenCurrent);
        _el('adb-ev-validate-btn')?.addEventListener('click', _validateCurrent);
        document.querySelectorAll('.adb-ev-tab').forEach(btn => {
            btn.addEventListener('click', () => _activateEntityTab(btn.dataset.target));
        });

        // Validation view — back button restores the page the user was on
        _el('adb-val-close')?.addEventListener('click', () => _loadEntityList(_currentFilter, _currentPage));

        // DB modal
        _el('adb-db-change-btn')?.addEventListener('click', _openDbModal);
        _el('adb-db-modal-close')?.addEventListener('click', _closeDbModal);
        _el('adb-db-modal-cancel')?.addEventListener('click', _closeDbModal);
        _el('adb-db-browse-btn')?.addEventListener('click', _browseFolder);
        _el('adb-db-modal-open')?.addEventListener('click', _openSelectedDb);
        _el('adb-db-folder-input')?.addEventListener('keydown', e => { if (e.key === 'Enter') _openSelectedDb(); });
        _el('adb-db-modal')?.addEventListener('click', e => {
            if (e.target === _el('adb-db-modal')) _closeDbModal();
        });
    }

    // ── Init ──────────────────────────────────────────────────────────────────

    function init() {
        const root = _el('aethviondb-root');
        if (!root || root.dataset.adbInit) return;
        root.dataset.adbInit = '1';

        // Restore last-used database from localStorage
        try {
            const saved = localStorage.getItem('aethviondb_last_db');
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
        _loadEntityList('all', 0);
    }

    document.addEventListener('panelLoaded', function (e) {
        if (e.detail?.tabName === 'aethviondb') init();
    });
})();
