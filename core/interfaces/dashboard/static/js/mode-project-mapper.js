/**
 * mode-project-mapper.js
 * Project Mapper dashboard panel — Scan | Explorer | Query
 *
 * API prefix: /api/project-mapper
 * Entity data via: /api/aethviondb/entities
 */
(function () {
    'use strict';

    // ── Shortcuts ─────────────────────────────────────────────────────────────
    const $ = id => document.getElementById(id);
    const PM  = '/api/project-mapper';
    const PMX = '/api/pm-explorer';   // Suite-side read-only view over PM snapshots

    // ── State ─────────────────────────────────────────────────────────────────
    let _pollTimer     = null;
    let _scanStartTime = null;
    let _elapsedTimer  = null;
    let _searchDebounce = null;

    /** Read current DB name from whichever pm-db-sync input is visible/first. */
    function dbName() {
        const inputs = document.querySelectorAll('.pm-db-sync');
        for (const inp of inputs) {
            const v = inp.value.trim();
            if (v) return v;
        }
        return 'default';
    }

    /** Keep all pm-db-sync inputs in sync when any one changes. */
    function syncDbInputs(changedInput) {
        const val = changedInput.value;
        document.querySelectorAll('.pm-db-sync').forEach(inp => {
            if (inp !== changedInput) inp.value = val;
        });
    }

    function projRoot()  { return $('pm-proj-root').value.trim(); }

    // ── Utility ───────────────────────────────────────────────────────────────
    function escHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function fmtBytes(n) {
        if (n < 1024)       return n + ' B';
        if (n < 1048576)    return (n / 1024).toFixed(1) + ' KB';
        if (n < 1073741824) return (n / 1048576).toFixed(1) + ' MB';
        return (n / 1073741824).toFixed(2) + ' GB';
    }

    function timeAgo(iso) {
        if (!iso) return '—';
        const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
        if (diff < 60)     return 'just now';
        if (diff < 3600)   return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400)  return Math.floor(diff / 3600) + 'h ago';
        return Math.floor(diff / 86400) + 'd ago';
    }

    // ── Tab navigation ────────────────────────────────────────────────────────
    function switchTab(tabId) {
        document.querySelectorAll('#pm-nav-tabs .pm-nav-tab').forEach(btn =>
            btn.classList.toggle('active', btn.dataset.pmTab === tabId));

        ['scan', 'explorer', 'query'].forEach(id => {
            const el = $(`pm-pane-${id}`);
            if (el) el.style.display = (id === tabId) ? '' : 'none';
        });

        if (tabId === 'explorer') refreshExplorer();
    }

    // ── Stats bar refresh ─────────────────────────────────────────────────────
    async function refreshStatsBar() {
        try {
            const r = await fetch(`${PM}/stats?db=${encodeURIComponent(dbName())}`);
            if (!r.ok) return;
            const s = await r.json();

            const scanStatus = (s.last_scan || {}).status || 'idle';
            const statusEl   = $('pm-sc-status');
            const valEl      = $('pm-sc-status-val');
            if (statusEl && valEl) {
                valEl.textContent = scanStatus;
                statusEl.className = 'pm-stat-chip pm-sc-' + (
                    { running: 'run', completed: 'ok', error: 'err', cancelled: 'warn' }[scanStatus] || ''
                );
            }

            const entities = $('pm-sc-entities');
            if (entities) entities.textContent = s.total_pm_entities ?? '—';

            const files = $('pm-sc-files');
            if (files) files.textContent = (s.file_manifest || {}).total_files ?? '—';

            const last = $('pm-sc-last');
            if (last) last.textContent = timeAgo((s.last_scan || {}).started_at);
        } catch (_) {}
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // SCAN PANE
    // ═══════════════════════════════════════════════════════════════════════════

    // ── Preview ───────────────────────────────────────────────────────────────
    async function previewFiles() {
        const root = projRoot();
        if (!root) { alert('Enter a project root path first.'); return; }

        const btn = $('pm-preview-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        try {
            const r = await fetch(`${PM}/preview?project_root=${encodeURIComponent(root)}`);
            const data = await r.json();

            if (!r.ok) throw new Error(data.detail || JSON.stringify(data));

            const panel  = $('pm-preview-panel');
            const badge  = $('pm-preview-badge');
            const content = $('pm-preview-content');

            const total = data.total_files ?? 0;
            if (badge) badge.textContent = `${total} files`;

            const byExt = data.by_extension || {};
            const extEntries = Object.entries(byExt).sort((a, b) => b[1] - a[1]);
            const extHtml = extEntries.length
                ? `<div class="pm-ext-grid">` +
                  extEntries.map(([ext, n]) =>
                      `<div class="pm-ext-row">
                         <span class="pm-ext-badge">${escHtml(ext || '(none)')}</span>
                         <span class="pm-ext-count">${n}</span>
                       </div>`
                  ).join('') + `</div>`
                : '';

            content.innerHTML =
                `<div class="pm-preview-summary">` +
                `<span><b>${total}</b> total files</span>` +
                (data.excluded_count != null ? `<span><b>${data.excluded_count}</b> dirs excluded</span>` : '') +
                `</div>` +
                extHtml;

            panel.style.display = '';
        } catch (e) {
            alert('Preview failed: ' + e.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-eye"></i> Preview';
        }
    }

    // ── Start scan ────────────────────────────────────────────────────────────
    async function startScan() {
        const root = projRoot();
        if (!root) { alert('Enter a project root path first.'); return; }

        setStatusPanelVisible(true);
        showStatus('Initializing…', 'running');

        $('pm-scan-btn').disabled = true;
        $('pm-cancel-btn').style.display = '';
        $('pm-delta-panel').style.display = 'none';

        _scanStartTime = Date.now();
        _elapsedTimer  = setInterval(() => {
            const s = ((Date.now() - _scanStartTime) / 1000).toFixed(1);
            const el = $('ps-elapsed');
            if (el) el.textContent = s + 's';
        }, 500);

        const body = {
            project_root: root,
            db:           dbName(),
            incremental:  $('pm-opt-incremental').checked,
            concurrency:  parseInt($('pm-concurrency').value, 10),
        };

        try {
            const r = await fetch(`${PM}/scan`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify(body),
            });
            const data = await r.json();
            if (!r.ok) throw new Error(data.detail || JSON.stringify(data));
            pollScanStatus(dbName());
        } catch (e) {
            clearInterval(_elapsedTimer);
            showStatus('Failed: ' + e.message, 'error');
            $('pm-scan-btn').disabled = false;
            $('pm-cancel-btn').style.display = 'none';
        }
    }

    // ── Poll scan status ──────────────────────────────────────────────────────
    function pollScanStatus(db) {
        if (_pollTimer) clearInterval(_pollTimer);
        _pollTimer = setInterval(async () => {
            try {
                const r = await fetch(`${PM}/scan/status?db=${encodeURIComponent(db)}`);
                const s = await r.json();
                applyStatus(s);
                if (['completed', 'error', 'cancelled', 'idle'].includes(s.status)) {
                    clearInterval(_pollTimer);
                    clearInterval(_elapsedTimer);
                    _pollTimer = null;
                    $('pm-scan-btn').disabled = false;
                    $('pm-cancel-btn').style.display = 'none';
                    refreshStatsBar();
                }
            } catch (_) {}
        }, 700);
    }

    // ── Apply status to UI ────────────────────────────────────────────────────
    function applyStatus(s) {
        if (!s) return;
        const status = s.status || 'unknown';
        const stats  = s.stats  || {};

        const LABELS = {
            running:   'Scanning…',
            cleanup:   'Cleanup…',
            completed: 'Completed',
            error:     'Error',
            cancelled: 'Cancelled',
            idle:      'Idle',
        };
        const BADGE_CLS = {
            running:   'pm-badge-info',
            cleanup:   'pm-badge-info',
            completed: 'pm-badge-success',
            error:     'pm-badge-error',
            cancelled: 'pm-badge-warning',
            idle:      'pm-badge-muted',
        };

        const iconEl = $('pm-status-icon');
        if (iconEl) {
            const spinning = ['running', 'cleanup'].includes(status);
            iconEl.className = spinning
                ? 'fas fa-circle-notch fa-spin'
                : status === 'completed' ? 'fas fa-circle-check' : 'fas fa-circle';
        }

        const labelEl = $('pm-status-label');
        if (labelEl) labelEl.textContent = LABELS[status] || status;

        const badgeEl = $('pm-status-badge');
        if (badgeEl) {
            badgeEl.textContent = status;
            badgeEl.className   = 'pm-badge ' + (BADGE_CLS[status] || 'pm-badge-muted');
        }

        // Progress bar
        const total   = stats.total_files  || 0;
        const done    = (stats.files_scanned || 0) + (stats.files_skipped || 0);
        const pct     = (total > 0) ? Math.min(100, Math.round(done / total * 100)) : (status === 'completed' ? 100 : 0);
        const fillEl  = $('pm-progress-fill');
        if (fillEl) fillEl.style.width = pct + '%';

        const _s = (id, val) => { const el = $(id); if (el) el.textContent = val; };
        _s('ps-scanned', stats.files_scanned  || 0);
        _s('ps-skipped', stats.files_skipped  || 0);
        _s('ps-created', stats.entities_created || 0);
        _s('ps-updated', stats.entities_updated || 0);
        _s('ps-retired', (stats.entities_retired || 0) + (stats.files_deleted || 0));

        const cfEl = $('pm-current-file');
        if (cfEl) cfEl.textContent = s.current_file ? `▶ ${s.current_file}` : '';

        // Update stats bar status chip
        const scStatus = $('pm-sc-status-val');
        if (scStatus) scStatus.textContent = status;
    }

    function setStatusPanelVisible(v) {
        const el = $('pm-status-panel');
        if (el) el.style.display = v ? '' : 'none';
    }

    function showStatus(label, type) {
        setStatusPanelVisible(true);
        const lEl = $('pm-status-label');
        const bEl = $('pm-status-badge');
        const fEl = $('pm-progress-fill');
        if (lEl) lEl.textContent = label;
        if (bEl) { bEl.textContent = type; bEl.className = 'pm-badge pm-badge-' + (type === 'error' ? 'error' : 'info'); }
        if (fEl) fEl.style.width = '0%';
    }

    // ── Cancel scan ───────────────────────────────────────────────────────────
    async function cancelScan() {
        if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
        if (_elapsedTimer) { clearInterval(_elapsedTimer); _elapsedTimer = null; }
        try {
            await fetch(`${PM}/scan/cancel?db=${encodeURIComponent(dbName())}`, { method: 'POST' });
        } catch (_) {}
        showStatus('Cancelled', 'warning');
        $('pm-scan-btn').disabled = false;
        $('pm-cancel-btn').style.display = 'none';
        refreshStatsBar();
    }

    // ── Delta preview ─────────────────────────────────────────────────────────
    async function showDelta() {
        const root = projRoot();
        if (!root) { alert('Enter a project root path first.'); return; }

        const btn = $('pm-delta-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        try {
            const url = `${PM}/delta?project_root=${encodeURIComponent(root)}&db=${encodeURIComponent(dbName())}&include_lists=false`;
            const r = await fetch(url);
            const d = await r.json();
            if (!r.ok) throw new Error(d.detail || JSON.stringify(d));

            const newF  = d.new_files       || 0;
            const modF  = d.modified_files  || 0;
            const delF  = d.deleted_files   || 0;
            const unch  = d.unchanged_count || 0;
            const hasChg = d.has_changes;

            $('pm-delta-content').innerHTML =
                `<div class="pm-delta-grid">
                   <div class="pm-delta-item pm-di-new"><i class="fas fa-plus"></i><b>${newF}</b> new</div>
                   <div class="pm-delta-item pm-di-mod"><i class="fas fa-pen"></i><b>${modF}</b> modified</div>
                   <div class="pm-delta-item pm-di-del"><i class="fas fa-trash"></i><b>${delF}</b> deleted</div>
                   <div class="pm-delta-item pm-di-ok"><i class="fas fa-check"></i><b>${unch}</b> unchanged</div>
                 </div>
                 <p class="pm-hint ${hasChg ? 'pm-hint-warn' : 'pm-hint-ok'}">
                   ${hasChg
                       ? 'Changes detected — run a scan to update the index.'
                       : 'Index is up to date. No scan needed.'
                   }
                 </p>`;
            $('pm-delta-panel').style.display = '';
        } catch (e) {
            alert('Delta failed: ' + e.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-code-compare"></i> Delta Preview';
        }
    }

    // ── Manual cleanup ────────────────────────────────────────────────────────
    async function runCleanup() {
        const root = projRoot();
        if (!root) { alert('Enter a project root path first.'); return; }
        if (!confirm('Retire all entities for files that no longer exist on disk?\n\nThis is non-destructive — entities are soft-deleted, not removed.')) return;

        const btn = $('pm-cleanup-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        try {
            const url = `${PM}/cleanup?project_root=${encodeURIComponent(root)}&db=${encodeURIComponent(dbName())}`;
            const r = await fetch(url, { method: 'POST' });
            const d = await r.json();
            if (!r.ok) throw new Error(d.detail || JSON.stringify(d));
            alert(`Cleanup complete.\nFiles deleted: ${d.deleted_file_count}\nEntities retired: ${d.retired_count}`);
            refreshStatsBar();
        } catch (e) {
            alert('Cleanup failed: ' + e.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-broom"></i> Cleanup';
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // EXPLORER PANE
    // ═══════════════════════════════════════════════════════════════════════════

    async function refreshExplorer() {
        await Promise.all([loadExplorerStats(), loadEntityList()]);
    }

    async function loadExplorerStats() {
        try {
            const r = await fetch(`${PMX}/stats?db=${encodeURIComponent(dbName())}`);
            if (!r.ok) return;
            const s = await r.json();
            const bt = s.by_type || {};
            const total = s.total_entities ?? Object.values(bt).reduce((a, v) => a + v, 0);
            const _sv = (id, v) => { const el = $(id); if (el) el.textContent = v ?? '—'; };
            _sv('pm-stat-total',     total);
            _sv('pm-stat-modules',   bt.module   ?? '—');
            _sv('pm-stat-classes',   bt.class    ?? '—');
            _sv('pm-stat-functions', bt.function ?? '—');
        } catch (_) {}
    }

    async function loadEntityList() {
        const db      = dbName();
        const typeVal = $('pm-type-filter').value;
        const qVal    = ($('pm-search-filter').value || '').trim();

        const listEl = $('pm-entity-list');
        listEl.innerHTML = '<div class="pm-list-empty"><i class="fas fa-spinner fa-spin"></i></div>';

        try {
            let url = `${PMX}/entities?db=${encodeURIComponent(db)}&limit=200&offset=0`;
            if (typeVal) url += `&entity_type=${encodeURIComponent(typeVal)}`;

            const r   = await fetch(url);
            const res = await r.json();
            if (!r.ok) throw new Error(res.detail || JSON.stringify(res));

            let entities = res.entities || [];

            // Client-side name filter (no server-side q param for aethviondb)
            if (qVal) {
                const ql = qVal.toLowerCase();
                entities = entities.filter(e => (e.name || e.id || '').toLowerCase().includes(ql));
            }

            if (!entities.length) {
                listEl.innerHTML =
                    '<div class="pm-list-empty"><i class="fas fa-inbox"></i><span>No entities found.<br>Scan a project first.</span></div>';
                return;
            }

            listEl.innerHTML = entities.map(e =>
                `<button class="pm-entity-row" data-eid="${escHtml(e.id)}">
                   <span class="pm-etype-badge pm-et-${escHtml(e.type || 'other')}">${escHtml(e.type || '?')}</span>
                   <span class="pm-ename">${escHtml(e.name || e.id)}</span>
                 </button>`
            ).join('');

            listEl.querySelectorAll('.pm-entity-row').forEach(btn =>
                btn.addEventListener('click', () => loadEntityDetail(btn.dataset.eid)));

        } catch (e) {
            listEl.innerHTML =
                `<div class="pm-list-empty"><i class="fas fa-triangle-exclamation"></i><span>Error: ${escHtml(e.message)}</span></div>`;
        }
    }

    async function loadEntityDetail(entityId) {
        const db     = dbName();
        const detail = $('pm-entity-detail');

        // Mark active row
        document.querySelectorAll('.pm-entity-row').forEach(b =>
            b.classList.toggle('active', b.dataset.eid === entityId));

        detail.innerHTML = '<div class="pm-detail-placeholder"><i class="fas fa-spinner fa-spin"></i></div>';

        try {
            const r = await fetch(`${PMX}/entities/${encodeURIComponent(entityId)}?db=${encodeURIComponent(db)}`);
            const e = await r.json();
            if (!r.ok) throw new Error(e.detail || JSON.stringify(e));

            const sections  = e.sections  || {};
            const coreProps = sections.core || {};
            const props     = { ...coreProps, ...(e.properties || {}) };
            const relations = sections.relations || [];
            const timeline  = e.timeline   || [];
            const sourceFiles = sections.source_files || [];

            // Properties table (exclude description for separate display)
            const { description, summary, ...restProps } = props;
            const desc = description || summary || '';

            const propRows = Object.entries(restProps)
                .filter(([, v]) => v !== null && v !== undefined && v !== '')
                .map(([k, v]) =>
                    `<tr>
                       <td class="pm-prop-key">${escHtml(k)}</td>
                       <td class="pm-prop-val">${escHtml(String(v))}</td>
                     </tr>`)
                .join('');

            const relRows = relations.map(rel =>
                `<div class="pm-rel-item">
                   <span class="pm-rel-type">${escHtml(rel.relation || rel.type || '?')}</span>
                   <span class="pm-rel-target">${escHtml(rel.target_name || rel.target_id || '?')}</span>
                 </div>`
            ).join('');

            const tlRows = timeline.slice(-5).reverse().map(t =>
                `<div class="pm-tl-item">
                   <span class="pm-tl-event">${escHtml(t.event || '?')}</span>
                   <span class="pm-tl-ts">${(t.timestamp || '').slice(0, 16).replace('T', ' ')}</span>
                 </div>`
            ).join('');

            const srcRows = sourceFiles.map(sf =>
                `<div class="pm-tl-item">
                   <span class="pm-tl-event">${escHtml(sf.path || sf)}</span>
                   ${sf.lines ? `<span class="pm-tl-ts">${sf.lines} lines</span>` : ''}
                 </div>`
            ).join('');

            detail.innerHTML =
                `<div class="pm-detail-header">
                   <span class="pm-etype-badge pm-et-${escHtml(e.type || 'other')}">${escHtml(e.type || '?')}</span>
                   <h3 class="pm-detail-name">${escHtml(e.name || e.id)}</h3>
                   <span class="pm-detail-id" title="${escHtml(e.id)}">${escHtml(e.id.slice(0, 16))}…</span>
                 </div>` +

                (desc ? `<p class="pm-detail-desc">${escHtml(desc)}</p>` : '') +

                (Object.keys(restProps).length
                    ? `<div class="pm-detail-section">
                         <div class="pm-detail-sec-title">Properties</div>
                         <table class="pm-prop-table">${propRows}</table>
                       </div>` : '') +

                (sourceFiles.length
                    ? `<div class="pm-detail-section">
                         <div class="pm-detail-sec-title">Source Files (${sourceFiles.length})</div>
                         <div class="pm-tl-list">${srcRows}</div>
                       </div>` : '') +

                (relations.length
                    ? `<div class="pm-detail-section">
                         <div class="pm-detail-sec-title">Relations (${relations.length})</div>
                         <div class="pm-rel-list">${relRows}</div>
                       </div>` : '') +

                (timeline.length
                    ? `<div class="pm-detail-section">
                         <div class="pm-detail-sec-title">Timeline (last 5)</div>
                         <div class="pm-tl-list">${tlRows}</div>
                       </div>` : '');

        } catch (e) {
            detail.innerHTML =
                `<div class="pm-detail-placeholder">
                   <i class="fas fa-triangle-exclamation"></i>
                   <p>Error: ${escHtml(e.message)}</p>
                 </div>`;
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // QUERY PANE
    // ═══════════════════════════════════════════════════════════════════════════

    function onToolChange() {
        const tool = $('pm-tool-select').value;
        ['impact', 'context', 'path', 'contribute', 'stats'].forEach(t => {
            const el = $(`pm-qf-${t}`);
            if (el) el.style.display = (t === tool) ? '' : 'none';
        });
    }

    async function runQuery() {
        const tool   = $('pm-tool-select').value;
        const db     = dbName();
        const outEl  = $('pm-query-output');
        const runBtn = $('pm-run-query');

        outEl.textContent = 'Running…';
        runBtn.disabled   = true;

        try {
            let r, body;

            switch (tool) {
                case 'impact': {
                    const name  = $('pm-q-impact-name').value.trim();
                    if (!name) throw new Error('Entity name is required.');
                    const depth = parseInt($('pm-q-impact-depth').value, 10);
                    r = await fetch(`${PM}/query/impact`, {
                        method:  'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body:    JSON.stringify({ entity: name, db, depth }),
                    });
                    break;
                }
                case 'context': {
                    const q      = $('pm-q-context-q').value.trim();
                    if (!q) throw new Error('Task description is required.');
                    const depth  = parseInt($('pm-q-context-hops').value, 10);
                    const detail = $('pm-q-context-detail').value;
                    r = await fetch(`${PM}/query/context`, {
                        method:  'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body:    JSON.stringify({ q, db, depth, detail_level: detail, max_results: 40 }),
                    });
                    break;
                }
                case 'path': {
                    const from = $('pm-q-path-from').value.trim();
                    const to   = $('pm-q-path-to').value.trim();
                    if (!from || !to) throw new Error('Both From and To entity names are required.');
                    const hops = parseInt($('pm-q-path-hops').value, 10);
                    r = await fetch(`${PM}/query/path`, {
                        method:  'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body:    JSON.stringify({ from_entity: from, to_entity: to, db, max_hops: hops }),
                    });
                    break;
                }
                case 'contribute': {
                    const name      = $('pm-q-contrib-name').value.trim();
                    const propsText = $('pm-q-contrib-props').value.trim();
                    const rationale = $('pm-q-contrib-rationale').value.trim();
                    if (!name) throw new Error('Entity name is required.');
                    let properties = {};
                    if (propsText) {
                        try { properties = JSON.parse(propsText); }
                        catch { throw new Error('Properties must be valid JSON.'); }
                    }
                    r = await fetch(`${PM}/contribute`, {
                        method:  'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body:    JSON.stringify({ entity_name: name, db, properties, relations: [], rationale, source: 'dashboard' }),
                    });
                    break;
                }
                case 'stats': {
                    r = await fetch(`${PM}/stats?db=${encodeURIComponent(db)}`);
                    break;
                }
                default:
                    throw new Error(`Unknown tool: ${tool}`);
            }

            const data = await r.json();
            if (!r.ok) throw new Error(data.detail || JSON.stringify(data));
            outEl.textContent = JSON.stringify(data, null, 2);
        } catch (e) {
            outEl.textContent = 'Error: ' + e.message;
        } finally {
            runBtn.disabled = false;
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // INIT
    // ═══════════════════════════════════════════════════════════════════════════

    function init() {
        // Register info content for the ExpInfo overlay
        if (window.ExpInfo) {
            window.ExpInfo.register('project-mapper', {
                icon:    'fas fa-diagram-project',
                name:    'Project Mapper',
                color:   'linear-gradient(135deg, #0ea5e9, #6366f1)',
                tagline: 'A static AST knowledge graph that reduces AI token usage by 87–91% — benchmarked.',
                status:  'Beta',
                concepts: [
                    {
                        icon:  'fas fa-circle-nodes',
                        label: 'Custom Knowledge Graph',
                        desc:  'Instead of sending raw source files to the AI, Project Mapper builds a typed entity graph: files, classes, functions, imports — all as structured nodes with relationships.',
                    },
                    {
                        icon:  'fas fa-bolt',
                        label: '87–91% Token Reduction',
                        desc:  'Benchmarked across multiple projects: AI agents using Project Mapper consume 87–91% fewer tokens than agents reading raw codebases. This is not a prompt trick — it is a structural change.',
                    },
                    {
                        icon:  'fas fa-database',
                        label: 'AethvionDB-Backed',
                        desc:  'Scan results are stored as typed entities in AethvionDB. The graph persists between sessions and supports delta scans — only changed files are re-indexed.',
                    },
                ],
                how: 'Project Mapper scans a codebase and extracts typed entities — files, classes, functions, imports, dependencies — into AethvionDB. When an AI agent needs to work on the codebase, it queries the graph instead of reading raw source files. The result is a precise, structured snapshot of the project that the AI can traverse without reading hundreds of files. Delta scans update only what has changed, making repeated scans fast.',
                vision: 'Project Mapper has already proven its value and is being spun out as a standalone product (github.com/Aethvion/Aethvion-ProjectMapper). The vision is a universal code intelligence layer that any AI agent can query — not just Aethvion Suite agents. Any tool that needs to understand a codebase can use Project Mapper as its knowledge foundation, replacing fragile file-reading strategies with a structured, queryable graph.',
                pitch: {
                    problem: 'Coding agents are constrained by context windows and token costs. Passing raw source files to an LLM every time it needs to understand a codebase is wildly inefficient, slow, and prone to hallucination when codebases exceed 100k lines.',
                    solution: 'Project Mapper acts as a deterministic knowledge layer. Instead of reading code, the AI queries a fast, local graph. This offloads structural reasoning (imports, dependencies, inheritance) from the LLM to deterministic code, saving massive amounts of compute.',
                    tam: 'Software Development & AI Coding Tools Market: $4.5B+ (Growing 25% YoY). Every enterprise building AI agents for code needs an efficient knowledge retrieval layer.',
                    tactics: [
                        'Spin out as a standalone open-source CLI tool to gain developer adoption.',
                        'Provide a premium managed API for enterprise AI agent builders.',
                        'Integrate as the default knowledge backend for popular AI IDE extensions.'
                    ]
                }
            });
        }

        // Info button
        const pmInfoBtn = document.getElementById('pm-info-btn');
        if (pmInfoBtn) {
            pmInfoBtn.addEventListener('click', () => {
                if (window.ExpInfo) window.ExpInfo.show('project-mapper');
            });
        }

        // Nav tab clicks
        document.querySelectorAll('#pm-nav-tabs .pm-nav-tab').forEach(btn =>
            btn.addEventListener('click', () => switchTab(btn.dataset.pmTab)));

        // Scan pane
        $('pm-preview-btn') .addEventListener('click', previewFiles);
        $('pm-scan-btn')    .addEventListener('click', startScan);
        $('pm-cancel-btn')  .addEventListener('click', cancelScan);
        $('pm-delta-btn')   .addEventListener('click', showDelta);
        $('pm-cleanup-btn') .addEventListener('click', runCleanup);

        // Explorer pane
        $('pm-refresh-explorer').addEventListener('click', refreshExplorer);
        $('pm-type-filter').addEventListener('change', loadEntityList);
        $('pm-search-filter').addEventListener('input', () => {
            clearTimeout(_searchDebounce);
            _searchDebounce = setTimeout(loadEntityList, 280);
        });

        // Query pane
        $('pm-tool-select').addEventListener('change', onToolChange);
        $('pm-run-query')  .addEventListener('click', runQuery);

        // Keep all DB inputs in sync; refresh stats bar on change
        document.querySelectorAll('.pm-db-sync').forEach(inp => {
            inp.addEventListener('input', () => { syncDbInputs(inp); });
            inp.addEventListener('change', () => { syncDbInputs(inp); refreshStatsBar(); });
        });

        // Load initial stats bar
        refreshStatsBar();
    }

    // Wait for the partial DOM to be available
    function tryInit() {
        if (document.getElementById('pm-root')) {
            init();
        } else {
            document.addEventListener('partial-loaded', function handler(e) {
                if (e.detail && e.detail.panel === 'project-mapper') {
                    document.removeEventListener('partial-loaded', handler);
                    init();
                }
            });
        }
    }

    tryInit();
})();
