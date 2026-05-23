/**
 * mode-automate.js
 * Aethvion Suite — Automate: node-editor workspace
 *
 * Fully isolated — does not share state with any other feature module.
 * All API calls go to /api/automate/*, which is equally isolated.
 *
 * Architecture:
 *   • Left sidebar  — saved workflow list
 *   • Canvas        — infinite canvas with pan (middle-mouse/alt-drag) + zoom (wheel)
 *   • Right palette — draggable node types, click to insert
 *   • Bottom panel  — slides up to show properties of the selected node
 *   • SVG overlay   — bezier connection curves rendered inside canvas-inner
 */
(function () {
    'use strict';

    // ── Constants ───────────────────────────────────────────────────────────
    const MIN_SCALE    = 0.12;
    const MAX_SCALE    = 3.5;
    const ZOOM_STEP    = 0.12;
    const NODE_WIDTH   = 230;    // matches CSS .at-node width
    const NODE_H_EST   = 90;     // estimated height for fit-to-screen
    const BEZIER_MIN_CP = 70;    // minimum bezier control-point offset

    // ── State ────────────────────────────────────────────────────────────────
    let _nodeTypes      = [];   // [{ type, label, category, icon, color, inputs, outputs, properties }]
    let _availModels    = [];   // [{ id, provider_id, provider_name, label, description }]
    let _modelsBySource = {};   // cache: source-url → model list
    let _workflows   = [];   // [{ id, name, node_count, updated }]
    let _active      = null; // { id, name, nodes:[], connections:[] }  — full workflow
    let _selNodeId   = null; // selected node id
    let _selConnId   = null; // selected connection id
    let _dragging    = null; // { nodeId, startCX, startCY, startNX, startNY }
    let _panning     = null; // { startCX, startCY, startVX, startVY }
    let _pending     = null; // { nodeId, portName, portType:'output' }
    let _dirty       = false;
    let _zTop        = 10;   // z-index counter for raised nodes
    let _placeOffset = 0;    // stagger offset for newly added nodes
    let _view        = { x: 0, y: 0, scale: 1 };

    // ── DOM refs ─────────────────────────────────────────────────────────────
    let _e = {}; // filled by _init

    // ════════════════════════════════════════════════════════════════════════
    //  Initialisation
    // ════════════════════════════════════════════════════════════════════════

    function _init() {
        _e = {
            wfLabel:       _$('at-wf-label'),
            wfRenameBtn:   _$('at-wf-rename-btn'),
            btnNew:        _$('at-btn-new'),
            btnSave:       _$('at-btn-save'),
            btnDelete:     _$('at-btn-delete'),
            btnRun:        _$('at-btn-run'),
            btnFit:        _$('at-btn-fit'),
            btnZoomIn:     _$('at-btn-zoom-in'),
            btnZoomOut:    _$('at-btn-zoom-out'),
            zoomLabel:     _$('at-zoom-label'),
            sidebarAdd:    _$('at-sidebar-add'),
            wfList:        _$('at-wf-list'),
            wfEmpty:       _$('at-wf-empty'),
            wfCreateFirst: _$('at-wf-create-first'),
            canvas:        _$('at-canvas'),
            canvasEmpty:   _$('at-canvas-empty'),
            canvasNewBtn:  _$('at-canvas-new-btn'),
            canvasInner:   _$('at-canvas-inner'),
            svg:           _$('at-svg'),
            paletteSearch: _$('at-palette-search'),
            paletteList:   _$('at-palette-list'),
            propsPanel:    _$('at-props-panel'),
            propsIcon:     _$('at-props-icon'),
            propsTitle:    _$('at-props-title'),
            propsBody:     _$('at-props-body'),
            propsClose:    _$('at-props-close'),
            toast:         _$('at-toast'),
        };

        // Load data then render
        Promise.all([_apiFetchNodeTypes(), _apiFetchWorkflows(), _apiFetchModels()]).then(function () {
            _renderPalette(null);
            _renderWfList();
        }).catch(function (err) {
            console.error('[Automate] Init failed:', err);
            _toast('Failed to load Automate data.', true);
        });

        _wireEvents();
        _updateToolbar();
    }

    function _$(id) { return document.getElementById(id); }

    // ════════════════════════════════════════════════════════════════════════
    //  API helpers
    // ════════════════════════════════════════════════════════════════════════

    async function _apiFetchNodeTypes() {
        const r = await fetch('/api/automate/node-types');
        if (!r.ok) throw new Error('node-types ' + r.status);
        const d = await r.json();
        _nodeTypes = d.node_types || [];
    }

    async function _apiFetchWorkflows() {
        const r = await fetch('/api/automate/workflows');
        if (!r.ok) throw new Error('workflows ' + r.status);
        const d = await r.json();
        _workflows = d.workflows || [];
    }

    async function _apiFetchModels(source) {
        const url = source || '/api/automate/models';
        if (_modelsBySource[url]) return _modelsBySource[url];
        try {
            const r = await fetch(url);
            if (!r.ok) return [];
            const d = await r.json();
            const list = d.models || [];
            _modelsBySource[url] = list;
            if (!source) _availModels = list;
            return list;
        } catch (_) { return []; }
    }

    async function _apiTestNode(node, inputData) {
        const r = await fetch('/api/automate/node/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ node: node, input_data: inputData || '' }),
        });
        return r.json();
    }

    async function _apiGetWorkflow(id) {
        const r = await fetch('/api/automate/workflows/' + id);
        if (!r.ok) throw new Error('get-workflow ' + r.status);
        return (await r.json()).workflow;
    }

    async function _apiCreateWorkflow(name) {
        const r = await fetch('/api/automate/workflows', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, nodes: [], connections: [] }),
        });
        if (!r.ok) throw new Error('create-workflow ' + r.status);
        return (await r.json()).workflow;
    }

    async function _apiSaveWorkflow() {
        if (!_active) return;
        const r = await fetch('/api/automate/workflows/' + _active.id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: _active.name,
                nodes: _active.nodes,
                connections: _active.connections,
            }),
        });
        if (!r.ok) throw new Error('save-workflow ' + r.status);
        _dirty = false;
        _updateToolbar();
        _toast('Workflow saved.');
    }

    async function _apiDeleteWorkflow() {
        if (!_active) return;
        const ok = confirm('Delete "' + _active.name + '"? This cannot be undone.');
        if (!ok) return;
        const r = await fetch('/api/automate/workflows/' + _active.id, { method: 'DELETE' });
        if (!r.ok) throw new Error('delete-workflow ' + r.status);
        const id = _active.id;
        _active = null;
        _workflows = _workflows.filter(function (w) { return w.id !== id; });
        _renderWfList();
        _showEmpty();
        _updateToolbar();
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Workflow execution
    // ════════════════════════════════════════════════════════════════════════

    async function _apiRunWorkflow() {
        if (!_active) return;

        // Auto-save before running so the backend has current node config
        if (_dirty) {
            try { await _apiSaveWorkflow(); } catch (_) {}
        }

        // Reset previous execution visuals
        _clearExecState();
        _closeProps();

        // Animate run button
        _e.btnRun.disabled = true;
        _e.btnRun.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Running…</span>';

        // Mark all nodes as "pending"
        _active.nodes.forEach(function (nd) { _setNodeExecState(nd.id, 'pending'); });

        try {
            const r = await fetch('/api/automate/workflows/' + _active.id + '/run', { method: 'POST' });
            const data = await r.json();
            _applyExecResults(data);
        } catch (e) {
            _toast('Execution failed: ' + e.message, true);
        } finally {
            _e.btnRun.disabled = false;
            _e.btnRun.innerHTML = '<i class="fas fa-play"></i><span>Run</span>';
        }
    }

    function _clearExecState() {
        if (!_e.canvasInner) return;
        _e.canvasInner.querySelectorAll('.at-node').forEach(function (el) {
            el.classList.remove('at-exec-running', 'at-exec-done', 'at-exec-error', 'at-exec-pending');
            var badge = el.querySelector('.at-node-exec-badge');
            if (badge) badge.remove();
            var errBar = el.querySelector('.at-node-error-bar');
            if (errBar) errBar.remove();
        });
    }

    function _setNodeExecState(nodeId, state) {
        var el = _e.canvasInner && _e.canvasInner.querySelector('[data-node-id="' + nodeId + '"].at-node');
        if (!el) return;
        el.classList.remove('at-exec-pending', 'at-exec-running', 'at-exec-done', 'at-exec-error');
        el.classList.add('at-exec-' + state);
    }

    function _applyExecResults(data) {
        var statuses = data.node_status  || {};
        var outputs  = data.node_outputs || {};
        var errors   = data.node_errors  || {};

        // Apply per-node states + outputs
        Object.keys(statuses).forEach(function (nodeId) {
            var status = statuses[nodeId];
            _setNodeExecState(nodeId, status);

            var el = _e.canvasInner && _e.canvasInner.querySelector('[data-node-id="' + nodeId + '"].at-node');
            if (!el) return;

            // Remove old badge / error bar
            var old = el.querySelector('.at-node-exec-badge');
            if (old) old.remove();
            var oldErr = el.querySelector('.at-node-error-bar');
            if (oldErr) oldErr.remove();

            // Insert status badge in header
            var hdr = el.querySelector('.at-node-hdr');
            if (hdr) {
                var badge = document.createElement('span');
                badge.className = 'at-node-exec-badge ' + status;
                badge.textContent = status === 'done' ? '✓' : '✗';
                badge.title = status;
                // Insert before delete button
                var del = hdr.querySelector('[data-del-node]');
                if (del) hdr.insertBefore(badge, del);
                else hdr.appendChild(badge);
            }

            // Show error bar
            if (status === 'error' && errors[nodeId]) {
                var errBar = document.createElement('div');
                errBar.className = 'at-node-error-bar';
                errBar.innerHTML = '<i class="fas fa-triangle-exclamation"></i>' +
                    '<span>' + _esc(errors[nodeId]) + '</span>';
                el.appendChild(errBar);
            }

            // Show output on AI / display nodes
            var nd = _active && _active.nodes.find(function (n) { return n.id === nodeId; });
            if (!nd) return;
            var outs = outputs[nodeId] || {};

            if (nd.type.startsWith('ai.') && outs.out) {
                _updateAINodeResult(nodeId, _to_str(outs.out), true);
            }
            if (nd.type === 'output.display') {
                var val = outs._display !== undefined ? outs._display : outs.out;
                _showDisplayOutput(nodeId, val);
            }
        });

        // Render execution log panel
        _renderExecPanel(data);
    }

    function _to_str(val) {
        if (val === null || val === undefined) return '';
        if (typeof val === 'string') return val;
        if (typeof val === 'object') return JSON.stringify(val, null, 2);
        return String(val);
    }

    function _showDisplayOutput(nodeId, val) {
        // Display nodes reuse the result panel mechanism
        var wrap = _e.canvasInner && _e.canvasInner.querySelector('[data-node-result="' + nodeId + '"]');
        var body = wrap && wrap.querySelector('[data-node-result-body="' + nodeId + '"]');
        if (!wrap || !body) return;
        body.textContent = _to_str(val);
        wrap.style.display = '';
    }

    // ── Execution log panel ───────────────────────────────────────────────────

    function _renderExecPanel(data) {
        var panel    = document.getElementById('at-exec-panel');
        var logView  = document.getElementById('at-exec-log-view');
        var outView  = document.getElementById('at-exec-out-view');
        var statusEl = document.getElementById('at-exec-panel-status');
        var textEl   = document.getElementById('at-exec-status-text');
        if (!panel) return;

        // Status header
        var ok = data.ok !== false;
        var errCount  = Object.keys(data.node_errors  || {}).length;
        var doneCount = Object.values(data.node_status || {}).filter(function (s) { return s === 'done'; }).length;
        statusEl.className = 'at-exec-panel-status ' + (ok ? 'ok' : 'error');
        statusEl.querySelector('i').className = ok ? 'fas fa-circle-check' : 'fas fa-circle-xmark';
        textEl.textContent = ok
            ? doneCount + ' node' + (doneCount !== 1 ? 's' : '') + ' completed'
            : doneCount + ' done, ' + errCount + ' error' + (errCount !== 1 ? 's' : '');

        // Log tab
        var log = data.log || [];
        logView.innerHTML = '';
        log.forEach(function (entry) {
            var row = document.createElement('div');
            row.className = 'at-exec-log-entry ' + (entry.level || 'info');
            row.innerHTML =
                '<span class="at-exec-log-ts">' + _esc(entry.ts || '') + '</span>' +
                '<span class="at-exec-log-msg">' + _esc(entry.msg || '') + '</span>';
            logView.appendChild(row);
        });
        // Scroll to bottom
        logView.scrollTop = logView.scrollHeight;

        // Outputs tab
        outView.innerHTML = '';
        var outputs = data.node_outputs || {};
        var statuses = data.node_status || {};
        Object.keys(outputs).forEach(function (nodeId) {
            var nd = _active && _active.nodes.find(function (n) { return n.id === nodeId; });
            var label  = nd ? (nd.label || nd.type) : nodeId;
            var status = statuses[nodeId] || 'done';
            var outs   = outputs[nodeId] || {};
            var hasOutput = Object.keys(outs).some(function (k) {
                return !k.startsWith('_') && outs[k] !== null && outs[k] !== undefined && outs[k] !== '';
            });
            if (!hasOutput && status !== 'error') return;

            var card = document.createElement('div');
            card.className = 'at-exec-out-card';

            var badgeCls = status === 'done' ? 'at-exec-badge-ok' : 'at-exec-badge-err';
            var badgeIcon = status === 'done' ? 'fa-circle-check' : 'fa-circle-xmark';
            card.innerHTML =
                '<div class="at-exec-out-card-hdr">' +
                '  <i class="fas ' + badgeIcon + ' ' + badgeCls + '"></i>' +
                '  <span>' + _esc(label) + '</span>' +
                '</div>';

            // Show each output port's value
            Object.keys(outs).forEach(function (port) {
                if (port.startsWith('_')) return;
                var val = outs[port];
                if (val === null || val === undefined || val === '') return;
                var body = document.createElement('div');
                body.className = 'at-exec-out-card-body';
                var prefix = Object.keys(outs).filter(function (k) { return !k.startsWith('_'); }).length > 1
                    ? '[' + port + '] ' : '';
                body.textContent = prefix + _to_str(val);
                card.appendChild(body);
            });

            outView.appendChild(card);
        });

        // Open panel
        panel.classList.add('at-open');
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Workflow list
    // ════════════════════════════════════════════════════════════════════════

    function _renderWfList() {
        const list = _e.wfList;
        // Remove existing items (keep empty placeholder)
        Array.from(list.children).forEach(function (c) {
            if (c !== _e.wfEmpty) c.remove();
        });

        if (_workflows.length === 0) {
            _e.wfEmpty.style.display = '';
            return;
        }
        _e.wfEmpty.style.display = 'none';

        _workflows.forEach(function (wf) {
            const item = document.createElement('div');
            item.className = 'at-wf-item' + (_active && _active.id === wf.id ? ' active' : '');
            item.dataset.wfId = wf.id;
            item.innerHTML =
                '<i class="fas fa-bolt"></i>' +
                '<span class="at-wf-item-name">' + _esc(wf.name) + '</span>' +
                '<span class="at-wf-item-count">' + (wf.node_count || 0) + '</span>';
            item.addEventListener('click', function () { _openWorkflow(wf.id); });
            list.insertBefore(item, _e.wfEmpty);
        });
    }

    function _openWorkflow(id) {
        _apiGetWorkflow(id).then(function (wf) {
            _active      = wf;
            _dirty       = false;
            _placeOffset = wf.nodes.length;
            _showCanvas();
            _renderCanvas();
            _updateToolbar();
            _renderWfList();
        }).catch(function (e) {
            _toast('Failed to open workflow.', true);
            console.error('[Automate]', e);
        });
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Canvas visibility
    // ════════════════════════════════════════════════════════════════════════

    function _showCanvas() {
        _e.canvasEmpty.style.display    = 'none';
        _e.canvasInner.style.display    = '';
        _e.wfLabel.textContent          = _active ? _active.name : '';
        _e.wfRenameBtn.style.display    = _active ? '' : 'none';
    }

    function _showEmpty() {
        _e.canvasEmpty.style.display    = '';
        _e.canvasInner.style.display    = 'none';
        _e.wfLabel.textContent          = 'No workflow selected';
        _e.wfRenameBtn.style.display    = 'none';
        _closeProps();
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Canvas / node rendering
    // ════════════════════════════════════════════════════════════════════════

    function _renderCanvas() {
        // Remove old node elements (keep SVG)
        Array.from(_e.canvasInner.children).forEach(function (c) {
            if (c !== _e.svg) c.remove();
        });
        if (!_active) return;
        _active.nodes.forEach(function (n) { _renderNode(n); });
        // Defer connections one frame so nodes have layout
        requestAnimationFrame(function () { _renderConns(); });
    }

    function _renderNode(nd) {
        const td = _typeDef(nd.type);
        const color   = td.color || '#64748b';
        const colorBg = color + '20';

        const el = document.createElement('div');
        el.className    = 'at-node';
        el.dataset.nodeId = nd.id;
        el.style.left   = nd.x + 'px';
        el.style.top    = nd.y + 'px';

        const inputsHtml = (td.inputs || []).map(function (p) {
            return (
                '<div class="at-port-row at-input" data-node-id="' + nd.id +
                '" data-port="' + p.name + '" data-port-type="input">' +
                '<div class="at-port at-input"></div>' +
                '<span class="at-port-label">' + _esc(p.label) + '</span>' +
                '</div>'
            );
        }).join('');

        const outputsHtml = (td.outputs || []).map(function (p) {
            return (
                '<div class="at-port-row at-output" data-node-id="' + nd.id +
                '" data-port="' + p.name + '" data-port-type="output">' +
                '<span class="at-port-label">' + _esc(p.label) + '</span>' +
                '<div class="at-port at-output"></div>' +
                '</div>'
            );
        }).join('');

        const isAI      = nd.type.startsWith('ai.');
        const isDisplay = nd.type === 'output.display';
        const showResult = (isAI && nd.properties['show_result'] !== false) || isDisplay;

        // AI extra bar: model badge + test button
        const aiBarHtml = isAI
            ? '<div class="at-node-ai-bar">' +
              '  <span class="at-node-model-badge" data-model-badge="' + nd.id + '">' +
                   _esc(nd.properties['model'] || 'no model') +
              '  </span>' +
              '  <button class="at-node-test-btn" data-test-node="' + nd.id + '" title="Test this node">' +
              '    <i class="fas fa-bolt"></i> Test' +
              '  </button>' +
              '</div>'
            : '';

        // Result panel — hidden until test/execution returns data
        const resultHtml = (isAI || isDisplay)
            ? '<div class="at-node-result" data-node-result="' + nd.id + '" style="display:none">' +
              '  <div class="at-node-result-hdr">' +
              '    <span><i class="fas fa-sparkles"></i> Result</span>' +
              '    <button class="at-node-result-close" data-close-result="' + nd.id + '">✕</button>' +
              '  </div>' +
              '  <div class="at-node-result-body" data-node-result-body="' + nd.id + '"></div>' +
              '</div>'
            : '';

        el.innerHTML =
            '<div class="at-node-hdr">' +
            '  <div class="at-node-icon" style="background:' + colorBg + ';color:' + color + '">' +
            '    <i class="fas ' + (td.icon || 'fa-cube') + '"></i>' +
            '  </div>' +
            '  <span class="at-node-label">' + _esc(nd.label || td.label) + '</span>' +
            '  <button class="at-node-del" data-del-node="' + nd.id + '" title="Delete node">' +
            '    <i class="fas fa-xmark"></i>' +
            '  </button>' +
            '</div>' +
            '<div class="at-node-ports">' +
            '  <div class="at-node-inputs">'  + inputsHtml  + '</div>' +
            '  <div class="at-node-outputs">' + outputsHtml + '</div>' +
            '</div>' +
            aiBarHtml +
            resultHtml;

        _e.canvasInner.insertBefore(el, _e.svg);
    }

    function _typeDef(typeStr) {
        return _nodeTypes.find(function (t) { return t.type === typeStr; }) ||
               { label: typeStr, icon: 'fa-cube', color: '#64748b', inputs: [], outputs: [], properties: [] };
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Connection rendering (SVG)
    // ════════════════════════════════════════════════════════════════════════

    function _renderConns() {
        // Remove existing connection paths (keep defs and temp line)
        Array.from(_e.svg.children).forEach(function (c) {
            if (c.tagName !== 'defs' && !c.classList.contains('at-conn-temp')) c.remove();
        });
        if (!_active) return;

        _active.connections.forEach(function (conn) {
            const src = _portPos(conn.sourceNodeId, conn.sourcePort, 'output');
            const tgt = _portPos(conn.targetNodeId, conn.targetPort, 'input');
            if (!src || !tgt) return;

            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('class',
                'at-conn' + (conn.id === _selConnId ? ' at-conn-selected' : ''));
            path.setAttribute('d', _bezier(src.x, src.y, tgt.x, tgt.y));
            path.dataset.connId = conn.id;
            _e.svg.appendChild(path);
        });

        // Update connected-port markers
        _updatePortMarkers();
    }

    /** Get canvas-inner coordinates of a port dot. */
    function _portPos(nodeId, portName, portType) {
        const row = _e.canvasInner.querySelector(
            '[data-node-id="' + nodeId + '"][data-port="' + portName + '"][data-port-type="' + portType + '"]'
        );
        if (!row) return null;
        const dot = row.querySelector('.at-port');
        if (!dot) return null;

        const dRect = dot.getBoundingClientRect();
        const iRect = _e.canvasInner.getBoundingClientRect();
        return {
            x: (dRect.left + dRect.width  / 2 - iRect.left) / _view.scale,
            y: (dRect.top  + dRect.height / 2 - iRect.top)  / _view.scale,
        };
    }

    function _bezier(sx, sy, tx, ty) {
        const dx = tx - sx;
        const cp = Math.max(BEZIER_MIN_CP, Math.abs(dx) * 0.45);
        return 'M ' + sx + ' ' + sy +
               ' C ' + (sx + cp) + ' ' + sy + ',' +
                       (tx - cp) + ' ' + ty + ',' +
                       tx + ' ' + ty;
    }

    /** Add/remove .at-connected class on port dots based on current connections. */
    function _updatePortMarkers() {
        if (!_active) return;
        // Clear all
        _e.canvasInner.querySelectorAll('.at-port').forEach(function (p) {
            p.classList.remove('at-connected');
        });
        // Mark connected
        _active.connections.forEach(function (conn) {
            var srcRow = _e.canvasInner.querySelector(
                '[data-node-id="' + conn.sourceNodeId + '"][data-port="' + conn.sourcePort + '"][data-port-type="output"]'
            );
            var tgtRow = _e.canvasInner.querySelector(
                '[data-node-id="' + conn.targetNodeId + '"][data-port="' + conn.targetPort + '"][data-port-type="input"]'
            );
            if (srcRow) { var d = srcRow.querySelector('.at-port'); if (d) d.classList.add('at-connected'); }
            if (tgtRow) { var d2 = tgtRow.querySelector('.at-port'); if (d2) d2.classList.add('at-connected'); }
        });
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Palette
    // ════════════════════════════════════════════════════════════════════════

    function _renderPalette(filter) {
        const list = _e.paletteList;
        list.innerHTML = '';
        const q = filter ? filter.toLowerCase() : '';

        // Group by category
        const cats = {};
        _nodeTypes.forEach(function (t) {
            if (q && t.label.toLowerCase().indexOf(q) === -1) return;
            const cat = t.category || 'Other';
            if (!cats[cat]) cats[cat] = [];
            cats[cat].push(t);
        });

        Object.keys(cats).forEach(function (cat) {
            if (cats[cat].length === 0) return;

            const label = document.createElement('div');
            label.className   = 'at-palette-cat';
            label.textContent = cat;
            list.appendChild(label);

            cats[cat].forEach(function (t) {
                const color = t.color || '#64748b';
                const item  = document.createElement('div');
                item.className = 'at-palette-item';
                item.title     = t.label;
                item.innerHTML =
                    '<div class="at-palette-icon" style="background:' + color + '20;color:' + color + '">' +
                    '  <i class="fas ' + (t.icon || 'fa-cube') + '"></i>' +
                    '</div>' +
                    '<span class="at-palette-name">' + _esc(t.label) + '</span>';
                item.addEventListener('click', function () { _addNode(t.type); });
                list.appendChild(item);
            });
        });

        if (list.children.length === 0) {
            list.innerHTML = '<div style="padding:1rem 0.5rem;font-size:0.75rem;color:var(--text-muted,#64748b)">No nodes match.</div>';
        }
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Node management
    // ════════════════════════════════════════════════════════════════════════

    function _addNode(typeStr) {
        if (!_active) { _toast('Open or create a workflow first.'); return; }
        const td = _typeDef(typeStr);

        // Place at centre of current viewport with slight stagger
        const rect  = _e.canvas.getBoundingClientRect();
        const stagger = (_placeOffset % 10) * 30;
        const x = Math.round((rect.width  / 2 - _view.x) / _view.scale - NODE_WIDTH  / 2 + stagger);
        const y = Math.round((rect.height / 2 - _view.y) / _view.scale - NODE_H_EST  / 2 + stagger);
        _placeOffset++;

        const nd = {
            id:         'n_' + Date.now() + '_' + (Math.random() * 9999 | 0),
            type:       typeStr,
            label:      td.label,
            x:          x,
            y:          y,
            properties: {},
        };
        // Apply defaults from type definition
        (td.properties || []).forEach(function (p) {
            if (p.default !== undefined) nd.properties[p.key] = p.default;
        });

        _active.nodes.push(nd);
        _renderNode(nd);
        _markDirty();
        _selectNode(nd.id);
    }

    function _deleteNode(nodeId) {
        if (!_active) return;
        _active.nodes       = _active.nodes.filter(function (n) { return n.id !== nodeId; });
        _active.connections = _active.connections.filter(function (c) {
            return c.sourceNodeId !== nodeId && c.targetNodeId !== nodeId;
        });
        const el = _e.canvasInner.querySelector('[data-node-id="' + nodeId + '"].at-node');
        if (el) el.remove();
        if (_selNodeId === nodeId) { _selNodeId = null; _closeProps(); }
        _renderConns();
        _markDirty();
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Selection
    // ════════════════════════════════════════════════════════════════════════

    function _selectNode(nodeId) {
        _deselectAll(false);
        _selNodeId = nodeId;
        const el = _e.canvasInner.querySelector('[data-node-id="' + nodeId + '"].at-node');
        if (el) {
            el.classList.add('at-selected');
            _zTop++;
            el.style.zIndex = _zTop;
        }
        _openProps(nodeId);
    }

    function _selectConn(connId) {
        _deselectAll(false);
        _selConnId = connId;
        _renderConns();
    }

    function _deselectAll(closeProps) {
        _selNodeId = null;
        _selConnId = null;
        _e.canvasInner.querySelectorAll('.at-node.at-selected').forEach(function (n) {
            n.classList.remove('at-selected');
        });
        _renderConns();
        if (closeProps !== false) _closeProps();
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Properties panel
    // ════════════════════════════════════════════════════════════════════════

    function _openProps(nodeId) {
        if (!_active) return;
        const nd = _active.nodes.find(function (n) { return n.id === nodeId; });
        if (!nd) return;
        const td = _typeDef(nd.type);

        // Update header
        const color = td.color || '#64748b';
        _e.propsIcon.style.background = color + '20';
        _e.propsIcon.style.color      = color;
        _e.propsIcon.innerHTML        = '<i class="fas ' + (td.icon || 'fa-cube') + '"></i>';
        _e.propsTitle.textContent     = nd.label || td.label;

        _e.propsBody.innerHTML = '';

        if (!td.properties || td.properties.length === 0) {
            _e.propsBody.innerHTML = '<span class="at-props-none">No configurable properties.</span>';
            _e.propsPanel.classList.add('at-open');
            return;
        }

        td.properties.forEach(function (prop) {
            const val = nd.properties[prop.key] !== undefined
                ? nd.properties[prop.key]
                : (prop.default !== undefined ? prop.default : '');

            const field = document.createElement('div');
            field.className = 'at-prop-field';

            let inputEl;

            if (prop.type === 'model_select') {
                // Async-populated model selector
                inputEl = document.createElement('select');
                inputEl.className = 'at-prop-select at-prop-model-select';
                const loadingOpt = document.createElement('option');
                loadingOpt.value = '';
                loadingOpt.textContent = 'Loading models…';
                inputEl.appendChild(loadingOpt);

                // Async-populate
                _apiFetchModels(prop.source).then(function (models) {
                    inputEl.innerHTML = '';
                    const blank = document.createElement('option');
                    blank.value = '';
                    blank.textContent = prop.placeholder || 'Select model…';
                    inputEl.appendChild(blank);
                    models.forEach(function (m) {
                        const o = document.createElement('option');
                        o.value = m.id;
                        o.textContent = m.label;
                        o.title = m.description || '';
                        o.selected = (m.id === String(val));
                        inputEl.appendChild(o);
                    });
                    // If current val not in list, keep blank selected
                    if (val && !models.find(function (m) { return m.id === val; })) {
                        const miss = document.createElement('option');
                        miss.value = String(val);
                        miss.textContent = String(val) + ' (not found)';
                        miss.selected = true;
                        inputEl.appendChild(miss);
                    }
                });

            } else if (prop.type === 'toggle') {
                // Checkbox toggle rendered as a pill
                const wrapper = document.createElement('label');
                wrapper.className = 'at-prop-toggle';
                const check = document.createElement('input');
                check.type    = 'checkbox';
                check.checked = val === true || val === 'true' || val === 1;
                check.dataset.propKey = prop.key;
                check.addEventListener('change', function () {
                    nd.properties[prop.key] = check.checked;
                    _markDirty();
                    // Update show_result live on node
                    if (prop.key === 'show_result') {
                        _updateAINodeResult(nd.id, null, check.checked);
                    }
                });
                const pill = document.createElement('span');
                pill.className = 'at-prop-toggle-pill';
                wrapper.appendChild(check);
                wrapper.appendChild(pill);
                field.innerHTML = '<span class="at-prop-label">' + _esc(prop.label) + '</span>';
                field.appendChild(wrapper);
                _e.propsBody.appendChild(field);
                return; // handled fully above

            } else if (prop.type === 'select') {
                inputEl = document.createElement('select');
                inputEl.className = 'at-prop-select';
                (prop.options || []).forEach(function (opt) {
                    const o = document.createElement('option');
                    o.value       = opt;
                    o.textContent = opt;
                    o.selected    = (opt === String(val));
                    inputEl.appendChild(o);
                });
            } else if (prop.type === 'textarea' || prop.type === 'code') {
                inputEl = document.createElement('textarea');
                inputEl.className   = 'at-prop-textarea';
                inputEl.placeholder = prop.placeholder || '';
                inputEl.value       = String(val);
            } else {
                inputEl = document.createElement('input');
                inputEl.className   = 'at-prop-input';
                inputEl.type        = prop.type === 'number' ? 'number' : 'text';
                inputEl.placeholder = prop.placeholder || '';
                inputEl.value       = String(val);
            }

            inputEl.dataset.propKey = prop.key;
            inputEl.addEventListener('input', function () {
                const newVal = prop.type === 'number'
                    ? parseFloat(inputEl.value) || 0
                    : inputEl.value;
                nd.properties[prop.key] = newVal;
                _markDirty();
                // Live-update the model badge on the node card
                if (prop.key === 'model') {
                    const badge = _e.canvasInner.querySelector('[data-model-badge="' + nd.id + '"]');
                    if (badge) badge.textContent = newVal || 'no model';
                }
            });

            field.innerHTML = '<span class="at-prop-label">' + _esc(prop.label) + '</span>';
            field.appendChild(inputEl);
            _e.propsBody.appendChild(field);
        });

        // Add "Test Node" button at bottom of props for AI nodes
        if (nd.type.startsWith('ai.')) {
            const sep = document.createElement('div');
            sep.className = 'at-prop-sep';
            _e.propsBody.appendChild(sep);

            const testRow = document.createElement('div');
            testRow.className = 'at-prop-test-row';
            testRow.innerHTML =
                '<div class="at-prop-test-input-wrap">' +
                '  <input type="text" class="at-prop-input at-prop-test-input" ' +
                '    id="at-prop-test-input-' + nd.id + '" placeholder="Test input (optional)…">' +
                '</div>' +
                '<button class="at-btn at-btn-accent at-prop-test-btn" data-prop-test-node="' + nd.id + '">' +
                '  <i class="fas fa-bolt"></i> Test Node' +
                '</button>';
            _e.propsBody.appendChild(testRow);
        }

        _e.propsPanel.classList.add('at-open');
    }

    function _closeProps() {
        _e.propsPanel.classList.remove('at-open');
    }

    // ════════════════════════════════════════════════════════════════════════
    //  AI node result display
    // ════════════════════════════════════════════════════════════════════════

    function _updateAINodeResult(nodeId, resultText, forceShow) {
        const nd      = _active && _active.nodes.find(function (n) { return n.id === nodeId; });
        const wrap    = _e.canvasInner.querySelector('[data-node-result="' + nodeId + '"]');
        const badge   = _e.canvasInner.querySelector('[data-model-badge="' + nodeId + '"]');
        if (!wrap) return;

        const shouldShow = forceShow !== undefined
            ? forceShow
            : (nd && nd.properties['show_result'] !== false);

        if (resultText !== null && resultText !== undefined) {
            const body = wrap.querySelector('[data-node-result-body="' + nodeId + '"]');
            if (body) body.textContent = resultText;
            nd._result = resultText;
        }
        // Only show the panel if there's actual content
        const hasContent = nd && nd._result;
        wrap.style.display = (shouldShow && hasContent) ? '' : 'none';
        if (badge && nd) badge.textContent = nd.properties['model'] || 'no model';
    }

    async function _testAINode(nodeId) {
        const nd = _active && _active.nodes.find(function (n) { return n.id === nodeId; });
        if (!nd) return;

        const testInputEl = document.getElementById('at-prop-test-input-' + nodeId);
        const inputData   = testInputEl ? testInputEl.value.trim() : '';

        // Show loading state on node
        const wrap = _e.canvasInner.querySelector('[data-node-result="' + nodeId + '"]');
        const body = wrap && wrap.querySelector('[data-node-result-body="' + nodeId + '"]');
        if (wrap) {
            wrap.style.display = '';
            wrap.classList.add('at-loading');
        }
        if (body) body.textContent = 'Running…';

        // Flash test button
        const testBtns = _e.canvasInner.querySelectorAll('[data-test-node="' + nodeId + '"]');
        testBtns.forEach(function (b) { b.disabled = true; b.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Running'; });

        try {
            const resp = await _apiTestNode(nd, inputData);
            if (resp.ok) {
                _updateAINodeResult(nodeId, resp.result, true);
                _toast('Test complete. ' + (resp.model ? '(' + resp.model + ')' : ''));
            } else {
                if (body) body.textContent = '⚠ ' + (resp.error || 'Unknown error');
                if (wrap) wrap.style.display = '';
                _toast(resp.error || 'Test failed.', true);
            }
        } catch (e) {
            if (body) body.textContent = '⚠ ' + e.message;
            if (wrap) wrap.style.display = '';
            _toast('Test failed: ' + e.message, true);
        } finally {
            if (wrap) wrap.classList.remove('at-loading');
            testBtns.forEach(function (b) {
                b.disabled = false;
                b.innerHTML = '<i class="fas fa-bolt"></i> Test';
            });
        }
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Port connections
    // ════════════════════════════════════════════════════════════════════════

    function _handlePortClick(portRow) {
        const nodeId   = portRow.dataset.nodeId;
        const portName = portRow.dataset.port;
        const portType = portRow.dataset.portType;

        if (!_pending) {
            // Start: only allow output ports as source
            if (portType !== 'output') return;
            _pending = { nodeId, portName, portType };
            var dot = portRow.querySelector('.at-port');
            if (dot) dot.classList.add('at-pending');
            _e.canvas.style.cursor = 'crosshair';
            return;
        }

        // Complete: must click an input port on a different node
        if (portType !== 'input') { _cancelPending(); return; }
        if (nodeId === _pending.nodeId) {
            _cancelPending();
            _toast('Cannot connect a node to itself.');
            return;
        }
        // Duplicate check
        const dup = _active && _active.connections.find(function (c) {
            return c.sourceNodeId === _pending.nodeId && c.sourcePort === _pending.portName &&
                   c.targetNodeId === nodeId && c.targetPort === portName;
        });
        if (dup) { _cancelPending(); _toast('Connection already exists.'); return; }

        _active.connections.push({
            id:           'c_' + Date.now(),
            sourceNodeId: _pending.nodeId,
            sourcePort:   _pending.portName,
            targetNodeId: nodeId,
            targetPort:   portName,
        });
        _cancelPending();
        _renderConns();
        _markDirty();
    }

    function _cancelPending() {
        if (!_pending) return;
        var row = _e.canvasInner.querySelector(
            '[data-node-id="' + _pending.nodeId + '"][data-port="' + _pending.portName +
            '"][data-port-type="' + _pending.portType + '"]'
        );
        if (row) { var d = row.querySelector('.at-port'); if (d) d.classList.remove('at-pending'); }
        _pending = null;
        _e.canvas.style.cursor = '';
        var tmp = _e.svg.querySelector('.at-conn-temp');
        if (tmp) tmp.remove();
    }

    function _deleteConn(connId) {
        if (!_active) return;
        _active.connections = _active.connections.filter(function (c) { return c.id !== connId; });
        if (_selConnId === connId) _selConnId = null;
        _renderConns();
        _markDirty();
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Pan / Zoom
    // ════════════════════════════════════════════════════════════════════════

    function _applyTransform() {
        _e.canvasInner.style.transform =
            'translate(' + _view.x + 'px,' + _view.y + 'px) scale(' + _view.scale + ')';
        _e.zoomLabel.textContent = Math.round(_view.scale * 100) + '%';
    }

    function _zoom(dir, clientX, clientY) {
        const rect = _e.canvas.getBoundingClientRect();
        const mx   = clientX - rect.left;
        const my   = clientY - rect.top;
        const prev = _view.scale;
        let next   = prev * (1 + dir * ZOOM_STEP);
        next = Math.max(MIN_SCALE, Math.min(MAX_SCALE, next));
        _view.x = mx - (mx - _view.x) * (next / prev);
        _view.y = my - (my - _view.y) * (next / prev);
        _view.scale = next;
        _applyTransform();
    }

    function _fitToScreen() {
        if (!_active || _active.nodes.length === 0) return;
        const rect    = _e.canvas.getBoundingClientRect();
        const padding = 80;
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;

        _active.nodes.forEach(function (n) {
            minX = Math.min(minX, n.x);
            minY = Math.min(minY, n.y);
            maxX = Math.max(maxX, n.x + NODE_WIDTH);
            maxY = Math.max(maxY, n.y + NODE_H_EST);
        });

        const bboxW = maxX - minX + padding * 2;
        const bboxH = maxY - minY + padding * 2;
        const scale = Math.min(
            rect.width  / bboxW,
            rect.height / bboxH,
            MAX_SCALE
        );
        _view.scale = Math.max(MIN_SCALE, scale);
        _view.x = (rect.width  - (minX + maxX) * _view.scale) / 2;
        _view.y = (rect.height - (minY + maxY) * _view.scale) / 2;
        _applyTransform();
    }

    // ════════════════════════════════════════════════════════════════════════
    //  New workflow / rename
    // ════════════════════════════════════════════════════════════════════════

    function _newWorkflow() {
        const name = prompt('Workflow name:', 'New Workflow');
        if (!name || !name.trim()) return;
        _apiCreateWorkflow(name.trim()).then(function (wf) {
            _workflows.unshift({ id: wf.id, name: wf.name, node_count: 0, updated: wf.updated });
            _renderWfList();
            _openWorkflow(wf.id);
        }).catch(function (e) {
            _toast('Failed to create workflow.', true);
            console.error('[Automate]', e);
        });
    }

    function _renameWorkflow() {
        if (!_active) return;
        const name = prompt('Rename workflow:', _active.name);
        if (!name || !name.trim() || name.trim() === _active.name) return;
        _active.name = name.trim();
        _e.wfLabel.textContent = _active.name;
        const entry = _workflows.find(function (w) { return w.id === _active.id; });
        if (entry) entry.name = _active.name;
        _renderWfList();
        _markDirty();
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Toolbar state
    // ════════════════════════════════════════════════════════════════════════

    function _updateToolbar() {
        const has = !!_active;
        _e.btnSave.disabled   = !has;
        _e.btnDelete.disabled = !has;
        _e.btnRun.disabled    = !has;
    }

    function _markDirty() {
        _dirty = true;
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Toast
    // ════════════════════════════════════════════════════════════════════════

    var _toastTimer = null;
    function _toast(msg, isError) {
        _e.toast.textContent = msg;
        _e.toast.className   = 'at-toast' + (isError ? ' at-toast-error' : '');
        _e.toast.style.display = '';
        if (_toastTimer) clearTimeout(_toastTimer);
        _toastTimer = setTimeout(function () { _e.toast.style.display = 'none'; }, 2800);
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Utilities
    // ════════════════════════════════════════════════════════════════════════

    function _esc(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function _isAutomate() {
        var p = document.getElementById('automate-panel');
        return p && p.offsetParent !== null;
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Event wiring
    // ════════════════════════════════════════════════════════════════════════

    function _wireEvents() {
        // ── Toolbar buttons ────────────────────────────────────────────────
        _e.btnNew   .addEventListener('click', _newWorkflow);
        _e.btnSave  .addEventListener('click', _apiSaveWorkflow);
        _e.btnDelete.addEventListener('click', _apiDeleteWorkflow);
        _e.btnRun   .addEventListener('click', _apiRunWorkflow);
        _e.btnFit   .addEventListener('click', _fitToScreen);

        _e.wfRenameBtn.addEventListener('click', _renameWorkflow);

        _e.btnZoomIn.addEventListener('click', function () {
            var r = _e.canvas.getBoundingClientRect();
            _zoom(1, r.left + r.width / 2, r.top + r.height / 2);
        });
        _e.btnZoomOut.addEventListener('click', function () {
            var r = _e.canvas.getBoundingClientRect();
            _zoom(-1, r.left + r.width / 2, r.top + r.height / 2);
        });

        // ── Sidebar ────────────────────────────────────────────────────────
        _e.sidebarAdd.addEventListener('click', _newWorkflow);
        if (_e.wfCreateFirst) _e.wfCreateFirst.addEventListener('click', _newWorkflow);
        if (_e.canvasNewBtn)  _e.canvasNewBtn .addEventListener('click', _newWorkflow);

        // ── Palette search ─────────────────────────────────────────────────
        _e.paletteSearch.addEventListener('input', function () {
            _renderPalette(this.value.trim() || null);
        });

        // ── Canvas pan (middle-mouse / Alt+left-drag) ──────────────────────
        _e.canvas.addEventListener('mousedown', function (e) {
            if (e.button === 1 || (e.button === 0 && e.altKey)) {
                e.preventDefault();
                _panning = {
                    startCX: e.clientX, startCY: e.clientY,
                    startVX: _view.x,   startVY: _view.y,
                };
                _e.canvas.classList.add('at-panning');
            }
        });

        // ── Canvas wheel zoom ──────────────────────────────────────────────
        _e.canvas.addEventListener('wheel', function (e) {
            e.preventDefault();
            _zoom(e.deltaY < 0 ? 1 : -1, e.clientX, e.clientY);
        }, { passive: false });

        // ── Canvas-inner click delegation ──────────────────────────────────
        _e.canvasInner.addEventListener('click', function (e) {
            // Port click
            const portRow = e.target.closest('.at-port-row');
            if (portRow) {
                e.stopPropagation();
                if (_active) _handlePortClick(portRow);
                return;
            }
            // Delete-node button
            const delBtn = e.target.closest('[data-del-node]');
            if (delBtn) {
                e.stopPropagation();
                _deleteNode(delBtn.dataset.delNode);
                return;
            }
            // Test-node button (on the AI bar in the node card)
            const testBtn = e.target.closest('[data-test-node]');
            if (testBtn) {
                e.stopPropagation();
                _testAINode(testBtn.dataset.testNode);
                return;
            }
            // Close result panel
            const closeResult = e.target.closest('[data-close-result]');
            if (closeResult) {
                e.stopPropagation();
                const nid = closeResult.dataset.closeResult;
                const wrap = _e.canvasInner.querySelector('[data-node-result="' + nid + '"]');
                if (wrap) wrap.style.display = 'none';
                return;
            }
            // Node body → select
            const nodeEl = e.target.closest('.at-node');
            if (nodeEl) {
                e.stopPropagation();
                _selectNode(nodeEl.dataset.nodeId);
                return;
            }
            // Canvas background
            _deselectAll();
            _cancelPending();
        });

        // ── Node header drag ───────────────────────────────────────────────
        _e.canvasInner.addEventListener('mousedown', function (e) {
            if (e.button !== 0) return;
            const hdr = e.target.closest('.at-node-hdr');
            if (!hdr) return;
            if (e.target.closest('[data-del-node]') || e.target.closest('.at-port-row')) return;
            const nodeEl = hdr.closest('.at-node');
            if (!nodeEl) return;
            const nodeId = nodeEl.dataset.nodeId;
            const nd     = _active && _active.nodes.find(function (n) { return n.id === nodeId; });
            if (!nd) return;
            e.preventDefault();
            e.stopPropagation();
            _dragging = {
                nodeId,
                startCX: e.clientX, startCY: e.clientY,
                startNX: nd.x,      startNY: nd.y,
            };
            _selectNode(nodeId);
        });

        // ── SVG connection click ───────────────────────────────────────────
        _e.svg.addEventListener('click', function (e) {
            const path = e.target.closest('.at-conn');
            if (path) {
                e.stopPropagation();
                _selectConn(path.dataset.connId);
            }
        });

        // ── Props close ────────────────────────────────────────────────────
        _e.propsClose.addEventListener('click', function () { _deselectAll(); });

        // ── Props body delegation (test button) ────────────────────────────
        _e.propsBody.addEventListener('click', function (e) {
            const btn = e.target.closest('[data-prop-test-node]');
            if (btn) {
                e.stopPropagation();
                _testAINode(btn.dataset.propTestNode);
            }
        });

        // ── Execution log panel ────────────────────────────────────────────
        var execClose = document.getElementById('at-exec-panel-close');
        if (execClose) {
            execClose.addEventListener('click', function () {
                var p = document.getElementById('at-exec-panel');
                if (p) p.classList.remove('at-open');
            });
        }
        var execTabs = document.querySelectorAll('.at-exec-tab');
        execTabs.forEach(function (tab) {
            tab.addEventListener('click', function () {
                execTabs.forEach(function (t) { t.classList.remove('active'); });
                tab.classList.add('active');
                var target = tab.dataset.execTab;
                var logView = document.getElementById('at-exec-log-view');
                var outView = document.getElementById('at-exec-out-view');
                if (logView) logView.classList.toggle('hidden', target !== 'log');
                if (outView) outView.classList.toggle('hidden', target !== 'outputs');
            });
        });

        // ── Global mouse move + up ─────────────────────────────────────────
        document.addEventListener('mousemove', function (e) {
            // Node drag
            if (_dragging) {
                const dx = (e.clientX - _dragging.startCX) / _view.scale;
                const dy = (e.clientY - _dragging.startCY) / _view.scale;
                const nd = _active && _active.nodes.find(function (n) { return n.id === _dragging.nodeId; });
                if (nd) {
                    nd.x = Math.round(_dragging.startNX + dx);
                    nd.y = Math.round(_dragging.startNY + dy);
                    const el = _e.canvasInner.querySelector('[data-node-id="' + _dragging.nodeId + '"].at-node');
                    if (el) { el.style.left = nd.x + 'px'; el.style.top = nd.y + 'px'; }
                    _renderConns();
                }
                return;
            }
            // Pan
            if (_panning) {
                _view.x = _panning.startVX + (e.clientX - _panning.startCX);
                _view.y = _panning.startVY + (e.clientY - _panning.startCY);
                _applyTransform();
                return;
            }
            // Temp connection line
            if (_pending) {
                const src = _portPos(_pending.nodeId, _pending.portName, _pending.portType);
                if (src) {
                    const iRect = _e.canvasInner.getBoundingClientRect();
                    const tx = (e.clientX - iRect.left) / _view.scale;
                    const ty = (e.clientY - iRect.top)  / _view.scale;
                    let tmp = _e.svg.querySelector('.at-conn-temp');
                    if (!tmp) {
                        tmp = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                        tmp.setAttribute('class', 'at-conn-temp');
                        _e.svg.appendChild(tmp);
                    }
                    tmp.setAttribute('d', _bezier(src.x, src.y, tx, ty));
                }
            }
        });

        document.addEventListener('mouseup', function () {
            if (_dragging) { _markDirty(); _dragging = null; }
            if (_panning)  { _panning = null; _e.canvas.classList.remove('at-panning'); }
        });

        // ── Context menu suppression on canvas ────────────────────────────
        _e.canvas.addEventListener('contextmenu', function (e) { e.preventDefault(); });

        // ── Keyboard shortcuts ─────────────────────────────────────────────
        document.addEventListener('keydown', function (e) {
            if (!_isAutomate()) return;
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' ||
                e.target.tagName === 'SELECT') return;

            if (e.key === 'Delete' || e.key === 'Backspace') {
                if (_selNodeId) { _deleteNode(_selNodeId); return; }
                if (_selConnId) { _deleteConn(_selConnId); return; }
            }
            if (e.key === 'Escape') { _cancelPending(); _deselectAll(); }
            if (e.ctrlKey && e.key === 's') { e.preventDefault(); _apiSaveWorkflow(); }
            if (e.key === 'f' || e.key === 'F') { _fitToScreen(); }
        });
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Panel loaded entry point
    // ════════════════════════════════════════════════════════════════════════

    document.addEventListener('panelLoaded', function (e) {
        if (e.detail && e.detail.tabName === 'automate') {
            _init();
        }
    });

})();
