/**
 * mode-lexmap.js
 * LexMap — Organisational Artifact Provenance Graph
 *
 * API prefix: /api/lexmap
 */
(function () {
    'use strict';

    // ── Constants ─────────────────────────────────────────────────────────────
    const API = '/api/lexmap';

    // ── State ─────────────────────────────────────────────────────────────────
    let _artifacts   = [];      // full list from server
    let _filtered    = [];      // after search filter
    let _activeId    = null;    // currently selected artifact ID
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
        document.querySelectorAll('.lm-nav-tab').forEach(btn =>
            btn.classList.toggle('active', btn.dataset.lmTab === tabId));

        ['artifacts', 'graph'].forEach(id => {
            const el = $(`lm-pane-${id}`);
            if (el) el.classList.toggle('active', id === tabId);
        });

        if (tabId === 'graph') loadGraph();
    }

    // ── Stats bar ─────────────────────────────────────────────────────────────
    function updateStats(artifacts) {
        const totalLinks = artifacts.reduce((n, d) => n + (d.links?.length || 0), 0);
        const allJurisdictions = new Set(artifacts.map(d => d.jurisdiction).filter(Boolean));

        const c = $('lm-stat-count');
        const l = $('lm-stat-links');
        const j = $('lm-stat-jurisdictions');
        if (c) c.textContent = artifacts.length;
        if (l) l.textContent = totalLinks;
        if (j) j.textContent = allJurisdictions.size;
    }

    // ── Load & render list ────────────────────────────────────────────────────
    async function loadArtifacts() {
        try {
            const res  = await fetch(`${API}/list`);
            const data = await res.json();
            _artifacts = data.artifacts || [];
            _filtered  = _artifacts;
            updateStats(_artifacts);
            renderList(_filtered);
        } catch (err) {
            const scroll = $('lm-list-scroll');
            if (scroll) scroll.innerHTML =
                `<div class="lm-error-banner"><i class="fas fa-circle-exclamation"></i> Failed to load artifacts.</div>`;
        }
    }

    function renderList(artifacts) {
        const scroll = $('lm-list-scroll');
        if (!scroll) return;

        if (!artifacts.length) {
            scroll.innerHTML = `
                <div class="lm-list-empty">
                    <i class="fas fa-timeline"></i>
                    No artifacts yet.<br>
                    Hit <strong>New</strong> to capture your first one.
                </div>`;
            return;
        }

        scroll.innerHTML = artifacts.map(d => `
            <div class="lm-artifact-card ${_activeId === d.id ? 'active' : ''}"
                 data-id="${esc(d.id)}" id="lm-card-${esc(d.id)}">
                <div class="lm-card-title">${esc(d.title)}</div>
                ${d.chosen_option
                    ? `<div class="lm-card-chosen"><i class="fas fa-check-circle"></i> ${esc(d.chosen_option)}</div>`
                    : ''}
                <div class="lm-card-tags">
                    ${(d.tags || []).map(t => `<span class="lm-tag">${esc(t)}</span>`).join('')}
                </div>
                <div class="lm-card-date">${timeAgo(d.updated_at || d.created_at)}</div>
            </div>
        `).join('');

        scroll.querySelectorAll('.lm-artifact-card').forEach(card => {
            card.addEventListener('click', () => selectArtifact(card.dataset.id));
        });
    }

    // ── Search ────────────────────────────────────────────────────────────────
    function applySearch(query) {
        const q = query.toLowerCase().trim();
        _filtered = q
            ? _artifacts.filter(d =>
                d.title?.toLowerCase().includes(q) ||
                (d.tags || []).some(t => t.toLowerCase().includes(q)) ||
                d.chosen_option?.toLowerCase().includes(q))
            : _artifacts;
        renderList(_filtered);
    }

    // ── Select & load a artifact ──────────────────────────────────────────────
    async function selectArtifact(id) {
        if (_activeId === id) return;
        _activeId = id;

        // Highlight card
        document.querySelectorAll('.lm-artifact-card').forEach(c =>
            c.classList.toggle('active', c.dataset.id === id));

        // Enable Ask inputs
        const textarea = $('lm-ask-textarea');
        const sendBtn  = $('lm-ask-send-btn');
        if (textarea) textarea.disabled = false;
        if (sendBtn)  sendBtn.disabled  = false;

        // Reset Ask panel
        const output = $('lm-ask-output');
        if (output) {
            output.innerHTML = `
                <div class="lm-ask-placeholder" id="lm-ask-placeholder">
                    <i class="fas fa-comments"></i>
                    Ask a question about this artifact.
                </div>`;
        }

        // Show loading state in detail pane
        const empty   = $('lm-detail-empty');
        const content = $('lm-detail-content');
        if (empty)   empty.style.display   = 'none';
        if (content) content.style.display = 'none';

        const scroll = $('lm-detail-scroll');
        if (scroll && !scroll.querySelector('#lm-detail-loading')) {
            const loading = document.createElement('div');
            loading.id = 'lm-detail-loading';
            loading.className = 'lm-loading';
            loading.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading…';
            scroll.appendChild(loading);
        }

        try {
            const res      = await fetch(`${API}/${id}`);
            const artifact = await res.json();
            renderDetail(artifact);
        } catch (err) {
            if (content) {
                content.style.display = '';
                content.innerHTML = `<div class="lm-error-banner"><i class="fas fa-circle-exclamation"></i> Failed to load artifact.</div>`;
            }
        } finally {
            const loading = $('lm-detail-loading');
            if (loading) loading.remove();
        }
    }

    // ── Render detail view ────────────────────────────────────────────────────
    async function renderDetail(d) {
        const content = $('lm-detail-content');
        if (!content) return;

        // Fetch linked artifact titles for display
        const linksHtml = await buildLinksHtml(d.links || []);

        content.innerHTML = `
            <div class="lm-detail-header">
                <div class="lm-detail-title">${esc(d.title)}</div>
                <div class="lm-detail-actions">
                    <button class="lm-icon-btn" id="lm-edit-btn" title="Edit artifact">
                        <i class="fas fa-pen"></i>
                    </button>
                    <button class="lm-icon-btn danger" id="lm-delete-btn" title="Delete artifact">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>

            <div class="lm-detail-meta">
                <span class="lm-meta-chip">
                    <i class="fas fa-scale-balanced"></i> ${esc(d.artifact_type)}
                </span>
                ${d.jurisdiction ? `
                <span class="lm-meta-chip">
                    <i class="fas fa-globe"></i> ${esc(d.jurisdiction)}
                </span>` : ''}
                <span class="lm-meta-chip">
                    <i class="fas fa-clock"></i> Created ${timeAgo(d.created_at)}
                </span>
                ${(d.tags || []).map(t => `<span class="lm-tag">${esc(t)}</span>`).join('')}
            </div>

            ${d.content ? `
            <div class="lm-section">
                <div class="lm-section-label"><i class="fas fa-file-lines"></i> Legal Content / Summary</div>
                <div class="lm-section-text">${esc(d.content)}</div>
            </div>` : ''}

            ${linksHtml ? `
            <div class="lm-section">
                <div class="lm-section-label"><i class="fas fa-link"></i> Connected Precedents</div>
                <div class="lm-links-grid">${linksHtml}</div>
            </div>` : ''}
        `;

        content.style.display = '';

        // Wire edit / delete
        const editBtn   = $('lm-edit-btn');
        const deleteBtn = $('lm-delete-btn');
        if (editBtn)   editBtn.addEventListener('click',   () => openModal(d));
        if (deleteBtn) deleteBtn.addEventListener('click', () => deleteArtifact(d.id));
    }

    async function buildLinksHtml(links) {
        if (!links?.length) return '';
        // Use cached list data if available
        return links.map(link => {
            const cached = _artifacts.find(d => d.id === link.to_id);
            const title  = cached?.title || link.to_id;
            return `<div class="lm-link-chip" data-linked-id="${esc(link.to_id)}">
                <span class="lm-link-edge">${esc(link.edge_type)}</span>
                <i class="fas fa-arrow-right"></i>
                ${esc(title)}
            </div>`;
        }).join('');
    }

    // ── Delete artifact ───────────────────────────────────────────────────────
    async function deleteArtifact(id) {
        if (!confirm('Delete this legal artifact? This cannot be undone.')) return;
        try {
            await fetch(`${API}/${id}`, { method: 'DELETE' });
            _activeId = null;
            const empty   = $('lm-detail-empty');
            const content = $('lm-detail-content');
            if (empty)   empty.style.display   = '';
            if (content) content.style.display = 'none';
            const textarea = $('lm-ask-input');
            const sendBtn  = $('lm-ask-btn');
            if (textarea) textarea.disabled = true;
            if (sendBtn)  sendBtn.disabled  = true;
            await loadArtifacts();
        } catch (err) {
            alert('Failed to delete artifact. Please try again.');
        }
    }

    // ── Modal: open ───────────────────────────────────────────────────────────
    function openModal(artifact = null) {
        _editingId = artifact ? artifact.id : null;
        const titleText = $('lm-modal-title-text');
        if (titleText) titleText.textContent = artifact ? 'Edit Legal Artifact' : 'New Legal Artifact';

        // Populate fields
        $('lm-form-title').value        = artifact?.title         || '';
        $('lm-form-type').value         = artifact?.artifact_type || 'Case';
        $('lm-form-jurisdiction').value = artifact?.jurisdiction  || '';
        $('lm-form-tags').value         = (artifact?.tags         || []).join(', ');
        $('lm-form-content').value      = artifact?.content       || '';

        const overlay = $('lm-modal-overlay');
        if (overlay) overlay.style.display = 'flex';
        setTimeout(() => { const t = $('lm-form-title'); if (t) t.focus(); }, 50);
    }

    // ── Modal: close ──────────────────────────────────────────────────────────
    function closeModal() {
        const overlay = $('lm-modal-overlay');
        if (overlay) overlay.style.display = 'none';
        _editingId = null;
    }

    // ── Modal: save ───────────────────────────────────────────────────────────
    async function saveArtifact() {
        const title = $('lm-form-title')?.value.trim();
        if (!title) { alert('Title is required.'); return; }

        const saveBtn = $('lm-modal-save');
        if (saveBtn) { saveBtn.disabled = true; saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…'; }

        const body = {
            title,
            artifact_type: $('lm-form-type')?.value       || 'Case',
            jurisdiction:  $('lm-form-jurisdiction')?.value.trim() || '',
            tags:          splitCommas($('lm-form-tags')?.value || ''),
            content:       $('lm-form-content')?.value.trim() || '',
            // links are preserved if editing, empty if new
        };

        try {
            if (_editingId) {
                await fetch(`${API}/${_editingId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                closeModal();
                await loadArtifacts();
                await selectArtifact(_editingId);
            } else {
                const res  = await fetch(`${API}/create`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const data = await res.json();
                closeModal();
                await loadArtifacts();
                await selectArtifact(data.id);
            }
        } catch (err) {
            alert('Failed to save artifact. Please try again.');
        } finally {
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.innerHTML = '<i class="fas fa-floppy-disk"></i> Save Artifact';
            }
        }
    }

    // ── Ask (streaming) ───────────────────────────────────────────────────────
    async function sendAsk() {
        if (!_activeId) return;
        const textarea = $('lm-ask-input');
        const sendBtn  = $('lm-ask-btn');
        const output   = $('lm-ask-output');
        const modelSel = $('lm-ask-model');

        const question = textarea?.value.trim();
        if (!question) return;

        if (sendBtn) { sendBtn.disabled = true; sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; }
        if (textarea) { textarea.disabled = true; }

        // Clear output and start fresh
        if (output) {
            output.innerHTML = `<div id="lm-ask-response" style="white-space:pre-wrap;"></div><span class="lm-cursor"></span>`;
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
            const respEl  = $('lm-ask-response');
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
                            const cursor = output?.querySelector('.lm-cursor');
                            if (cursor) cursor.remove();
                        }
                    } catch (_) { /* ignore parse errors */ }
                }
            }

        } catch (err) {
            if (output) output.innerHTML = `<div class="lm-error-banner"><i class="fas fa-circle-exclamation"></i> ${esc(err.message)}</div>`;
        } finally {
            if (sendBtn) { sendBtn.disabled = false; sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Ask'; }
            if (textarea) { textarea.disabled = false; textarea.value = ''; }
        }
    }

    // ── Graph pane ────────────────────────────────────────────────────────────
    async function loadGraph() {
        const wrap    = $('lm-graph-canvas-wrap');
        const nodes   = $('lm-graph-nodes');
        const loading = $('lm-graph-loading');

        if (loading) loading.style.display = 'flex';
        if (nodes)   nodes.style.display   = 'none';

        try {
            const res  = await fetch(`${API}/graph/all`);
            const data = await res.json();
            renderGraph(data);
        } catch (err) {
            if (wrap) wrap.innerHTML = `<div class="lm-error-banner"><i class="fas fa-circle-exclamation"></i> Failed to load graph.</div>`;
        }
    }

    function renderGraph(data) {
        const loading = $('lm-graph-loading');
        const nodeEl  = $('lm-graph-nodes');

        if (loading) loading.style.display = 'none';
        if (!nodeEl) return;

        const { nodes = [], edges = [] } = data;
        const edgeMap = {};
        edges.forEach(e => {
            edgeMap[e.from] = edgeMap[e.from] || [];
            edgeMap[e.from].push(e.to);
        });

        if (!nodes.length) {
            nodeEl.innerHTML = `<div class="lm-graph-empty"><i class="fas fa-circle-nodes" style="font-size:28px;opacity:0.3;display:block;margin-bottom:10px;"></i>No artifacts yet. Create some to see the graph.</div>`;
            nodeEl.style.display = '';
            return;
        }

        nodeEl.innerHTML = nodes.map(n => {
            const links = edgeMap[n.id] || [];
            return `
                <div class="lm-graph-node" data-node-id="${esc(n.id)}">
                    <div class="lm-graph-node-title">${esc(n.title)}</div>
                    ${n.chosen_option ? `<div class="lm-graph-node-chosen"><i class="fas fa-check-circle"></i> ${esc(n.chosen_option)}</div>` : ''}
                    ${links.length ? `<div class="lm-graph-node-links"><i class="fas fa-link"></i> ${links.length} link${links.length > 1 ? 's' : ''}</div>` : ''}
                </div>`;
        }).join('');

        nodeEl.style.display = 'flex';

        // Click on graph node → switch to artifacts pane and open it
        nodeEl.querySelectorAll('.lm-graph-node').forEach(node => {
            node.addEventListener('click', async () => {
                switchTab('artifacts');
                await selectArtifact(node.dataset.nodeId);
            });
        });
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        // Register info content for the ExpInfo overlay
        if (window.ExpInfo) {
            window.ExpInfo.register('lexmap', {
                icon:    'fas fa-timeline',
                name:    'LexMap',
                color:   'linear-gradient(135deg, #6366f1, #7c3aed)',
                tagline: 'Organisational artifact provenance — capture not just what was decided, but why.',
                status:  'Experimental',
                concepts: [
                    {
                        icon:  'fas fa-timeline',
                        label: 'Artifact Provenance Graph',
                        desc:  'Artifacts are typed entities linked to each other. You can traverse why things are the way they are, across months or years.',
                    },
                    {
                        icon:  'fas fa-scale-balanced',
                        label: 'Structured Reasoning Records',
                        desc:  'Each artifact captures options considered, constraints, trade-offs, and stakeholders — not just the outcome.',
                    },
                    {
                        icon:  'fas fa-wand-magic-sparkles',
                        label: 'AI-Assisted Analysis',
                        desc:  'Ask the AI about any artifact — it receives the full artifact graph as structured context, not raw text.',
                    },
                ],
                how: 'Artifacts are stored as typed JSON entities locally. Each entry holds the context, the options that were considered, the chosen option, the constraints that existed, the trade-offs that were accepted, and the stakeholders involved. Artifacts can be linked to each other to form a causal chain. The AI "Ask" feature sends the full artifact plus all linked artifacts as structured context — there is no retrieval guesswork, the model sees exactly what is relevant.',
                vision: 'LexMap is the personal-to-team evolution of AethvionDB. Where AethvionDB captures knowledge entities, LexMap captures reasoning chains. The long-term vision is an organisation-wide artifact intelligence layer: when someone asks "why is X like this?", the answer is a graph traversal — deterministic, instant, and complete — not a search through Confluence pages. If validated here, it will spin out as a standalone product targeting engineering organisations, law firms, and hospitals where the cost of lost institutional memory is highest.',
                pitch: {
                    problem: 'Organisations lose institutional memory constantly. When people leave, the "why" behind architecture or business artifacts leaves with them. Reading old Jira tickets or Confluence pages provides what was done, but rarely the constraints or rejected options that drove the artifact.',
                    solution: 'LexMap enforces a structured schema for recording artifacts (options, constraints, trade-offs) and links them into a causal graph. AI can then query this structured graph to explain past reasoning instantly to new employees.',
                    tam: 'Enterprise Knowledge Management & Artifact Intelligence: $8.5B+ (Growing 18% YoY). Target: Engineering leadership, Product Management, Legal teams.',
                    tactics: [
                        'Provide Jira and GitHub integrations to capture artifacts where work happens.',
                        'Target Engineering Managers and CTOs with a focus on reducing onboarding time.',
                        'Offer enterprise SSO and compliance-grade audit logging for regulated industries.'
                    ]
                }
            });
        }

        // Info button
        $('lm-info-btn')?.addEventListener('click', () => {
            if (window.ExpInfo) window.ExpInfo.show('lexmap');
        });

        // Tab switcher
        document.querySelectorAll('.lm-nav-tab').forEach(btn => {
            btn.addEventListener('click', () => switchTab(btn.dataset.lmTab));
        });

        // Search
        const searchInput = $('lm-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                clearTimeout(_searchTimer);
                _searchTimer = setTimeout(() => applySearch(searchInput.value), 180);
            });
        }

        // New artifact button
        const newBtn = $('lm-new-btn');
        if (newBtn) newBtn.addEventListener('click', () => openModal());

        // Modal controls
        $('lm-modal-close')?.addEventListener('click',  closeModal);
        $('lm-modal-cancel')?.addEventListener('click', closeModal);
        $('lm-modal-save')?.addEventListener('click',   saveArtifact);
        $('lm-modal-overlay')?.addEventListener('click', e => {
            if (e.target === $('lm-modal-overlay')) closeModal();
        });

        // Ask panel
        const sendBtn  = $('lm-ask-btn');
        const textarea = $('lm-ask-input');
        if (sendBtn)  sendBtn.addEventListener('click', sendAsk);
        if (textarea) textarea.addEventListener('keydown', e => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                sendAsk();
            }
        });

        // Graph refresh
        $('lm-graph-refresh')?.addEventListener('click', loadGraph);

        // Linked artifact click → navigate
        document.addEventListener('click', e => {
            const chip = e.target.closest('[data-linked-id]');
            if (chip) selectArtifact(chip.dataset.linkedId);
        });

        // Initial load
        loadArtifacts();
    }

    // Wait for DOM to be ready (panelLoaded event or DOMContentLoaded)
    if (document.getElementById('lm-root')) {
        init();
    } else {
        document.addEventListener('panelLoaded', function handler(e) {
            if (e.detail?.tabName === 'lexmap') {
                document.removeEventListener('panelLoaded', handler);
                init();
            }
        });
    }

})();
