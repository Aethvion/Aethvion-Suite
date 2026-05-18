'use strict';
/**
 * Aethvion Suite — AethvionDB
 * mode-aethviondb.js
 *
 * Entity list is the primary view — auto-loaded on init.
 * Backend: /api/aethviondb/
 * All DOM IDs use the adb- prefix to match partials/aethviondb.html.
 */

(function () {
    const API        = '/api/aethviondb';
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
    let _currentTab          = 'explorer'; // 'explorer' | 'graph'
    let _selectedIds         = new Set(); // entity IDs checked in the list view
    let _sortCol             = null;      // null | 'type'|'name'|'tags'|'rel'|'sub'|'status'
    let _sortDir             = 'asc';    // 'asc' | 'desc'

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

    /** Return the currently selected model (null means "auto" / server decides). */
    function _selectedModel() {
        const v = _el('adb-distill-model')?.value;
        return (v && v !== 'auto') ? v : null;
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
        _show('adb-explorer-header');
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
        _hide('adb-explorer-header');
        _hide('adb-list-pane');
        _hide('adb-entity-detail');
        _show('adb-validation-view');
    }

    function _switchTab(tab) {
        _currentTab = tab;
        document.querySelectorAll('.adb-nav-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tab);
        });
        _el('adb-tab-pane-tools')   ?.classList.toggle('hidden', tab !== 'tools');
        _el('adb-tab-pane-bake')    ?.classList.toggle('hidden', tab !== 'bake');
        _el('adb-tab-pane-explorer')?.classList.toggle('hidden', tab !== 'explorer');
        _el('adb-tab-pane-graph')   ?.classList.toggle('hidden', tab !== 'graph');
        _el('adb-tab-pane-api')     ?.classList.toggle('hidden', tab !== 'api');
        if (tab === 'bake') _bakeLoadList();
        if (tab === 'api')  { _apiRenderTree(); _apiLoadKeys(); }
        if (tab === 'graph') {
            _openGraph();
        } else {
            if (_graphSim) _graphSim.stop();
        }
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
        if (_graphSim) { _graphSim.stop(); _graphSim = null; }
        _switchTab('explorer');
        _fdStopPolling();
        _fdSection('adb-fd-pick');
        _bakeStopPolling();
        _vecStopPolling();
        _bakeVecModelsLoaded = false;
        _bakeToggleVecFoldout(false);
        _loadCachedInfo();
        _fdCheckExistingJob();
        _bakeCheckExisting();
        _vecCheckExisting();
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
        if (_graphSim) { _graphSim.stop(); _graphSim = null; }
        _switchTab('explorer');
        _fdStopPolling();
        _fdSection('adb-fd-pick');
        _bakeStopPolling();
        _vecStopPolling();
        _bakeVecModelsLoaded = false;
        _bakeToggleVecFoldout(false);
        _loadCachedInfo();
        _fdCheckExistingJob();
        _bakeCheckExisting();
        _vecCheckExisting();
        _loadEntityList('all', 0);
        const name = folderPath.replace(/\\/g, '/').split('/').filter(Boolean).pop() || folderPath;
        _toast(`Database: ${name}`, 'info');
    }

    /** Reset stat values to "—" and show the "click to load" hint. */
    function _resetStatsDisplay() {
        ['adb-stat-total', 'adb-stat-stubs', 'adb-stat-index', 'adb-stat-size'].forEach(id => {
            const el = _el(id); if (el) el.textContent = '—';
        });
        const ht = _el('adb-stats-hint-text');
        if (ht) ht.textContent = 'Click ↻ to load stats';
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
            _updateExpandCounts(data.stubs_by_min_relations);
        } catch (e) {
            console.error('[AethvionDB] Stats failed:', e);
            _toast('Failed to load stats', 'error');
        } finally {
            if (refreshBtn) { refreshBtn.disabled = false; refreshBtn.classList.remove('adb-btn-spinning'); }
        }
    }

    /**
     * Read AethvionDB.INFO from the server (instant — no scanning).
     * Populates the stats bar with cached values so numbers are visible
     * immediately on page load / tab switch, before the user clicks ↻.
     */
    async function _loadCachedInfo() {
        try {
            const res  = await fetch(`${API}/info?${_dbParam()}`);
            const data = await res.json();
            if (!data.cached) return;  // no INFO file yet for this db

            const te = _el('adb-stat-total'); if (te) te.textContent = _fmtNum(data.total_entities);
            const st = _el('adb-stat-stubs'); if (st) st.textContent = _fmtNum(data.stub_count);
            const si = _el('adb-stat-index'); if (si) si.textContent = _fmtNum(data.index_size);
            const sz = _el('adb-stat-size');  if (sz) sz.textContent = _fmtBytes(data.total_size_bytes);

            // Update hint: show when data was last refreshed instead of prompting
            const ht = _el('adb-stats-hint-text');
            if (ht && data.last_updated) {
                const d   = new Date(data.last_updated);
                const fmt = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
                ht.textContent = `Cached · ${fmt}`;
            }
            _show('adb-stats-hint');  // keep visible as a "this is cached" indicator

            // Populate smart-expand dropdown counts
            _updateExpandCounts(data.stubs_by_min_relations);
        } catch { /* cached info is optional — silently ignore network/parse errors */ }
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

            const sorted = _sortEntities(entities);
            listEl.innerHTML = _renderTable(sorted);
            _wireTableCheckboxes(sorted);
            _wireTableSort(entities, listEl);
            _wireTableRows(listEl);

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
        const checked   = _selectedIds.has(e.id);

        const tagHtml = tags.slice(0, 3).map(t => `<span class="adb-tag-sm">${t}</span>`).join('')
                      + (tags.length > 3 ? `<span class="adb-tag-sm">+${tags.length - 3}</span>` : '');

        return `<tr class="adb-tr${checked ? ' adb-tr-selected' : ''}" data-id="${e.id}" data-stub="${isStub}" tabindex="0">
            <td class="adb-td adb-td-check">
                <input type="checkbox" class="adb-row-check" data-id="${e.id}" ${checked ? 'checked' : ''} aria-label="Select ${(e.name || e.id).replace(/"/g, '')}">
            </td>
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

    /** Return a sorted copy of entities based on current _sortCol / _sortDir. */
    function _sortEntities(entities) {
        if (!_sortCol) return entities;
        const dir = _sortDir === 'asc' ? 1 : -1;
        return [...entities].sort((a, b) => {
            switch (_sortCol) {
                case 'type': {
                    const av = (a.type || 'other').toLowerCase();
                    const bv = (b.type || 'other').toLowerCase();
                    return dir * av.localeCompare(bv);
                }
                case 'name': {
                    const av = (a.name || a.id || '').toLowerCase();
                    const bv = (b.name || b.id || '').toLowerCase();
                    return dir * av.localeCompare(bv);
                }
                case 'tags': {
                    const at = a.tags || a.sections?.core?.tags || [];
                    const bt = b.tags || b.sections?.core?.tags || [];
                    if (at.length !== bt.length) return dir * (at.length - bt.length);
                    return dir * (at[0] || '').toLowerCase().localeCompare((bt[0] || '').toLowerCase());
                }
                case 'rel': {
                    const av = a.relations_count ?? a.sections?.relations?.length ?? -1;
                    const bv = b.relations_count ?? b.sections?.relations?.length ?? -1;
                    return dir * (av - bv);
                }
                case 'sub': {
                    const av = a.stubs_count ?? a.sections?.stubs?.length ?? -1;
                    const bv = b.stubs_count ?? b.sections?.stubs?.length ?? -1;
                    return dir * (av - bv);
                }
                case 'status': {
                    const av = a.status === 'stub' ? 0 : 1;
                    const bv = b.status === 'stub' ? 0 : 1;
                    return dir * (av - bv);
                }
                default: return 0;
            }
        });
    }

    /** Wire sort-click events on `.adb-th-sort` headers.
     *  originalEntities = raw server response (never re-sorted in place).
     *  listEl           = the container whose innerHTML we replace on sort change. */
    function _wireTableSort(originalEntities, listEl) {
        listEl.querySelectorAll('.adb-th-sort[data-sort]').forEach(th => {
            th.addEventListener('click', () => {
                const col = th.dataset.sort;
                if (_sortCol === col) {
                    _sortDir = _sortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    _sortCol = col;
                    _sortDir = 'asc';
                }
                const sorted = _sortEntities(originalEntities);
                listEl.innerHTML = _renderTable(sorted);
                _wireTableCheckboxes(sorted);
                _wireTableSort(originalEntities, listEl); // keep original ref
                _wireTableRows(listEl);
            });
        });
    }

    /** Wire row click / keyboard navigation after every table render. */
    function _wireTableRows(listEl) {
        listEl.querySelectorAll('.adb-tr').forEach(row => {
            row.addEventListener('click', e => {
                if (e.target.closest('.adb-td-check')) return;
                _loadEntity(row.dataset.id);
            });
            row.addEventListener('keydown', ev => {
                if (ev.key === 'Enter') { _loadEntity(row.dataset.id); return; }
                if (ev.key === ' ') {
                    ev.preventDefault();
                    const chk = row.querySelector('.adb-row-check');
                    if (chk) { chk.checked = !chk.checked; chk.dispatchEvent(new Event('change')); }
                }
            });
        });
    }

    function _renderTable(entities) {
        const _si = col => {
            if (_sortCol !== col) return `<span class="adb-sort-icon adb-sort-inactive"><i class="fas fa-sort"></i></span>`;
            const icon = _sortDir === 'asc' ? 'fa-sort-up' : 'fa-sort-down';
            return `<span class="adb-sort-icon"><i class="fas ${icon}"></i></span>`;
        };
        const _thCls = col => `adb-th-sort${_sortCol === col ? ' adb-sort-active' : ''}`;
        return `<table class="adb-table">
            <colgroup>
                <col class="adb-col-check">
                <col class="adb-col-type">
                <col>
                <col class="adb-col-tags">
                <col class="adb-col-rel">
                <col class="adb-col-stubs">
                <col class="adb-col-status">
            </colgroup>
            <thead>
                <tr>
                    <th class="adb-col-check adb-th-check">
                        <input type="checkbox" id="adb-select-all" class="adb-row-check" title="Select all on this page">
                    </th>
                    <th class="adb-col-type ${_thCls('type')}" data-sort="type">Type${_si('type')}</th>
                    <th class="${_thCls('name')}" data-sort="name">Name / Summary${_si('name')}</th>
                    <th class="adb-col-tags ${_thCls('tags')}" data-sort="tags">Tags${_si('tags')}</th>
                    <th class="adb-col-rel ${_thCls('rel')}" data-sort="rel" title="Number of relations">Rel.${_si('rel')}</th>
                    <th class="adb-col-stubs ${_thCls('sub')}" data-sort="sub" title="Number of sub-topics">Sub.${_si('sub')}</th>
                    <th class="adb-col-status ${_thCls('status')}" data-sort="status">Status${_si('status')}</th>
                </tr>
            </thead>
            <tbody>
                ${entities.map(e => _entityRowHtml(e)).join('')}
            </tbody>
        </table>`;
    }

    // ── Selection & bulk actions ──────────────────────────────────────────────

    function _updateBulkBar() {
        const bar     = _el('adb-bulk-bar');
        const countEl = _el('adb-bulk-count');
        if (!bar || !countEl) return;
        const n = _selectedIds.size;
        if (n === 0) {
            bar.classList.add('hidden');
        } else {
            bar.classList.remove('hidden');
            countEl.textContent = `${n} selected`;
        }
    }

    function _clearSelection() {
        _selectedIds.clear();
        document.querySelectorAll('.adb-row-check').forEach(c => { c.checked = false; });
        document.querySelectorAll('.adb-tr').forEach(r => r.classList.remove('adb-tr-selected'));
        const sa = _el('adb-select-all');
        if (sa) { sa.checked = false; sa.indeterminate = false; }
        _updateBulkBar();
    }

    function _wireTableCheckboxes(entities) {
        const selectAll = _el('adb-select-all');

        // Set initial select-all state
        if (selectAll) {
            const allSel = entities.length > 0 && entities.every(e => _selectedIds.has(e.id));
            const anySel = entities.some(e => _selectedIds.has(e.id));
            selectAll.checked       = allSel;
            selectAll.indeterminate = !allSel && anySel;

            selectAll.addEventListener('change', () => {
                if (selectAll.checked) {
                    entities.forEach(e => _selectedIds.add(e.id));
                } else {
                    entities.forEach(e => _selectedIds.delete(e.id));
                }
                document.querySelectorAll('.adb-row-check:not(#adb-select-all)').forEach(c => {
                    c.checked = _selectedIds.has(c.dataset.id);
                    c.closest('.adb-tr')?.classList.toggle('adb-tr-selected', c.checked);
                });
                _updateBulkBar();
            });
        }

        // Wire individual row checkboxes
        document.querySelectorAll('.adb-row-check:not(#adb-select-all)').forEach(chk => {
            chk.addEventListener('change', () => {
                const id = chk.dataset.id;
                if (chk.checked) _selectedIds.add(id);
                else             _selectedIds.delete(id);
                chk.closest('.adb-tr')?.classList.toggle('adb-tr-selected', chk.checked);

                // Sync select-all state
                if (selectAll) {
                    const allNow = entities.every(e => _selectedIds.has(e.id));
                    const anyNow = entities.some(e => _selectedIds.has(e.id));
                    selectAll.checked       = allNow;
                    selectAll.indeterminate = !allNow && anyNow;
                }
                _updateBulkBar();
            });
        });
    }

    // ── Bulk progress helpers ─────────────────────────────────────────────────

    function _bulkProgShow(label, total) {
        const prog = _el('adb-bulk-prog');
        const fill = _el('adb-bulk-prog-fill');
        if (prog) prog.classList.remove('hidden');
        if (fill) fill.style.width = '0%';
        const countEl = _el('adb-bulk-count');
        if (countEl) countEl.textContent = `${label} 0 / ${total}`;
        // Lock controls during processing
        ['adb-bulk-expand', 'adb-bulk-delete', 'adb-bulk-clear'].forEach(id => {
            _el(id)?.setAttribute('disabled', '');
        });
    }

    function _bulkProgUpdate(done, total, label) {
        const fill    = _el('adb-bulk-prog-fill');
        const countEl = _el('adb-bulk-count');
        if (fill)    fill.style.width = `${Math.round((done / total) * 100)}%`;
        if (countEl) countEl.textContent = `${label} ${done} / ${total}`;
    }

    function _bulkProgDone() {
        const fill = _el('adb-bulk-prog-fill');
        if (fill) fill.style.width = '100%';
        // Re-enable controls
        ['adb-bulk-expand', 'adb-bulk-delete', 'adb-bulk-clear'].forEach(id => {
            _el(id)?.removeAttribute('disabled');
        });
        // Fade out the strip after a short hold
        setTimeout(() => _el('adb-bulk-prog')?.classList.add('hidden'), 900);
    }

    /** Update a row's visual state while a bulk operation is running. */
    function _markRowState(id, state) {
        const row   = document.querySelector(`.adb-tr[data-id="${id}"]`);
        if (!row) return;
        row.classList.remove('adb-tr-processing', 'adb-tr-op-done', 'adb-tr-op-fail', 'adb-tr-op-skip', 'adb-tr-op-del');
        const badge = row.querySelector('.adb-badge'); // status badge (not type badge)
        if (!badge) return;
        switch (state) {
            case 'processing':
                row.classList.add('adb-tr-processing');
                badge.className = 'adb-badge adb-badge-working';
                badge.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i>';
                break;
            case 'done':
                row.classList.add('adb-tr-op-done');
                badge.className = 'adb-badge adb-badge-op-ok';
                badge.innerHTML = '<i class="fas fa-check"></i> done';
                break;
            case 'skipped':
                row.classList.add('adb-tr-op-skip');
                // Leave badge as-is — entity was already active
                break;
            case 'failed':
                row.classList.add('adb-tr-op-fail');
                badge.className = 'adb-badge adb-badge-op-err';
                badge.innerHTML = '<i class="fas fa-times"></i> failed';
                break;
            case 'deleted':
                row.classList.add('adb-tr-op-del');
                badge.className = 'adb-badge adb-badge-op-err';
                badge.innerHTML = '<i class="fas fa-trash"></i>';
                break;
        }
    }

    // ── Bulk operations ───────────────────────────────────────────────────────

    async function _bulkExpandStubs() {
        const ids = [..._selectedIds];
        if (!ids.length) return;
        const n = ids.length;

        _bulkProgShow('Expanding', n);
        const model = _selectedModel();
        let expanded = 0, failed = 0, skipped = 0, done = 0;

        for (const id of ids) {
            _markRowState(id, 'processing');
            try {
                const res  = await fetch(`${API}/entities/${id}/expand?${_dbParam(model ? { model } : {})}`, { method: 'POST' });
                const data = await res.json();
                if (!res.ok) {
                    failed++;
                    _markRowState(id, 'failed');
                } else if (data.error === 'already_active') {
                    skipped++;
                    _markRowState(id, 'skipped');
                } else {
                    expanded++;
                    _markRowState(id, 'done');
                }
            } catch {
                failed++;
                _markRowState(id, 'failed');
            }
            done++;
            _bulkProgUpdate(done, n, 'Expanding');
        }

        _bulkProgDone();
        const parts = [];
        if (expanded) parts.push(`${expanded} expanded`);
        if (skipped)  parts.push(`${skipped} already active`);
        if (failed)   parts.push(`${failed} failed`);
        _toast(parts.join(' · ') || 'Done', failed ? 'error' : 'success');

        _selectedIds.clear();
        // Let the user see the row states for a moment before refreshing
        setTimeout(() => {
            _updateBulkBar();
            _loadEntityList(_currentFilter, _currentPage);
        }, 1100);
    }

    async function _bulkDelete() {
        const ids = [..._selectedIds];
        if (!ids.length) return;
        const n = ids.length;

        _bulkProgShow('Deleting', n);
        let deleted = 0, failed = 0, done = 0;

        for (const id of ids) {
            _markRowState(id, 'processing');
            try {
                const res = await fetch(`${API}/entities/${id}?${_dbParam()}`, { method: 'DELETE' });
                if (!res.ok) {
                    failed++;
                    _markRowState(id, 'failed');
                } else {
                    deleted++;
                    _markRowState(id, 'deleted');
                }
            } catch {
                failed++;
                _markRowState(id, 'failed');
            }
            done++;
            _bulkProgUpdate(done, n, 'Deleting');
        }

        _bulkProgDone();
        _toast(
            `Deleted ${deleted}${failed ? ` · ${failed} failed` : ''}`,
            failed ? 'error' : 'success'
        );
        _selectedIds.clear();
        setTimeout(() => {
            _updateBulkBar();
            _loadEntityList(_currentFilter, _currentPage);
        }, 800);
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

            const sorted = _sortEntities(results);
            listEl.innerHTML = _renderTable(sorted);
            _wireTableCheckboxes(sorted);
            _wireTableSort(results, listEl);
            _wireTableRows(listEl);
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

        // Vectors tab
        const vecListEl = _el('adb-ev-vectors-list');
        if (vecListEl) {
            const vectors = entity.sections?.vectors || {};
            const entries = Object.entries(vectors);
            if (!entries.length) {
                vecListEl.innerHTML = '<div class="adb-empty-hint">No embeddings generated yet. Use the Vector Search panel in the Tools tab.</div>';
            } else {
                vecListEl.innerHTML = entries.map(([modelKey, vec]) => {
                    const _OPENAI_MODELS = ['text-embedding-3-small','text-embedding-3-large','text-embedding-ada-002'];
                    const provider  = _OPENAI_MODELS.includes(modelKey) ? 'openai' : 'google';
                    const provLabel = provider === 'openai' ? 'OpenAI' : 'Google';
                    const provCls   = `adb-vec-provider-${provider}`;
                    const dims      = vec.dimensions || (vec.embedding?.length ?? '?');
                    const genDate   = vec.generated_at ? _fmtDate(vec.generated_at) : '—';
                    const inputPrev = vec.input ? `"${vec.input.slice(0, 160)}${vec.input.length > 160 ? '…' : ''}"` : '—';
                    const embPrev   = vec.embedding?.length
                        ? `[${vec.embedding.slice(0, 6).map(v => v.toFixed(4)).join(', ')}${vec.embedding.length > 6 ? `, … +${vec.embedding.length - 6} more` : ''}]`
                        : '—';
                    return `
                    <div class="adb-vec-card">
                        <div class="adb-vec-card-header">
                            <span class="adb-vec-model-name">${modelKey}</span>
                            <span class="adb-vec-provider-badge ${provCls}">${provLabel}</span>
                            <span class="adb-vec-dims">${dims} dims</span>
                            <span class="adb-vec-date">${genDate}</span>
                        </div>
                        <div class="adb-vec-row">
                            <span class="adb-vec-row-label">Input</span>
                            <span class="adb-vec-input-preview">${inputPrev}</span>
                        </div>
                        <div class="adb-vec-row">
                            <span class="adb-vec-row-label">Vector</span>
                            <code class="adb-vec-embedding-preview">${embPrev}</code>
                        </div>
                    </div>`;
                }).join('');
            }
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

    // ── Smart expand dropdown ─────────────────────────────────────────────────

    let _expandDdOpen = false;

    function _updateExpandCounts(counts) {
        if (!counts) return;
        const c1 = _el('adb-expand-count-1'); if (c1) c1.textContent = _fmtNum(counts['1'] ?? null);
        const c2 = _el('adb-expand-count-2'); if (c2) c2.textContent = _fmtNum(counts['2'] ?? null);
        const c3 = _el('adb-expand-count-3'); if (c3) c3.textContent = _fmtNum(counts['3'] ?? null);
    }

    function _openExpandDropdown() {
        _expandDdOpen = true;
        _el('adb-expand-dropdown')?.classList.remove('hidden');
        _el('adb-expand-wrap')?.classList.add('open');
    }

    function _closeExpandDropdown() {
        _expandDdOpen = false;
        _el('adb-expand-dropdown')?.classList.add('hidden');
        _el('adb-expand-wrap')?.classList.remove('open');
    }

    function _toggleExpandDropdown(e) {
        e.stopPropagation();
        _expandDdOpen ? _closeExpandDropdown() : _openExpandDropdown();
    }

    async function _smartExpand(minRelations) {
        _closeExpandDropdown();
        _showBusy(`Expanding stubs with ${minRelations}+ relations…`);
        try {
            const model = _selectedModel();
            const res  = await fetch(
                `${API}/expand/smart?${_dbParam({ min_relations: minRelations, max_entities: 20, ...(model ? { model } : {}) })}`,
                { method: 'POST' }
            );
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Expansion failed');

            if (data.message && !data.expanded?.length) {
                _toast(data.message, 'info');
            } else {
                const expanded = data.expanded?.length || 0;
                const failed   = data.failed?.length   || 0;
                const newStubs = data.new_stubs?.length || 0;
                if (failed > 0 && expanded === 0) {
                    _toast(`Expansion failed for ${failed} stub${failed !== 1 ? 's' : ''}`, 'error');
                } else if (failed > 0) {
                    _toast(`Expanded ${expanded}, ${failed} failed${newStubs ? `, ${newStubs} new stubs` : ''}`, 'error');
                } else {
                    _toast(
                        `Expanded ${expanded} stub${expanded !== 1 ? 's' : ''}` +
                        (newStubs ? ` — ${newStubs} new sub-topics` : '') + ' ✓',
                        'success'
                    );
                }
            }
            await _loadEntityList(_currentFilter, 0);
        } catch (e) {
            _toast(`Expansion failed: ${e.message}`, 'error');
        } finally { _hideBusy(); }
    }

    async function _expandAll() {
        _showBusy('Expanding stubs…');
        try {
            const model = _selectedModel();
            const res  = await fetch(`${API}/expand?${_dbParam()}`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ max_entities: 10, ...(model ? { model } : {}) }),
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
                const model = _selectedModel();
                const res  = await fetch(`${API}/entities/${_currentEntityId}/expand?${_dbParam(model ? { model } : {})}`, { method: 'POST' });
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
                const model = _selectedModel();
                const res  = await fetch(`${API}/entities/${_currentEntityId}/deepen?${_dbParam({ max_stubs: 5, ...(model ? { model } : {}) })}`, { method: 'POST' });
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

            const mismatches = data.stub_mismatches || [];
            const failed     = data.failed_ids      || [];

            // ── Summary chips ────────────────────────────────────────────────
            const sumEl = _el('adb-val-summary');
            if (sumEl) {
                const mmChip = mismatches.length
                    ? `<span class="adb-val-chip adb-val-chip-warn">
                           <i class="fas fa-tag"></i> ${mismatches.length} status mismatch${mismatches.length !== 1 ? 'es' : ''}
                       </span>`
                    : '';
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
                        ${mmChip}
                    </div>`;
            }

            // ── Issues pane ──────────────────────────────────────────────────
            const issueEl = _el('adb-val-issues');
            if (!issueEl) return;

            if (!mismatches.length && !failed.length) {
                issueEl.innerHTML = '<div class="adb-empty-hint"><i class="fas fa-check-circle"></i> All entities passed checks.</div>';
                return;
            }

            let html = '';

            // Status-mismatch group with Fix All button
            if (mismatches.length) {
                html += `
                <div class="adb-val-mm-group">
                    <div class="adb-val-mm-header">
                        <div class="adb-val-mm-title">
                            <i class="fas fa-tag"></i>
                            Status Mismatches
                            <span class="adb-val-mm-badge">${mismatches.length}</span>
                        </div>
                        <button id="adb-val-fix-btn" class="adb-btn adb-btn-accent adb-btn-sm">
                            <i class="fas fa-wand-sparkles"></i> Fix All
                        </button>
                    </div>
                    <p class="adb-val-mm-desc">
                        These entities have a summary but are still marked as <code>stub</code>.
                        Their status should be <code>active</code>.
                    </p>
                    <div class="adb-val-mm-list">
                        ${mismatches.map(m => `
                            <div class="adb-val-mm-item" data-id="${m.id}" role="button" tabindex="0">
                                <i class="fas fa-circle-dot adb-val-mm-dot"></i>
                                <span class="adb-val-mm-name">${m.name}</span>
                                <code class="adb-val-mm-id">${m.id}</code>
                            </div>`).join('')}
                    </div>
                </div>`;
            }

            // Regular integrity issues
            if (failed.length) {
                if (mismatches.length) html += '<div class="adb-val-section-sep"></div>';
                html += `<div class="adb-val-section-label">Integrity Issues</div>`;
                html += failed.map(id =>
                    `<div class="adb-val-item" data-id="${id}" role="button" tabindex="0">
                        <i class="fas fa-exclamation-triangle"></i> <code>${id}</code>
                    </div>`).join('');
            }

            issueEl.innerHTML = html;

            // Wire mismatch item clicks → open entity
            issueEl.querySelectorAll('.adb-val-mm-item[data-id]').forEach(item => {
                item.addEventListener('click', () => _loadEntity(item.dataset.id));
                item.addEventListener('keydown', e => { if (e.key === 'Enter') _loadEntity(item.dataset.id); });
            });

            // Wire regular issue clicks → open entity
            issueEl.querySelectorAll('.adb-val-item[data-id]').forEach(item => {
                item.addEventListener('click', () => _loadEntity(item.dataset.id));
                item.addEventListener('keydown', e => { if (e.key === 'Enter') _loadEntity(item.dataset.id); });
            });

            // Fix All button — promotes all mismatched entities, then re-runs validation
            _el('adb-val-fix-btn')?.addEventListener('click', async () => {
                const btn = _el('adb-val-fix-btn');
                if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Fixing…'; }
                try {
                    const fixRes  = await fetch(`${API}/validate/fix-status-mismatches?${_dbParam()}`, { method: 'POST' });
                    const fixData = await fixRes.json();
                    const n = fixData.fixed ?? 0;
                    _toast(`Promoted ${n} ${n === 1 ? 'entity' : 'entities'} to active`, 'success');
                    await _validateAll(); // refresh the view
                } catch {
                    _toast('Fix failed', 'error');
                    if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-wand-sparkles"></i> Fix All'; }
                }
            });

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

    // ── Graph view ────────────────────────────────────────────────────────────

    /** Entity-type → fill colour (matches badge palette). */
    const _GRAPH_COLORS = {
        person:       '#f472b6',
        place:        '#4ade80',
        event:        '#fbbf24',
        concept:      '#818cf8',
        organization: '#22d3ee',
        artifact:     '#c084fc',
        creature:     '#f87171',
        work:         '#2dd4bf',
        species:      '#a3e635',
        substance:    '#facc15',
        phenomenon:   '#fb923c',
        process:      '#60a5fa',
        universe:     '#e879f9',
        other:        '#9ca3af',
    };

    /** Relation kind → edge stroke colour. */
    const _EDGE_COLORS = {
        parent_of:       '#f59e0b',
        child_of:        '#f59e0b',
        contains:        '#60a5fa',
        part_of:         '#60a5fa',
        has_part:        '#60a5fa',
        created:         '#c084fc',
        created_by:      '#c084fc',
        influenced:      '#2dd4bf',
        influenced_by:   '#2dd4bf',
        located_in:      '#4ade80',
        location_of:     '#4ade80',
        member_of:       '#fb923c',
        participated_in: '#fb923c',
        instance_of:     '#818cf8',
        has_instance:    '#818cf8',
    };

    // Graph state
    let _graphSim      = null;   // d3 force simulation
    let _graphFocusId  = null;   // entity ID of the focused node (null = full graph)
    let _graphNodeSel  = null;   // d3 node circle selection
    let _graphLinkSel  = null;   // d3 edge line selection
    let _graphLabelSel = null;   // d3 label text selection
    let _graphLinkData = null;   // raw link array (after d3 resolves source/target)

    function _gNodeColor(type)  { return _GRAPH_COLORS[type] || '#9ca3af'; }
    function _gNodeRadius(d)    { return Math.max(5, Math.min(22, 5 + (d.rel_count || 0) * 1.8)); }
    function _gEdgeColor(kind)  { return _EDGE_COLORS[kind]  || 'rgba(100,116,139,0.4)'; }

    // ── D3 lazy loader ────────────────────────────────────────────────────────

    async function _graphLoadD3() {
        if (window.d3) return;
        return new Promise((resolve, reject) => {
            const s    = document.createElement('script');
            s.src      = 'https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js';
            s.onload   = resolve;
            s.onerror  = () => reject(new Error('Failed to load D3 from CDN. Check your internet connection.'));
            document.head.appendChild(s);
        });
    }

    // ── View helpers ──────────────────────────────────────────────────────────

    async function _openGraph() {
        _show('adb-graph-loading');
        _hide('adb-graph-card');
        try {
            await _graphLoadD3();
            await _graphLoad();
        } catch(e) {
            _toast(`Graph load failed: ${e.message}`, 'error');
        }
    }

    function _closeGraph() {
        if (_graphSim) { _graphSim.stop(); _graphSim = null; }
        _switchTab('explorer');
        _showEntityList();
    }

    // ── Data loading ──────────────────────────────────────────────────────────

    async function _graphLoad(entityId = null) {
        _graphFocusId = entityId;
        _show('adb-graph-loading');
        _hide('adb-graph-card');

        const depth  = _el('adb-graph-depth')?.value || '2';
        const params = new URLSearchParams(_dbParam({ limit: 500 }));
        if (entityId) { params.set('entity_id', entityId); params.set('depth', depth); }

        try {
            const res  = await fetch(`${API}/graph?${params}`);
            const data = await res.json();

            const infoEl = _el('adb-graph-info');
            if (infoEl) {
                infoEl.textContent =
                    `${_fmtNum(data.node_count)} nodes · ${_fmtNum(data.edge_count)} edges` +
                    (data.truncated ? ' (truncated — use Focus for large databases)' : '');
            }

            if (data.node_count === 0) {
                _toast('No entities to show. Distil some content first.', 'info');
                _closeGraph();
                return;
            }

            _graphRender(data);
        } catch (e) {
            _toast(`Graph load failed: ${e.message}`, 'error');
        } finally {
            _hide('adb-graph-loading');
        }
    }

    // ── Render (D3 force graph) ───────────────────────────────────────────────

    function _graphRender(data) {
        if (_graphSim) { _graphSim.stop(); _graphSim = null; }

        const svgEl = _el('adb-graph-svg');
        if (!svgEl || !window.d3) return;

        const d3     = window.d3;
        const svg    = d3.select(svgEl);
        const width  = svgEl.clientWidth  || 900;
        const height = svgEl.clientHeight || 600;

        svg.selectAll('*').remove();

        // ── Defs: arrowhead marker ──
        svg.append('defs').append('marker')
            .attr('id', 'adb-graph-arrow')
            .attr('viewBox', '0 -4 8 8')
            .attr('refX', 14).attr('refY', 0)
            .attr('markerWidth', 5).attr('markerHeight', 5)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-4L8,0L0,4')
            .attr('fill', 'rgba(100,116,139,0.45)');

        // ── Zoom / pan ──
        const g    = svg.append('g');
        const zoom = d3.zoom()
            .scaleExtent([0.04, 8])
            .on('zoom', evt => g.attr('transform', evt.transform));
        svg.call(zoom)
            .on('dblclick.zoom', null);  // disable double-click zoom (we use it to open entity)

        // ── Node and link data (cloned so D3 can mutate source/target) ──
        const nodes = data.nodes.map(d => ({ ...d }));
        const links = data.edges.map(d => ({ ...d }));
        _graphLinkData = links;

        // ── Edges ──
        const linkG   = g.append('g').attr('class', 'adb-graph-link-g');
        const linkEl  = linkG.selectAll('line')
            .data(links)
            .join('line')
            .attr('stroke',         d => _gEdgeColor(d.kind))
            .attr('stroke-width',   1.5)
            .attr('stroke-opacity', 0.55)
            .attr('marker-end',     'url(#adb-graph-arrow)');
        _graphLinkSel = linkEl;

        // ── Nodes ──
        const nodeG  = g.append('g').attr('class', 'adb-graph-node-g');
        const nodeEl = nodeG.selectAll('circle')
            .data(nodes)
            .join('circle')
            .attr('r',            _gNodeRadius)
            .attr('fill',         d => _gNodeColor(d.type))
            .attr('fill-opacity', d => d.status === 'stub' ? 0.35 : 0.82)
            .attr('stroke',       d => _gNodeColor(d.type))
            .attr('stroke-width', d => d.id === data.focused_id ? 3 : 1.5)
            .attr('stroke-opacity', d => d.status === 'stub' ? 0.5 : 0.7)
            .attr('cursor', 'pointer')
            // Drag
            .call(d3.drag()
                .on('start', (evt, d) => {
                    if (!evt.active) _graphSim.alphaTarget(0.3).restart();
                    d.fx = d.x; d.fy = d.y;
                })
                .on('drag', (evt, d) => { d.fx = evt.x; d.fy = evt.y; })
                .on('end',  (evt, d) => {
                    if (!evt.active) _graphSim.alphaTarget(0);
                    d.fx = null; d.fy = null;
                }))
            // Hover
            .on('mouseenter', (evt, d) => _graphHighlight(d.id, true))
            .on('mouseleave', ()       => _graphHighlight(null,  false))
            // Click → floating card
            .on('click', (evt, d)  => { evt.stopPropagation(); _graphSelectNode(d); });
        _graphNodeSel = nodeEl;

        // ── Labels ──
        const showLbls = _el('adb-graph-labels-cb')?.checked ?? true;
        const labelEl  = g.append('g').attr('class', 'adb-graph-label-g')
            .attr('display', showLbls ? null : 'none')
            .selectAll('text')
            .data(nodes)
            .join('text')
            .attr('text-anchor',      'middle')
            .attr('dominant-baseline','hanging')
            .attr('font-size',        '10')
            .attr('font-family',      'inherit')
            .attr('fill',             '#94a3b8')
            .attr('pointer-events',   'none')
            .attr('dy',               d => _gNodeRadius(d) + 3)
            .text(d => d.name.length > 20 ? d.name.slice(0, 18) + '…' : d.name);
        _graphLabelSel = labelEl;

        // Dismiss card on background click
        svg.on('click', () => _hide('adb-graph-card'));

        // ── Force simulation ──
        _graphSim = d3.forceSimulation(nodes)
            .force('link',      d3.forceLink(links).id(d => d.id).distance(85).strength(0.45))
            .force('charge',    d3.forceManyBody().strength(nodes.length > 150 ? -80 : -200))
            .force('center',    d3.forceCenter(0, 0))
            .force('collision', d3.forceCollide().radius(d => _gNodeRadius(d) + 3))
            .alphaDecay(nodes.length > 200 ? 0.04 : 0.025)
            .on('tick', () => {
                linkEl
                    .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
                    .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
                nodeEl .attr('cx', d => d.x).attr('cy', d => d.y);
                labelEl.attr('x',  d => d.x).attr('y',  d => d.y);
            });

        // Pin focused node at centre so its neighbourhood fans out from it
        if (data.focused_id) {
            const focal = nodes.find(n => n.id === data.focused_id);
            if (focal) { focal.fx = 0; focal.fy = 0; }
        }

        // Centre the view after settling
        _graphSim.on('end', () => {
            const pad = 40;
            const xs  = nodes.map(n => n.x);
            const ys  = nodes.map(n => n.y);
            const x0  = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad;
            const y0  = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad;
            const gw  = x1 - x0 || width;
            const gh  = y1 - y0 || height;
            const sc  = Math.min(8, 0.9 * Math.min(width / gw, height / gh));
            const tx  = width  / 2 - sc * (x0 + gw / 2);
            const ty  = height / 2 - sc * (y0 + gh / 2);
            svg.transition().duration(600)
                .call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(sc));
        });
    }

    // ── Hover highlight ───────────────────────────────────────────────────────

    function _graphHighlight(focusId, on) {
        if (!_graphNodeSel || !_graphLinkSel) return;

        if (!on || !focusId) {
            _graphNodeSel .attr('opacity', 1);
            _graphLinkSel .attr('opacity', 1);
            _graphLabelSel?.attr('opacity', 1);
            return;
        }

        // Collect all IDs directly connected to focusId
        const connected = new Set([focusId]);
        (_graphLinkData || []).forEach(d => {
            const s = typeof d.source === 'object' ? d.source.id : d.source;
            const t = typeof d.target === 'object' ? d.target.id : d.target;
            if (s === focusId) connected.add(t);
            if (t === focusId) connected.add(s);
        });

        _graphNodeSel .attr('opacity', d => connected.has(d.id) ? 1 : 0.1);
        _graphLinkSel .attr('opacity', d => {
            const s = typeof d.source === 'object' ? d.source.id : d.source;
            const t = typeof d.target === 'object' ? d.target.id : d.target;
            return (s === focusId || t === focusId) ? 1 : 0.05;
        });
        _graphLabelSel?.attr('opacity', d => connected.has(d.id) ? 1 : 0.06);
    }

    // ── Node selection card ───────────────────────────────────────────────────

    function _graphSelectNode(d) {
        const typeEl = _el('adb-graph-card-type');
        if (typeEl) {
            typeEl.textContent = d.type || 'other';
            typeEl.className   = `adb-type-badge adb-type-${d.type || 'other'}`;
        }
        const nameEl = _el('adb-graph-card-name');
        if (nameEl) nameEl.textContent = d.name;

        const sumEl = _el('adb-graph-card-summary');
        if (sumEl) sumEl.textContent = d.summary || '';

        const metaEl = _el('adb-graph-card-meta');
        if (metaEl) {
            const isStub = d.status === 'stub';
            metaEl.innerHTML =
                `<span class="adb-badge ${isStub ? 'adb-badge-stub' : 'adb-badge-expanded'}">${isStub ? 'stub' : 'expanded'}</span>` +
                (d.rel_count ? `<span>${d.rel_count} relation${d.rel_count !== 1 ? 's' : ''}</span>` : '');
        }

        const openBtn = _el('adb-graph-card-open');
        if (openBtn) openBtn.onclick = () => { _closeGraph(); _loadEntity(d.id); };

        const focBtn = _el('adb-graph-card-focus');
        if (focBtn) focBtn.onclick = () => _graphLoad(d.id);

        _show('adb-graph-card');
    }

    // ── Focus search ──────────────────────────────────────────────────────────

    async function _graphFocusSearch() {
        const q = _el('adb-graph-search')?.value?.trim();
        if (!q) { _graphLoad(null); return; }

        try {
            // Try exact name lookup first, fall back to search
            let entityId = null;
            const lr = await fetch(`${API}/lookup?name=${encodeURIComponent(q)}&${_dbParam()}`);
            if (lr.ok) {
                entityId = (await lr.json()).id;
            } else {
                const sr   = await fetch(`${API}/search?q=${encodeURIComponent(q)}&${_dbParam({ limit: 1 })}`);
                const sd   = await sr.json();
                entityId   = sd.results?.[0]?.id ?? null;
            }
            if (!entityId) { _toast(`No entity found for "${q}"`, 'error'); return; }
            _graphLoad(entityId);
        } catch (e) {
            _toast(`Focus failed: ${e.message}`, 'error');
        }
    }

    // ── Graph wiring ──────────────────────────────────────────────────────────

    function _graphWire() {
        _el('adb-graph-close-btn') ?.addEventListener('click', _closeGraph);
        _el('adb-graph-focus-btn') ?.addEventListener('click', _graphFocusSearch);
        _el('adb-graph-full-btn')  ?.addEventListener('click', () => {
            const si = _el('adb-graph-search'); if (si) si.value = '';
            _graphLoad(null);
        });
        _el('adb-graph-search')    ?.addEventListener('keydown', e => { if (e.key === 'Enter') _graphFocusSearch(); });
        _el('adb-graph-card-close')?.addEventListener('click',   () => _hide('adb-graph-card'));
        _el('adb-graph-depth')     ?.addEventListener('change',  () => { if (_graphFocusId) _graphLoad(_graphFocusId); });
        _el('adb-graph-labels-cb') ?.addEventListener('change',  e => {
            _graphLabelSel?.attr('display', e.target.checked ? null : 'none');
        });
    }

    // ── Folder distillation ───────────────────────────────────────────────────

    /**
     * File extensions the backend will distil (mirrored from folder_distiller.py).
     * Used purely for the scan-results visual — grays out unsupported types.
     */
    const _FD_SUPPORTED = new Set([
        '.txt','.md','.markdown','.rst','.org','.tex',
        '.html','.htm',
        '.csv','.tsv','.json','.yaml','.yml','.toml','.xml',
        '.py','.js','.ts','.jsx','.tsx','.mjs',
        '.java','.cpp','.c','.h','.hpp',
        '.rb','.go','.rs','.php','.cs','.swift','.kt',
        '.sh','.bash','.zsh','.fish',
        '.sql','.r','.lua','.log',
    ]);

    let _fdScanData    = null;     // last scan result
    let _fdPollHandle  = null;     // setInterval handle

    function _fdEl(id) { return document.getElementById(id); }

    function _fdSection(show) {
        ['adb-fd-pick', 'adb-fd-info', 'adb-fd-prog'].forEach(id => {
            _fdEl(id)?.classList.toggle('hidden', id !== show);
        });
    }

    // ── Browse ────────────────────────────────────────────────────────────────

    async function _fdBrowse() {
        const btn   = _fdEl('adb-fd-browse-btn');
        const input = _fdEl('adb-fd-path-input');
        const init  = input?.value?.trim() || _currentPath || '';
        if (btn) { btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true; }
        try {
            const res  = await fetch(`${BROWSE_API}?initial=${encodeURIComponent(init)}`);
            const data = await res.json();
            if (!data.cancelled && data.path && input) input.value = data.path;
        } catch {
            _toast('Could not open folder browser.', 'error');
        } finally {
            if (btn) { btn.innerHTML = '<i class="fas fa-folder-open"></i>'; btn.disabled = false; }
        }
    }

    // ── Scan ──────────────────────────────────────────────────────────────────

    async function _fdScan() {
        const folder   = _fdEl('adb-fd-path-input')?.value?.trim();
        if (!folder) { _toast('Enter a folder path first.', 'error'); return; }

        const btn      = _fdEl('adb-fd-scan-btn');
        const statusEl = _fdEl('adb-fd-pick-status');

        if (btn) btn.disabled = true;
        if (statusEl) {
            statusEl.textContent = 'Scanning…';
            statusEl.className   = 'adb-status adb-status-loading';
            statusEl.classList.remove('hidden');
        }

        try {
            const res  = await fetch(`${API}/distill-folder/scan?folder=${encodeURIComponent(folder)}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Scan failed');

            _fdScanData = data;
            _fdRenderScanResults(data);
            _fdSection('adb-fd-info');
            if (statusEl) statusEl.classList.add('hidden');
        } catch (e) {
            if (statusEl) {
                statusEl.textContent = `✗ ${e.message}`;
                statusEl.className   = 'adb-status adb-status-error';
            }
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    function _fdRenderScanResults(data) {
        // Stat grid
        const statsEl = _fdEl('adb-fd-scan-stats');
        if (statsEl) {
            statsEl.innerHTML = `
                <div class="adb-fd-stat-grid">
                    <div class="adb-fd-stat-item">
                        <span class="adb-fd-stat-val">${_fmtNum(data.total_files)}</span>
                        <span class="adb-fd-stat-lbl">total files</span>
                    </div>
                    <div class="adb-fd-stat-item adb-fd-stat-item-accent">
                        <span class="adb-fd-stat-val">${_fmtNum(data.supported_files)}</span>
                        <span class="adb-fd-stat-lbl">supported</span>
                    </div>
                    <div class="adb-fd-stat-item">
                        <span class="adb-fd-stat-val">${data.total_size_fmt || _fmtBytes(data.total_size_bytes)}</span>
                        <span class="adb-fd-stat-lbl">total size</span>
                    </div>
                </div>`;
        }

        // File-type breakdown bars
        const typeEl = _fdEl('adb-fd-type-list');
        if (typeEl) {
            const types    = data.top_types || [];
            const maxCount = Math.max(...types.map(t => t.count), 1);
            typeEl.innerHTML = types.slice(0, 8).map(t => {
                const pct       = Math.max(4, Math.round(t.count / maxCount * 100));
                const supported = _FD_SUPPORTED.has(t.ext);
                return `<div class="adb-fd-type-row${supported ? '' : ' adb-fd-type-unsupported'}">
                    <span class="adb-fd-type-ext">${t.ext}</span>
                    <div class="adb-fd-type-bar-wrap">
                        <div class="adb-fd-type-bar" style="width:${pct}%"></div>
                    </div>
                    <span class="adb-fd-type-count">${_fmtNum(t.count)}</span>
                </div>`;
            }).join('');
        }

        // Sync model options to fd-model selector
        const src  = _fdEl('adb-distill-model');
        const dest = _fdEl('adb-fd-model');
        if (src && dest) dest.innerHTML = src.innerHTML;
    }

    // ── Start ─────────────────────────────────────────────────────────────────

    async function _fdStart() {
        const folder      = _fdScanData?.folder_path || _fdEl('adb-fd-path-input')?.value?.trim();
        const model       = _fdEl('adb-fd-model')?.value || 'auto';
        const concurrency = parseInt(_fdEl('adb-fd-concurrency')?.value || '1', 10);
        if (!folder) return;

        const btn = _fdEl('adb-fd-start-btn');
        if (btn) btn.disabled = true;

        try {
            const params = new URLSearchParams(_dbParam({ folder, model, concurrency }));
            const res    = await fetch(`${API}/distill-folder/start?${params}`, { method: 'POST' });
            const data   = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Could not start');

            _fdSection('adb-fd-prog');
            _fdStartPolling();
            const parallelNote = concurrency > 1 ? `, ${concurrency} at a time` : '';
            _toast(`Distilling ${_fmtNum(data.total_files)} files${parallelNote}`, 'info');
        } catch (e) {
            _toast(`Start failed: ${e.message}`, 'error');
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    // ── Pause / Resume / Cancel ───────────────────────────────────────────────

    async function _fdPause() {
        try {
            await fetch(`${API}/distill-folder/pause?${_dbParam()}`, { method: 'POST' });
            _fdStopPolling();
            await _fdPollOnce();   // immediate UI update
        } catch (e) {
            _toast(`Pause failed: ${e.message}`, 'error');
        }
    }

    async function _fdResume() {
        try {
            const res  = await fetch(`${API}/distill-folder/resume?${_dbParam()}`, { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Could not resume');
            _fdStartPolling();
        } catch (e) {
            _toast(`Resume failed: ${e.message}`, 'error');
        }
    }

    async function _fdCancel() {
        if (!confirm('Cancel this distillation job?')) return;
        try {
            await fetch(`${API}/distill-folder/cancel?${_dbParam()}`, { method: 'POST' });
            _fdStopPolling();
            await _fdPollOnce();
        } catch (e) {
            _toast(`Cancel failed: ${e.message}`, 'error');
        }
    }

    // ── Polling ───────────────────────────────────────────────────────────────

    function _fdStartPolling() {
        _fdStopPolling();
        _fdPollOnce();
        _fdPollHandle = setInterval(_fdPollOnce, 2500);
    }

    function _fdStopPolling() {
        if (_fdPollHandle) { clearInterval(_fdPollHandle); _fdPollHandle = null; }
    }

    async function _fdPollOnce() {
        try {
            const res  = await fetch(`${API}/distill-folder/status?${_dbParam()}`);
            const data = await res.json();
            _fdApplyStatus(data);
            if (['paused', 'completed', 'cancelled', 'idle'].includes(data.status)) {
                _fdStopPolling();
            }
        } catch { /* ignore transient poll errors */ }
    }

    // ── Render progress view ──────────────────────────────────────────────────

    function _fdApplyStatus(data) {
        if (!data || data.status === 'idle') {
            _fdSection('adb-fd-pick');
            return;
        }

        _fdSection('adb-fd-prog');

        // Folder name label
        const folderEl = _fdEl('adb-fd-prog-folder');
        if (folderEl) {
            const parts = (data.folder_path || '').replace(/\\/g, '/').split('/').filter(Boolean);
            folderEl.textContent = parts[parts.length - 1] || data.folder_path || '—';
            folderEl.title       = data.folder_path || '';
        }

        // Status badge
        const badgeEl = _fdEl('adb-fd-prog-badge');
        if (badgeEl) {
            const LABELS  = { running:'Running', paused:'Paused', completed:'Done', cancelled:'Cancelled', error:'Error', starting:'Starting' };
            const CLASSES = { running:'adb-fd-badge-running', paused:'adb-fd-badge-paused', completed:'adb-fd-badge-done', cancelled:'adb-fd-badge-paused', error:'adb-fd-badge-error' };
            badgeEl.textContent = LABELS[data.status]  || data.status;
            badgeEl.className   = `adb-fd-badge ${CLASSES[data.status] || ''}`;
        }

        // Progress bar
        const pct    = data.progress_pct ?? 0;
        const fillEl = _fdEl('adb-fd-bar-fill');
        const pctEl  = _fdEl('adb-fd-bar-pct');
        if (fillEl) fillEl.style.width  = `${pct}%`;
        if (pctEl)  pctEl.textContent   = `${pct.toFixed(1)}%`;

        // Stats block
        const statsEl = _fdEl('adb-fd-prog-stats');
        if (statsEl) {
            const total       = data.total_files  || 0;
            const done        = data.next_index   || 0;
            const remaining   = Math.max(0, total - done);
            const concurrency = data.concurrency  || 1;
            const parallelTag = concurrency > 1
                ? `<span class="adb-fd-ps-parallel"><i class="fas fa-bolt"></i> ${concurrency} parallel</span>`
                : '';
            statsEl.innerHTML = `
                <div class="adb-fd-ps-row">
                    <span class="adb-fd-ps-val adb-fd-ps-ok">${_fmtNum(data.processed || 0)}</span>
                    <span class="adb-fd-ps-lbl">distilled</span>
                    <span class="adb-fd-ps-val adb-fd-ps-skip">${_fmtNum(data.skipped  || 0)}</span>
                    <span class="adb-fd-ps-lbl">skipped</span>
                    <span class="adb-fd-ps-val adb-fd-ps-err">${_fmtNum(data.failed   || 0)}</span>
                    <span class="adb-fd-ps-lbl">failed</span>
                    ${parallelTag}
                </div>
                <div class="adb-fd-ps-remaining">${_fmtNum(remaining)} remaining of ${_fmtNum(total)}</div>`;
        }

        // Log window — current file indicator + scrollable history
        const _esc       = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        const logEl      = _fdEl('adb-fd-log');
        const logNowEl   = _fdEl('adb-fd-log-now');

        if (logEl) {
            const entries = Array.isArray(data.log) ? data.log : [];
            if (entries.length > 0) {
                const atBottom = logEl.scrollTop >= logEl.scrollHeight - logEl.clientHeight - 16;
                logEl.innerHTML = entries.map(line => {
                    let cls = 'adb-fd-log-entry';
                    if (line.startsWith('✓')) cls += ' adb-fd-log-ok';
                    else if (line.startsWith('✗')) cls += ' adb-fd-log-err';
                    return `<div class="${cls}">${_esc(line)}</div>`;
                }).join('');
                if (atBottom) logEl.scrollTop = logEl.scrollHeight;
            }
        }

        if (logNowEl) {
            const isActive = data.status === 'running' || data.status === 'starting';
            const cf = (isActive && data.current_file) ? String(data.current_file) : '';
            if (cf) {
                // current_file may be "file1.txt | file2.md | file3.py" for parallel batches
                const parts = cf.split(' | ').filter(Boolean);
                const display = parts.length <= 2
                    ? cf
                    : `${parts[0]}  +${parts.length - 1} more`;
                logNowEl.textContent = `⟳  ${display}`;
                logNowEl.classList.remove('hidden');
            } else {
                logNowEl.classList.add('hidden');
            }
        }

        // Context-sensitive buttons
        const isRunning  = data.status === 'running' || data.status === 'starting';
        const isPaused   = data.status === 'paused';
        const isDone     = data.status === 'completed' || data.status === 'cancelled';

        _fdEl('adb-fd-pause-btn') ?.classList.toggle('hidden', !isRunning);
        _fdEl('adb-fd-resume-btn')?.classList.toggle('hidden', !isPaused);
        _fdEl('adb-fd-cancel-btn')?.classList.toggle('hidden', isDone || (!isRunning && !isPaused));
        _fdEl('adb-fd-new-btn')   ?.classList.toggle('hidden', !isDone);
    }

    // ── Init check (restore state from DISTILLINFO on load) ──────────────────

    async function _fdCheckExistingJob() {
        try {
            const res  = await fetch(`${API}/distill-folder/status?${_dbParam()}`);
            const data = await res.json();
            if (data.status && data.status !== 'idle') {
                _fdApplyStatus(data);
                if (data.status === 'running') _fdStartPolling();
            }
        } catch { /* ignore */ }
    }

    // ── Wire ──────────────────────────────────────────────────────────────────

    function _fdWire() {
        _fdEl('adb-fd-browse-btn')   ?.addEventListener('click', _fdBrowse);
        _fdEl('adb-fd-scan-btn')     ?.addEventListener('click', _fdScan);
        _fdEl('adb-fd-path-input')   ?.addEventListener('keydown', e => { if (e.key === 'Enter') _fdScan(); });
        _fdEl('adb-fd-info-back-btn')?.addEventListener('click', () => _fdSection('adb-fd-pick'));
        _fdEl('adb-fd-start-btn')    ?.addEventListener('click', _fdStart);
        _fdEl('adb-fd-pause-btn')    ?.addEventListener('click', _fdPause);
        _fdEl('adb-fd-resume-btn')   ?.addEventListener('click', _fdResume);
        _fdEl('adb-fd-cancel-btn')   ?.addEventListener('click', _fdCancel);
        _fdEl('adb-fd-new-btn')      ?.addEventListener('click', () => { _fdStopPolling(); _fdSection('adb-fd-pick'); });
    }

    // ── Vector search ─────────────────────────────────────────────────────────────

    let _vecPollHandle = null;

    function _vecStopPolling() {
        if (_vecPollHandle) { clearInterval(_vecPollHandle); _vecPollHandle = null; }
    }

    function _vecStartPolling() {
        _vecStopPolling();
        _vecPollHandle = setInterval(_vecPoll, 2000);
    }

    async function _vecPoll() {
        try {
            const res  = await fetch(`${API}/vectors/status?${_dbParam()}`);
            const data = await res.json();
            _vecApplyStatus(data);
            if (!data.is_vectorizing) _vecStopPolling();
        } catch { /* ignore */ }
    }

    function _vecApplyStatus(data) {
        const statusEl    = _el('adb-vec-status');
        const countEl     = _el('adb-vec-count-label');
        const badgeEl     = _el('adb-vec-badge');
        const fillEl      = _el('adb-vec-bar-fill');
        const pctEl       = _el('adb-vec-bar-pct');
        const generateBtn = _el('adb-vec-generate-btn');
        const cancelBtn   = _el('adb-vec-cancel-btn');

        if (!data || data.status === 'idle') {
            statusEl?.classList.add('hidden');
            if (cancelBtn) cancelBtn.classList.add('hidden');
            return;
        }

        statusEl?.classList.remove('hidden');

        const total      = data.total      || 0;
        const vectorized = data.vectorized || 0;
        const skipped    = data.skipped    || 0;
        const failedCnt  = data.failed     || 0;
        const pct        = total > 0 ? Math.round(vectorized / total * 100) : 0;

        if (fillEl)  fillEl.style.width = `${pct}%`;
        if (pctEl)   pctEl.textContent  = `${pct}%`;

        const STATUS_LABEL = { running:'Running', done:'Done', error:'Error', cancelled:'Cancelled' };
        const STATUS_CLS   = { running:'adb-fd-badge-running', done:'adb-fd-badge-done', error:'adb-fd-badge-error', cancelled:'adb-fd-badge-paused' };
        if (badgeEl) {
            badgeEl.textContent = STATUS_LABEL[data.status] || data.status;
            badgeEl.className   = `adb-fd-badge ${STATUS_CLS[data.status] || ''}`;
        }

        // Build the count label — surface errors prominently
        if (countEl) {
            const errorMsg = data.error || data.last_error || null;
            if ((data.status === 'error' || (data.status === 'done' && vectorized === 0 && failedCnt > 0)) && errorMsg) {
                // Trim long SDK error messages to a readable length
                const short = errorMsg.length > 120 ? errorMsg.slice(0, 120) + '…' : errorMsg;
                countEl.textContent = `Error: ${short}`;
                countEl.style.color = '#f87171';
                if (badgeEl) badgeEl.className = 'adb-fd-badge adb-fd-badge-error';
            } else if (data.status === 'done') {
                const parts = [`${_fmtNum(vectorized)} / ${_fmtNum(total)} embedded`];
                if (skipped  > 0) parts.push(`${_fmtNum(skipped)} skipped`);
                if (failedCnt > 0) parts.push(`${_fmtNum(failedCnt)} failed`);
                countEl.textContent = parts.join(' · ');
                countEl.style.color = failedCnt > 0 ? '#fbbf24' : '';
            } else {
                countEl.textContent = `${_fmtNum(vectorized)} / ${_fmtNum(total)} entities`;
                countEl.style.color = '';
            }
        }

        const isRunning = data.is_vectorizing;
        if (cancelBtn)   cancelBtn.classList.toggle('hidden', !isRunning);
        if (generateBtn) {
            generateBtn.disabled = isRunning;
            generateBtn.innerHTML = isRunning
                ? '<i class="fas fa-spinner fa-spin"></i> Vectorizing…'
                : '<i class="fas fa-microchip"></i> Generate Embeddings';
        }
    }

    async function _vecGenerate() {
        const model         = _el('adb-vec-model')?.value || 'text-embedding-004';
        const forceRewrite  = _el('adb-vec-force')?.checked ?? false;
        const includeStubs  = _el('adb-vec-stubs')?.checked ?? true;
        try {
            const res = await fetch(
                `${API}/vectors/generate?${_dbParam({
                    model,
                    force_rewrite:  forceRewrite,
                    include_stubs:  includeStubs,
                })}`,
                { method: 'POST' }
            );
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `HTTP ${res.status}`);
            }
            _vecApplyStatus({ status: 'running', is_vectorizing: true, total: 0, vectorized: 0 });
            _vecStartPolling();
        } catch(e) {
            _toast(`Vectorize failed: ${e.message}`, 'error');
        }
    }

    async function _vecCancel() {
        try {
            await fetch(`${API}/vectors/cancel?${_dbParam()}`, { method: 'POST' });
            _vecStopPolling();
            _vecPoll();  // refresh status once
        } catch(e) {
            _toast(`Cancel failed: ${e.message}`, 'error');
        }
    }

    async function _vecCheckExisting() {
        try {
            const res  = await fetch(`${API}/vectors/status?${_dbParam()}`);
            const data = await res.json();
            if (data.status && data.status !== 'idle') {
                _vecApplyStatus(data);
                if (data.is_vectorizing) _vecStartPolling();
            }
        } catch { /* ignore */ }
    }

    function _vecWire() {
        _el('adb-vec-generate-btn')?.addEventListener('click', _vecGenerate);
        _el('adb-vec-cancel-btn')  ?.addEventListener('click', _vecCancel);
    }

    // ── Bake ─────────────────────────────────────────────────────────────────

    let _bakePollHandle = null;

    function _bakeStopPolling() {
        if (_bakePollHandle) { clearInterval(_bakePollHandle); _bakePollHandle = null; }
    }

    function _bakeStartPolling() {
        _bakeStopPolling();
        _bakePollHandle = setInterval(_bakePoll, 1500);
    }

    async function _bakePoll() {
        try {
            const res  = await fetch(`${API}/bake/status?${_dbParam()}`);
            const data = await res.json();
            _bakeApplyStatus(data);
            if (data.status !== 'running') { _bakeStopPolling(); _bakeLoadList(); }
        } catch { /* ignore transient poll errors */ }
    }

    function _bakeApplyStatus(data) {
        const resultEl = _el('adb-bake-result');
        const innerEl  = _el('adb-bake-result-inner');
        const bakeBtn  = _el('adb-bake-btn');
        if (!resultEl || !innerEl) return;

        if (!data || data.status === 'idle') {
            resultEl.classList.add('hidden');
            if (bakeBtn) { bakeBtn.disabled = false; bakeBtn.innerHTML = '<i class="fas fa-box-archive"></i> Bake Now'; }
            return;
        }

        resultEl.classList.remove('hidden');

        const STATUS_LABEL = { running:'Baking…', done:'Done', error:'Error' };
        const STATUS_CLS   = { running:'adb-bake-badge-running', done:'adb-bake-badge-done', error:'adb-bake-badge-error' };
        const badge = `<span class="adb-bake-badge ${STATUS_CLS[data.status] || ''}">${STATUS_LABEL[data.status] || data.status}</span>`;

        if (data.status === 'running') {
            innerEl.innerHTML = `<div class="adb-bake-meta-row">${badge} <span>Baking <em>${data.name || ''}</em>…</span></div>`;
            if (bakeBtn) { bakeBtn.disabled = true; bakeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Baking…'; }
        } else if (data.status === 'done') {
            const fmt = { jsonl:'JSONL', json:'JSON', markdown:'Markdown', txt:'Plain text' }[data.format] || data.format || '—';
            innerEl.innerHTML = `
                <div class="adb-bake-meta-row">${badge}
                    <span class="adb-bake-key">Name</span><span class="adb-bake-val">${data.name || '—'}</span>
                </div>
                <div class="adb-bake-meta-row">
                    <span class="adb-bake-key">Format</span><span class="adb-bake-val">${fmt}</span>
                    <span class="adb-bake-key">Entities</span><span class="adb-bake-val">${_fmtNum(data.entity_count)}</span>
                    <span class="adb-bake-key">Size</span><span class="adb-bake-val">${data.size_fmt || '—'}</span>
                </div>`;
            if (bakeBtn) { bakeBtn.disabled = false; bakeBtn.innerHTML = '<i class="fas fa-box-archive"></i> Bake Now'; }
        } else if (data.status === 'error') {
            innerEl.innerHTML = `<div class="adb-bake-meta-row">${badge} <span style="color:#f87171">${data.error || 'Unknown error'}</span></div>`;
            if (bakeBtn) { bakeBtn.disabled = false; bakeBtn.innerHTML = '<i class="fas fa-box-archive"></i> Bake Now'; }
        }
    }

    // ── Baked datasets list ───────────────────────────────────────────────────

    async function _bakeLoadList() {
        const listEl = _el('adb-bake-list');
        if (!listEl) return;
        try {
            const res  = await fetch(`${API}/bake/list?${_dbParam()}`);
            const data = await res.json();
            _bakeRenderList(data.bakes || []);
        } catch { /* ignore */ }
    }

    function _bakeRenderList(bakes) {
        const listEl = _el('adb-bake-list');
        if (!listEl) return;
        if (!bakes.length) {
            listEl.innerHTML = '<div class="adb-empty-hint">No bakes yet — run a bake to see it here.</div>';
            return;
        }
        const FMT_LABEL = { jsonl:'JSONL', json:'JSON', markdown:'MD', txt:'TXT' };
        const FMT_CLS   = { jsonl:'adb-bake-fmt-jsonl', json:'adb-bake-fmt-json', markdown:'adb-bake-fmt-md', txt:'adb-bake-fmt-txt' };
        const _OPENAI   = ['text-embedding-3-small','text-embedding-3-large','text-embedding-ada-002'];

        listEl.innerHTML = bakes.map(b => {
            const fmtLabel   = FMT_LABEL[b.format] || b.format || '?';
            const fmtCls     = FMT_CLS[b.format] || '';
            const dateStr    = b.baked_at ? _fmtDate(b.baked_at) : (b.started_at ? _fmtDate(b.started_at) : '—');
            const running    = b.status === 'running';
            const failed     = b.status === 'error';
            const fileName   = b.output_file || '';

            // Embeddings row — list each model with provider badge
            let embeddingHtml = '';
            if (b.include_vectors) {
                const models = b.vector_models?.length ? b.vector_models : ['all embedded models'];
                const chips  = models.map(m => {
                    const isOpenAI = _OPENAI.includes(m);
                    const provCls  = isOpenAI ? 'adb-vec-provider-openai' : (m === 'all embedded models' ? '' : 'adb-vec-provider-google');
                    const provLbl  = isOpenAI ? 'OpenAI' : (m === 'all embedded models' ? '' : 'Google');
                    return `<span class="adb-bake-emb-chip">
                        <code>${m}</code>
                        ${provLbl ? `<span class="adb-vec-provider-badge ${provCls}">${provLbl}</span>` : ''}
                    </span>`;
                }).join('');
                embeddingHtml = `
                <div class="adb-bake-item-embeddings">
                    <span class="adb-bake-emb-label"><i class="fas fa-microchip"></i> Embeddings</span>
                    <div class="adb-bake-emb-chips">${chips}</div>
                </div>`;
            }

            return `
            <div class="adb-bake-item ${running ? 'adb-bake-item-running' : ''} ${failed ? 'adb-bake-item-error' : ''}" data-name="${b.name}">
                <div class="adb-bake-item-top">
                    <span class="adb-bake-item-name" title="${b.name}">${b.name}</span>
                    <span class="adb-bake-fmt-badge ${fmtCls}">${fmtLabel}</span>
                    ${running ? '<span class="adb-bake-badge adb-bake-badge-running">Running</span>' : ''}
                    ${failed  ? '<span class="adb-bake-badge adb-bake-badge-error">Error</span>'   : ''}
                    ${!running && !failed ? `
                    <div class="adb-bake-item-actions">
                        <button class="adb-btn adb-btn-ghost adb-btn-xs adb-bake-dl-btn" data-name="${b.name}" title="Download ${fileName}">
                            <i class="fas fa-download"></i>
                        </button>
                        <button class="adb-btn adb-btn-ghost adb-btn-xs adb-bake-rename-btn" data-name="${b.name}" title="Rename">
                            <i class="fas fa-pencil"></i>
                        </button>
                        <button class="adb-btn adb-btn-ghost adb-btn-xs adb-bake-del-btn" data-name="${b.name}" title="Delete" style="color:#f87171">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>` : ''}
                </div>
                <div class="adb-bake-item-meta">
                    ${b.entity_count != null ? `<span>${_fmtNum(b.entity_count)} entities</span>` : ''}
                    ${b.size_fmt   ? `<span>${b.size_fmt}</span>` : ''}
                    ${b.include_stubs === false ? `<span style="color:#f59e0b">no stubs</span>` : ''}
                    ${fileName     ? `<span class="adb-bake-filename" title="${fileName}">${fileName}</span>` : ''}
                    <span>${dateStr}</span>
                </div>
                ${embeddingHtml}
            </div>`;
        }).join('');

        // Wire item buttons
        listEl.querySelectorAll('.adb-bake-dl-btn').forEach(btn =>
            btn.addEventListener('click', () => _bakeDownloadItem(btn.dataset.name)));
        listEl.querySelectorAll('.adb-bake-del-btn').forEach(btn =>
            btn.addEventListener('click', () => _bakeDeleteItem(btn.dataset.name)));
        listEl.querySelectorAll('.adb-bake-rename-btn').forEach(btn =>
            btn.addEventListener('click', () => _bakeRenameItem(btn.dataset.name)));
    }

    function _bakeDownloadItem(name) {
        const a = document.createElement('a');
        a.href  = `${API}/bake/${encodeURIComponent(name)}/download?${_dbParam()}`;
        a.click();
    }

    async function _bakeOpenFolder() {
        try {
            await fetch(`${API}/bake/open-folder?${_dbParam()}`, { method: 'POST' });
        } catch (e) { _toast(`Could not open folder: ${e.message}`, 'error'); }
    }

    async function _bakeDeleteItem(name) {
        if (!confirm(`Delete bake "${name}"? This cannot be undone.`)) return;
        try {
            const res = await fetch(`${API}/bake/${encodeURIComponent(name)}?${_dbParam()}`, { method: 'DELETE' });
            if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
            _toast(`Deleted bake "${name}"`, 'info');
            _bakeLoadList();
        } catch (e) { _toast(`Delete failed: ${e.message}`, 'error'); }
    }

    async function _bakeRenameItem(oldName) {
        const listEl = _el('adb-bake-list');
        const itemEl = listEl?.querySelector(`.adb-bake-item[data-name="${oldName}"]`);
        if (!itemEl) return;
        const nameSpan = itemEl.querySelector('.adb-bake-item-name');
        if (!nameSpan) return;

        const input = document.createElement('input');
        input.type      = 'text';
        input.value     = oldName;
        input.className = 'adb-bake-rename-input';
        input.maxLength = 64;
        nameSpan.replaceWith(input);
        input.select();

        const commit = async () => {
            const newName = input.value.trim();
            if (!newName || newName === oldName) { _bakeLoadList(); return; }
            try {
                const res = await fetch(
                    `${API}/bake/${encodeURIComponent(oldName)}?${_dbParam()}`,
                    { method: 'PATCH', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ new_name: newName }) }
                );
                if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
                _toast(`Renamed to "${newName}"`, 'info');
            } catch (e) { _toast(`Rename failed: ${e.message}`, 'error'); }
            _bakeLoadList();
        };

        input.addEventListener('blur',  commit);
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
            if (e.key === 'Escape') { _bakeLoadList(); }
        });
    }

    let _bakeVecModelsLoaded = false;

    async function _bakeDiscoverVecModels() {
        const hint    = _el('adb-bake-vec-hint');
        const listEl  = _el('adb-bake-vec-model-list');
        if (!listEl) return;

        if (hint) hint.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Scanning database…';
        listEl.innerHTML = '';

        try {
            const res  = await fetch(`${API}/vectors/models?${_dbParam()}`);
            const data = await res.json();
            const models = data.models || [];

            if (!models.length) {
                if (hint) hint.textContent = 'No embeddings found in this database.';
                return;
            }

            if (hint) hint.classList.add('hidden');

            const _OPENAI = ['text-embedding-3-small','text-embedding-3-large','text-embedding-ada-002'];
            listEl.innerHTML = models.map(m => {
                const provider = _OPENAI.includes(m) ? 'OpenAI' : 'Google';
                const provCls  = _OPENAI.includes(m) ? 'adb-vec-provider-openai' : 'adb-vec-provider-google';
                return `
                <label class="adb-bake-vec-model-row">
                    <input type="checkbox" class="adb-bake-vec-model-cb" value="${m}" checked>
                    <span class="adb-bake-vec-model-name">${m}</span>
                    <span class="adb-vec-provider-badge ${provCls}">${provider}</span>
                </label>`;
            }).join('');

            _bakeVecModelsLoaded = true;
        } catch {
            if (hint) hint.textContent = 'Could not load embedding models.';
        }
    }

    function _bakeToggleVecFoldout(open) {
        const foldout = _el('adb-bake-vec-foldout');
        const chevron = _el('adb-bake-vec-chevron');
        if (!foldout) return;
        if (open) {
            foldout.classList.remove('hidden');
            if (chevron) chevron.style.transform = 'rotate(180deg)';
            if (!_bakeVecModelsLoaded) _bakeDiscoverVecModels();
        } else {
            foldout.classList.add('hidden');
            if (chevron) chevron.style.transform = '';
        }
    }

    function _bakeGetSelectedModels() {
        const cbs = document.querySelectorAll('.adb-bake-vec-model-cb:checked');
        return Array.from(cbs).map(cb => cb.value);
    }

    async function _bakeStart() {
        const name           = (_el('adb-bake-name')?.value.trim() || 'default');
        const fmt            = _el('adb-bake-format')?.value || 'jsonl';
        const includeStubs   = _el('adb-bake-stubs')?.checked ?? true;
        const includeVectors = _el('adb-bake-vectors')?.checked ?? false;
        const vectorModels   = includeVectors ? _bakeGetSelectedModels() : [];
        const bakeBtn        = _el('adb-bake-btn');

        if (bakeBtn) { bakeBtn.disabled = true; bakeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting…'; }

        try {
            const res = await fetch(`${API}/bake?${_dbParam()}`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ name, format: fmt, include_stubs: includeStubs, include_vectors: includeVectors, vector_models: vectorModels }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `HTTP ${res.status}`);
            }
            _bakeApplyStatus({ status: 'running', name });
            _bakeStartPolling();
        } catch (e) {
            _toast(`Bake failed: ${e.message}`, 'error');
            if (bakeBtn) { bakeBtn.disabled = false; bakeBtn.innerHTML = '<i class="fas fa-box-archive"></i> Bake Now'; }
        }
    }

    async function _bakeCheckExisting() {
        try {
            const res  = await fetch(`${API}/bake/status?${_dbParam()}`);
            const data = await res.json();
            if (data.status && data.status !== 'idle') {
                _bakeApplyStatus(data);
                if (data.status === 'running') _bakeStartPolling();
            }
        } catch { /* ignore */ }
    }

    function _bakeWire() {
        _el('adb-bake-btn')              ?.addEventListener('click', _bakeStart);
        _el('adb-bake-refresh-list')     ?.addEventListener('click', _bakeLoadList);
        _el('adb-bake-open-folder-btn')  ?.addEventListener('click', _bakeOpenFolder);
        _el('adb-bake-vectors')?.addEventListener('change', e => {
            _bakeToggleVecFoldout(e.target.checked);
        });
    }

    // ══════════════════════════════════════════════════════════════════════════
    // API Explorer
    // ══════════════════════════════════════════════════════════════════════════

    const _API_V1 = '/api/v1';

    // ── Endpoint definitions ──────────────────────────────────────────────────

    const _EP = [
        {
            group: 'raw', label: 'Raw Database', icon: 'fa-database',
            items: [
                { id:'raw.entities.list',      method:'GET',    path:'/{db}/raw/entities',
                  label:'List Entities',        desc:'Paginated list with optional status / type filters.',
                  params:[{n:'status',v:'active',d:'active | stub | deleted | all'},{n:'type',v:'',d:'Filter by entity type'},{n:'limit',v:'50',d:'Max results (≤500)'},{n:'cursor',v:'',d:'Cursor from previous response'}],
                  body: null },

                { id:'raw.entities.get',        method:'GET',    path:'/{db}/raw/entities/{id}',
                  label:'Get Entity',           desc:'Retrieve a single entity by ID.',
                  pathParams:[{n:'id',v:''}],
                  params:[{n:'sections',v:'',d:'Comma-separated: core,relations,vectors,timeline,properties'}],
                  body: null },

                { id:'raw.entities.upsert',     method:'POST',   path:'/{db}/raw/entities/upsert',
                  label:'Upsert Entity',        desc:'Create or merge by name. Relations resolved automatically.',
                  body:{ name:'Aetheron Prime', type:'character', source:'api',
                         summary:'The first-born AI consciousness of the Aethvion galaxy.',
                         aliases:['The Prime'], tags:['ai','protagonist'],
                         properties:{ faction:'Aethvion Council' },
                         relations:[{ kind:'allied_with', target_name:'Cipher Unit 7', note:'since the Fracture War' }] } },

                { id:'raw.entities.batch',      method:'POST',   path:'/{db}/raw/entities/batch',
                  label:'Batch Operations',     desc:'Multiple create / patch / delete in one call.',
                  body:{ operations:[
                    { op:'upsert', data:{ name:'Entity A', type:'character', summary:'...' } },
                    { op:'upsert', data:{ name:'Entity B', type:'location',  summary:'...' } },
                  ], atomic:false } },

                { id:'raw.entities.patch',      method:'PATCH',  path:'/{db}/raw/entities/{id}',
                  label:'Patch Entity',         desc:'Partial update using dot-path mutations.',
                  pathParams:[{n:'id',v:''}],
                  body:{ mutations:{ 'sections.core.summary':'Updated summary.', 'sections.core.tags':['updated'] } } },

                { id:'raw.entities.delete',     method:'DELETE', path:'/{db}/raw/entities/{id}',
                  label:'Delete Entity',        desc:'Soft-delete by default. Pass ?hard=true for permanent removal.',
                  pathParams:[{n:'id',v:''}],
                  params:[{n:'hard',v:'false',d:'true for permanent deletion'}],
                  body: null },

                { id:'raw.search',              method:'POST',   path:'/{db}/raw/search',
                  label:'Hybrid Search',        desc:'Combine keyword, vector, and metadata modes with scoring.',
                  body:{ query:'ancient AI consciousness allied with rebels',
                         modes:['keyword','vector'], vector_model:'text-embedding-3-small',
                         filters:{ type:'character', status:'active' }, limit:20, min_score:0.3 } },

                { id:'raw.vectors.search',      method:'POST',   path:'/{db}/raw/vectors/search',
                  label:'Vector Similarity',    desc:'ANN search — embed on server or supply your own vector.',
                  body:{ query:'ancient AI consciousness', model:'text-embedding-3-small', top_k:10, filters:{} } },

                { id:'raw.graph.traverse',      method:'POST',   path:'/{db}/raw/graph/traverse',
                  label:'Graph Traverse',       desc:'BFS from a start node with depth, direction, and relation filters.',
                  body:{ start_id:'', algorithm:'bfs', depth:2, direction:'outbound', relation_kinds:null, limit:100 } },

                { id:'raw.graph.neighbors',     method:'GET',    path:'/{db}/raw/graph/neighbors/{id}',
                  label:'Get Neighbors',        desc:"Entity's immediate inbound and outbound neighbors.",
                  pathParams:[{n:'id',v:''}],
                  params:[{n:'direction',v:'both',d:'outbound | inbound | both'}],
                  body: null },

                { id:'raw.graph.path',          method:'POST',   path:'/{db}/raw/graph/path',
                  label:'Shortest Path',        desc:'BFS shortest path between two entities.',
                  body:{ start_id:'', end_id:'', max_depth:6 } },

                { id:'raw.distill',             method:'POST',   path:'/{db}/raw/distill',
                  label:'Distill Text',         desc:'AI extracts structured entities from any text.',
                  body:{ content:'The Aethvion Council is an ancient governing body…', source:'api', model:'auto' } },

                { id:'raw.entities.relations',  method:'GET',    path:'/{db}/raw/entities/{id}/relations',
                  label:'Entity Relations',     desc:'All relations with resolved target names.',
                  pathParams:[{n:'id',v:''}], body: null },

                { id:'raw.entities.vectors',    method:'GET',    path:'/{db}/raw/entities/{id}/vectors',
                  label:'Entity Vectors',       desc:'Embedding metadata stored on an entity.',
                  pathParams:[{n:'id',v:''}], body: null },

                { id:'raw.entities.timeline',   method:'GET',    path:'/{db}/raw/entities/{id}/timeline',
                  label:'Entity Timeline',      desc:'Timeline events for an entity.',
                  pathParams:[{n:'id',v:''}], body: null },
            ]
        },
        {
            group: 'baked', label: 'Baked Snapshots', icon: 'fa-box-archive',
            items: [
                { id:'baked.list',              method:'GET',    path:'/{db}/baked',
                  label:'List Snapshots',       desc:'All named bakes for this database, newest first.',
                  body: null },

                { id:'baked.trigger',           method:'POST',   path:'/{db}/baked',
                  label:'Trigger Bake',         desc:'Start a new bake job in the background.',
                  body:{ name:'my-snapshot', format:'jsonl', include_stubs:false, include_vectors:false, vector_models:[] } },

                { id:'baked.get',               method:'GET',    path:'/{db}/baked/{name}',
                  label:'Get Snapshot',         desc:'Metadata for a named bake.',
                  pathParams:[{n:'name',v:'default'}], body: null },

                { id:'baked.entities',          method:'GET',    path:'/{db}/baked/{name}/entities',
                  label:'Snapshot Entities',    desc:'Paginated entities from a baked snapshot.',
                  pathParams:[{n:'name',v:'default'}],
                  params:[{n:'limit',v:'100',d:'Max results (≤500)'},{n:'cursor',v:'',d:'Pagination cursor'}],
                  body: null },

                { id:'baked.search',            method:'POST',   path:'/{db}/baked/{name}/search',
                  label:'Search Snapshot',      desc:'Keyword search within a baked snapshot — no live DB required.',
                  pathParams:[{n:'name',v:'default'}],
                  body:{ query:'ancient AI', filters:{ type:'character' }, limit:20 } },

                { id:'baked.delete',            method:'DELETE', path:'/{db}/baked/{name}',
                  label:'Delete Snapshot',      desc:'Remove a named bake and its metadata.',
                  pathParams:[{n:'name',v:'default'}], body: null },
            ]
        },
        {
            group: 'keys', label: 'API Keys', icon: 'fa-key',
            items: [
                { id:'keys.list',               method:'GET',    path:'/{db}/keys',
                  label:'List Keys',            desc:'All API keys for this database (hashes not shown).',
                  body: null },

                { id:'keys.generate',           method:'POST',   path:'/{db}/keys',
                  label:'Generate Key',         desc:'Generate a new API key. Shown once — copy immediately.',
                  body:{ label:'my-key', scopes:['read','write'] } },

                { id:'keys.revoke',             method:'DELETE', path:'/{db}/keys/{label}',
                  label:'Revoke Key',           desc:'Permanently revoke a key by its label.',
                  pathParams:[{n:'label',v:'my-key'}], body: null },
            ]
        },
    ];

    // ── State ─────────────────────────────────────────────────────────────────

    let _apiCurrentEp   = null;   // selected endpoint definition
    let _apiCurrentLang = 'python';
    let _apiLastRaw     = '';     // last raw response text (for copy)
    let _apiCodeRaw     = '';     // current code text (for copy)
    let _apiParamValues = {};     // {paramName: value} for path + query params

    // DB context
    let _apiDb         = null;    // null = inherit _currentDb; string = API-tab override
    let _apiDbs        = [];      // available database names
    let _apiDbTypes    = [];      // entity types in current API db (for smart selects)
    let _apiDbBakes    = [];      // bake names for {name} path params
    let _apiDbKeys     = [];      // key labels for {label} path params
    let _apiDbStats    = {};      // {total, stub_count, by_type}
    let _apiCtxReady   = false;   // has context been loaded for current _apiDb?

    // Entity picker
    let _apiPickerParam  = null;  // which param name the picker is filling
    let _apiPickerTimer  = null;  // debounce handle

    // ── Helpers ───────────────────────────────────────────────────────────────

    function _apiEl(id) { return document.getElementById(id); }

    /** The database the API Explorer is currently targeting. */
    function _apiCurrentDb() {
        if (_apiDb) return _apiDb;
        if (_currentPath) {
            const p = _currentPath.replace(/\\/g, '/').split('/').filter(Boolean);
            return p[p.length - 1] || 'default';
        }
        return _currentDb || 'default';
    }

    function _apiBuildUrl(ep, pathValues, queryValues) {
        let path = ep.path.replace('{db}', _apiCurrentDb());
        for (const [k, v] of Object.entries(pathValues || {})) {
            if (v) path = path.replace(`{${k}}`, encodeURIComponent(v));
        }
        const qp = new URLSearchParams();
        for (const [k, v] of Object.entries(queryValues || {})) {
            if (v !== '' && v !== null && v !== undefined) qp.set(k, v);
        }
        const qs = qp.toString();
        return `${_API_V1}${path}${qs ? '?' + qs : ''}`;
    }

    function _apiMethodClass(method) {
        return { GET:'adb-api-m-get', POST:'adb-api-m-post', PATCH:'adb-api-m-patch', DELETE:'adb-api-m-delete' }[method] || 'adb-api-m-get';
    }
    function _apiBadgeClass(method) {
        return { GET:'adb-api-m-get', POST:'adb-api-m-post', PATCH:'adb-api-m-patch', DELETE:'adb-api-m-delete' }[method] || 'adb-api-m-get';
    }

    function _apiHighlightJson(raw) {
        return raw
            .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, m => {
                let cls = 'adb-json-number';
                if (/^"/.test(m)) cls = /:$/.test(m) ? 'adb-json-key' : 'adb-json-string';
                else if (/true|false/.test(m)) cls = 'adb-json-bool';
                else if (/null/.test(m)) cls = 'adb-json-null';
                return `<span class="${cls}">${m}</span>`;
            });
    }

    function _apiFmtBytes(b) {
        if (b < 1024) return b + ' B';
        if (b < 1024*1024) return (b/1024).toFixed(1) + ' KB';
        return (b/1024/1024).toFixed(1) + ' MB';
    }

    // ── Smart param control ───────────────────────────────────────────────────

    /**
     * Returns an HTML string for the appropriate input control for a given
     * parameter name. Context-aware: uses loaded DB entity types, bake names,
     * and key labels when available.
     */
    function _apiSmartControl(name, defaultVal, desc, isPath) {
        const n    = (name || '').toLowerCase();
        const val  = defaultVal != null ? String(defaultVal) : '';
        const base = isPath ? 'adb-api-path-param' : 'adb-api-query-param';
        const esc  = s => String(s).replace(/"/g, '&quot;').replace(/</g, '&lt;');

        // Entity ID → picker button + hidden input
        if (isPath && n === 'id') {
            return `<div class="adb-api-pick-row">
                <input class="adb-api-small-input ${base}" data-param="${name}"
                    value="${esc(val)}" placeholder="entity ID" style="width:90px;min-width:60px">
                <button class="adb-api-pick-btn" data-pick-param="${name}" title="Browse entities">
                    <i class="fas fa-search"></i>
                </button>
                <span class="adb-api-pick-label">${val ? esc(val) : 'pick…'}</span>
            </div>`;
        }

        // Bake name → dropdown from _apiDbBakes, fallback text input
        if (isPath && n === 'name') {
            if (_apiDbBakes.length) {
                const cur = val || _apiDbBakes[0];
                return `<select class="adb-api-small-input adb-api-smart-select ${base}" data-param="${name}">
                    ${_apiDbBakes.map(b => `<option value="${esc(b)}" ${b === cur ? 'selected' : ''}>${esc(b)}</option>`).join('')}
                </select>`;
            }
            return `<input class="adb-api-small-input ${base}" data-param="${name}"
                value="${esc(val || 'default')}" placeholder="snapshot name" style="width:130px">`;
        }

        // Key label → dropdown from _apiDbKeys, fallback text input
        if (isPath && n === 'label') {
            if (_apiDbKeys.length) {
                const cur = val || _apiDbKeys[0];
                return `<select class="adb-api-small-input adb-api-smart-select ${base}" data-param="${name}">
                    ${_apiDbKeys.map(k => `<option value="${esc(k)}" ${k === cur ? 'selected' : ''}>${esc(k)}</option>`).join('')}
                </select>`;
            }
            return `<input class="adb-api-small-input ${base}" data-param="${name}"
                value="${esc(val)}" placeholder="key label" style="width:130px">`;
        }

        // status → fixed set
        if (!isPath && n === 'status') {
            const opts = ['active', 'stub', 'deleted', 'all'];
            const cur  = val || 'active';
            return `<select class="adb-api-small-input adb-api-smart-select ${base}" data-param="${name}">
                ${opts.map(o => `<option value="${o}" ${o === cur ? 'selected' : ''}>${o}</option>`).join('')}
            </select>`;
        }

        // type → entity types from DB + "any"
        if (!isPath && n === 'type') {
            if (_apiDbTypes.length) {
                return `<select class="adb-api-small-input adb-api-smart-select ${base}" data-param="${name}">
                    <option value="">— any —</option>
                    ${_apiDbTypes.map(t => `<option value="${esc(t)}" ${t === val ? 'selected' : ''}>${esc(t)}</option>`).join('')}
                </select>`;
            }
            return `<input class="adb-api-small-input ${base}" data-param="${name}"
                value="${esc(val)}" placeholder="entity type" style="width:130px">`;
        }

        // direction → fixed set
        if (!isPath && n === 'direction') {
            const opts = ['both', 'outbound', 'inbound'];
            const cur  = val || 'both';
            return `<select class="adb-api-small-input adb-api-smart-select ${base}" data-param="${name}">
                ${opts.map(o => `<option value="${o}" ${o === cur ? 'selected' : ''}>${o}</option>`).join('')}
            </select>`;
        }

        // hard → boolean
        if (!isPath && n === 'hard') {
            return `<select class="adb-api-small-input adb-api-smart-select ${base}" data-param="${name}">
                <option value="false" ${val !== 'true' ? 'selected' : ''}>false</option>
                <option value="true"  ${val === 'true' ? 'selected' : ''}>true</option>
            </select>`;
        }

        // numeric inputs
        if (['limit', 'top_k', 'max_depth', 'offset', 'max_entities'].includes(n)) {
            return `<input type="number" class="adb-api-small-input ${base}" data-param="${name}"
                value="${esc(val)}" placeholder="${n}" min="1" style="width:80px">`;
        }

        // sections → hints
        if (!isPath && n === 'sections') {
            return `<input class="adb-api-small-input ${base}" data-param="${name}"
                value="${esc(val)}" placeholder="core,relations,vectors" style="width:180px">`;
        }

        // default text input
        const placeholder = isPath ? 'required' : 'optional';
        return `<input class="adb-api-small-input ${base}" data-param="${name}"
            value="${esc(val)}" placeholder="${placeholder}" style="width:130px">`;
    }

    // ── Smart params pane ─────────────────────────────────────────────────────

    function _apiRenderSmartParams(ep) {
        const cont = _apiEl('adb-api-params-content');
        if (!cont) return;

        const pathParams  = ep.pathParams || [];
        const queryParams = ep.params     || [];
        let   html        = '';

        if (pathParams.length) {
            html += `<div class="adb-api-params-group-label">Path Parameters</div>
            <table class="adb-api-params-table-inner">
                <thead><tr><th>Name</th><th>Value</th><th>Description</th></tr></thead>
                <tbody>
                ${pathParams.map(p => `<tr>
                    <td class="adb-api-param-name">{${p.n}}</td>
                    <td>${_apiSmartControl(p.n, p.v, 'Path param', true)}</td>
                    <td class="adb-api-param-desc">path</td>
                </tr>`).join('')}
                </tbody>
            </table>`;
        }

        if (queryParams.length) {
            html += `<div class="adb-api-params-group-label" style="margin-top:0.6rem">Query Parameters</div>
            <table class="adb-api-params-table-inner">
                <thead><tr><th>Name</th><th>Value</th><th>Description</th></tr></thead>
                <tbody>
                ${queryParams.map(p => `<tr>
                    <td class="adb-api-param-name">${p.n}</td>
                    <td>${_apiSmartControl(p.n, p.v, p.d, false)}</td>
                    <td class="adb-api-param-desc">${p.d || ''}</td>
                </tr>`).join('')}
                </tbody>
            </table>`;
        }

        if (!pathParams.length && !queryParams.length) {
            html = '<div class="adb-empty-hint" style="padding:0.75rem">No parameters for this endpoint.</div>';
        }

        cont.innerHTML = html;

        // Initialise _apiParamValues from rendered inputs + selects
        cont.querySelectorAll('.adb-api-path-param, .adb-api-query-param').forEach(ctrl => {
            _apiParamValues[ctrl.dataset.param] = ctrl.value;

            const onChange = () => {
                _apiParamValues[ctrl.dataset.param] = ctrl.value;
                // If it's the entity ID path param, update the pick-label
                if (ctrl.classList.contains('adb-api-path-param')) {
                    const label = ctrl.closest('td')?.querySelector('.adb-api-pick-label');
                    if (label) label.textContent = ctrl.value || 'pick…';
                }
                _apiUpdateUrlDisplay();
                _apiGenerateCode(_apiCurrentLang);
            };
            ctrl.addEventListener('input',  onChange);
            ctrl.addEventListener('change', onChange);
        });

        // Wire entity picker open buttons
        cont.querySelectorAll('.adb-api-pick-btn').forEach(btn => {
            btn.addEventListener('click', () => _apiPickerOpen(btn.dataset.pickParam));
        });
    }

    // ── DB list + context loading ─────────────────────────────────────────────

    async function _apiLoadDatabases() {
        const sel = _apiEl('adb-api-db-select');
        if (!sel) return;

        try {
            // Try the v1 discovery endpoint first
            const res  = await fetch(`${_API_V1}/`);
            const data = await res.json();
            _apiDbs = (data?.data?.databases || []).map(d => (typeof d === 'string' ? d : d.name));
        } catch {
            // Fallback to the legacy endpoint
            try {
                const res  = await fetch(`${API}/databases`);
                const data = await res.json();
                _apiDbs = (data.databases || []).map(d => d.name || d);
            } catch { _apiDbs = []; }
        }

        // If the current global DB isn't in the discovered list, prepend it
        // (handles edge case where path-based DB has same folder name as a named DB)
        const cur = _apiCurrentDb();
        if (cur && !_apiDbs.includes(cur)) _apiDbs.unshift(cur);

        sel.innerHTML = _apiDbs.length
            ? _apiDbs.map(name =>
                `<option value="${name}" ${name === cur ? 'selected' : ''}>${name}</option>`
              ).join('')
            : `<option value="${cur}">${cur}</option>`;
    }

    function _apiSetDb(name) {
        _apiDb       = name || null;
        _apiCtxReady = false;
        _apiDbTypes  = [];
        _apiDbBakes  = [];
        _apiDbKeys   = [];
        _apiDbStats  = {};
        _apiUpdateUrlDisplay();
        _apiUpdateDbStats();
        _apiLoadDbContext();
    }

    async function _apiLoadDbContext() {
        const db = _apiCurrentDb();

        // ── Entity types + counts ──
        // When _apiDb is null and the global explorer has a path-based database,
        // pass ?path= so the legacy endpoint reads the right directory AND
        // triggers register_path_db() — priming the registry for all v1 calls.
        try {
            let statsUrl = `${API}/stats?db=${encodeURIComponent(db)}`;
            if (!_apiDb && _currentPath) {
                statsUrl += `&path=${encodeURIComponent(_currentPath)}`;
            }
            const res  = await fetch(statsUrl);
            const data = await res.json();
            _apiDbStats = data;
            _apiDbTypes = Object.keys(data.by_type || {}).sort();
        } catch { _apiDbStats = {}; _apiDbTypes = []; }

        // ── Bake names ──
        try {
            const res  = await fetch(`${_API_V1}/${encodeURIComponent(db)}/baked`);
            const data = await res.json();
            // API returns "bakes" key (list_bakes endpoint); keep "snapshots" as fallback
            _apiDbBakes = (data?.data?.bakes || data?.data?.snapshots || []).map(s => s.name).filter(Boolean);
        } catch { _apiDbBakes = []; }

        // ── Key labels ──
        try {
            const res  = await fetch(`${_API_V1}/${encodeURIComponent(db)}/keys`);
            const data = await res.json();
            _apiDbKeys = (data?.data?.keys || []).map(k => k.label).filter(Boolean);
        } catch { _apiDbKeys = []; }

        _apiCtxReady = true;
        _apiUpdateDbStats();

        // Re-render params for the active endpoint so smart controls pick up new context
        if (_apiCurrentEp) _apiRenderSmartParams(_apiCurrentEp);
    }

    function _apiUpdateDbStats() {
        const el = _apiEl('adb-api-db-stats');
        if (!el) return;
        const total  = _apiDbStats.total_entities ?? _apiDbStats.count ?? null;
        const stubs  = _apiDbStats.stub_count ?? null;
        const types  = _apiDbTypes.length;
        const bakes  = _apiDbBakes.length;
        if (total != null) {
            let txt = `${_fmtNum(total)} entities`;
            if (stubs != null) txt += ` · ${_fmtNum(stubs)} stubs`;
            if (types)  txt += ` · ${types} type${types !== 1 ? 's' : ''}`;
            if (bakes)  txt += ` · ${bakes} snapshot${bakes !== 1 ? 's' : ''}`;
            el.textContent = txt;
        } else if (bakes) {
            el.textContent = `${bakes} snapshot${bakes !== 1 ? 's' : ''}`;
        } else {
            el.textContent = '';
        }
    }

    // ── Entity picker ─────────────────────────────────────────────────────────

    function _apiPickerOpen(paramName) {
        _apiPickerParam = paramName;
        const overlay = _apiEl('adb-api-picker');
        if (!overlay) return;
        overlay.classList.remove('hidden');
        const input = _apiEl('adb-api-picker-search');
        if (input) { input.value = ''; input.focus(); }
        // Show empty-state message without hitting the API on open
        const resultsEl = _apiEl('adb-api-picker-results');
        if (resultsEl) resultsEl.innerHTML = '<div class="adb-empty-hint">Type to search entities…</div>';
    }

    async function _apiPickerSearch(q) {
        const db        = _apiCurrentDb();
        const resultsEl = _apiEl('adb-api-picker-results');
        if (!resultsEl) return;

        resultsEl.innerHTML = '<div class="adb-empty-hint"><i class="fas fa-spinner fa-spin"></i></div>';

        try {
            const res  = await fetch(`${_API_V1}/${encodeURIComponent(db)}/raw/search`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ query: q || '', modes: ['keyword'], limit: 25 }),
            });
            const data = await res.json();
            const items = data?.data?.results || [];

            if (!items.length) {
                resultsEl.innerHTML = q
                    ? '<div class="adb-empty-hint">No results.</div>'
                    : '<div class="adb-empty-hint">Type to search entities…</div>';
                return;
            }

            resultsEl.innerHTML = items.map(e => {
                const name = (e.name || '').replace(/</g, '&lt;');
                const type = (e.type || '').replace(/</g, '&lt;');
                const id   = (e.id   || '').replace(/</g, '&lt;');
                return `<div class="adb-api-picker-item" data-id="${id}" data-name="${name}" data-type="${type}">
                    <span class="adb-api-picker-item-name">${name}</span>
                    ${type ? `<span class="adb-api-picker-item-type">${type}</span>` : ''}
                    <code class="adb-api-picker-item-id">${id}</code>
                </div>`;
            }).join('');

            resultsEl.querySelectorAll('.adb-api-picker-item').forEach(item => {
                item.addEventListener('click', () =>
                    _apiPickerSelect(item.dataset.id, item.dataset.name, item.dataset.type)
                );
            });
        } catch {
            resultsEl.innerHTML = '<div class="adb-empty-hint">Search failed.</div>';
        }
    }

    function _apiPickerClose() {
        _apiEl('adb-api-picker')?.classList.add('hidden');
        _apiPickerParam = null;
        clearTimeout(_apiPickerTimer);
    }

    function _apiPickerSelect(id, name, type) {
        if (!_apiPickerParam) return;

        // Fill the matching path-param input
        const input = document.querySelector(`.adb-api-path-param[data-param="${_apiPickerParam}"]`);
        if (input) {
            input.value = id;
            _apiParamValues[_apiPickerParam] = id;

            // Update the pick-label next to the input
            const label = input.closest('td')?.querySelector('.adb-api-pick-label');
            if (label) label.textContent = `${name}${type ? ' · ' + type : ''}`;

            _apiUpdateUrlDisplay();
            _apiGenerateCode(_apiCurrentLang);
        }

        _apiPickerClose();
    }

    // ── Render endpoint tree ──────────────────────────────────────────────────

    function _apiRenderTree() {
        const treeEl = _apiEl('adb-api-tree');
        if (!treeEl) return;
        treeEl.innerHTML = _EP.map(group => `
            <div class="adb-api-tree-group" data-group="${group.group}">
                <div class="adb-api-tree-group-hdr">
                    <i class="fas ${group.icon}"></i>
                    ${group.label}
                    <i class="fas fa-chevron-down adb-api-tree-group-chevron"></i>
                </div>
                <div class="adb-api-tree-items">
                    ${group.items.map(ep => `
                        <div class="adb-api-tree-item" data-ep-id="${ep.id}">
                            <span class="adb-api-method-sm ${_apiMethodClass(ep.method)}">${ep.method}</span>
                            <span>${ep.label}</span>
                        </div>`).join('')}
                </div>
            </div>`).join('');

        // Wire group collapse toggle
        treeEl.querySelectorAll('.adb-api-tree-group-hdr').forEach(hdr => {
            hdr.addEventListener('click', () => {
                hdr.parentElement.classList.toggle('collapsed');
            });
        });

        // Wire endpoint selection
        treeEl.querySelectorAll('.adb-api-tree-item').forEach(item => {
            item.addEventListener('click', () => {
                const epId = item.dataset.epId;
                const ep   = _EP.flatMap(g => g.items).find(e => e.id === epId);
                if (ep) _apiSelectEndpoint(ep);
            });
        });

        // Bootstrap DB list + context on first open
        if (!_apiCtxReady) {
            _apiLoadDatabases();
            _apiLoadDbContext();
        }
    }

    // ── Select endpoint ───────────────────────────────────────────────────────

    function _apiSelectEndpoint(ep) {
        _apiCurrentEp    = ep;
        _apiParamValues  = {};

        // Mark active in tree
        document.querySelectorAll('.adb-api-tree-item').forEach(el => {
            el.classList.toggle('active', el.dataset.epId === ep.id);
        });

        // Method badge
        const badge = _apiEl('adb-api-method-badge');
        if (badge) {
            badge.textContent = ep.method;
            badge.className   = `adb-api-method-badge ${_apiBadgeClass(ep.method)}`;
        }

        // URL display — resolved via _apiCurrentDb()
        _apiUpdateUrlDisplay();

        // Endpoint description
        const descEl = _apiEl('adb-api-endpoint-desc');
        if (descEl) descEl.textContent = ep.desc || '';

        // Body pane
        const bodyEditor = _apiEl('adb-api-body-editor');
        if (bodyEditor) {
            const hasBody = ep.body !== null && ep.body !== undefined;
            bodyEditor.value    = hasBody ? JSON.stringify(ep.body, null, 2) : '';
            bodyEditor.disabled = !hasBody;
            bodyEditor.style.opacity = hasBody ? '1' : '0.35';
        }

        // Params pane — context-aware smart controls
        _apiRenderSmartParams(ep);

        // Enable send button — show "Preview" for destructive, "Send" for safe
        const sendBtn = _apiEl('adb-api-send-btn');
        if (sendBtn) {
            sendBtn.disabled = false;
            sendBtn.innerHTML = _apiIsDestructive(ep)
                ? '<i class="fas fa-shield-halved"></i> Preview'
                : '<i class="fas fa-play"></i> Send';
        }

        // Generate code for default lang
        _apiGenerateCode(_apiCurrentLang);
    }

    // ── Render params tab ─────────────────────────────────────────────────────

    function _apiRenderParams(ep) {
        const cont = _apiEl('adb-api-params-content');
        if (!cont) return;

        const pathParams  = ep.pathParams  || [];
        const queryParams = ep.params      || [];
        let   html        = '';

        if (pathParams.length) {
            html += `<div class="adb-api-params-group-label">Path Parameters</div>
            <table class="adb-api-params-table-inner">
                <thead><tr><th>Name</th><th>Value</th><th>Description</th></tr></thead>
                <tbody>
                ${pathParams.map(p => `<tr>
                    <td class="adb-api-param-name">{${p.n}}</td>
                    <td><input class="adb-api-small-input adb-api-path-param" data-param="${p.n}"
                        value="${p.v || ''}" placeholder="required" style="width:120px"></td>
                    <td class="adb-api-param-desc">Path param</td>
                </tr>`).join('')}
                </tbody>
            </table>`;
        }

        if (queryParams.length) {
            html += `<div class="adb-api-params-group-label" style="margin-top:0.6rem">Query Parameters</div>
            <table class="adb-api-params-table-inner">
                <thead><tr><th>Name</th><th>Value</th><th>Description</th></tr></thead>
                <tbody>
                ${queryParams.map(p => `<tr>
                    <td class="adb-api-param-name">${p.n}</td>
                    <td><input class="adb-api-small-input adb-api-query-param" data-param="${p.n}"
                        value="${p.v || ''}" placeholder="optional" style="width:120px"></td>
                    <td class="adb-api-param-desc">${p.d || ''}</td>
                </tr>`).join('')}
                </tbody>
            </table>`;
        }

        if (!pathParams.length && !queryParams.length) {
            html = '<div class="adb-empty-hint" style="padding:0.75rem">No parameters for this endpoint.</div>';
        }

        cont.innerHTML = html;

        // Wire param inputs
        cont.querySelectorAll('.adb-api-path-param, .adb-api-query-param').forEach(input => {
            input.addEventListener('input', () => {
                _apiParamValues[input.dataset.param] = input.value;
                _apiUpdateUrlDisplay();
                _apiGenerateCode(_apiCurrentLang);
            });
            _apiParamValues[input.dataset.param] = input.value;
        });
    }

    function _apiUpdateUrlDisplay() {
        if (!_apiCurrentEp) return;
        const ep  = _apiCurrentEp;
        const db  = _apiCurrentDb();
        const urlDisplay = _apiEl('adb-api-url-text');
        if (!urlDisplay) return;
        let path = ep.path.replace('{db}', db);
        for (const [k, v] of Object.entries(_apiParamValues)) {
            if (v) path = path.replace(`{${k}}`, v);
        }
        const html = (`${_API_V1}` + path)
            .replace(db, `<span class="adb-api-url-db">${db}</span>`)
            .replace(/\{([^}]+)\}/g, '<span class="adb-api-url-param">{$1}</span>');
        urlDisplay.innerHTML = html;
    }

    // ── Destructive-method check ──────────────────────────────────────────────

    const _DESTRUCTIVE = new Set(['PATCH', 'DELETE']);

    /** True when the current endpoint modifies or removes database data. */
    function _apiIsDestructive(ep) {
        return _DESTRUCTIVE.has(ep?.method);
    }

    // ── Send request ──────────────────────────────────────────────────────────

    async function _apiSend(force = false) {
        if (!_apiCurrentEp) return;
        const ep = _apiCurrentEp;

        // Gather params
        const pathValues  = {};
        const queryValues = {};
        document.querySelectorAll('.adb-api-path-param').forEach(i  => { pathValues[i.dataset.param]  = i.value; });
        document.querySelectorAll('.adb-api-query-param').forEach(i => { queryValues[i.dataset.param] = i.value; });

        const url = window.location.origin + _apiBuildUrl(ep, pathValues, queryValues);

        // Auth header
        const authVal = _apiEl('adb-api-auth-input')?.value?.trim() || '';
        const headers = { 'Content-Type': 'application/json' };
        if (authVal) headers['Authorization'] = authVal;

        // Body
        let body = undefined;
        if (['POST','PATCH','PUT'].includes(ep.method)) {
            const raw = _apiEl('adb-api-body-editor')?.value?.trim() || '';
            if (raw) {
                try { JSON.parse(raw); body = raw; } catch { _toast('Request body is not valid JSON.', 'error'); return; }
            }
        }

        // ── Dry-run guard for destructive methods ──
        if (!force && _apiIsDestructive(ep)) {
            _apiShowDryRun(ep, url, headers, body);
            _apiGenerateCode(_apiCurrentLang);
            return;
        }

        // Live send
        const sendBtn = _apiEl('adb-api-send-btn');
        if (sendBtn) { sendBtn.disabled = true; sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; }

        const t0 = performance.now();
        try {
            const res = await fetch(url, { method: ep.method, headers, body });
            const ms  = performance.now() - t0;
            const txt = await res.text();
            _apiLastRaw = txt;
            _apiShowResponse(res.status, ms, txt);
        } catch (err) {
            const ms = performance.now() - t0;
            _apiLastRaw = JSON.stringify({ error: err.message });
            _apiShowResponse(0, ms, _apiLastRaw);
        } finally {
            if (sendBtn) {
                const label = _apiIsDestructive(ep)
                    ? '<i class="fas fa-shield-halved"></i> Preview'
                    : '<i class="fas fa-play"></i> Send';
                sendBtn.disabled = false;
                sendBtn.innerHTML = label;
            }
        }

        _apiGenerateCode(_apiCurrentLang);
    }

    // ── Dry-run preview ───────────────────────────────────────────────────────

    function _apiShowDryRun(ep, url, headers, body) {
        const statusEl = _apiEl('adb-api-res-status');
        const timeEl   = _apiEl('adb-api-res-time');
        const sizeEl   = _apiEl('adb-api-res-size');
        const bodyEl   = _apiEl('adb-api-res-body');

        if (statusEl) {
            statusEl.textContent = '🛡 Dry Run';
            statusEl.className   = 'adb-api-res-status dry';
        }
        if (timeEl) timeEl.textContent = '— ms';
        if (sizeEl) sizeEl.textContent = '';

        const methodLabel  = ep.method;
        const isDelete     = ep.method === 'DELETE';
        const actionVerb   = isDelete ? 'delete' : 'mutate';

        // Build the dry-run body JSON to display
        const preview = {
            method:  ep.method,
            url,
            headers: { 'Content-Type': 'application/json', ...(headers.Authorization ? { Authorization: '***' } : {}) },
            ...(body ? { body: JSON.parse(body) } : {}),
        };

        _apiLastRaw = JSON.stringify(preview, null, 2);

        if (bodyEl) {
            bodyEl.innerHTML = `
                <div class="adb-api-dryrun-banner">
                    <i class="fas fa-shield-halved"></i>
                    <strong>Safe Mode — No changes were made.</strong>
                    This is a ${methodLabel} request that would ${actionVerb} database data.<br>
                    Review the request below, then click <strong>Execute</strong> to actually send it.
                    <button class="adb-api-dryrun-execute" id="adb-api-dryrun-execute-btn">
                        <i class="fas fa-bolt"></i> Execute Request
                    </button>
                </div>
                <pre class="adb-api-dryrun-preview">${_apiHighlightJson(_apiLastRaw)}</pre>`;

            _apiEl('adb-api-dryrun-execute-btn')?.addEventListener('click', () => _apiSend(true));
        }
    }

    // ── Show response ─────────────────────────────────────────────────────────

    function _apiShowResponse(status, ms, rawText) {
        const statusEl = _apiEl('adb-api-res-status');
        const timeEl   = _apiEl('adb-api-res-time');
        const sizeEl   = _apiEl('adb-api-res-size');
        const bodyEl   = _apiEl('adb-api-res-body');

        if (statusEl) {
            const ok = status >= 200 && status < 300;
            statusEl.textContent = status ? `● ${status}` : '● Error';
            statusEl.className   = `adb-api-res-status ${ok ? 'ok' : 'err'}`;
        }
        if (timeEl)  timeEl.textContent  = `${ms.toFixed(0)} ms`;
        if (sizeEl)  sizeEl.textContent  = _apiFmtBytes(new TextEncoder().encode(rawText).length);

        if (bodyEl) {
            try {
                const parsed = JSON.parse(rawText);
                const pretty = JSON.stringify(parsed, null, 2);
                bodyEl.innerHTML = _apiHighlightJson(pretty);
            } catch {
                bodyEl.textContent = rawText;
            }
        }
    }

    // ── Code generator ────────────────────────────────────────────────────────

    function _apiGenerateCode(lang) {
        _apiCurrentLang = lang;
        const out = _apiEl('adb-api-codegen-output');
        if (!out || !_apiCurrentEp) return;

        const ep = _apiCurrentEp;
        const pathValues  = {};
        const queryValues = {};
        document.querySelectorAll('.adb-api-path-param').forEach(i  => { pathValues[i.dataset.param]  = i.value; });
        document.querySelectorAll('.adb-api-query-param').forEach(i => { queryValues[i.dataset.param] = i.value; });

        const url        = window.location.origin + _apiBuildUrl(ep, pathValues, queryValues);
        const authVal    = _apiEl('adb-api-auth-input')?.value?.trim() || '';
        const bodyRaw    = _apiEl('adb-api-body-editor')?.value?.trim() || '';
        const hasBody    = ['POST','PATCH','PUT'].includes(ep.method) && bodyRaw;

        let code = '';

        if (lang === 'python') {
            code  = `import requests\n\n`;
            code += `url = "${url}"\n`;
            code += `headers = {\n    "Content-Type": "application/json",\n`;
            if (authVal) code += `    "Authorization": "${authVal}",\n`;
            code += `}\n`;
            if (hasBody) {
                code += `body = ${bodyRaw}\n\n`;
                code += `response = requests.${ep.method.toLowerCase()}(url, json=body, headers=headers)\n`;
            } else {
                code += `\nresponse = requests.${ep.method.toLowerCase()}(url, headers=headers)\n`;
            }
            code += `print(response.json())`;
        }

        else if (lang === 'javascript') {
            code  = `const response = await fetch("${url}", {\n`;
            code += `  method: "${ep.method}",\n`;
            code += `  headers: {\n    "Content-Type": "application/json",\n`;
            if (authVal) code += `    "Authorization": "${authVal}",\n`;
            code += `  },\n`;
            if (hasBody) code += `  body: JSON.stringify(${bodyRaw}),\n`;
            code += `});\nconst data = await response.json();\nconsole.log(data);`;
        }

        else if (lang === 'curl') {
            code  = `curl -X ${ep.method} "${url}" \\\n`;
            code += `  -H "Content-Type: application/json"`;
            if (authVal) code += ` \\\n  -H "Authorization: ${authVal}"`;
            if (hasBody) {
                const oneLine = bodyRaw.replace(/\n/g, ' ').replace(/  +/g, ' ');
                code += ` \\\n  -d '${oneLine}'`;
            }
        }

        _apiCodeRaw = code;
        out.textContent = code;

        // Sync tab active state
        document.querySelectorAll('.adb-api-codegen-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.lang === lang);
        });
    }

    // ── API Key management ────────────────────────────────────────────────────

    async function _apiLoadKeys() {
        const listEl = _apiEl('adb-apikey-list');
        if (!listEl) return;
        try {
            const res  = await fetch(`${_API_V1}/${_apiCurrentDb()}/keys`);
            if (!res.ok) { listEl.innerHTML = '<div class="adb-empty-hint">—</div>'; return; }
            const data = await res.json();
            const keys = data?.data?.keys || [];
            // Keep _apiDbKeys in sync for the {label} smart param picker
            _apiDbKeys = keys.map(k => k.label).filter(Boolean);
            if (!keys.length) {
                listEl.innerHTML = '<div class="adb-empty-hint" style="padding:0.4rem 0.5rem;font-size:0.75rem">No keys — open access</div>';
            } else {
                listEl.innerHTML = keys.map(k => `
                    <div class="adb-apikey-item">
                        <span class="adb-apikey-item-label" title="${k.created}">${k.label}</span>
                        <span class="adb-apikey-item-scope">${(k.scopes||[]).join('+')}</span>
                        <button class="adb-apikey-revoke-btn" data-label="${k.label}" title="Revoke">
                            <i class="fas fa-xmark"></i>
                        </button>
                    </div>`).join('');
                listEl.querySelectorAll('.adb-apikey-revoke-btn').forEach(btn => {
                    btn.addEventListener('click', () => _apiRevokeKey(btn.dataset.label));
                });
            }
        } catch {
            listEl.innerHTML = '<div class="adb-empty-hint">—</div>';
        }
    }

    async function _apiGenerateKey() {
        const label = (_apiEl('adb-apikey-label-input')?.value?.trim()) || 'default';
        try {
            const res  = await fetch(`${_API_V1}/${_apiCurrentDb()}/keys`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label, scopes: ['read', 'write'] }),
            });
            const data = await res.json();
            if (!res.ok || !data.data?.key) throw new Error(data.error?.message || 'Generate failed');

            const raw = data.data.key;

            // Show reveal box
            const reveal = _apiEl('adb-apikey-reveal');
            const valEl  = _apiEl('adb-apikey-reveal-value');
            if (valEl)  valEl.textContent = raw;
            if (reveal) reveal.classList.remove('hidden');

            // Hide form
            _apiEl('adb-apikey-new-form')?.classList.add('hidden');
            _apiEl('adb-apikey-label-input') && (_apiEl('adb-apikey-label-input').value = '');

            _apiLoadKeys();
        } catch (err) {
            _toast(`Key generation failed: ${err.message}`, 'error');
        }
    }

    async function _apiRevokeKey(label) {
        if (!confirm(`Revoke key "${label}"? This cannot be undone.`)) return;
        try {
            await fetch(`${_API_V1}/${_apiCurrentDb()}/keys/${encodeURIComponent(label)}`, { method: 'DELETE' });
            _apiLoadKeys();
            _toast(`Key "${label}" revoked.`, 'success');
        } catch (err) {
            _toast(`Revoke failed: ${err.message}`, 'error');
        }
    }

    // ── Request sub-tab switching ─────────────────────────────────────────────

    function _apiSwitchReqPane(pane) {
        ['body','params','headers'].forEach(p => {
            _apiEl(`adb-api-pane-${p}`)?.classList.toggle('hidden', p !== pane);
        });
        document.querySelectorAll('.adb-api-req-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.pane === pane);
        });
    }

    // ── Wire ──────────────────────────────────────────────────────────────────

    function _apiWire() {
        // Send button
        _apiEl('adb-api-send-btn')?.addEventListener('click', () => _apiSend());

        // Request sub-tabs
        document.querySelectorAll('.adb-api-req-tab').forEach(btn => {
            btn.addEventListener('click', () => _apiSwitchReqPane(btn.dataset.pane));
        });

        // Code gen tabs
        document.querySelectorAll('.adb-api-codegen-tab').forEach(btn => {
            btn.addEventListener('click', () => _apiGenerateCode(btn.dataset.lang));
        });

        // Copy response
        _apiEl('adb-api-res-copy-btn')?.addEventListener('click', () => {
            if (_apiLastRaw) {
                navigator.clipboard.writeText(_apiLastRaw).then(() => _toast('Response copied.', 'success'));
            }
        });

        // Copy code
        _apiEl('adb-api-code-copy-btn')?.addEventListener('click', () => {
            if (_apiCodeRaw) {
                navigator.clipboard.writeText(_apiCodeRaw).then(() => _toast('Code copied.', 'success'));
            }
        });

        // API key new button — show form
        _apiEl('adb-apikey-new-btn')?.addEventListener('click', () => {
            _apiEl('adb-apikey-new-form')?.classList.toggle('hidden');
            _apiEl('adb-apikey-reveal')?.classList.add('hidden');
        });
        _apiEl('adb-apikey-gen-btn')?.addEventListener('click', _apiGenerateKey);
        _apiEl('adb-apikey-cancel-btn')?.addEventListener('click', () => {
            _apiEl('adb-apikey-new-form')?.classList.add('hidden');
        });
        _apiEl('adb-apikey-reveal-copy')?.addEventListener('click', () => {
            const val = _apiEl('adb-apikey-reveal-value')?.textContent;
            if (val) navigator.clipboard.writeText(val).then(() => _toast('API key copied.', 'success'));
        });

        // Body editor → regenerate code on change
        _apiEl('adb-api-body-editor')?.addEventListener('input', () => {
            _apiGenerateCode(_apiCurrentLang);
        });

        // Auth input → regenerate code on change
        _apiEl('adb-api-auth-input')?.addEventListener('input', () => {
            _apiGenerateCode(_apiCurrentLang);
        });

        // ── DB selector bar ──
        _apiEl('adb-api-db-select')?.addEventListener('change', e => {
            _apiSetDb(e.target.value);
        });

        _apiEl('adb-api-db-refresh')?.addEventListener('click', () => {
            _apiLoadDatabases();
            _apiLoadDbContext();
        });

        // ── Entity picker ──
        _apiEl('adb-api-picker-close')?.addEventListener('click', _apiPickerClose);

        _apiEl('adb-api-picker-search')?.addEventListener('input', e => {
            clearTimeout(_apiPickerTimer);
            _apiPickerTimer = setTimeout(() => _apiPickerSearch(e.target.value), 280);
        });

        // Close picker on Escape
        _apiEl('adb-api-picker-search')?.addEventListener('keydown', e => {
            if (e.key === 'Escape') _apiPickerClose();
        });
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
        _el('adb-expand-btn')?.addEventListener('click', _toggleExpandDropdown);
        document.querySelectorAll('.adb-expand-option').forEach(opt => {
            opt.addEventListener('click', e => {
                e.stopPropagation();
                _smartExpand(parseInt(opt.dataset.min, 10));
            });
        });
        // Close dropdown when clicking anywhere outside it
        document.addEventListener('click', e => {
            if (_expandDdOpen && !_el('adb-expand-wrap')?.contains(e.target)) {
                _closeExpandDropdown();
            }
        });
        _el('adb-validate-btn')?.addEventListener('click', _validateAll);

        // Tab navigation
        document.querySelectorAll('.adb-nav-tab').forEach(btn => {
            btn.addEventListener('click', () => _switchTab(btn.dataset.tab));
        });

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

        // Bulk selection action bar
        _el('adb-bulk-clear')?.addEventListener('click', _clearSelection);
        _el('adb-bulk-expand')?.addEventListener('click', _bulkExpandStubs);
        _el('adb-bulk-delete')?.addEventListener('click', _bulkDelete);

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
        _graphWire();
        _fdWire();
        _vecWire();
        _bakeWire();
        _apiWire();
        _fetchModels();
        _loadCachedInfo();          // populate stats from AethvionDB.INFO instantly
        _fdCheckExistingJob();      // restore folder-distill progress view if a job exists
        _bakeCheckExisting();       // restore bake result panel if a bake exists
        _vecCheckExisting();        // restore vector status if a job exists
        _loadEntityList('all', 0);
    }

    document.addEventListener('panelLoaded', function (e) {
        if (e.detail?.tabName === 'aethviondb') init();
    });
})();
