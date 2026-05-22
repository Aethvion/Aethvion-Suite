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

    // ── Databases tab state ───────────────────────────────────────────────────
    let _dbmData    = [];            // raw list from last /databases fetch
    let _dbmSortCol = 'lastOpened'; // active sort column
    let _dbmSortDir = 'desc';       // 'asc' | 'desc'

    // ── Search state ──────────────────────────────────────────────────────────
    let _searchMode = 'keyword';    // 'keyword' | 'semantic'

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

    function _relTime(iso) {
        if (!iso) return null;
        try {
            const diff = Date.now() - new Date(iso).getTime();
            const m    = Math.floor(diff / 60000);
            if (m < 1)   return 'just now';
            if (m < 60)  return `${m}m ago`;
            const h = Math.floor(m / 60);
            if (h < 24)  return `${h}h ago`;
            const d = Math.floor(h / 24);
            if (d < 30)  return `${d}d ago`;
            return _fmtDate(iso);
        } catch { return _fmtDate(iso); }
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

    // ── HTML escaping ─────────────────────────────────────────────────────────

    function _escHtml(str) {
        return String(str ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function _escAttr(str) { return _escHtml(str); }

    // ── View switching ────────────────────────────────────────────────────────

    function _showEntityList() {
        _currentEntityId     = null;
        _currentEntityStatus = null;
        _show('adb-explorer-header');
        _show('adb-list-pane');
        _hide('adb-entity-detail');
        _hide('adb-deepen-preview');
        _hide('adb-validation-view');
    }

    function _showEntityDetail() {
        _hide('adb-list-pane');
        _show('adb-entity-detail');
        _hide('adb-deepen-preview');
        _hide('adb-validation-view');
    }

    function _showDeepenPreviewPanel() {
        _hide('adb-list-pane');
        _hide('adb-entity-detail');
        _hide('adb-validation-view');
        _show('adb-deepen-preview');
    }

    function _showValidation() {
        _hide('adb-explorer-header');
        _hide('adb-bulk-bar');
        _hide('adb-list-pane');
        _hide('adb-entity-detail');
        _hide('adb-deepen-preview');
        _show('adb-validation-view');
    }

    function _switchTab(tab) {
        _currentTab = tab;
        try { localStorage.setItem('adb_last_subtab', tab); } catch {}
        document.querySelectorAll('.adb-nav-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tab);
        });
        _el('adb-tab-pane-databases')?.classList.toggle('hidden', tab !== 'databases');
        _el('adb-tab-pane-tools')    ?.classList.toggle('hidden', tab !== 'tools');
        _el('adb-tab-pane-bake')     ?.classList.toggle('hidden', tab !== 'bake');
        _el('adb-tab-pane-explorer') ?.classList.toggle('hidden', tab !== 'explorer');
        _el('adb-tab-pane-graph')    ?.classList.toggle('hidden', tab !== 'graph');
        _el('adb-tab-pane-api')      ?.classList.toggle('hidden', tab !== 'api');
        _el('adb-tab-pane-test')     ?.classList.toggle('hidden', tab !== 'test');
        if (tab === 'databases') { _dbmView('adb-dbm-list'); _dbmLoadList(); }
        if (tab === 'bake') _bakeLoadList();
        if (tab === 'api')  { _apiRenderTree(); _apiLoadKeys(); }
        if (tab === 'tools') _testLoadChunks();
        if (tab === 'test') _testOnEnter();
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

    let _dbmSettingsName = null;   // name of DB currently shown in settings view

    function _dbmOpen() {
        _switchTab('databases');
    }

    function _dbmClose() {
        // No-op — databases is a full tab now; navigation uses _dbmView() / _switchTab()
    }

    /** Switch between the three tab views (list / create / settings). */
    function _dbmView(viewId) {
        ['adb-dbm-list', 'adb-dbm-create', 'adb-dbm-settings'].forEach(id => {
            const el = _el(id);
            if (el) el.classList.toggle('hidden', id !== viewId);
        });
    }

    // ── Databases table helpers ───────────────────────────────────────────────

    function _dbmGetAllLastOpened() {
        try { return JSON.parse(localStorage.getItem('adb_last_opened') || '{}'); }
        catch { return {}; }
    }

    function _dbmTrackOpened(name) {
        if (!name) return;
        try {
            const map = _dbmGetAllLastOpened();
            map[name] = new Date().toISOString();
            localStorage.setItem('adb_last_opened', JSON.stringify(map));
        } catch {}
    }

    function _dbmSortBy(col) {
        if (_dbmSortCol === col) {
            _dbmSortDir = _dbmSortDir === 'asc' ? 'desc' : 'asc';
        } else {
            _dbmSortCol = col;
            _dbmSortDir = col === 'name' ? 'asc' : 'desc';
        }
        _dbmRenderTable();
    }

    function _dbmRenderTable() {
        const tbody = _el('adb-dbm-tbody');
        if (!tbody) return;

        const loMap = _dbmGetAllLastOpened();
        const rows  = _dbmData.map(db => ({ ...db, lastOpened: loMap[db.name] || null }));

        // Sort — nulls/empty always last regardless of direction
        const col = _dbmSortCol;
        const dir = _dbmSortDir === 'asc' ? 1 : -1;
        rows.sort((a, b) => {
            let av, bv;
            switch (col) {
                case 'name':       av = a.name?.toLowerCase() || '';  bv = b.name?.toLowerCase() || '';  break;
                case 'entities':   av = a.entity_count ?? null;        bv = b.entity_count ?? null;        break;
                case 'size':       av = a.size_bytes   ?? null;        bv = b.size_bytes   ?? null;        break;
                case 'backups':    av = a.backup_count ?? null;        bv = b.backup_count ?? null;        break;
                case 'lastBackup': av = a.last_backup  || null;        bv = b.last_backup  || null;        break;
                case 'created':    av = a.created      || null;        bv = b.created      || null;        break;
                case 'updated':    av = a.last_updated || null;        bv = b.last_updated || null;        break;
                case 'lastOpened': av = a.lastOpened   || null;        bv = b.lastOpened   || null;        break;
                default:           av = null; bv = null;
            }
            if (av === null && bv === null) return 0;
            if (av === null) return 1;   // nulls always sink to bottom
            if (bv === null) return -1;
            if (av < bv) return -dir;
            if (av > bv) return  dir;
            return 0;
        });

        const isActive = db =>
            (!_currentPath && db.name === _currentDb) ||
            (_currentPath  && db.path === _currentPath);

        tbody.innerHTML = rows.map(db => {
            const active = isActive(db);
            const loRel  = _relTime(db.lastOpened);
            return `<tr class="adb-dbm-tr${active ? ' adb-dbm-tr-active' : ''}" data-name="${_escAttr(db.name)}">
                <td class="adb-dbm-td adb-dbm-td-icon">
                    <span class="adb-dbm-row-icon${active ? ' adb-dbm-row-icon-active' : ''}">
                        <i class="fas fa-database"></i>
                    </span>
                </td>
                <td class="adb-dbm-td adb-dbm-td-name">
                    <div class="adb-dbm-name-cell">
                        <span class="adb-dbm-name-text">
                            ${_escHtml(db.name)}
                            ${active ? '<span class="adb-dbm-active-badge">active</span>' : ''}
                            ${!db.path_exists ? '<span class="adb-dbm-warn-badge" title="Path not found on disk">missing</span>' : ''}
                        </span>
                        ${db.description ? `<span class="adb-dbm-name-desc">${_escHtml(db.description)}</span>` : ''}
                        <span class="adb-dbm-name-path" title="${_escAttr(db.path)}">${_escHtml(db.path)}</span>
                    </div>
                </td>
                <td class="adb-dbm-td adb-dbm-td-num">${db.entity_count != null ? _fmtNum(db.entity_count) : '<span class="adb-dbm-null">—</span>'}</td>
                <td class="adb-dbm-td adb-dbm-td-num">${db.size_bytes > 0 ? _fmtBytes(db.size_bytes) : '<span class="adb-dbm-null">—</span>'}</td>
                <td class="adb-dbm-td adb-dbm-td-num">${db.backup_count > 0 ? db.backup_count : '<span class="adb-dbm-null adb-dbm-null-dim">0</span>'}</td>
                <td class="adb-dbm-td adb-dbm-td-date">${db.last_backup  ? `<span title="${_escAttr(db.last_backup)}">${_relTime(db.last_backup)}</span>`   : '<span class="adb-dbm-null">—</span>'}</td>
                <td class="adb-dbm-td adb-dbm-td-date">${db.created      ? `<span title="${_escAttr(db.created)}">${_fmtDate(db.created)}</span>`           : '<span class="adb-dbm-null">—</span>'}</td>
                <td class="adb-dbm-td adb-dbm-td-date">${db.last_updated ? `<span title="${_escAttr(db.last_updated)}">${_relTime(db.last_updated)}</span>`  : '<span class="adb-dbm-null">—</span>'}</td>
                <td class="adb-dbm-td adb-dbm-td-date">${loRel           ? `<span title="${_escAttr(db.lastOpened)}">${loRel}</span>`                        : '<span class="adb-dbm-null">—</span>'}</td>
                <td class="adb-dbm-td adb-dbm-td-actions">
                    <div class="adb-dbm-row-actions">
                        <button class="adb-btn adb-btn-ghost adb-btn-xs adb-dbm-settings-btn" data-name="${_escAttr(db.name)}" title="Settings">
                            <i class="fas fa-cog"></i>
                        </button>
                        ${active
                            ? '<span class="adb-dbm-active-label">Active</span>'
                            : `<button class="adb-btn adb-btn-accent adb-btn-xs adb-dbm-switch-btn" data-name="${_escAttr(db.name)}">
                                   <i class="fas fa-right-to-bracket"></i> Switch
                               </button>`}
                    </div>
                </td>
            </tr>`;
        }).join('');

        // Update sort-header icons
        document.querySelectorAll('.adb-dbm-th-sortable').forEach(th => {
            const thCol = th.dataset.col;
            th.classList.toggle('adb-dbm-th-active', thCol === col);
            const icon = th.querySelector('.adb-dbm-sort-icon');
            if (icon) {
                icon.className = thCol === col
                    ? `adb-dbm-sort-icon fas fa-arrow-${_dbmSortDir === 'asc' ? 'up' : 'down'}`
                    : 'adb-dbm-sort-icon fas fa-sort';
            }
        });

        // Wire row action buttons
        tbody.querySelectorAll('.adb-dbm-switch-btn').forEach(btn => {
            btn.addEventListener('click', () => _switchToNamed(btn.dataset.name));
        });
        tbody.querySelectorAll('.adb-dbm-settings-btn').forEach(btn => {
            btn.addEventListener('click', () => _dbmShowSettings(btn.dataset.name));
        });
    }

    async function _dbmLoadList() {
        const listEl  = _el('adb-dbm-db-list');
        const countEl = _el('adb-dbm-tab-count');
        if (!listEl) return;
        listEl.innerHTML = '<div class="adb-empty-hint"><i class="fas fa-spinner fa-spin"></i></div>';
        try {
            const res  = await fetch(`${API}/databases`);
            const data = await res.json();
            const dbs  = data.databases || [];
            _dbmData   = dbs;

            if (countEl) countEl.textContent = dbs.length ? `${dbs.length} database${dbs.length !== 1 ? 's' : ''}` : '';

            if (!dbs.length) {
                listEl.innerHTML = '<div class="adb-empty-hint">No databases yet. Click <strong>New Database</strong> to create one.</div>';
                return;
            }

            // Column definitions
            const cols = [
                { col: null,          label: '',             sortable: false },
                { col: 'name',        label: 'Name',         sortable: true  },
                { col: 'entities',    label: 'Entities',     sortable: true  },
                { col: 'size',        label: 'Size',         sortable: true  },
                { col: 'backups',     label: 'Backups',      sortable: true  },
                { col: 'lastBackup',  label: 'Last Backup',  sortable: true  },
                { col: 'created',     label: 'Created',      sortable: true  },
                { col: 'updated',     label: 'Updated',      sortable: true  },
                { col: 'lastOpened',  label: 'Last Opened',  sortable: true  },
                { col: null,          label: 'Actions',      sortable: false },
            ];

            const theadHtml = `<thead><tr class="adb-dbm-tr-head">${cols.map(c => {
                if (!c.sortable) return `<th class="adb-dbm-th">${c.label}</th>`;
                const active = c.col === _dbmSortCol;
                const icon   = active
                    ? `fa-arrow-${_dbmSortDir === 'asc' ? 'up' : 'down'}`
                    : 'fa-sort';
                return `<th class="adb-dbm-th adb-dbm-th-sortable${active ? ' adb-dbm-th-active' : ''}" data-col="${c.col}">
                    ${c.label} <i class="adb-dbm-sort-icon fas ${icon}"></i>
                </th>`;
            }).join('')}</tr></thead>`;

            listEl.innerHTML = `<div class="adb-dbm-table-wrap">
                <table class="adb-dbm-table">
                    ${theadHtml}
                    <tbody id="adb-dbm-tbody"></tbody>
                </table>
            </div>`;

            // Wire sortable header clicks
            listEl.querySelectorAll('.adb-dbm-th-sortable').forEach(th => {
                th.addEventListener('click', () => _dbmSortBy(th.dataset.col));
            });

            _dbmRenderTable();

        } catch {
            listEl.innerHTML = '<div class="adb-empty-hint">Could not load databases.</div>';
        }
    }

    function _dbmShowCreate() {
        _dbmView('adb-dbm-create');
        const n = _el('adb-dbm-create-name'); if (n) { n.value = ''; setTimeout(() => n.focus(), 60); }
        const p = _el('adb-dbm-create-path'); if (p) p.value = '';
        const d = _el('adb-dbm-create-desc'); if (d) d.value = '';
    }

    async function _dbmCreate() {
        const name = _el('adb-dbm-create-name')?.value?.trim();
        const path = _el('adb-dbm-create-path')?.value?.trim() || null;
        const desc = _el('adb-dbm-create-desc')?.value?.trim() || '';

        if (!name) { _toast('Database name is required.', 'warning'); return; }

        const btn = _el('adb-dbm-create-submit');
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; }

        try {
            const res  = await fetch(`${API}/databases`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ name, path, description: desc }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Create failed');
            const verb = data.created ? 'created' : 'registered';
            _toast(`Database "${name}" ${verb}.`, 'success');
            _switchToNamed(name);
            // Stay on the databases tab, go back to list so user sees the new entry
            _dbmView('adb-dbm-list');
            _dbmLoadList();
        } catch (e) {
            _toast(e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-plus"></i> Create'; }
        }
    }

    async function _dbmBrowse(inputId) {
        const input   = _el(inputId);
        const initial = input?.value?.trim() || '';
        // Find the browse button nearest to the input
        const btn = input?.closest('.adb-db-path-row')?.querySelector('.adb-db-browse-btn');
        if (btn) { btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true; }
        try {
            const res  = await fetch(`${BROWSE_API}?initial=${encodeURIComponent(initial)}`);
            const data = await res.json();
            if (!data.cancelled && data.path && input) input.value = data.path;
        } catch {
            _toast('Could not open folder browser.', 'error');
        } finally {
            if (btn) { btn.innerHTML = '<i class="fas fa-folder-open"></i>'; btn.disabled = false; }
        }
    }

    async function _dbmShowSettings(name) {
        _dbmSettingsName = name;
        _dbmView('adb-dbm-settings');
        const title = _el('adb-dbm-settings-title');
        if (title) title.textContent = `${name} — Settings`;

        // Load registry metadata via list endpoint
        try {
            const res  = await fetch(`${API}/databases`);
            const data = await res.json();
            const db   = (data.databases || []).find(d => d.name === name);
            if (db) {
                const desc = _el('adb-dbm-settings-desc');
                if (desc) desc.value = db.description || '';
                const bkEnabled = _el('adb-dbm-backup-enabled');
                if (bkEnabled) bkEnabled.checked = db.backup?.enabled || false;
                const bkKeep = _el('adb-dbm-backup-keep');
                if (bkKeep) bkKeep.value = db.backup?.keep_count ?? 5;
            }
        } catch {
            _toast('Could not load database settings.', 'error');
        }

        _dbmLoadBackups(name);
    }

    async function _dbmSaveSettings() {
        const name = _dbmSettingsName;
        if (!name) return;

        const desc      = _el('adb-dbm-settings-desc')?.value?.trim() ?? '';
        const enabled   = _el('adb-dbm-backup-enabled')?.checked ?? false;
        const keepCount = parseInt(_el('adb-dbm-backup-keep')?.value || '5', 10);

        const btn = _el('adb-dbm-settings-save');
        if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }

        try {
            const res = await fetch(`${API}/databases/${encodeURIComponent(name)}/settings`, {
                method:  'PUT',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ description: desc, backup: { enabled, keep_count: keepCount } }),
            });
            if (!res.ok) throw new Error((await res.json()).detail || 'Save failed');
            _toast('Settings saved.', 'success');
        } catch (e) {
            _toast(e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Save Settings'; }
        }
    }

    async function _dbmCreateBackup() {
        const name = _dbmSettingsName;
        if (!name) return;
        const label = prompt('Backup label (optional):', '') ?? '';

        const btn = _el('adb-dbm-backup-now-btn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating…'; }

        try {
            const res  = await fetch(`${API}/databases/${encodeURIComponent(name)}/backup`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ label }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Backup failed');
            _toast(`Backup created: ${data.backup_id}`, 'success');
            _dbmLoadBackups(name);
        } catch (e) {
            _toast(e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-download"></i> Create Backup Now'; }
        }
    }

    async function _dbmLoadBackups(name) {
        const listEl = _el('adb-dbm-backup-list');
        if (!listEl) return;
        listEl.innerHTML = '<div class="adb-empty-hint"><i class="fas fa-spinner fa-spin"></i></div>';
        try {
            const res  = await fetch(`${API}/databases/${encodeURIComponent(name)}/backups`);
            const data = await res.json();
            const bks  = data.backups || [];

            if (!bks.length) {
                listEl.innerHTML = '<div class="adb-empty-hint">No backups yet.</div>';
                return;
            }

            listEl.innerHTML = bks.map(b => `
                <div class="adb-dbm-backup-row" data-bid="${_escAttr(b.backup_id)}">
                    <div class="adb-dbm-backup-info">
                        <span class="adb-dbm-backup-id">${_escHtml(b.backup_id)}</span>
                        ${b.label ? `<span class="adb-dbm-backup-label">${_escHtml(b.label)}</span>` : ''}
                        <span class="adb-dbm-backup-meta">${_fmtDate(b.created)} · ${b.entity_count} entities · ${_fmtBytes(b.size_bytes)}</span>
                    </div>
                    <div class="adb-dbm-backup-actions">
                        <button class="adb-btn adb-btn-ghost adb-btn-xs adb-dbm-restore-btn" data-bid="${_escAttr(b.backup_id)}" title="Restore this backup">
                            <i class="fas fa-undo"></i> Restore
                        </button>
                        <button class="adb-btn adb-btn-ghost adb-btn-xs adb-dbm-del-backup-btn" data-bid="${_escAttr(b.backup_id)}" title="Delete backup">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>`).join('');

            listEl.querySelectorAll('.adb-dbm-restore-btn').forEach(btn => {
                btn.addEventListener('click', () => _dbmRestoreBackup(name, btn.dataset.bid));
            });
            listEl.querySelectorAll('.adb-dbm-del-backup-btn').forEach(btn => {
                btn.addEventListener('click', () => _dbmDeleteBackup(name, btn.dataset.bid));
            });
        } catch {
            listEl.innerHTML = '<div class="adb-empty-hint">Could not load backups.</div>';
        }
    }

    async function _dbmRestoreBackup(name, bid) {
        if (!confirm(
            `Restore backup "${bid}"?\n\nThis replaces ALL current database contents. The current data will be lost.`
        )) return;

        _showBusy('Restoring backup…');
        try {
            const res  = await fetch(
                `${API}/databases/${encodeURIComponent(name)}/backups/${encodeURIComponent(bid)}/restore`,
                { method: 'POST' }
            );
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Restore failed');
            _toast(`Restored: ${data.entity_count} entities.`, 'success');
            // Reload entity list if this is the active database
            if (name === _currentDb) _loadEntityList(_currentFilter, _currentPage);
        } catch (e) {
            _toast(e.message, 'error');
        } finally {
            _hideBusy();
        }
    }

    async function _dbmDeleteBackup(name, bid) {
        if (!confirm(`Delete backup "${bid}"? This cannot be undone.`)) return;
        try {
            const res = await fetch(
                `${API}/databases/${encodeURIComponent(name)}/backups/${encodeURIComponent(bid)}`,
                { method: 'DELETE' }
            );
            if (!res.ok) throw new Error((await res.json()).detail || 'Delete failed');
            _toast('Backup deleted.', 'success');
            _dbmLoadBackups(name);
        } catch (e) {
            _toast(e.message, 'error');
        }
    }

    async function _dbmDeleteDatabase() {
        const name = _dbmSettingsName;
        if (!name) return;
        if (!confirm(`Delete database "${name}"?\n\nALL entity data will be permanently deleted from disk.`)) return;
        const typed = prompt(`Type "${name}" to confirm:`);
        if (typed !== name) { _toast('Deletion cancelled.', 'info'); return; }

        _showBusy('Deleting database…');
        try {
            const res = await fetch(
                `${API}/databases/${encodeURIComponent(name)}?confirm=true`,
                { method: 'DELETE' }
            );
            if (!res.ok) throw new Error((await res.json()).detail || 'Delete failed');
            _toast(`Database "${name}" deleted.`, 'success');
            if (name === _currentDb) _switchToNamed('default');
            _dbmView('adb-dbm-list');
            _dbmLoadList();
        } catch (e) {
            _toast(e.message, 'error');
        } finally {
            _hideBusy();
        }
    }

    // Keep legacy stubs so any other code that calls them doesn't break
    function _openDbModal()  { _dbmOpen(); }
    function _closeDbModal() { _dbmClose(); }
    async function _browseFolder() { await _dbmBrowse('adb-db-folder-input'); }
    function _openSelectedDb() {
        const path = _el('adb-db-folder-input')?.value?.trim();
        if (path) _switchToPath(path);
        _dbmClose();
    }

    function _switchToNamed(name) {
        _currentDb   = name;
        _currentPath = null;
        _dbmTrackOpened(name);
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

    /** Toggle between keyword and semantic (vector) search modes. */
    function _vsearchToggle() {
        _searchMode = _searchMode === 'keyword' ? 'semantic' : 'keyword';
        const btn  = _el('adb-vsearch-toggle');
        const sel  = _el('adb-vsearch-model');
        const inp  = _el('adb-search-input');
        const icon = _el('adb-search-mode-icon');
        const sem  = _searchMode === 'semantic';
        btn ?.classList.toggle('adb-vsearch-active', sem);
        sel ?.classList.toggle('hidden', !sem);
        if (icon) icon.className = sem ? 'fas fa-microchip adb-search-icon adb-search-icon-sem' : 'fas fa-search adb-search-icon';
        if (inp)  inp.placeholder = sem
            ? 'Describe what you\'re looking for — semantic / vector search…'
            : 'Search by name, summary, or tag…';
    }

    async function _search() {
        const q    = _el('adb-search-input')?.value?.trim() || '';
        const type = _el('adb-search-type')?.value || '';

        if (_searchMode === 'semantic') { await _searchSemantic(q); return; }

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
            listEl.innerHTML = `<div class="adb-empty-state"><i class="fas fa-exclamation-triangle"></i><p>Error: ${_escHtml(err.message)}</p></div>`;
        }
    }

    /**
     * Semantic / vector similarity search.
     * Calls POST /api/v1/{db}/raw/vectors/search — requires pre-generated embeddings.
     */
    async function _searchSemantic(q) {
        if (!q) { _loadEntityList(_currentFilter); return; }

        // v1 API operates on named databases, not arbitrary paths
        if (_currentPath) {
            _showEntityList();
            _hide('adb-entity-pagination');
            const listEl = _el('adb-entity-list');
            if (listEl) listEl.innerHTML = `<div class="adb-empty-state">
                <i class="fas fa-microchip"></i>
                <p>Vector search is only available for named databases.</p>
                <p class="adb-empty-sub">Switch to a named database via the <strong>Databases</strong> tab.</p>
            </div>`;
            return;
        }

        _showEntityList();
        _hide('adb-entity-pagination');
        const listEl = _el('adb-entity-list');
        if (!listEl) return;
        listEl.innerHTML = '<div class="adb-list-loading"><i class="fas fa-microchip fa-spin"></i> Embedding query…</div>';

        const db    = _currentDb;
        const model = _el('adb-vsearch-model')?.value || 'text-embedding-3-small';

        try {
            const res  = await fetch(`${_API_V1}/${encodeURIComponent(db)}/raw/vectors/search`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ query: q, model, top_k: 50, filters: {} }),
            });
            const data = await res.json();

            if (!res.ok) {
                const msg = data?.error?.message || data?.detail || 'Vector search failed';
                listEl.innerHTML = `<div class="adb-empty-state">
                    <i class="fas fa-exclamation-triangle"></i>
                    <p>${_escHtml(msg)}</p>
                </div>`;
                return;
            }

            const results = data?.data?.results || [];

            if (!results.length) {
                listEl.innerHTML = `<div class="adb-empty-state">
                    <i class="fas fa-microchip"></i>
                    <p>No vector matches found.</p>
                    <p class="adb-empty-sub">Generate embeddings first via
                        <strong>Tools → Vector Search</strong>,
                        then search here using the same model (<em>${_escHtml(model)}</em>).
                    </p>
                </div>`;
                return;
            }

            listEl.innerHTML = _renderVectorTable(results);
            _wireTableCheckboxes(results);
            _wireTableRows(listEl);

            const pagEl = _el('adb-entity-pagination');
            if (pagEl) {
                pagEl.classList.remove('hidden');
                pagEl.innerHTML = `<div class="adb-pag-info">${results.length} semantic match${results.length !== 1 ? 'es' : ''} · <span class="adb-pag-model">${_escHtml(model)}</span></div>`;
            }
        } catch (err) {
            listEl.innerHTML = `<div class="adb-empty-state"><i class="fas fa-exclamation-triangle"></i><p>Error: ${_escHtml(err.message)}</p></div>`;
        }
    }

    /** Render the entity table for vector search results (adds a Score column). */
    function _renderVectorTable(results) {
        return `<table class="adb-table">
            <colgroup>
                <col class="adb-col-check">
                <col class="adb-col-type">
                <col>
                <col class="adb-col-tags">
                <col class="adb-col-rel">
                <col class="adb-col-stubs">
                <col class="adb-col-score">
            </colgroup>
            <thead>
                <tr>
                    <th class="adb-col-check adb-th-check">
                        <input type="checkbox" id="adb-select-all" class="adb-row-check" title="Select all">
                    </th>
                    <th class="adb-col-type">Type</th>
                    <th>Name / Summary</th>
                    <th class="adb-col-tags">Tags</th>
                    <th class="adb-col-rel" title="Relations">Rel.</th>
                    <th class="adb-col-stubs" title="Sub-topics">Sub.</th>
                    <th class="adb-col-score" title="Cosine similarity score">Score</th>
                </tr>
            </thead>
            <tbody>
                ${results.map(e => _entityRowVectorHtml(e)).join('')}
            </tbody>
        </table>`;
    }

    /** Row renderer for vector search results — adds a score badge in the last column. */
    function _entityRowVectorHtml(e) {
        const isStub    = e.status === 'stub';
        const summary   = e.summary || '';
        const tags      = e.tags || [];
        const relCount  = e.relations_count != null ? e.relations_count : null;
        const checked   = _selectedIds.has(e.id);
        const scorePct  = e.score != null ? Math.round(e.score * 100) : null;

        const tagHtml = tags.slice(0, 3).map(t => `<span class="adb-tag-sm">${_escHtml(t)}</span>`).join('')
                      + (tags.length > 3 ? `<span class="adb-tag-sm">+${tags.length - 3}</span>` : '');

        const scoreCls = scorePct >= 80 ? 'adb-score-high'
                       : scorePct >= 55 ? 'adb-score-mid'
                       :                  'adb-score-low';

        return `<tr class="adb-tr${checked ? ' adb-tr-selected' : ''}" data-id="${_escAttr(e.id)}" data-stub="${isStub}" tabindex="0">
            <td class="adb-td adb-td-check">
                <input type="checkbox" class="adb-row-check" data-id="${_escAttr(e.id)}" ${checked ? 'checked' : ''}>
            </td>
            <td class="adb-td">
                <span class="adb-type-badge adb-type-${e.type || 'other'}">${_escHtml(e.type || 'other')}</span>
            </td>
            <td class="adb-td">
                <div class="adb-td-name-text">${_escHtml(e.name || e.id)}</div>
                ${summary ? `<div class="adb-td-summary">${_escHtml(summary)}</div>` : ''}
            </td>
            <td class="adb-td">
                <div class="adb-td-tags">${tagHtml}</div>
            </td>
            <td class="adb-td adb-td-num${relCount ? ' has-data' : ''}">${relCount ?? '—'}</td>
            <td class="adb-td adb-td-num">—</td>
            <td class="adb-td adb-td-score">
                ${scorePct != null ? `<span class="adb-score-badge ${scoreCls}">${scorePct}%</span>` : '—'}
            </td>
        </tr>`;
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

        // If we were in edit mode, clean up the DOM and reset button states
        if (_editingEntity) { _editingEntity = null; _exitEditDom(); }
        _show('adb-ev-edit-btn');
        _show('adb-ev-expand-btn');
        _hide('adb-ev-save-btn');
        _hide('adb-ev-cancel-btn');

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

    // ── Entity edit mode ──────────────────────────────────────────────────────

    let _editingEntity = null; // deep clone stored when edit mode is active

    const _VALID_TYPES = [
        'person','place','event','concept','organization','artifact',
        'creature','substance','process','phenomenon','work','species','universe','other',
    ];
    const _RELATION_KINDS = [
        'parent_of','child_of','member_of','contains','created_by','created',
        'located_in','location_of','part_of','has_part','preceded_by','followed_by',
        'related_to','instance_of','has_instance','influenced_by','influenced',
        'participated_in','has_participant',
    ];
    const _kindOptsHtml = _RELATION_KINDS.map(k => `<option value="${k}">${k}</option>`).join('');

    function _enterEditMode(entity) {
        _editingEntity = JSON.parse(JSON.stringify(entity));

        _hide('adb-ev-edit-btn');
        _hide('adb-ev-expand-btn');
        _show('adb-ev-save-btn');
        _show('adb-ev-cancel-btn');

        _renderEditHeader(entity);
        _renderEditCore(entity);
        _renderEditTimeline(entity);
        _renderEditRelations(entity);
        _renderEditProperties(entity);
        _renderEditStubs(entity);
    }

    /** Restore any DOM elements that were replaced/mutated during edit mode. */
    function _exitEditDom() {
        // type badge: select → span
        const typeSel = _el('adb-ev-type-badge');
        if (typeSel && typeSel.tagName === 'SELECT') {
            const span = document.createElement('span');
            span.id = 'adb-ev-type-badge';
            span.className = 'adb-type-badge';
            typeSel.replaceWith(span);
        }
        // summary: textarea → p
        const summaryTa = _el('adb-ev-summary');
        if (summaryTa && summaryTa.tagName === 'TEXTAREA') {
            const p = document.createElement('p');
            p.id        = 'adb-ev-summary';
            p.className = 'adb-ev-summary';
            summaryTa.replaceWith(p);
        }
        // status badge: select → span
        const statusSel = _el('adb-ev-status-badge');
        if (statusSel && statusSel.tagName === 'SELECT') {
            const span = document.createElement('span');
            span.id        = 'adb-ev-status-badge';
            span.className = 'adb-badge';
            statusSel.replaceWith(span);
        }
        // name: remove contentEditable
        const nameEl = _el('adb-ev-name');
        if (nameEl) {
            nameEl.contentEditable = 'false';
            nameEl.classList.remove('adb-edit-name');
        }
    }

    function _cancelEditMode() {
        if (!_editingEntity) return;
        const stored = _editingEntity;
        _editingEntity = null;
        _exitEditDom();
        _show('adb-ev-edit-btn');
        _show('adb-ev-expand-btn');
        _hide('adb-ev-save-btn');
        _hide('adb-ev-cancel-btn');
        _renderEntity(stored);
    }

    function _renderEditHeader(entity) {
        // Type badge → <select>
        const typeBadge = _el('adb-ev-type-badge');
        if (typeBadge) {
            const opts = _VALID_TYPES.map(t =>
                `<option value="${t}" ${t === (entity.type || 'other') ? 'selected' : ''}>${t}</option>`
            ).join('');
            const sel = document.createElement('select');
            sel.id        = 'adb-ev-type-badge';
            sel.className = 'adb-edit-type-select';
            sel.innerHTML = opts;
            typeBadge.replaceWith(sel);
        }

        // Name → contenteditable span
        const nameEl = _el('adb-ev-name');
        if (nameEl) {
            nameEl.contentEditable = 'true';
            nameEl.classList.add('adb-edit-name');
            nameEl.spellcheck = false;
        }

        // Summary → <textarea>
        const summaryEl = _el('adb-ev-summary');
        if (summaryEl) {
            const ta = document.createElement('textarea');
            ta.id        = 'adb-ev-summary';
            ta.className = 'adb-edit-summary';
            ta.rows      = 3;
            ta.value     = entity.sections?.core?.summary || '';
            summaryEl.replaceWith(ta);
        }

        // Status badge → <select>
        const statusEl = _el('adb-ev-status-badge');
        if (statusEl) {
            const sel = document.createElement('select');
            sel.id        = 'adb-ev-status-badge';
            sel.className = 'adb-badge adb-edit-status-select';
            sel.innerHTML = ['active','stub'].map(s =>
                `<option value="${s}" ${s === entity.status ? 'selected' : ''}>${s}</option>`
            ).join('');
            statusEl.replaceWith(sel);
        }
    }

    /* ── Tag editor (aliases / categories / tags) ── */

    function _renderTagEditor(id, label, items) {
        const chips = items.map(item =>
            `<span class="adb-edit-chip">${_escHtml(item)}<button class="adb-edit-chip-remove" title="Remove" type="button">×</button></span>`
        ).join('');
        return `
            <div class="adb-ev-section-label">${label}</div>
            <div class="adb-edit-tag-row" id="${id}">${chips}</div>
            <div class="adb-edit-tag-add">
                <input type="text" class="adb-edit-input adb-edit-tag-input" data-for="${id}" placeholder="Add…">
                <button class="adb-btn adb-btn-ghost adb-btn-xs adb-edit-tag-add-btn" data-for="${id}" type="button">+</button>
            </div>`;
    }

    function _wireTagEditor(container, id) {
        container.querySelectorAll('.adb-edit-chip-remove').forEach(btn =>
            btn.addEventListener('click', () => btn.closest('.adb-edit-chip')?.remove())
        );
        const addBtn = container.querySelector(`.adb-edit-tag-add-btn[data-for="${id}"]`);
        const input  = container.querySelector(`.adb-edit-tag-input[data-for="${id}"]`);
        const row    = container.querySelector(`#${id}`);
        if (!addBtn || !input || !row) return;
        const addTag = () => {
            const val = input.value.trim(); if (!val) return;
            const chip = document.createElement('span');
            chip.className = 'adb-edit-chip';
            chip.innerHTML = `${_escHtml(val)}<button class="adb-edit-chip-remove" title="Remove" type="button">×</button>`;
            chip.querySelector('.adb-edit-chip-remove').addEventListener('click', () => chip.remove());
            row.appendChild(chip);
            input.value = '';
        };
        addBtn.addEventListener('click', addTag);
        input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addTag(); } });
    }

    function _getTagEditorValues(container, id) {
        return Array.from(container.querySelectorAll(`#${id} .adb-edit-chip`))
            .map(chip => chip.childNodes[0]?.textContent?.trim() || '')
            .filter(Boolean);
    }

    function _renderEditCore(entity) {
        const core   = entity.sections?.core || {};
        const aliasEl = _el('adb-ev-aliases');
        const catEl   = _el('adb-ev-categories');
        const tagEl   = _el('adb-ev-tags');
        if (aliasEl) { aliasEl.innerHTML = _renderTagEditor('adb-edit-aliases',    'Aliases',     core.aliases    || []); _wireTagEditor(aliasEl, 'adb-edit-aliases');    }
        if (catEl)   { catEl.innerHTML   = _renderTagEditor('adb-edit-categories', 'Categories',  core.categories || []); _wireTagEditor(catEl,   'adb-edit-categories'); }
        if (tagEl)   { tagEl.innerHTML   = _renderTagEditor('adb-edit-tags',       'Tags',        core.tags       || []); _wireTagEditor(tagEl,   'adb-edit-tags');       }
    }

    /* ── Timeline editor ── */

    function _tlRow(ev) {
        return `<div class="adb-edit-tl-row">
            <input class="adb-edit-input adb-edit-tl-date"  type="text" placeholder="YYYY or YYYY-MM-DD" value="${_escAttr(ev.date  || '')}">
            <input class="adb-edit-input adb-edit-tl-event" type="text" placeholder="Event description"  value="${_escAttr(ev.event || '')}">
            <button class="adb-edit-remove-btn" title="Remove" type="button">×</button>
        </div>`;
    }

    function _wireTimelineEditor(tlEl) {
        tlEl.querySelector('#adb-edit-tl-add')?.addEventListener('click', () => {
            const rows = tlEl.querySelector('#adb-edit-tl-rows');
            const div  = document.createElement('div');
            div.className = 'adb-edit-tl-row';
            div.innerHTML = `
                <input class="adb-edit-input adb-edit-tl-date"  type="text" placeholder="YYYY or YYYY-MM-DD">
                <input class="adb-edit-input adb-edit-tl-event" type="text" placeholder="Event description">
                <button class="adb-edit-remove-btn" title="Remove" type="button">×</button>`;
            div.querySelector('.adb-edit-remove-btn').addEventListener('click', () => div.remove());
            rows?.appendChild(div);
        });
        tlEl.querySelectorAll('#adb-edit-tl-rows .adb-edit-remove-btn').forEach(btn =>
            btn.addEventListener('click', () => btn.closest('.adb-edit-tl-row')?.remove())
        );
    }

    function _renderEditTimeline(entity) {
        const tlEl = _el('adb-ev-timeline-list');
        if (!tlEl) return;
        tlEl.innerHTML = `
            <div class="adb-edit-tl-list" id="adb-edit-tl-rows">
                ${(entity.sections?.timeline || []).map(_tlRow).join('')}
            </div>
            <button class="adb-btn adb-btn-ghost adb-btn-sm adb-edit-add-btn" id="adb-edit-tl-add" type="button">
                <i class="fas fa-plus"></i> Add Event
            </button>`;
        _wireTimelineEditor(tlEl);
    }

    /* ── Relations editor ── */

    function _relRow(rel) {
        const opts = _RELATION_KINDS.map(k =>
            `<option value="${k}" ${k === (rel.kind || 'related_to') ? 'selected' : ''}>${k}</option>`
        ).join('');
        return `<div class="adb-edit-rel-row">
            <select class="adb-edit-input adb-edit-rel-kind">${opts}</select>
            <input class="adb-edit-input adb-edit-rel-target" type="text" placeholder="Entity name…"
                   value="" data-entity-id="${_escAttr(rel.target_id || '')}">
            <input class="adb-edit-input adb-edit-rel-note" type="text" placeholder="Note (optional)"
                   value="${_escAttr(rel.note || '')}">
            <button class="adb-edit-remove-btn" title="Remove" type="button">×</button>
        </div>`;
    }

    function _wireRelEditor(relEl) {
        relEl.querySelector('#adb-edit-rel-add')?.addEventListener('click', () => {
            const rows = relEl.querySelector('#adb-edit-rel-rows');
            const div  = document.createElement('div');
            div.className = 'adb-edit-rel-row';
            div.innerHTML = `
                <select class="adb-edit-input adb-edit-rel-kind">${_kindOptsHtml}</select>
                <input class="adb-edit-input adb-edit-rel-target" type="text" placeholder="Entity name…" data-entity-id="">
                <input class="adb-edit-input adb-edit-rel-note"   type="text" placeholder="Note (optional)">
                <button class="adb-edit-remove-btn" title="Remove" type="button">×</button>`;
            div.querySelector('.adb-edit-remove-btn').addEventListener('click', () => div.remove());
            div.querySelector('.adb-edit-rel-target').addEventListener('input', function () { this.dataset.entityId = ''; });
            rows?.appendChild(div);
        });
        relEl.querySelectorAll('#adb-edit-rel-rows .adb-edit-remove-btn').forEach(btn =>
            btn.addEventListener('click', () => btn.closest('.adb-edit-rel-row')?.remove())
        );
        relEl.querySelectorAll('.adb-edit-rel-target').forEach(inp =>
            inp.addEventListener('input', function () { this.dataset.entityId = ''; })
        );
    }

    function _renderEditRelations(entity) {
        const relEl = _el('adb-ev-relations-list');
        if (!relEl) return;
        relEl.innerHTML = `
            <div class="adb-edit-rel-list" id="adb-edit-rel-rows">
                ${(entity.sections?.relations || []).map(_relRow).join('')}
            </div>
            <button class="adb-btn adb-btn-ghost adb-btn-sm adb-edit-add-btn" id="adb-edit-rel-add" type="button">
                <i class="fas fa-plus"></i> Add Relation
            </button>`;
        _wireRelEditor(relEl);
        // Async: resolve target IDs to display names
        relEl.querySelectorAll('.adb-edit-rel-target').forEach(inp => {
            const tid = inp.dataset.entityId;
            if (!tid) return;
            fetch(`${API}/entities/${tid}?${_dbParam()}`)
                .then(r => r.ok ? r.json() : null)
                .then(ent => { if (ent) inp.value = ent.name; })
                .catch(() => {});
        });
    }

    /* ── Properties editor ── */

    function _propRow(k, v) {
        return `<div class="adb-edit-prop-row">
            <input class="adb-edit-input adb-edit-prop-key" type="text" placeholder="key"   value="${_escAttr(k)}">
            <input class="adb-edit-input adb-edit-prop-val" type="text" placeholder="value" value="${_escAttr(v)}">
            <button class="adb-edit-remove-btn" title="Remove" type="button">×</button>
        </div>`;
    }

    function _wirePropEditor(propEl) {
        propEl.querySelector('#adb-edit-prop-add')?.addEventListener('click', () => {
            const rows = propEl.querySelector('#adb-edit-prop-rows');
            const div  = document.createElement('div');
            div.className = 'adb-edit-prop-row';
            div.innerHTML = `
                <input class="adb-edit-input adb-edit-prop-key" type="text" placeholder="key">
                <input class="adb-edit-input adb-edit-prop-val" type="text" placeholder="value">
                <button class="adb-edit-remove-btn" title="Remove" type="button">×</button>`;
            div.querySelector('.adb-edit-remove-btn').addEventListener('click', () => div.remove());
            rows?.appendChild(div);
        });
        propEl.querySelectorAll('.adb-edit-remove-btn').forEach(btn =>
            btn.addEventListener('click', () => btn.closest('.adb-edit-prop-row')?.remove())
        );
    }

    function _renderEditProperties(entity) {
        const propEl = _el('adb-ev-props-table');
        if (!propEl) return;
        const entries = Object.entries(entity.sections?.properties || {});
        propEl.innerHTML = `
            <div class="adb-edit-prop-list" id="adb-edit-prop-rows">
                ${entries.map(([k, v]) => _propRow(k, v)).join('')}
            </div>
            <button class="adb-btn adb-btn-ghost adb-btn-sm adb-edit-add-btn" id="adb-edit-prop-add" type="button">
                <i class="fas fa-plus"></i> Add Property
            </button>`;
        _wirePropEditor(propEl);
    }

    /* ── Stubs editor ── */

    function _stubRow(s) {
        return `<div class="adb-edit-stub-row">
            <i class="fas fa-circle-half-stroke"></i>
            <input class="adb-edit-input adb-edit-stub-name" type="text" value="${_escAttr(s)}">
            <button class="adb-edit-remove-btn" title="Remove" type="button">×</button>
        </div>`;
    }

    function _wireStubEditor(stubEl) {
        stubEl.querySelector('#adb-edit-stub-add')?.addEventListener('click', () => {
            const rows = stubEl.querySelector('#adb-edit-stub-rows');
            const div  = document.createElement('div');
            div.className = 'adb-edit-stub-row';
            div.innerHTML = `
                <i class="fas fa-circle-half-stroke"></i>
                <input class="adb-edit-input adb-edit-stub-name" type="text" placeholder="Sub-topic name">
                <button class="adb-edit-remove-btn" title="Remove" type="button">×</button>`;
            div.querySelector('.adb-edit-remove-btn').addEventListener('click', () => div.remove());
            rows?.appendChild(div);
        });
        stubEl.querySelectorAll('.adb-edit-remove-btn').forEach(btn =>
            btn.addEventListener('click', () => btn.closest('.adb-edit-stub-row')?.remove())
        );
    }

    function _renderEditStubs(entity) {
        const stubEl = _el('adb-ev-stubs-list');
        if (!stubEl) return;
        stubEl.innerHTML = `
            <div class="adb-edit-stub-list" id="adb-edit-stub-rows">
                ${(entity.sections?.stubs || []).map(_stubRow).join('')}
            </div>
            <button class="adb-btn adb-btn-ghost adb-btn-sm adb-edit-add-btn" id="adb-edit-stub-add" type="button">
                <i class="fas fa-plus"></i> Add Sub-topic
            </button>`;
        _wireStubEditor(stubEl);
    }

    /* ── Collect & save ── */

    async function _saveEdit() {
        if (!_currentEntityId) return;
        const btn = _el('adb-ev-save-btn');
        if (btn) btn.disabled = true;

        try {
            const nameEl    = _el('adb-ev-name');
            const typeSel   = _el('adb-ev-type-badge');
            const statusSel = _el('adb-ev-status-badge');
            const summaryEl = _el('adb-ev-summary');

            const name   = nameEl?.textContent?.trim() || _editingEntity?.name || '';
            const type   = typeSel?.value              || _editingEntity?.type  || 'other';
            const status = statusSel?.value             || _editingEntity?.status || 'active';
            const summary = summaryEl?.value?.trim()   || '';

            const aliasEl    = _el('adb-ev-aliases');
            const catEl      = _el('adb-ev-categories');
            const tagEl      = _el('adb-ev-tags');
            const aliases    = aliasEl ? _getTagEditorValues(aliasEl, 'adb-edit-aliases')    : [];
            const categories = catEl   ? _getTagEditorValues(catEl,   'adb-edit-categories') : [];
            const tags       = tagEl   ? _getTagEditorValues(tagEl,   'adb-edit-tags')       : [];

            // Timeline
            const timeline = [];
            document.querySelectorAll('#adb-edit-tl-rows .adb-edit-tl-row').forEach(row => {
                const date  = row.querySelector('.adb-edit-tl-date')?.value?.trim();
                const event = row.querySelector('.adb-edit-tl-event')?.value?.trim();
                if (date && event) timeline.push({ date, event });
            });

            // Properties
            const properties = {};
            document.querySelectorAll('#adb-edit-prop-rows .adb-edit-prop-row').forEach(row => {
                const k = row.querySelector('.adb-edit-prop-key')?.value?.trim();
                const v = row.querySelector('.adb-edit-prop-val')?.value?.trim();
                if (k) properties[k] = v || '';
            });

            // Stubs
            const stubs = [];
            document.querySelectorAll('#adb-edit-stub-rows .adb-edit-stub-row').forEach(row => {
                const n = row.querySelector('.adb-edit-stub-name')?.value?.trim();
                if (n) stubs.push(n);
            });

            // Relations — resolve target names to IDs
            const relations = [];
            for (const row of document.querySelectorAll('#adb-edit-rel-rows .adb-edit-rel-row')) {
                const kind      = row.querySelector('.adb-edit-rel-kind')?.value || 'related_to';
                const targetInp = row.querySelector('.adb-edit-rel-target');
                const note      = row.querySelector('.adb-edit-rel-note')?.value?.trim() || '';
                if (!targetInp) continue;

                let target_id  = targetInp.dataset.entityId || '';
                const targetName = targetInp.value?.trim();
                if (!target_id && targetName) {
                    try {
                        const r   = await fetch(`${API}/lookup?${_dbParam({ name: targetName })}`);
                        const ent = r.ok ? await r.json() : null;
                        if (ent) target_id = ent.id;
                    } catch {}
                }
                if (!target_id && targetName) {
                    try {
                        const r = await fetch(`${API}/entities?${_dbParam()}`, {
                            method:  'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body:    JSON.stringify({ name: targetName, entity_type: 'other', source: 'manual' }),
                        });
                        const created = r.ok ? await r.json() : null;
                        if (created?.entity) target_id = created.entity.id;
                    } catch {}
                }
                if (target_id) {
                    const rel = { kind, target_id };
                    if (note) rel.note = note;
                    relations.push(rel);
                }
            }

            const mutations = {
                name, type, status,
                sections: { core: { summary, aliases, categories, tags }, timeline, relations, properties, stubs },
            };

            const res  = await fetch(
                `${API}/entities/${_currentEntityId}?${_dbParam()}&replace_sections=true`, {
                    method:  'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body:    JSON.stringify({ mutations }),
                }
            );
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Save failed');

            _editingEntity = null;
            _exitEditDom();
            _show('adb-ev-edit-btn');
            _show('adb-ev-expand-btn');
            _hide('adb-ev-save-btn');
            _hide('adb-ev-cancel-btn');
            _renderEntity(data);
            _toast('Entity saved ✓', 'success');
            _loadEntityList(_currentFilter, _currentPage);
        } catch (e) {
            _toast(`Save failed: ${e.message}`, 'error');
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    // ── Deepen preview ────────────────────────────────────────────────────────

    function _onDpBack() {
        _hide('adb-deepen-preview');
        _showEntityDetail();
    }

    function _renderPreviewCard(name, proposed, idx, selectable) {
        const p = proposed || {};
        const checkHtml = selectable
            ? `<input type="checkbox" class="adb-dp-check" data-idx="${idx}" checked>`
            : '';
        return `<label class="adb-dp-card${selectable ? ' adb-dp-card-selectable' : ''}">
            ${checkHtml}
            <div class="adb-dp-card-body">
                <div class="adb-dp-card-header">
                    <span class="adb-type-badge adb-type-${p.type || 'other'}">${p.type || 'other'}</span>
                    <span class="adb-dp-card-name">${_escHtml(name)}</span>
                </div>
                <p class="adb-dp-summary">${_escHtml(p.summary || '(No summary generated)')}</p>
                ${p.aliases?.length
                    ? `<div class="adb-dp-row"><span class="adb-dp-label">Aliases:</span> ${p.aliases.map(a => `<span class="adb-tag">${_escHtml(a)}</span>`).join(' ')}</div>`
                    : ''}
                ${p.tags?.length
                    ? `<div class="adb-dp-row"><span class="adb-dp-label">Tags:</span> ${p.tags.map(t => `<span class="adb-tag adb-tag-accent">${_escHtml(t)}</span>`).join(' ')}</div>`
                    : ''}
                ${p.relations?.length
                    ? `<div class="adb-dp-row"><span class="adb-dp-label">Relations:</span> ${p.relations.map(r => `<span class="adb-rel-kind">${_escHtml(r.kind || 'related_to')}</span> ${_escHtml(r.target_name || '')}`).join(', ')}</div>`
                    : ''}
                ${p.stubs?.length
                    ? `<div class="adb-dp-row"><span class="adb-dp-label">New sub-topics:</span> ${p.stubs.map(s => `<span class="adb-tag">${_escHtml(s)}</span>`).join(' ')}</div>`
                    : ''}
            </div>
        </label>`;
    }

    function _showExpandPreview(data) {
        const titleEl   = _el('adb-dp-title');
        const contentEl = _el('adb-dp-content');
        if (!titleEl || !contentEl) return;

        titleEl.textContent = `Preview: ${data.entity_name}`;
        contentEl.innerHTML = `
            <div class="adb-dp-description">
                Review the proposed expansion for <strong>${_escHtml(data.entity_name)}</strong>.
                Nothing will be written until you click <strong>Apply Selected</strong>.
            </div>
            ${_renderPreviewCard(data.entity_name, data.proposed, 0, false)}`;

        const applyBtn = _el('adb-dp-apply-btn');
        if (applyBtn) {
            applyBtn.dataset.mode    = 'expand';
            applyBtn.dataset.payload = JSON.stringify({ proposed: data.proposed });
        }
        _el('adb-dp-back')?.addEventListener('click', _onDpBack, { once: true });
        _showDeepenPreviewPanel();
    }

    function _showDeepenPreview(data) {
        const titleEl   = _el('adb-dp-title');
        const contentEl = _el('adb-dp-content');
        if (!titleEl || !contentEl) return;

        const allPreviews = data.previews || [];
        const ok  = allPreviews.filter(p => !p.error);
        const bad = allPreviews.filter(p =>  p.error);

        titleEl.textContent = `Sub-topic Preview — ${data.entity_name}`;
        const goodCards = ok.map((preview, i) => _renderPreviewCard(preview.name, preview.proposed, i, true)).join('');
        const errCards  = bad.map(p => `
            <div class="adb-dp-card adb-dp-card-error">
                <div class="adb-dp-card-header">
                    <span class="adb-dp-card-name">${_escHtml(p.name)}</span>
                    <span class="adb-badge adb-badge-stub">Error</span>
                </div>
                <p class="adb-dp-error">${_escHtml(p.error)}</p>
            </div>`).join('');

        contentEl.innerHTML = `
            <div class="adb-dp-description">
                ${ok.length} sub-topic${ok.length !== 1 ? 's' : ''} previewed for <strong>${_escHtml(data.entity_name)}</strong>.
                Uncheck any you don't want to apply.
            </div>
            ${goodCards}${errCards}`;

        const applyBtn = _el('adb-dp-apply-btn');
        if (applyBtn) {
            applyBtn.dataset.mode    = 'deepen';
            applyBtn.dataset.payload = JSON.stringify({ previews: data.previews });
        }
        _el('adb-dp-back')?.addEventListener('click', _onDpBack, { once: true });
        _showDeepenPreviewPanel();
    }

    async function _applyDeepenPreview() {
        const applyBtn = _el('adb-dp-apply-btn');
        if (!applyBtn || !_currentEntityId) return;

        const mode    = applyBtn.dataset.mode;
        const payload = JSON.parse(applyBtn.dataset.payload || '{}');

        applyBtn.disabled = true;
        _showBusy('Applying…');

        try {
            if (mode === 'expand') {
                const res  = await fetch(`${API}/entities/${_currentEntityId}/expand/apply?${_dbParam()}`, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body:    JSON.stringify({ proposed: payload.proposed }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Apply failed');
                const newStubs = data.new_stubs?.length || 0;
                _toast(`Expanded ✓${newStubs ? ` — ${newStubs} new sub-topics found` : ''}`, 'success');
            } else {
                const allPrev = payload.previews || [];
                const checks  = Array.from(document.querySelectorAll('.adb-dp-check'));
                const selected = checks
                    .filter(c => c.checked)
                    .map(c => allPrev[parseInt(c.dataset.idx)])
                    .filter(p => p && !p.error);

                if (!selected.length) {
                    _toast('No items selected', 'info');
                    applyBtn.disabled = false;
                    _hideBusy();
                    return;
                }
                const res  = await fetch(`${API}/entities/${_currentEntityId}/deepen/apply?${_dbParam()}`, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body:    JSON.stringify({ previews: selected }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Apply failed');
                const n = data.applied?.length || 0;
                const f = data.failed?.length  || 0;
                if (f > 0) {
                    _toast(`Applied ${n}, ${f} failed`, 'error');
                    console.warn('[AethvionDB] Deepen apply failures:', data.failed);
                } else {
                    _toast(`Applied ${n} sub-topic${n !== 1 ? 's' : ''} ✓`, 'success');
                }
            }

            _hide('adb-deepen-preview');
            await _loadEntity(_currentEntityId);
            _loadEntityList(_currentFilter, _currentPage);
        } catch (e) {
            _toast(`Apply failed: ${e.message}`, 'error');
        } finally {
            applyBtn.disabled = false;
            _hideBusy();
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
            // Stub entity: preview expanding it (non-destructive)
            _showBusy('Generating expansion preview…');
            try {
                const model = _selectedModel();
                const res  = await fetch(
                    `${API}/entities/${_currentEntityId}/expand/preview?${_dbParam(model ? { model } : {})}`,
                    { method: 'POST' }
                );
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Preview failed');
                _hideBusy();
                _showExpandPreview(data);
            } catch (e) {
                _hideBusy();
                _toast(`Preview failed: ${e.message}`, 'error');
            }
        } else {
            // Active entity: preview deepening sub-topics (non-destructive)
            _showBusy('Generating deepen preview…');
            try {
                const model = _selectedModel();
                const res  = await fetch(
                    `${API}/entities/${_currentEntityId}/deepen/preview?${_dbParam({ max_stubs: 5, ...(model ? { model } : {}) })}`,
                    { method: 'POST' }
                );
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Preview failed');
                _hideBusy();
                if (!data.previews?.length) {
                    _toast('No sub-topics to preview (add some in the Stubs tab first)', 'info');
                    return;
                }
                _showDeepenPreview(data);
            } catch (e) {
                _hideBusy();
                _toast(`Preview failed: ${e.message}`, 'error');
            }
        }
    }

    // ── Validation ────────────────────────────────────────────────────────────

    async function _validateAll() {
        _showBusy('Running integrity checks…');
        try {
            const res  = await fetch(`${API}/validate?${_dbParam()}`);
            const data = await res.json();
            _showValidation();

            const mismatches       = data.stub_mismatches       || [];
            const dupGroups        = data.duplicate_groups       || [];
            const errEntities      = data.entities_with_errors   || [];
            const warnSummary      = data.warning_summary        || [];
            const orphanStubs      = data.orphan_stubs           || [];
            const deletedEntities  = data.deleted_entities       || [];
            const autoGroups       = dupGroups.filter(g => g.action === 'auto');
            const stubDupGroups    = dupGroups.filter(g => g.action === 'stub_auto');
            const chooseGroups     = dupGroups.filter(g => g.action === 'choose');
            const timelineWarn     = warnSummary.find(w => w.check === 'temporal');
            const timelineCount    = timelineWarn ? timelineWarn.count : 0;

            // ── Control panel (overview + fix toggles) ───────────────────────
            const sumEl = _el('adb-val-summary');
            if (sumEl) {
                const chips = [
                    { icon: 'fa-check-circle',         cls: 'ok',   val: data.clean ?? 0,          label: 'clean' },
                    { icon: 'fa-exclamation-circle',   cls: 'err',  val: data.with_errors ?? 0,    label: 'with errors' },
                    { icon: 'fa-triangle-exclamation', cls: 'warn', val: data.total_warnings ?? 0, label: 'warnings' },
                    ...(dupGroups.length   ? [{ icon: 'fa-copy',      cls: 'dup',  val: dupGroups.length,   label: `duplicate group${dupGroups.length !== 1 ? 's' : ''}` }] : []),
                    ...(mismatches.length  ? [{ icon: 'fa-tag',       cls: 'warn', val: mismatches.length,  label: `status mismatch${mismatches.length !== 1 ? 'es' : ''}` }] : []),
                    ...(orphanStubs.length    ? [{ icon: 'fa-link-slash', cls: 'warn', val: orphanStubs.length,    label: `orphan stub${orphanStubs.length !== 1 ? 's' : ''}` }] : []),
                    ...(deletedEntities.length ? [{ icon: 'fa-trash',      cls: 'del',  val: deletedEntities.length, label: `deleted file${deletedEntities.length !== 1 ? 's' : ''} on disk` }] : []),
                ];

                // Build fix-toggle rows — one per auto-fixable action type
                const fixRows = [];
                if (autoGroups.length)    fixRows.push({ id: 'adb-vfix-dups',      label: 'Auto-fix clear-winner duplicates', desc: 'keeps the active entity, removes stubs, updates all refs',             count: autoGroups.length });
                if (stubDupGroups.length) fixRows.push({ id: 'adb-vfix-stub-dups', label: 'Fix duplicate stubs',              desc: 'removes lower-ranked stub, updates referenced IDs',                   count: stubDupGroups.length });
                if (orphanStubs.length)      fixRows.push({ id: 'adb-vfix-orphans',   label: 'Remove orphan stubs',              desc: 'marks as deleted (files remain on disk — use Purge to fully remove)', count: orphanStubs.length });
                if (deletedEntities.length) fixRows.push({ id: 'adb-vfix-purge',    label: 'Purge deleted files',              desc: 'permanently removes soft-deleted files from disk — irreversible',     count: deletedEntities.length });
                if (mismatches.length)      fixRows.push({ id: 'adb-vfix-mm',       label: 'Promote status mismatches',        desc: 'stub with non-empty summary → mark as active',                        count: mismatches.length });
                if (timelineCount)          fixRows.push({ id: 'adb-vfix-timeline', label: 'Sort timeline events',             desc: 'orders events chronologically, unparseable dates moved to end',       count: timelineCount });

                const fixBox = fixRows.length ? `
                    <div class="adb-val-fixbox">
                        <div class="adb-val-fixbox-title"><i class="fas fa-bolt"></i> Quick Fix</div>
                        <div class="adb-val-fixbox-rows">
                            ${fixRows.map(r => `
                                <label class="adb-val-fixrow">
                                    <input type="checkbox" id="${r.id}" class="adb-val-fixtick" checked>
                                    <span class="adb-val-fixrow-label">${r.label}</span>
                                    <em class="adb-val-fixrow-desc">${r.desc}</em>
                                    <span class="adb-val-fixrow-cnt">${r.count}</span>
                                </label>`).join('')}
                        </div>
                        <button id="adb-val-fix-all-btn" class="adb-btn adb-btn-accent adb-btn-sm">
                            <i class="fas fa-wand-sparkles"></i> Fix Selected
                        </button>
                    </div>` : '';

                sumEl.innerHTML = `
                    <div class="adb-val-ctrl">
                        <div class="adb-val-summary-row">
                            <div class="adb-val-chips">
                                ${chips.map(o =>
                                    `<span class="adb-val-chip adb-val-chip-${o.cls}">
                                        <i class="fas ${o.icon}"></i> <strong>${o.val}</strong>&nbsp;${o.label}
                                     </span>`
                                ).join('')}
                            </div>
                        </div>
                        ${fixBox}
                    </div>`;
            }

            // ── Issues pane ──────────────────────────────────────────────────
            const issueEl = _el('adb-val-issues');
            if (!issueEl) return;

            const hasAnything = dupGroups.length || errEntities.length || warnSummary.length || mismatches.length || orphanStubs.length || deletedEntities.length;
            if (!hasAnything) {
                issueEl.innerHTML = '<div class="adb-empty-hint"><i class="fas fa-check-circle"></i> All entities passed checks.</div>';
                return;
            }

            // ── Helpers shared by sections ───────────────────────────────────
            const _statusBadge = s => {
                const cls = s === 'active' ? 'adb-val-dup-badge-active'
                          : s === 'stub'   ? 'adb-val-dup-badge-stub'
                          :                  'adb-val-dup-badge-other';
                return `<span class="adb-val-dup-badge ${cls}">${s}</span>`;
            };
            const _statLine = e => {
                const parts = [];
                if (e.relation_count) parts.push(`${e.relation_count} rel`);
                if (e.timeline_count) parts.push(`${e.timeline_count} events`);
                if (e.alias_count)    parts.push(`${e.alias_count} aliases`);
                parts.push(`v${e.version}`);
                return parts.join(' · ');
            };

            let html = '';

            // ── 1. Duplicate groups ──────────────────────────────────────────
            if (dupGroups.length) {
                html += `
                <div class="adb-val-dup-group adb-val-collapsible" data-collapsed="true">
                    <div class="adb-val-mm-header adb-val-collapse-hdr" role="button" tabindex="0">
                        <div class="adb-val-mm-title">
                            <i class="fas fa-copy"></i>
                            Duplicate Entities
                            <span class="adb-val-mm-badge adb-val-mm-badge-dup">${dupGroups.length}</span>
                        </div>
                        <div class="adb-val-collapse-chips">
                            ${autoGroups.length   ? `<span class="adb-val-cc-chip adb-val-cc-auto">${autoGroups.length} clear winner${autoGroups.length!==1?'s':''}</span>` : ''}
                            ${stubDupGroups.length ? `<span class="adb-val-cc-chip adb-val-cc-stub">${stubDupGroups.length} stub dup${stubDupGroups.length!==1?'s':''}</span>` : ''}
                            ${chooseGroups.length  ? `<span class="adb-val-cc-chip adb-val-cc-choose">${chooseGroups.length} need review</span>` : ''}
                        </div>
                        <i class="fas fa-chevron-down adb-val-collapse-chevron"></i>
                    </div>
                    <div class="adb-val-collapse-body">
                    <p class="adb-val-mm-desc">Entities sharing the same name or alias. The recommended action is pre-selected — review then confirm.</p>
                    <div class="adb-val-dup-clusters">
                        ${dupGroups.map((g, gi) => {
                            const primary = g.recommended_primary;
                            const isAuto  = g.action === 'auto' || g.action === 'stub_auto';
                            const entityRows = (g.entities || []).map((e, ei) => {
                                const isWinner = e.id === primary;
                                return `
                                <div class="adb-val-dup-entity${isWinner ? ' adb-val-dup-winner' : ''}" data-id="${e.id}" role="button" tabindex="0" title="Open entity">
                                    <div class="adb-val-dup-entity-top">
                                        ${_statusBadge(e.status)}
                                        <span class="adb-val-dup-entity-name">${e.name || e.id}</span>
                                        <code class="adb-val-mm-id">${e.id}</code>
                                        ${isWinner ? '<span class="adb-val-dup-keep-tag">keep</span>' : '<span class="adb-val-dup-remove-tag">remove</span>'}
                                    </div>
                                    ${e.has_summary ? `<div class="adb-val-dup-entity-summary">${e.summary}${e.summary && e.summary.length >= 120 ? '…' : ''}</div>` : ''}
                                    <div class="adb-val-dup-entity-meta">${_statLine(e)}</div>
                                </div>`;
                            }).join('');
                            const actionBtns = isAuto
                                ? `<button class="adb-btn adb-btn-sm adb-val-dup-fix-btn adb-val-dup-auto-btn"
                                           data-gi="${gi}" data-primary="${primary}" data-remove="${(g.recommended_remove||[]).join(',')}" data-merge="true">
                                       <i class="fas fa-wand-sparkles"></i> Auto-fix
                                   </button>`
                                : `<button class="adb-btn adb-btn-sm adb-val-dup-fix-btn adb-val-dup-merge-btn"
                                           data-gi="${gi}" data-primary="${primary}" data-remove="${(g.recommended_remove||[]).join(',')}" data-merge="true">
                                       <i class="fas fa-object-group"></i> Merge
                                   </button>
                                   ${(g.entities||[]).map((e,ei) => {
                                       const others = (g.entities||[]).filter(x=>x.id!==e.id).map(x=>x.id).join(',');
                                       return `<button class="adb-btn adb-btn-sm adb-btn-ghost adb-val-dup-fix-btn adb-val-dup-keep-btn"
                                                       data-gi="${gi}" data-primary="${e.id}" data-remove="${others}" data-merge="false"
                                                       title="Keep only ${e.name||e.id}">Keep ${ei===0?'A':ei===1?'B':'C'}</button>`;
                                   }).join('')}`;
                            return `
                            <div class="adb-val-dup-cluster" data-gi="${gi}">
                                <div class="adb-val-dup-label">
                                    <i class="fas fa-link"></i>
                                    <span class="adb-val-dup-norm">"${g.norm_name}"</span>
                                    ${isAuto
                                        ? '<span class="adb-val-dup-auto-tag"><i class="fas fa-bolt"></i> clear winner</span>'
                                        : '<span class="adb-val-dup-choose-tag"><i class="fas fa-scale-balanced"></i> needs review</span>'}
                                </div>
                                <div class="adb-val-dup-entities">${entityRows}</div>
                                <div class="adb-val-dup-actions">${actionBtns}</div>
                            </div>`;
                        }).join('')}
                    </div>
                    </div>
                </div>`;
            }

            // ── 2. Integrity errors ──────────────────────────────────────────
            if (errEntities.length) {
                if (dupGroups.length) html += '<div class="adb-val-section-sep"></div>';

                // Detect which entities have fixable broken-relation errors
                const brokenRelEntities = errEntities.filter(e =>
                    (e.issues || []).some(i => i.check === 'reference_integrity')
                );
                const fixAllRelBtn = brokenRelEntities.length
                    ? `<button class="adb-val-quick-fix-btn adb-val-fix-all-rels"
                               title="Remove all broken relation targets across all affected entities">
                           <i class="fas fa-wand-magic-sparkles"></i> Fix All Broken Relations (${brokenRelEntities.length})
                       </button>`
                    : '';

                html += `
                <div class="adb-val-issue-group adb-val-issue-group-err adb-val-collapsible" data-collapsed="true">
                    <div class="adb-val-issue-header adb-val-collapse-hdr" role="button" tabindex="0">
                        <i class="fas fa-exclamation-circle"></i>
                        Integrity Errors
                        <span class="adb-val-issue-badge adb-val-issue-badge-err">${errEntities.length} entit${errEntities.length!==1?'ies':'y'}</span>
                        <i class="fas fa-chevron-down adb-val-collapse-chevron"></i>
                    </div>
                    <div class="adb-val-collapse-body">
                    ${fixAllRelBtn ? `<div class="adb-val-quick-fix-row">${fixAllRelBtn}</div>` : ''}
                    <div class="adb-val-issue-list">
                        ${errEntities.map(e => {
                            const hasRelErr = (e.issues || []).some(i => i.check === 'reference_integrity');
                            const fixBtn = hasRelErr
                                ? `<button class="adb-val-quick-fix-btn adb-val-fix-rel-btn"
                                           data-entity-id="${e.id}"
                                           title="Remove broken relations from this entity">
                                       <i class="fas fa-scissors"></i> Fix
                                   </button>`
                                : '';
                            return `
                            <div class="adb-val-err-entity" data-id="${e.id}" role="button" tabindex="0">
                                <div class="adb-val-err-entity-top">
                                    <span class="adb-val-err-entity-name">${e.name || e.id}</span>
                                    <code class="adb-val-mm-id">${e.id}</code>
                                    ${fixBtn}
                                </div>
                                ${(e.issues||[]).map(i =>
                                    `<div class="adb-val-err-msg">
                                        <i class="fas fa-xmark"></i>
                                        <span class="adb-val-err-check">${i.check}</span>
                                        ${i.message}
                                     </div>`
                                ).join('')}
                            </div>`;
                        }).join('')}
                    </div>
                    </div>
                </div>`;
            }

            // ── 3. Warnings summary (grouped by check type) ──────────────────
            if (warnSummary.length) {
                if (dupGroups.length || errEntities.length) html += '<div class="adb-val-section-sep"></div>';
                html += `
                <div class="adb-val-issue-group adb-val-issue-group-warn adb-val-collapsible" data-collapsed="true">
                    <div class="adb-val-issue-header adb-val-collapse-hdr" role="button" tabindex="0">
                        <i class="fas fa-triangle-exclamation"></i>
                        Warnings
                        <span class="adb-val-issue-badge adb-val-issue-badge-warn">${data.total_warnings ?? 0} total</span>
                        <i class="fas fa-chevron-down adb-val-collapse-chevron"></i>
                    </div>
                    <div class="adb-val-collapse-body">
                    <div class="adb-val-warn-list">
                        ${warnSummary.map(w => {
                            const ents   = w.entities || [];
                            const limit  = 60;
                            const shown  = ents.slice(0, limit);
                            const extra  = ents.length - shown.length;
                            return `
                            <div class="adb-val-warn-group" data-collapsed="true">
                                <div class="adb-val-warn-row adb-val-collapse-hdr" role="button" tabindex="0">
                                    <span class="adb-val-warn-cnt">${w.count}</span>
                                    <span class="adb-val-warn-label">${w.label}</span>
                                    <span class="adb-val-warn-check">${w.check}</span>
                                    <i class="fas fa-chevron-down adb-val-warn-chevron"></i>
                                </div>
                                <div class="adb-val-warn-entity-list adb-val-collapse-body">
                                    ${shown.map(e => `
                                        <div class="adb-val-warn-entity" data-id="${e.id}" role="button" tabindex="0">
                                            <span class="adb-val-warn-entity-name">${e.name || e.id}</span>
                                            <code class="adb-val-mm-id">${e.id}</code>
                                            <span class="adb-val-warn-entity-msg">${e.message}</span>
                                        </div>`).join('')}
                                    ${extra > 0 ? `<div class="adb-val-warn-more">… and ${extra} more</div>` : ''}
                                </div>
                            </div>`;
                        }).join('')}
                    </div>
                    </div>
                </div>`;
            }

            // ── 4. Orphan stubs ──────────────────────────────────────────────
            if (orphanStubs.length) {
                if (dupGroups.length || errEntities.length || warnSummary.length) html += '<div class="adb-val-section-sep"></div>';
                html += `
                <div class="adb-val-issue-group adb-val-issue-group-orphan adb-val-collapsible" data-collapsed="true">
                    <div class="adb-val-issue-header adb-val-collapse-hdr" role="button" tabindex="0">
                        <i class="fas fa-link-slash"></i>
                        Orphan Stubs
                        <span class="adb-val-issue-badge adb-val-issue-badge-orphan">${orphanStubs.length} stub${orphanStubs.length!==1?'s':''}</span>
                        <i class="fas fa-chevron-down adb-val-collapse-chevron"></i>
                    </div>
                    <div class="adb-val-collapse-body">
                    <p class="adb-val-mm-desc">Stubs with no outgoing relations and not referenced by any other entity. They carry no information and are safe to remove. <strong>Note:</strong> the fix marks them as <code>deleted</code> — files remain on disk and are still visible in the explorer. Use the <em>Purge deleted files</em> option to permanently remove them.</p>
                    <div class="adb-val-issue-list">
                        ${orphanStubs.map(e => `
                            <div class="adb-val-orphan-entity" data-id="${e.id}" role="button" tabindex="0">
                                <span class="adb-val-orphan-name">${e.name || e.id}</span>
                                <code class="adb-val-mm-id">${e.id}</code>
                            </div>`).join('')}
                    </div>
                    </div>
                </div>`;
            }

            // ── 5. Deleted files pending purge ───────────────────────────────
            if (deletedEntities.length) {
                if (dupGroups.length || errEntities.length || warnSummary.length || orphanStubs.length) html += '<div class="adb-val-section-sep"></div>';
                const shown = deletedEntities.slice(0, 200);
                const extra = deletedEntities.length - shown.length;
                html += `
                <div class="adb-val-issue-group adb-val-issue-group-del adb-val-collapsible" data-collapsed="true">
                    <div class="adb-val-issue-header adb-val-collapse-hdr" role="button" tabindex="0">
                        <i class="fas fa-trash"></i>
                        Deleted Files on Disk
                        <span class="adb-val-issue-badge adb-val-issue-badge-del">${deletedEntities.length} file${deletedEntities.length!==1?'s':''}</span>
                        <i class="fas fa-chevron-down adb-val-collapse-chevron"></i>
                    </div>
                    <div class="adb-val-collapse-body">
                    <p class="adb-val-mm-desc">These entities have been soft-deleted (marked <code>status: deleted</code>) but their files remain on disk. They are excluded from all counts and searches. Use <strong>Purge deleted files</strong> in Quick Fix to permanently remove them.</p>
                    <div class="adb-val-issue-list">
                        ${shown.map(e => `
                            <div class="adb-val-del-entity">
                                <span class="adb-val-del-name">${e.name || e.id}</span>
                                <code class="adb-val-mm-id">${e.id}</code>
                            </div>`).join('')}
                        ${extra > 0 ? `<div class="adb-val-warn-more">… and ${extra} more</div>` : ''}
                    </div>
                    </div>
                </div>`;
            }

            issueEl.innerHTML = html;

            // Wire: collapse/expand — any hdr inside any [data-collapsed] container
            issueEl.querySelectorAll('.adb-val-collapse-hdr').forEach(hdr => {
                const section = hdr.closest('[data-collapsed]');
                if (!section) return;
                const toggle = () => {
                    section.dataset.collapsed = section.dataset.collapsed === 'true' ? 'false' : 'true';
                };
                hdr.addEventListener('click', toggle);
                hdr.addEventListener('keydown', e => {
                    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
                });
            });

            // Wire: dup entity rows → open entity
            issueEl.querySelectorAll('.adb-val-dup-entity[data-id]').forEach(row => {
                row.addEventListener('click', () => _loadEntity(row.dataset.id));
                row.addEventListener('keydown', e => { if (e.key === 'Enter') _loadEntity(row.dataset.id); });
            });

            // Wire: dup fix buttons (auto-fix / merge / keep-X)
            issueEl.querySelectorAll('.adb-val-dup-fix-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const primaryId = btn.dataset.primary;
                    const removeIds = btn.dataset.remove ? btn.dataset.remove.split(',').filter(Boolean) : [];
                    const doMerge   = btn.dataset.merge !== 'false';
                    const clusterEl = btn.closest('.adb-val-dup-cluster');
                    btn.disabled = true;
                    btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i>';
                    try {
                        const res = await fetch(`${API}/validate/fix-duplicates?${_dbParam()}`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ primary_id: primaryId, remove_ids: removeIds, merge: doMerge }),
                        });
                        if (!res.ok) throw new Error(await res.text());
                        const d = await res.json();
                        _toast(`${doMerge ? 'Merged' : 'Resolved'}: kept ${primaryId}, removed ${d.removed?.length??0}, rewired ${d.ref_updates??0} refs`, 'success');
                        if (clusterEl) {
                            clusterEl.style.opacity = '0.4';
                            clusterEl.style.pointerEvents = 'none';
                            clusterEl.querySelector('.adb-val-dup-actions').innerHTML =
                                '<span class="adb-val-dup-resolved"><i class="fas fa-check"></i> Resolved</span>';
                        }
                    } catch (err) {
                        _toast(`Fix failed: ${err.message}`, 'error');
                        btn.disabled = false;
                        btn.innerHTML = btn.classList.contains('adb-val-dup-auto-btn') ? '<i class="fas fa-wand-sparkles"></i> Auto-fix'
                                      : btn.classList.contains('adb-val-dup-merge-btn') ? '<i class="fas fa-object-group"></i> Merge'
                                      : btn.textContent.trim();
                    }
                });
            });

            // Wire: error entity rows → open entity
            issueEl.querySelectorAll('.adb-val-err-entity[data-id]').forEach(row => {
                row.addEventListener('click', () => _loadEntity(row.dataset.id));
                row.addEventListener('keydown', e => { if (e.key === 'Enter') _loadEntity(row.dataset.id); });
            });

            // Wire: warning entity rows → open entity
            issueEl.querySelectorAll('.adb-val-warn-entity[data-id]').forEach(row => {
                row.addEventListener('click', e => { e.stopPropagation(); _loadEntity(row.dataset.id); });
                row.addEventListener('keydown', e => { if (e.key === 'Enter') { e.stopPropagation(); _loadEntity(row.dataset.id); }});
            });

            // Wire: orphan stub rows → open entity
            issueEl.querySelectorAll('.adb-val-orphan-entity[data-id]').forEach(row => {
                row.addEventListener('click', () => _loadEntity(row.dataset.id));
                row.addEventListener('keydown', e => { if (e.key === 'Enter') _loadEntity(row.dataset.id); });
            });

            // Wire: Fix Selected button (control panel)
            _el('adb-val-fix-all-btn')?.addEventListener('click', async () => {
                const btn      = _el('adb-val-fix-all-btn');
                const fixDups     = _el('adb-vfix-dups')?.checked      ?? false;
                const fixStubDups = _el('adb-vfix-stub-dups')?.checked ?? false;
                const fixOrphans  = _el('adb-vfix-orphans')?.checked   ?? false;
                const fixPurge    = _el('adb-vfix-purge')?.checked     ?? false;
                const fixMm       = _el('adb-vfix-mm')?.checked        ?? false;
                const fixTimeline = _el('adb-vfix-timeline')?.checked  ?? false;
                if (!fixDups && !fixStubDups && !fixOrphans && !fixPurge && !fixMm && !fixTimeline) { _toast('Nothing selected to fix', 'info'); return; }
                if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Working…'; }
                let dupFixed = 0, orphanFixed = 0, purgeFixed = 0, mmFixed = 0, timelineFixed = 0;
                try {
                    if (fixDups || fixStubDups) {
                        const groupsToFix = [
                            ...(fixDups     ? autoGroups    : []),
                            ...(fixStubDups ? stubDupGroups : []),
                        ];
                        for (const g of groupsToFix) {
                            const removeIds = g.recommended_remove || [];
                            if (!removeIds.length) continue;
                            const r = await fetch(`${API}/validate/fix-duplicates?${_dbParam()}`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ primary_id: g.recommended_primary, remove_ids: removeIds, merge: true }),
                            });
                            if (r.ok) dupFixed++;
                        }
                    }
                    if (fixOrphans && orphanStubs.length) {
                        const orRes  = await fetch(`${API}/validate/fix-orphan-stubs?${_dbParam()}`, { method: 'POST' });
                        const orData = await orRes.json();
                        orphanFixed = orData.fixed ?? 0;
                    }
                    if (fixPurge && deletedEntities.length) {
                        const prRes  = await fetch(`${API}/validate/purge-deleted?${_dbParam()}`, { method: 'POST' });
                        const prData = await prRes.json();
                        purgeFixed = prData.purged ?? 0;
                    }
                    if (fixMm && mismatches.length) {
                        const mmRes  = await fetch(`${API}/validate/fix-status-mismatches?${_dbParam()}`, { method: 'POST' });
                        const mmData = await mmRes.json();
                        mmFixed = mmData.fixed ?? 0;
                    }
                    if (fixTimeline && timelineCount) {
                        const tlRes  = await fetch(`${API}/validate/fix-timeline-sort?${_dbParam()}`, { method: 'POST' });
                        const tlData = await tlRes.json();
                        timelineFixed = tlData.fixed ?? 0;
                    }
                    const parts = [];
                    if (dupFixed)      parts.push(`fixed ${dupFixed} duplicate group${dupFixed!==1?'s':''}`);
                    if (orphanFixed)   parts.push(`removed ${orphanFixed} orphan stub${orphanFixed!==1?'s':''}`);
                    if (purgeFixed)    parts.push(`purged ${purgeFixed} deleted file${purgeFixed!==1?'s':''}`);
                    if (mmFixed)       parts.push(`promoted ${mmFixed} stub${mmFixed!==1?'s':''}`);
                    if (timelineFixed) parts.push(`sorted timelines in ${timelineFixed} entit${timelineFixed!==1?'ies':'y'}`);
                    _toast(parts.join(', ') || 'Done', 'success');
                    await _validateAll();
                } catch (err) {
                    _toast(`Fix failed: ${err.message}`, 'error');
                    if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-wand-sparkles"></i> Fix Selected'; }
                }
            });

            // ── Quick fix: Fix All Broken Relations ──────────────────────────
            issueEl.querySelector('.adb-val-fix-all-rels')?.addEventListener('click', async (ev) => {
                ev.stopPropagation();
                const btn = ev.currentTarget;
                btn.disabled = true;
                btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Fixing…';
                try {
                    const res  = await fetch(`${API}/validate/fix-broken-relations?${_dbParam()}`, { method: 'POST' });
                    const data = await res.json();
                    const n    = data.removed_relations ?? 0;
                    _toast(`Removed ${n} broken relation${n !== 1 ? 's' : ''} across ${data.fixed} entit${data.fixed !== 1 ? 'ies' : 'y'}`, 'success');
                    await _validateAll();
                } catch (err) {
                    _toast(`Fix failed: ${err.message}`, 'error');
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i> Fix All Broken Relations';
                }
            });

            // ── Quick fix: Fix Broken Relations for a single entity ───────────
            issueEl.querySelectorAll('.adb-val-fix-rel-btn').forEach(btn => {
                btn.addEventListener('click', async (ev) => {
                    ev.stopPropagation();
                    const entityId = btn.dataset.entityId;
                    btn.disabled = true;
                    btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i>';
                    try {
                        const res  = await fetch(`${API}/validate/fix-broken-relations?${_dbParam()}&entity_id=${encodeURIComponent(entityId)}`, { method: 'POST' });
                        const data = await res.json();
                        const n    = data.removed_relations ?? 0;
                        _toast(`Removed ${n} broken relation${n !== 1 ? 's' : ''} from "${data.entities?.[0]?.name || entityId}"`, 'success');
                        await _validateAll();
                    } catch (err) {
                        _toast(`Fix failed: ${err.message}`, 'error');
                        btn.disabled = false;
                        btn.innerHTML = '<i class="fas fa-scissors"></i> Fix';
                    }
                });
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
    let _graphSim        = null;   // d3 force simulation
    let _graphFocusId    = null;   // entity ID of the focused node (null = full graph)
    let _graphNodeSel    = null;   // d3 node circle selection
    let _graphLinkSel    = null;   // d3 edge line selection
    let _graphLabelSel   = null;   // d3 label text selection
    let _graphLinkData   = null;   // raw link array (after d3 resolves source/target)
    let _graphFitDone    = false;  // true after the initial auto-fit; prevents re-fits on drag
    let _pendingChunkId  = null;   // chunk to select once the graph dropdown is populated

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
            await _graphLoadChunkOptions();   // populate chunk dropdown first (resolves _pendingChunkId)
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
        // Show the Back button only when viewing a focused subgraph
        const backBtn = _el('adb-graph-back-btn');
        if (backBtn) backBtn.classList.toggle('hidden', !entityId);

        const depth   = _el('adb-graph-depth')?.value || '2';
        const chunkId = _el('adb-graph-chunk-sel')?.value || '';
        const params  = new URLSearchParams(_dbParam({ limit: 500 }));
        if (entityId) { params.set('entity_id', entityId); params.set('depth', depth); }
        else if (chunkId) { params.set('chunk_id', chunkId); }

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
        _graphFitDone = false;   // reset so the new graph gets its initial fit

        const svgEl = _el('adb-graph-svg');
        if (!svgEl || !window.d3) return;

        const d3     = window.d3;
        const svg    = d3.select(svgEl);
        const width  = svgEl.clientWidth  || 900;
        const height = svgEl.clientHeight || 600;

        svg.selectAll('*').remove();

        // ── Defs: arrowhead markers + edge glow filter ──
        const defs = svg.append('defs');

        // Default arrow (muted)
        defs.append('marker')
            .attr('id', 'adb-graph-arrow')
            .attr('viewBox', '0 -4 8 8')
            .attr('refX', 14).attr('refY', 0)
            .attr('markerWidth', 5).attr('markerHeight', 5)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-4L8,0L0,4')
            .attr('fill', 'rgba(100,116,139,0.45)');

        // Hover arrow (bright)
        defs.append('marker')
            .attr('id', 'adb-graph-arrow-hover')
            .attr('viewBox', '0 -4 8 8')
            .attr('refX', 14).attr('refY', 0)
            .attr('markerWidth', 5).attr('markerHeight', 5)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-4L8,0L0,4')
            .attr('fill', 'rgba(226,232,240,0.92)');

        // Glow filter applied to highlighted edges
        const glowF = defs.append('filter')
            .attr('id',     'adb-graph-edge-glow')
            .attr('x',      '-40%').attr('y',      '-40%')
            .attr('width',  '180%').attr('height', '180%');
        glowF.append('feGaussianBlur')
            .attr('in', 'SourceGraphic')
            .attr('stdDeviation', '3')
            .attr('result', 'blur');
        const glowMerge = glowF.append('feMerge');
        glowMerge.append('feMergeNode').attr('in', 'blur');
        glowMerge.append('feMergeNode').attr('in', 'SourceGraphic');

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
                    // Keep the node pinned at its drop position so it stays where
                    // the user placed it.  Releasing (fx=null) would let the node
                    // drift back to force-equilibrium, which also triggers another
                    // simulation 'end' event and causes the view to re-fit.
                    d.fx = d.x; d.fy = d.y;
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

        // Pin focused node at centre so its neighbourhood fans out from it.
        // Also immediately shift the viewport so (0,0) maps to canvas centre —
        // without this the focused node sits at the SVG origin (top-left corner)
        // until the simulation settles and the 'end' fit fires.
        if (data.focused_id) {
            const focal = nodes.find(n => n.id === data.focused_id);
            if (focal) {
                focal.fx = 0; focal.fy = 0;
                svg.call(zoom.transform, d3.zoomIdentity.translate(width / 2, height / 2));
            }
        }

        // Centre the view after the initial settle only.
        // Subsequent 'end' events (from drag interactions) must not reset the
        // viewport — the user may have panned/zoomed to exactly where they want.
        _graphSim.on('end', () => {
            if (_graphFitDone) return;
            _graphFitDone = true;
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
            // ── Reset to baseline ──────────────────────────────────────────
            _graphNodeSel
                .attr('opacity',        1)
                .attr('stroke',         d => _gNodeColor(d.type))
                .attr('stroke-width',   d => d.id === _graphFocusId ? 3 : 1.5)
                .attr('stroke-opacity', d => d.status === 'stub' ? 0.5 : 0.7);
            _graphLinkSel
                .attr('stroke-opacity', 0.55)
                .attr('stroke-width',   1.5)
                .attr('stroke',         d => _gEdgeColor(d.kind))
                .attr('filter',         null)
                .attr('marker-end',     'url(#adb-graph-arrow)');
            _graphLabelSel?.attr('opacity', 1);
            return;
        }

        // ── Build neighbour sets ───────────────────────────────────────────
        const connected = new Set([focusId]);
        (_graphLinkData || []).forEach(d => {
            const s = typeof d.source === 'object' ? d.source.id : d.source;
            const t = typeof d.target === 'object' ? d.target.id : d.target;
            if (s === focusId) connected.add(t);
            if (t === focusId) connected.add(s);
        });

        const _isHot = d => {
            const s = typeof d.source === 'object' ? d.source.id : d.source;
            const t = typeof d.target === 'object' ? d.target.id : d.target;
            return s === focusId || t === focusId;
        };

        // ── Nodes: no dimming — white ring on hovered node, slightly bolder ──
        // ring on direct neighbours; everything else stays fully visible.
        _graphNodeSel
            .attr('opacity',        1)
            .attr('stroke',         d => d.id === focusId ? '#ffffff' : _gNodeColor(d.type))
            .attr('stroke-width',   d => d.id === focusId ? 3.5 : connected.has(d.id) ? 2 : 1.5)
            .attr('stroke-opacity', d => d.id === focusId ? 1 : d.status === 'stub' ? 0.5 : 0.7);

        // ── Edges: connected ones glow; others fade to nearly invisible ───
        _graphLinkSel
            .attr('stroke-opacity', d => _isHot(d) ? 1.0  : 0.04)
            .attr('stroke-width',   d => _isHot(d) ? 3.0  : 1.0)
            .attr('stroke',         d => _isHot(d) ? 'rgba(226,232,240,0.9)' : _gEdgeColor(d.kind))
            .attr('filter',         d => _isHot(d) ? 'url(#adb-graph-edge-glow)' : null)
            .attr('marker-end',     d => _isHot(d) ? 'url(#adb-graph-arrow-hover)' : 'url(#adb-graph-arrow)');

        // ── Labels: fully visible at all times ───────────────────────────
        _graphLabelSel?.attr('opacity', 1);
    }

    // ── Node selection card ───────────────────────────────────────────────────

    function _graphSelectNode(d) {
        // ── Header: type badge + name ─────────────────────────────────────────
        const typeEl = _el('adb-graph-card-type');
        if (typeEl) {
            typeEl.textContent = d.type || 'other';
            typeEl.className   = `adb-type-badge adb-type-${d.type || 'other'}`;
        }
        const nameEl = _el('adb-graph-card-name');
        if (nameEl) nameEl.textContent = d.name;

        // ── Summary ───────────────────────────────────────────────────────────
        const sumEl = _el('adb-graph-card-summary');
        if (sumEl) sumEl.textContent = d.summary || '';

        // ── Tags ──────────────────────────────────────────────────────────────
        const tagsEl = _el('adb-graph-card-tags');
        if (tagsEl) {
            const tags = d.tags || [];
            if (tags.length) {
                tagsEl.innerHTML = tags.map(t => `<span class="adb-tag adb-tag-sm">${_escHtml(t)}</span>`).join('');
                tagsEl.classList.remove('hidden');
            } else {
                tagsEl.classList.add('hidden');
            }
        }

        // ── Meta: status badge + relation count ───────────────────────────────
        const metaEl = _el('adb-graph-card-meta');
        if (metaEl) {
            const isStub = d.status === 'stub';
            metaEl.innerHTML =
                `<span class="adb-badge ${isStub ? 'adb-badge-stub' : 'adb-badge-expanded'}">${isStub ? 'stub' : 'expanded'}</span>` +
                (d.rel_count ? `<span>${d.rel_count} relation${d.rel_count !== 1 ? 's' : ''}</span>` : '');
        }

        // ── Connected relations (from already-loaded graph data) ───────────────
        const relsEl = _el('adb-graph-card-rels');
        if (relsEl && _graphLinkData) {
            const connected = [];
            for (const link of _graphLinkData) {
                // After d3.forceLink runs, source/target are node objects
                const src   = link.source;
                const tgt   = link.target;
                const srcId = typeof src === 'object' ? src.id   : src;
                const tgtId = typeof tgt === 'object' ? tgt.id   : tgt;
                const srcName = typeof src === 'object' ? src.name : srcId;
                const tgtName = typeof tgt === 'object' ? tgt.name : tgtId;
                if (srcId === d.id) {
                    connected.push({ dir: '→', kind: link.kind, name: tgtName });
                } else if (tgtId === d.id) {
                    connected.push({ dir: '←', kind: link.kind, name: srcName });
                }
            }
            if (connected.length) {
                const MAX  = 7;
                const rows = connected.slice(0, MAX).map(r =>
                    `<div class="adb-graph-rel-row">
                        <span class="adb-graph-rel-dir">${r.dir}</span>
                        <span class="adb-graph-rel-kind">${_escHtml(r.kind)}</span>
                        <span class="adb-graph-rel-name">${_escHtml(r.name)}</span>
                    </div>`
                ).join('');
                const more = connected.length > MAX
                    ? `<div class="adb-graph-rel-more">+${connected.length - MAX} more</div>` : '';
                relsEl.innerHTML = `<div class="adb-graph-rels-label">Relations</div>${rows}${more}`;
                relsEl.classList.remove('hidden');
            } else {
                relsEl.classList.add('hidden');
            }
        }

        // ── Action buttons ────────────────────────────────────────────────────
        const openBtn = _el('adb-graph-card-open');
        if (openBtn) openBtn.onclick = () => { _closeGraph(); _loadEntity(d.id); };

        const focBtn = _el('adb-graph-card-focus');
        if (focBtn) focBtn.onclick = () => _graphLoad(d.id);

        const deepenBtn = _el('adb-graph-card-deepen');
        if (deepenBtn) {
            const isStub = d.status === 'stub';
            deepenBtn.innerHTML = isStub
                ? '<i class="fas fa-wand-sparkles"></i> Expand'
                : '<i class="fas fa-wand-sparkles"></i> Deepen';

            deepenBtn.onclick = async () => {
                // Snapshot current node IDs so we can highlight what's new after reload
                const prevNodeIds = new Set(_graphSim ? _graphSim.nodes().map(n => n.id) : []);

                deepenBtn.disabled = true;
                deepenBtn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i>';

                try {
                    if (isStub) {
                        // ── Expand stub directly ───────────────────────────
                        const res = await fetch(`${API}/entities/${d.id}/expand?${_dbParam()}`, { method: 'POST' });
                        if (!res.ok) {
                            let msg; try { msg = (await res.json()).detail; } catch { msg = `HTTP ${res.status}`; }
                            throw new Error(msg);
                        }
                    } else {
                        // ── Deepen active entity directly ──────────────────
                        const res = await fetch(`${API}/entities/${d.id}/deepen?${_dbParam({ max_stubs: 5 })}`, { method: 'POST' });
                        if (!res.ok) {
                            let msg; try { msg = (await res.json()).detail; } catch { msg = `HTTP ${res.status}`; }
                            throw new Error(msg);
                        }
                    }

                    _hide('adb-graph-card');

                    // Reload graph centred on this entity — new nodes animate in
                    await _graphLoad(d.id);

                    // Identify and flash new nodes so additions are immediately obvious
                    if (_graphNodeSel && prevNodeIds.size) {
                        const newEls = _graphNodeSel.filter(n => !prevNodeIds.has(n.id));
                        if (!newEls.empty()) {
                            // Cyan ring flash
                            newEls
                                .attr('stroke',         '#22d3ee')
                                .attr('stroke-width',   4)
                                .attr('stroke-opacity', 1);
                            setTimeout(() => {
                                newEls.transition().duration(1400)
                                    .attr('stroke',         n => _gNodeColor(n.type))
                                    .attr('stroke-width',   1.5)
                                    .attr('stroke-opacity', n => n.status === 'stub' ? 0.5 : 0.7);
                            }, 1800);
                            const n = newEls.size();
                            _toast(
                                isStub
                                    ? `Expanded — ${n} new node${n !== 1 ? 's' : ''} added to graph`
                                    : `Deepened — ${n} new node${n !== 1 ? 's' : ''} added to graph`,
                                'success'
                            );
                        } else {
                            _toast(
                                isStub ? `"${d.name}" is already fully expanded` : `No new sub-topics found for "${d.name}"`,
                                'info'
                            );
                        }
                    } else {
                        _toast(isStub ? `"${d.name}" expanded` : `"${d.name}" deepened`, 'success');
                    }

                } catch (err) {
                    _toast(`Failed: ${err.message}`, 'error');
                    deepenBtn.disabled = false;
                    deepenBtn.innerHTML = isStub
                        ? '<i class="fas fa-wand-sparkles"></i> Expand'
                        : '<i class="fas fa-wand-sparkles"></i> Deepen';
                }
            };
        }

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
        _el('adb-graph-back-btn')  ?.addEventListener('click', () => {
            const si = _el('adb-graph-search'); if (si) si.value = '';
            _graphLoad(null);
        });
        _el('adb-graph-focus-btn') ?.addEventListener('click', _graphFocusSearch);
        _el('adb-graph-full-btn')  ?.addEventListener('click', () => {
            const si = _el('adb-graph-search'); if (si) si.value = '';
            _graphLoad(null);
        });
        _el('adb-graph-search')    ?.addEventListener('keydown', e => { if (e.key === 'Enter') _graphFocusSearch(); });
        _el('adb-graph-card-close')?.addEventListener('click',   () => _hide('adb-graph-card'));
        _el('adb-graph-depth')     ?.addEventListener('change',  () => { if (_graphFocusId) _graphLoad(_graphFocusId); });
        _el('adb-graph-chunk-sel') ?.addEventListener('change',  () => {
            // Reset focus when switching chunks
            _graphFocusId = null;
            const si = _el('adb-graph-search'); if (si) si.value = '';
            _graphLoad(null);
        });
        _el('adb-graph-labels-cb') ?.addEventListener('change',  e => {
            _graphLabelSel?.attr('display', e.target.checked ? null : 'none');
        });
    }

    /** Populate the chunk filter dropdown in the graph toolbar. */
    async function _graphLoadChunkOptions() {
        const sel = _el('adb-graph-chunk-sel');
        if (!sel) return;
        try {
            const res  = await fetch(`${API}/chunks?${_dbParam()}`);
            const data = await res.json();
            const chunks = data.chunks || [];
            // Prefer a pending chunk set via "View in Graph", otherwise keep the current value
            const target = _pendingChunkId || sel.value;
            _pendingChunkId = null;
            // Rebuild options
            sel.innerHTML = '<option value="">All chunks</option>';
            chunks.forEach(c => {
                const opt   = document.createElement('option');
                opt.value   = c.id;
                opt.title   = c.label;
                // Truncate long labels for the dropdown
                opt.textContent = c.label.length > 38 ? c.label.slice(0, 36) + '…' : c.label;
                sel.appendChild(opt);
            });
            if (target && [...sel.options].some(o => o.value === target)) sel.value = target;
        } catch { /* non-fatal — chunk dropdown stays as "All" */ }
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
            if (!data.is_vectorizing) {
                _vecStopPolling();
                _vecLoadCoverage();   // refresh coverage counts after run completes
            }
        } catch { /* ignore */ }
    }

    function _vecApplyStatus(data) {
        const statusEl    = _el('adb-vec-status');
        const countEl     = _el('adb-vec-count-label');
        const badgeEl     = _el('adb-vec-badge');
        const fillEl      = _el('adb-vec-bar-fill');
        const pctEl       = _el('adb-vec-bar-pct');
        const breakdownEl = _el('adb-vec-breakdown');
        const errorMsgEl  = _el('adb-vec-error-msg');
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
        // Skipped = already had embeddings, counts as "done" for progress purposes.
        // Only actual failures keep the bar from reaching 100 %.
        const done = vectorized + skipped;
        const pct  = total > 0 ? Math.round(done / total * 100) : 0;

        if (fillEl)  fillEl.style.width = `${pct}%`;
        if (pctEl)   pctEl.textContent  = `${pct}%`;

        const STATUS_LABEL = { running:'Running', done:'Done', error:'Error', cancelled:'Cancelled' };
        const STATUS_CLS   = { running:'adb-fd-badge-running', done:'adb-fd-badge-done', error:'adb-fd-badge-error', cancelled:'adb-fd-badge-paused' };
        if (badgeEl) {
            badgeEl.textContent = STATUS_LABEL[data.status] || data.status;
            badgeEl.className   = `adb-fd-badge ${STATUS_CLS[data.status] || ''}`;
        }

        // Count label: simple total progress (detail is in the breakdown below)
        if (countEl) {
            countEl.textContent = `${_fmtNum(done)} / ${_fmtNum(total)} entities`;
            countEl.style.color = '';
        }

        // Breakdown: embedded · skipped (already vectorized) · failed
        if (breakdownEl) {
            if (total > 0) {
                const parts = [
                    `<span class="adb-vec-bd-embedded"><i class="fas fa-check-circle"></i> ${_fmtNum(vectorized)} embedded</span>`,
                ];
                if (skipped > 0) {
                    parts.push(`<span class="adb-vec-bd-skipped" title="Already had embeddings for this model — skipped to avoid overwriting"><i class="fas fa-forward"></i> ${_fmtNum(skipped)} already vectorized</span>`);
                }
                if (failedCnt > 0) {
                    parts.push(`<span class="adb-vec-bd-failed"><i class="fas fa-circle-xmark"></i> ${_fmtNum(failedCnt)} failed</span>`);
                }
                breakdownEl.innerHTML = parts.join('');
                breakdownEl.classList.remove('hidden');
            } else {
                breakdownEl.classList.add('hidden');
            }
        }

        // Error message (last_error from VECINFO)
        if (errorMsgEl) {
            const errorMsg = data.error || data.last_error || null;
            if (errorMsg && (data.status === 'error' || failedCnt > 0)) {
                const short = errorMsg.length > 200 ? errorMsg.slice(0, 200) + '…' : errorMsg;
                errorMsgEl.textContent = short;
                errorMsgEl.classList.remove('hidden');
            } else {
                errorMsgEl.classList.add('hidden');
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

    async function _vecLoadCoverage() {
        const coverageEl = _el('adb-vec-coverage');
        const bodyEl     = _el('adb-vec-coverage-body');
        if (!bodyEl) return;

        try {
            const res  = await fetch(`${API}/vectors/models?${_dbParam()}`);
            const data = await res.json();
            const models = data.models || [];
            const counts = data.counts || {};

            if (!models.length) {
                if (coverageEl) coverageEl.classList.add('hidden');
                return;
            }

            if (coverageEl) coverageEl.classList.remove('hidden');

            const _OPENAI = ['text-embedding-3-small', 'text-embedding-3-large', 'text-embedding-ada-002'];
            bodyEl.innerHTML = `<table class="adb-vec-cov-table"><tbody>${
                models.map(m => {
                    const provider = _OPENAI.includes(m) ? 'OpenAI' : 'Google';
                    const provCls  = _OPENAI.includes(m) ? 'adb-vec-provider-openai' : 'adb-vec-provider-google';
                    return `<tr>
                        <td class="adb-vec-cov-model">${m}</td>
                        <td><span class="adb-vec-provider-badge ${provCls}">${provider}</span></td>
                        <td class="adb-vec-cov-count">${_fmtNum(counts[m] || 0)} entities</td>
                    </tr>`;
                }).join('')
            }</tbody></table>`;
        } catch {
            if (coverageEl) coverageEl.classList.add('hidden');
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
        _vecLoadCoverage();   // always refresh coverage when switching databases
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
    // Import
    // ══════════════════════════════════════════════════════════════════════════

    let _importContent  = null;
    let _importFilename = null;

    function _importFileSelected(e) {
        const file = e.target.files?.[0];
        if (!file) return;

        _importFilename = file.name;
        const displayEl = _el('adb-import-filename-display');
        if (displayEl) displayEl.value = file.name;

        const reader = new FileReader();
        reader.onload = evt => {
            _importContent = evt.target.result;
            _importShowPreview(file.name, _importContent);
            const btn = _el('adb-import-btn');
            if (btn) btn.disabled = false;
        };
        reader.readAsText(file, 'utf-8');
    }

    function _importShowPreview(filename, content) {
        const previewEl = _el('adb-import-preview');
        const textEl    = _el('adb-import-preview-text');
        if (!previewEl || !textEl) return;

        let count   = 0;
        let fmtLabel = 'unknown format';
        const lower  = filename.toLowerCase();

        try {
            if (lower.endsWith('.jsonl')) {
                count    = content.split('\n').filter(l => l.trim()).length;
                fmtLabel = 'JSONL bake';
            } else {
                const parsed = JSON.parse(content);
                if (Array.isArray(parsed)) {
                    count    = parsed.length;
                    fmtLabel = 'JSON array';
                } else if (parsed.entities) {
                    count    = parsed.entities.length;
                    fmtLabel = 'JSON bake';
                } else if (parsed.id && parsed.sections) {
                    count    = 1;
                    fmtLabel = 'single entity JSON';
                } else if (parsed.id) {
                    count    = 1;
                    fmtLabel = 'single flat entity';
                }
            }
        } catch {
            // Try JSONL fallback
            const lines = content.split('\n').filter(l => l.trim());
            if (lines.length) {
                try { JSON.parse(lines[0]); count = lines.length; fmtLabel = 'JSONL'; } catch {}
            }
        }

        const icon = count > 0 ? '<i class="fas fa-circle-check" style="color:#4ade80"></i>' : '<i class="fas fa-triangle-exclamation" style="color:#fb923c"></i>';
        textEl.innerHTML = count > 0
            ? `${icon} <strong>${count}</strong> ${count === 1 ? 'entity' : 'entities'} detected &mdash; <em>${fmtLabel}</em>`
            : `${icon} Could not detect entity count &mdash; try importing anyway`;

        previewEl.classList.remove('hidden');
    }

    async function _runImport() {
        if (!_importContent) return;

        const btn      = _el('adb-import-btn');
        const resultEl = _el('adb-import-result');
        const conflict = _el('adb-import-conflict')?.value || 'skip';
        const source   = _el('adb-import-source')?.value?.trim() || null;

        if (btn) btn.disabled = true;
        if (resultEl) {
            resultEl.innerHTML = '<div class="adb-status adb-status-loading"><i class="fas fa-spinner fa-spin"></i> Importing…</div>';
            resultEl.classList.remove('hidden');
        }

        try {
            const res  = await fetch(`${API}/import?${_dbParam()}`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({
                    content:       _importContent,
                    filename:      _importFilename || 'import.json',
                    conflict_mode: conflict,
                    ...(source ? { source } : {}),
                }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Import failed');

            const isOk    = data.failed === 0;
            const hasData = data.imported > 0 || data.skipped > 0;

            const statusCls = !isOk ? 'adb-status-error' : data.imported > 0 ? 'adb-status-ok' : 'adb-status-loading';
            const icon2     = data.imported > 0 ? '✓' : data.failed > 0 ? '✗' : 'ℹ';

            let failDetails = '';
            if (data.failed_list?.length) {
                const rows = data.failed_list.map(f =>
                    `<div class="adb-import-fail-row"><code>${_escHtml(f.name)}</code> — ${_escHtml(f.error)}</div>`
                ).join('');
                failDetails = `<details class="adb-import-failures"><summary>${data.failed} failure${data.failed !== 1 ? 's' : ''}</summary>${rows}</details>`;
            }

            if (resultEl) {
                resultEl.innerHTML = `
                    <div class="adb-status ${statusCls}">
                        ${icon2} Imported <strong>${data.imported}</strong>
                        &nbsp;·&nbsp; Skipped <strong>${data.skipped}</strong>
                        &nbsp;·&nbsp; Failed <strong>${data.failed}</strong>
                        &nbsp;<span class="adb-import-fmt-tag">${data.format || ''}</span>
                    </div>
                    ${failDetails}`;
            }

            if (data.imported > 0) {
                _toast(`Imported ${data.imported} ${data.imported === 1 ? 'entity' : 'entities'} ✓`, 'success');
                _loadEntityList(_currentFilter, _currentPage);
            } else if (data.skipped > 0 && data.imported === 0) {
                _toast(`All ${data.skipped} ${data.skipped === 1 ? 'entity' : 'entities'} already exist — skipped`, 'info');
            } else if (data.failed > 0 && data.imported === 0) {
                _toast(`Import failed for all ${data.failed} entities`, 'error');
            }
        } catch (e) {
            if (resultEl) {
                resultEl.innerHTML = `<div class="adb-status adb-status-error">✗ ${_escHtml(e.message)}</div>`;
            }
            _toast(`Import failed: ${e.message}`, 'error');
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    function _importWire() {
        _el('adb-import-browse-btn')?.addEventListener('click', () => {
            _el('adb-import-file-input')?.click();
        });
        _el('adb-import-file-input')?.addEventListener('change', _importFileSelected);
        _el('adb-import-btn')?.addEventListener('click', _runImport);
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

    // ══════════════════════════════════════════════════════════════════════════
    // Test tab — Speed Benchmark
    // ══════════════════════════════════════════════════════════════════════════

    let _benchBakeOptions = [];   // [{name, format, size_fmt, include_vectors}, …]

    /** Called when the Test tab becomes active. */
    function _testOnEnter() {
        _testLoadBakes();
    }

    // ── Bake rows ─────────────────────────────────────────────────────────────

    /** Fetch the list of completed bakes and initialise the first bake row. */
    async function _testLoadBakes() {
        const rowsEl = _el('adb-bench-bake-rows');
        if (!rowsEl) return;

        try {
            const res  = await fetch(`${API}/bake/list?${_dbParam()}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            _benchBakeOptions = (data.bakes || []).filter(b => b.status === 'done');
        } catch {
            _benchBakeOptions = [];
        }

        // If no bake rows yet, add one default row
        if (!rowsEl.querySelector('.adb-bench-bake-row')) {
            _testAddBakeRow();
        } else {
            // Refresh options in existing selects
            rowsEl.querySelectorAll('.adb-bench-bake-row select').forEach(_testFillBakeSelect);
        }
    }

    /** Fill a <select> with the current bake options. */
    function _testFillBakeSelect(sel) {
        const prev = sel.value;
        sel.innerHTML = '<option value="">— none —</option>';
        _benchBakeOptions.forEach(b => {
            const opt   = document.createElement('option');
            opt.value   = b.name;
            const vecs  = b.include_vectors ? ' · vectors' : '';
            opt.textContent = `${b.name}  (${b.format}${vecs} · ${b.size_fmt || '?'})`;
            sel.appendChild(opt);
        });
        if (prev && [...sel.options].some(o => o.value === prev)) sel.value = prev;
        else if (_benchBakeOptions.length > 0) sel.value = _benchBakeOptions[0].name;
    }

    /** Add a new bake-row to the list. */
    function _testAddBakeRow() {
        const rowsEl = _el('adb-bench-bake-rows');
        if (!rowsEl) return;

        // Remove empty-state hint if present
        const hint = rowsEl.querySelector('.adb-bench-bake-empty');
        if (hint) hint.remove();

        const row = document.createElement('div');
        row.className = 'adb-bench-bake-row';

        const sel = document.createElement('select');
        _testFillBakeSelect(sel);

        const removeBtn = document.createElement('button');
        removeBtn.className = 'adb-btn adb-btn-ghost adb-btn-xs adb-bench-bake-remove';
        removeBtn.title = 'Remove';
        removeBtn.innerHTML = '<i class="fas fa-times"></i>';
        removeBtn.addEventListener('click', () => {
            row.remove();
            if (!rowsEl.querySelector('.adb-bench-bake-row')) {
                rowsEl.innerHTML = '<div class="adb-bench-bake-empty">No bakes configured.</div>';
            }
        });

        row.appendChild(sel);
        row.appendChild(removeBtn);
        rowsEl.appendChild(row);
    }

    // ── Benchmark ─────────────────────────────────────────────────────────────

    async function _testRunBench() {
        const btn   = _el('adb-bench-run-btn');
        const query = _el('adb-bench-query')?.value?.trim() || 'a';

        // Collect selected bake names from the rows
        const bakeNames = [...(_el('adb-bench-bake-rows')?.querySelectorAll('.adb-bench-bake-row select') || [])]
            .map(s => s.value)
            .filter(Boolean);

        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Running…'; }

        try {
            const params = new URLSearchParams(_dbParam({ query, bakes: bakeNames.join(',') }));
            const res    = await fetch(`${API}/benchmark?${params}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            _testRenderBench(data);
        } catch (e) {
            _toast(`Benchmark failed: ${e.message}`, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-play"></i> Run Benchmark'; }
        }
    }

    function _testRenderBench(data) {
        const resultsEl = _el('adb-bench-results');
        const tbodyEl   = _el('adb-bench-tbody');
        const metaEl    = _el('adb-bench-meta');
        if (!resultsEl || !tbodyEl) return;

        if (metaEl) metaEl.textContent = `Database: ${data.db || 'default'} · Query: "${data.query}"`;

        const rows  = data.results || [];
        let lastCat = null;
        let html    = '';

        // User-readable category label
        function _catLabel(cat) {
            if (cat === 'raw')    return 'Raw Files';
            if (cat === 'baked')  return 'Baked Snapshot';
            if (cat === 'chunks') return 'Chunk Index';
            if (cat.startsWith('bake:')) return `Bake — ${cat.slice(5)}`;
            return cat;
        }

        rows.forEach(r => {
            if (r.category !== lastCat) {
                lastCat = r.category;
                html += `<tr class="adb-bench-cat-row"><td colspan="3">${_escHtml(_catLabel(r.category))}</td></tr>`;
            }
            const ms = r.ms;
            let timeHtml;
            if (ms === null || ms === undefined) {
                timeHtml = `<td class="adb-bench-td-time adb-bench-na">—</td>`;
            } else {
                const cls = ms < 5 ? 'adb-bench-fast' : ms < 50 ? 'adb-bench-mid' : 'adb-bench-slow';
                timeHtml = `<td class="adb-bench-td-time ${cls}">${ms.toFixed(1)} ms</td>`;
            }
            html += `
                <tr>
                    <td class="adb-bench-td-test">${_escHtml(r.test)}</td>
                    ${timeHtml}
                    <td class="adb-bench-td-note">${_escHtml(r.note || '')}</td>
                </tr>`;
        });

        tbodyEl.innerHTML = html;
        resultsEl.classList.remove('hidden');
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Smart Chunks (lives in Tools tab)
    // ══════════════════════════════════════════════════════════════════════════

    async function _testBuildChunks() {
        const btn = _el('adb-chunk-build-btn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Building…'; }
        const statusEl = _el('adb-chunk-status');
        if (statusEl) { statusEl.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Analysing database…'; statusEl.classList.remove('hidden'); }

        try {
            const res  = await fetch(`${API}/chunks/build?${_dbParam()}`, { method: 'POST' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            _toast(`Built ${data.chunk_count} chunks in ${data.elapsed_ms} ms`, 'success');
            _testRenderChunks(data);
            _graphLoadChunkOptions();   // refresh graph dropdown
        } catch (e) {
            _toast(`Chunk build failed: ${e.message}`, 'error');
            if (statusEl) statusEl.classList.add('hidden');
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-wand-sparkles"></i> Rebuild Chunks'; }
        }
    }

    async function _testLoadChunks() {
        const listEl = _el('adb-chunk-list');
        if (!listEl) return;
        try {
            const res  = await fetch(`${API}/chunks?${_dbParam()}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            _testRenderChunks(await res.json());
        } catch { /* non-fatal */ }
    }

    function _testRenderChunks(data) {
        const listEl   = _el('adb-chunk-list');
        const statusEl = _el('adb-chunk-status');
        if (!listEl) return;

        const chunks = data.chunks || [];

        if (chunks.length === 0) {
            listEl.innerHTML = '<div class="adb-empty-hint">No chunks yet — click Rebuild Chunks to analyse this database.</div>';
            if (statusEl) statusEl.classList.add('hidden');
            return;
        }

        const strategyLabels  = { type: 'Type', property: 'Prop', tag: 'Tag', alpha: 'A–Z' };
        const strategyClasses = {
            type:     'adb-chunk-strategy-type',
            property: 'adb-chunk-strategy-property',
            tag:      'adb-chunk-strategy-tag',
            alpha:    'adb-chunk-strategy-alpha',
        };

        listEl.innerHTML = chunks.map(c => `
            <div class="adb-chunk-row" title="${_escHtml(c.label)}">
                <span class="adb-chunk-strategy ${strategyClasses[c.strategy] || 'adb-chunk-strategy-type'}">
                    ${strategyLabels[c.strategy] || c.strategy}
                </span>
                <span class="adb-chunk-label">${_escHtml(c.label)}</span>
                <span class="adb-chunk-count">${c.entity_count} entities</span>
                <button class="adb-btn adb-btn-ghost adb-btn-xs adb-chunk-graph-btn"
                        data-chunk-id="${_escHtml(c.id)}" title="View in Graph">
                    <i class="fas fa-diagram-project"></i>
                </button>
            </div>`).join('');

        listEl.querySelectorAll('.adb-chunk-graph-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                // Store the desired chunk ID so _graphLoadChunkOptions can apply it
                // after the dropdown is populated (setting sel.value before options
                // exist causes the browser to silently revert it to "").
                _pendingChunkId = btn.dataset.chunkId;
                _switchTab('graph');
            });
        });

        if (statusEl) {
            const builtAt = data.built_at ? new Date(data.built_at).toLocaleString() : '—';
            statusEl.innerHTML = `
                <i class="fas fa-check-circle" style="color:#4ade80"></i>
                ${chunks.length} chunks · ${data.entity_count || 0} entities · Built ${builtAt}`;
            statusEl.classList.remove('hidden');
        }
    }

    function _testWire() {
        _el('adb-bench-run-btn')   ?.addEventListener('click', _testRunBench);
        _el('adb-bench-add-bake')  ?.addEventListener('click', _testAddBakeRow);
        _el('adb-chunk-build-btn') ?.addEventListener('click', _testBuildChunks);
        _el('adb-chunk-refresh-btn')?.addEventListener('click', _testLoadChunks);
        _el('adb-bench-query')     ?.addEventListener('keydown', e => { if (e.key === 'Enter') _testRunBench(); });
    }

    // ── Wiring ────────────────────────────────────────────────────────────────

    function _wire() {
        // Distill
        _el('adb-distill-btn')?.addEventListener('click', _distill);
        _el('adb-distill-text')?.addEventListener('keydown', e => { if (e.key === 'Enter' && e.ctrlKey) _distill(); });

        // Search
        _el('adb-search-btn')?.addEventListener('click', _search);
        _el('adb-search-input')?.addEventListener('keydown', e => { if (e.key === 'Enter') _search(); });
        _el('adb-vsearch-toggle')?.addEventListener('click', _vsearchToggle);

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
        _el('adb-detail-back')?.addEventListener('click', () => {
            if (_editingEntity) { _cancelEditMode(); return; }
            _loadEntityList(_currentFilter, _currentPage);
        });
        _el('adb-ev-edit-btn')?.addEventListener('click', () => {
            if (!_currentEntityId) return;
            fetch(`${API}/entities/${_currentEntityId}?${_dbParam()}`)
                .then(r => r.ok ? r.json() : null)
                .then(ent => { if (ent) _enterEditMode(ent); })
                .catch(e => _toast(`Load failed: ${e.message}`, 'error'));
        });
        _el('adb-ev-save-btn')?.addEventListener('click', _saveEdit);
        _el('adb-ev-cancel-btn')?.addEventListener('click', _cancelEditMode);
        _el('adb-ev-expand-btn')?.addEventListener('click', _deepenCurrent);
        _el('adb-ev-validate-btn')?.addEventListener('click', _validateCurrent);
        document.querySelectorAll('.adb-ev-tab').forEach(btn => {
            btn.addEventListener('click', () => _activateEntityTab(btn.dataset.target));
        });

        // Deepen preview panel
        _el('adb-dp-apply-btn')?.addEventListener('click', _applyDeepenPreview);

        // Validation view — back button restores the page the user was on
        _el('adb-val-close')?.addEventListener('click', () => _loadEntityList(_currentFilter, _currentPage));

        // Bulk selection action bar
        _el('adb-bulk-clear')?.addEventListener('click', _clearSelection);
        _el('adb-bulk-expand')?.addEventListener('click', _bulkExpandStubs);
        _el('adb-bulk-delete')?.addEventListener('click', _bulkDelete);

        // DB chip in stats bar → navigate to Databases tab
        _el('adb-db-change-btn')?.addEventListener('click', () => _switchTab('databases'));

        // Databases tab — list view
        _el('adb-dbm-new-btn')?.addEventListener('click', _dbmShowCreate);

        // Databases tab — create view
        _el('adb-dbm-create-back')?.addEventListener('click', () => { _dbmView('adb-dbm-list'); _dbmLoadList(); });
        _el('adb-dbm-create-cancel')?.addEventListener('click', () => { _dbmView('adb-dbm-list'); _dbmLoadList(); });
        _el('adb-dbm-create-submit')?.addEventListener('click', _dbmCreate);
        _el('adb-dbm-create-browse')?.addEventListener('click', () => _dbmBrowse('adb-dbm-create-path'));
        _el('adb-dbm-create-name')?.addEventListener('keydown', e => { if (e.key === 'Enter') _dbmCreate(); });

        // Databases tab — settings view
        _el('adb-dbm-settings-back')?.addEventListener('click', () => { _dbmView('adb-dbm-list'); _dbmLoadList(); });
        _el('adb-dbm-settings-cancel')?.addEventListener('click', () => { _dbmView('adb-dbm-list'); _dbmLoadList(); });
        _el('adb-dbm-settings-save')?.addEventListener('click', _dbmSaveSettings);
        _el('adb-dbm-backup-now-btn')?.addEventListener('click', _dbmCreateBackup);
        _el('adb-dbm-delete-btn')?.addEventListener('click', _dbmDeleteDatabase);
    }

    // ── Init ──────────────────────────────────────────────────────────────────

    const _VALID_SUBTABS = new Set(['databases', 'tools', 'bake', 'explorer', 'graph', 'api', 'test']);

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

        // Restore last active sub-tab (databases / tools / bake / explorer / graph / api)
        try {
            const savedTab = localStorage.getItem('adb_last_subtab');
            if (savedTab && _VALID_SUBTABS.has(savedTab)) _currentTab = savedTab;
        } catch { /* ignore */ }

        _updateDbIndicator();
        _wire();
        _graphWire();
        _fdWire();
        _vecWire();
        _bakeWire();
        _importWire();
        _apiWire();
        _testWire();
        _fetchModels();
        _loadCachedInfo();          // populate stats from AethvionDB.INFO instantly
        _fdCheckExistingJob();      // restore folder-distill progress view if a job exists
        _bakeCheckExisting();       // restore bake result panel if a bake exists
        _vecCheckExisting();        // restore vector status if a job exists
        _switchTab(_currentTab);    // apply sub-tab visibility (uses restored or default value)
        _loadEntityList('all', 0);
    }

    document.addEventListener('panelLoaded', function (e) {
        if (e.detail?.tabName === 'aethviondb') init();
    });
})();
