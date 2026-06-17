/**
 * mode-decision-trace.js
 * DecisionTrace — Organisational Decision Provenance Graph
 *
 * API prefix: /api/decision-trace
 */
(function () {
    'use strict';

    // ── Constants ─────────────────────────────────────────────────────────────
    const API = '/api/decision-trace';

    // ── State ─────────────────────────────────────────────────────────────────
    let _decisions   = [];      // full list from server
    let _filtered    = [];      // after search filter
    let _activeId    = null;    // currently selected decision ID
    let _editingId   = null;    // null = new, string = existing ID being edited
    let _askStream   = null;    // active EventSource
    let _searchTimer = null;

    // ── DOM shortcuts ─────────────────────────────────────────────────────────
    const $ = id => document.getElementById(id);

    // ── Utilities ─────────────────────────────────────────────────────────────
    function esc(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function timeAgo(iso) {
        if (!iso) return '—';
        const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
        if (diff < 60)    return 'just now';
        if (diff < 3600)  return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
        return Math.floor(diff / 86400) + 'd ago';
    }

    function splitLines(val) {
        return val.split('\n').map(s => s.trim()).filter(Boolean);
    }

    function splitCommas(val) {
        return val.split(',').map(s => s.trim()).filter(Boolean);
    }

    // ── Tab navigation ────────────────────────────────────────────────────────
    function switchTab(tabId) {
        document.querySelectorAll('.dt-nav-tab').forEach(btn =>
            btn.classList.toggle('active', btn.dataset.dtTab === tabId));

        ['decisions', 'graph'].forEach(id => {
            const el = $(`dt-pane-${id}`);
            if (el) el.classList.toggle('active', id === tabId);
        });

        if (tabId === 'graph') loadGraph();
    }

    // ── Stats bar ─────────────────────────────────────────────────────────────
    function updateStats(decisions) {
        const totalLinks = decisions.reduce((n, d) => n + (d.links_to?.length || 0), 0);
        const allTags    = new Set(decisions.flatMap(d => d.tags || []));

        const c = $('dt-stat-count');
        const l = $('dt-stat-links');
        const t = $('dt-stat-tags');
        if (c) c.textContent = decisions.length;
        if (l) l.textContent = totalLinks;
        if (t) t.textContent = allTags.size;
    }

    // ── Load & render list ────────────────────────────────────────────────────
    async function loadDecisions() {
        try {
            const res  = await fetch(`${API}/list`);
            const data = await res.json();
            _decisions = data.decisions || [];
            _filtered  = _decisions;
            updateStats(_decisions);
            renderList(_filtered);
        } catch (err) {
            const scroll = $('dt-list-scroll');
            if (scroll) scroll.innerHTML =
                `<div class="dt-error-banner"><i class="fas fa-circle-exclamation"></i> Failed to load decisions.</div>`;
        }
    }

    function renderList(decisions) {
        const scroll = $('dt-list-scroll');
        if (!scroll) return;

        if (!decisions.length) {
            scroll.innerHTML = `
                <div class="dt-list-empty">
                    <i class="fas fa-timeline"></i>
                    No decisions yet.<br>
                    Hit <strong>New</strong> to capture your first one.
                </div>`;
            return;
        }

        scroll.innerHTML = decisions.map(d => `
            <div class="dt-decision-card ${_activeId === d.id ? 'active' : ''}"
                 data-id="${esc(d.id)}" id="dt-card-${esc(d.id)}">
                <div class="dt-card-title">${esc(d.title)}</div>
                ${d.chosen_option
                    ? `<div class="dt-card-chosen"><i class="fas fa-check-circle"></i> ${esc(d.chosen_option)}</div>`
                    : ''}
                <div class="dt-card-tags">
                    ${(d.tags || []).map(t => `<span class="dt-tag">${esc(t)}</span>`).join('')}
                </div>
                <div class="dt-card-date">${timeAgo(d.updated_at || d.created_at)}</div>
            </div>
        `).join('');

        scroll.querySelectorAll('.dt-decision-card').forEach(card => {
            card.addEventListener('click', () => selectDecision(card.dataset.id));
        });
    }

    // ── Search ────────────────────────────────────────────────────────────────
    function applySearch(query) {
        const q = query.toLowerCase().trim();
        _filtered = q
            ? _decisions.filter(d =>
                d.title?.toLowerCase().includes(q) ||
                (d.tags || []).some(t => t.toLowerCase().includes(q)) ||
                d.chosen_option?.toLowerCase().includes(q))
            : _decisions;
        renderList(_filtered);
    }

    // ── Select & load a decision ──────────────────────────────────────────────
    async function selectDecision(id) {
        if (_activeId === id) return;
        _activeId = id;

        // Highlight card
        document.querySelectorAll('.dt-decision-card').forEach(c =>
            c.classList.toggle('active', c.dataset.id === id));

        // Enable Ask inputs
        const textarea = $('dt-ask-textarea');
        const sendBtn  = $('dt-ask-send-btn');
        if (textarea) textarea.disabled = false;
        if (sendBtn)  sendBtn.disabled  = false;

        // Reset Ask panel
        const output = $('dt-ask-output');
        if (output) {
            output.innerHTML = `
                <div class="dt-ask-placeholder" id="dt-ask-placeholder">
                    <i class="fas fa-comments"></i>
                    Ask a question about this decision.
                </div>`;
        }

        // Show loading state in detail pane
        const empty   = $('dt-detail-empty');
        const content = $('dt-detail-content');
        if (empty)   empty.style.display   = 'none';
        if (content) content.style.display = 'none';

        const scroll = $('dt-detail-scroll');
        if (scroll && !scroll.querySelector('#dt-detail-loading')) {
            const loading = document.createElement('div');
            loading.id = 'dt-detail-loading';
            loading.className = 'dt-loading';
            loading.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading…';
            scroll.appendChild(loading);
        }

        try {
            const res      = await fetch(`${API}/${id}`);
            const decision = await res.json();
            renderDetail(decision);
        } catch (err) {
            if (content) {
                content.style.display = '';
                content.innerHTML = `<div class="dt-error-banner"><i class="fas fa-circle-exclamation"></i> Failed to load decision.</div>`;
            }
        } finally {
            const loading = $('dt-detail-loading');
            if (loading) loading.remove();
        }
    }

    // ── Render detail view ────────────────────────────────────────────────────
    async function renderDetail(d) {
        const content = $('dt-detail-content');
        if (!content) return;

        // Fetch linked decision titles for display
        const linksHtml = await buildLinksHtml(d.links_to || []);

        const optionsList = (d.options_considered || []).map(o =>
            `<li><i class="fas fa-circle-small"></i> ${esc(o)}</li>`).join('');

        const constraintsList = (d.constraints || []).map(c =>
            `<li><i class="fas fa-shield"></i> ${esc(c)}</li>`).join('');

        const stakeholderChips = (d.stakeholders || []).map(s =>
            `<span class="dt-stakeholder-chip"><i class="fas fa-user"></i> ${esc(s)}</span>`).join('');

        content.innerHTML = `
            <div class="dt-detail-header">
                <div class="dt-detail-title">${esc(d.title)}</div>
                <div class="dt-detail-actions">
                    <button class="dt-icon-btn" id="dt-edit-btn" title="Edit decision">
                        <i class="fas fa-pen"></i>
                    </button>
                    <button class="dt-icon-btn danger" id="dt-delete-btn" title="Delete decision">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>

            <div class="dt-detail-meta">
                <span class="dt-meta-chip">
                    <i class="fas fa-clock"></i> Created ${timeAgo(d.created_at)}
                </span>
                ${d.updated_at && d.updated_at !== d.created_at
                    ? `<span class="dt-meta-chip"><i class="fas fa-pen"></i> Updated ${timeAgo(d.updated_at)}</span>`
                    : ''}
                ${(d.tags || []).map(t => `<span class="dt-tag">${esc(t)}</span>`).join('')}
            </div>

            ${d.context ? `
            <div class="dt-section">
                <div class="dt-section-label"><i class="fas fa-file-lines"></i> Context</div>
                <div class="dt-section-text">${esc(d.context)}</div>
            </div>` : ''}

            ${d.chosen_option ? `
            <div class="dt-section">
                <div class="dt-section-label"><i class="fas fa-check-circle"></i> Decision</div>
                <div class="dt-chosen-badge">
                    <i class="fas fa-check-circle"></i> ${esc(d.chosen_option)}
                </div>
            </div>` : ''}

            ${optionsList ? `
            <div class="dt-section">
                <div class="dt-section-label"><i class="fas fa-list"></i> Options Considered</div>
                <ul class="dt-options-list">${optionsList}</ul>
            </div>` : ''}

            ${constraintsList ? `
            <div class="dt-section">
                <div class="dt-section-label"><i class="fas fa-shield"></i> Constraints</div>
                <ul class="dt-constraints-list">${constraintsList}</ul>
            </div>` : ''}

            ${d.trade_offs ? `
            <div class="dt-section">
                <div class="dt-section-label"><i class="fas fa-scale-balanced"></i> Trade-offs Accepted</div>
                <div class="dt-section-text">${esc(d.trade_offs)}</div>
            </div>` : ''}

            ${stakeholderChips ? `
            <div class="dt-section">
                <div class="dt-section-label"><i class="fas fa-users"></i> Stakeholders</div>
                <div class="dt-stakeholder-chips">${stakeholderChips}</div>
            </div>` : ''}

            ${linksHtml ? `
            <div class="dt-section">
                <div class="dt-section-label"><i class="fas fa-link"></i> Linked Decisions</div>
                <div class="dt-links-grid">${linksHtml}</div>
            </div>` : ''}
        `;

        content.style.display = '';

        // Wire edit / delete
        const editBtn   = $('dt-edit-btn');
        const deleteBtn = $('dt-delete-btn');
        if (editBtn)   editBtn.addEventListener('click',   () => openModal(d));
        if (deleteBtn) deleteBtn.addEventListener('click', () => deleteDecision(d.id));
    }

    async function buildLinksHtml(linkIds) {
        if (!linkIds?.length) return '';
        // Use cached list data if available
        return linkIds.map(lid => {
            const cached = _decisions.find(d => d.id === lid);
            const title  = cached?.title || lid;
            return `<div class="dt-link-chip" data-linked-id="${esc(lid)}">
                <i class="fas fa-arrow-right"></i>
                ${esc(title)}
            </div>`;
        }).join('');
    }

    // ── Delete decision ───────────────────────────────────────────────────────
    async function deleteDecision(id) {
        if (!confirm('Delete this decision? This cannot be undone.')) return;
        try {
            await fetch(`${API}/${id}`, { method: 'DELETE' });
            _activeId = null;
            const empty   = $('dt-detail-empty');
            const content = $('dt-detail-content');
            if (empty)   empty.style.display   = '';
            if (content) content.style.display = 'none';
            const textarea = $('dt-ask-textarea');
            const sendBtn  = $('dt-ask-send-btn');
            if (textarea) textarea.disabled = true;
            if (sendBtn)  sendBtn.disabled  = true;
            await loadDecisions();
        } catch (err) {
            alert('Failed to delete decision. Please try again.');
        }
    }

    // ── Modal: open ───────────────────────────────────────────────────────────
    function openModal(decision = null) {
        _editingId = decision ? decision.id : null;
        const titleText = $('dt-modal-title-text');
        if (titleText) titleText.textContent = decision ? 'Edit Decision' : 'New Decision';

        // Populate fields
        $('dt-form-title').value       = decision?.title              || '';
        $('dt-form-context').value     = decision?.context            || '';
        $('dt-form-options').value     = (decision?.options_considered || []).join('\n');
        $('dt-form-chosen').value      = decision?.chosen_option       || '';
        $('dt-form-constraints').value = (decision?.constraints       || []).join('\n');
        $('dt-form-tradeoffs').value   = decision?.trade_offs          || '';
        $('dt-form-stakeholders').value= (decision?.stakeholders      || []).join(', ');
        $('dt-form-tags').value        = (decision?.tags              || []).join(', ');

        const overlay = $('dt-modal-overlay');
        if (overlay) overlay.style.display = 'flex';
        setTimeout(() => { const t = $('dt-form-title'); if (t) t.focus(); }, 50);
    }

    // ── Modal: close ──────────────────────────────────────────────────────────
    function closeModal() {
        const overlay = $('dt-modal-overlay');
        if (overlay) overlay.style.display = 'none';
        _editingId = null;
    }

    // ── Modal: save ───────────────────────────────────────────────────────────
    async function saveDecision() {
        const title = $('dt-form-title')?.value.trim();
        if (!title) { alert('Title is required.'); return; }

        const saveBtn = $('dt-modal-save');
        if (saveBtn) { saveBtn.disabled = true; saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…'; }

        const body = {
            title,
            context:            $('dt-form-context')?.value.trim()     || '',
            options_considered: splitLines($('dt-form-options')?.value  || ''),
            chosen_option:      $('dt-form-chosen')?.value.trim()       || '',
            constraints:        splitLines($('dt-form-constraints')?.value || ''),
            trade_offs:         $('dt-form-tradeoffs')?.value.trim()    || '',
            stakeholders:       splitCommas($('dt-form-stakeholders')?.value || ''),
            tags:               splitCommas($('dt-form-tags')?.value     || ''),
            links_to:           [],   // link management via graph view (future)
        };

        try {
            if (_editingId) {
                await fetch(`${API}/${_editingId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                closeModal();
                await loadDecisions();
                await selectDecision(_editingId);
            } else {
                const res  = await fetch(`${API}/create`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const data = await res.json();
                closeModal();
                await loadDecisions();
                await selectDecision(data.id);
            }
        } catch (err) {
            alert('Failed to save decision. Please try again.');
        } finally {
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.innerHTML = '<i class="fas fa-floppy-disk"></i> Save Decision';
            }
        }
    }

    // ── Ask (streaming) ───────────────────────────────────────────────────────
    async function sendAsk() {
        if (!_activeId) return;
        const textarea = $('dt-ask-textarea');
        const sendBtn  = $('dt-ask-send-btn');
        const output   = $('dt-ask-output');
        const modelSel = $('dt-ask-model');

        const question = textarea?.value.trim();
        if (!question) return;

        if (sendBtn) { sendBtn.disabled = true; sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; }
        if (textarea) { textarea.disabled = true; }

        // Clear output and start fresh
        if (output) {
            output.innerHTML = `<div id="dt-ask-response" style="white-space:pre-wrap;"></div><span class="dt-cursor"></span>`;
        }

        const model = modelSel?.value || 'auto';

        try {
            // We use fetch + ReadableStream instead of EventSource so we can POST
            const res = await fetch(`${API}/${_activeId}/ask`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question, model_id: model }),
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const reader  = res.body.getReader();
            const decoder = new TextDecoder();
            const respEl  = $('dt-ask-response');
            let buffer    = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                const parts = buffer.split('\n\n');
                buffer = parts.pop(); // keep incomplete last chunk

                for (const part of parts) {
                    const line = part.replace(/^data: /, '').trim();
                    if (!line) continue;
                    try {
                        const msg = JSON.parse(line);
                        if (msg.token && respEl) {
                            respEl.textContent += msg.token;
                            if (output) output.scrollTop = output.scrollHeight;
                        }
                        if (msg.error) {
                            if (respEl) respEl.textContent = `Error: ${msg.error}`;
                        }
                        if (msg.done) {
                            // Remove cursor
                            const cursor = output?.querySelector('.dt-cursor');
                            if (cursor) cursor.remove();
                        }
                    } catch (_) { /* ignore parse errors */ }
                }
            }

        } catch (err) {
            if (output) output.innerHTML = `<div class="dt-error-banner"><i class="fas fa-circle-exclamation"></i> ${esc(err.message)}</div>`;
        } finally {
            if (sendBtn) { sendBtn.disabled = false; sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Ask'; }
            if (textarea) { textarea.disabled = false; textarea.value = ''; }
        }
    }

    // ── Graph pane ────────────────────────────────────────────────────────────
    async function loadGraph() {
        const wrap    = $('dt-graph-canvas-wrap');
        const nodes   = $('dt-graph-nodes');
        const loading = $('dt-graph-loading');

        if (loading) loading.style.display = 'flex';
        if (nodes)   nodes.style.display   = 'none';

        try {
            const res  = await fetch(`${API}/graph/all`);
            const data = await res.json();
            renderGraph(data);
        } catch (err) {
            if (wrap) wrap.innerHTML = `<div class="dt-error-banner"><i class="fas fa-circle-exclamation"></i> Failed to load graph.</div>`;
        }
    }

    function renderGraph(data) {
        const loading = $('dt-graph-loading');
        const nodeEl  = $('dt-graph-nodes');

        if (loading) loading.style.display = 'none';
        if (!nodeEl) return;

        const { nodes = [], edges = [] } = data;
        const edgeMap = {};
        edges.forEach(e => {
            edgeMap[e.from] = edgeMap[e.from] || [];
            edgeMap[e.from].push(e.to);
        });

        if (!nodes.length) {
            nodeEl.innerHTML = `<div class="dt-graph-empty"><i class="fas fa-circle-nodes" style="font-size:28px;opacity:0.3;display:block;margin-bottom:10px;"></i>No decisions yet. Create some to see the graph.</div>`;
            nodeEl.style.display = '';
            return;
        }

        nodeEl.innerHTML = nodes.map(n => {
            const links = edgeMap[n.id] || [];
            return `
                <div class="dt-graph-node" data-node-id="${esc(n.id)}">
                    <div class="dt-graph-node-title">${esc(n.title)}</div>
                    ${n.chosen_option ? `<div class="dt-graph-node-chosen"><i class="fas fa-check-circle"></i> ${esc(n.chosen_option)}</div>` : ''}
                    ${links.length ? `<div class="dt-graph-node-links"><i class="fas fa-link"></i> ${links.length} link${links.length > 1 ? 's' : ''}</div>` : ''}
                </div>`;
        }).join('');

        nodeEl.style.display = 'flex';

        // Click on graph node → switch to decisions pane and open it
        nodeEl.querySelectorAll('.dt-graph-node').forEach(node => {
            node.addEventListener('click', async () => {
                switchTab('decisions');
                await selectDecision(node.dataset.nodeId);
            });
        });
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        // Tab switcher
        document.querySelectorAll('.dt-nav-tab').forEach(btn => {
            btn.addEventListener('click', () => switchTab(btn.dataset.dtTab));
        });

        // Search
        const searchInput = $('dt-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                clearTimeout(_searchTimer);
                _searchTimer = setTimeout(() => applySearch(searchInput.value), 180);
            });
        }

        // New decision button
        const newBtn = $('dt-new-btn');
        if (newBtn) newBtn.addEventListener('click', () => openModal());

        // Modal controls
        $('dt-modal-close')?.addEventListener('click',  closeModal);
        $('dt-modal-cancel')?.addEventListener('click', closeModal);
        $('dt-modal-save')?.addEventListener('click',   saveDecision);
        $('dt-modal-overlay')?.addEventListener('click', e => {
            if (e.target === $('dt-modal-overlay')) closeModal();
        });

        // Ask panel
        const sendBtn  = $('dt-ask-send-btn');
        const textarea = $('dt-ask-textarea');
        if (sendBtn)  sendBtn.addEventListener('click', sendAsk);
        if (textarea) textarea.addEventListener('keydown', e => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                sendAsk();
            }
        });

        // Graph refresh
        $('dt-graph-refresh-btn')?.addEventListener('click', loadGraph);

        // Linked decision click → navigate
        document.addEventListener('click', e => {
            const chip = e.target.closest('[data-linked-id]');
            if (chip) selectDecision(chip.dataset.linkedId);
        });

        // Initial load
        loadDecisions();
    }

    // Wait for DOM to be ready (panelLoaded event or DOMContentLoaded)
    if (document.getElementById('dt-root')) {
        init();
    } else {
        document.addEventListener('panelLoaded', function handler(e) {
            if (e.detail?.tabName === 'decision-trace') {
                document.removeEventListener('panelLoaded', handler);
                init();
            }
        });
    }

})();
