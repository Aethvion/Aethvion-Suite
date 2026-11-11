/**
 * Assets & Models tab
 *   Asset Library   — browse everything workflows produced, with preview and lineage
 *   Model Endpoints — every model the Suite can call; add / edit / test custom ones
 *
 * Backend: /api/assets (core/assets/asset_routes.py), /api/modelhub (core/modelhub/modelhub_routes.py)
 */
(function () {
    'use strict';

    var PAGE = 60;
    var KIND_ICONS = { image: 'fa-image', mesh: 'fa-cube', audio: 'fa-volume-high', video: 'fa-film',
                       text: 'fa-file-lines', json: 'fa-file-code', file: 'fa-file' };

    var S = { kind: '', q: '', loadTicket: 0, total: 0, assets: [], selected: null,
              endpoints: [], caps: [], cap: '', templates: [], viewer: null, editingId: null, testing: null };
    var inited = false;

    function $(id) { return document.getElementById(id); }
    function esc(s) {
        return String(s === null || s === undefined ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function fmtSize(n) {
        n = Number(n) || 0;
        if (n < 1024) return n + ' B';
        if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
        return (n / 1048576).toFixed(1) + ' MB';
    }
    function fmtDate(iso) {
        var d = new Date(iso);
        return isNaN(d) ? '' : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    }
    async function api(url, opts) {
        var r = await fetch(url, opts);
        var data = null;
        try { data = await r.json(); } catch (_) { /* no body */ }
        if (!r.ok) throw new Error((data && (data.detail || data.error)) || ('Request failed (' + r.status + ')'));
        return data;
    }
    function toast(msg, isErr) {
        if (typeof window.showToast === 'function') { window.showToast(msg, isErr ? 'error' : 'success'); return; }
        console[isErr ? 'error' : 'log']('[assets] ' + msg);
    }

    // ── Asset Library ──────────────────────────────────────────────────────

    async function loadSummary() {
        var sum = await api('/api/assets/summary');
        var kinds = sum.kinds || {};
        var html = '<button class="al-kind' + (S.kind === '' ? ' active' : '') + '" data-kind="">All <b>' + (sum.total || 0) + '</b></button>';
        Object.keys(KIND_ICONS).forEach(function (k) {
            if (!kinds[k]) return;
            html += '<button class="al-kind' + (S.kind === k ? ' active' : '') + '" data-kind="' + k + '">' +
                    '<i class="fas ' + KIND_ICONS[k] + '"></i> ' + k + ' <b>' + kinds[k] + '</b></button>';
        });
        $('al-kinds').innerHTML = html;
    }

    async function loadAssets(reset) {
        // Two refreshes can overlap (tab shown + filter click); only the newest one may render.
        var ticket = ++S.loadTicket;
        var offset = reset ? 0 : S.assets.length;
        var url = '/api/assets?limit=' + PAGE + '&offset=' + offset +
                  (S.kind ? '&kind=' + encodeURIComponent(S.kind) : '') +
                  (S.q ? '&q=' + encodeURIComponent(S.q) : '');
        var res = await api(url);
        if (ticket !== S.loadTicket) return;
        S.total = res.total;
        S.assets = reset ? res.assets : S.assets.concat(res.assets);
        renderGrid();
    }

    function renderGrid() {
        var grid = $('al-grid');
        grid.innerHTML = S.assets.map(function (a) {
            var thumb = a.kind === 'image'
                ? '<img loading="lazy" src="' + esc(a.url) + '" alt="">'
                : '<i class="fas ' + (KIND_ICONS[a.kind] || 'fa-file') + '"></i>';
            var src = a.source || {};
            var origin = src.endpoint || src.workflow_name || src.type || '';
            return '<button class="al-card' + (S.selected === a.id ? ' selected' : '') + '" data-asset="' + a.id + '">' +
                   '<div class="al-thumb">' + thumb + '</div>' +
                   '<div class="al-card-meta">' +
                   '<div class="al-card-name" title="' + esc(a.name) + '">' + esc(a.name) + '.' + esc(a.ext) + '</div>' +
                   '<div class="al-card-sub"><span>' + esc(origin) + '</span><span>' + esc(fmtDate(a.created_at)) + '</span></div>' +
                   '</div></button>';
        }).join('');
        $('al-empty').style.display = S.assets.length ? 'none' : '';
        $('al-more').style.display = S.assets.length < S.total ? '' : 'none';
    }

    function disposeViewer() {
        if (S.viewer && typeof S.viewer.dispose === 'function') {
            try { S.viewer.dispose(); } catch (_) { /* ignore */ }
        }
        S.viewer = null;
    }

    function closeDetail() {
        disposeViewer();
        S.selected = null;
        $('al-detail').style.display = 'none';
        $('al-detail').innerHTML = '';
        renderGrid();
    }

    function lineageItem(a, current) {
        return '<button class="al-lin-item' + (current ? ' current' : '') + '" ' + (current ? '' : 'data-goto="' + a.id + '"') + '>' +
               '<i class="fas ' + (KIND_ICONS[a.kind] || 'fa-file') + '"></i>' +
               '<span>' + esc(a.name) + '.' + esc(a.ext) + '</span>' +
               '<em>' + esc((a.source || {}).endpoint || a.kind) + '</em></button>';
    }

    async function openDetail(id) {
        var res;
        try { res = await api('/api/assets/' + encodeURIComponent(id)); }
        catch (e) { toast(e.message, true); return; }
        disposeViewer();
        S.selected = id;
        renderGrid();

        var a = res.asset, src = a.source || {}, meta = a.meta || {};
        var preview = '';
        if (a.kind === 'image')      preview = '<img src="' + esc(a.url) + '" alt="">';
        else if (a.kind === 'audio') preview = '<audio controls src="' + esc(a.url) + '"></audio>';
        else if (a.kind === 'video') preview = '<video controls src="' + esc(a.url) + '"></video>';
        else if (a.kind === 'mesh')  preview = '<div class="al-viewer" id="al-viewer"><div class="al-viewer-note">Loading 3D preview…</div></div>';
        else if (a.kind === 'text' || a.kind === 'json') preview = '<pre id="al-text-preview">Loading…</pre>';

        var props = [
            ['Kind', a.kind + ' · .' + a.ext + ' · ' + fmtSize(a.size_bytes)],
            ['Created', fmtDate(a.created_at)],
            ['Model', src.endpoint || ''],
            ['Step', src.capability || ''],
            ['Workflow', src.workflow_name ? src.workflow_name + (src.node_label ? ' → ' + src.node_label : '') : ''],
            ['Run', src.run_id || ''],
            ['Exported to', meta.exported_to || ''],
            ['ID', a.id],
        ].filter(function (p) { return p[1]; })
         .map(function (p) { return '<dt>' + esc(p[0]) + '</dt><dd>' + esc(p[1]) + '</dd>'; }).join('');

        var chain = res.ancestors.slice().reverse().map(function (x) { return lineageItem(x, false); })
            .concat([lineageItem(a, true)])
            .concat(res.descendants.map(function (x) { return lineageItem(x, false); }))
            .join('<div class="al-lin-arrow"><i class="fas fa-arrow-down"></i></div>');

        var el = $('al-detail');
        el.innerHTML =
            '<div class="al-detail-hdr"><div><h3>' + esc(a.name) + '.' + esc(a.ext) + '</h3></div>' +
            '<button class="al-btn al-btn-icon" data-act="close" title="Close"><i class="fas fa-xmark"></i></button></div>' +
            (preview ? '<div class="al-preview">' + preview + '</div>' : '') +
            '<div class="al-actions">' +
            '<a class="al-btn" href="' + esc(a.url) + '?download=true"><i class="fas fa-download"></i> Download</a>' +
            '<button class="al-btn" data-act="export"><i class="fas fa-file-export"></i> Export to folder</button>' +
            '<button class="al-btn" data-act="copy"><i class="fas fa-copy"></i> Copy ID</button>' +
            '<button class="al-btn al-btn-danger" data-act="delete"><i class="fas fa-trash"></i></button>' +
            '</div>' +
            (meta.prompt ? '<div class="al-section-title">Prompt</div><div class="al-prompt">' + esc(meta.prompt) + '</div>' : '') +
            '<div class="al-section-title">Details</div><dl class="al-props">' + props + '</dl>' +
            '<div class="al-section-title">Tags</div><div class="al-tags">' +
            (a.tags || []).map(function (t) { return '<span class="al-tag">' + esc(t) + '</span>'; }).join('') +
            '<button class="al-btn al-btn-icon" data-act="tags" title="Edit tags"><i class="fas fa-pen"></i></button></div>' +
            ((res.ancestors.length || res.descendants.length)
                ? '<div class="al-section-title">History — made from / turned into</div><div class="al-lineage">' + chain + '</div>' : '');
        el.style.display = '';
        el.dataset.assetId = a.id;
        el.dataset.tags = (a.tags || []).join(', ');

        if (a.kind === 'mesh') {
            if (a.ext === 'glb' || a.ext === 'gltf') {
                import('/static/js/3d-viewer.js').then(function (mod) {
                    if (S.selected !== a.id || !$('al-viewer')) return;
                    $('al-viewer').innerHTML = '';
                    S.viewer = new mod.ThreeDViewer('al-viewer');
                    S.viewer.loadModel(a.url);
                }).catch(function (e) {
                    if ($('al-viewer')) $('al-viewer').innerHTML = '<div class="al-viewer-note">3D preview unavailable: ' + esc(e.message) + '</div>';
                });
            } else {
                $('al-viewer').innerHTML = '<div class="al-viewer-note">No in-browser preview for .' + esc(a.ext) + ' files.</div>';
            }
        } else if (a.kind === 'text' || a.kind === 'json') {
            fetch(a.url).then(function (r) { return r.text(); }).then(function (t) {
                var pre = $('al-text-preview');
                if (pre) pre.textContent = t.length > 20000 ? t.slice(0, 20000) + '\n… (truncated)' : t;
            });
        }
    }

    async function onDetailClick(e) {
        var el = $('al-detail');
        var id = el.dataset.assetId;
        var go = e.target.closest('[data-goto]');
        if (go) { openDetail(go.dataset.goto); return; }
        var btn = e.target.closest('[data-act]');
        if (!btn) return;
        var act = btn.dataset.act;
        try {
            if (act === 'close') { closeDetail(); }
            else if (act === 'copy') { await navigator.clipboard.writeText(id); toast('Asset ID copied'); }
            else if (act === 'delete') {
                if (!window.confirm('Delete this asset permanently? The file is removed from the library.')) return;
                await api('/api/assets/' + id, { method: 'DELETE' });
                closeDetail(); await refreshAssets();
            } else if (act === 'tags') {
                var t = window.prompt('Tags (comma-separated)', el.dataset.tags || '');
                if (t === null) return;
                await api('/api/assets/' + id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tags: t.split(',').map(function (x) { return x.trim(); }).filter(Boolean) }) });
                openDetail(id);
            } else if (act === 'export') {
                var last = '';
                try { last = localStorage.getItem('al-export-dir') || ''; } catch (_) { /* ignore */ }
                var dir = window.prompt('Export to which folder? (e.g. your game project\'s Assets folder)', last);
                if (!dir) return;
                var res = await api('/api/assets/' + id + '/export', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target_dir: dir }) });
                try { localStorage.setItem('al-export-dir', dir); } catch (_) { /* ignore */ }
                toast('Exported to ' + res.path);
                openDetail(id);
            }
        } catch (err) { toast(err.message, true); }
    }

    async function refreshAssets() {
        try { await Promise.all([loadSummary(), loadAssets(true)]); }
        catch (e) { toast(e.message, true); }
    }

    // ── Model Endpoints ────────────────────────────────────────────────────

    async function loadEndpoints() {
        try {
            var res = await Promise.all([api('/api/modelhub/endpoints'), api('/api/modelhub/capabilities')]);
            S.endpoints = res[0].endpoints;
            S.caps = res[1].capabilities;
            renderEndpoints();
        } catch (e) { toast(e.message, true); }
    }

    function capLabel(id) {
        var c = S.caps.find(function (x) { return x.id === id; });
        return c ? c.label : id;
    }

    function renderEndpoints() {
        var counts = {};
        S.endpoints.forEach(function (e) { e.capabilities.forEach(function (c) { counts[c] = (counts[c] || 0) + 1; }); });
        $('al-caps').innerHTML =
            '<button class="al-kind' + (S.cap === '' ? ' active' : '') + '" data-cap="">All <b>' + S.endpoints.length + '</b></button>' +
            S.caps.filter(function (c) { return counts[c.id]; }).map(function (c) {
                return '<button class="al-kind' + (S.cap === c.id ? ' active' : '') + '" data-cap="' + c.id + '" title="' + esc(c.description) + '">' +
                       esc(c.label) + ' <b>' + counts[c.id] + '</b></button>';
            }).join('');

        var list = S.endpoints.filter(function (e) { return !S.cap || e.capabilities.indexOf(S.cap) !== -1; });
        var groups = {};
        list.forEach(function (e) {
            var g = e.builtin ? e.group : 'Your endpoints';
            (groups[g] = groups[g] || []).push(e);
        });
        var order = Object.keys(groups).sort(function (a, b) {
            if (a === 'Your endpoints') return -1;
            if (b === 'Your endpoints') return 1;
            return a.localeCompare(b);
        });
        $('al-endpoints').innerHTML = order.map(function (g) {
            return '<div class="al-group-title">' + esc(g) + '</div>' + groups[g].map(function (e) {
                return '<div class="al-ep">' +
                    '<span class="al-dot' + (e.available ? '' : ' off') + '" title="' + esc(e.available ? 'Available' : e.reason) + '"></span>' +
                    '<div class="al-ep-main">' +
                    '<div class="al-ep-name">' + esc(e.name) + ' <code>' + esc(e.id) + '</code></div>' +
                    '<div class="al-ep-desc">' + esc(e.available ? e.description : e.reason) + '</div>' +
                    '<div class="al-ep-caps">' + e.capabilities.map(function (c) { return '<span class="al-cap">' + esc(capLabel(c)) + '</span>'; }).join('') + '</div>' +
                    '</div><div class="al-ep-actions">' +
                    (e.available ? '<button class="al-btn" data-test="' + esc(e.id) + '"><i class="fas fa-play"></i> Test</button>' : '') +
                    (e.builtin ? '' :
                        '<button class="al-btn al-btn-icon" data-edit="' + esc(e.id) + '" title="Edit"><i class="fas fa-pen"></i></button>' +
                        '<button class="al-btn al-btn-icon al-btn-danger" data-del="' + esc(e.id) + '" title="Delete"><i class="fas fa-trash"></i></button>') +
                    '</div></div>';
            }).join('');
        }).join('') || '<p class="al-hint">No endpoints for this capability yet. Add one with “Add endpoint”.</p>';
    }

    function setMsg(id, text, cls) {
        var m = $(id);
        m.textContent = text || '';
        m.className = 'al-msg' + (cls ? ' ' + cls : '');
    }

    async function openEditor(existingId) {
        S.editingId = existingId || null;
        setMsg('al-modal-msg', '');
        $('al-modal-title').textContent = existingId ? 'Edit endpoint' : 'Add endpoint';
        $('al-template-row').style.display = existingId ? 'none' : '';
        if (existingId) {
            var ep = S.endpoints.find(function (e) { return e.id === existingId; });
            $('al-def').value = JSON.stringify(ep.definition, null, 2);
        } else {
            if (!S.templates.length) S.templates = (await api('/api/modelhub/templates')).templates;
            $('al-template').innerHTML = S.templates.map(function (t, i) {
                return '<option value="' + i + '">' + esc(t.name) + '  [' + esc(t.adapter) + ']</option>';
            }).join('');
            applyTemplate(0);
        }
        $('al-modal').style.display = '';
    }

    function applyTemplate(i) {
        var t = S.templates[i];
        if (!t) return;
        var def = Object.assign({}, t);
        delete def.template;
        $('al-def').value = JSON.stringify(def, null, 2);
        $('al-template-desc').textContent = t.description || '';
    }

    function readDefinition() {
        try { return JSON.parse($('al-def').value); }
        catch (e) { setMsg('al-modal-msg', 'Not valid JSON: ' + e.message, 'err'); return null; }
    }

    async function validateDefinition() {
        var def = readDefinition();
        if (!def) return false;
        var res = await api('/api/modelhub/endpoints/validate', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ definition: def }) });
        if (res.ok) setMsg('al-modal-msg', 'Looks good.', 'ok');
        else setMsg('al-modal-msg', res.errors.join('\n'), 'err');
        return res.ok;
    }

    async function saveDefinition() {
        var def = readDefinition();
        if (!def) return;
        try {
            await api('/api/modelhub/endpoints', { method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ definition: def }) });
            if (S.editingId && S.editingId !== def.id) {
                await api('/api/modelhub/endpoints/' + encodeURIComponent(S.editingId), { method: 'DELETE' });
            }
            $('al-modal').style.display = 'none';
            toast('Endpoint saved');
            loadEndpoints();
        } catch (e) { setMsg('al-modal-msg', e.message, 'err'); }
    }

    function openTest(id) {
        var ep = S.endpoints.find(function (e) { return e.id === id; });
        if (!ep) return;
        S.testing = ep;
        $('al-test-title').textContent = 'Test: ' + ep.name;
        $('al-test-cap').innerHTML = ep.capabilities.map(function (c) { return '<option value="' + c + '">' + esc(capLabel(c)) + '</option>'; }).join('');
        $('al-test-result').innerHTML = '';
        setMsg('al-test-msg', '');
        $('al-test').style.display = '';
    }

    async function runTest() {
        var ep = S.testing;
        if (!ep) return;
        var cap = $('al-test-cap').value;
        var input = $('al-test-input').value.trim();
        var body = { endpoint: ep.id, capability: cap, prompt: $('al-test-prompt').value, tags: ['test'] };
        if (input) {
            var needsMesh = cap.indexOf('mesh.') === 0 && cap !== 'mesh.generate';
            body[needsMesh ? 'mesh' : (cap === 'audio.transcribe' ? 'audio' : 'image')] = input;
        }
        var btn = $('al-test-run');
        btn.disabled = true;
        setMsg('al-test-msg', 'Running… (the first call to a local model can take a while)');
        $('al-test-result').innerHTML = '';
        try {
            var res = await api('/api/modelhub/invoke', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            if (!res.ok) { setMsg('al-test-msg', res.error, 'err'); return; }
            setMsg('al-test-msg', 'Done in ' + (res.duration_ms / 1000).toFixed(1) + ' s', 'ok');
            var html = '';
            (res.assets || []).forEach(function (a) {
                html += a.kind === 'image'
                    ? '<div class="al-preview"><img src="' + esc(a.url) + '" alt=""></div>'
                    : '<button class="al-btn" data-open-asset="' + a.id + '"><i class="fas ' + (KIND_ICONS[a.kind] || 'fa-file') + '"></i> ' +
                      esc(a.name) + '.' + esc(a.ext) + ' — open in library</button>';
            });
            if (res.text) html += '<div class="al-prompt" style="margin-top:.6rem">' + esc(res.text.slice(0, 4000)) + '</div>';
            $('al-test-result').innerHTML = html;
        } catch (e) { setMsg('al-test-msg', e.message, 'err'); }
        finally { btn.disabled = false; }
    }

    // ── Wiring ─────────────────────────────────────────────────────────────

    function switchTab(tab) {
        document.querySelectorAll('#al-root .al-nav-tab').forEach(function (b) { b.classList.toggle('active', b.dataset.alTab === tab); });
        $('al-pane-assets').classList.toggle('active', tab === 'assets');
        $('al-pane-models').classList.toggle('active', tab === 'models');
        if (tab === 'models') loadEndpoints(); else refreshAssets();
    }

    function init() {
        if (inited || !$('al-root')) return;
        inited = true;

        document.querySelectorAll('#al-root .al-nav-tab').forEach(function (b) {
            b.addEventListener('click', function () { switchTab(b.dataset.alTab); });
        });

        $('al-kinds').addEventListener('click', function (e) {
            var b = e.target.closest('[data-kind]');
            if (!b) return;
            S.kind = b.dataset.kind;
            refreshAssets();
        });
        var searchTimer = null;
        $('al-search').addEventListener('input', function (e) {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(function () { S.q = e.target.value.trim(); loadAssets(true).catch(function (err) { toast(err.message, true); }); }, 250);
        });
        $('al-refresh').addEventListener('click', refreshAssets);
        $('al-more').addEventListener('click', function () { loadAssets(false).catch(function (err) { toast(err.message, true); }); });
        $('al-grid').addEventListener('click', function (e) {
            var c = e.target.closest('[data-asset]');
            if (c) openDetail(c.dataset.asset);
        });
        $('al-detail').addEventListener('click', onDetailClick);
        $('al-upload').addEventListener('change', async function (e) {
            var f = e.target.files[0];
            if (!f) return;
            var fd = new FormData();
            fd.append('file', f);
            try {
                var res = await api('/api/assets/upload', { method: 'POST', body: fd });
                await refreshAssets();
                openDetail(res.asset.id);
            } catch (err) { toast(err.message, true); }
            e.target.value = '';
        });

        $('al-caps').addEventListener('click', function (e) {
            var b = e.target.closest('[data-cap]');
            if (!b) return;
            S.cap = b.dataset.cap;
            renderEndpoints();
        });
        $('al-refresh-models').addEventListener('click', loadEndpoints);
        $('al-add-endpoint').addEventListener('click', function () { openEditor(null).catch(function (err) { toast(err.message, true); }); });
        $('al-endpoints').addEventListener('click', async function (e) {
            var t = e.target.closest('[data-test]'), ed = e.target.closest('[data-edit]'), del = e.target.closest('[data-del]');
            if (t) openTest(t.dataset.test);
            else if (ed) openEditor(ed.dataset.edit);
            else if (del) {
                if (!window.confirm('Delete the endpoint "' + del.dataset.del + '"? Workflows that use it will fail until you pick another model.')) return;
                try { await api('/api/modelhub/endpoints/' + encodeURIComponent(del.dataset.del), { method: 'DELETE' }); loadEndpoints(); }
                catch (err) { toast(err.message, true); }
            }
        });
        $('al-template').addEventListener('change', function (e) { applyTemplate(Number(e.target.value)); });
        $('al-modal-close').addEventListener('click', function () { $('al-modal').style.display = 'none'; });
        $('al-modal-validate').addEventListener('click', function () { validateDefinition().catch(function (err) { setMsg('al-modal-msg', err.message, 'err'); }); });
        $('al-modal-save').addEventListener('click', saveDefinition);
        $('al-test-close').addEventListener('click', function () { $('al-test').style.display = 'none'; });
        $('al-test-run').addEventListener('click', runTest);
        $('al-test-result').addEventListener('click', function (e) {
            var b = e.target.closest('[data-open-asset]');
            if (!b) return;
            $('al-test').style.display = 'none';
            switchTab('assets');
            openDetail(b.dataset.openAsset);
        });

        refreshAssets();
    }

    // Refresh when the tab is shown again (new assets may have been produced meanwhile)
    document.addEventListener('panelLoaded', function (e) {
        if (e.detail && e.detail.tabName === 'asset-library') {
            if (!inited) init(); else if ($('al-pane-assets').classList.contains('active')) refreshAssets();
        }
    });
    if (document.getElementById('al-root')) init();
})();
